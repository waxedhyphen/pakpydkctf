import json
import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_state_inspector_patch as inspector
import ui_browser_timeline_playback_patch as patch


class UITimelinePlaybackTests(unittest.TestCase):
    def test_instance_normalization_and_looping(self):
        state = patch.normalize_timeline_instance(
            {"frame": 9, "playing": True},
            frame_count=3,
        )
        self.assertEqual(state["frame"], 3)
        self.assertEqual(patch.advance_timeline_instance(state, 1), 1)
        state["playing"] = False
        self.assertEqual(patch.advance_timeline_instance(state, 2), 1)

    def test_manual_frame_override_precedes_playback_frame(self):
        definition = ui_browser.SpriteDef(7, 5, [], {})
        movie = SimpleNamespace(
            definitions={7: definition},
            ui_timeline_states={"root/2:clip": {"frame": 4, "playing": True, "frame_count": 5}},
        )
        patch.register_movie(movie, movie.ui_timeline_states)
        self.assertEqual(
            patch.timeline_frame_for_path(definition, "root/2:clip", {}),
            4,
        )
        self.assertEqual(
            patch.timeline_frame_for_path(
                definition,
                "root/2:clip",
                {"root/2:clip": {"sprite_frame": 2}},
            ),
            2,
        )

    def test_playback_preset_is_json_safe(self):
        playback = patch.normalize_playback_preset({
            "speed": "2",
            "playing": 1,
            "instances": {
                "root/1:menu": {"frame": "12", "playing": 0},
                "root/2:bad": "ignored",
            },
        })
        json.dumps(playback)
        self.assertEqual(playback["speed"], 2.0)
        self.assertTrue(playback["playing"])
        self.assertEqual(playback["instances"]["root/1:menu"]["frame"], 12)
        self.assertFalse(playback["instances"]["root/1:menu"]["playing"])
        self.assertNotIn("root/2:bad", playback["instances"])

    def test_decorated_inspector_node_marks_timeline_source(self):
        node = inspector.StateNode(
            "root/1:clip", 1, "clip", "MovieClip", True,
            7, "", {"sprite_frame": 3}, (),
        )
        movie = SimpleNamespace(
            ui_timeline_states={
                "root/1:clip": {"frame": 3, "playing": False, "frame_count": 5},
            },
        )
        decorated = patch._decorate_nodes(movie, (node,), {})[0]
        self.assertEqual(decorated.metadata["timeline_frame"], 3)
        self.assertFalse(decorated.metadata["timeline_playing"])
        self.assertFalse(decorated.metadata["timeline_manual_frame"])

        manual = patch._decorate_nodes(
            movie,
            (node,),
            {"root/1:clip": {"sprite_frame": 2}},
        )[0]
        self.assertTrue(manual.metadata["timeline_manual_frame"])


if __name__ == "__main__":
    unittest.main()
