from __future__ import annotations

import hashlib
import struct
import unittest

from exefs_nso import NsoImage
from exefs_strings import catalog_strings, find_callback_records, find_pointer_references, find_strings


def build_string_nso() -> tuple[bytearray, dict[str, int]]:
    text_offset, ro_offset, data_offset = 0x200, 0x300, 0x400
    text_va, ro_va, data_va = 0x0000, 0x1000, 0x2000
    size = 0x100
    raw = bytearray(0x500)
    raw[:4] = b"NSO0"
    struct.pack_into("<III", raw, 0x04, 0, 0, (1 << 3) | (1 << 4) | (1 << 5))
    struct.pack_into("<III", raw, 0x10, text_offset, text_va, size)
    struct.pack_into("<III", raw, 0x20, ro_offset, ro_va, size)
    struct.pack_into("<III", raw, 0x30, data_offset, data_va, size)
    struct.pack_into("<III", raw, 0x60, size, size, size)
    raw[0x40:0x60] = bytes(range(32))
    raw[0xA0:0xC0] = hashlib.sha256(raw[text_offset:text_offset + size]).digest()
    raw[0xC0:0xE0] = hashlib.sha256(raw[ro_offset:ro_offset + size]).digest()
    raw[0xE0:0x100] = hashlib.sha256(raw[data_offset:data_offset + size]).digest()
    return raw, {
        "text_offset": text_offset,
        "ro_offset": ro_offset,
        "data_offset": data_offset,
        "text_va": text_va,
        "ro_va": ro_va,
        "data_va": data_va,
    }


def update_hashes(raw: bytearray, info: dict[str, int]) -> None:
    raw[0xA0:0xC0] = hashlib.sha256(raw[info["text_offset"]:info["text_offset"] + 0x100]).digest()
    raw[0xC0:0xE0] = hashlib.sha256(raw[info["ro_offset"]:info["ro_offset"] + 0x100]).digest()
    raw[0xE0:0x100] = hashlib.sha256(raw[info["data_offset"]:info["data_offset"] + 0x100]).digest()


class ExeFsStringTests(unittest.TestCase):
    def test_string_catalog_and_pointer_reference(self):
        raw, info = build_string_nso()
        value = b"initLevelTransition\0"
        raw[info["ro_offset"]:info["ro_offset"] + len(value)] = value
        struct.pack_into("<Q", raw, info["data_offset"], info["ro_va"])
        update_hashes(raw, info)
        image = NsoImage.from_bytes(bytes(raw))
        catalog = catalog_strings(image, segments=("rodata",), include_utf16=False)
        found = find_strings(image, "initLevelTransition", exact=True, catalog=catalog)
        self.assertEqual(len(found), 1)
        pointers = find_pointer_references(image, {found[0].memory_offset}, segments=("data",))
        self.assertEqual(len(pointers), 1)
        self.assertEqual(pointers[0].memory_offset, info["data_va"])

    def test_callback_record_detection(self):
        raw, info = build_string_nso()
        name = b"callback\0"
        raw[info["ro_offset"]:info["ro_offset"] + len(name)] = name
        struct.pack_into(
            "<QQQQ",
            raw,
            info["data_offset"],
            info["ro_va"],
            1,
            info["text_va"] + 0x40,
            0,
        )
        update_hashes(raw, info)
        image = NsoImage.from_bytes(bytes(raw))
        records = find_callback_records(image)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "callback")
        self.assertEqual(records[0].function_address, 0x40)


if __name__ == "__main__":
    unittest.main()
