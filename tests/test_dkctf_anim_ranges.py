import math

import pytest

from PAKPY.dkctf_anim_ranges import decode_vec_range_word, load_vec_ranges


def test_zero_word_decodes_to_zero_range():
    decoded = decode_vec_range_word(0)
    assert decoded.minimum == (0.0, 0.0, 0.0)
    assert decoded.extent == (0.0, 0.0, 0.0)


def test_literal_reference_word():
    decoded = decode_vec_range_word(0x0123456789ABCDEF)
    assert decoded.minimum == pytest.approx(
        (-155.21259784698486, 12.97637790441513, 4.409448802471161)
    )
    assert decoded.extent == pytest.approx(
        (137.07086563110352, -4.283464550971985, -4.283464550971985)
    )


def test_loader_consumes_exactly_eight_bytes_per_record():
    data = bytes.fromhex('0000000000000000 efcdab8967452301 aabb')
    ranges, next_offset = load_vec_ranges(data, 2)
    assert len(ranges) == 2
    assert next_offset == 16


def test_loader_rejects_truncated_record():
    with pytest.raises(ValueError, match='exceed input'):
        load_vec_ranges(b'\x00' * 7, 1)
