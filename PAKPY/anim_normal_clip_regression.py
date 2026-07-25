import argparse
import hashlib
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path

CONTROL_WORD_CANDIDATE = bytes.fromhex('1c000000')
BODY_OFFSET = 0x54
ROOT_TRANSFORM_OFFSET = 0x37
ROOT_TRANSFORM_END = 0x53


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


def root_transform_header(data):
    if len(data) < BODY_OFFSET:
        return {'status': 'pending:short_anim_header', 'asset_size': len(data)}
    values = struct.unpack('>7f', data[ROOT_TRANSFORM_OFFSET:ROOT_TRANSFORM_END])
    quaternion = list(values[:4])
    translation = list(values[4:])
    finite = all(math.isfinite(value) for value in values)
    norm = math.sqrt(sum(value * value for value in quaternion)) if finite else None
    errors = []
    if not finite:
        errors.append('nonfinite_values')
    if norm is not None and not 0.5 <= norm <= 1.5:
        errors.append('implausible_quaternion_norm')
    return {
        'status': 'ok:root_transform_header' if not errors else 'pending:root_transform_header_validation',
        'prefix_hex': data[0x30:0x37].hex(),
        'quaternion_wxyz': quaternion,
        'quaternion_norm': norm,
        'translation_xyz': translation,
        'end_marker_u8': data[0x53],
        'errors': errors,
    }


