import unittest

import ui_browser_avm2_duplicate_module_fix_patch as fix
import ui_browser_avm2_repack as repack


class DuplicateDoABCResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fix.install()

    @staticmethod
    def _location(abc_offset, methods):
        return repack.DoABCLocation(
            "<unbenannt>", "root", 0, 0, abc_offset, 100, tuple(methods),
        )

    def test_uses_unique_module_containing_selected_method(self):
        first = self._location(10, (repack.MethodCodeRange(411, 5, 389),))
        second = self._location(500, (repack.MethodCodeRange(12, 5, 20),))
        patch = repack.BytePatch(
            "<unbenannt>", "root", 411, 0x145, b"\xD3", b"\x26",
        )
        self.assertIs(fix._find_module((first, second), patch), first)

    def test_uses_expected_bytes_when_both_modules_have_method(self):
        first = self._location(10, (repack.MethodCodeRange(419, 5, 550),))
        second = self._location(800, (repack.MethodCodeRange(419, 5, 550),))
        patch = repack.BytePatch(
            "<unbenannt>", "root", 419, 0x165,
            b"\x12\x18\x00\x00", b"\x29\x02\x02\x02",
        )
        data = bytearray(1600)
        first_offset = first.abc_offset + first.methods[0].code_offset + patch.code_offset
        second_offset = second.abc_offset + second.methods[0].code_offset + patch.code_offset
        data[first_offset:first_offset + 4] = patch.expected
        data[second_offset:second_offset + 4] = b"\x11\x18\x00\x00"
        fix._LAST_INFLATED_DATA = bytes(data)
        self.assertIs(fix._find_module((first, second), patch), first)

    def test_still_rejects_truly_ambiguous_modules(self):
        first = self._location(10, (repack.MethodCodeRange(1, 5, 20),))
        second = self._location(100, (repack.MethodCodeRange(1, 5, 20),))
        patch = repack.BytePatch(
            "<unbenannt>", "root", 1, 0, b"\x26", b"\x27",
        )
        data = bytearray(200)
        data[15] = 0x26
        data[105] = 0x26
        fix._LAST_INFLATED_DATA = bytes(data)
        with self.assertRaisesRegex(repack.AVM2PatchError, "bleibt mehrdeutig"):
            fix._find_module((first, second), patch)


if __name__ == "__main__":
    unittest.main()
