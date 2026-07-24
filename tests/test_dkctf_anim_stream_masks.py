from PAKPY.dkctf_anim_stream_masks import (
    build_active_bone_set,
    build_bone_map,
)


def test_build_bone_map_is_lsb_first_and_advances_rounded_size() -> None:
    result = build_bone_map(9, bytes([0b10000101, 0b00000001, 0xFF]), 0)
    assert result.bone_indices == (0, 2, 7, 8)
    assert result.next_offset == 2


def test_build_active_bone_set_matches_switch_partition() -> None:
    result = build_active_bone_set(8, bytes([0b10000101]))
    assert result.set_bits == (0, 2, 7)
    assert result.clear_bits == (1, 3, 4, 5, 6)
    assert result.next_offset == 1


def test_active_bone_set_processes_padding_bits_like_original() -> None:
    result = build_active_bone_set(9, bytes([0x00, 0x01]))
    assert result.set_bits == (8,)
    assert result.clear_bits == tuple(range(8)) + tuple(range(9, 16))
    assert result.next_offset == 2
