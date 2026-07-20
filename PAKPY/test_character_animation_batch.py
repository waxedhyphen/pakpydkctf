import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import char_skeletal_package_patch as char_export
import character_animation_batch as batch


def skeleton(name="root", matrix_value=1.0):
    matrix = [
        [matrix_value, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    return {
        "node_count": 1,
        "skin_bone_count": 1,
        "skin_node_indices": [0],
        "nodes": [{"name": name, "parent_index": 255, "matrix": matrix}],
        "bones": [{"name": name, "node_index": 0, "parent_index": -1, "matrix": matrix}],
    }


class CharacterAnimationBatchTests(unittest.TestCase):
    def test_stale_generated_diagnostics_are_removed_without_touching_other_debug_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stale = root / "models" / "body" / "debug" / "anim_normal_clip_bind"
            stale.mkdir(parents=True)
            (stale / "huge.json").write_text("generated", encoding="utf-8")
            keep = root / "models" / "body" / "debug" / "skeleton_debug.json"
            keep.write_text("{}", encoding="utf-8")
            char_export._clear_generated_animation_diagnostics(root)
            self.assertFalse(stale.exists())
            self.assertTrue(keep.is_file())

    def _write_model(self, root, name, skeleton_document):
        model_root = root / "models" / name
        blend = model_root / "model" / f"{name}.experimental_skeletal.blend"
        blend.parent.mkdir(parents=True)
        blend.write_bytes(b"BLENDER")
        debug = model_root / "debug" / "skeleton_debug.json"
        debug.parent.mkdir(parents=True)
        debug.write_text(json.dumps(skeleton_document), encoding="utf-8")
        (model_root / "repack_manifest.json").write_text(
            json.dumps({
                "experimental_skeletal_blend": f"model/{blend.name}",
                "skeleton_debug_json": "debug/skeleton_debug.json",
            }),
            encoding="utf-8",
        )
        return {"resolved": True, "model_package_dir": f"models/{name}"}

    def test_identical_skeletons_share_one_group(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = [
                self._write_model(root, "body", skeleton()),
                self._write_model(root, "head", skeleton()),
            ]
            groups, errors = batch.collect_skeleton_groups(root, {"models": models})
            self.assertEqual(errors, [])
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]["models"]), 2)

    def test_different_rest_pose_creates_another_group(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            models = [
                self._write_model(root, "body", skeleton(matrix_value=1.0)),
                self._write_model(root, "other", skeleton(matrix_value=2.0)),
            ]
            groups, errors = batch.collect_skeleton_groups(root, {"models": models})
            self.assertEqual(errors, [])
            self.assertEqual(len(groups), 2)

    def test_char_export_resolves_animations_once_and_never_feeds_models(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            char_entry = {
                "type": "CHAR",
                "index": 0,
                "uuid_hex": "1" * 32,
                "name": "actor",
            }
            model_entry = {
                "type": "SMDL",
                "index": 1,
                "uuid_hex": "2" * 32,
                "name": "body",
            }
            anim_entry = {
                "type": "ANIM",
                "index": 2,
                "uuid_hex": "3" * 32,
                "name": "idle",
            }
            info = {
                "name": "actor",
                "uuid_hex": char_entry["uuid_hex"],
                "model_slots": [{"index": 0, "slot_name": "body", "uuid_hex": model_entry["uuid_hex"]}],
                "animations": [{"index": 0, "name": "idle", "uuid_hex": anim_entry["uuid_hex"]}],
            }
            parsed = {"path": str(root / "actor.pak")}
            resolve_calls = []

            def resolve(_parsed, uuid_hex, _store):
                resolve_calls.append(uuid_hex)
                if uuid_hex == model_entry["uuid_hex"]:
                    return b"MODEL", model_entry, "pak", parsed["path"]
                if uuid_hex == anim_entry["uuid_hex"]:
                    return b"ANIMATION", anim_entry, "pak", parsed["path"]
                return None, None, "", ""

            def export_model(_parsed, _entry, out_dir, **kwargs):
                self.assertIsNone(kwargs.get("animation_refs"))
                package = Path(out_dir) / "body_smdl_package"
                package.mkdir(parents=True)
                manifest = package / "repack_manifest.json"
                manifest.write_text("{}", encoding="utf-8")
                return {"package_dir": str(package), "manifest_path": str(manifest)}

            with patch.object(char_export, "get_entry_asset", return_value=b"CHAR"):
                with patch.object(char_export.char_codec, "parse_char_asset", return_value=info):
                    with patch.object(char_export.char_codec, "_resolve_ref", side_effect=resolve):
                        with patch.object(char_export, "_collect_skeleton_refs", return_value=[]):
                            with patch("model_package.export_model_package", side_effect=export_model):
                                result = char_export.export_clean_char_package(parsed, char_entry, root)

            package = Path(result["package_dir"])
            self.assertEqual(resolve_calls.count(anim_entry["uuid_hex"]), 1)
            self.assertEqual((package / "source" / "anim").glob("*.anim").__iter__().__next__().read_bytes(), b"ANIMATION")
            for dirname in (
                "anim_probe21",
                "anim_normal_clip_values",
                "anim_normal_clip_pose",
                "anim_normal_clip_bind",
            ):
                self.assertFalse(any(package.rglob(dirname)))


if __name__ == "__main__":
    unittest.main()
