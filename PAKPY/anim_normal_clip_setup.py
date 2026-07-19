#!/usr/bin/env python3
"""Verified setup-stage parser for DKCTF ANIM normal_clip.

Covers, in serialized order:
  * LoadIdxData @ 0x195BA8
  * LoadPairData @ 0x1969A4
  * LoadRotRange @ 0x196D88
  * vector range loader @ 0x196E98 for translation and scale

It stops at the first frame-processing byte. It does not decode animated keys.
"""
from __future__ import annotations

import math
import struct
from dataclasses import asdict, dataclass
from typing import Any

from anim_normal_clip_indices import LoadIdxDataError, LoadIdxDataResult, parse_load_idx_data

ROT_QUANT_SCALE = 2.0 ** -27
ROT_RANGE_SCALE = 2.0 ** -23
PAIR_VECTOR_QUANT_SCALE = 2.0 ** -29
VEC_RANGE_DECODE_SCALE = struct.unpack('<f', bytes.fromhex('0402813f'))[0]
VEC_RANGE_FINE_MULTIPLIER = 2.0 ** -30
VEC_RANGE_COARSE_MULTIPLIER = 2.0 ** -20


def _u32(value: int) -> int:
    return value & 0xFFFFFFFF


def _rev32(value: int) -> int:
    return int.from_bytes(_u32(value).to_bytes(4, 'little'), 'big')


def _bfi(dst: int, src: int, lsb: int, width: int) -> int:
    mask = ((1 << width) - 1) << lsb
    return _u32((dst & ~mask) | ((src & ((1 << width) - 1)) << lsb))


def _bfxil(dst: int, src: int, lsb: int, width: int) -> int:
    mask = (1 << width) - 1
    return _u32((dst & ~mask) | ((src >> lsb) & mask))


def _f32_from_bits(bits: int) -> float:
    return struct.unpack('<f', _u32(bits).to_bytes(4, 'little'))[0]


def _read_lookahead(raw: bytes, offset: int, size: int, label: str) -> bytes:
    end = offset + size
    if offset < 0 or end > len(raw):
        raise LoadIdxDataError(
            f'{label} truncated at file offset 0x{offset:X}: need {size} bytes, file size=0x{len(raw):X}'
        )
    return raw[offset:end]


@dataclass
class ConstantRotation:
    node_index: int
    file_offset: int
    record_size: int
    extended_precision: bool
    negative_w: bool
    quantized_xyz: tuple[int, int, int]
    quaternion_wxyz: tuple[float, float, float, float]
    xyz_length_squared: float


@dataclass
class ConstantVector:
    node_index: int
    file_offset: int
    record_size: int
    extended_precision: bool
    reciprocal_range: bool
    exponent: int
    range_value: float
    quantized_xyz: tuple[int, int, int]
    value_xyz: tuple[float, float, float]


@dataclass
class RotationRange:
    node_index: int
    table_byte_offset: int
    nibble_position: str
    nibble: int
    range_value: float
    base: float
    scale: float


@dataclass
class VectorRange:
    node_index: int
    file_offset: int
    encoded_hex: str
    base_xyz: tuple[float, float, float]
    raw_span_xyz: tuple[float, float, float]
    span_multiplier: float
    span_xyz: tuple[float, float, float]


@dataclass
class NormalClipSetupResult:
    type: str
    indices: LoadIdxDataResult
    pair_data_file_offset: int
    pair_data_end_file_offset: int
    constant_rotations: list[ConstantRotation]
    constant_translations: list[ConstantVector]
    rotation_range_file_offset: int
    rotation_range_end_file_offset: int
    rotation_ranges: list[RotationRange]
    translation_range_file_offset: int
    translation_range_end_file_offset: int
    translation_span_multiplier: float
    translation_ranges: list[VectorRange]
    scale_range_file_offset: int
    scale_range_end_file_offset: int
    scale_span_multiplier: float
    scale_ranges: list[VectorRange]
    frame_data_file_offset: int
    bytes_consumed_after_load_idx_data: int
    notes: list[str]

    def to_dict(self, node_names: list[str] | None = None) -> dict[str, Any]:
        out = asdict(self)
        if node_names is not None:
            out['indices'] = self.indices.to_dict(node_names)
            for key in ('constant_rotations', 'constant_translations', 'rotation_ranges',
                        'translation_ranges', 'scale_ranges'):
                for item in out[key]:
                    idx = item['node_index']
                    item['node_name'] = node_names[idx] if 0 <= idx < len(node_names) else f'<node_{idx}>'
        return out


