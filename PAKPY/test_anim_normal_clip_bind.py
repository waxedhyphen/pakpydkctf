import math
import unittest

from anim_normal_clip_bind import (
    affine_inverse,
    build_absolute_no_scale_propagation,
    build_absolute_scale_propagation,
    build_base_absolute,
    build_current_absolute,
    build_relative_coords,
    build_render_matrices,
    compose_animation_with_bind,
    coords_to_matrix,
    derive_layout_start_info,
    matrix_multiply,
    quaternion_multiply_wxyz,
)
from anim_normal_clip_pose import LocalTRS


I = LocalTRS((1.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0))


class BindHierarchyTests(unittest.TestCase):
    def test_layout_start_info_matches_three_control_roots(self):
        info = derive_layout_start_info(
            [255, 255, 255, 0, 3],
            [0x44, 0x1C, 0x2C, 0x05, 0x84],
        )
        self.assertEqual(info.relative_start, 2)
        self.assertEqual(info.hierarchy_start, 3)
        self.assertEqual(info.active_anchor, 2)

    def test_xyss_rotation_order_scale_and_translation(self):
        half = math.sqrt(0.5)
        anim = LocalTRS((half, half, 0.0, 0.0), (2.0, 3.0, 4.0), (1.0, 2.0, 3.0))
        bind = LocalTRS((half, 0.0, half, 0.0), (5.0, 6.0, 7.0), (4.0, 5.0, 6.0))
        result = compose_animation_with_bind(anim, bind)
        self.assertEqual(result.scale_xyz, (10.0, 18.0, 28.0))
        self.assertEqual(result.translation_xyz, (5.0, 7.0, 9.0))
        expected = quaternion_multiply_wxyz(anim.rotation_wxyz, bind.rotation_wxyz)
        for actual, wanted in zip(result.rotation_wxyz, expected):
            self.assertAlmostEqual(actual, wanted)

    def test_affine_inverse_round_trip(self):
        matrix = coords_to_matrix(
            LocalTRS((0.9238795325, 0.0, 0.3826834324, 0.0), (2.0, 3.0, 4.0), (5.0, 6.0, 7.0))
        )
        product = matrix_multiply(matrix, affine_inverse(matrix))
        for row in range(4):
            for column in range(4):
                self.assertAlmostEqual(product[row][column], 1.0 if row == column else 0.0, places=6)

    def test_no_scale_propagation_cancels_parent_relative_scale(self):
        parent_relative = LocalTRS(I.rotation_wxyz, (2.0, 3.0, 4.0), I.translation_xyz)
        parent_absolute = coords_to_matrix(parent_relative)
        child = LocalTRS(I.rotation_wxyz, (5.0, 6.0, 7.0), (1.0, 2.0, 3.0))
        propagated = build_absolute_scale_propagation(parent_absolute, child)
        suppressed = build_absolute_no_scale_propagation(parent_absolute, parent_relative, child)
        self.assertEqual(tuple(propagated[i][i] for i in range(3)), (10.0, 18.0, 28.0))
        self.assertEqual(tuple(suppressed[i][i] for i in range(3)), (5.0, 6.0, 7.0))

    def test_identity_animation_reproduces_rest_skin_matrices(self):
        bind = [
            LocalTRS(I.rotation_wxyz, I.scale_xyz, (0.0, 1.0, 0.0)),
            I,
            LocalTRS(I.rotation_wxyz, I.scale_xyz, (0.0, 1.0, 0.0)),
            LocalTRS(I.rotation_wxyz, I.scale_xyz, (1.0, 0.0, 0.0)),
            LocalTRS(I.rotation_wxyz, I.scale_xyz, (0.0, 2.0, 0.0)),
        ]
        parents = [255, 255, 255, 0, 3]
        flags = [0x44, 0x1C, 0x2C, 0x05, 0x84]
        layout = derive_layout_start_info(parents, flags)
        relative = build_relative_coords([I] * 5, bind, layout)
        base = build_base_absolute(bind, parents, layout)
        current = build_current_absolute(relative, parents, flags, layout)
        render = build_render_matrices(current, [affine_inverse(x) for x in base], [3, 4])
        for matrix in render:
            for row in range(4):
                for column in range(4):
                    self.assertAlmostEqual(matrix[row][column], 1.0 if row == column else 0.0, places=6)


if __name__ == "__main__":
    unittest.main()
