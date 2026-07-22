import json
import struct
import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_state_override_patch as patch


def _place2(depth, character_id, name=""):
    flags = 0x02 | (0x20 if name else 0)
    payload = bytes([flags]) + struct.pack("<HH", depth, character_id)
    if name:
        payload += name.encode("utf-8") + b"\x00"
    return (ui_browser.TAG_PLACE_OBJECT2, payload)


def _remove2(depth):
    return (ui_browser.TAG_REMOVE_OBJECT2, struct.pack("<H", depth))


def _movie(definitions, root_tags, frame_count=1):
    return SimpleNamespace(
        definitions=definitions,
        root_tags=root_tags,
        frame_count=frame_count,
        frame_rate=30.0,
        stage_bounds=(0.0, 0.0, 1280.0, 720.0),
        symbol_classes={},
        scaling_grids={},
    )


class UIStateOverrideTests(unittest.TestCase):
    def test_visibility_filters_and_blend_are_applied_to_copy(self):
        item = ui_browser.DisplayObject(depth=5, character_id=9, name="panel")
        item.filters = (SimpleNamespace(filter_id=2, name="Glow", raw=b"\x02"),)
        item.blend_mode = 3
        movie = _movie({9: ui_browser.ShapeDef(9, (0, 0, 20, 20))}, [])
        path = "root/5:panel"
        clone, actual_path, override = patch.apply_item_override(
            movie,
            "root",
            5,
            item,
            {path: {"visible": False, "disable_filters": True, "disable_blend": True}},
        )
        self.assertEqual(actual_path, path)
        self.assertIsNot(clone, item)
        self.assertFalse(clone.visible)
        self.assertEqual(clone.filters, ())
        self.assertEqual(clone.blend_mode, 0)
        self.assertTrue(item.visible)
        self.assertEqual(item.blend_mode, 3)
        self.assertTrue(override["disable_filters"])

    def test_nested_movieclip_frame_override_changes_inspected_children(self):
        shape_a = ui_browser.ShapeDef(2, (0, 0, 10, 10))
        shape_b = ui_browser.ShapeDef(3, (0, 0, 10, 10))
        sprite = ui_browser.SpriteDef(
            1,
            2,
            [
                _place2(1, 2, "first"),
                (ui_browser.TAG_SHOW_FRAME, b""),
                _remove2(1),
                _place2(1, 3, "second"),
                (ui_browser.TAG_SHOW_FRAME, b""),
            ],
            {},
        )
        movie = _movie(
            {1: sprite, 2: shape_a, 3: shape_b},
            [_place2(1, 1, "clip"), (ui_browser.TAG_SHOW_FRAME, b"")],
        )
        nodes = patch.inspect_movie_state_with_overrides(
            movie,
            1,
            {"root/1:clip": {"sprite_frame": 2}},
        )
        self.assertEqual(nodes[0].metadata["sprite_frame"], 2)
        self.assertEqual(nodes[0].children[0].label, "second")
        self.assertEqual(nodes[0].children[0].character_id, 3)

    def test_text_override_is_exposed_in_state_tree(self):
        text = ui_browser.EditTextDef(
            4,
            (0.0, 0.0, 200.0, 50.0),
            "scoreText",
            "100",
            (255, 255, 255, 255),
            24.0,
            False,
        )
        text.font_class = "$NormalFont"
        text.html = True
        movie = _movie(
            {4: text},
            [_place2(2, 4, "score"), (ui_browser.TAG_SHOW_FRAME, b"")],
        )
        nodes = patch.inspect_movie_state_with_overrides(
            movie,
            1,
            {"root/2:score": {"text": "999", "html": False}},
        )
        node = nodes[0]
        self.assertEqual(node.metadata["display_text"], "999")
        self.assertEqual(node.metadata["original_text"], "100")
        self.assertFalse(node.metadata["html"])
        self.assertEqual(text.initial_text, "100")

    def test_preset_normalization_is_json_safe(self):
        preset = patch.normalize_preset({
            "format": patch.PRESET_FORMAT,
            "version": 1,
            "pak": "UIPak.pak",
            "movie": "Options.swf",
            "root_frame": "7",
            "overrides": {
                "root/1:menu": {
                    "visible": 0,
                    "sprite_frame": "3",
                    "text": 123,
                    "html": 1,
                    "disable_filters": 1,
                    "ignored": "value",
                },
                "root/2:empty": {},
            },
        })
        json.dumps(preset)
        self.assertEqual(preset["root_frame"], 7)
        item = preset["overrides"]["root/1:menu"]
        self.assertFalse(item["visible"])
        self.assertEqual(item["sprite_frame"], 3)
        self.assertEqual(item["text"], "123")
        self.assertTrue(item["html"])
        self.assertNotIn("ignored", item)
        self.assertNotIn("root/2:empty", preset["overrides"])


if __name__ == "__main__":
    unittest.main()
