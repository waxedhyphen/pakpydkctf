import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import blender_embed_character_actions_patch as character_embed


class CharacterBlendActionEmbedTests(unittest.TestCase):
    def test_final_pass_uses_character_root_bind_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bind_dir = root / "debug" / "anim_normal_clip_bind"
            bind_dir.mkdir(parents=True)
            (bind_dir / "idle.normal_clip_bind.json").write_text("{}", encoding="utf-8")

            model_root = root / "models" / "actor_smdl_package"
            blend_path = model_root / "model" / "actor.experimental_skeletal.blend"
            blend_path.parent.mkdir(parents=True)
            blend_path.write_bytes(b"BLENDER")
            (model_root / "repack_manifest.json").write_text(
                json.dumps({"experimental_skeletal_blend": "model/actor.experimental_skeletal.blend"}),
                encoding="utf-8",
            )
            (root / "manifest.json").write_text(
                json.dumps({"models": [{"model_package_dir": "models/actor_smdl_package"}]}),
                encoding="utf-8",
            )

            calls = []

            def fake_embed(package_dir, result):
                calls.append((Path(package_dir), dict(result)))
                self.assertTrue(
                    (Path(package_dir) / "debug" / "anim_normal_clip_bind" / "idle.normal_clip_bind.json").is_file()
                )
                (root / character_embed.model_embed.REPORT_NAME).write_text("{}", encoding="utf-8")
                return {
                    "status": "ok",
                    "blend_path": str(blend_path),
                    "created_action_count": 4,
                    "error_count": 0,
                    "error": "",
                }

            updated_model_manifests = []
            result = {"package_dir": str(root)}
            with patch.object(
                character_embed.model_embed,
                "embed_normal_clip_actions",
                side_effect=fake_embed,
            ):
                with patch.object(
                    character_embed.model_embed,
                    "_update_manifest",
                    side_effect=lambda *args: updated_model_manifests.append(args),
                ):
                    aggregate = character_embed.embed_character_package_actions(root, result)

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0].resolve(), root.resolve())
            self.assertEqual(aggregate["status"], "ok")
            self.assertEqual(aggregate["created_action_count"], 4)
            self.assertEqual(result["experimental_skeletal_blend_action_count"], 4)
            self.assertEqual(len(updated_model_manifests), 1)
            self.assertTrue(
                (model_root / "debug" / character_embed.model_embed.REPORT_NAME).is_file()
            )
            self.assertTrue((root / character_embed.REPORT_NAME).is_file())

            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["experimental_skeletal_blend_action_count"], 4)
            self.assertEqual(
                manifest["models"][0]["experimental_skeletal_blend_action_count"],
                4,
            )

    def test_wrapper_runs_after_original_writes_bind_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def original(_parsed, _entry, _out_dir, require_store=None):
                bind_dir = root / "debug" / "anim_normal_clip_bind"
                bind_dir.mkdir(parents=True)
                (bind_dir / "idle.normal_clip_bind.json").write_text("{}", encoding="utf-8")
                return {"package_dir": str(root)}

            wrapped = character_embed._wrap_character_export(original)

            def final_pass(package_dir, _result):
                self.assertTrue(
                    (Path(package_dir) / "debug" / "anim_normal_clip_bind" / "idle.normal_clip_bind.json").is_file()
                )
                return {}

            with patch.object(
                character_embed,
                "embed_character_package_actions",
                side_effect=final_pass,
            ) as mocked:
                wrapped(None, None, None)
            mocked.assert_called_once()

    def test_raw_character_export_dispatches_direct_batch_without_bind_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def original(_parsed, _entry, _out_dir, require_store=None):
                return {
                    "package_dir": str(root),
                    "animation_source_mode": "character_root_raw",
                }

            wrapped = character_embed._wrap_character_export(original)
            with patch.object(
                character_embed.character_animation_batch,
                "run_character_animation_batch",
                return_value={"status": "ok"},
            ) as batch_run:
                wrapped(None, None, None)
            batch_run.assert_called_once()
            self.assertEqual(batch_run.call_args.args[0], root.resolve())


if __name__ == "__main__":
    unittest.main()
