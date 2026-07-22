import unittest

import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_runtime_compare_fix_patch as patch


class UIAVM2RuntimeCompareFixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch.install()

    def test_undefined_relational_comparison_is_false(self):
        self.assertFalse(patch.binary("greaterthan", runtime._UNDEFINED, 0))
        self.assertFalse(patch.binary("lessthan", runtime._UNDEFINED, 0))

    def test_normal_relational_comparison_uses_base_semantics(self):
        self.assertTrue(patch.binary("greaterthan", 4, 3))
        self.assertTrue(patch.binary("lessequals", 3, 3))


if __name__ == "__main__":
    unittest.main()
