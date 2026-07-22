import unittest
from types import SimpleNamespace

import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_button_navigation_patch as button
import ui_browser_button_owner_fix_patch as patch
import ui_browser_state_inspector_patch as inspector


class Owner:
    def __init__(self, movie):
        self._current_movie = movie
        self.frame_var = SimpleNamespace(get=lambda: 1)


class ButtonOwnerFixTests(unittest.TestCase):
    def setUp(self):
        self.movie = SimpleNamespace(
            ui_avm2_runtime_generation=0,
            ui_avm2_runtime_properties={},
            ui_avm2_dynamic_state=None,
            ui_input_hit_regions=[],
        )
        self.owner = Owner(self.movie)

    def test_child_shape_routes_to_named_button_movieclip(self):
        parent = inspector.StateNode(
            "root/1:btnPlay", 1, "btnPlay", "MovieClip", True, 7, "",
            {"sprite_frame_count": 3, "sprite_labels": {"up": 1, "over": 2, "down": 3}},
            (),
        )
        child = inspector.StateNode(
            "root/1:btnPlay/1:background", 1, "background", "Shape", True, 8, "", {}, (),
        )
        parent = inspector.StateNode(
            parent.path, parent.depth, parent.label, parent.kind, parent.visible,
            parent.character_id, parent.class_name, parent.metadata, (child,),
        )
        old = button._node_index
        button._node_index = lambda _owner, _movie: {
            parent.path: parent,
            child.path: child,
        }
        try:
            self.assertEqual(
                patch.resolve_button_owner(self.owner, child.path),
                parent.path,
            )
        finally:
            button._node_index = old

    def test_weak_control_owner_is_used_only_when_no_strong_button_exists(self):
        control = inspector.StateNode(
            "root/1:options_control", 1, "options_control", "MovieClip",
            True, 7, "", {"sprite_frame_count": 2}, (),
        )
        child = inspector.StateNode(
            "root/1:options_control/2:label", 2, "label", "EditText",
            True, 8, "", {}, (),
        )
        old = button._node_index
        button._node_index = lambda _owner, _movie: {
            control.path: control,
            child.path: child,
        }
        try:
            self.assertEqual(
                patch.resolve_button_owner(self.owner, child.path),
                control.path,
            )
        finally:
            button._node_index = old

    def test_candidate_regions_deduplicate_children_of_same_button(self):
        parent_path = "root/1:btnPlay"
        left = dynamic.HitRegion(parent_path + "/1:left", (0, 0, 10, 10), "left")
        right = dynamic.HitRegion(parent_path + "/2:right", (10, 0, 20, 10), "right")
        self.movie.ui_input_hit_regions = [left, right]
        descriptor = button.ButtonDescriptor(
            parent_path, "btnPlay", 3,
            (("up", 1), ("over", 2), ("down", 3)),
        )
        old = patch.descriptor
        patch.descriptor = lambda _owner, _path, region=None: descriptor
        try:
            values = patch.candidate_regions(self.owner)
        finally:
            patch.descriptor = old
        self.assertEqual(len(values), 1)
        self.assertEqual(values[0].path, parent_path)


if __name__ == "__main__":
    unittest.main()
