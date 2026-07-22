import json
import struct
import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_state_inspector_patch as patch


def _place2(depth, character_id, name=""):
    flags = 0x02 | (0x20 if name else 0)
    payload = bytes([flags]) + struct.pack("<HH", depth, character_id)
    if name:
        payload += name.encode("utf-8") + b"\x00"
    return (ui_browser.TAG_PLACE_OBJECT2, payload)


def _movie(definitions, root_tags, scaling_grids=None):
    return SimpleNamespace(
        definitions=definitions,
        root_tags=root_tags,
        frame_count=1,
        frame_rate=30.0,
        stage_bounds=(0.0, 0.0, 1280.0, 720.0),
        symbol_classes={},
        scaling_grids=scaling_grids or {},
    )


class UIBrowserStateInspectorTests(unittest.TestCase):
    def test_recursive_sprite_and_edit_text_are_exposed(self):
        text = ui_browser.EditTextDef(
            2, (0.0, 0.0, 200.0, 40.0),
            "scoreText", "100", (255, 255, 255, 255), 24.0, False,
        )
        text.font_class = "$NormalFont"
        text.html = True
        sprite = ui_browser.SpriteDef(
            1, 1,
            [_place2(7, 2, "score"), (ui_browser.TAG_SHOW_FRAME, b"")],
            {},
        )
        movie = _movie(
            {1: sprite, 2: text},
            [_place2(3, 1, "hud"), (ui_browser.TAG_SHOW_FRAME, b"")],
        )
        nodes = patch.inspect_movie_state(movie, 1)
        self.assertEqual(nodes[0].label, "hud")
        self.assertEqual(nodes[0].kind, "MovieClip")
        self.assertEqual(nodes[0].children[0].label, "score")
        self.assertEqual(nodes[0].children[0].kind, "EditText")
        self.assertEqual(nodes[0].children[0].metadata["font_class"], "$NormalFont")
        self.assertEqual(nodes[0].children[0].metadata["display_text"], "100")
        self.assertEqual(nodes[0].children[0].path, "root/3:hud/7:score")

    def test_effect_and_scale9_metadata_are_kept(self):
        item = ui_browser.DisplayObject(
            depth=5,
            character_id=9,
            matrix=ui_browser.Affine(2.0, 0.0, 0.0, 1.5, 40.0, 60.0),
            name="panel",
            clip_depth=12,
        )
        item.filters = (SimpleNamespace(filter_id=2, name="Glow", raw=b"\x02" + b"\x00" * 15),)
        item.blend_mode = 3
        item.cache_as_bitmap = 1
        ui_browser.BLEND_NAMES = {3: "Multiply"}
        shape = ui_browser.ShapeDef(9, (0.0, 0.0, 100.0, 50.0))
        movie = _movie(
            {9: shape},
            [],
            {9: SimpleNamespace(rect=(10.0, 10.0, 90.0, 40.0))},
        )
        node = patch.inspect_display_state(movie, {5: item})[0]
        self.assertEqual(node.metadata["blend_mode"]["name"], "Multiply")
        self.assertEqual(node.metadata["filters"][0]["name"], "Glow")
        self.assertEqual(node.metadata["clip_depth"], 12)
        self.assertEqual(node.metadata["scale9_grid"], (10.0, 10.0, 90.0, 40.0))
        self.assertEqual(node.metadata["matrix"]["tx"], 40.0)

    def test_recursive_reference_is_stopped_and_marked(self):
        sprite = ui_browser.SpriteDef(
            1, 1,
            [_place2(1, 1, "self"), (ui_browser.TAG_SHOW_FRAME, b"")],
            {},
        )
        movie = _movie(
            {1: sprite},
            [_place2(1, 1, "rootSprite"), (ui_browser.TAG_SHOW_FRAME, b"")],
        )
        node = patch.inspect_movie_state(movie, 1)[0]
        self.assertEqual(len(node.children), 1)
        self.assertTrue(node.children[0].metadata["cycle"])
        self.assertEqual(node.children[0].children, ())

    def test_search_keeps_matching_ancestors_and_snapshot_is_json(self):
        child = patch.StateNode(
            "root/1:parent/2:score", 2, "score", "EditText", True,
            2, "", {"display_text": "999"}, (),
        )
        parent = patch.StateNode(
            "root/1:parent", 1, "parent", "MovieClip", True,
            1, "", {}, (child,),
        )
        filtered = patch.filter_state_nodes((parent,), "999")
        self.assertEqual(filtered[0].children[0].label, "score")
        movie = _movie({}, [])
        snapshot = patch.state_snapshot(movie, 1, filtered)
        json.dumps(snapshot)
        self.assertEqual(snapshot["nodes"][0]["children"][0]["metadata"]["display_text"], "999")


if __name__ == "__main__":
    unittest.main()
