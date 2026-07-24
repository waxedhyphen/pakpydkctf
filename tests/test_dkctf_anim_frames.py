from __future__ import annotations

import pytest

from PAKPY.dkctf_anim_frames import (
    FrameDecodeError,
    VectorRange,
    decode_quantized_vector,
    decode_vector_key,
    pack_quantized_vector,
)


@pytest.mark.parametrize(
    "xyz",
    [
        (0, 0, 0),
        (1, 2, 3),
        (0x3FF, 0x400, 0x7FF),
        (0x12345, 0xABCDE, 0xFEDCB),
        (0xFFFFF, 0xFFFFF, 0xFFFFF),
    ],
)
def test_eight_byte_round_trip(xyz: tuple[int, int, int]) -> None:
    raw = pack_quantized_vector(*xyz, byte_count=8)
    decoded = decode_quantized_vector(raw)
    assert (decoded.x, decoded.y, decoded.z) == xyz
    assert decoded.byte_count == 8


def test_four_byte_zero_record() -> None:
    decoded = decode_quantized_vector(b"\x00\x00\x00\x00")
    assert (decoded.x, decoded.y, decoded.z) == (0, 0, 0)
    assert decoded.byte_count == 4


def test_vector_key_interpolation_and_history() -> None:
    raw = pack_quantized_vector(2, 3, 4, byte_count=8)
    key = decode_vector_key(
        raw,
        VectorRange((10.0, 20.0, 30.0), (0.5, 2.0, -1.0)),
        (1.0, 2.0, 3.0),
    )
    assert key.previous == (1.0, 2.0, 3.0)
    assert key.current == (11.0, 26.0, 26.0)
    assert key.next_offset == 8


def test_truncated_records_rejected() -> None:
    with pytest.raises(FrameDecodeError):
        decode_quantized_vector(b"\x00\x00\x00")
    with pytest.raises(FrameDecodeError):
        decode_quantized_vector(b"\x80\x00\x00\x00")
