import copy
import unittest
from types import SimpleNamespace

import ui_browser_state_inspector_patch as inspector
import ui_browser_game_state_patch as patch


class UIGameStatePatchTests(unittest.TestCase):
    def test_role_matcher_prefers_semantic_names_and_parent_paths(self):
        self.assertEqual(
            patch.match_text_role("root/2:scoreText", {"variable_name": "scoreText"}),
            "score",
        )
        self.assertEqual(
            patch.match_text_role(
                "root/4:levelTitle/1:text_base",
                {"variable_name": "text", "instance_name": "text_base"},
            ),
            "level_name",
        )
        self.assertEqual(
            patch.match_text_role(
                "root/5:bananaCoins/2:text_stroke",
                {"variable_name": "text"},
            ),
            "banana_coins",
        )
        self.assertIsNone(
            patch.match_text_role("root/1:text_base", {"variable_name": "text"})
        )

    def test_game_state_normalization_and_timer_format(self):
        state = patch.normalize_game_state({
            "profile": "hud_1p",
            "values": {"lives": "9", "timer_seconds": "2:03.5"},
        })
        self.assertTrue(state["enabled"])
        self.assertIn("lives", state["roles"])
        self.assertEqual(state["values"]["lives"], 9)
        self.assertAlmostEqual(state["values"]["timer_seconds"], 123.5)
        self.assertEqual(patch.format_mock_value("timer_seconds", 83.42), "01:23.42")
        self.assertEqual(patch.format_mock_value("progress_percent", 42), "42%")

    def test_text_mock_does_not_override_manual_text(self):
        original = patch._BASE_TEXT_DEFINITION

        def base(definition, path, overrides):
            override = (overrides or {}).get(path, {})
            if "text" not in override:
                return definition
            clone = copy.copy(definition)
            clone.initial_text = str(override["text"])
            clone.html = bool(override.get("html", False))
            return clone

        patch._BASE_TEXT_DEFINITION = base
        try:
            movie = SimpleNamespace(
                ui_game_mock_enabled=True,
                ui_game_mock_roles=("score",),
                ui_game_mock_values={"score": 999},
                _ui_game_mock_render_paths=set(),
            )
            definition = SimpleNamespace(
                variable_name="scoreText",
                initial_text="100",
                html=True,
                _ui_game_state_movie=movie,
            )
            mocked = patch.text_definition_for_path(definition, "root/1:scoreText", {})
            manual = patch.text_definition_for_path(
                definition,
                "root/1:scoreText",
                {"root/1:scoreText": {"text": "777", "html": False}},
            )
            self.assertEqual(mocked.initial_text, "999")
            self.assertFalse(mocked.html)
            self.assertEqual(manual.initial_text, "777")
            self.assertEqual(definition.initial_text, "100")
        finally:
            patch._BASE_TEXT_DEFINITION = original

    def test_inspector_node_is_decorated_with_mock_value(self):
        node = inspector.StateNode(
            "root/1:scoreText", 1, "scoreText", "EditText", True,
            None, "", {"variable_name": "scoreText", "text": "100", "display_text": "100"}, (),
        )
        movie = SimpleNamespace(
            ui_game_mock_enabled=True,
            ui_game_mock_roles=("score",),
            ui_game_mock_values={"score": 321},
        )
        decorated = patch._decorate_mock_nodes(movie, (node,))[0]
        self.assertEqual(decorated.metadata["display_text"], "321")
        self.assertEqual(decorated.metadata["mock_role"], "score")
        self.assertEqual(decorated.metadata["original_text"], "100")

    def test_options_profile_uses_known_root_frame(self):
        movie = SimpleNamespace(frame_count=30, labels={})
        profile = patch.PROFILE_BY_ID["options"]
        self.assertEqual(patch.profile_root_frame(profile, movie, "Options.swf"), 20)
        self.assertTrue(patch.profile_matches_movie(profile, "Options.swf"))
        self.assertFalse(patch.profile_matches_movie(profile, "HUD_TimeAttack.swf"))

    def test_preset_game_state_is_backward_compatible(self):
        original_make = patch._BASE_MAKE_PRESET
        original_normalize = patch._BASE_NORMALIZE_PRESET
        patch._BASE_MAKE_PRESET = lambda owner: {
            "format": "PAKPY_UI_STATE_PRESET", "version": 1,
            "root_frame": 1, "overrides": {}, "playback": {},
        }
        patch._BASE_NORMALIZE_PRESET = lambda data: dict(data)
        try:
            owner = SimpleNamespace(
                _ui_game_mock_enabled=True,
                _ui_active_game_profile_id="hud_1p",
                _ui_game_mock_roles=("lives", "score"),
                _ui_game_mock_values={**patch.DEFAULT_MOCK_VALUES, "lives": 7},
            )
            preset = patch.make_preset(owner)
            self.assertEqual(preset["game_state"]["profile"], "hud_1p")
            self.assertEqual(preset["game_state"]["values"]["lives"], 7)
            old = patch.normalize_preset({"root_frame": 1, "overrides": {}, "playback": {}})
            self.assertFalse(old["game_state"]["enabled"])
        finally:
            patch._BASE_MAKE_PRESET = original_make
            patch._BASE_NORMALIZE_PRESET = original_normalize


if __name__ == "__main__":
    unittest.main()
