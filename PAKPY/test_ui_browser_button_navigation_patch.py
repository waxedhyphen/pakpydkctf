import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_state_inspector_patch as inspector
import ui_browser_button_navigation_patch as patch


class Owner:
    def __init__(self, movie):
        self._current_movie = movie
        self.frame_var = SimpleNamespace(get=lambda: 1)
        self.renders = 0
        self._closed = False

    def request_render(self):
        self.renders += 1


def movie():
    value = SimpleNamespace(
        frame_count=10,
        definitions={},
        ui_input_hit_regions=[],
        ui_avm2_runtime_enabled=True,
        ui_avm2_runtime_generation=0,
        ui_avm2_runtime_revision=0,
        ui_avm2_runtime_properties={},
        ui_avm2_runtime_log=[],
        ui_avm2_runtime_errors=[],
        ui_state_overrides={},
        ui_timeline_states={},
        ui_override_revision=0,
        ui_timeline_revision=0,
    )
    value._ui_avm2_runtime_owner = Owner(value)
    return value


class ButtonNavigationTests(unittest.TestCase):
    def test_semantic_labels_resolve_case_and_punctuation(self):
        labels = {
            "default": 1,
            "startHighlighted": 5,
            "start-Pressed": 9,
            "DISABLED": 12,
        }
        descriptor = patch.ButtonDescriptor(
            "root/1:btn", "btn", 12, tuple(labels.items()),
        )
        self.assertEqual(patch.infer_button_frame(descriptor, "up"), 1)
        self.assertEqual(patch.infer_button_frame(descriptor, "over"), 5)
        self.assertEqual(patch.infer_button_frame(descriptor, "down"), 9)
        self.assertEqual(patch.infer_button_frame(descriptor, "disabled"), 12)

    def test_unlabeled_multiframe_button_uses_safe_fallback(self):
        descriptor = patch.ButtonDescriptor("root/1:btnPlay", "btnPlay", 4)
        self.assertEqual(patch.infer_button_frame(descriptor, "up"), 1)
        self.assertEqual(patch.infer_button_frame(descriptor, "over"), 2)
        self.assertEqual(patch.infer_button_frame(descriptor, "down"), 3)
        self.assertEqual(patch.infer_button_frame(descriptor, "disabled"), 4)

    def test_button_detection_uses_labels_flags_and_names(self):
        self.assertTrue(patch.is_button_descriptor(
            patch.ButtonDescriptor("root/1:item", "item", 2, (("highlighted", 2),)),
        ))
        self.assertTrue(patch.is_button_descriptor(
            patch.ButtonDescriptor("root/1:any", "any", button_mode=True),
        ))
        self.assertTrue(patch.is_button_descriptor(
            patch.ButtonDescriptor("root/1:btnBack", "btnBack"),
        ))
        self.assertFalse(patch.is_button_descriptor(
            patch.ButtonDescriptor("root/1:background", "background"),
        ))

    def test_directional_target_prefers_same_row_or_column(self):
        regions = [
            dynamic.HitRegion("left", (0, 40, 20, 60)),
            dynamic.HitRegion("center", (40, 40, 60, 60)),
            dynamic.HitRegion("right", (80, 42, 100, 62)),
            dynamic.HitRegion("far_down", (60, 180, 80, 200)),
        ]
        self.assertEqual(
            patch.directional_target(regions, "center", "right").path,
            "right",
        )
        self.assertEqual(
            patch.directional_target(regions, "center", "left").path,
            "left",
        )
        self.assertEqual(
            patch.directional_target(regions, "center", "down").path,
            "far_down",
        )

    def test_mouse_children_false_retargets_to_parent(self):
        value = movie()
        value.ui_avm2_runtime_properties["root/1:menu"] = {"mouseChildren": False}
        child = dynamic.HitRegion(
            "root/1:menu/2:label", (10, 10, 30, 30), "label",
        )
        result = patch._collapse_mouse_children(value, child)
        self.assertEqual(result.path, "root/1:menu")
        self.assertEqual(result.bounds, child.bounds)

    def test_static_button_state_updates_timeline_without_manual_override(self):
        value = movie()
        owner = value._ui_avm2_runtime_owner
        descriptor = patch.ButtonDescriptor(
            "root/1:btn", "btn", 3,
            (("up", 1), ("over", 2), ("down", 3)),
            button_mode=True,
        )
        old = patch._descriptor
        patch._descriptor = lambda _owner, _path, _region=None: descriptor
        try:
            self.assertTrue(patch._set_button_state(owner, descriptor.path, "over"))
        finally:
            patch._descriptor = old
        self.assertEqual(value.ui_timeline_states[descriptor.path]["frame"], 2)
        self.assertFalse(value.ui_timeline_states[descriptor.path]["playing"])
        self.assertEqual(
            value.ui_avm2_runtime_properties[descriptor.path]["buttonState"],
            "over",
        )

    def test_manual_movieclip_frame_keeps_visual_precedence(self):
        value = movie()
        owner = value._ui_avm2_runtime_owner
        path = "root/1:btn"
        value.ui_state_overrides[path] = {"sprite_frame": 3}
        value.ui_timeline_states[path] = {"frame": 1, "playing": True, "frame_count": 3}
        descriptor = patch.ButtonDescriptor(path, "btn", 3, button_mode=True)
        old = patch._descriptor
        patch._descriptor = lambda _owner, _path, _region=None: descriptor
        try:
            patch._set_button_state(owner, path, "over")
        finally:
            patch._descriptor = old
        self.assertEqual(value.ui_timeline_states[path]["frame"], 1)
        self.assertEqual(
            value.ui_avm2_runtime_properties[path]["buttonState"],
            "over",
        )

    def test_dynamic_button_uses_its_own_movieclip_frame(self):
        value = movie()
        owner = value._ui_avm2_runtime_owner
        obj = dynamic.DynamicDisplayObject(
            1, "MovieClip", name="btnDynamic",
            path="root/$dyn1:btnDynamic", parent_path="root",
        )
        obj.definition = ui_browser.SpriteDef(7, 3, [])
        state = dynamic._state(value)
        state["objects"][1] = obj
        state["by_path"][obj.path] = 1
        descriptor = patch.ButtonDescriptor(
            obj.path, obj.name, 3, button_mode=True, dynamic=True,
        )
        old = patch._descriptor
        patch._descriptor = lambda _owner, _path, _region=None: descriptor
        try:
            patch._set_button_state(owner, obj.path, "down")
        finally:
            patch._descriptor = old
        self.assertEqual(obj.current_frame, 3)
        self.assertFalse(obj.playing)
        self.assertEqual(obj.extras["buttonState"], "down")

    def test_inspector_decorator_exposes_active_button_state(self):
        value = movie()
        path = "root/1:btn"
        patch._button_state_store(value)["states"][path] = {
            "state": "down", "frame": 3,
        }
        node = inspector.StateNode(
            path, 1, "btn", "MovieClip", True, 7, "", {}, (),
        )
        old = patch._BASE.get("inspect")
        patch._BASE["inspect"] = lambda _movie, _frame, _depth: (node,)
        try:
            result = patch.inspect_movie_state(value, 1)
        finally:
            if old is None:
                patch._BASE.pop("inspect", None)
            else:
                patch._BASE["inspect"] = old
        self.assertEqual(result[0].metadata["button_state"], "down")
        self.assertEqual(result[0].metadata["button_frame"], 3)


if __name__ == "__main__":
    unittest.main()
