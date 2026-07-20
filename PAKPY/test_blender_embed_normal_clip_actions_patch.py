import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import blender_embed_normal_clip_actions_patch as embed_patch


class EmbeddedNormalClipActionTests(unittest.TestCase):
    def test_skips_package_without_decoded_bind_files(self):
        with tempfile.TemporaryDirectory() as temp:
            result = embed_patch.embed_normal_clip_actions(temp, {})
        self.assertEqual(result["status"], "skipped:no_normal_clip_bind_files")
        self.assertEqual(result["created_action_count"], 0)

    def test_runs_blender_on_existing_blend_and_reads_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bind_dir = root / "debug" / "anim_normal_clip_bind"
            bind_dir.mkdir(parents=True)
            (bind_dir / "idle.normal_clip_bind.json").write_text("{}", encoding="utf-8")
            blend_path = root / "model" / "actor.experimental_skeletal.blend"
            blend_path.parent.mkdir(parents=True)
            blend_path.write_bytes(b"BLENDER")
            manifest_path = root / "repack_manifest.json"
            manifest_path.write_text(
                json.dumps({"experimental_skeletal_blend": "model/actor.experimental_skeletal.blend"}),
                encoding="utf-8",
            )
            commands = []

            def fake_run(command, **_kwargs):
                commands.append(command)
                (root / embed_patch.REPORT_NAME).write_text(
                    json.dumps(
                        {
                            "created_action_count": 2,
                            "actions": [{"action": "idle"}, {"action": "alert"}],
                            "errors": [],
                        }
                    ),
                    encoding="utf-8",
                )
                return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

            with patch.object(embed_patch.skeletal_tail_patch, "_find_blender_exe", return_value="blender"):
                with patch.object(embed_patch.subprocess, "run", side_effect=fake_run):
                    result = embed_patch.embed_normal_clip_actions(
                        root, {"experimental_skeletal_blend": str(blend_path)}
                    )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["created_action_count"], 2)
            self.assertEqual(len(commands), 1)
            command = commands[0]
            self.assertIn(str(blend_path.resolve()), command)
            self.assertIn("--save", command)
            self.assertTrue((root / "blender_import_normal_clip_actions.py").is_file())

            embed_patch._update_manifest(root, result)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["experimental_skeletal_blend_actions_status"], "ok")
            self.assertEqual(manifest["experimental_skeletal_blend_action_count"], 2)
            self.assertEqual(
                manifest["experimental_skeletal_blend_action_report"],
                embed_patch.REPORT_NAME,
            )


if __name__ == "__main__":
    unittest.main()
