from __future__ import annotations

from dataclasses import dataclass


class IndexDataError(ValueError):
    """Raised when compressed animation index data is truncated or inconsistent."""


@dataclass(frozen=True)
class IndexChannel:
    """One LoadIdxData channel after both bitsets have been expanded.

    ``bone_map`` contains the logical bone indices selected by the first bitset.
    ``active`` and ``inactive`` contain those indices partitioned by the second
    bitset. All bitsets are consumed least-significant bit first, matching the
    Switch implementation.
    """

    bone_map: tuple[int, ...]
    active: tuple[int, ...]
    inactive: tuple[int, ...]


@dataclass(frozen=True)
class IndexData:
    translation: IndexChannel | None
    rotation: IndexChannel | None
    scale: IndexChannel | None
    next_offset: int


def _byte_count(bit_count: int) -> int:
    if bit_count < 0:
        raise IndexDataError("bit count must be non-negative")
    return (bit_count + 7) // 8


def _read_bit_indices(data: bytes, bit_count: int, offset: int) -> tuple[tuple[int, ...], int]:
    """Expand a packed LSB-first bitset exactly as BuildBoneMap does."""
    size = _byte_count(bit_count)
    end = offset + size
    if offset < 0 or end > len(data):
        raise IndexDataError("index bitset exceeds input")

    out: list[int] = []
    for byte_index, value in enumerate(data[offset:end]):
        base = byte_index * 8
        for bit in range(8):
            if value & (1 << bit):
                index = base + bit
                if index >= bit_count:
                    raise IndexDataError("non-zero padding bit in index bitset")
                out.append(index)
    return tuple(out), end


def decode_index_channel(data: bytes, bone_count: int, offset: int = 0) -> tuple[IndexChannel, int]:
    """Port the repeated channel block inside CAnimStreamData::LoadIdxData.

    Layout::

        ceil(bone_count / 8) bytes       bone-selection map
        ceil(selected_count / 8) bytes  active/inactive partition

    The second map addresses entries in the first map, not skeleton bones
    directly. LoadIdxData performs exactly this indirection after calling
    BuildActiveBoneSet.
    """
    bone_map, offset = _read_bit_indices(data, bone_count, offset)
    selected_count = len(bone_map)

    active_positions, offset = _read_bit_indices(data, selected_count, offset)
    active_position_set = set(active_positions)

    active = tuple(bone_map[position] for position in active_positions)
    inactive = tuple(
        bone_map[position]
        for position in range(selected_count)
        if position not in active_position_set
    )
    return IndexChannel(bone_map, active, inactive), offset


def load_idx_data(
    data: bytes,
    bone_count: int,
    flags: int,
    offset: int = 0,
) -> IndexData:
    """Decode the three index channels consumed by LoadIdxData.

    ``flags`` is descriptor byte ``descriptor[1]`` from the original routine.
    Bits 6, 5 and 4 gate translation, rotation and scale respectively. Channels
    are stored consecutively in that order.
    """
    if not 0 <= flags <= 0xFF:
        raise IndexDataError("flags must fit in one byte")
    if offset < 0:
        raise IndexDataError("offset must be non-negative")

    channels: list[IndexChannel | None] = []
    for mask in (0x40, 0x20, 0x10):
        if flags & mask:
            channel, offset = decode_index_channel(data, bone_count, offset)
            channels.append(channel)
        else:
            channels.append(None)

    return IndexData(channels[0], channels[1], channels[2], offset)