def decode_constant_rotation(raw: bytes, offset: int, node_index: int) -> ConstantRotation:
    b = _read_lookahead(raw, offset, 12, 'constant rotation record/lookahead')
    raw0 = int.from_bytes(b[0:4], 'little')
    raw1 = int.from_bytes(b[4:8], 'little')
    be0 = _rev32(raw0)
    be1 = _rev32(raw1)

    qx = _rev32(raw0 & 0x00FFFF0F) | b[9]
    middle = _bfi(be1 >> 20, be0, 12, 8)
    qy = _bfi(b[10], middle, 8, 20)
    qz = _bfi(b[11], be1, 8, 20)

    x = qx * ROT_QUANT_SCALE - 1.0
    y = qy * ROT_QUANT_SCALE - 1.0
    z = qz * ROT_QUANT_SCALE - 1.0
    length2 = x * x + y * y + z * z
    negative_w = bool((be0 >> 30) & 1)
    if length2 < 1.0:
        w = math.sqrt(max(0.0, 1.0 - length2))
        if negative_w:
            w = -w
    else:
        w = 0.0

    extended = bool((be0 >> 31) & 1)
    return ConstantRotation(
        node_index=node_index,
        file_offset=offset,
        record_size=12 if extended else 8,
        extended_precision=extended,
        negative_w=negative_w,
        quantized_xyz=(qx, qy, qz),
        quaternion_wxyz=(w, x, y, z),
        xyz_length_squared=length2,
    )


def decode_constant_vector(raw: bytes, offset: int, node_index: int) -> ConstantVector:
    b = _read_lookahead(raw, offset, 12, 'constant translation record/lookahead')
    raw0 = int.from_bytes(b[0:4], 'little')
    raw1 = int.from_bytes(b[4:8], 'little')
    raw2 = int.from_bytes(b[8:12], 'little')
    be0 = _rev32(raw0)
    be1 = _rev32(raw1)
    be2 = _rev32(raw2)

    exponent = (be0 >> 25) & 0x1F
    range_value = float(1 << exponent)
    reciprocal = bool((be0 >> 30) & 1)
    if reciprocal:
        range_value = 1.0 / range_value

    shared = _bfi(be1 >> 19, be0, 13, 6)
    qy = _bfi(be2 >> 10, shared, 10, 22)

    qx = _u32(be0 << 4) & 0x1FFFFC00
    qx = _bfxil(qx, be2, 20, 10)

    qz = _rev32(raw2 & _u32(-0xFD0000))
    qz = _u32(qz | (_u32(be1 << 10) & 0x1FFFFC00))

    scale = (2.0 * range_value) * PAIR_VECTOR_QUANT_SCALE
    x = qx * scale - range_value
    y = qy * scale - range_value
    z = qz * scale - range_value

    extended = bool((be0 >> 31) & 1)
    return ConstantVector(
        node_index=node_index,
        file_offset=offset,
        record_size=12 if extended else 8,
        extended_precision=extended,
        reciprocal_range=reciprocal,
        exponent=exponent,
        range_value=range_value,
        quantized_xyz=(qx, qy, qz),
        value_xyz=(x, y, z),
    )


