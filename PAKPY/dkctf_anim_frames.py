from __future__ import annotations

from dataclasses import dataclass
import struct


class FrameDecodeError(ValueError):
    """Raised when a compressed frame vector is truncated."""


@dataclass(frozen=True)
class QuantizedVector:
    x: int
    y: int
    z: int
    byte_count: int


@dataclass(frozen=True)
class VectorRange:
    minimum: tuple[float, float, float]
    step: tuple[float, float, float]


@dataclass(frozen=True)
class VectorKey:
    previous: tuple[float, float, float]
    current: tuple[float, float, float]
    next_offset: int


def _rev32(value: int) -> int:
    return int.from_bytes((value & 0xFFFFFFFF).to_bytes(4, "little"), "big")


def _bfxil(dst: int, src: int, lsb: int, width: int) -> int:
    mask = (1 << width) - 1
    return (dst & ~mask) | ((src >> lsb) & mask)


def decode_quantized_vector(data: bytes, offset: int = 0) -> QuantizedVector:
    """Port the packed XYZ extraction used by ProcessFrame.

    The stream stores three unsigned 20-bit components.  The high bit of the
    first big-endian word selects a 4- or 8-byte record.  ProcessFrame performs
    an eight-byte load in either case, but advances by only the selected size;
    this safe port requires only the bytes logically consumed and pads the
    speculative second word with zero for a four-byte record.
    """

    if offset < 0 or offset + 4 > len(data):
        raise FrameDecodeError("packed vector header exceeds input")

    first_le = int.from_bytes(data[offset:offset + 4], "little")
    first_be = _rev32(first_le)
    byte_count = 8 if (first_be & 0x80000000) else 4
    if offset + byte_count > len(data):
        raise FrameDecodeError("packed vector payload exceeds input")

    second_bytes = data[offset + 4:offset + 8]
    second_le = int.from_bytes(second_bytes.ljust(4, b"\x00"), "little")
    second_be = _rev32(second_le)

    x = (first_be >> 10) & 0xFFC00
    x = _bfxil(x, second_be, 20, 10)

    y_hi = (second_be >> 10) & 0x3FF
    y_lo = _rev32(first_le & 0x00FC0F00)
    y = y_hi | y_lo

    z_hi = (first_be & 0x3FF) << 10
    z_lo = _rev32(second_le & 0xFF030000)
    z = z_hi | z_lo

    return QuantizedVector(x, y, z, byte_count)


def decode_vector_key(
    data: bytes,
    value_range: VectorRange,
    previous_current: tuple[float, float, float],
    offset: int = 0,
) -> VectorKey:
    """Decode one ProcessFrame vector and preserve the prior current value."""

    packed = decode_quantized_vector(data, offset)
    current = (
        value_range.minimum[0] + value_range.step[0] * packed.x,
        value_range.minimum[1] + value_range.step[1] * packed.y,
        value_range.minimum[2] + value_range.step[2] * packed.z,
    )
    return VectorKey(previous_current, current, offset + packed.byte_count)


def pack_quantized_vector(x: int, y: int, z: int, *, byte_count: int = 8) -> bytes:
    """Inverse helper for tests and tooling; emits the ProcessFrame bit layout."""

    if byte_count not in (4, 8):
        raise ValueError("byte_count must be 4 or 8")
    if not all(0 <= value <= 0xFFFFF for value in (x, y, z)):
        raise ValueError("components must be unsigned 20-bit integers")

    first_be = 0
    second_be = 0

    first_be |= (x & 0xFFC00) << 10
    second_be |= (x & 0x3FF) << 20

    y_lo_be = y & 0xFFC00
    first_masked_le = _rev32(y_lo_be)
    first_be |= _rev32(first_masked_le & 0x00FC0F00)
    second_be |= (y & 0x3FF) << 10

    first_be |= (z >> 10) & 0x3FF
    z_lo_be = z & 0x3FF
    second_masked_le = _rev32(z_lo_be)
    second_be |= _rev32(second_masked_le & 0xFF030000)

    if byte_count == 8:
        first_be |= 0x80000000
    elif second_be != 0:
        raise ValueError("four-byte form cannot encode non-zero spill bits")

    raw = first_be.to_bytes(4, "big") + second_be.to_bytes(4, "big")
    return raw[:byte_count]
