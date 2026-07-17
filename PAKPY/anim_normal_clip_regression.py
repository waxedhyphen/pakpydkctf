import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

CONTROL_WORD = bytes.fromhex('1c000000')
BODY_OFFSET = 0x54


def u32be(data, offset):
    if offset + 4 > len(data):
        return 0
    return int.from_bytes(data[offset:offset + 4], 'big')


def find_offsets(data, needle):
    result = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return result
        result.append(pos)
        start = pos + 1


def package_root_for_anim(path):
    for parent in path.parents:
        if (parent / 'source' / 'anim').is_dir():
            return parent
    return None


def skeleton_names(path, cache):
    root = package_root_for_anim(path)
    if root is None:
        return []
    key = str(root.resolve())
    if key in cache:
        return cache[key]
    paths = sorted((root / 'source' / 'skel').glob('*.json'))
    if not paths and (root / 'debug' / 'skeleton_debug.json').is_file():
        paths = [root / 'debug' / 'skeleton_debug.json']
    if not paths:
        cache[key] = []
        return []
    try:
        data = json.loads(paths[0].read_text(encoding='utf-8'))
        names = [str(item.get('name', '') or f'name_{index}') for index, item in enumerate(data.get('names') or [])]
    except Exception:
        names = []
    cache[key] = names
    return names


def field_bits(chunk, names):
    total_bits = len(chunk) * 8
    named = []
    reserved = []
    for physical_index in range(total_bits):
        if not chunk[physical_index >> 3] & (0x80 >> (physical_index & 7)):
            continue
        logical_index = total_bits - 1 - physical_index
        item = {
            'physical_msb_index': physical_index,
            'logical_reverse_padded_index': logical_index,
        }
        if logical_index < len(names):
            item['name'] = names[logical_index]
            named.append(item)
        else:
            reserved.append(item)
    return {
        'hex': chunk.hex(),
        'set_count': len(named) + len(reserved),
        'named_channels': named,
        'reserved_channels': reserved,
    }


def prefix_fields(body, names):
    width = (len(names) + 7) // 8 if names else 0
    required = width * 2
    if not width or len(body) < required:
        return {
            'status': 'pending:missing_or_short_skeleton_prefix',
            'name_count': len(names),
            'field_width': width,
        }
    fields = [field_bits(body[:width], names), field_bits(body[width:required], names)]
    return {
        'status': 'ok:two_skeleton_width_fields',
        'name_count': len(names),
        'field_width': width,
        'field_bytes': required,
        'fields': fields,
    }


def compact_candidate(body, frame_count, fields):
    if fields.get('status') != 'ok:two_skeleton_width_fields' or frame_count != 2:
        return None
    offsets = [offset for offset in find_offsets(body, CONTROL_WORD) if offset % 4 == 0]
    if len(offsets) != 1:
        return None
    start = fields['field_bytes']
    end = offsets[0]
    payload = body[start:end]
    named = []
    seen = set()
    for field in fields['fields']:
        for item in field['named_channels']:
            index = item['logical_reverse_padded_index']
            if index in seen:
                continue
            seen.add(index)
            named.append(item)
    exact = bool(
        len(payload) % 4 == 0
        and len(named) > 0
        and len(payload) == frame_count * len(named) * 4
    )
    words = [payload[index:index + 4].hex() for index in range(0, len(payload), 4)]
    return {
        'status': 'ok:two_frame_packed_u32_candidate' if exact else 'pending:two_frame_layout_mismatch',
        'control_word_offset': end,
        'payload_size': len(payload),
        'named_channel_count': len(named),
        'named_channel_order_candidate': named,
        'packed_u32be_words': words,
        'value_semantics': 'pending:packed_transform_decode',
    }


