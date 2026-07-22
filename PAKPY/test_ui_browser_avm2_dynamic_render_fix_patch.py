import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_dynamic_render_fix_patch as patch
import ui_browser_performance_patch as performance


class DynamicRenderFixTests(unittest.TestCase):
    def setUp(self):
        patch._CACHE_HITS.clear()
        patch._CACHE_MOVIES.clear()

    def test_cache_hit_restores_matching_hit_regions(self):
        movie = SimpleNamespace(ui_input_hit_regions=["stale"])
        key = ("frame", 1)
        patch._CACHE_MOVIES[key] = movie
        patch._CACHE_HITS[key] = ("first", "second")
        old = patch._BASE_GET
        patch._BASE_GET = lambda value: ("image", "stats") if value == key else None
        try:
            self.assertEqual(patch.cache_get(key), ("image", "stats"))
        finally:
            patch._BASE_GET = old
        self.assertEqual(movie.ui_input_hit_regions, ["first", "second"])

    def test_cache_clear_removes_hit_region_side_cache(self):
        patch._CACHE_MOVIES["key"] = object()
        patch._CACHE_HITS["key"] = ("region",)
        old = patch._BASE_CLEAR
        calls = []
        patch._BASE_CLEAR = lambda: calls.append(True)
        try:
            patch.cache_clear()
        finally:
            patch._BASE_CLEAR = old
        self.assertEqual(patch._CACHE_MOVIES, {})
        self.assertEqual(patch._CACHE_HITS, {})
        self.assertEqual(calls, [True])

    def test_current_depth_regions_are_recorded_after_nested_content(self):
        movie = SimpleNamespace(
            ui_input_hit_regions=[], ui_state_overrides={}, definitions={1: ui_browser.ShapeDef(1, (0, 0, 10, 10))},
            ui_avm2_runtime_properties={},
        )
        item = ui_browser.DisplayObject(1, character_id=1, name="overlay")
        renderer = SimpleNamespace(movie=movie)
        renderer._ui_state_parent_path = "root"
        renderer._point = lambda matrix, x, y: (x, y)
        display = {1: item}
        old_draw = dynamic._BASE.get("draw")
        old_record = dynamic._record_hit
        old_bounds = dynamic._bounds_for_static
        old_children = dynamic._children
        old_dynamic = dynamic._draw_dynamic
        dynamic._BASE["draw"] = lambda *args: movie.ui_input_hit_regions.append("nested")
        dynamic._record_hit = lambda renderer, path, matrix, bounds, *args: movie.ui_input_hit_regions.append(path)
        dynamic._bounds_for_static = lambda renderer, value, definition: definition.bounds
        dynamic._children = lambda movie, path: ()
        dynamic._draw_dynamic = lambda *args: None
        try:
            patch.draw_display(renderer, None, display, ui_browser.Affine(), ui_browser.IDENTITY_COLOR, set(), 0)
        finally:
            dynamic._BASE["draw"] = old_draw
            dynamic._record_hit = old_record
            dynamic._bounds_for_static = old_bounds
            dynamic._children = old_children
            dynamic._draw_dynamic = old_dynamic
        self.assertEqual(movie.ui_input_hit_regions, ["nested", "root/1:overlay"])


if __name__ == "__main__":
    unittest.main()
