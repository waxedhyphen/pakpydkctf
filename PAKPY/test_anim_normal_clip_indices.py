import unittest

from anim_normal_clip_indices import parse_load_idx_data, set_bit_indices_lsb


class LoadIdxDataTests(unittest.TestCase):
    def test_lsb_bit_order(self):
        self.assertEqual(set_bit_indices_lsb(bytes([0xEC])), [2, 3, 5, 6, 7])

    def test_synthetic_two_level_maps(self):
        raw = bytearray(0x80)
        raw[0:4] = b"RFRM"
        raw[0x14:0x18] = b"ANIM"
        raw[0x28:0x2C] = bytes.fromhex("00000003")
        start = 0x28 + 8
        raw[start:start + 2] = bytes([1, 0x70])
        cursor = start + 2
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

        result = parse_load_idx_data(bytes(raw), 9)
        self.assertEqual(result.rotation.base_nodes, [0, 2, 8])
        self.assertEqual(result.rotation.animated_nodes, [0, 8])
        self.assertEqual(result.rotation.constant_nodes, [2])
        self.assertEqual(result.translation.animated_nodes, [1])
        self.assertEqual(result.translation.constant_nodes, [3])
        self.assertEqual(result.scale.animated_nodes, [4])
        self.assertEqual(result.load_pair_data_file_offset, cursor + 1)


if __name__ == "__main__":
    unittest.main()
