import math
import unittest

import anim_tf_codec as codec


class TropicalFreezeCodecTests(unittest.TestCase):
    def test_smallest_three_roundtrip(self):
        source = [0.78, -0.33, 0.40, 0.35]
        packed = codec.encode_smallest_three_u64_be(source)
        decoded = codec.decode_smallest_three_u64_be(packed)
        length = math.sqrt(sum(item * item for item in source))
        expected = [item / length for item in source]
        # q and -q represent the same rotation.
        dot = abs(sum(a * b for a, b in zip(expected, decoded)))
        self.assertGreater(dot, 0.999999)

    def test_known_urchin_compact_key(self):
        decoded = codec.decode_smallest_three_u64_be(bytes.fromhex("088a398f3eb7ef60"))
        expected = [0.782160599, -0.329691845, 0.395662179, 0.350684368]
        for actual, wanted in zip(decoded, expected):
            self.assertAlmostEqual(actual, wanted, places=8)

    def test_lsb_node_mask(self):
        # Nodes 1, 6 and 10 in an eleven-node skeleton.
        body = bytes([0b01000010, 0b00000100])
        self.assertEqual(codec.active_node_indices(body, 11), [1, 6, 10])


if __name__ == "__main__":
    unittest.main()