def inspect_anim(path, name_cache):
    data = path.read_bytes()
    control = u32be(data, 0x28)
    body = data[BODY_OFFSET:] if len(data) >= BODY_OFFSET else b''
    used = body.rstrip(b'\x00')
    all_markers = find_offsets(body, CONTROL_WORD)
    aligned = [offset for offset in all_markers if offset % 4 == 0]
    spans = [aligned[index + 1] - aligned[index] for index in range(len(aligned) - 1)]
    names = skeleton_names(path, name_cache)
    fields = prefix_fields(body, names)
    frame_count = control & 0xff
    compact = compact_candidate(body, frame_count, fields)
    return {
        'path': str(path),
        'sha1': hashlib.sha1(data).hexdigest(),
        'size': len(data),
        'valid_rfrm': data[:4] == b'RFRM',
        'format_magic': f'{u32be(data, 0x20):08x}',
        'control': f'{control:08x}',
        'family': f'{(control >> 24) & 0xff:02x}',
        'flags': f'{(control >> 16) & 0xff:02x}',
        'frame_count_low16': control & 0xffff,
        'frame_count_low8': frame_count,
        'group_hash': f'{u32be(data, 0x2c):08x}',
        'body_size': len(body),
        'body_used_size': len(used),
        'body_prefix_hex': used[:160].hex(),
        'aligned_control_word_count': len(aligned),
        'aligned_control_word_offsets': aligned,
        'unaligned_control_word_offsets': [offset for offset in all_markers if offset % 4],
        'prefix_size_before_first_control_word': aligned[0] if aligned else len(body),
        'record_spans': spans,
        'record_span_histogram': dict(sorted(Counter(spans).items())),
        'tail_size_after_last_control_word': len(body) - aligned[-1] if aligned else len(body),
        'normal_clip_prefix': fields,
        'compact_two_frame_candidate': compact,
    }


def discover(paths):
    files = []
    for raw in paths:
        path = Path(raw)
        if path.is_file() and path.suffix.lower() == '.anim':
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob('*.anim'))
    return sorted(set(files))


def main():
    parser = argparse.ArgumentParser(description='Inspect DKCTF 0x81 ANIM structure without fabricating transform tracks.')
    parser.add_argument('paths', nargs='+', help='ANIM files, package roots, or directories')
    parser.add_argument('-o', '--output', default='anim_normal_clip_regression_report.json')
    args = parser.parse_args()

    unique = {}
    errors = []
    name_cache = {}
    for path in discover(args.paths):
        try:
            item = inspect_anim(path, name_cache)
        except Exception as exc:
            errors.append({'path': str(path), 'error': str(exc)})
            continue
        if item['family'] == '81':
            current = unique.get(item['sha1'])
            item_ok = (item.get('normal_clip_prefix') or {}).get('status') == 'ok:two_skeleton_width_fields'
            current_ok = current and (current.get('normal_clip_prefix') or {}).get('status') == 'ok:two_skeleton_width_fields'
            if current is None or (item_ok and not current_ok):
                unique[item['sha1']] = item

    clips = list(unique.values())
    by_control = Counter(item['control'] for item in clips)
    by_hash = defaultdict(int)
    for item in clips:
        by_hash[item['group_hash']] += 1
    compact_ok = [
        item for item in clips
        if (item.get('compact_two_frame_candidate') or {}).get('status') == 'ok:two_frame_packed_u32_candidate'
    ]
    prefix_ok = [
        item for item in clips
        if (item.get('normal_clip_prefix') or {}).get('status') == 'ok:two_skeleton_width_fields'
    ]

    report = {
        'version': 2,
        'type': 'DKCTF_NORMAL_CLIP_REGRESSION',
        'control_word_hex': CONTROL_WORD.hex(),
        'body_offset': BODY_OFFSET,
        'unique_normal_clip_count': len(clips),
        'two_field_prefix_count': len(prefix_ok),
        'compact_two_frame_exact_count': len(compact_ok),
        'error_count': len(errors),
        'controls': dict(sorted(by_control.items())),
        'group_hash_counts': dict(sorted(by_hash.items())),
        'control_word_count_histogram': dict(sorted(Counter(item['aligned_control_word_count'] for item in clips).items())),
        'clips': clips,
        'errors': errors,
        'warning': 'This report decodes structure and raw packed words only. Quaternion/translation semantics are still pending.',
    }
    out = Path(args.output)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    print(f'Wrote {out}')
    print(f'Unique 0x81 clips: {len(clips)}')
    print(f'Two-field prefixes: {len(prefix_ok)}')
    print(f'Exact compact two-frame layouts: {len(compact_ok)}')
    print(f'Errors: {len(errors)}')


if __name__ == '__main__':
    main()
