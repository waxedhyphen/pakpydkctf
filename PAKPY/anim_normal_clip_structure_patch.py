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


def _field_bits(chunk, names):
    total_bits = len(chunk) * 8
    physical = []
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
        physical.append(physical_index)
        if logical_index < len(names):
            item['name'] = names[logical_index]
            named.append(item)
        else:
            reserved.append(item)
    return {
        'hex': chunk.hex(),
        'set_count': len(physical),
        'physical_msb_indices': physical,
        'named_channels': named,
        'reserved_channels': reserved,
    }


def _compact_candidate(probe, prefix, fields, field_bytes):
    stream = probe.get('frame_marker_probe') or {}
    offsets = stream.get('aligned_marker_offsets') or []
    frame_count = int(probe.get('frame_count_guess') or 0)
    if frame_count != 2 or len(offsets) != 1:
        return None
    marker_offset = int(offsets[0])
    payload = prefix[field_bytes:marker_offset]
    named = []
    seen = set()
    for field in fields:
        for item in field.get('named_channels') or []:
            key = item.get('logical_reverse_padded_index')
            if key in seen:
                continue
            seen.add(key)
            named.append(item)
    exact = bool(
        marker_offset >= field_bytes
        and len(payload) % 4 == 0
        and len(named) > 0
        and len(payload) == frame_count * len(named) * 4
    )
    words = [payload[index:index + 4].hex() for index in range(0, len(payload), 4)]
    frames = []
    if exact:
        cursor = 0
        for frame_index in range(frame_count):
            values = []
            for channel in named:
                values.append({
                    'name': channel.get('name', ''),
                    'logical_reverse_padded_index': channel.get('logical_reverse_padded_index'),
                    'packed_u32be_hex': words[cursor],
                })
                cursor += 1
            frames.append({'frame_index': frame_index, 'values': values})
    return {
        'status': 'ok:two_frame_packed_u32_candidate' if exact else 'pending:two_frame_layout_mismatch',
        'marker_offset': marker_offset,
        'field_bytes': field_bytes,
        'payload_size': len(payload),
        'packed_u32be_word_count': len(words),
        'packed_u32be_words': words,
        'named_channel_count': len(named),
        'named_channel_order_candidate': named,
        'frames': frames,
        'value_semantics': 'pending:packed_transform_decode',
        'note': 'The word-to-channel order is structurally consistent for compact two-frame clips, but the 32-bit transform codec is not decoded yet.',
    }


def _normal_clip_layout(probe, skel):
    names = _named_items(skel.get('names') or [], 'name')
    prefix = _prefix_bytes(probe)
    width = (len(names) + 7) // 8 if names else 0
    field_bytes = width * 2
    if not width:
        return {
            'version': 3,
            'status': 'pending:missing_skeleton_names',
            'name_count': 0,
        }
    if len(prefix) < field_bytes:
        return {
            'version': 3,
            'status': 'pending:short_normal_clip_prefix',
            'name_count': len(names),
            'field_width': width,
            'required_prefix_bytes': field_bytes,
            'available_prefix_bytes': len(prefix),
        }
    chunks = [prefix[0:width], prefix[width:field_bytes]]
    fields = [_field_bits(chunk, names) for chunk in chunks]
    compact = _compact_candidate(probe, prefix, fields, field_bytes)
    return {
        'version': 3,
        'status': 'ok:two_skeleton_width_fields',
        'semantics_status': 'pending:field_roles_and_packed_transform_codec',
        'name_count': len(names),
        'field_count': 2,
        'field_width': width,
        'field_bytes': field_bytes,
        'fields': fields,
        'payload_prefix_hex': prefix[field_bytes:field_bytes + 96].hex(),
        'stream_probe': probe.get('frame_marker_probe') or {},
        'compact_two_frame_candidate': compact,
        'note': 'Two skeleton-width prefix fields are confirmed structurally. Reverse-padded name mapping is exposed as a candidate; field roles are not asserted.',
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
            mapping['note'] = 'two_skeleton_width_fields_and_compact_u32_records_parsed; packed_transform_decode_pending'
            mapping['groups'] = []
            mapping['absolute_frame_count'] = 0
            result['track_skeleton_map'] = mapping
        return result

    mapping_module._apply_mapping = apply_mapping
    mapping_module._normal_clip_structure_installed = True
