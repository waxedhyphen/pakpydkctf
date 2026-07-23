from types import SimpleNamespace
import unittest

import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_graphics_patch as graphics


class AVM2GraphicsPatchTests(unittest.TestCase):
    def target(self):
        movie = SimpleNamespace(ui_avm2_runtime_generation=1)
        obj = dynamic.DynamicDisplayObject(
            token=1, kind="Shape", name="shape1",
            path="root/$dyn1:shape1", parent_path="root",
        )
        context = SimpleNamespace(movie=movie, writes=0)
        proxy = graphics.GraphicsProxy(movie, obj.path, obj)
        return movie, obj, context, proxy

    def test_runtime_commands_create_a_raster(self):
        _movie, obj, context, proxy = self.target()
        graphics._invoke_graphics(context, proxy, "beginFill", (0xFF0000, 1.0))
        graphics._invoke_graphics(context, proxy, "drawCircle", (20, 20, 10))
        graphics._invoke_graphics(context, proxy, "endFill", ())
        state = graphics._graphics_state(obj, False)
        self.assertIsNotNone(state)
        self.assertEqual(len(state.primitives), 1)
        raster = graphics._rasterize(state)
        self.assertIsNotNone(raster)
        image, _origin, _bounds, _cache_hit = raster
        self.assertIsNotNone(image.getchannel("A").getbbox())
        self.assertEqual(context.writes, 3)

    def test_unsupported_command_is_counted_without_mutation(self):
        movie, obj, context, proxy = self.target()
        result = graphics._invoke_graphics(context, proxy, "drawTriangles", ([],))
        self.assertIs(result, graphics.runtime._UNDEFINED)
        self.assertEqual(context.writes, 0)
        self.assertEqual(graphics._movie_state(movie)["rejected"], 1)
        self.assertEqual(graphics._graphics_state(obj).command_count, 0)


if __name__ == "__main__":
    unittest.main()
