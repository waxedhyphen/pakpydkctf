CONTROL_WORD_CANDIDATE = bytes.fromhex('1c000000')


def _find_offsets(data, needle):
    out = []
    start = 0
    while True:
        pos = data.find(needle, start)
        if pos < 0:
            return out
        out.append(pos)
        start = pos + 1


def _normal_stream_probe(body):
    body = body or b''
    offsets = _find_offsets(body, CONTROL_WORD_CANDIDATE)
    aligned = [offset for offset in offsets if offset % 4 == 0]
    unaligned = [offset for offset in offsets if offset % 4 != 0]
    occurrences = []
    for offset in offsets[:1024]:
        occurrences.append({
            'offset': offset,
            'aligned_u32': offset % 4 == 0,
            'bytes_before_hex': body[max(0, offset - 16):offset].hex(),
            'bytes_after_hex': body[offset + 4:offset + 20].hex(),
        })
    return {
        'version': 3,
        'status': 'ok:control_word_occurrence_scan',
        'control_word_candidate_hex': CONTROL_WORD_CANDIDATE.hex(),
        'body_size': len(body),
        'occurrence_count': len(offsets),
        'occurrence_offsets': offsets[:1024],
        'aligned_control_word_count': len(aligned),
        'aligned_control_word_offsets': aligned[:1024],
        'unaligned_control_word_count': len(unaligned),
        'unaligned_control_word_offsets': unaligned[:256],
        'occurrences': occurrences,
        'interpretation': 'opaque_control_word_candidate',
        'interpretation_note': 'Occurrences are reported only. 1c000000 is not a universal frame delimiter: longer clips can contain nonzero data after it and other control words also occur.',
    }


def install_into():
    raw = __import__('anim_raw_probe_patch')
    if getattr(raw, '_normal_clip_stream_probe_installed', False):
        return

    old_build_track_decode = raw._build_track_decode

    def frame_marker_probe(body):
        return _normal_stream_probe(body)

    def build_track_decode(probe, body=None):
        if probe.get('raw_family') != 'normal_clip':
            return old_build_track_decode(probe, body)
        stream_probe = probe.get('frame_marker_probe') or _normal_stream_probe(body or b'')
        return {
            'version': 6,
            'status': 'pending:normal_clip_packed_transform_codec',
            'frame_count_guess': probe.get('frame_count_guess', 0),
            'group_count': 0,
            'groups': [],
            'primary_group_index': None,
            'primary_timeline_frame_count': 0,
            'normal_clip_stream_probe': stream_probe,
        }

    raw.FRAME_MARKER = CONTROL_WORD_CANDIDATE
    raw._frame_marker_probe = frame_marker_probe
    raw._build_track_decode = build_track_decode
    raw._normal_clip_stream_probe_installed = True
