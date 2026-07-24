from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from exefs_patch import ExeFsPatchEntry, build_ips32, export_atmosphere_patch, preview_project
from test_exefs_functions import build_code_nso


class ExeFsPatchTests(unittest.TestCase):
    def test_preview_and_ips32_offset(self):
        image = build_code_nso(bytes.fromhex("29 15 1E 12 C0 03 5F D6"))
        entry = ExeFsPatchEntry(
            0,
            bytes.fromhex("29 15 1E 12"),
            bytes.fromhex("29 19 1F 12"),
            "mask",
        )
        preview = preview_project(image, "test", (entry,))
        self.assertTrue(preview.valid)
        payload = build_ips32(preview)
        self.assertEqual(payload[:5], b"IPS32")
        self.assertEqual(int.from_bytes(payload[5:9], "big"), 0x100)
        self.assertEqual(payload[9:11], b"\x00\x04")
        self.assertEqual(payload[11:15], bytes.fromhex("29 19 1F 12"))
        self.assertEqual(payload[-4:], b"EEOF")

    def test_expected_bytes_mismatch_blocks_export(self):
        image = build_code_nso(bytes.fromhex("1F 20 03 D5"))
        entry = ExeFsPatchEntry(
            0,
            bytes.fromhex("29 15 1E 12"),
            bytes.fromhex("29 19 1F 12"),
        )
        preview = preview_project(image, "bad", (entry,))
        self.assertFalse(preview.valid)
        with self.assertRaises(Exception):
            build_ips32(preview)

    def test_atmosphere_folder_export(self):
        image = build_code_nso(bytes.fromhex("29 15 1E 12"))
        entry = ExeFsPatchEntry(
            0,
            bytes.fromhex("29 15 1E 12"),
            bytes.fromhex("29 19 1F 12"),
        )
        preview = preview_project(image, "test", (entry,))
        with tempfile.TemporaryDirectory() as folder:
            result = export_atmosphere_patch(preview, folder, "DKCTF_Test")
            self.assertTrue(Path(result["patch"]).is_file())
            self.assertTrue(Path(result["manifest"]).is_file())
            self.assertTrue(Path(result["report"]).is_file())


if __name__ == "__main__":
    unittest.main()
