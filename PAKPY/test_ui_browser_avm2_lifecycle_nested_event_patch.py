import unittest
from types import SimpleNamespace

import ui_browser_avm2_lifecycle_nested_event_patch as patch


class NestedEventTests(unittest.TestCase):
    def test_nested_handler_commits_frame_and_playing_state(self):
        movie = SimpleNamespace(ui_timeline_states={"root/1:clip": {"frame": 1, "playing": True}})
        listener = SimpleNamespace(path="root/1:clip")
        context = SimpleNamespace(frame=4, playing=False, frame_count=6)
        old = patch._BASE_INVOKE
        patch._BASE_INVOKE = lambda movie, listener, event, arguments=None: context
        try:
            self.assertIs(patch.invoke(movie, listener, None), context)
        finally:
            patch._BASE_INVOKE = old
        state = movie.ui_timeline_states[listener.path]
        self.assertEqual(state["frame"], 4)
        self.assertFalse(state["playing"])


if __name__ == "__main__":
    unittest.main()
