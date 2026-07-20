import subprocess
import tempfile
import unittest
from pathlib import Path

import skeletal_tail_patch


class BlenderCharacterAnimationBatchIntegrationTests(unittest.TestCase):
    def test_bulk_action_and_cross_blend_copy(self):
        blender = skeletal_tail_patch._find_blender_exe()
        if not blender:
            self.skipTest("Blender is not installed")
        driver = Path(__file__).with_name("blender_character_animation_batch_test_driver.py")
        with tempfile.TemporaryDirectory() as temp:
            completed = subprocess.run(
                [blender, "--background", "--python", str(driver), "--", "--temp", temp],
                capture_output=True,
                text=True,
                timeout=60,
            )
        self.assertEqual(
            completed.returncode,
            0,
            ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-4000:],
        )


if __name__ == "__main__":
    unittest.main()
