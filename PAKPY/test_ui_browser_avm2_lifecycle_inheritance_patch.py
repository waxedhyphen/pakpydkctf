import unittest
from types import SimpleNamespace

import ui_browser_avm2_lifecycle_inheritance_patch as patch


class ABC:
    def __init__(self):
        self.instances = (
            SimpleNamespace(super_name_index=0),
            SimpleNamespace(super_name_index=1),
        )

    def class_name(self, index):
        return ("pkg.Base", "pkg.Derived")[index]

    def multiname_name(self, index):
        return {0: "", 1: "pkg.Base"}.get(index, "")


class InheritanceTests(unittest.TestCase):
    def test_base_initializer_runs_before_derived(self):
        module = SimpleNamespace(abc=ABC())
        movie = object()
        calls = []
        old_find = patch.lifecycle._find_class
        old_base = patch._BASE_INITIALIZE
        patch.lifecycle._find_class = lambda movie, name: (module, 1)
        patch._BASE_INITIALIZE = lambda owner, movie, path, definition, name, frame, playing: calls.append(name) or True
        try:
            self.assertTrue(patch.initialize_instance(None, movie, "root", None, "pkg.Derived"))
        finally:
            patch.lifecycle._find_class = old_find
            patch._BASE_INITIALIZE = old_base
        self.assertEqual(calls, ["pkg.Base", "pkg.Derived"])


if __name__ == "__main__":
    unittest.main()
