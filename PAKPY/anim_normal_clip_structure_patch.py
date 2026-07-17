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


def _track_field(chunk, names):
    count = len(names)
    raw_value = int.from_bytes(chunk, 'big')
    bone_mask = (1 << count) - 1 if count else 0
    bone_bits = raw_value & bone_mask
    high_metadata = raw_value >> count if count else raw_value
    active_indices = [index for index in range(count) if bone_bits & (1 << index)]
    return {
        'raw_hex': chunk.hex(),
        'raw_value': raw_value,
        'bone_count': count,
        'bone_bits_value': bone_bits,
        'bone_bits_hex': f'{bone_bits:0{len(chunk) * 2}x}',
        'high_metadata_value': high_metadata,
        'high_metadata_bit_count': max(0, len(chunk) * 8 - count),
        'active_count': len(active_indices),
        'active_indices': active_indices,
        'active_names': [names[index] for index in active_indices],
        'bit_mapping': 'big_endian_integer_lsb_is_bone_index_0',
    }


def _track_states(fields, names):
    states = []
    counts = Counter()
    active = []
    first = fields[0]['bone_bits_value']
    second = fields[1]['bone_bits_value']
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


def _compact_descriptor_candidate(probe, prefix, field_bytes, track_states):
    frame_count = int(probe.get('frame_count_guess') or 0)
    stream = probe.get('frame_marker_probe') or {}
    offsets = stream.get('aligned_control_word_offsets') or stream.get('aligned_marker_offsets') or []
    active = track_states.get('active_channels') or []
    if frame_count != 2 or len(offsets) != 1 or not active:
        return None
    control_offset = int(offsets[0])
    descriptor_size = control_offset - field_bytes
    expected_size = len(active) * 8
    exact = bool(control_offset >= field_bytes and descriptor_size == expected_size)
    descriptor_bytes = prefix[field_bytes:control_offset]
    descriptors = []
    if exact and len(descriptor_bytes) >= expected_size:
        for channel_index, channel in enumerate(active):
            raw = descriptor_bytes[channel_index * 8:(channel_index + 1) * 8]
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
        'control_word_offset': control_offset,
        'field_bytes': field_bytes,
        'descriptor_size': max(0, descriptor_size),
        'expected_descriptor_size': expected_size,
        'descriptor_stride': 8,
        'descriptors': descriptors,
        'descriptor_semantics': 'pending:packed_transform_descriptor',
        'note': 'This recognizes only the exact compact two-frame shape. The 1c000000 occurrence is not treated as a universal frame boundary.',
    }


def _normal_clip_layout(probe, skel):
    names = _named_items(skel.get('names') or [], 'name')
    prefix = _prefix_bytes(probe)
    width = (len(names) + 7) // 8 if names else 0
    field_bytes = width * 2
    if not width:
        return {
            'version': 4,
            'status': 'pending:missing_skeleton_names',
            'name_count': 0,
        }
    if len(prefix) < field_bytes:
        return {
            'version': 4,
            'status': 'pending:short_normal_clip_prefix',
            'name_count': len(names),
            'field_width': width,
            'required_prefix_bytes': field_bytes,
            'available_prefix_bytes': len(prefix),
        }
    chunks = [prefix[0:width], prefix[width:field_bytes]]
    fields = [_track_field(chunk, names) for chunk in chunks]
    states = _track_states(fields, names)
    compact = _compact_descriptor_candidate(probe, prefix, field_bytes, states)
    return {
        'version': 4,
        'status': 'ok:two_track_state_bitplanes',
        'semantics_status': 'pending:track_state_meaning_and_packed_transform_codec',
        'name_count': len(names),
        'field_count': 2,
        'field_width': width,
        'field_bytes': field_bytes,
        'fields': fields,
        'track_states': states,
        'payload_prefix_hex': prefix[field_bytes:field_bytes + 96].hex(),
        'stream_probe': probe.get('frame_marker_probe') or {},
        'compact_two_frame_descriptor_candidate': compact,
        'note': 'The low name_count bits of each big-endian field map to skeleton names with integer bit 0 as bone index 0. High unused bits are preserved as metadata, not discarded as padding. State roles and packed transforms remain unresolved.',
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
            mapping['note'] = 'track_state_bitplanes_parsed; high_metadata_preserved; packed_transform_decode_pending'
            mapping['groups'] = []
            mapping['absolute_frame_count'] = 0
            result['track_skeleton_map'] = mapping
        return result

    mapping_module._apply_mapping = apply_mapping
    mapping_module._normal_clip_structure_installed = True
