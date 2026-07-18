"""Donkey Kong Country: Tropical Freeze ANIM decoding primitives.

This module deliberately separates verified decoding from format probes. It
must never turn unknown bit patterns into Blender transforms.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable


class AnimDecodeError(ValueError):
    pass


@dataclass(frozen=True)
class AnimEnvelope:
    control: int
    descriptor: bytes
    body: bytes

    @property
    def family(self) -> str:
        top = (self.control >> 24) & 0xFF
        if top == 0x81:
            return "normal_clip"
        if top == 0x82:
            return "packed_clip_82"
        if top == 0xC1:
            return "packed_state_c1"
        if top == 0xC2:
            return "packed_state_c2"
        return "unknown_raw"

    @property
    def frame_count_hint(self) -> int:
        return self.control & 0xFF


class LsbBitReader:
    """Bit reader matching the little-endian/LSB-first stream used by ANIM."""

    def __init__(self, data: bytes):
        self.data = memoryview(data)
        self.bit_offset = 0

    @property
    def remaining(self) -> int:
        return len(self.data) * 8 - self.bit_offset

    def read(self, width: int) -> int:
        if width < 0 or width > self.remaining:
            raise AnimDecodeError("bitstream is truncated")
        value = 0
        for out_bit in range(width):
            pos = self.bit_offset + out_bit
            value |= ((self.data[pos // 8] >> (pos & 7)) & 1) << out_bit
        self.bit_offset += width
        return value

    def read_mask(self, count: int) -> list[int]:
        return [index for index in range(count) if self.read(1)]


def parse_envelope(asset: bytes) -> AnimEnvelope:
    if len(asset) < 84 or asset[:4] != b"RFRM" or asset[20:24] != b"ANIM":
        raise AnimDecodeError("not a Tropical Freeze RFRM/ANIM asset")
    payload = asset[32:]
    if len(payload) < 52:
        raise AnimDecodeError("ANIM payload is truncated")
    inner_size = int.from_bytes(payload[4:8], "big")
    if inner_size + 8 > len(payload):
        raise AnimDecodeError("ANIM inner size exceeds payload")
    return AnimEnvelope(
        control=int.from_bytes(payload[8:12], "big"),
        descriptor=bytes(payload[16:32]),
        body=bytes(payload[52:]),
    )


def active_node_indices(body: bytes, node_count: int) -> list[int]:
    if node_count <= 0:
        raise AnimDecodeError("skeleton has no nodes")
    return LsbBitReader(body).read_mask(node_count)


def _dequantize_smallest_three(value: int) -> float:
    maximum = (1 << 20) - 1
    return value / maximum * math.sqrt(2.0) - 1.0 / math.sqrt(2.0)


def decode_smallest_three_u64_be(raw: bytes) -> list[float]:
    """Decode TF's verified 64-bit quaternion representation.

    Layout, MSB to LSB: largest-component index (2), largest sign (1), three
    unsigned 20-bit components, one padding bit. Return order is W, X, Y, Z.
    """
    if len(raw) != 8:
        raise AnimDecodeError("a packed quaternion must be exactly 8 bytes")
    packed = int.from_bytes(raw, "big")
    largest_index = (packed >> 62) & 0x3
    largest_negative = bool((packed >> 61) & 0x1)
    mask = (1 << 20) - 1
    stored = [
        (packed >> 41) & mask,
        (packed >> 21) & mask,
        (packed >> 1) & mask,
    ]
    small = [_dequantize_smallest_three(item) for item in stored]
    missing_sq = max(0.0, 1.0 - sum(item * item for item in small))
    largest = math.sqrt(missing_sq)
    if largest_negative:
        largest = -largest
    out: list[float] = []
    cursor = 0
    for component in range(4):
        if component == largest_index:
            out.append(largest)
        else:
            out.append(small[cursor])
            cursor += 1
    length = math.sqrt(sum(item * item for item in out))
    if length <= 1e-12:
        raise AnimDecodeError("decoded zero quaternion")
    return [round(item / length, 9) for item in out]


def encode_smallest_three_u64_be(quaternion: Iterable[float]) -> bytes:
    """Reference encoder used by tests and future ANIM repacking."""
    values = [float(item) for item in quaternion]
    if len(values) != 4:
        raise AnimDecodeError("quaternion must contain W, X, Y, Z")
    length = math.sqrt(sum(item * item for item in values))
    if length <= 1e-12:
        raise AnimDecodeError("cannot encode zero quaternion")
    values = [item / length for item in values]
    largest_index = max(range(4), key=lambda index: abs(values[index]))
    largest_negative = values[largest_index] < 0.0
    maximum = (1 << 20) - 1
    small = [values[index] for index in range(4) if index != largest_index]
    quantized = []
    for item in small:
        scaled = (item + 1.0 / math.sqrt(2.0)) / math.sqrt(2.0)
        quantized.append(max(0, min(maximum, int(round(scaled * maximum)))))
    packed = (largest_index & 3) << 62
    packed |= int(largest_negative) << 61
    packed |= quantized[0] << 41
    packed |= quantized[1] << 21
    packed |= quantized[2] << 1
    return packed.to_bytes(8, "big")


def _node_names(skeleton: dict[str, Any]) -> list[str]:
    return [str(node.get("name") or f"node_{index:03d}") for index, node in enumerate(skeleton.get("nodes") or [])]


def decode_compact21(envelope: AnimEnvelope, skeleton: dict[str, Any]) -> dict[str, Any]:
    """Decode the verified two-key compact clip used by additive eye shifts."""
    used = envelope.body.rstrip(b"\x00")
    names = _node_names(skeleton)
    if envelope.family != "normal_clip" or len(used) != 21:
        raise AnimDecodeError("not a compact21 clip")
    if envelope.frame_count_hint != 2:
        raise AnimDecodeError("compact21 clip does not contain two frames")
    active = active_node_indices(envelope.body, len(names))
    if len(active) != 1:
        raise AnimDecodeError("compact21 currently requires exactly one active node")
    key_blob = used[4:20]
    if len(key_blob) != 16:
        raise AnimDecodeError("compact21 quaternion payload is truncated")
    values = [
        decode_smallest_three_u64_be(key_blob[0:8]),
        decode_smallest_three_u64_be(key_blob[8:16]),
    ]
    node_index = active[0]
    track = {
        "group_index": 0,
        "lane_index": node_index,
        "target_node_index": node_index,
        "target_name_hint": names[node_index],
        "channel": "rotation_quaternion",
        "value_kind": "tf_smallest_three_u64_be_wxyz",
        "timeline_values": values,
        "timeline_frame_count": 2,
        "summary": {"first": values[0], "last": values[-1]},
    }
    return {
        "version": 1,
        "status": "ok:tf_compact21",
        "frame_count_guess": 2,
        "group_count": 1,
        "primary_group_index": 0,
        "primary_timeline_frame_count": 2,
        "groups": [{
            "group_index": 0,
            "start_offset": 0,
            "end_offset": 20,
            "vector_count": len(names),
            "timeline_frame_count": 2,
            "track_value_kind": track["value_kind"],
            "target_order_hint": "explicit_node_index",
            "active_node_indices": active,
            "tracks": [track],
        }],
        "active_node_indices": active,
        "active_node_names": [names[index] for index in active],
    }


def decode_asset(asset: bytes, skeleton: dict[str, Any]) -> dict[str, Any]:
    envelope = parse_envelope(asset)
    names = _node_names(skeleton)
    result: dict[str, Any] = {
        "version": 1,
        "status": f"pending:{envelope.family}",
        "raw_family": envelope.family,
        "frame_count_guess": envelope.frame_count_hint,
        "descriptor_hex": envelope.descriptor.hex(),
        "body_size": len(envelope.body),
    }
    if names:
        active = active_node_indices(envelope.body, len(names))
        result["active_node_indices"] = active
        result["active_node_names"] = [names[index] for index in active]
    if envelope.family == "normal_clip" and len(envelope.body.rstrip(b"\x00")) == 21:
        return decode_compact21(envelope, skeleton)
    result["reason"] = "delta stream layout is not verified; no transforms were fabricated"
    return result
