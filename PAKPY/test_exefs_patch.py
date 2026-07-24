from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import exefs_patch
from exefs_patch import (
    ExeFsPatchEntry,
    ExeFsPatchProject,
    build_ips32,
    export_atmosphere_patch,
    export_emulator_patch,
    load_patch_project,
    preview_patch_project,
    preview_project,
    save_patch_project,
)
from test_exefs_functions import build_code_nso


class ExeFsPatchTests(unittest.TestCase):
    def make_entry(self):
        return ExeFsPatchEntry(
            0,
            bytes.fromhex("29 15 1E 12"),
            bytes.fromhex("29 19 1F 12"),
            "mask",
        )

    def test_preview_and_ips32_offset(self):
        image = build_code_nso(bytes.fromhex("29 15 1E 12 C0 03 5F D6"))
        preview = preview_project(image, "test", (self.make_entry(),))
        self.assertTrue(preview.valid)
        payload = build_ips32(preview)
        self.assertEqual(payload[:5], b"IPS32")
        self.assertEqual(int.from_bytes(payload[5:9], "big"), 0x100)
        self.assertEqual(payload[9:11], b"\x00\x04")
        self.assertEqual(payload[11:15], bytes.fromhex("29 19 1F 12"))
        self.assertEqual(payload[-4:], b"EEOF")

    def test_expected_bytes_mismatch_blocks_export(self):
        image = build_code_nso(bytes.fromhex("1F 20 03 D5"))
        preview = preview_project(image, "bad", (self.make_entry(),))
        self.assertFalse(preview.valid)
        with self.assertRaises(Exception):
            build_ips32(preview)

    def test_external_json_roundtrip(self):
        project = ExeFsPatchProject(
            name="generic",
            patch_group="Any_Game",
            expected_build_id="00" * 32,
            notes="data, not Python",
            entries=(self.make_entry(),),
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "project.json"
            save_patch_project(project, path)
            loaded = load_patch_project(path)
        self.assertEqual(loaded, project)

    def test_build_id_mismatch_blocks_export(self):
        image = build_code_nso(bytes.fromhex("29 15 1E 12"))
        project = ExeFsPatchProject(
            name="wrong build",
            patch_group="Any_Game",
            expected_build_id="11" * 32,
            entries=(self.make_entry(),),
        )
        preview = preview_patch_project(image, project)
        self.assertFalse(preview.build_id_valid)
        self.assertFalse(preview.valid)
        with self.assertRaises(Exception):
            build_ips32(preview)

    def test_atmosphere_and_emulator_export(self):
        image = build_code_nso(bytes.fromhex("29 15 1E 12"))
        project = ExeFsPatchProject(
            name="test",
            patch_group="Generic_Test",
            expected_build_id=image.build_id_hex,
            entries=(self.make_entry(),),
        )
        preview = preview_patch_project(image, project)
        with tempfile.TemporaryDirectory() as folder:
            atmosphere = export_atmosphere_patch(preview, folder)
            emulator = export_emulator_patch(preview, Path(folder) / "My Mod")
            self.assertTrue(Path(atmosphere["patch"]).is_file())
            self.assertTrue(Path(atmosphere["manifest"]).is_file())
            self.assertTrue(Path(emulator["patch"]).is_file())
            self.assertEqual(Path(emulator["patch"]).parent.name, "exefs")

    def test_engine_contains_no_dkctf_profile_function(self):
        self.assertFalse(hasattr(exefs_patch, "hardmode_keep_p2_active_entries"))


if __name__ == "__main__":
    unittest.main()
