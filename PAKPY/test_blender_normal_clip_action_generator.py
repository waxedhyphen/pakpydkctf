import unittest

import blender_normal_clip_action_script_patch as base_patch
from blender_normal_clip_action_v2_patch import README, upgrade_script


class BlenderNormalClipActionGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = upgrade_script(base_patch.NORMAL_CLIP_ACTION_SCRIPT)

    def test_generated_script_compiles(self):
        compile(self.script, 'blender_import_normal_clip_actions.py', 'exec')

    def test_capture_rate_and_clip_rate_are_separate(self):
        self.assertIn('frame_scale = float(scene_fps) / float(clip_fps)', self.script)
        self.assertIn('blender_frame = 1.0 + source_frame * frame_scale', self.script)
        self.assertIn('--scene-fps', self.script)
        self.assertIn('--clip-fps', self.script)

    def test_bad_rest_basis_is_not_silently_accepted(self):
        self.assertIn('--max-basis-residual', self.script)
        self.assertIn('basis_residual_max > float(max_basis_residual)', self.script)
        self.assertIn('PREFERRED_BASIS_BONES', self.script)

    def test_loop_actions_receive_cycles(self):
        self.assertIn('document_is_cyclic', self.script)
        self.assertIn('curve.modifiers.new(type="CYCLES")', self.script)

    def test_readme_documents_60_hz_capture_mode(self):
        self.assertIn('--scene-fps 60 --clip-fps 30', README)
        self.assertIn('a_pompy_idle_ws', README)


if __name__ == '__main__':
    unittest.main()
