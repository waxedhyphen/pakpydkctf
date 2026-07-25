from collections import Counter


def _named_items(source, fallback_prefix):
    out = []
    for index, item in enumerate(source or []):
        if isinstance(item, dict):
            out.append(str(item.get('name', '') or f'{fallback_prefix}_{index}'))
        else:
            out.append(str(item or f'{fallback_prefix}_{index}'))
    return out


def _prefix_bytes(probe):
    body = probe.get('body') or {}
    value = body.get('prefix_hex', '') if isinstance(body, dict) else ''
    if not value:
        value = probe.get('body_used_hex_prefix_160', '') or ''
    try:
        return bytes.fromhex(value)
    except Exception:
        return b''


def _track_field(chunk, names, field_index):
    count = len(names)
    bit_capacity = len(chunk) * 8
    top_control_index = bit_capacity - 1
    raw_value = int.from_bytes(chunk, 'big')
    named_indices = [index for index in range(count) if raw_value & (1 << index)]
    auxiliary_indices = [
        index for index in range(count, top_control_index)
        if raw_value & (1 << index)
    ]
    top_control_set = bool(raw_value & (1 << top_control_index)) if top_control_index >= 0 else False
    return {
        'field_index': field_index,
        'raw_hex': chunk.hex(),
        'raw_value': raw_value,
        'bit_capacity': bit_capacity,
        'named_indices': named_indices,
        'named_names': [names[index] for index in named_indices],
        'auxiliary_indices': auxiliary_indices,
        'top_control_index': top_control_index,
        'top_control_set': top_control_set,
        'descriptor_slot_count_candidate': len(named_indices) + len(auxiliary_indices),
        'bit_mapping': 'big_endian_integer_lsb_is_skeleton_name_index_0',
    }


def _track_states(fields, names):
    states = []
    counts = Counter()
    active = []
    first = fields[0]['raw_value']
    second = fields[1]['raw_value']
    for index, name in enumerate(names):
        state = ((first >> index) & 1) | (((second >> index) & 1) << 1)
        counts[state] += 1
        item = {'index': index, 'name': name, 'state': state}
        states.append(item)
        if state:
            active.append(item)
    return {
        'state_counts': {str(state): counts.get(state, 0) for state in range(4)},
        'active_count': len(active),
        'active_indices': [item['index'] for item in active],
        'active_names': [item['name'] for item in active],
        'active_channels': active,
        'all_channels': states,
        'state_semantics': 'pending',
    }


def _descriptor_slot_order(fields, names):
    if not fields:
        return []
    top_control_index = fields[0]['top_control_index']
    slots = []
    for bit_index in range(top_control_index):
        for field in fields:
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


def _packed_record_candidate(raw, slot):
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
        'record_semantics': 'candidate_only',
    }


def _short_packed_block_candidate(probe, prefix, field_bytes, slots):
    body_size = int(probe.get('body_size') or 0)
    if not body_size or not slots:
        return None
    table_size = len(slots) * 8
    table_end = field_bytes + table_size
    tail_size = body_size - table_end
    short_shape = 0 <= tail_size <= 16
    available = len(prefix) >= table_end
    records = []
    if short_shape and available:
        table = prefix[field_bytes:table_end]
        for index, slot in enumerate(slots):
            raw = table[index * 8:(index + 1) * 8]
            records.append(_packed_record_candidate(raw, slot))
    return {
        'status': 'ok:short_fixed8_packed_block_candidate' if short_shape and available else 'pending:not_short_fixed8_shape',
        'descriptor_stride_candidate': 8,
        'descriptor_slot_count_candidate': len(slots),
        'descriptor_table_offset_candidate': field_bytes,
        'descriptor_table_size_candidate': table_size,
        'descriptor_table_end_candidate': table_end,
        'tail_size_after_candidate': tail_size,
        'prefix_has_candidate_table': available,
        'slot_order_candidate': slots,
        'records': records,
        'note': 'Only short clips whose complete candidate table fits before at most 16 tail bytes are materialized. The 8-byte record and delta-width interpretation remain candidates, not decoded transforms.',
    }


def _normal_clip_layout(probe, skel):
    names = _named_items(skel.get('names') or [], 'name')
    prefix = _prefix_bytes(probe)
    width = (len(names) + 7) // 8 if names else 0
    field_bytes = width * 2
    if not width:
        return {'version': 5, 'status': 'pending:missing_skeleton_names', 'name_count': 0}
    if len(prefix) < field_bytes:
        return {
            'version': 5,
            'status': 'pending:short_normal_clip_prefix',
            'name_count': len(names),
            'field_width': width,
            'required_prefix_bytes': field_bytes,
            'available_prefix_bytes': len(prefix),
        }
    chunks = [prefix[0:width], prefix[width:field_bytes]]
    fields = [_track_field(chunk, names, index) for index, chunk in enumerate(chunks)]
    states = _track_states(fields, names)
    slots = _descriptor_slot_order(fields, names)
    short_block = _short_packed_block_candidate(probe, prefix, field_bytes, slots)
    return {
        'version': 5,
        'status': 'ok:two_track_state_bitplanes',
        'semantics_status': 'pending:track_roles_and_packed_transform_codec',
        'name_count': len(names),
        'field_count': 2,
        'field_width': width,
        'field_bytes': field_bytes,
        'fields': fields,
        'track_states': states,
        'descriptor_slots_candidate': slots,
        'payload_prefix_hex': prefix[field_bytes:field_bytes + 128].hex(),
        'normal_clip_header': probe.get('normal_clip_header') or {},
        'stream_probe': probe.get('frame_marker_probe') or {},
        'short_packed_block_candidate': short_block,
        'note': 'Name bits, auxiliary bits below the top control bit, and the top control bit are reported separately. No transform values are emitted until the packed codec is validated.',
    }


def install_into():
    mapping_module = __import__('anim_track_skel_map_patch')
    if getattr(mapping_module, '_normal_clip_structure_installed', False):
        return
    old_apply = mapping_module._apply_mapping

    def apply_mapping(probe, skel, skel_file):
        is_normal = probe.get('raw_family') == 'normal_clip'
        layout = _normal_clip_layout(probe, skel) if is_normal else None
        if layout is not None:
            probe['normal_clip_layout'] = layout
            track_decode = probe.get('track_decode') or {}
            track_decode['normal_clip_layout'] = layout
            probe['track_decode'] = track_decode
        result = old_apply(probe, skel, skel_file)
        if layout is not None:
            mapping = result.get('track_skeleton_map') or {}
            mapping['normal_clip_layout'] = layout
            mapping['status'] = 'pending:normal_clip_packed_transform_codec'
            mapping['note'] = 'root_transform_header_and_track_bitplanes_parsed; packed_transform_decode_pending'
            mapping['groups'] = []
            mapping['absolute_frame_count'] = 0
            result['track_skeleton_map'] = mapping
        return result

    mapping_module._apply_mapping = apply_mapping
    mapping_module._normal_clip_structure_installed = True
