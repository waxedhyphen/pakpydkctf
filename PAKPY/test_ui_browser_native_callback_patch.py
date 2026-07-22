import json
import unittest
from types import SimpleNamespace

import ui_browser_avm2_patch as avm2
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_native_callback_catalog as catalog
import ui_browser_native_callback_patch as patch


def make_movie():
    return SimpleNamespace(
        avm2_modules=(),
        ui_avm2_runtime_generation=0,
        ui_avm2_runtime_revision=0,
        ui_avm2_runtime_log=[],
        ui_avm2_runtime_errors=[],
        ui_avm2_native_data={},
        ui_game_mock_enabled=True,
        ui_game_mock_roles=("lives", "banana_coins"),
        ui_game_mock_values={"lives": 5, "banana_coins": 23},
    )


class Context:
    def __init__(self, movie):
        self.movie = movie
        self.path = "root/1:test"
        self.callbacks = 0


def base_native(result=runtime._UNDEFINED):
    def call(context, name, args):
        context.callbacks += 1
        runtime._log(context.movie, "callback", name=name, status="base", result=repr(result), path=context.path)
        return result
    return call


class NativeCallbackPatchTests(unittest.TestCase):
    def setUp(self):
        patch._BASE["native"] = base_native()

    def test_catalog_classifies_critical_callback_groups(self):
        self.assertEqual(catalog.callback_spec("GetDataValue").category, "data-read")
        self.assertEqual(catalog.callback_spec("playSound").category, "audio")
        self.assertEqual(catalog.callback_spec("PrepareForTransition").category, "navigation")
        self.assertEqual(catalog.callback_spec("newSaveGame").category, "save/profile")
        self.assertEqual(catalog.callback_spec("GetExtrasUnlockState").category, "extras")
        self.assertEqual(catalog.callback_spec("FillLeaderBoard").category, "leaderboard")

    def test_extracts_external_interface_and_controller_sites(self):
        abc = SimpleNamespace(methods=(object(),), instances=(), classes=(), scripts=())
        abc.method_name = lambda index: "frame1"
        module = SimpleNamespace(abc=abc, name="test", source="root")
        instruction_a = SimpleNamespace(offset=10)
        instruction_b = SimpleNamespace(offset=20)
        old = avm2._simulate_calls
        avm2._simulate_calls = lambda *_args: (
            ("call", (("literal", "playSound"), ("literal", "UI_Menu_OK")), ("lex", "ExternalInterface"), instruction_a),
            ("GetDataValue", (("literal", "source"), ("literal", "mRuntimeData"), ("literal", "Count_Balloons")), ("lex", "Controller"), instruction_b),
        )
        try:
            sites = patch.extract_callback_sites(module)
        finally:
            avm2._simulate_calls = old
        self.assertEqual([site.callback for site in sites], ["playSound", "GetDataValue"])
        self.assertEqual(sites[0].arguments, ("UI_Menu_OK",))
        self.assertEqual(sites[1].bridge, "Controller")

    def test_registered_base_result_has_priority_over_built_in(self):
        movie = make_movie()
        context = Context(movie)
        patch._BASE["native"] = base_native(77)
        result = patch.native_call(context, "GetExtrasUnlockState", ())
        self.assertEqual(result, 77)
        self.assertEqual(patch._callback_state(movie)["calls"][-1]["source"], "Basis/Registry")

    def test_explicit_return_override_has_highest_priority(self):
        movie = make_movie()
        movie.ui_native_callback_overrides = {"GetExtrasUnlockState": False}
        context = Context(movie)
        result = patch.native_call(context, "GetExtrasUnlockState", ())
        self.assertFalse(result)
        self.assertEqual(patch._callback_state(movie)["calls"][-1]["source"], "Native-Override")

    def test_data_dictionary_init_listen_and_export_are_preview_only(self):
        movie = make_movie()
        context = Context(movie)
        self.assertTrue(patch.native_call(context, "FillDataDictionary", ("mRuntimeData", "mSaveData")))
        self.assertEqual(patch.native_call(context, "InitDataValue", ("mRuntimeData", "allowInput", True)), True)
        self.assertTrue(patch.native_call(context, "ListenForData", ("Count_Balloons", "handler")))
        state = patch._callback_state(movie)
        self.assertIn("mRuntimeData", state["dictionaries"])
        self.assertEqual(movie.ui_avm2_native_data[("mRuntimeData", "allowInput")], True)
        self.assertEqual(state["subscriptions"]["Count_Balloons"], ["handler"])

    def test_audio_and_telemetry_are_queued_without_host_side_effects(self):
        movie = make_movie()
        context = Context(movie)
        self.assertTrue(patch.native_call(context, "playSound", (None, "UI_Menu_Button_Enter", False)))
        self.assertIs(patch.native_call(context, "LogEvent", ("menu-open",)), runtime._UNDEFINED)
        state = patch._callback_state(movie)
        self.assertEqual(state["audio_requests"][0]["sound"], "UI_Menu_Button_Enter")
        self.assertEqual(state["telemetry"][0]["arguments"], ["menu-open"])

    def test_save_controller_and_transition_handlers_keep_isolated_state(self):
        movie = make_movie()
        context = Context(movie)
        self.assertTrue(patch.native_call(context, "newSaveGame", (1, True)))
        self.assertTrue(patch.native_call(context, "setPlayer1ControllerMode", (2,)))
        self.assertTrue(patch.native_call(context, "PrepareForTransition", ()))
        self.assertTrue(patch.native_call(context, "TransitionState", ("Trans_Test", 2)))
        state = patch._callback_state(movie)
        self.assertTrue(state["save"]["slots"][1]["funky_mode"])
        self.assertEqual(state["controller"]["player1_mode"], 2)
        self.assertTrue(state["transition"]["prepared"])
        self.assertEqual(state["transition"]["states"]["Trans_Test"], 2)

    def test_observe_mode_does_not_apply_new_simulation(self):
        movie = make_movie()
        movie.ui_native_callback_mode = "observe"
        context = Context(movie)
        result = patch.native_call(context, "GetExtrasUnlockState", ())
        self.assertIs(result, runtime._UNDEFINED)
        self.assertEqual(patch._callback_state(movie)["calls"][-1]["source"], "Nur beobachtet")

    def test_unknown_query_uses_deterministic_false_default(self):
        movie = make_movie()
        context = Context(movie)
        self.assertFalse(patch.native_call(context, "CanDoUnknownThing", ()))
        self.assertEqual(len(patch._callback_state(movie)["unknown"]), 1)

    def test_config_and_preset_payload_are_json_safe(self):
        clean = patch.normalize_native_callback_config({
            "mode": "bad", "overrides": {"A": {"x": [1, True, None]}},
        })
        self.assertEqual(clean["mode"], "simulate")
        self.assertEqual(clean["overrides"]["A"]["x"], [1, True, None])
        json.dumps(clean)

    def test_f_data_aliases_share_preview_data_store(self):
        movie = make_movie()
        context = Context(movie)
        self.assertEqual(
            patch.native_call(context, "fSetDataValue", ("debug", "mSaveData", "Count_Coins", 99)),
            99,
        )
        self.assertEqual(
            patch.native_call(context, "fGetDataValue", ("debug", "mSaveData", "Count_Coins")),
            99,
        )

    def test_controller_event_dispatcher_calls_are_not_host_callbacks(self):
        found = patch._callback_from_call(
            "addEventListener", (("literal", "CHANGE"), ("local", 1)),
            ("property", ("lex", "Controller"), "mEventDispatcher"),
        )
        self.assertIsNone(found)

    def test_inventory_snapshot_is_json_serializable(self):
        movie = make_movie()
        movie.ui_native_callback_sites = ()
        movie.ui_native_callback_summaries = ()
        movie._ui_native_callback_inventory_token = ()
        data = patch.native_callback_inventory(movie)
        self.assertEqual(data["schema"], 1)
        json.dumps(data)


if __name__ == "__main__":
    unittest.main()
