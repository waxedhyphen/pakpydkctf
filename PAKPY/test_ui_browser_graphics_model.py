import unittest

import ui_browser_graphics_model as graphics


class GraphicsModelTests(unittest.TestCase):
    def test_filled_rectangle_has_stable_bounds(self):
        state = graphics.GraphicsState()
        graphics.begin_fill(state, 0x336699, 0.5)
        graphics.draw_rect(state, 10, 20, 30, 40)
        self.assertEqual(len(state.primitives), 1)
        self.assertEqual(state.primitives[0].fill.color, 0x336699)
        self.assertEqual(graphics.state_bounds(state), (9.0, 19.0, 41.0, 61.0))

    def test_path_seals_when_style_changes(self):
        state = graphics.GraphicsState()
        graphics.line_style(state, 2, 0xFFFFFF)
        graphics.move_to(state, 0, 0)
        graphics.line_to(state, 20, 0)
        graphics.begin_fill(state, 0xFF0000)
        self.assertEqual(len(state.primitives), 1)
        self.assertIsNotNone(state.primitives[0].line)
        self.assertIsNone(state.primitives[0].fill)

    def test_quadratic_and_cubic_curves_are_flattened(self):
        state = graphics.GraphicsState()
        graphics.begin_fill(state, 0x00FF00)
        graphics.move_to(state, 0, 0)
        graphics.curve_to(state, 50, 100, 100, 0)
        graphics.cubic_curve_to(state, 125, -50, 175, 50, 200, 0)
        graphics.end_fill(state)
        contours = graphics.flatten_primitive(state.primitives[0])
        self.assertEqual(len(contours), 1)
        self.assertGreater(len(contours[0][0]), 10)
        self.assertEqual(contours[0][0][-1], (200.0, 0.0))

    def test_gradient_is_bounded_and_uses_common_length(self):
        state = graphics.GraphicsState()
        graphics.begin_gradient_fill(
            state, "radial",
            list(range(30)), [1.0] * 20, list(range(25)),
            focal=4.0,
        )
        self.assertEqual(state.fill.kind, "focal")
        self.assertEqual(len(state.fill.colors), 15)
        self.assertEqual(len(state.fill.alphas), 15)
        self.assertEqual(len(state.fill.ratios), 15)
        self.assertEqual(state.fill.focal, 0.99)

    def test_round_rect_and_circle_close_their_contours(self):
        state = graphics.GraphicsState()
        graphics.begin_fill(state, 0xFFFFFF)
        graphics.draw_round_rect(state, 0, 0, 100, 40, 10)
        graphics.draw_circle(state, 50, 50, 12)
        self.assertEqual(len(state.primitives), 2)
        for primitive in state.primitives:
            contours = graphics.flatten_primitive(primitive)
            self.assertTrue(contours[0][1])
            self.assertEqual(contours[0][0][0], contours[0][0][-1])

    def test_coordinate_and_command_limits_reject_growth(self):
        state = graphics.GraphicsState(command_count=graphics.MAX_GRAPHICS_COMMANDS)
        graphics.line_to(state, graphics.MAX_GRAPHICS_COORDINATE * 2, 0)
        self.assertEqual(state.rejected, 1)
        self.assertEqual(state.current_commands, [])

    def test_clear_resets_stream_but_advances_revision(self):
        state = graphics.GraphicsState()
        graphics.begin_fill(state, 1)
        graphics.draw_rect(state, 0, 0, 10, 10)
        revision = state.revision
        graphics.clear(state)
        self.assertEqual(state.primitives, [])
        self.assertEqual(state.command_count, 0)
        self.assertGreater(state.revision, revision)


if __name__ == "__main__":
    unittest.main()
