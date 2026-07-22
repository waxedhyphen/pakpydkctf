import unittest

from PIL import Image

import ui_browser
import ui_browser_classic_button as classic
import scan_ui_classic_buttons as scanner


def button1_payload():
    # Button 3: one character at depth 1 in Up and HitTest, followed by Stop.
    return (
        (3).to_bytes(2, "little")
        + bytes([0x09])
        + (10).to_bytes(2, "little")
        + (1).to_bytes(2, "little")
        + b"\x00"  # identity MATRIX
        + b"\x00"  # end of records
        + b"\x07\x00"  # Stop, End
    )


def button2_payload():
    record = (
        bytes([0x0F])
        + (11).to_bytes(2, "little")
        + (2).to_bytes(2, "little")
        + b"\x00"  # identity MATRIX
        + b"\x00"  # identity CXFORMWITHALPHA
        + b"\x00"  # end of records
    )
    condition = (
        (0).to_bytes(2, "little")  # final condition block
        + (0x0800).to_bytes(2, "little")  # OverDown -> OverUp
        + b"\x06\x00"  # Play, End
    )
    # ActionOffset is measured from the beginning of the ActionOffset field.
    return (
        (4).to_bytes(2, "little")
        + b"\x01"
        + (len(record) + 2).to_bytes(2, "little")
        + record
        + condition
    )


class ClassicButtonModelTests(unittest.TestCase):
    def test_parses_define_button_and_exposes_four_state_timeline(self):
        definition = classic.parse_classic_button(button1_payload(), 1)
        self.assertIsInstance(definition, ui_browser.SpriteDef)
        self.assertEqual(definition.records[0].states, ("up", "hit"))
        self.assertEqual(definition.button_actions[0].actions[0].name, "Stop")
        self.assertEqual(ui_browser.build_display_list(definition.tags, 1)[1].character_id, 10)
        self.assertEqual(ui_browser.build_display_list(definition.tags, 2), {})
        self.assertEqual(ui_browser.build_display_list(definition.tags, 4)[1].character_id, 10)

    def test_parses_define_button2_conditions_and_action_offset(self):
        definition = classic.parse_classic_button(button2_payload(), 2)
        self.assertTrue(definition.track_as_menu)
        self.assertIn("over_down_to_over_up", definition.button_actions[0].conditions)
        self.assertEqual(definition.button_actions[0].actions[0].name, "Play")

    def test_avm1_inventory_marks_only_timeline_actions_safe(self):
        actions, _ = classic.parse_avm1_actions(
            b"\x81\x02\x00\x04\x00"  # GotoFrame 4 (zero based)
            b"\x83\x0b\x00https://x\x00\x00"  # GetURL
            b"\x00"
        )
        self.assertEqual(actions[0].argument, 5)
        self.assertTrue(actions[0].safe)
        self.assertEqual(actions[1].name, "GetURL")
        self.assertFalse(actions[1].safe)

    def test_alpha_geometry_and_clip_both_have_to_match(self):
        alpha = Image.new("L", (4, 4), 0)
        alpha.putpixel((1, 1), 255)
        clip = classic.HitGeometry(
            "clip", "rect", (1, 1, 3, 3),
            (1, 0, 0, 0, 1, 0), (1, 1, 3, 3),
        )
        hit = classic.HitGeometry(
            "button", "vector", (0, 0, 4, 4),
            (1, 0, 0, 0, 1, 0), (0, 0, 4, 4),
            alpha, (0, 0), (classic.HitClip((clip,), "clipDepth"),),
        )
        self.assertTrue(hit.contains((1.5, 1.5)))
        self.assertFalse(hit.contains((2.5, 2.5)))
        self.assertFalse(hit.contains((0.5, 0.5)))

    def test_rect_normalization_is_bounded_and_deterministic(self):
        self.assertEqual(
            classic.normalize_rect({"x": 2, "y": 3, "width": 4, "height": 5}),
            (2.0, 3.0, 6.0, 8.0),
        )
        self.assertEqual(classic.normalize_rect((2, 3, -4, -5)), (2.0, 3.0, 2.0, 3.0))

    def test_recursive_button_bounds_do_not_loop(self):
        definition = classic.ClassicButtonDef(20, 1, (), ())
        record = classic.ButtonRecord(
            20, 1, ui_browser.Affine(), ui_browser.IDENTITY_COLOR,
            ("hit",), b"\x00",
        )
        definition.records = (record,)
        movie = type("Movie", (), {"definitions": {20: definition}})()
        self.assertIsNone(classic.definition_local_bounds(movie, definition))

    def test_scanner_reads_place_object2_clip_depth(self):
        payload = bytes([0x44]) + (2).to_bytes(2, "little") + b"\x00" + (9).to_bytes(2, "little")
        self.assertEqual(scanner._clip_depth(scanner.TAG_PLACE_OBJECT2, payload), 9)

    def test_scanner_reads_place_object3_clip_depth(self):
        payload = bytes([0x44, 0x00]) + (2).to_bytes(2, "little") + b"\x00" + (9).to_bytes(2, "little")
        self.assertEqual(scanner._clip_depth(scanner.TAG_PLACE_OBJECT3, payload), 9)


if __name__ == "__main__":
    unittest.main()
