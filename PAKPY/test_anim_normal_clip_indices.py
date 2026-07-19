import unittest

from anim_normal_clip_indices import (
    LoadIdxDataError,
    consume_auxiliary_bit_track,
    decode_stream_sample_count,
    parse_load_idx_data,
    set_bit_indices_lsb,
)


class LoadIdxDataTests(unittest.TestCase):
    def test_lsb_bit_order(self):
        self.assertEqual(set_bit_indices_lsb(bytes([0xEC])), [2, 3, 5, 6, 7])

    @staticmethod
    def _write_two_level_maps(raw, cursor):
        raw[cursor:cursor + 2] = bytes([0x05, 0x01])
        cursor += 2
        raw[cursor:cursor + 2] = bytes([0x0A, 0x00])
        cursor += 2
        raw[cursor:cursor + 2] = bytes([0x10, 0x00])
        cursor += 2
        raw[cursor] = 0x05
        cursor += 1
        raw[cursor] = 0x01
        cursor += 1
        raw[cursor] = 0x01
        return cursor + 1

    def test_synthetic_two_level_maps(self):
        raw = bytearray(0x80)
        raw[0:4] = b"RFRM"
        raw[0x14:0x18] = b"ANIM"
        raw[0x28:0x2C] = bytes.fromhex("00000003")
        start = 0x28 + 8
        raw[start:start + 2] = bytes([1, 0x70])
        end = self._write_two_level_maps(raw, start + 2)

        result = parse_load_idx_data(bytes(raw), 9)
        self.assertIsNone(result.auxiliary_bit_track)
        self.assertEqual(result.rotation.base_nodes, [0, 2, 8])
        self.assertEqual(result.rotation.animated_nodes, [0, 8])
        self.assertEqual(result.rotation.constant_nodes, [2])
        self.assertEqual(result.translation.animated_nodes, [1])
        self.assertEqual(result.translation.constant_nodes, [3])
        self.assertEqual(result.scale.animated_nodes, [4])
        self.assertEqual(result.load_pair_data_file_offset, end)

    def test_constant_auxiliary_track_moves_index_start_by_two_bytes(self):
        raw = bytearray(0xA0)
        raw[0:4] = b"RFRM"
        raw[0x14:0x18] = b"ANIM"
        raw[0x28:0x2C] = bytes.fromhex("81800003")
        raw[0x30] = 0
        start = 0x28 + 15
        raw[start:start + 2] = bytes([1, 0x70])
        cursor = start + 2
        raw[cursor:cursor + 2] = bytes([0x0E, 0x07])
        cursor += 2
        end = self._write_two_level_maps(raw, cursor)

        result = parse_load_idx_data(bytes(raw), 9)
        track = result.auxiliary_bit_track
        self.assertIsNotNone(track)
        self.assertEqual(track.descriptor, 0x0E)
        self.assertEqual(track.bits_per_sample, 0)
        self.assertEqual(track.payload_byte_count, 1)
        self.assertEqual(result.index_data_file_offset, cursor)
        self.assertEqual(result.load_pair_data_file_offset, end)

    def test_auxiliary_descriptor_is_generic_not_squawks_specific(self):
        raw = bytearray(0xA0)
        raw[0:4] = b"RFRM"
        raw[0x14:0x18] = b"ANIM"
        raw[0x28:0x2C] = bytes.fromhex("81800003")
        raw[0x30] = 0
        start = 0x28 + 15
        raw[start:start + 2] = bytes([1, 0x70])
        cursor = start + 2

        # 0x14 => bit 1 clear and descriptor>>2 == 5 bits per sample.
        # 8 setup bits + 3*5 sample bits = 23 bits => three payload bytes.
        raw[cursor] = 0x14
        raw[cursor + 1:cursor + 4] = bytes([0xA5, 0x5A, 0x03])
        cursor += 4
        end = self._write_two_level_maps(raw, cursor)

        result = parse_load_idx_data(bytes(raw), 9)
        track = result.auxiliary_bit_track
        self.assertIsNotNone(track)
        self.assertEqual(track.descriptor, 0x14)
        self.assertEqual(track.bits_per_sample, 5)
        self.assertEqual(track.payload_byte_count, 3)
        self.assertEqual(result.index_data_file_offset, cursor)
        self.assertEqual(result.load_pair_data_file_offset, end)

    def test_descriptor_bit_one_disables_per_sample_payload(self):
        track, end = consume_auxiliary_bit_track(bytes([0xFE, 0xAA]), 0, 200)
        self.assertEqual(track.bits_per_sample, 0)
        self.assertEqual(track.payload_byte_count, 1)
        self.assertEqual(end, 2)

    def test_auxiliary_payload_truncation_is_rejected(self):
        with self.assertRaises(LoadIdxDataError):
            consume_auxiliary_bit_track(bytes([0x14, 0x00]), 0, 3)

    def test_extended_control_count(self):
        stream = bytearray(9)
        stream[0] = 0x40
        stream[3] = 0x34
        stream[8] = 0x12
        self.assertEqual(decode_stream_sample_count(bytes(stream)), 0x1234)


if __name__ == "__main__":
    unittest.main()
