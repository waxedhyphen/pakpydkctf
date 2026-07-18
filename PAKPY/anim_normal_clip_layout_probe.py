#!/usr/bin/env python3
"""Structural DKCTF ANIM normal-clip probe.

This intentionally does not claim to decode the compressed sample payload.
It exposes fields that are stable across the supplied version-20 clips:
- a seven-byte prefix
- seven big-endian floats and one flag before the body
- three fixed 11-byte candidate channel maps (rotation/translation/scale)
- one zero alignment byte
- the remaining compressed stream
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any, Iterable

RFRM = b"RFRM"
ANIM = b"ANIM"
NORMAL_V20_BODY_OFFSET = 0x54
NODE_COUNT = 81
MASK_BYTES = 11
RAW_FIELD_BITS = MASK_BYTES * 8
MASK_NAMES = ("rotation_candidate", "translation_candidate", "scale_candidate")


def u32be(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"u32 outside file at 0x{offset:X}")
    return int.from_bytes(data[offset : offset + 4], "big")


def f32be(data: bytes, offset: int) -> float:
    if offset < 0 or offset + 4 > len(data):
        raise ValueError(f"f32 outside file at 0x{offset:X}")
    value = struct.unpack_from(">f", data, offset)[0]
    return 0.0 if abs(value) < 1e-30 else float(value)


def trailing_zero_count(data: bytes) -> int:
    return len(data) - len(data.rstrip(b"\0"))


def mask_bits(mask: bytes, bit_order: str = "msb") -> list[int]:
    out: list[int] = []
    for value in mask:
        if bit_order == "msb":
            out.extend((value >> (7 - bit)) & 1 for bit in range(8))
        elif bit_order == "lsb":
            out.extend((value >> bit) & 1 for bit in range(8))
        else:
            raise ValueError("bit_order must be 'msb' or 'lsb'")
    return out


def load_node_names(skel_json: Path | None) -> list[str] | None:
    if skel_json is None:
        return None
    data = json.loads(skel_json.read_text(encoding="utf-8"))
    names = data.get("names") or []
    node_name_indices = data.get("node_name_indices") or []
    if len(node_name_indices) < NODE_COUNT:
        raise ValueError("SKEL JSON has fewer than 81 node_name_indices")
    out: list[str] = []
    for name_index in node_name_indices[:NODE_COUNT]:
        item = names[int(name_index)]
        out.append(str(item.get("name", name_index)) if isinstance(item, dict) else str(item))
    return out


def decode_mask(mask: bytes, node_names: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "hex": mask.hex(),
        "bit_count": sum(value.bit_count() for value in mask),
        "raw_bit_count": len(mask) * 8,
        "skeleton_slot_difference": len(mask) * 8 - NODE_COUNT,
    }
    for order in ("msb", "lsb"):
        bits = mask_bits(mask, order)
        result[f"raw_{order}_set_indices"] = [index for index, value in enumerate(bits) if value]
        mappings: list[dict[str, Any]] = []
        for offset in (0, 7, 8):
            available = max(0, min(NODE_COUNT, len(bits) - offset))
            set_indices = [index for index in range(available) if bits[offset + index]]
            item: dict[str, Any] = {
                "bit_order": order,
                "raw_bit_offset": offset,
                "mapped_node_count": available,
                "unmapped_node_count": NODE_COUNT - available,
                "set_node_indices": set_indices,
            }
            if node_names:
                item["set_node_names"] = [node_names[index] for index in set_indices]
            mappings.append(item)
        result[f"node_mapping_candidates_{order}"] = mappings
    return result


def stride_candidates(stream: bytes, frame_count: int) -> list[dict[str, int]]:
    """Find small head/tail adjustments that make the stream frame-divisible.

    Divisibility is only a structural clue, not proof that records are frame-strided.
    """
    if frame_count <= 0:
        return []
    candidates: list[dict[str, int]] = []
    for head in range(0, 65):
        for tail in range(0, 65):
            usable = len(stream) - head - tail
            if usable <= 0 or usable % frame_count:
                continue
            candidates.append(
                {
                    "head_bytes": head,
                    "tail_bytes": tail,
                    "record_bytes": usable // frame_count,
                    "record_bits": (usable // frame_count) * 8,
                }
            )
    candidates.sort(key=lambda item: (item["head_bytes"] + item["tail_bytes"], item["head_bytes"]))
    return candidates[:16]


def parse_anim(path: Path, skel_json: Path | None = None) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) < NORMAL_V20_BODY_OFFSET:
        raise ValueError("file is too small for the observed normal-clip layout")
    if raw[:4] != RFRM:
        raise ValueError("missing RFRM form magic")
    if raw[0x14:0x18] != ANIM:
        raise ValueError("missing ANIM form magic at 0x14")

    version_a = u32be(raw, 0x18)
    version_b = u32be(raw, 0x1C)
    marker = u32be(raw, 0x20)
    inner_size = u32be(raw, 0x24)
    control = u32be(raw, 0x28)
    group_hash = u32be(raw, 0x2C)
    frame_count = control & 0xFF
    family = {
        0x81: "normal_clip",
        0x82: "packed_clip_82",
        0xC1: "packed_state_c1",
        0xC2: "packed_state_c2",
    }.get((control >> 24) & 0xFF, "unknown")

    prefix = raw[0x30:0x37]
    header_floats = [f32be(raw, 0x37 + index * 4) for index in range(7)]
    header_flag = raw[0x53]
    body = raw[NORMAL_V20_BODY_OFFSET:]
    if len(body) < MASK_BYTES * 3 + 1:
        raise ValueError("body is too small for three 11-byte fields plus alignment byte")

    node_names = load_node_names(skel_json)
    masks = [body[index * MASK_BYTES : (index + 1) * MASK_BYTES] for index in range(3)]
    alignment = body[MASK_BYTES * 3]
    stream = body[MASK_BYTES * 3 + 1 :]
    zero_tail = trailing_zero_count(stream)
    stream_used = stream[:-zero_tail] if zero_tail else stream

    return {
        "type": "DKCTF_ANIM_NORMAL_CLIP_STRUCTURAL_PROBE",
        "status": "structural_only_not_sample_decoded",
        "source": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "file_size": len(raw),
        "form": {
            "magic": raw[:4].decode("ascii", errors="replace"),
            "outer_size": u32be(raw, 4),
            "anim_magic": raw[0x14:0x18].decode("ascii", errors="replace"),
            "version_a": version_a,
            "version_b": version_b,
            "marker_hex": f"0x{marker:08X}",
            "inner_size": inner_size,
            "control_hex": f"0x{control:08X}",
            "family": family,
            "frame_count_low_byte": frame_count,
            "group_hash_hex": f"0x{group_hash:08X}",
        },
        "pre_body_header": {
            "offset": 0x30,
            "size": 36,
            "prefix_hex": prefix.hex(),
            "prefix_bytes": list(prefix),
            "float_encoding": "big_endian_f32",
            "float_values": header_floats,
            "semantic_candidate": {
                "quaternion_wxyz": header_floats[:4],
                "vector_xyz": header_floats[4:7],
                "warning": "Semantics are strongly suggested by cross-clip behavior but not yet proven from game code.",
            },
            "flag": header_flag,
        },
        "body_layout_candidate": {
            "body_offset": NORMAL_V20_BODY_OFFSET,
            "body_size": len(body),
            "skeleton_node_count": NODE_COUNT,
            "raw_field_bits": RAW_FIELD_BITS,
            "unresolved_extra_slots_vs_skeleton": RAW_FIELD_BITS - NODE_COUNT,
            "field_bytes_each": MASK_BYTES,
            "masks": {name: decode_mask(mask, node_names) for name, mask in zip(MASK_NAMES, masks)},
            "alignment_byte_offset_in_body": MASK_BYTES * 3,
            "alignment_byte": alignment,
            "compressed_stream_offset_in_body": MASK_BYTES * 3 + 1,
            "compressed_stream_size": len(stream),
            "compressed_stream_trailing_zero_bytes": zero_tail,
            "compressed_stream_used_size": len(stream_used),
            "compressed_stream_prefix_hex": stream[:128].hex(),
            "frame_stride_candidates": stride_candidates(stream, frame_count),
        },
        "confidence": {
            "three_fixed_11_byte_fields": "high",
            "relationship_of_88_raw_bits_to_81_skeleton_nodes": "unknown",
            "field_semantics_rotation_translation_scale": "medium",
            "pre_body_4_plus_3_float_semantics": "medium_high",
            "compressed_payload_codec": "unknown",
        },
    }


def iter_anim_paths(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
    elif path.is_dir():
        yield from sorted(path.glob("*.anim"))
    else:
        raise FileNotFoundError(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="ANIM file or directory")
    parser.add_argument("--skel-json", type=Path, default=None, help="optional decoded SKEL JSON")
    parser.add_argument("--output", type=Path, required=True, help="JSON output file")
    args = parser.parse_args()

    records = []
    errors = []
    for path in iter_anim_paths(args.input):
        try:
            records.append(parse_anim(path, args.skel_json))
        except Exception as exc:
            errors.append({"source": str(path), "error": f"{type(exc).__name__}: {exc}"})
    payload = {
        "type": "DKCTF_ANIM_NORMAL_CLIP_STRUCTURAL_PROBE_SET",
        "record_count": len(records),
        "error_count": len(errors),
        "records": records,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(records)} records and {len(errors)} errors to {args.output}")
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
