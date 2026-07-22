import unittest
from types import SimpleNamespace

import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_dynamic_constructor_patch as patch
import ui_browser_avm2_lifecycle_patch as lifecycle


class DynamicConstructorTimingTests(unittest.TestCase):
    def test_linked_constructor_runs_at_new_before_add_child(self):
        movie = SimpleNamespace(_ui_avm2_runtime_owner="owner", ui_avm2_runtime_errors=[])
        context = SimpleNamespace(movie=movie, owner=None)
        obj = dynamic.DynamicDisplayObject(1, "MovieClip", "pkg.Button", path="root/$dyn1:Button")
        calls = []
        old_base = patch._BASE_CONSTRUCT
        old_find = lifecycle._find_class
        old_init = lifecycle.initialize_instance
        patch._BASE_CONSTRUCT = lambda _context, _name, _args: obj
        lifecycle._find_class = lambda _movie, _name: (object(), 0)
        lifecycle.initialize_instance = lambda *args: calls.append(args)
        try:
            self.assertIs(patch.construct_dynamic(context, "pkg.Button"), obj)
            self.assertTrue(obj.extras["initialized"])
            self.assertEqual(len(calls), 1)
            patch.construct_dynamic(context, "pkg.Button")
            self.assertEqual(len(calls), 1)
        finally:
            patch._BASE_CONSTRUCT = old_base
            lifecycle._find_class = old_find
            lifecycle.initialize_instance = old_init

    def test_builtin_without_abc_class_does_not_fake_initializer(self):
        movie = SimpleNamespace(_ui_avm2_runtime_owner=None, ui_avm2_runtime_errors=[])
        context = SimpleNamespace(movie=movie, owner=None)
        obj = dynamic.DynamicDisplayObject(1, "MovieClip", "MovieClip", path="root/$dyn1:MovieClip")
        old_base = patch._BASE_CONSTRUCT
        old_find = lifecycle._find_class
        patch._BASE_CONSTRUCT = lambda _context, _name, _args: obj
        lifecycle._find_class = lambda _movie, _name: None
        try:
            self.assertIs(patch.construct_dynamic(context, "MovieClip"), obj)
            self.assertNotIn("initialized", obj.extras)
        finally:
            patch._BASE_CONSTRUCT = old_base
            lifecycle._find_class = old_find


if __name__ == "__main__":
    unittest.main()