def decode_rotation_ranges(raw: bytes, offset: int, node_indices: list[int]) -> tuple[list[RotationRange], int]:
    count = len(node_indices)
    size = (count + 1) // 2
    table = _read_lookahead(raw, offset, size, 'rotation range table') if size else b''
    out: list[RotationRange] = []
    for i, node_index in enumerate(node_indices):
        byte_index = i // 2
        nibble = (table[byte_index] & 0x0F) if i % 2 == 0 else (table[byte_index] >> 4)
        bits = _u32(0x3F800000 - (nibble << 22))
        range_value = _f32_from_bits(bits)
        out.append(RotationRange(
            node_index=node_index,
            table_byte_offset=offset + byte_index,
            nibble_position='low' if i % 2 == 0 else 'high',
            nibble=nibble,
            range_value=range_value,
            base=-range_value,
            scale=range_value * ROT_RANGE_SCALE,
        ))
    return out, offset + size


def decode_vector_range_record(encoded: bytes) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    if len(encoded) != 8:
        raise ValueError('vector range record must be exactly 8 bytes')
    x12 = int.from_bytes(encoded, 'little')
    w12_initial = x12 & 0xFFFFFFFF
    w13 = _rev32(w12_initial)
    w14 = _u32(w12_initial << 8)
    x15 = x12 >> 39
    x16 = x12 >> 55
    x17 = x12 >> 47
    x18 = x12 >> 32
    x3 = x12 >> 16
    x4 = (x12 >> 8) & 0xFFFFFF
    x5 = x12 >> 24
    x6 = x12 >> 40

    w12 = _bfxil(w12_initial, w13, 16, 16)
    base_a = (_u32(w12 << 13) & 0x0F800000) + 0x3A000000
    sign_a1 = _u32(w14) & 0x80000000
    sign_a2 = w12 & 0x80000000
    base_b = (_u32(w12 << 18) & 0x0F800000) + 0x3A000000

    f_b1 = _f32_from_bits(_u32(base_b | _u32(x15 << 31)))
    f_a1 = _f32_from_bits(_u32(base_a | sign_a1))
    f_a2 = _f32_from_bits(_u32(base_a | sign_a2))
    f_b2 = _f32_from_bits(_u32(base_b | _u32(x17 << 31)))

    base_c = (_u32((w12 & 0x1F) << 23)) + 0x3A000000
    f_c1 = _f32_from_bits(_u32(base_c | _u32(x16 << 31)))
    f_c2 = _f32_from_bits(_u32(base_c | (x18 & 0x80000000)))

    end_x_bits = _u32((base_a | sign_a1) | (w12 & 0x007F0000))
    min_x = (_f32_from_bits(end_x_bits) - f_a1) * VEC_RANGE_DECODE_SCALE

    end_y_bits = _u32((base_b | _u32(x15 << 31)) | (x3 & 0x007F0000))
    min_y = (_f32_from_bits(end_y_bits) - f_b1) * VEC_RANGE_DECODE_SCALE

    end_z_bits = _u32((base_c | _u32(x16 << 31)) | (x18 & 0x007F0000))
    min_z = (_f32_from_bits(end_z_bits) - f_c1) * VEC_RANGE_DECODE_SCALE

    max_x_bits = _u32((base_a | sign_a2) | (x4 & 0x007F0000))
    max_x = (_f32_from_bits(max_x_bits) - f_a2) * VEC_RANGE_DECODE_SCALE

    max_y_bits = _u32((base_b | _u32(x17 << 31)) | (x5 & 0x007F0000))
    max_y = (_f32_from_bits(max_y_bits) - f_b2) * VEC_RANGE_DECODE_SCALE

    max_z_bits = _u32((base_c | (x18 & 0x80000000)) | (x6 & 0x007F0000))
    max_z = (_f32_from_bits(max_z_bits) - f_c2) * VEC_RANGE_DECODE_SCALE

    base = (min_x, min_y, min_z)
    raw_span = (max_x - min_x, max_y - min_y, max_z - min_z)
    return base, raw_span


def decode_vector_ranges(raw: bytes, offset: int, node_indices: list[int], span_multiplier: float) -> tuple[list[VectorRange], int]:
    out: list[VectorRange] = []
    cursor = offset
    for node_index in node_indices:
        encoded = _read_lookahead(raw, cursor, 8, 'vector range record')
        base, raw_span = decode_vector_range_record(encoded)
        span = tuple(value * span_multiplier for value in raw_span)
        out.append(VectorRange(
            node_index=node_index,
            file_offset=cursor,
            encoded_hex=encoded.hex(),
            base_xyz=base,
            raw_span_xyz=raw_span,
            span_multiplier=span_multiplier,
            span_xyz=span,
        ))
        cursor += 8
    return out, cursor


