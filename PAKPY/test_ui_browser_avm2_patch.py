import struct
import unittest
from types import SimpleNamespace

import ui_browser_avm2_patch as patch


def _u30(value):
    value = int(value)
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _pool(items, encoder):
    return _u30(len(items) + 1) + b"".join(encoder(item) for item in items)


def _string_pool(strings):
    return _pool(strings, lambda value: _u30(len(value.encode("utf-8"))) + value.encode("utf-8"))


def _trait(name_index, kind, *values):
    data = _u30(name_index) + bytes([kind])
    for value in values:
        data += _u30(value)
    return data


def _body(method_index, code, max_stack=4, local_count=1):
    return (
        _u30(method_index) + _u30(max_stack) + _u30(local_count) + _u30(0) + _u30(1)
        + _u30(len(code)) + code + _u30(0) + _u30(0)
    )


def build_test_abc():
    strings = [
        "pkg", "Doc", "Object", "addFrameScript", "frame1", "stop",
        "gotoAndStop", "iinit", "cinit", "scriptInit",
    ]
    data = bytearray(struct.pack("<HH", 16, 46))
    data += _u30(1)
    data += _u30(1)
    data += _u30(1)
    data += _string_pool(strings)
    data += _u30(3) + bytes([0x16]) + _u30(1) + bytes([0x16]) + _u30(0)
    data += _u30(1)
    data += _u30(7)
    data += bytes([0x07]) + _u30(1) + _u30(2)
    for string_index in (3, 4, 5, 6, 7):
        data += bytes([0x07]) + _u30(2) + _u30(string_index)

    data += _u30(4)
    for name_index in (8, 9, 10, 5):
        data += _u30(0) + _u30(0) + _u30(name_index) + b"\x00"
    data += _u30(0)

    data += _u30(1)
    data += _u30(1) + _u30(2) + b"\x00" + _u30(0) + _u30(0) + _u30(1)
    data += _trait(4, 1, 0, 3)
    data += _u30(1) + _u30(0)
    data += _u30(1) + _u30(2) + _u30(1) + _trait(1, 4, 1, 0)

    iinit = bytes([
        0xD0,
        0x49, 0x00,
        0xD0,
        0x24, 0x00,
        0xD0,
        0x66, 0x04,
        0x4F, 0x03, 0x02,
        0x47,
    ])
    frame1 = bytes([
        0xD0, 0x4F, 0x05, 0x00,
        0xD0, 0x24, 0x03, 0x4F, 0x06, 0x01,
        0x47,
    ])
    data += _u30(4)
    data += _body(0, iinit)
    data += _body(1, b"\x47", 1, 1)
    data += _body(2, b"\x47", 1, 1)
    data += _body(3, frame1)
    return bytes(data)


class UIAVM2PatchTests(unittest.TestCase):
    def test_parse_abc_structural_tables(self):
        abc = patch.parse_abc(build_test_abc())
        self.assertEqual((abc.major_version, abc.minor_version), (46, 16))
        self.assertEqual(abc.class_name(0), "pkg.Doc")
        self.assertEqual(len(abc.methods), 4)
        self.assertEqual(len(abc.method_bodies), 4)
        self.assertEqual(abc.multiname_name(3), "addFrameScript")

    def test_doabc_and_frame_script_extraction(self):
        payload = struct.pack("<I", 1) + b"main\x00" + build_test_abc()
        module = patch.parse_doabc(payload)
        self.assertFalse(module.error)
        bindings = patch.extract_frame_scripts(module)
        self.assertEqual(len(bindings), 1)
        binding = bindings[0]
        self.assertEqual(binding.class_name, "pkg.Doc")
        self.assertEqual(binding.frame, 1)
        self.assertEqual(binding.method_name, "frame1")
        self.assertEqual(
            [(action.operation, action.target) for action in binding.actions],
            [("stop", None), ("gotoAndStop", 3)],
        )

    def test_disassembly_resolves_direct_calls(self):
        abc = patch.parse_abc(build_test_abc())
        instructions = patch.disassemble_method(abc, 3)
        self.assertEqual(instructions[1].name, "callpropvoid")
        self.assertEqual(abc.multiname_name(instructions[1].operands[0]), "stop")
        self.assertIn("gotoAndStop", patch.format_disassembly(abc, 3))

    def test_safe_timeline_action_execution_and_labels(self):
        actions = (
            patch.TimelineAction("play"),
            patch.TimelineAction("gotoAndStop", "highlighted"),
        )
        frame, playing, jumped = patch.execute_timeline_actions(
            1, False, actions, 10, {"highlighted": 7},
        )
        self.assertEqual(frame, 7)
        self.assertFalse(playing)
        self.assertTrue(jumped)
        self.assertIsNone(patch.resolve_action_target("missing", 10, {}))

    def test_inventory_reports_modules_and_frame_scripts(self):
        module = patch.parse_doabc(struct.pack("<I", 0) + b"main\x00" + build_test_abc())
        movie = SimpleNamespace(
            root_tags=[], definitions={}, symbol_classes={0: "pkg.Doc"},
            avm2_modules=(module,), avm2_frame_scripts=patch.extract_frame_scripts(module),
        )
        inventory = patch.avm2_inventory(movie)
        self.assertEqual(inventory["document_class"], "pkg.Doc")
        self.assertEqual(inventory["modules"][0]["classes"], ["pkg.Doc"])
        self.assertEqual(inventory["frame_scripts"][0]["actions"][0]["operation"], "stop")


if __name__ == "__main__":
    unittest.main()
