import copy
import struct
import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_state_override_patch as override_patch
import ui_browser_avm2_runtime_patch as patch


class DummyABC:
    def __init__(self):
        self.names = {
            1: "scoreText", 2: "visible", 3: "alpha",
            4: "ExternalInterface", 5: "call", 6: "gotoAndStop",
        }
        self.strings = ("", "getLives")
        self.ints = (0,)
        self.uints = (0,)
        self.doubles = (float("nan"), 0.5)

    def multiname_name(self, index):
        return self.names.get(index, f"name{index}")

    def namespace_name(self, index):
        return ""

    def string(self, index):
        return self.strings[index] if 0 <= index < len(self.strings) else ""

    def method_name(self, index):
        return f"method{index}"

    def method_body(self, index):
        return SimpleNamespace(local_count=1)


def ins(offset, name, operands=(), size=1, opcode=0):
    return SimpleNamespace(offset=offset, name=name, operands=tuple(operands), size=size, opcode=opcode)


def place2(depth, character_id, name):
    flags = 0x02 | 0x20
    return (
        ui_browser.TAG_PLACE_OBJECT2,
        bytes([flags]) + struct.pack("<HH", depth, character_id) + name.encode("utf-8") + b"\0",
    )


def execution(movie, frame=1, playing=True):
    return patch.RuntimeContext(
        movie=movie, abc=DummyABC(), class_name="pkg.Doc",
        path="root", definition=None, frame=frame, playing=playing,
        frame_count=10, labels={"highlighted": 7}, trait_methods={}, slot_names={},
    )


class UIAVM2RuntimePatchTests(unittest.TestCase):
    def make_movie(self):
        shape = ui_browser.ShapeDef(1, (0.0, 0.0, 10.0, 10.0))
        return SimpleNamespace(
            definitions={1: shape},
            root_tags=[place2(1, 1, "scoreText"), (ui_browser.TAG_SHOW_FRAME, b"")],
            frame_count=1, labels={}, symbol_classes={},
            ui_state_overrides={}, ui_timeline_states={},
            ui_avm2_runtime_enabled=True, ui_avm2_runtime_properties={},
            ui_avm2_runtime_log=[], ui_avm2_runtime_errors=[],
            ui_avm2_runtime_revision=0,
        )

    def test_existing_child_visibility_and_alpha_are_written(self):
        movie = self.make_movie()
        runtime = execution(movie)
        instructions = (
            ins(0, "getlocal_0"),
            ins(1, "getproperty", (1,), 2),
            ins(3, "pushfalse"),
            ins(4, "setproperty", (2,), 2),
            ins(6, "getlocal_0"),
            ins(7, "getproperty", (1,), 2),
            ins(9, "pushdouble", (1,), 2),
            ins(11, "setproperty", (3,), 2),
            ins(13, "returnvoid"),
        )
        patch.execute_instructions(runtime, instructions)
        values = movie.ui_avm2_runtime_properties["root/1:scoreText"]
        self.assertFalse(values["visible"])
        self.assertEqual(values["alpha"], 0.5)
        self.assertEqual(runtime.writes, 2)

    def test_simple_branch_skips_property_write(self):
        movie = self.make_movie()
        runtime = execution(movie)
        instructions = (
            ins(0, "pushfalse"),
            ins(1, "iffalse", (4,), 4),
            ins(5, "getlocal_0"),
            ins(6, "pushfalse"),
            ins(7, "setproperty", (2,), 2),
            ins(9, "returnvoid"),
        )
        patch.execute_instructions(runtime, instructions)
        self.assertEqual(movie.ui_avm2_runtime_properties, {})

    def test_external_interface_reads_enabled_game_mock(self):
        movie = self.make_movie()
        movie.ui_game_mock_enabled = True
        movie.ui_game_mock_roles = ("lives",)
        movie.ui_game_mock_values = {"lives": 9}
        runtime = execution(movie)
        instructions = (
            ins(0, "getlex", (4,), 2),
            ins(2, "pushstring", (1,), 2),
            ins(4, "callproperty", (5, 1), 3),
            ins(7, "returnvalue"),
        )
        result = patch.execute_instructions(runtime, instructions)
        self.assertEqual(result, 9)
        self.assertEqual(runtime.callbacks, 1)
        self.assertEqual(movie.ui_avm2_runtime_log[-1]["status"], "Game-Mock:lives")

    def test_timeline_call_changes_frame_and_playing_state(self):
        movie = self.make_movie()
        runtime = execution(movie, frame=1, playing=True)
        instructions = (
            ins(0, "getlocal_0"),
            ins(1, "pushbyte", (3,), 2),
            ins(3, "callpropvoid", (6, 1), 3),
            ins(6, "returnvoid"),
        )
        patch.execute_instructions(runtime, instructions)
        self.assertEqual(runtime.frame, 3)
        self.assertFalse(runtime.playing)
        self.assertTrue(runtime.jumped)

    def test_manual_overrides_retain_precedence_over_runtime(self):
        movie = self.make_movie()
        movie.ui_avm2_runtime_properties["root/1:scoreText"] = {
            "visible": False, "text": "runtime",
        }
        display = ui_browser.build_display_list(movie.root_tags, 1)
        old_apply = patch._BASE_APPLY_ITEM
        old_text = patch._BASE_TEXT_DEF
        patch._BASE_APPLY_ITEM = override_patch.apply_item_override

        def base_text(definition, path, overrides):
            raw = (overrides or {}).get(path, {})
            if "text" not in raw:
                return definition
            clone = copy.copy(definition)
            clone.initial_text = raw["text"]
            return clone

        patch._BASE_TEXT_DEF = base_text
        try:
            item, _path, _manual = patch.apply_item_override(
                movie, "root", 1, display[1],
                {"root/1:scoreText": {"visible": True}},
            )
            self.assertTrue(item.visible)
            definition = SimpleNamespace(initial_text="original", html=False, _ui_game_state_movie=movie)
            rendered = patch.text_definition_for_path(
                definition, "root/1:scoreText",
                {"root/1:scoreText": {"text": "manual", "html": False}},
            )
            self.assertEqual(rendered.initial_text, "manual")
        finally:
            patch._BASE_APPLY_ITEM = old_apply
            patch._BASE_TEXT_DEF = old_text


if __name__ == "__main__":
    unittest.main()
