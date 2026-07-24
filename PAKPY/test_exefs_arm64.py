from __future__ import annotations

import unittest

from exefs_arm64 import decode_word, disassemble_image
from exefs_nso import NsoImage
from test_exefs_nso import build_nso


class Arm64DecoderTests(unittest.TestCase):
    def assertDecoded(self, word, address, mnemonic, operand_contains="", target=None):
        got_mnemonic, operands, got_target, _call, _ret = decode_word(word, address)
        self.assertEqual(got_mnemonic, mnemonic)
        if operand_contains:
            self.assertIn(operand_contains, operands)
        if target is not None:
            self.assertEqual(got_target, target)

    def test_control_flow(self):
        self.assertDecoded(0x14000002, 0x1000, "b", "0x1008", 0x1008)
        self.assertDecoded(0x94000002, 0x1000, "bl", "0x1008", 0x1008)
        self.assertDecoded(0x54000040, 0x1000, "b.eq", "0x1008", 0x1008)
        self.assertDecoded(0x35000048, 0x1000, "cbnz", "w8", 0x1008)
        self.assertDecoded(0xD65F03C0, 0x1000, "ret")

    def test_address_and_stack_instructions(self):
        self.assertDecoded(0xD10243FF, 0x24, "sub", "sp, sp, #0x90")
        self.assertDecoded(0xA9074FF4, 0x28, "stp", "x20, x19")
        self.assertDecoded(0xA9087BFD, 0x2C, "stp", "x29, x30")
        self.assertDecoded(0x910203FD, 0x30, "add", "x29, sp, #0x80")
        self.assertDecoded(0xD000CFF3, 0x34, "adrp", "x19")
        self.assertDecoded(0xB940BA68, 0x38, "ldr", "w8, [x19")
        self.assertDecoded(0xAA0203F6, 0x3C, "mov", "x22, x2")
        self.assertDecoded(0x2A0003F5, 0x40, "mov", "w21, w0")
        self.assertDecoded(0xEB09011F, 0x44, "cmp", "x8, x9")

    def test_unknown_is_preserved(self):
        mnemonic, operands, *_ = decode_word(0, 0)
        self.assertEqual(mnemonic, ".word")
        self.assertEqual(operands, "0x00000000")

    def test_disassemble_nso_text(self):
        raw, _ = build_nso()
        mutable = bytearray(raw)
        code = bytes.fromhex("02000014 C0035FD6")
        text_offset = 0x120
        mutable[text_offset:text_offset + len(code)] = code
        image = NsoImage.from_bytes(bytes(mutable))
        result = disassemble_image(image, 0, instruction_count=2, backend="builtin")
        self.assertEqual([item.mnemonic for item in result.instructions], ["b", "ret"])
        self.assertEqual(result.instructions[0].branch_target, 8)


if __name__ == "__main__":
    unittest.main()
