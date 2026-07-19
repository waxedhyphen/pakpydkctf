import math
import unittest
from dataclasses import dataclass

from anim_normal_clip_pose import (
    IDENTITY_ROTATION,
    IDENTITY_SCALE,
    ZERO_TRANSLATION,
    LocalTRS,
    apply_skeleton_maps,
    evaluate_local_pose_frame,
    evaluate_rotation_track,
    evaluate_vector_track,
    linear_lerp_xyz,
    normalized_lerp_wxyz,
    remap_quaternion_wxyz,
    remap_translation_xyz,
    split_skeleton_map_entries,
)


@dataclass
class RotationKey:
    frame: int
    quaternion_wxyz: tuple[float, float, float, float]
    interpolation_sign_bit: int = 0


@dataclass
class VectorKey:
    frame: int
    value_xyz: tuple[float, float, float]


@dataclass
class Track:
    node_index: int
    keys: list


class Values:
    frame_count = 3
    constant_rotations = []
    constant_translations = []
    rotation_tracks = []
    translation_tracks = []
    scale_tracks = []


class PoseTests(unittest.TestCase):
    def test_shortest_path_nlerp(self):
        q = normalized_lerp_wxyz((1, 0, 0, 0), (-1, 0, 0, 0), 0.5, negate_right=True)
        self.assertAlmostEqual(q[0], 1.0)
        self.assertAlmostEqual(sum(x * x for x in q), 1.0)

    def test_right_key_controls_rotation_interval_sign(self):
        track = Track(0, [
            RotationKey(0, (1, 0, 0, 0), 0),
            RotationKey(2, (-1, 0, 0, 0), 1),
        ])
        self.assertEqual(evaluate_rotation_track(track, 1.0), (1.0, 0.0, 0.0, 0.0))

    def test_linear_vector(self):
        self.assertEqual(linear_lerp_xyz((0, 2, 4), (2, 4, 8), 0.5), (1.0, 3.0, 6.0))
        track = Track(0, [VectorKey(0, (0, 0, 0)), VectorKey(2, (2, 4, 6))])
        self.assertEqual(evaluate_vector_track(track, 1.0), (1.0, 2.0, 3.0))

    def test_quaternion_map_sign_and_identity_permutation(self):
        # 0x50 flips sources 2 and 3; 0xE4 maps 0,1,2,3 identically.
        value = remap_quaternion_wxyz((0.5, 0.5, 0.5, 0.5), 0x50E4)
        self.assertEqual(value, (0.5, 0.5, -0.5, -0.5))
        self.assertEqual(remap_quaternion_wxyz((1, 0, 0, 0), 0xFFE4), IDENTITY_ROTATION)

    def test_translation_map_permutation(self):
        # Destinations: source0->2, source1->0, source2->1; no sign flips.
        permutation = (2 << 0) | (0 << 2) | (1 << 4)
        self.assertEqual(remap_translation_xyz((1, 2, 3), permutation), (2.0, 3.0, 1.0))

    def test_missing_channels_inherit_base_pose(self):
        base = [LocalTRS((1, 0, 0, 0), (2, 3, 4), (5, 6, 7))]
        nodes = evaluate_local_pose_frame(Values(), 1, 0.0, base_pose=base)
        self.assertEqual(nodes[0], base[0])
        identity = evaluate_local_pose_frame(Values(), 1, 0.0)[0]
        self.assertEqual(identity.rotation_wxyz, IDENTITY_ROTATION)
        self.assertEqual(identity.scale_xyz, IDENTITY_SCALE)
        self.assertEqual(identity.translation_xyz, ZERO_TRANSLATION)

    def test_apply_maps_and_split(self):
        node = LocalTRS((0.5, 0.5, 0.5, 0.5), (1, 1, 1), (1, 2, 3))
        mapped = apply_skeleton_maps([node], [0x50E4], [0xFFE4])[0]
        self.assertEqual(mapped.rotation_wxyz, (0.5, 0.5, -0.5, -0.5))
        self.assertEqual(mapped.translation_xyz, (1.0, 2.0, 3.0))
        self.assertEqual(split_skeleton_map_entries([1, 2, 3, 4], 2), ([1, 2], [3, 4]))


if __name__ == "__main__":
    unittest.main()
