import unittest

import ui_browser_graphics_model as base
import ui_browser_graphics_complete_model as complete


class GraphicsCompleteModelTests(unittest.TestCase):
    def test_bitmap_data_pixel_fill_copy_and_clone(self):
        bitmap = complete.PreviewBitmapData(4, 3, True, 0x00000000)
        bitmap.set_pixel(1, 1, 0x80402010, True)
        self.assertEqual(bitmap.get_pixel(1, 1, True), 0x80402010)
        bitmap.fill_rect({"x": 0, "y": 0, "width": 2, "height": 1}, 0xFF112233)
        self.assertEqual(bitmap.get_pixel(0, 0, True), 0xFF112233)
        clone = bitmap.clone()
        target = complete.PreviewBitmapData(4, 3, True, 0)
        self.assertTrue(target.copy_pixels(clone, clone.rect, (0, 0)))
        self.assertEqual(target.get_pixel(1, 1, True), 0x80402010)
        self.assertGreater(bitmap.revision, 0)

    def test_bitmap_data_draw_scroll_flood_and_dispose(self):
        source = complete.PreviewBitmapData(2, 2, True, 0xFFFF0000)
        target = complete.PreviewBitmapData(4, 4, True, 0)
        self.assertTrue(target.draw_bitmap(source, (1, 0, 0, 1, 1, 1), False))
        self.assertEqual(target.get_pixel(1, 1), 0xFF0000)
        target.scroll(1, 0)
        self.assertEqual(target.get_pixel(2, 1), 0xFF0000)
        target.flood_fill(0, 0, 0xFF00FF00)
        self.assertEqual(target.get_pixel(0, 0), 0x00FF00)
        target.dispose()
        with self.assertRaises(ValueError):
            target.get_pixel(0, 0)

    def test_draw_path_supports_all_command_types_and_winding(self):
        state = base.GraphicsState()
        base.begin_fill(state, 0xFFFFFF, 1)
        accepted = complete.draw_path(
            state,
            [1, 2, 3, 4, 5, 6],
            [
                0, 0,
                10, 0,
                15, 0, 20, 5,
                0, 0, 20, 10,
                0, 0, 0, 10,
                0, 10, 5, 15, 10, 10,
            ],
            "nonZero",
        )
        self.assertEqual(accepted, 6)
        self.assertTrue(state.primitives)
        self.assertEqual(
            complete.primitive_metadata(state, state.primitives[-1]).get("winding"),
            "nonZero",
        )

    def test_draw_path_rejects_truncated_data_without_raising(self):
        state = base.GraphicsState()
        accepted = complete.draw_path(state, [1, 2], [0, 0], "evenOdd")
        self.assertEqual(accepted, 1)
        self.assertGreater(state.rejected, 0)

    def test_draw_triangles_tracks_uvt_and_culling(self):
        state = base.GraphicsState()
        base.begin_fill(state, 0xFFFFFF, 1)
        accepted = complete.draw_triangles(
            state,
            [0, 0, 10, 0, 0, 10, 10, 10],
            [0, 1, 2, 1, 3, 2],
            [0, 0, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1],
            "none",
        )
        self.assertEqual(accepted, 2)
        meta = complete.primitive_metadata(state, state.primitives[0])
        self.assertEqual(meta["source"], "drawTriangles")
        self.assertEqual(len(meta["uvt"]), 3)

        culled = base.GraphicsState()
        base.begin_fill(culled, 0xFFFFFF, 1)
        self.assertEqual(
            complete.draw_triangles(culled, [0, 0, 10, 0, 0, 10], None, None, "positive"),
            0,
        )

    def test_bitmap_fill_and_line_paints_are_revision_sensitive(self):
        bitmap = complete.PreviewBitmapData(2, 2, True, 0xFFFFFFFF)
        state = base.GraphicsState()
        self.assertTrue(complete.begin_bitmap_fill(state, bitmap, (1, 0, 0, 1, 0, 0), True, True))
        base.draw_rect(state, 0, 0, 10, 10)
        base.line_style(state, 2, 0, 1)
        self.assertTrue(complete.line_bitmap_style(state, bitmap, None, False, False))
        base.move_to(state, 0, 0)
        base.line_to(state, 10, 10)
        base.seal(state)
        before = complete.state_resource_revision(state)
        bitmap.set_pixel(0, 0, 0xFF000000, True)
        after = complete.state_resource_revision(state)
        self.assertNotEqual(before, after)
        self.assertTrue(complete.has_extended_content(state))


if __name__ == "__main__":
    unittest.main()
