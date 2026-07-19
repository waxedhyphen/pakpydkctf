import math
import unittest

from anim_normal_clip_setup import (
    VEC_RANGE_COARSE_MULTIPLIER,
    VEC_RANGE_FINE_MULTIPLIER,
    scale_span_multiplier,
    translation_span_multiplier,
)
from anim_normal_clip_values import (
    decode_compact_vector_payload,
    decode_extended_vector_payload,
    decode_rotation_payload,
)


class SetupMultiplierTests(unittest.TestCase):
    def test_exact_vector_multiplier_constants(self):
        self.assertEqual(VEC_RANGE_FINE_MULTIPLIER.hex(), "0x1.0000000000000p-30")
        self.assertEqual(VEC_RANGE_COARSE_MULTIPLIER.hex(), "0x1.0000100000000p-20")

    def test_translation_codec_flags_select_multiplier(self):
        self.assertEqual(translation_span_multiplier(0x0C), VEC_RANGE_FINE_MULTIPLIER)
        self.assertEqual(translation_span_multiplier(0x08), VEC_RANGE_COARSE_MULTIPLIER)
        self.assertEqual(translation_span_multiplier(0x04), VEC_RANGE_COARSE_MULTIPLIER)

    def test_scale_codec_flags_select_multiplier(self):
        self.assertEqual(scale_span_multiplier(0x30), VEC_RANGE_FINE_MULTIPLIER)
        self.assertEqual(scale_span_multiplier(0x20), VEC_RANGE_COARSE_MULTIPLIER)
        self.assertEqual(scale_span_multiplier(0x10), VEC_RANGE_COARSE_MULTIPLIER)


class RotationPayloadTests(unittest.TestCase):
    def test_real_extended_rotation_fixture(self):
        payload = decode_rotation_payload(
            bytes.fromhex("8000928f1cf19e2d20ee7554"),
            0,
            -0.375,
            0.375 * (2.0**-23),
        )
        self.assertEqual(payload["quantized_xyz"], (9605102, 1896821, 10366292))
        self.assertTrue(payload["extended"])
        self.assertFalse(payload["special"])
        expected = (
            0.9513186669831153,
            0.05438151955604553,
            -0.2902054935693741,
            0.08840936422348022,
        )
        for actual, wanted in zip(payload["quaternion_wxyz"], expected):
            self.assertAlmostEqual(actual, wanted, places=12)
        norm = math.sqrt(sum(value * value for value in payload["quaternion_wxyz"]))
        self.assertAlmostEqual(norm, 1.0, places=12)

    def test_compact_special_axis_quaternion(self):
        record = bytes.fromhex("400100020001000300000000")
        payload = decode_rotation_payload(record, 0, -1.0, 1.0)
        self.assertTrue(payload["special"])
        self.assertFalse(payload["extended"])
        self.assertEqual(payload["quantized_xyz"], None)
        self.assertEqual(payload["quaternion_wxyz"], (0.0, 0.0, -1.0, 0.0))


class VectorPayloadTests(unittest.TestCase):
    def test_compact_20_bit_fixture(self):
        base = (0.13582677114754915, -0.042322834488004446, -0.06102362181991339)
        span = (3.754626859638719e-09, 2.1119776085467796e-08, 7.978582076732279e-08)
        payload = decode_compact_vector_payload(
            bytes.fromhex("89efbfff2074a7ef"), 0, base, span
        )
        self.assertEqual(payload["quantized_xyz"], (162311, 1031465, 1048559))
        expected = (0.13643618838776397, -0.020538524648007407, 0.022636518618049828)
        for actual, wanted in zip(payload["value_xyz"], expected):
            self.assertAlmostEqual(actual, wanted, places=12)

    def test_extended_30_bit_fixture_with_lookahead(self):
        base = (0.9921259805560112,) * 3
        span = (
            2.9332994366804144e-11,
            1.4666497183402072e-11,
            1.4666497183402072e-11,
        )
        payload = decode_extended_vector_payload(
            bytes.fromhex("074a328c34700000074a328c"), 0, base, span
        )
        self.assertEqual(payload["quantized_xyz"], (122494068, 683672204, 683672204))
        expected = (0.9957190983626221, 1.0021530570103474, 1.0021530570103474)
        for actual, wanted in zip(payload["value_xyz"], expected):
            self.assertAlmostEqual(actual, wanted, places=12)


if __name__ == "__main__":
    unittest.main()
