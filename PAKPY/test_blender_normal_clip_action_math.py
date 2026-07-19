import unittest

from anim_normal_clip_bind import affine_inverse, matrix_multiply


def apply_rest_calibration(conversion, base, current, blender_rest):
    correction = matrix_multiply(affine_inverse(matrix_multiply(conversion, base)), blender_rest)
    return matrix_multiply(matrix_multiply(conversion, current), correction)


class BlenderActionMathTests(unittest.TestCase):
    def test_rest_frame_maps_exactly_to_blender_rest(self):
        conversion = (
            (0.0, -1.0, 0.0, 2.0),
            (1.0, 0.0, 0.0, -3.0),
            (0.0, 0.0, 1.0, 4.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        base = (
            (1.0, 0.0, 0.0, 0.5),
            (0.0, 1.0, 0.0, 1.5),
            (0.0, 0.0, 1.0, -0.25),
            (0.0, 0.0, 0.0, 1.0),
        )
        blender_rest = (
            (0.0, 0.0, 1.0, 0.25),
            (1.0, 0.0, 0.0, 1.5),
            (0.0, 1.0, 0.0, 2.75),
            (0.0, 0.0, 0.0, 1.0),
        )
        result = apply_rest_calibration(conversion, base, base, blender_rest)
        for expected_row, actual_row in zip(blender_rest, result):
            for expected, actual in zip(expected_row, actual_row):
                self.assertAlmostEqual(expected, actual, places=7)

    def test_current_motion_is_preserved_after_rest_correction(self):
        identity = (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        base = identity
        current = (
            (1.0, 0.0, 0.0, 2.0),
            (0.0, 1.0, 0.0, 3.0),
            (0.0, 0.0, 1.0, 4.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        blender_rest = (
            (0.0, -1.0, 0.0, 0.0),
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
        result = apply_rest_calibration(identity, base, current, blender_rest)
        self.assertAlmostEqual(result[0][3], 2.0)
        self.assertAlmostEqual(result[1][3], 3.0)
        self.assertAlmostEqual(result[2][3], 4.0)


if __name__ == "__main__":
    unittest.main()
