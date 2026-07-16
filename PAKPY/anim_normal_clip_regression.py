import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

SENTINEL = bytes.fromhex('1c000000')
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


def inspect_anim(path):
    data = path.read_bytes()
    control = u32be(data, 0x28)
    body = data[BODY_OFFSET:] if len(data) >= BODY_OFFSET else b''
    used = body.rstrip(b'\x00')
    all_markers = find_offsets(body, SENTINEL)
    aligned = [offset for offset in all_markers if offset % 4 == 0]
    spans = [aligned[index + 1] - aligned[index] for index in range(len(aligned) - 1)]
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
        'frame_count_low8': control & 0xff,
        'group_hash': f'{u32be(data, 0x2c):08x}',
        'body_size': len(body),
        'body_used_size': len(used),
        'body_prefix_hex': used[:160].hex(),
        'aligned_marker_count': len(aligned),
        'aligned_marker_offsets': aligned,
        'unaligned_marker_offsets': [offset for offset in all_markers if offset % 4],
        'prefix_size_before_first_marker': aligned[0] if aligned else len(body),
        'record_spans': spans,
        'record_span_histogram': dict(sorted(Counter(spans).items())),
        'tail_size_after_last_marker': len(body) - aligned[-1] if aligned else len(body),
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
    parser = argparse.ArgumentParser(description='Inspect DKCTF 0x81 ANIM stream structure without fabricating transform tracks.')
    parser.add_argument('paths', nargs='+', help='ANIM files or directories')
    parser.add_argument('-o', '--output', default='anim_normal_clip_regression_report.json')
    args = parser.parse_args()

    unique = {}
    errors = []
    for path in discover(args.paths):
        try:
            item = inspect_anim(path)
        except Exception as exc:
            errors.append({'path': str(path), 'error': str(exc)})
            continue
        if item['family'] == '81':
            unique.setdefault(item['sha1'], item)

    clips = list(unique.values())
    by_control = Counter(item['control'] for item in clips)
    by_hash = defaultdict(int)
    for item in clips:
        by_hash[item['group_hash']] += 1

    report = {
        'version': 1,
        'type': 'DKCTF_NORMAL_CLIP_REGRESSION',
        'sentinel_hex': SENTINEL.hex(),
        'body_offset': BODY_OFFSET,
        'unique_normal_clip_count': len(clips),
        'error_count': len(errors),
        'controls': dict(sorted(by_control.items())),
        'group_hash_counts': dict(sorted(by_hash.items())),
        'marker_count_histogram': dict(sorted(Counter(item['aligned_marker_count'] for item in clips).items())),
        'clips': clips,
        'errors': errors,
        'warning': 'This report is structural only. It does not claim that 1c000000 is a universal frame marker or decode transforms.',
    }
    out = Path(args.output)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    print(f'Wrote {out}')
    print(f'Unique 0x81 clips: {len(clips)}')
    print(f'Errors: {len(errors)}')


if __name__ == '__main__':
    main()
