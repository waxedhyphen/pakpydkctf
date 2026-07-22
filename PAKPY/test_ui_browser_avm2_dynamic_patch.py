import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_dynamic_patch as patch


class DummyABC:
    instances = ()

    def multiname_name(self, index):
        return ""


class Owner:
    def __init__(self, movie):
        self._current_movie = movie
        self._ui_playback_running = False
        self.frame_var = SimpleNamespace(get=lambda: 1)
        self.renders = 0

    def request_render(self):
        self.renders += 1


class DynamicDisplayPatchTests(unittest.TestCase):
    def setUp(self):
        self.movie = SimpleNamespace(
            definitions={}, symbol_classes={}, root_tags=[], frame_count=10, frame_rate=10.0,
            labels={}, ui_state_overrides={}, ui_timeline_states={},
            ui_avm2_runtime_enabled=True, ui_avm2_runtime_generation=0,
            ui_avm2_runtime_revision=0, ui_avm2_runtime_properties={},
            ui_avm2_runtime_log=[], ui_avm2_runtime_errors=[],
        )
        self.owner = Owner(self.movie)
        self.movie._ui_avm2_runtime_owner = self.owner
        self.context = runtime.RuntimeContext(
            self.movie, DummyABC(), "pkg.Doc", "root", None, 1, False, 10, {},
            self.owner, {}, {},
        )
        patch._BASE.setdefault("call", lambda context, receiver, name, args: runtime._UNDEFINED)
        patch._BASE.setdefault("get", lambda context, receiver, name: runtime._UNDEFINED)
        patch._BASE.setdefault("set", lambda context, receiver, name, value: False)
        patch._BASE.setdefault("key", lambda value: None)

    def test_construct_add_lookup_and_remove_dynamic_movieclip(self):
        root = self.context.this_ref()
        child = patch.construct_dynamic(self.context, "MovieClip")
        self.assertIsInstance(child, patch.DynamicDisplayObject)
        self.assertIs(patch.call_value(self.context, root, "addChild", (child,)), child)
        self.assertEqual(patch.get_property(self.context, root, "numChildren"), 1)
        self.assertIs(patch.call_value(self.context, root, "getChildByName", (child.name,)), child)
        self.assertIs(patch.call_value(self.context, root, "removeChild", (child,)), child)
        self.assertEqual(patch.get_property(self.context, root, "numChildren"), 0)

    def test_dynamic_transform_text_and_timeline_properties_roundtrip(self):
        child = patch.construct_dynamic(self.context, "TextField")
        patch.set_property(self.context, child, "x", 42)
        patch.set_property(self.context, child, "scaleX", 1.5)
        patch.set_property(self.context, child, "text", "runtime")
        patch.set_property(self.context, child, "tabEnabled", True)
        self.assertEqual(patch.get_property(self.context, child, "x"), 42.0)
        self.assertEqual(patch.get_property(self.context, child, "scaleX"), 1.5)
        self.assertEqual(patch.get_property(self.context, child, "text"), "runtime")
        self.assertTrue(patch.get_property(self.context, child, "tabEnabled"))

    def test_static_transform_properties_rebuild_affine_matrix(self):
        item = ui_browser.DisplayObject(1, matrix=ui_browser.Affine(1, 0, 0, 1, 5, 6), name="button")
        path = "root/1:button"
        self.movie.ui_avm2_runtime_properties[path] = {
            "x": 30, "y": 40, "scaleX": 2, "scaleY": 3, "rotation": 90,
            "enabled": False,
        }
        old = patch._BASE.get("apply")
        patch._BASE["apply"] = lambda movie, parent, depth, value, overrides: (value, path, {})
        try:
            result, returned, _manual = patch.apply_item_override(self.movie, "root", 1, item, {})
        finally:
            patch._BASE["apply"] = old
        self.assertEqual(returned, path)
        self.assertAlmostEqual(result.matrix.tx, 30)
        self.assertAlmostEqual(result.matrix.ty, 40)
        self.assertAlmostEqual(result.matrix.b, 2)
        self.assertAlmostEqual(result.matrix.c, -3)
        self.assertFalse(result._ui_enabled)
        self.assertEqual(item.matrix.tx, 5)

    def test_child_order_operations_are_isolated_from_source_display_list(self):
        root = self.context.this_ref()
        left = patch.construct_dynamic(self.context, "MovieClip")
        right = patch.construct_dynamic(self.context, "MovieClip")
        patch.call_value(self.context, root, "addChild", (left,))
        patch.call_value(self.context, root, "addChildAt", (right, 0))
        self.assertIs(patch.call_value(self.context, root, "getChildAt", (0,)), right)
        patch.call_value(self.context, root, "swapChildren", (left, right))
        self.assertIs(patch.call_value(self.context, root, "getChildAt", (0,)), left)
        self.assertEqual(self.movie.root_tags, [])

    def test_dynamic_objects_use_path_event_dispatcher_keys(self):
        child = patch.construct_dynamic(self.context, "MovieClip")
        self.assertEqual(patch._key(child), ("path", child.path))

    def test_focus_dispatches_focus_out_and_focus_in(self):
        calls = []
        old = lifecycle._dispatch_key
        lifecycle._dispatch_key = lambda movie, key, event: calls.append((key, event.type)) or 1
        try:
            patch._set_focus(self.movie, "root/1:first")
            patch._set_focus(self.movie, "root/2:second")
        finally:
            lifecycle._dispatch_key = old
        self.assertEqual(calls, [
            (("path", "root/1:first"), "focusIn"),
            (("path", "root/1:first"), "focusOut"),
            (("path", "root/2:second"), "focusIn"),
        ])

    def test_dynamic_movieclip_advances_with_ui_timeline(self):
        definition = ui_browser.SpriteDef(7, 3, [])
        child = patch.DynamicDisplayObject(1, "MovieClip", definition=definition, path="root/$dyn1:test", parent_path="root")
        state = patch._state(self.movie)
        state["objects"][1] = child
        state["by_path"][child.path] = 1
        old = patch._BASE.get("advance")
        patch._BASE["advance"] = lambda owner, steps, force_nested=False: None
        try:
            patch.advance(self.owner, 2)
        finally:
            patch._BASE["advance"] = old
        self.assertEqual(child.current_frame, 3)


if __name__ == "__main__":
    unittest.main()
