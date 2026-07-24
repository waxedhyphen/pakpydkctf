from __future__ import annotations

import hashlib
import struct
import unittest

from exefs_nso import DEFAULT_RUNTIME_BASE, NsoError, NsoImage, parse_int


def lz4_literal_block(data: bytes) -> bytes:
    length = len(data)
    result = bytearray()
    result.append(min(length, 15) << 4)
    if length >= 15:
        remaining = length - 15
        while remaining >= 255:
            result.append(255)
            remaining -= 255
        result.append(remaining)
    result.extend(data)
    return bytes(result)


def build_nso(compress_text: bool = False) -> tuple[bytes, dict[str, bytes]]:
    text = b"TEXT-CONTENT-1234"
    rodata = b"RODATA!!"
    data = b"DATA"
    stored_text = lz4_literal_block(text) if compress_text else text
    module_name = b"dkctf-test\0"

    module_name_offset = 0x100
    text_offset = 0x120
    ro_offset = 0x140
    data_offset = 0x150
    total = data_offset + len(data)
    raw = bytearray(total)
    raw[:4] = b"NSO0"
    flags = (1 if compress_text else 0) | (1 << 12) | (1 << 16) | (1 << 20)
    struct.pack_into("<III", raw, 0x04, 0, 0, flags)
    struct.pack_into("<III", raw, 0x10, text_offset, 0x0000, len(text))
    struct.pack_into("<I", raw, 0x1C, module_name_offset)
    struct.pack_into("<III", raw, 0x20, ro_offset, 0x1000, len(rodata))
    struct.pack_into("<I", raw, 0x2C, len(module_name))
    struct.pack_into("<III", raw, 0x30, data_offset, 0x2000, len(data))
    struct.pack_into("<I", raw, 0x3C, 0x20)
    raw[0x40:0x60] = bytes(range(32))
    struct.pack_into("<III", raw, 0x60, len(stored_text), len(rodata), len(data))
    raw[0xA0:0xC0] = hashlib.sha256(text).digest()
    raw[0xC0:0xE0] = hashlib.sha256(rodata).digest()
    raw[0xE0:0x100] = hashlib.sha256(data).digest()
    raw[module_name_offset:module_name_offset + len(module_name)] = module_name
    raw[text_offset:text_offset + len(stored_text)] = stored_text
    raw[ro_offset:ro_offset + len(rodata)] = rodata
    raw[data_offset:data_offset + len(data)] = data
    return bytes(raw), {"text": text, "rodata": rodata, "data": data}


class NsoImageTests(unittest.TestCase):
    def test_parse_metadata_and_segments(self):
        raw, expected = build_nso()
        image = NsoImage.from_bytes(raw)
        self.assertEqual(image.module_name, "dkctf-test")
        self.assertEqual(image.build_id_hex, bytes(range(32)).hex().upper())
        self.assertEqual(
            [segment.name for segment in image.segments],
            ["text", "rodata", "data", "bss"],
        )
        self.assertEqual(image.segment("bss").memory_offset, 0x2004)
        self.assertEqual(image.read_segment("text", verify_hash=True), expected["text"])
        self.assertEqual(
            image.verify_enabled_hashes(),
            {"text": True, "rodata": True, "data": True},
        )

    def test_uncompressed_address_translation(self):
        raw, _ = build_nso()
        image = NsoImage.from_bytes(raw)
        from_file = image.translate_file_offset(0x123, DEFAULT_RUNTIME_BASE)
        self.assertEqual(from_file.segment, "text")
        self.assertEqual(from_file.memory_offset, 3)
        self.assertEqual(from_file.runtime_address, DEFAULT_RUNTIME_BASE + 3)
        self.assertTrue(from_file.exact_file_mapping)

        from_memory = image.translate_memory_offset(0x1002, DEFAULT_RUNTIME_BASE)
        self.assertEqual(from_memory.file_offset, 0x142)
        self.assertEqual(from_memory.segment, "rodata")

    def test_bss_has_no_file_mapping(self):
        raw, _ = build_nso()
        image = NsoImage.from_bytes(raw)
        result = image.translate_memory_offset(0x2008)
        self.assertEqual(result.segment, "bss")
        self.assertIsNone(result.file_offset)
        self.assertFalse(result.exact_file_mapping)

    def test_compressed_segment_is_decompressed_but_not_fake_mapped(self):
        raw, expected = build_nso(compress_text=True)
        image = NsoImage.from_bytes(raw)
        self.assertTrue(image.segment("text").compressed)
        self.assertEqual(image.read_segment("text", verify_hash=True), expected["text"])
        memory_result = image.translate_memory_offset(2)
        self.assertEqual(memory_result.segment, "text")
        self.assertIsNone(memory_result.file_offset)
        self.assertFalse(memory_result.exact_file_mapping)
        file_result = image.translate_file_offset(0x121)
        self.assertIsNone(file_result.memory_offset)

    def test_runtime_translation(self):
        raw, _ = build_nso()
        image = NsoImage.from_bytes(raw)
        result = image.translate_runtime_address(DEFAULT_RUNTIME_BASE + 0x2001)
        self.assertEqual(result.segment, "data")
        self.assertEqual(result.file_offset, 0x151)
        self.assertEqual(result.memory_offset, 0x2001)

    def test_invalid_magic_and_numbers(self):
        with self.assertRaises(NsoError):
            NsoImage.from_bytes(bytes(0x100))
        self.assertEqual(parse_int("0x7100000000"), DEFAULT_RUNTIME_BASE)
        self.assertEqual(parse_int("7100000000"), 0x7100000000)
        with self.assertRaises(NsoError):
            parse_int("not-an-address")


if __name__ == "__main__":
    unittest.main()
