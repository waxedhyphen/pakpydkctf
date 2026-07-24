from PAKPY.dkctf_anim_indices import (
    IndexDataError,
    decode_index_channel,
    load_idx_data,
)


def test_decode_channel_uses_second_map_as_indices_into_first_map():
    channel, end = decode_index_channel(bytes([0b00100101, 0b00000010, 0b00001010]), 10)
    assert channel.bone_map == (0, 2, 5, 9)
    assert channel.active == (2, 9)
    assert channel.inactive == (0, 5)
    assert end == 3


def test_load_idx_data_decodes_present_channels_in_trs_order():
    raw = bytes([
        0b00000011, 0b00000010,
        0b00000100, 0b00000001,
    ])
    decoded = load_idx_data(raw, bone_count=8, flags=0x60)
    assert decoded.translation is not None
    assert decoded.translation.active == (1,)
    assert decoded.translation.inactive == (0,)
    assert decoded.rotation is not None
    assert decoded.rotation.active == (2,)
    assert decoded.rotation.inactive == ()
    assert decoded.scale is None
    assert decoded.next_offset == len(raw)


def test_zero_selected_bones_consumes_no_partition_bytes():
    decoded = load_idx_data(b"\x00", bone_count=8, flags=0x40)
    assert decoded.translation is not None
    assert decoded.translation.bone_map == ()
    assert decoded.next_offset == 1


def test_rejects_nonzero_padding_bits():
    try:
        decode_index_channel(bytes([0x80]), bone_count=3)
    except IndexDataError as exc:
        assert "padding" in str(exc)
    else:
        raise AssertionError("expected IndexDataError")
