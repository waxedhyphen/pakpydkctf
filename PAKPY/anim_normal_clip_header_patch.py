import math
import struct


HEADER_PREFIX_OFFSET = 0x30
ROOT_TRANSFORM_OFFSET = 0x37
ROOT_TRANSFORM_END = 0x53
HEADER_END_MARKER_OFFSET = 0x53


def _normal_clip_header(asset):
    if len(asset) < 0x54:
        return {
            'version': 1,
            'status': 'pending:short_anim_header',
            'asset_size': len(asset),
        }
    prefix = asset[HEADER_PREFIX_OFFSET:ROOT_TRANSFORM_OFFSET]
    values = struct.unpack('>7f', asset[ROOT_TRANSFORM_OFFSET:ROOT_TRANSFORM_END])
    quaternion = list(values[:4])
    translation = list(values[4:])
    finite = all(math.isfinite(value) for value in values)
    norm = math.sqrt(sum(value * value for value in quaternion)) if finite else None
    return {
        'version': 1,
        'status': 'ok:root_transform_header' if finite else 'pending:nonfinite_root_transform_header',
        'prefix_hex': prefix.hex(),
        'prefix_bytes': list(prefix),
        'quaternion_wxyz': quaternion,
        'quaternion_norm': norm,
        'translation_xyz': translation,
        'end_marker_u8': asset[HEADER_END_MARKER_OFFSET],
        'body_offset': 0x54,
        'note': 'Offsets 0x37..0x52 decode consistently as seven big-endian floats: quaternion WXYZ followed by translation XYZ.',
    }


def install_into():
    raw = __import__('anim_raw_probe_patch')
    if getattr(raw, '_normal_clip_header_patch_installed', False):
        return
    old_enhance = raw._enhance

    def enhance(asset, probe):
        result = old_enhance(asset, probe)
        if result.get('raw_family') == 'normal_clip':
            result['normal_clip_header'] = _normal_clip_header(asset)
            track_decode = result.get('track_decode') or {}
            track_decode['normal_clip_header'] = result['normal_clip_header']
            result['track_decode'] = track_decode
        return result

    raw._enhance = enhance
    raw._normal_clip_header_patch_installed = True
