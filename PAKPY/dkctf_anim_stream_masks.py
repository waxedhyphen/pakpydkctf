from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoneMapResult:
    bone_indices: tuple[int, ...]
    next_offset: int


@dataclass(frozen=True)
class ActiveBoneSetResult:
    set_bits: tuple[int, ...]
    clear_bits: tuple[int, ...]
    next_offset: int


def _byte_count(bit_count: int) -> int:
    if bit_count < 0:
        raise ValueError("bit_count must be non-negative")
    return (bit_count + 7) // 8


def build_bone_map(bit_count: int, data: bytes, offset: int = 0) -> BoneMapResult:
    """Exact Python port of NAnimStream::BuildBoneMap from Switch main.

    The game reads ceil(bit_count / 8) bytes, scans every byte least-significant
    bit first, and emits the numeric bit index for each set bit.  The returned
    offset is advanced by the rounded byte count.
    """
    count = _byte_count(bit_count)
    end = offset + count
    if offset < 0 or end > len(data):
        raise ValueError("bone-map bitset exceeds input")

    indices: list[int] = []
    for byte_index, value in enumerate(data[offset:end]):
        base = byte_index * 8
        for bit in range(8):
            if value & (1 << bit):
                indices.append(base + bit)

    return BoneMapResult(tuple(indices), end)


def build_active_bone_set(
    bit_count: int,
    data: bytes,
    offset: int = 0,
) -> ActiveBoneSetResult:
    """Exact Python port of NAnimStream::BuildActiveBoneSet from Switch main.

    The routine consumes ceil(bit_count / 8) bytes.  For each byte it emits all
    eight bit indices in LSB-first order, separating set and clear bits into two
    output streams.  Padding bits in the final byte are processed exactly like
    the original routine; callers that need a logical bone-count clamp must do
    that explicitly after decoding.
    """
    count = _byte_count(bit_count)
    end = offset + count
    if offset < 0 or end > len(data):
        raise ValueError("active-bone bitset exceeds input")

    set_bits: list[int] = []
    clear_bits: list[int] = []
    for byte_index, value in enumerate(data[offset:end]):
        base = byte_index * 8
        for bit in range(8):
            index = base + bit
            (set_bits if value & (1 << bit) else clear_bits).append(index)

    return ActiveBoneSetResult(tuple(set_bits), tuple(clear_bits), end)
