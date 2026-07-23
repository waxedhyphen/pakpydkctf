from types import SimpleNamespace
import unittest

import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_graphics_order_fix_patch as order_fix


class GraphicsOrderFixTests(unittest.TestCase):
    def test_replaces_state_renderer_unmasked_closure(self):
        calls = []

        def original(*args):
            calls.append(args)
            return "drawn"

        def make_state_draw():
            draw_unmasked = original

            def state_draw(*args):
                return draw_unmasked(*args)

            return state_draw

        previous = dynamic._BASE.get("draw")
        state_draw = make_state_draw()
        dynamic._BASE["draw"] = state_draw
        old_original = order_fix._ORIGINAL_UNMASKED
        old_cell = order_fix._PATCHED_CELL
        try:
            order_fix._ORIGINAL_UNMASKED = None
            order_fix._PATCHED_CELL = None
            self.assertTrue(order_fix._patch_state_draw_cell())
            renderer = SimpleNamespace(_ui_current_path="", movie=SimpleNamespace())
            result = state_draw(renderer, None, {}, None, None, set(), 0)
            self.assertEqual(result, "drawn")
            self.assertEqual(len(calls), 1)
            self.assertIsNotNone(order_fix._PATCHED_CELL)
        finally:
            if order_fix._PATCHED_CELL is not None:
                order_fix._PATCHED_CELL.cell_contents = original
            order_fix._ORIGINAL_UNMASKED = old_original
            order_fix._PATCHED_CELL = old_cell
            if previous is None:
                dynamic._BASE.pop("draw", None)
            else:
                dynamic._BASE["draw"] = previous


if __name__ == "__main__":
    unittest.main()
