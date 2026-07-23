from types import SimpleNamespace
import unittest

import ui_browser
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_graphics_complete_model as complete
import ui_browser_avm2_graphics_complete_patch as patch


class AVM2GraphicsCompletePatchTests(unittest.TestCase):
    def _context(self):
        movie = SimpleNamespace(ui_avm2_runtime_generation=1)
        return SimpleNamespace(movie=movie, path="root", writes=0)

    def test_static_timeline_proxy_accepts_draw_path(self):
        context = self._context()
        definition = ui_browser.ShapeDef(7, (0.0, 0.0, 20.0, 20.0))
        reference = runtime.RuntimeRef("root/1:shape", definition=definition)
        proxy = patch.get_property(context, reference, "graphics")
        self.assertIsInstance(proxy, patch.CompleteGraphicsProxy)
        self.assertTrue(proxy.static)
        patch._invoke_graphics(context, proxy, "beginFill", (0xFF0000, 1.0))
        patch._invoke_graphics(
            context, proxy, "drawPath",
            ([1, 2, 2, 2], [0, 0, 20, 0, 20, 20, 0, 20], "nonZero"),
        )
        value = patch.rasterize(patch._state_for_proxy(proxy))
        self.assertIsNotNone(value)
        self.assertIsNotNone(value[0].getchannel("A").getbbox())
        self.assertGreater(context.writes, 0)

    def test_bitmap_fill_and_uvt_triangle_render(self):
        context = self._context()
        bitmap = complete.PreviewBitmapData(2, 2, True, 0xFFFF0000)
        bitmap.set_pixel(1, 0, 0xFF00FF00, True)
        bitmap.set_pixel(0, 1, 0xFF0000FF, True)
        proxy = patch.CompleteGraphicsProxy(context.movie, "root/test", None, True)
        patch._invoke_graphics(context, proxy, "beginBitmapFill", (bitmap, None, False, False))
        patch._invoke_graphics(
            context, proxy, "drawTriangles",
            (
                [0, 0, 24, 0, 0, 24],
                [0, 1, 2],
                [0, 0, 1, 1, 0, 1, 0, 1, 1],
                "none",
            ),
        )
        image = patch.rasterize(patch._state_for_proxy(proxy))[0]
        self.assertIsNotNone(image.getchannel("A").getbbox())
        self.assertGreater(len(set(image.getdata())), 1)

    def test_line_gradient_style_renders(self):
        context = self._context()
        proxy = patch.CompleteGraphicsProxy(context.movie, "root/line", None, True)
        patch._invoke_graphics(context, proxy, "lineStyle", (4, 0, 1.0))
        patch._invoke_graphics(
            context, proxy, "lineGradientStyle",
            ("linear", [0xFF0000, 0x0000FF], [1.0, 1.0], [0, 255], None, "pad", "rgb", 0),
        )
        patch._invoke_graphics(context, proxy, "moveTo", (0, 0))
        patch._invoke_graphics(context, proxy, "lineTo", (40, 0))
        image = patch.rasterize(patch._state_for_proxy(proxy))[0]
        self.assertIsNotNone(image.getchannel("A").getbbox())

    def test_bitmapdata_and_bitmap_constructors_are_isolated(self):
        context = self._context()
        bitmap = patch.call_value(
            context, runtime.RuntimeGlobal("flash.display.BitmapData"),
            "BitmapData", (4, 3, True, 0xFF102030),
        )
        self.assertIsInstance(bitmap, complete.PreviewBitmapData)
        self.assertEqual(bitmap.get_pixel(0, 0, True), 0xFF102030)
        display = patch.call_value(
            context, runtime.RuntimeGlobal("flash.display.Bitmap"),
            "Bitmap", (bitmap, "auto", True),
        )
        self.assertEqual(display.kind, "Bitmap")
        self.assertIs(display.extras["bitmapData"], bitmap)
        self.assertEqual(display.width, 4.0)

    def test_bitmapdata_methods_touch_preview_revision(self):
        context = self._context()
        bitmap = complete.PreviewBitmapData(2, 2, True, 0)
        before = bitmap.revision
        patch._bitmap_call(context, bitmap, "setpixel32", (1, 1, 0xFFFFFFFF))
        self.assertGreater(bitmap.revision, before)
        self.assertEqual(bitmap.get_pixel(1, 1, True), 0xFFFFFFFF)
        clone = patch._bitmap_call(context, bitmap, "clone", ())
        self.assertIsInstance(clone, complete.PreviewBitmapData)
        self.assertIsNot(clone.image, bitmap.image)


if __name__ == "__main__":
    unittest.main()
