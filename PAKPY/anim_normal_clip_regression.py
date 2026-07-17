import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

CONTROL_WORD_CANDIDATE = bytes.fromhex('1c000000')
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


def track_field(chunk, names):
    count = len(names)
    raw_value = int.from_bytes(chunk, 'big')
    bone_mask = (1 << count) - 1 if count else 0
    bone_bits = raw_value & bone_mask
    high_metadata = raw_value >> count if count else raw_value
    active_indices = [index for index in range(count) if bone_bits & (1 << index)]
    return {
        'raw_hex': chunk.hex(),
        'raw_value': raw_value,
        'bone_bits_value': bone_bits,
        'bone_bits_hex': f'{bone_bits:0{len(chunk) * 2}x}',
        'high_metadata_value': high_metadata,
        'high_metadata_bit_count': max(0, len(chunk) * 8 - count),
        'active_indices': active_indices,
        'active_names': [names[index] for index in active_indices],
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
    fields = [track_field(body[:width], names), track_field(body[width:required], names)]
    active = []
    state_counts = Counter()
    states = []
    for index, name in enumerate(names):
        state = ((fields[0]['bone_bits_value'] >> index) & 1) | (((fields[1]['bone_bits_value'] >> index) & 1) << 1)
        state_counts[state] += 1
        item = {'index': index, 'name': name, 'state': state}
        states.append(item)
        if state:
            active.append(item)
    return {
        'status': 'ok:two_track_state_bitplanes',
        'name_count': len(names),
        'field_width': width,
        'field_bytes': required,
        'fields': fields,
        'track_states': {
            'state_counts': {str(state): state_counts.get(state, 0) for state in range(4)},
            'active_indices': [item['index'] for item in active],
            'active_names': [item['name'] for item in active],
            'active_channels': active,
        },
    }


def compact_descriptor_candidate(body, frame_count, fields, aligned_offsets):
    if fields.get('status') != 'ok:two_track_state_bitplanes' or frame_count != 2 or len(aligned_offsets) != 1:
        return None
    active = fields['track_states']['active_channels']
    if not active:
        return None
    start = fields['field_bytes']
    end = aligned_offsets[0]
    descriptor = body[start:end]
    expected = len(active) * 8
    exact = len(descriptor) == expected
    descriptors = []
    if exact:
        for channel_index, channel in enumerate(active):
            raw = descriptor[channel_index * 8:(channel_index + 1) * 8]
            descriptors.append({
                'channel_index': channel_index,
                'bone_index': channel['index'],
                'bone_name': channel['name'],
                'track_state': channel['state'],
                'raw_hex': raw.hex(),
                'word0_u32be': int.from_bytes(raw[:4], 'big'),
                'word1_u32be': int.from_bytes(raw[4:], 'big'),
            })
    return {
        'status': 'ok:two_frame_static_descriptor_shape' if exact else 'pending:two_frame_descriptor_shape_mismatch',
        'control_word_offset': end,
        'descriptor_size': len(descriptor),
        'expected_descriptor_size': expected,
        'descriptors': descriptors,
        'warning': 'The control word is used only to recognize this exact compact shape; it is not a universal frame boundary.',
    }


def semantic_anchor_errors(path, fields):
    if fields.get('status') != 'ok:two_track_state_bitplanes':
        return []
    lower = path.name.lower()
    actual = set(fields['track_states']['active_names'])
    expected = None
    label = None
    if 'add_shift_' in lower and 'urchin' in lower:
        expected = {'eye_r_skin', 'eye_l_skin'}
        label = 'urchin_eye_shift'
    elif 'add_blink_urchin' in lower:
        expected = {
            'eyelid_top_l_skin',
            'eyelid_top_r_skin',
            'eyelid_bottom_r_skin',
            'eyelid_bottom_l_skin',
        }
        label = 'urchin_blink'
    if expected is None or actual == expected:
        return []
    return [{
        'path': str(path),
        'anchor': label,
        'expected_active_names': sorted(expected),
        'actual_active_names': sorted(actual),
    }]


def inspect_anim(path, name_cache):
    data = path.read_bytes()
    control = u32be(data, 0x28)
    body = data[BODY_OFFSET:] if len(data) >= BODY_OFFSET else b''
    used = body.rstrip(b'\x00')
    occurrences = find_offsets(body, CONTROL_WORD_CANDIDATE)
    aligned = [offset for offset in occurrences if offset % 4 == 0]
    names = skeleton_names(path, name_cache)
    fields = prefix_fields(body, names)
    frame_count = control & 0xff
    compact = compact_descriptor_candidate(body, frame_count, fields, aligned)
    anchors = semantic_anchor_errors(path, fields)
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
        'control_word_candidate_count': len(occurrences),
        'control_word_candidate_offsets': occurrences,
        'aligned_control_word_offsets': aligned,
        'normal_clip_prefix': fields,
        'compact_two_frame_descriptor_candidate': compact,
        'semantic_anchor_errors': anchors,
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
    parser = argparse.ArgumentParser(description='Inspect DKCTF 0x81 ANIM track-state bitplanes without fabricating transform tracks.')
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
            item_ok = (item.get('normal_clip_prefix') or {}).get('status') == 'ok:two_track_state_bitplanes'
            current_ok = current and (current.get('normal_clip_prefix') or {}).get('status') == 'ok:two_track_state_bitplanes'
            if current is None or (item_ok and not current_ok):
                unique[item['sha1']] = item

    clips = list(unique.values())
    prefix_ok = [item for item in clips if item['normal_clip_prefix'].get('status') == 'ok:two_track_state_bitplanes']
    compact_ok = [item for item in clips if (item.get('compact_two_frame_descriptor_candidate') or {}).get('status') == 'ok:two_frame_static_descriptor_shape']
    anchor_errors = [error for item in clips for error in item.get('semantic_anchor_errors') or []]
    by_control = Counter(item['control'] for item in clips)
    by_hash = defaultdict(int)
    high_metadata_pairs = Counter()
    for item in clips:
        by_hash[item['group_hash']] += 1
        prefix = item.get('normal_clip_prefix') or {}
        if prefix.get('status') == 'ok:two_track_state_bitplanes':
            values = tuple(field['high_metadata_value'] for field in prefix['fields'])
            high_metadata_pairs[str(values)] += 1

    report = {
        'version': 3,
        'type': 'DKCTF_NORMAL_CLIP_REGRESSION',
        'control_word_candidate_hex': CONTROL_WORD_CANDIDATE.hex(),
        'body_offset': BODY_OFFSET,
        'unique_normal_clip_count': len(clips),
        'track_state_bitplane_count': len(prefix_ok),
        'compact_two_frame_descriptor_count': len(compact_ok),
        'semantic_anchor_error_count': len(anchor_errors),
        'error_count': len(errors),
        'controls': dict(sorted(by_control.items())),
        'group_hash_counts': dict(sorted(by_hash.items())),
        'control_word_occurrence_histogram': dict(sorted(Counter(item['control_word_candidate_count'] for item in clips).items())),
        'high_metadata_pair_histogram': dict(sorted(high_metadata_pairs.items())),
        'semantic_anchor_errors': anchor_errors,
        'clips': clips,
        'errors': errors,
        'warning': 'This report validates bone bit mapping, preserves high metadata bits, and recognizes a compact descriptor shape. Transform/quaternion decoding is still pending; 1c000000 is not treated as a universal frame delimiter.',
    }
    out = Path(args.output)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    print(f'Wrote {out}')
    print(f'Unique 0x81 clips: {len(clips)}')
    print(f'Track-state bitplanes: {len(prefix_ok)}')
    print(f'Compact two-frame descriptors: {len(compact_ok)}')
    print(f'Semantic anchor errors: {len(anchor_errors)}')
    print(f'Errors: {len(errors)}')


if __name__ == '__main__':
    main()
