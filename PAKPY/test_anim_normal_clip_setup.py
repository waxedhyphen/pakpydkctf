import unittest

from anim_normal_clip_setup import (
    ROT_RANGE_SCALE,
    VEC_RANGE_COARSE_MULTIPLIER,
    VEC_RANGE_FINE_MULTIPLIER,
    decode_constant_rotation,
    decode_rotation_ranges,
    decode_vector_range_record,
    scale_span_multiplier,
    translation_span_multiplier,
)


class NormalClipSetupTests(unittest.TestCase):
    def test_rotation_range_nibble_order_and_scale(self):
        ranges, end = decode_rotation_ranges(bytes([0x21]), 0, [4, 9])
        self.assertEqual(end, 1)
        self.assertEqual([item.nibble for item in ranges], [1, 2])
        self.assertEqual([item.nibble_position for item in ranges], ["low", "high"])
        self.assertAlmostEqual(ranges[0].range_value, 0.75)
        self.assertAlmostEqual(ranges[1].range_value, 0.5)
        self.assertAlmostEqual(ranges[0].base, -0.75)
        self.assertAlmostEqual(ranges[0].scale, 0.75 * ROT_RANGE_SCALE)

    def test_constant_rotation_matches_instruction_port(self):
        data = bytes.fromhex("07ffff7ffffa0b840859af7f")
        item = decode_constant_rotation(data, 0, 11)
        self.assertEqual(item.record_size, 8)
        self.assertFalse(item.extended_precision)
        self.assertAlmostEqual(sum(v * v for v in item.quaternion_wxyz), 1.0, places=12)
        self.assertAlmostEqual(item.quaternion_wxyz[0], 0.9667763276800967)
        self.assertAlmostEqual(item.quaternion_wxyz[3], 0.25562380999326706)

    def test_zero_vector_range_record(self):
        base, span = decode_vector_range_record(bytes(8))
        self.assertEqual(base, (0.0, 0.0, 0.0))
        self.assertEqual(span, (0.0, 0.0, 0.0))

    def test_precision_modes_from_stream_flags(self):
        self.assertEqual(translation_span_multiplier(0x79), VEC_RANGE_COARSE_MULTIPLIER)
        self.assertEqual(translation_span_multiplier(0x7D), VEC_RANGE_FINE_MULTIPLIER)
        self.assertEqual(scale_span_multiplier(0x79), VEC_RANGE_FINE_MULTIPLIER)
        self.assertEqual(scale_span_multiplier(0x7A), VEC_RANGE_FINE_MULTIPLIER)


if __name__ == "__main__":
    unittest.main()
