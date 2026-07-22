import unittest

import ui_browser_game_state_patch as game_state
import ui_browser_game_state_corpus_patch as patch


class UIGameStateCorpusPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patch.install()

    def test_shipped_counter_names_are_recognized(self):
        cases = {
            "balloonCounter": "lives",
            "coinCounter": "banana_coins",
            "PuzzleTally": "puzzle_pieces",
            "currentTime": "timer_seconds",
            "text_time": "timer_seconds",
            "KongTally": "kong_letters",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    game_state.match_text_role(f"root/1:{name}", {"instance_name": name}),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
