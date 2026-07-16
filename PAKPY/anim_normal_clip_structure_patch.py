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


def _bit_candidate(chunk, names, lsb_first):
    indices = []
    padding = []
    for index in range(len(chunk) * 8):
        bit = (1 << (index & 7)) if lsb_first else (0x80 >> (index & 7))
        if not chunk[index >> 3] & bit:
            continue
        if index < len(names):
            indices.append(index)
        else:
            padding.append(index)
    return {
        'set_count': len(indices),
        'set_indices': indices,
        'set_names': [names[index] for index in indices],
        'padding_set_bits': padding,
    }


def _basis_candidate(label, names, prefix):
    count = len(names)
    byte_width = (count + 7) // 8 if count else 0
    required = byte_width * 2
    first = prefix[:byte_width]
    second = prefix[byte_width:required]
    return {
        'basis': label,
        'count': count,
        'byte_width': byte_width,
        'two_chunk_prefix_size': required,
        'available': bool(byte_width and len(prefix) >= required),
        'first_chunk_hex': first.hex(),
        'second_chunk_hex': second.hex(),
        'bytes_after_two_chunks_hex': prefix[required:required + 64].hex(),
        'bit_order_candidates': {
            'msb_first': [
                _bit_candidate(first, names, False),
                _bit_candidate(second, names, False),
            ] if byte_width else [],
            'lsb_first': [
                _bit_candidate(first, names, True),
                _bit_candidate(second, names, True),
            ] if byte_width else [],
        },
    }


def _normal_clip_layout(probe, skel):
    prefix = _prefix_bytes(probe)
    bases = [
        ('names', _named_items(skel.get('names') or [], 'name')),
        ('nodes', _named_items(skel.get('nodes') or [], 'node')),
        ('skin_bones', _named_items(skel.get('bones') or [], 'bone')),
    ]
    candidates = [_basis_candidate(label, names, prefix) for label, names in bases if names]
    stream_probe = probe.get('frame_marker_probe') or {}
    return {
        'version': 2,
        'status': 'pending:normal_clip_prefix_layout',
        'semantics_status': 'pending:channel_tables_quantization_and_bit_order',
        'available_prefix_bytes': len(prefix),
        'basis_candidates': candidates,
        'stream_probe': stream_probe,
        'note': 'Candidate partitions are reported for comparison only; no mask count or transform role is asserted.',
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
            mapping['status'] = 'pending:normal_clip_quantized_stream'
            mapping['note'] = 'prefix_candidates_and_aligned_sentinel_records_reported; transform_decode_pending'
            mapping['groups'] = []
            mapping['absolute_frame_count'] = 0
            result['track_skeleton_map'] = mapping
        return result

    mapping_module._apply_mapping = apply_mapping
    mapping_module._normal_clip_structure_installed = True
