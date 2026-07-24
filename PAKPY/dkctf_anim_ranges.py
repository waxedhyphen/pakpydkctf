from __future__ import annotations

from dataclasses import dataclass
import struct

_VEC_SCALE = struct.unpack('<f', struct.pack('<I', 0x3F810204))[0]
_ROT_SCALE = struct.unpack('<f', struct.pack('<I', 0x34000000))[0]


def _u32(v: int) -> int:
    return v & 0xFFFFFFFF


def _f32_bits(v: int) -> float:
    return struct.unpack('<f', struct.pack('<I', _u32(v)))[0]


def _rev32(v: int) -> int:
    return int.from_bytes(_u32(v).to_bytes(4, 'little'), 'big')


@dataclass(frozen=True)
class VecRange:
    minimum: tuple[float, float, float]
    extent: tuple[float, float, float]


@dataclass(frozen=True)
class RotRange:
    minimum: float
    extent: float


def decode_vec_range_word(word: int) -> VecRange:
    """Literal scalar port of CAnimStreamData::LoadVecRange for one 8-byte record."""
    x12_64 = word & 0xFFFFFFFFFFFFFFFF
    w12 = x12_64 & 0xFFFFFFFF
    w13 = _rev32(w12)
    w14 = _u32(w12 << 8)
    x15 = x12_64 >> 39
    x16 = x12_64 >> 55
    x17 = x12_64 >> 47
    x18 = x12_64 >> 32
    x3 = x12_64 >> 16
    x4 = (x12_64 >> 8) & 0xFFFFFF
    x5 = x12_64 >> 24
    x6 = x12_64 >> 40

    w12 = (w12 & 0x0000FFFF) | (w13 & 0xFFFF0000)
    w11 = 0x3A000000

    w13 = ((_u32(w12 << 13) & 0x0F800000) + w11) & 0xFFFFFFFF
    w14 = w14 & 0x80000000
    w19 = w12 & 0x80000000
    w7 = ((_u32(w12 << 18) & 0x0F800000) + w11) & 0xFFFFFFFF

    w15 = w7 | ((_u32(x15) << 31) & 0x80000000)
    w14 = w13 | w14
    w13 = w13 | w19
    w17 = w7 | ((_u32(x17) << 31) & 0x80000000)

    w19 = ((_u32(w12 << 23) & 0x0F800000) + w11) & 0xFFFFFFFF
    w12v = w12 & 0x007F0000
    f1 = _f32_bits(w14 | w12v) - _f32_bits(w14)

    w3 = _u32(x3) & 0x007F0000
    f2 = _f32_bits(w15 | w3) - _f32_bits(w15)

    w16 = w19 | ((_u32(x16) << 31) & 0x80000000)
    w7sign = _u32(x18) & 0x80000000
    w18 = (_u32(x18) & 0x007F0000) | w16
    w7b = w19 | w7sign
    f3 = _f32_bits(w18) - _f32_bits(w16)

    w4 = (_u32(x4) & 0x007F0000) | w13
    w6 = (_u32(x6) & 0x007F0000) | w7b
    f4 = _f32_bits(w4) - _f32_bits(w13)

    w5 = (_u32(x5) & 0x007F0000) | w17
    f5 = _f32_bits(w5) - _f32_bits(w17)
    f6 = _f32_bits(w6) - _f32_bits(w7b)

    minimum = (f1 * _VEC_SCALE, f2 * _VEC_SCALE, f3 * _VEC_SCALE)
    maximum = (f4 * _VEC_SCALE, f5 * _VEC_SCALE, f6 * _VEC_SCALE)
    extent = tuple(maximum[i] - minimum[i] for i in range(3))
    return VecRange(minimum, extent)


def load_vec_ranges(data: bytes, count: int, offset: int = 0) -> tuple[tuple[VecRange, ...], int]:
    if count < 0 or offset < 0:
        raise ValueError('count and offset must be non-negative')
    end = offset + count * 8
    if end > len(data):
        raise ValueError('vector-range records exceed input')
    out = []
    for pos in range(offset, end, 8):
        out.append(decode_vec_range_word(int.from_bytes(data[pos:pos + 8], 'little')))
    return tuple(out), end


def _decode_rot_nibble(nibble: int) -> RotRange:
    """Port of the float construction and final normalization in LoadRotRange."""
    if not 0 <= nibble <= 0xF:
        raise ValueError('rotation nibble must be in range 0..15')
    value = _f32_bits(_u32(0x3F800000 - (nibble << 22)))
    return RotRange(-value, value * _ROT_SCALE)


def load_rot_ranges(data: bytes, count: int, offset: int = 0) -> tuple[tuple[RotRange, ...], int]:
    """Literal packed-nibble decoder from CAnimStreamData::LoadRotRange.

    Two rotation range descriptors are stored per byte.  The low nibble is
    decoded first, followed by the high nibble.  An odd final descriptor uses
    only the low nibble.  Each descriptor is normalized exactly as the Switch
    routine: minimum=-value and extent=value*2^-23.
    """
    if count < 0 or offset < 0:
        raise ValueError('count and offset must be non-negative')
    byte_count = (count + 1) // 2
    end = offset + byte_count
    if end > len(data):
        raise ValueError('rotation-range records exceed input')

    out: list[RotRange] = []
    for value in data[offset:end]:
        out.append(_decode_rot_nibble(value & 0xF))
        if len(out) < count:
            out.append(_decode_rot_nibble(value >> 4))
    return tuple(out), end
