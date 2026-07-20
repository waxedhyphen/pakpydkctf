#!/usr/bin/env python3
"""Structural frame-stream parser for DKCTF ANIM ``normal_clip``.

This is an instruction-level port of the stream traversal performed by:

* ``CAnimStreamProcess::LoadSetupFrames`` @ ``0x197BE0``
* duration descriptor helper @ ``0x198A38``
* packed duration decoder @ ``0x198E4C``
* due-channel list builder @ ``0x198F40``
* ``CAnimStreamProcess::ProcessFrame`` @ ``0x199058``

It resolves exact key times and exact record boundaries for every animated
rotation/translation/scale channel. It deliberately does not interpret the
record payload values yet; that is the next codec layer.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


class NormalClipFrameError(ValueError):
    pass


def align_up(value: int, alignment: int) -> int:
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    return (value + alignment - 1) & ~(alignment - 1)


def _require(raw: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or offset + size > len(raw):
        raise NormalClipFrameError(
            f"{label} outside file at 0x{offset:X}: need {size} bytes, size=0x{len(raw):X}"
        )
    return raw[offset:offset + size]


def rotation_record_size(raw: bytes, offset: int) -> int:
    """Record advance used by the rotation reader @ 0x198B64."""
    first = int.from_bytes(_require(raw, offset, 2, "rotation record"), "big")
    return 12 if first & 0x8000 else 8


def compact_vector_record_size(raw: bytes, offset: int) -> int:
    """4/8-byte vector layout in the inline ProcessFrame path."""
    first = int.from_bytes(_require(raw, offset, 4, "compact vector record"), "big")
    return 8 if first & 0x80000000 else 4


def extended_vector_record_size(raw: bytes, offset: int) -> int:
    """4/8/12-byte vector layout decoded by helper @ 0x198D48."""
    data = _require(raw, offset, 8, "extended vector record/lookahead")
    first = int.from_bytes(data[0:4], "big")
    second = int.from_bytes(data[4:8], "big")
    return 4 + 4 * ((first >> 31) + ((first & second) >> 31))


@dataclass
class ValueRecord:
    channel_type: str
    channel_index: int
    node_index: int
    key_frame: int
    file_offset: int
    record_size: int
    codec: str


@dataclass
class DurationUpdate:
    channel_type: str
    channel_index: int
    node_index: int
    previous_key_frame: int
    previous_duration: int
    duration: int
    next_key_frame: int
    implicit_one: bool


@dataclass
class FrameBlock:
    kind: str
    scan_frame: int
    header_file_offset: int
    header: int
    duration_bit_width: int
    implicit_one_types: list[str]
    explicit_duration_types: list[str]
    duration_stream_file_offset: int | None
    duration_stream_end_file_offset: int | None
    duration_bits_consumed: int
    value_data_file_offset: int
    value_data_end_file_offset: int
    active_rotation_count: int
    active_translation_count: int
    active_scale_count: int
    duration_updates: list[DurationUpdate]
    records: list[ValueRecord]


@dataclass
class NormalClipFrameSchedule:
    type: str
    frame_count: int
    flags: int
    frame_data_file_offset: int
    initial_value_data_file_offset: int
    initial_value_data_end_file_offset: int
    initial_records: list[ValueRecord]
    blocks: list[FrameBlock]
    stream_end_file_offset: int
    trailing_file_offset: int
    trailing_hex: str
    rotation_key_frames: list[list[int]]
    translation_key_frames: list[list[int]]
    scale_key_frames: list[list[int]]
    notes: list[str]

    def to_dict(self, node_names: list[str] | None = None) -> dict[str, Any]:
        out = asdict(self)
        if node_names is not None:
            for record in out["initial_records"]:
                idx = record["node_index"]
                record["node_name"] = (
                    node_names[idx] if 0 <= idx < len(node_names) else f"<node_{idx}>"
                )
            for block in out["blocks"]:
                for collection in (block["duration_updates"], block["records"]):
                    for item in collection:
                        idx = item["node_index"]
                        item["node_name"] = (
                            node_names[idx] if 0 <= idx < len(node_names) else f"<node_{idx}>"
                        )
        return out


class _WordDurationReader:
    """Big-endian 16-bit words, consumed LSB-first within each word."""

    def __init__(self, raw: bytes, offset: int):
        self.raw = raw
        self.start = offset
        self.bit_position = 0

    def _bit(self) -> int:
        word_index, bit_index = divmod(self.bit_position, 16)
        off = self.start + word_index * 2
        word = int.from_bytes(_require(self.raw, off, 2, "duration word"), "big")
        self.bit_position += 1
        return (word >> bit_index) & 1

    def decode(self, payload_width: int) -> int:
        prefix = self._bit()
        if prefix == 0:
            return 1
        value = 0
        for bit in range(payload_width):
            value |= self._bit() << bit
        return value + 1

    @property
    def end_offset(self) -> int:
        return self.start + ((self.bit_position + 15) // 16) * 2


_TYPE_BITS = {"rotation": 4, "translation": 3, "scale": 2}


def _node_lists(setup: Any) -> dict[str, list[int]]:
    idx = setup.indices
    return {
        "rotation": list(idx.rotation.animated_nodes),
        "translation": list(idx.translation.animated_nodes),
        "scale": list(idx.scale.animated_nodes),
    }


def _vector_codec(flags: int, channel_type: str) -> str:
    if channel_type == "translation":
        return (
            "vector_extended_4_8_12"
            if (flags & 0x0C) == 0x0C
            else "vector_compact_4_8"
        )
    if channel_type == "scale":
        return (
            "vector_extended_4_8_12"
            if (flags & 0x30) == 0x30
            else "vector_compact_4_8"
        )
    raise ValueError(channel_type)


def _consume_value_records(
    raw: bytes,
    cursor: int,
    flags: int,
    nodes: dict[str, list[int]],
    active: dict[str, list[int]],
    key_frames: dict[str, list[int]],
    *,
    allow_truncated: bool = False,
) -> tuple[list[ValueRecord], int]:
    records: list[ValueRecord] = []
    for channel_type in ("rotation", "translation", "scale"):
        for channel_index, key_frame in zip(
            active[channel_type], key_frames[channel_type]
        ):
            node_index = nodes[channel_type][channel_index]
            try:
                if channel_type == "rotation":
                    size = rotation_record_size(raw, cursor)
                    codec = "rotation_8_12"
                else:
                    codec = _vector_codec(flags, channel_type)
                    if codec == "vector_extended_4_8_12":
                        size = extended_vector_record_size(raw, cursor)
                    else:
                        size = compact_vector_record_size(raw, cursor)
                _require(raw, cursor, size, f"{channel_type} value record")
            except NormalClipFrameError:
                # Some shipped clips omit a redundant final key record exactly
                # at EOF.  Production playback can hold the previous sparse
                # key; strict diagnostics still reject the malformed stream.
                if allow_truncated and cursor >= len(raw) - 1:
                    return records, len(raw)
                raise
            records.append(
                ValueRecord(
                    channel_type=channel_type,
                    channel_index=channel_index,
                    node_index=node_index,
                    key_frame=key_frame,
                    file_offset=cursor,
                    record_size=size,
                    codec=codec,
                )
            )
            cursor += size
    return records, cursor


def _apply_header(
    raw: bytes,
    cursor: int,
    nodes: dict[str, list[int]],
    active: dict[str, list[int]],
    timing: dict[str, list[list[int]]],
) -> tuple[
    tuple[
        int,
        int,
        int,
        list[str],
        list[str],
        int | None,
        int | None,
        int,
        list[DurationUpdate],
    ],
    int,
]:
    header_offset = cursor
    header = _require(raw, cursor, 1, "frame header")[0]
    cursor += 1
    width = (header & 0x03) + 3
    implicit_types: list[str] = []
    explicit_types: list[str] = []
    pending_explicit: list[tuple[str, int]] = []
    updates: list[DurationUpdate] = []

    for channel_type in ("rotation", "translation", "scale"):
        indices = active[channel_type]
        if header & (1 << _TYPE_BITS[channel_type]):
            if indices:
                implicit_types.append(channel_type)
            for channel_index in indices:
                previous_key, previous_duration = timing[channel_type][channel_index]
                duration = 1
                next_key = previous_key + previous_duration + duration
                timing[channel_type][channel_index] = [
                    previous_key + previous_duration,
                    duration,
                ]
                updates.append(
                    DurationUpdate(
                        channel_type=channel_type,
                        channel_index=channel_index,
                        node_index=nodes[channel_type][channel_index],
                        previous_key_frame=previous_key,
                        previous_duration=previous_duration,
                        duration=duration,
                        next_key_frame=next_key,
                        implicit_one=True,
                    )
                )
        elif indices:
            explicit_types.append(channel_type)
            pending_explicit.extend(
                (channel_type, channel_index) for channel_index in indices
            )

    duration_start: int | None = None
    duration_end: int | None = None
    bits_consumed = 0
    if pending_explicit:
        cursor = align_up(cursor, 2)
        duration_start = cursor
        reader = _WordDurationReader(raw, cursor)
        for channel_type, channel_index in pending_explicit:
            duration = reader.decode(width)
            previous_key, previous_duration = timing[channel_type][channel_index]
            next_key = previous_key + previous_duration + duration
            timing[channel_type][channel_index] = [
                previous_key + previous_duration,
                duration,
            ]
            updates.append(
                DurationUpdate(
                    channel_type=channel_type,
                    channel_index=channel_index,
                    node_index=nodes[channel_type][channel_index],
                    previous_key_frame=previous_key,
                    previous_duration=previous_duration,
                    duration=duration,
                    next_key_frame=next_key,
                    implicit_one=False,
                )
            )
        bits_consumed = reader.bit_position
        duration_end = reader.end_offset
        cursor = duration_end

    return (
        (
            header_offset,
            header,
            width,
            implicit_types,
            explicit_types,
            duration_start,
            duration_end,
            bits_consumed,
            updates,
        ),
        cursor,
    )


def parse_frame_schedule_from_setup(
    raw: bytes, setup: Any, *, strict: bool = True
) -> NormalClipFrameSchedule:
    nodes = _node_lists(setup)
    flags = int(setup.indices.flags)
    frame_count = int(setup.indices.frame_count_field)
    if frame_count < 2:
        raise NormalClipFrameError(
            f"normal_clip frame count {frame_count} is not supported"
        )

    all_active = {name: list(range(len(values))) for name, values in nodes.items()}
    timing = {name: [[0, 0] for _ in values] for name, values in nodes.items()}
    key_tracks = {name: [[0] for _ in values] for name, values in nodes.items()}

    cursor = align_up(int(setup.frame_data_file_offset), 4)
    initial_start = cursor
    zero_frames = {name: [0] * len(values) for name, values in nodes.items()}
    initial_records, cursor = _consume_value_records(
        raw, cursor, flags, nodes, all_active, zero_frames, allow_truncated=not strict
    )
    initial_end = cursor

    header_data, cursor = _apply_header(raw, cursor, nodes, all_active, timing)
    value_start = align_up(cursor, 4)
    second_key_frames = {
        name: [timing[name][i][0] + timing[name][i][1] for i in all_active[name]]
        for name in nodes
    }
    second_records, value_end = _consume_value_records(
        raw, value_start, flags, nodes, all_active, second_key_frames, allow_truncated=not strict
    )
    for name in nodes:
        for i, frame in enumerate(second_key_frames[name]):
            key_tracks[name][i].append(frame)

    blocks: list[FrameBlock] = [
        FrameBlock(
            kind="setup",
            scan_frame=0,
            header_file_offset=header_data[0],
            header=header_data[1],
            duration_bit_width=header_data[2],
            implicit_one_types=header_data[3],
            explicit_duration_types=header_data[4],
            duration_stream_file_offset=header_data[5],
            duration_stream_end_file_offset=header_data[6],
            duration_bits_consumed=header_data[7],
            value_data_file_offset=value_start,
            value_data_end_file_offset=value_end,
            active_rotation_count=len(nodes["rotation"]),
            active_translation_count=len(nodes["translation"]),
            active_scale_count=len(nodes["scale"]),
            duration_updates=header_data[8],
            records=second_records,
        )
    ]
    cursor = value_end

    # To prepare the final resource frame, scan frames 1..frame_count-2.
    for scan_frame in range(1, frame_count - 1):
        active = {
            name: [
                i
                for i, (key, duration) in enumerate(timing[name])
                if key + duration == scan_frame
            ]
            for name in nodes
        }
        if not strict and not any(active.values()):
            # No channel reaches another key inside this clip.  Some resources
            # end here instead of serializing empty headers up to frame_count.
            break
        header_data, cursor = _apply_header(raw, cursor, nodes, active, timing)
        value_start = align_up(cursor, 4)
        new_key_frames = {
            name: [
                timing[name][i][0] + timing[name][i][1]
                for i in active[name]
            ]
            for name in nodes
        }
        record_active = active
        record_key_frames = new_key_frames
        if not strict:
            # A duration is allowed to carry a sparse key beyond the clip's
            # final sampled frame.  The game holds the previous value and does
            # not serialize a payload for that out-of-range key.
            record_active = {name: [] for name in nodes}
            record_key_frames = {name: [] for name in nodes}
            for name in nodes:
                for channel_index, key_frame in zip(active[name], new_key_frames[name]):
                    if key_frame < frame_count:
                        record_active[name].append(channel_index)
                        record_key_frames[name].append(key_frame)
        records, value_end = _consume_value_records(
            raw,
            value_start,
            flags,
            nodes,
            record_active,
            record_key_frames,
            allow_truncated=not strict,
        )
        for name in nodes:
            for i, frame in zip(record_active[name], record_key_frames[name]):
                key_tracks[name][i].append(frame)
        blocks.append(
            FrameBlock(
                kind="frame",
                scan_frame=scan_frame,
                header_file_offset=header_data[0],
                header=header_data[1],
                duration_bit_width=header_data[2],
                implicit_one_types=header_data[3],
                explicit_duration_types=header_data[4],
                duration_stream_file_offset=header_data[5],
                duration_stream_end_file_offset=header_data[6],
                duration_bits_consumed=header_data[7],
                value_data_file_offset=value_start,
                value_data_end_file_offset=value_end,
                active_rotation_count=len(active["rotation"]),
                active_translation_count=len(active["translation"]),
                active_scale_count=len(active["scale"]),
                duration_updates=header_data[8],
                records=records,
            )
        )
        cursor = value_end

    trailing = raw[cursor:]
    if strict:
        expected_last = frame_count - 1
        for channel_type, tracks in key_tracks.items():
            for channel_index, track in enumerate(tracks):
                if not track or track[0] != 0 or track[-1] != expected_last:
                    raise NormalClipFrameError(
                        f"{channel_type}[{channel_index}] key coverage "
                        f"{track[:1]}..{track[-1:]}, expected 0..{expected_last}"
                    )
                if any(a >= b for a, b in zip(track, track[1:])):
                    raise NormalClipFrameError(
                        f"{channel_type}[{channel_index}] key frames are not "
                        f"strictly increasing: {track}"
                    )
        if any(trailing):
            raise NormalClipFrameError(
                f"non-zero trailing data after frame stream at 0x{cursor:X}: "
                f"{trailing[:32].hex()}"
            )
        for block in blocks:
            if block.header & 0xE0:
                raise NormalClipFrameError(
                    f"unknown frame-header high bits at "
                    f"0x{block.header_file_offset:X}: 0x{block.header:02X}"
                )

    return NormalClipFrameSchedule(
        type="ANIM_NORMAL_CLIP_FRAME_SCHEDULE",
        frame_count=frame_count,
        flags=flags,
        frame_data_file_offset=int(setup.frame_data_file_offset),
        initial_value_data_file_offset=initial_start,
        initial_value_data_end_file_offset=initial_end,
        initial_records=initial_records,
        blocks=blocks,
        stream_end_file_offset=cursor,
        trailing_file_offset=cursor,
        trailing_hex=trailing.hex(),
        rotation_key_frames=key_tracks["rotation"],
        translation_key_frames=key_tracks["translation"],
        scale_key_frames=key_tracks["scale"],
        notes=[
            "Frame value blocks are 4-byte aligned; explicit duration streams are 2-byte aligned.",
            "Duration words are big-endian u16 and consumed LSB-first within each word.",
            "Duration prefix 0 encodes 1; prefix 1 encodes the next 3..6 bits plus 1.",
            "Header bits 4/3/2 select implicit duration 1 for rotation/translation/scale.",
            "Record boundaries and key times are resolved; payload values are not decoded yet.",
        ],
    )


def parse_normal_clip_frames(
    raw: bytes, node_count: int, *, strict: bool = True
) -> NormalClipFrameSchedule:
    from anim_normal_clip_setup import parse_normal_clip_setup

    setup = parse_normal_clip_setup(raw, node_count, strict=strict)
    return parse_frame_schedule_from_setup(raw, setup, strict=strict)
