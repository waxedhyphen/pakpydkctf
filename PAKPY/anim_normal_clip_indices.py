#!/usr/bin/env python3
"""Exact reference parser for DKCTF ANIM normal_clip index data.

Reverse engineered from the supplied ExeFS build:

* ``CAnimStream::CreateAnimData`` @ ``0x193708``
* optional pre-index bit-track setup @ ``0x1954DC`` / ``0x1826DC``
* ``CAnimStreamData::LoadIdxData`` @ ``0x195BA8``

The optional bit track is serialized between ``SAnimStreamStart`` and the
rotation/translation/scale bitmaps.  Its values are not needed by the current
skeletal decoder, but its exact byte length must be consumed before
``LoadIdxData`` starts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


RFRM_HEADER_SIZE = 0x20
ANIM_STREAM_FILE_OFFSET = 0x28
AUXILIARY_TRACK_SETUP_BITS = 8


class LoadIdxDataError(ValueError):
    pass


def ceil_div(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def u16le(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 2 > len(data):
        raise LoadIdxDataError(f"u16 read outside stream at 0x{offset:X}")
    return int.from_bytes(data[offset : offset + 2], "little")


def set_bit_indices_lsb(data: bytes) -> list[int]:
    """Expand bytes exactly in the order used by BuildBoneMap."""
    result: list[int] = []
    for byte_index, value in enumerate(data):
        for bit_index in range(8):
            if value & (1 << bit_index):
                result.append(byte_index * 8 + bit_index)
    return result


def compute_stream_start_offset(stream: bytes) -> int:
    """Port of ``CAnimStream::CreateAnimData`` @ ``0x193708``.

    ``stream`` starts at the ANIM control word (file offset ``0x28``).  The
    return value is relative to ``stream`` and points at ``SAnimStreamStart``.
    """
    header = u16le(stream, 0)
    offset = 8
    offset = (offset & ~1) | ((header >> 6) & 1)
    offset += (header >> 2) & 1
    if header & 0x80:
        if offset >= len(stream):
            raise LoadIdxDataError("truncated extended stream header")
        offset = offset + stream[offset] * 4 + 7
    return offset


def decode_stream_sample_count(stream: bytes) -> int:
    """Port the control-field count helper at ExeFS text ``0x192F74``.

    Most normal clips store an 8-bit count in control byte 3.  Formats whose
    first control byte sets bit 6 extend it with control byte 8.
    """
    _read_exact(stream, 0, 4, "ANIM control word")
    count = stream[3]
    if stream[0] & 0x40:
        count |= _read_exact(stream, 8, 1, "extended ANIM sample count")[0] << 8
    return count


def has_auxiliary_pre_index_track(stream: bytes) -> bool:
    """Match the signed-halfword test at ExeFS text ``0x1954DC``."""
    _read_exact(stream, 0, 2, "ANIM control halfword")
    return bool(stream[1] & 0x80)


@dataclass
class AuxiliaryBitTrack:
    descriptor_file_offset: int
    descriptor: int
    descriptor_hex: str
    setup_bit_count: int
    bits_per_sample: int
    sample_count: int
    payload_file_offset: int
    payload_byte_count: int
    end_file_offset: int


@dataclass
class ChannelIndexSet:
    name: str
    presence_flag: int
    present: bool
    base_bitmap_file_offset: int | None
    base_bitmap_hex: str
    base_count: int
    base_nodes: list[int]
    selector_bitmap_file_offset: int | None
    selector_bitmap_hex: str
    animated_count: int
    animated_nodes: list[int]
    constant_count: int
    constant_nodes: list[int]
    base_padding_set_bits: list[int]
    selector_padding_set_bits: list[int]


@dataclass
class LoadIdxDataResult:
    type: str
    source_sha256: str
    node_count: int
    control_u32: str
    control_class: int
    frame_count_field: int
    stream_file_offset: int
    stream_start_relative_offset: int
    stream_start_file_offset: int
    stream_start_byte0: int
    flags: int
    flags_hex: str
    auxiliary_bit_track: AuxiliaryBitTrack | None
    index_data_file_offset: int
    load_pair_data_file_offset: int
    bytes_consumed_by_load_idx_data: int
    rotation: ChannelIndexSet
    translation: ChannelIndexSet
    scale: ChannelIndexSet
    notes: list[str]

    def to_dict(self, node_names: list[str] | None = None) -> dict[str, Any]:
        output = asdict(self)
        if node_names is not None:
            for key in ("rotation", "translation", "scale"):
                channel = output[key]
                channel["base_node_names"] = [
                    node_names[index] if 0 <= index < len(node_names) else f"<node_{index}>"
                    for index in channel["base_nodes"]
                ]
                channel["animated_node_names"] = [
                    node_names[index] if 0 <= index < len(node_names) else f"<node_{index}>"
                    for index in channel["animated_nodes"]
                ]
                channel["constant_node_names"] = [
                    node_names[index] if 0 <= index < len(node_names) else f"<node_{index}>"
                    for index in channel["constant_nodes"]
                ]
        return output


def _read_exact(data: bytes, offset: int, size: int, label: str) -> bytes:
    end = offset + size
    if offset < 0 or end > len(data):
        raise LoadIdxDataError(
            f"{label} truncated: need stream[0x{offset:X}:0x{end:X}], size=0x{len(data):X}"
        )
    return data[offset:end]


def consume_auxiliary_bit_track(
    stream: bytes,
    cursor: int,
    sample_count: int,
) -> tuple[AuxiliaryBitTrack, int]:
    """Consume the generic pre-index bit track loaded at ExeFS ``0x1826DC``.

    The first byte is a descriptor.  When descriptor bit 1 is clear, bits 2..7
    encode the number of bits stored per sample; when bit 1 is set, the track is
    constant and has no per-sample payload.  The current normal-clip layout
    first consumes one 8-bit setup value, matching the codec-0 reader at
    ``0x1825C4``.  The game then advances by the rounded-up total bit count.

    The values themselves are intentionally ignored.  Only the exact cursor
    movement is required before the existing normal-clip index/setup/frame/value
    decoders can run.
    """
    if sample_count < 0:
        raise LoadIdxDataError(f"invalid auxiliary sample count {sample_count}")

    descriptor_offset = cursor
    descriptor = _read_exact(stream, cursor, 1, "auxiliary bit-track descriptor")[0]
    cursor += 1

    bits_per_sample = 0 if descriptor & 0x02 else descriptor >> 2
    payload_bits = AUXILIARY_TRACK_SETUP_BITS + bits_per_sample * sample_count
    payload_bytes = ceil_div(payload_bits, 8)
    _read_exact(stream, cursor, payload_bytes, "auxiliary bit-track payload")
    end = cursor + payload_bytes

    return (
        AuxiliaryBitTrack(
            descriptor_file_offset=ANIM_STREAM_FILE_OFFSET + descriptor_offset,
            descriptor=descriptor,
            descriptor_hex=f"0x{descriptor:02X}",
            setup_bit_count=AUXILIARY_TRACK_SETUP_BITS,
            bits_per_sample=bits_per_sample,
            sample_count=sample_count,
            payload_file_offset=ANIM_STREAM_FILE_OFFSET + cursor,
            payload_byte_count=payload_bytes,
            end_file_offset=ANIM_STREAM_FILE_OFFSET + end,
        ),
        end,
    )


def parse_load_idx_data(raw: bytes, node_count: int, *, strict: bool = True) -> LoadIdxDataResult:
    """Parse the optional pre-index track and exact ``LoadIdxData`` payload.

    ``raw`` must be a complete RFRM/ANIM resource. ``node_count`` is the full
    CSkelLayout node count, not the skin-bone count.
    """
    if node_count <= 0 or node_count > 255:
        raise LoadIdxDataError(f"invalid node_count {node_count}; serialized indices are u8")
    if len(raw) < ANIM_STREAM_FILE_OFFSET + 2:
        raise LoadIdxDataError("ANIM resource is too small")
    if raw[:4] != b"RFRM":
        raise LoadIdxDataError("not an RFRM resource")
    if raw[0x14:0x18] != b"ANIM":
        raise LoadIdxDataError(f"not an ANIM form: {raw[0x14:0x18]!r}")

    stream = raw[ANIM_STREAM_FILE_OFFSET:]
    control = int.from_bytes(raw[0x28:0x2C], "big")
    sample_count = decode_stream_sample_count(stream)
    start_rel = compute_stream_start_offset(stream)
    start = _read_exact(stream, start_rel, 2, "SAnimStreamStart")
    flags = start[1]
    cursor = start_rel + 2

    auxiliary_bit_track: AuxiliaryBitTrack | None = None
    if has_auxiliary_pre_index_track(stream):
        auxiliary_bit_track, cursor = consume_auxiliary_bit_track(
            stream,
            cursor,
            sample_count,
        )

    index_data_start = cursor
    definitions = (
        ("rotation", 0x40),
        ("translation", 0x20),
        ("scale", 0x10),
    )
    base_bitmaps: dict[str, bytes] = {}
    base_nodes: dict[str, list[int]] = {}
    base_offsets: dict[str, int | None] = {}
    base_padding: dict[str, list[int]] = {}
    node_bitmap_size = ceil_div(node_count, 8)

    for name, flag in definitions:
        if flags & flag:
            bitmap = _read_exact(stream, cursor, node_bitmap_size, f"{name} base bitmap")
            base_offsets[name] = ANIM_STREAM_FILE_OFFSET + cursor
            cursor += node_bitmap_size
            expanded = set_bit_indices_lsb(bitmap)
            invalid = [index for index in expanded if index >= node_count]
            if strict and invalid:
                raise LoadIdxDataError(
                    f"{name} base bitmap has set padding indices {invalid} for node_count={node_count}"
                )
            base_bitmaps[name] = bitmap
            base_nodes[name] = [index for index in expanded if index < node_count]
            base_padding[name] = invalid
        else:
            base_offsets[name] = None
            base_bitmaps[name] = b""
            base_nodes[name] = []
            base_padding[name] = []

    channels: dict[str, ChannelIndexSet] = {}
    for name, flag in definitions:
        present = bool(flags & flag)
        if present:
            remap = base_nodes[name]
            selector_size = ceil_div(len(remap), 8)
            selector_offset = ANIM_STREAM_FILE_OFFSET + cursor
            selector = _read_exact(stream, cursor, selector_size, f"{name} selector bitmap")
            cursor += selector_size

            local_set_all = set_bit_indices_lsb(selector)
            invalid_selector = [index for index in local_set_all if index >= len(remap)]
            if strict and invalid_selector:
                raise LoadIdxDataError(
                    f"{name} selector has set padding indices {invalid_selector}; base_count={len(remap)}"
                )
            local_animated = [index for index in local_set_all if index < len(remap)]
            active_lookup = set(local_animated)
            local_constant = [index for index in range(len(remap)) if index not in active_lookup]
            animated = [remap[index] for index in local_animated]
            constant = [remap[index] for index in local_constant]
        else:
            selector_offset = None
            selector = b""
            invalid_selector = []
            animated = []
            constant = []

        channels[name] = ChannelIndexSet(
            name=name,
            presence_flag=flag,
            present=present,
            base_bitmap_file_offset=base_offsets[name],
            base_bitmap_hex=base_bitmaps[name].hex(),
            base_count=len(base_nodes[name]),
            base_nodes=base_nodes[name],
            selector_bitmap_file_offset=selector_offset,
            selector_bitmap_hex=selector.hex(),
            animated_count=len(animated),
            animated_nodes=animated,
            constant_count=len(constant),
            constant_nodes=constant,
            base_padding_set_bits=base_padding[name],
            selector_padding_set_bits=invalid_selector,
        )

    notes = [
        "Bitmap bit order is LSB-first within every byte.",
        "The selector bitmap addresses positions in the base-node list, not skeleton nodes directly.",
        "A negative control halfword enables a generic auxiliary bit track before LoadIdxData.",
        "The auxiliary descriptor controls bits per sample; its values are skipped but not interpreted.",
        "LoadIdxData stores constant-node lists for rotation and translation; constant scale nodes are not persisted.",
        "No keyframe times or sample records are parsed by LoadIdxData.",
    ]

    return LoadIdxDataResult(
        type="DKCTF_ANIM_LOAD_IDX_DATA",
        source_sha256=hashlib.sha256(raw).hexdigest(),
        node_count=node_count,
        control_u32=f"0x{control:08X}",
        control_class=(control >> 24) & 0xFF,
        frame_count_field=sample_count,
        stream_file_offset=ANIM_STREAM_FILE_OFFSET,
        stream_start_relative_offset=start_rel,
        stream_start_file_offset=ANIM_STREAM_FILE_OFFSET + start_rel,
        stream_start_byte0=start[0],
        flags=flags,
        flags_hex=f"0x{flags:02X}",
        auxiliary_bit_track=auxiliary_bit_track,
        index_data_file_offset=ANIM_STREAM_FILE_OFFSET + index_data_start,
        load_pair_data_file_offset=ANIM_STREAM_FILE_OFFSET + cursor,
        bytes_consumed_by_load_idx_data=cursor - index_data_start,
        rotation=channels["rotation"],
        translation=channels["translation"],
        scale=channels["scale"],
        notes=notes,
    )


def load_skeleton_names(path: Path) -> tuple[int, list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise LoadIdxDataError(f"skeleton JSON has no nodes list: {path}")
    names = [str(node.get("name", "")) if isinstance(node, dict) else "" for node in nodes]
    return len(nodes), names


def format_summary(result: LoadIdxDataResult) -> str:
    lines = [
        f"SAnimStreamStart: file 0x{result.stream_start_file_offset:X}, flags {result.flags_hex}",
    ]
    if result.auxiliary_bit_track is not None:
        track = result.auxiliary_bit_track
        lines.append(
            "Auxiliary bit track: "
            f"descriptor {track.descriptor_hex}, {track.bits_per_sample} bits/sample, "
            f"file 0x{track.descriptor_file_offset:X}..0x{track.end_file_offset:X}"
        )
    lines.append(
        f"LoadIdxData payload: 0x{result.index_data_file_offset:X}..0x{result.load_pair_data_file_offset:X} "
        f"({result.bytes_consumed_by_load_idx_data} bytes)"
    )
    for channel in (result.rotation, result.translation, result.scale):
        base_offset = f"0x{channel.base_bitmap_file_offset:X}" if channel.base_bitmap_file_offset is not None else "-"
        selector_offset = f"0x{channel.selector_bitmap_file_offset:X}" if channel.selector_bitmap_file_offset is not None else "-"
        lines.append(
            f"{channel.name:11s}: base={channel.base_count:3d}, "
            f"animated={channel.animated_count:3d}, constant={channel.constant_count:3d}, "
            f"base@{base_offset}, selector@{selector_offset}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("anim", type=Path, help="complete RFRM/ANIM resource")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--nodes", type=int, help="full skeleton node count")
    group.add_argument("--skel", type=Path, help="skeleton JSON containing a nodes list")
    parser.add_argument("--json", type=Path, help="write detailed JSON result")
    parser.add_argument("--non-strict", action="store_true", help="report rather than reject set padding bits")
    args = parser.parse_args()

    node_names: list[str] | None = None
    if args.skel:
        node_count, node_names = load_skeleton_names(args.skel)
    else:
        node_count = args.nodes

    result = parse_load_idx_data(args.anim.read_bytes(), node_count, strict=not args.non_strict)
    print(format_summary(result))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result.to_dict(node_names), indent=2, ensure_ascii=False),
            encoding="utf-8",
            newline="\n",
        )
        print(f"JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