def track_field(chunk, names, field_index):
    count = len(names)
    bit_capacity = len(chunk) * 8
    top_control_index = bit_capacity - 1
    raw_value = int.from_bytes(chunk, 'big')
    named_indices = [index for index in range(count) if raw_value & (1 << index)]
    auxiliary_indices = [index for index in range(count, top_control_index) if raw_value & (1 << index)]
    return {
        'field_index': field_index,
        'raw_hex': chunk.hex(),
        'raw_value': raw_value,
        'bit_capacity': bit_capacity,
        'named_indices': named_indices,
        'named_names': [names[index] for index in named_indices],
        'auxiliary_indices': auxiliary_indices,
        'top_control_index': top_control_index,
        'top_control_set': bool(raw_value & (1 << top_control_index)),
        'descriptor_slot_count_candidate': len(named_indices) + len(auxiliary_indices),
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
    fields = [track_field(body[index * width:(index + 1) * width], names, index) for index in range(2)]
    active = []
    state_counts = Counter()
    for index, name in enumerate(names):
        state = ((fields[0]['raw_value'] >> index) & 1) | (((fields[1]['raw_value'] >> index) & 1) << 1)
        state_counts[state] += 1
        if state:
            active.append({'index': index, 'name': name, 'state': state})
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


def descriptor_slot_order(fields, names):
    if fields.get('status') != 'ok:two_track_state_bitplanes':
        return []
    field_rows = fields['fields']
    top_control_index = field_rows[0]['top_control_index']
    slots = []
    for bit_index in range(top_control_index):
        for field in field_rows:
            if not field['raw_value'] & (1 << bit_index):
                continue
            item = {
                'slot_index': len(slots),
                'bit_index': bit_index,
                'field_index': field['field_index'],
                'slot_kind': 'named' if bit_index < len(names) else 'auxiliary',
            }
            if bit_index < len(names):
                item['name'] = names[bit_index]
            slots.append(item)
    return slots


def packed_record_candidate(raw, slot):
    initial_u16 = [int.from_bytes(raw[offset:offset + 2], 'big') for offset in (2, 4, 6)]
    initial_s16 = [value - 0x10000 if value & 0x8000 else value for value in initial_u16]
    return {
        **slot,
        'raw_hex': raw.hex(),
        'byte0': raw[0],
        'byte1': raw[1],
        'delta_width_candidate_xyz': [raw[0], raw[1] >> 4, raw[1] & 0x0F],
        'initial_u16be_candidate_xyz': initial_u16,
        'initial_s16be_candidate_xyz': initial_s16,
    }


def short_packed_block(body, fields, slots):
    if fields.get('status') != 'ok:two_track_state_bitplanes' or not slots:
        return None
    start = fields['field_bytes']
    table_size = len(slots) * 8
    end = start + table_size
    tail_size = len(body) - end
    short_shape = 0 <= tail_size <= 16
    records = []
    if short_shape:
        table = body[start:end]
        for index, slot in enumerate(slots):
            records.append(packed_record_candidate(table[index * 8:(index + 1) * 8], slot))
    return {
        'status': 'ok:short_fixed8_packed_block_candidate' if short_shape else 'pending:not_short_fixed8_shape',
        'table_offset_candidate': start,
        'table_size_candidate': table_size,
        'table_end_candidate': end,
        'tail_size_after_candidate': tail_size,
        'records': records,
        'warning': 'The fixed 8-byte record interpretation is restricted to short clips and remains a candidate. It is not used to emit transforms.',
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
    names = skeleton_names(path, name_cache)
    fields = prefix_fields(body, names)
    slots = descriptor_slot_order(fields, names)
    occurrences = find_offsets(body, CONTROL_WORD_CANDIDATE)
    header = root_transform_header(data)
    return {
        'path': str(path),
        'sha1': hashlib.sha1(data).hexdigest(),
        'size': len(data),
        'valid_rfrm': data[:4] == b'RFRM',
        'format_magic': f'{u32be(data, 0x20):08x}',
        'control': f'{control:08x}',
        'family': f'{(control >> 24) & 0xff:02x}',
        'flags': f'{(control >> 16) & 0xff:02x}',
        'frame_count_low8': control & 0xff,
        'group_hash': f'{u32be(data, 0x2c):08x}',
        'normal_clip_header': header,
        'body_size': len(body),
        'body_prefix_hex': body[:192].hex(),
        'control_word_candidate_count': len(occurrences),
        'control_word_candidate_offsets': occurrences,
        'normal_clip_prefix': fields,
        'descriptor_slots_candidate': slots,
        'short_packed_block_candidate': short_packed_block(body, fields, slots),
        'semantic_anchor_errors': semantic_anchor_errors(path, fields),
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
    parser = argparse.ArgumentParser(description='Inspect DKCTF 0x81 ANIM headers and track bitplanes without fabricating transforms.')
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
        if item['family'] != '81':
            continue
        current = unique.get(item['sha1'])
        item_ok = item['normal_clip_prefix'].get('status') == 'ok:two_track_state_bitplanes'
        current_ok = current and current['normal_clip_prefix'].get('status') == 'ok:two_track_state_bitplanes'
        if current is None or (item_ok and not current_ok):
            unique[item['sha1']] = item

    clips = list(unique.values())
    prefix_ok = [item for item in clips if item['normal_clip_prefix'].get('status') == 'ok:two_track_state_bitplanes']
    header_ok = [item for item in clips if item['normal_clip_header'].get('status') == 'ok:root_transform_header']
    short_ok = [item for item in clips if (item.get('short_packed_block_candidate') or {}).get('status') == 'ok:short_fixed8_packed_block_candidate']
    anchor_errors = [error for item in clips for error in item.get('semantic_anchor_errors') or []]
    header_errors = [
        {'path': item['path'], 'errors': item['normal_clip_header'].get('errors')}
        for item in clips if item['normal_clip_header'].get('errors')
    ]
    by_control = Counter(item['control'] for item in clips)
    by_hash = defaultdict(int)
    top_control_pairs = Counter()
    auxiliary_count_pairs = Counter()
    for item in clips:
        by_hash[item['group_hash']] += 1
        prefix = item.get('normal_clip_prefix') or {}
        if prefix.get('status') == 'ok:two_track_state_bitplanes':
            top_control_pairs[str(tuple(field['top_control_set'] for field in prefix['fields']))] += 1
            auxiliary_count_pairs[str(tuple(len(field['auxiliary_indices']) for field in prefix['fields']))] += 1

    report = {
        'version': 4,
        'type': 'DKCTF_NORMAL_CLIP_REGRESSION',
        'body_offset': BODY_OFFSET,
        'root_transform_offset': ROOT_TRANSFORM_OFFSET,
        'unique_normal_clip_count': len(clips),
        'root_transform_header_count': len(header_ok),
        'track_state_bitplane_count': len(prefix_ok),
        'short_fixed8_packed_block_candidate_count': len(short_ok),
        'semantic_anchor_error_count': len(anchor_errors),
        'root_transform_header_error_count': len(header_errors),
        'error_count': len(errors),
        'controls': dict(sorted(by_control.items())),
        'group_hash_counts': dict(sorted(by_hash.items())),
        'top_control_bit_pair_histogram': dict(sorted(top_control_pairs.items())),
        'auxiliary_slot_count_pair_histogram': dict(sorted(auxiliary_count_pairs.items())),
        'semantic_anchor_errors': anchor_errors,
        'root_transform_header_errors': header_errors,
        'clips': clips,
        'errors': errors,
        'warning': 'This report validates the root transform header, name-bit mapping, auxiliary slots, and short packed-block shapes. It does not decode quaternion/translation keys or create Blender actions.',
    }
    out = Path(args.output)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    print(f'Wrote {out}')
    print(f'Unique 0x81 clips: {len(clips)}')
    print(f'Root transform headers: {len(header_ok)}')
    print(f'Track-state bitplanes: {len(prefix_ok)}')
    print(f'Short fixed8 candidates: {len(short_ok)}')
    print(f'Semantic anchor errors: {len(anchor_errors)}')
    print(f'Header validation errors: {len(header_errors)}')
    print(f'Parser errors: {len(errors)}')


if __name__ == '__main__':
    main()
