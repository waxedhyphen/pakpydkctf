from __future__ import annotations

import hashlib
import struct
import unittest

from exefs_dataflow import trace_function
from exefs_functions import analyze_function, scan_memory_accesses
from exefs_nso import NsoImage


def build_code_nso(code: bytes) -> NsoImage:
    size = max(0x100, len(code))
    text_offset, ro_offset, data_offset = 0x200, 0x300, 0x400
    raw = bytearray(0x500)
    raw[:4] = b"NSO0"
    struct.pack_into("<III", raw, 0x04, 0, 0, (1 << 3) | (1 << 4) | (1 << 5))
    struct.pack_into("<III", raw, 0x10, text_offset, 0, size)
    struct.pack_into("<III", raw, 0x20, ro_offset, 0x1000, 0x100)
    struct.pack_into("<III", raw, 0x30, data_offset, 0x2000, 0x100)
    struct.pack_into("<III", raw, 0x60, size, 0x100, 0x100)
    raw[text_offset:text_offset + len(code)] = code
    raw[0xA0:0xC0] = hashlib.sha256(raw[text_offset:text_offset + size]).digest()
    raw[0xC0:0xE0] = hashlib.sha256(raw[ro_offset:ro_offset + 0x100]).digest()
    raw[0xE0:0x100] = hashlib.sha256(raw[data_offset:data_offset + 0x100]).digest()
    return NsoImage.from_bytes(bytes(raw))


class FunctionAnalysisTests(unittest.TestCase):
    def test_cfg_and_calls(self):
        code = bytes.fromhex(
            "02000094"
            "02000014"
            "C0035FD6"
            "C0035FD6"
        )
        image = build_code_nso(code)
        summary = analyze_function(image, 0)
        self.assertEqual(summary.calls[0].target, 8)
        self.assertIn(12, summary.returns)
        self.assertIn(12, summary.basic_block_starts)

    def test_memory_field_dataflow(self):
        code = bytes.fromhex(
            "F30300AA"
            "684248B9"
            "1F090071"
            "41000054"
            "C0035FD6"
            "C0035FD6"
        )
        image = build_code_nso(code)
        summary = analyze_function(image, 0)
        traced = trace_function(summary)
        lines = "\n".join(traced.format_lines())
        self.assertIn("load32(arg0+0x840) != 2", lines)
        accesses = scan_memory_accesses(image, displacement=0x840)
        self.assertEqual(len(accesses), 1)
        self.assertEqual(accesses[0].base_register, 19)


if __name__ == "__main__":
    unittest.main()
