import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_avm2_patch as avm2
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_runtime_corpus_patch as patch
import ui_browser_avm2_runtime_corpus_fix_patch as fix_patch


class DummyABC:
    def __init__(self):
        self.names = {1: "Event", 2: "visible"}
        self.strings = ("", "value")
        self.ints = (0,)
        self.uints = (0,)
        self.doubles = (float("nan"),)

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


def movie():
    return SimpleNamespace(
        definitions={}, root_tags=[], frame_count=10, labels={}, symbol_classes={},
        ui_state_overrides={}, ui_timeline_states={},
        ui_avm2_runtime_enabled=True, ui_avm2_runtime_properties={},
        ui_avm2_runtime_log=[], ui_avm2_runtime_errors=[], ui_avm2_runtime_revision=0,
    )


def context(value):
    return runtime.RuntimeContext(
        movie=value, abc=DummyABC(), class_name="pkg.Doc", path="root",
        definition=None, frame=1, playing=True, frame_count=10, labels={},
        trait_methods={}, slot_names={},
    )


class UIAVM2RuntimeCorpusPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch.install()
        fix_patch.install()

    def test_frozen_instruction_translation_handles_cast_and_constructor(self):
        value = movie()
        ctx = context(value)
        instructions = (
            avm2.AVM2Instruction(0, 0x2C, "pushstring", (1,), 2),
            avm2.AVM2Instruction(2, 0x60, "getlex", (1,), 2),
            avm2.AVM2Instruction(4, 0x87, "astypelate", (), 1),
            avm2.AVM2Instruction(5, 0x5D, "findpropstrict", (1,), 2),
            avm2.AVM2Instruction(7, 0x4A, "constructprop", (1, 0), 3),
            avm2.AVM2Instruction(10, 0x29, "pop", (), 1),
            avm2.AVM2Instruction(11, 0x48, "returnvalue", (), 1),
        )
        self.assertEqual(patch.execute_instructions(ctx, instructions), "value")
        self.assertEqual(value.ui_avm2_runtime_errors, [])

    def test_generic_data_value_callbacks_bridge_game_mocks_and_runtime_data(self):
        value = movie()
        value.ui_game_mock_enabled = True
        value.ui_game_mock_roles = ("lives",)
        value.ui_game_mock_values = {"lives": 12}
        ctx = context(value)
        self.assertEqual(
            patch.native_call(ctx, "GetDataValue", ("source", "mSaveData", "Count_Balloons")),
            12,
        )
        patch.native_call(ctx, "SetDataValue", ("source", "mRuntimeData", "allowInput", True))
        self.assertTrue(
            patch.native_call(ctx, "GetDataValue", ("source", "mRuntimeData", "allowInput"))
        )

    def test_noncurrent_movieclip_timeline_call_updates_its_own_state(self):
        value = movie()
        clip = ui_browser.SpriteDef(7, 5, [], {"highlighted": 4})
        reference = runtime.RuntimeRef("root/2:button", definition=clip, frame=1)
        ctx = context(value)
        self.assertTrue(patch._child_timeline_call(ctx, reference, "gotoAndStop", ("highlighted",)))
        self.assertEqual(ctx.frame, 1)
        self.assertTrue(ctx.playing)
        self.assertEqual(value.ui_timeline_states[reference.path]["frame"], 4)
        self.assertFalse(value.ui_timeline_states[reference.path]["playing"])

    def test_script_local_properties_are_retained_for_later_conditions(self):
        value = movie()
        ctx = context(value)
        reference = runtime.RuntimeRef("root")
        self.assertTrue(patch.set_property(ctx, reference, "dialogIsOff", False))
        self.assertFalse(patch.get_property(ctx, reference, "dialogIsOff"))


if __name__ == "__main__":
    unittest.main()
