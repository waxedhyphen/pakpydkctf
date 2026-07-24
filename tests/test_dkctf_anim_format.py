from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "PAKPY"))

from dkctf_anim_format import AnimFormatError, parse_anim_bytes


def build_anim(*, family: int = 0x81, frame_count: int = 2, source_count: int = 1) -> bytes:
    c_family = family in {0xC1, 0xC2}
    descriptor_offset = 0x31 if c_family else 0x30
    payload_offset = 0x55 if c_family else 0x54
    data = bytearray(payload_offset + 8)
    data[0:4] = b"RFRM"
    data[0x14:0x18] = b"ANIM"
    struct.pack_into(">I", data, 0x18, 20)
    struct.pack_into(">I", data, 0x1C, 20)
    struct.pack_into(">I", data, 0x20, 0x49170014)
    control = (family << 24) | (frame_count if not c_family else 2)
    struct.pack_into(">I", data, 0x28, control)
    struct.pack_into(">I", data, 0x2C, 0x12345678)
    if c_family:
        data[0x30] = frame_count

    ids = {1: (1,), 3: (1, 2, 3), 4: (1, 2, 3, 4)}[source_count]
    data[descriptor_offset] = 7 * source_count
    data[descriptor_offset + 1] = source_count
    data[descriptor_offset + 2] = 0xFF
    data[descriptor_offset + 3:descriptor_offset + 3 + source_count] = bytes(ids)

    root_offset = descriptor_offset + 7
    struct.pack_into(">4f", data, root_offset, 1.0, 0.0, 0.0, 0.0)
    struct.pack_into(">3f", data, root_offset + 16, 1.0, 2.0, 3.0)
    data[root_offset + 28] = 1
    data[payload_offset:] = b"\x60\x08\x03\x1c\x00\x00\x00\x1c"

    struct.pack_into(">Q", data, 0x04, len(data) - 0x20)
    struct.pack_into(">Q", data, 0x0C, 0)
    struct.pack_into(">I", data, 0x24, len(data) - 0x28)
    return bytes(data)


def test_ordinary_header() -> None:
    anim = parse_anim_bytes(build_anim(family=0x81, frame_count=31, source_count=1))
    assert anim.payload_offset == 0x54
    assert anim.stored_frame_count == 31
    assert anim.descriptor.encoded_width == 7
    assert anim.descriptor.source_ids == (1,)
    assert anim.root_transform.translation_xyz == (1.0, 2.0, 3.0)
    assert math.isclose(anim.root_transform.quaternion_norm_sq, 1.0)


def test_c_family_inserts_byte() -> None:
    anim = parse_anim_bytes(build_anim(family=0xC2, frame_count=38, source_count=4))
    assert anim.payload_offset == 0x55
    assert anim.stored_frame_count == 38
    assert anim.descriptor.encoded_width == 28
    assert anim.descriptor.source_ids == (1, 2, 3, 4)


def test_rejects_non_normalized_quaternion() -> None:
    data = bytearray(build_anim())
    struct.pack_into(">4f", data, 0x37, 2.0, 0.0, 0.0, 0.0)
    try:
        parse_anim_bytes(bytes(data))
    except AnimFormatError as exc:
        assert "not normalized" in str(exc)
    else:
        raise AssertionError("non-normalized quaternion was accepted")
