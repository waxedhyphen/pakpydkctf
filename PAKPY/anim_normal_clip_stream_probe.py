from collections import Counter

SENTINEL = bytes.fromhex('1c000000')


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
    all_offsets = _find_offsets(body, SENTINEL)
    aligned = [offset for offset in all_offsets if offset % 4 == 0]
    unaligned = [offset for offset in all_offsets if offset % 4 != 0]
    spans = [aligned[index + 1] - aligned[index] for index in range(len(aligned) - 1)]
    records = []
    for index, offset in enumerate(aligned):
        next_offset = aligned[index + 1] if index + 1 < len(aligned) else len(body)
        records.append({
            'index': index,
            'marker_offset': offset,
            'next_marker_offset': next_offset,
            'record_span': next_offset - offset,
            'payload_size_after_marker': max(0, next_offset - offset - len(SENTINEL)),
            'payload_prefix_hex': body[offset + len(SENTINEL):offset + len(SENTINEL) + 32].hex(),
        })
    return {
        'version': 2,
        'status': 'ok:aligned_control_word_scan',
        'control_word_hex': SENTINEL.hex(),
        'body_size': len(body),
        'aligned_marker_count': len(aligned),
        'aligned_marker_offsets': aligned[:1024],
        'unaligned_marker_count': len(unaligned),
        'unaligned_marker_offsets': unaligned[:256],
        'prefix_size_before_first_marker': aligned[0] if aligned else len(body),
        'tail_size_after_last_marker': len(body) - aligned[-1] if aligned else len(body),
        'record_spans': spans[:1024],
        'record_span_histogram': [
            {'span': span, 'count': count}
            for span, count in sorted(Counter(spans).items())
        ],
        'records': records[:512],
        'interpretation': 'aligned_control_word_candidate',
        'interpretation_note': '1c000000 behaves as an aligned frame/control word in compact and multi-frame clips. Other control words may exist, so this is not a complete record decoder.',
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
            'version': 5,
            'status': 'pending:normal_clip_packed_transform_codec',
            'frame_count_guess': probe.get('frame_count_guess', 0),
            'group_count': 0,
            'groups': [],
            'primary_group_index': None,
            'primary_timeline_frame_count': 0,
            'normal_clip_stream_probe': stream_probe,
        }

    raw.FRAME_MARKER = SENTINEL
    raw._frame_marker_probe = frame_marker_probe
    raw._build_track_decode = build_track_decode
    raw._normal_clip_stream_probe_installed = True