def translation_span_multiplier(flags: int) -> float:
    return VEC_RANGE_FINE_MULTIPLIER if (flags & 0x04) else VEC_RANGE_COARSE_MULTIPLIER


def scale_span_multiplier(flags: int) -> float:
    mode = ((flags & 0x03) + 1) & 0x03
    return VEC_RANGE_FINE_MULTIPLIER if mode == 0x03 else VEC_RANGE_COARSE_MULTIPLIER


def parse_normal_clip_setup(raw: bytes, node_count: int, *, strict: bool = True) -> NormalClipSetupResult:
    idx = parse_load_idx_data(raw, node_count, strict=strict)
    cursor = idx.load_pair_data_file_offset
    pair_start = cursor

    constant_rotations: list[ConstantRotation] = []
    for node_index in idx.rotation.constant_nodes:
        item = decode_constant_rotation(raw, cursor, node_index)
        constant_rotations.append(item)
        cursor += item.record_size

    constant_translations: list[ConstantVector] = []
    for node_index in idx.translation.constant_nodes:
        item = decode_constant_vector(raw, cursor, node_index)
        constant_translations.append(item)
        cursor += item.record_size
    pair_end = cursor

    rot_start = cursor
    rotation_ranges, cursor = decode_rotation_ranges(raw, cursor, idx.rotation.animated_nodes)
    rot_end = cursor

    trans_start = cursor
    trans_multiplier = translation_span_multiplier(idx.flags)
    translation_ranges, cursor = decode_vector_ranges(raw, cursor, idx.translation.animated_nodes, trans_multiplier)
    trans_end = cursor

    scale_start = cursor
    scale_multiplier = scale_span_multiplier(idx.flags)
    scale_ranges, cursor = decode_vector_ranges(raw, cursor, idx.scale.animated_nodes, scale_multiplier)
    scale_end = cursor

    if strict:
        for item in constant_rotations:
            if not all(math.isfinite(v) for v in item.quaternion_wxyz):
                raise LoadIdxDataError(f'non-finite constant quaternion at 0x{item.file_offset:X}')
        for collection in (constant_translations, translation_ranges, scale_ranges):
            for item in collection:
                values = item.value_xyz if isinstance(item, ConstantVector) else (*item.base_xyz, *item.span_xyz)
                if not all(math.isfinite(v) for v in values):
                    raise LoadIdxDataError(f'non-finite vector setup value at 0x{item.file_offset:X}')

    return NormalClipSetupResult(
        type='ANIM_NORMAL_CLIP_SETUP',
        indices=idx,
        pair_data_file_offset=pair_start,
        pair_data_end_file_offset=pair_end,
        constant_rotations=constant_rotations,
        constant_translations=constant_translations,
        rotation_range_file_offset=rot_start,
        rotation_range_end_file_offset=rot_end,
        rotation_ranges=rotation_ranges,
        translation_range_file_offset=trans_start,
        translation_range_end_file_offset=trans_end,
        translation_span_multiplier=trans_multiplier,
        translation_ranges=translation_ranges,
        scale_range_file_offset=scale_start,
        scale_range_end_file_offset=scale_end,
        scale_span_multiplier=scale_multiplier,
        scale_ranges=scale_ranges,
        frame_data_file_offset=cursor,
        bytes_consumed_after_load_idx_data=cursor - pair_start,
        notes=[
            'LoadPairData uses a branchless 12-byte lookahead and advances each record by 8 or 12 bytes.',
            'LoadRotRange consumes low nibble first and uses scale=R*2^-23.',
            'Vector range records are 8 bytes per animated channel.',
            'frame_data_file_offset is the offset stored in CAnimStreamData+0x08 after setup parsing.',
        ],
    )
