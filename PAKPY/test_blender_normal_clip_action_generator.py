import unittest

import blender_normal_clip_action_script_patch as base_patch
from blender_normal_clip_fixed_basis_patch import README, upgrade_script


class BlenderNormalClipActionGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = upgrade_script(base_patch.NORMAL_CLIP_ACTION_SCRIPT)

    def test_generated_script_compiles(self):
        compile(self.script, "blender_import_normal_clip_actions.py", "exec")

    def test_uses_exact_gltf_basis_instead_of_point_fit(self):
        self.assertIn("def gltf_to_blender_conversion():", self.script)
        self.assertIn("(0.0, 0.0, -units_per_meter, 0.0)", self.script)
        self.assertIn("(0.0, units_per_meter, 0.0, 0.0)", self.script)
        self.assertNotIn("def estimate_similarity(", self.script)
        self.assertNotIn("import numpy", self.script)

    def test_applies_global_game_delta_to_blender_rest(self):
        self.assertIn(
            "game_delta = game_current @ game_rest_inverse[pose_bone.name]",
            self.script,
        )
        self.assertIn(
            "target = conversion @ game_delta @ conversion_inverse @ blender_rest_by_bone[pose_bone.name]",
            self.script,
        )
        self.assertIn('"basis_mode": "gltf_yup_to_blender"', self.script)

    def test_small_rigs_are_supported(self):
        self.assertIn("if not entries:", self.script)
        self.assertNotIn("if len(entries) < 3:", self.script)
        self.assertIn("nur einem oder zwei", README)


if __name__ == "__main__":
    unittest.main()
