import struct
import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_state_override_patch as override_patch
import ui_browser_performance_patch as patch

try:
    from PIL import Image
except Exception:
    Image = None


def _place2(depth, character_id, name=""):
    flags = 0x02 | (0x20 if name else 0)
    payload = bytes([flags]) + struct.pack("<HH", depth, character_id)
    if name:
        payload += name.encode("utf-8") + b"\x00"
    return (ui_browser.TAG_PLACE_OBJECT2, payload)


class _Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class UIPerformancePatchTests(unittest.TestCase):
    def test_display_list_cache_builds_once_and_returns_copy(self):
        cache = patch.DisplayListCache(max_entries=2)
        tags = []
        calls = []

        def builder(actual_tags, frame):
            calls.append((actual_tags, frame))
            return {1: "item"}

        first = cache.get_or_build(tags, 3, builder)
        first[2] = "local"
        second = cache.get_or_build(tags, 3, builder)
        self.assertEqual(len(calls), 1)
        self.assertEqual(second, {1: "item"})
        self.assertEqual(cache.hits, 1)
        self.assertEqual(cache.misses, 1)

    def test_auto_preview_scale_is_fast_only_during_interaction(self):
        owner = SimpleNamespace(
            preview_quality_var=_Var("Auto"),
            _ui_force_full_quality=False,
            _ui_playback_running=False,
            _ui_fast_preview_until=0.0,
            _ui_adaptive_preview_scale=0.5,
        )
        self.assertEqual(patch.choose_preview_scale(owner, now=10.0), 1.0)
        owner._ui_fast_preview_until = 11.0
        self.assertEqual(patch.choose_preview_scale(owner, now=10.0), 0.5)
        owner.preview_quality_var = _Var("35%")
        self.assertEqual(patch.choose_preview_scale(owner, now=20.0), 0.35)
        owner._ui_force_full_quality = True
        self.assertEqual(patch.choose_preview_scale(owner, now=20.0), 1.0)

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_render_frame_cache_uses_byte_budget_and_copies_stats(self):
        cache = patch.RenderFrameCache(max_bytes=200)
        stats = SimpleNamespace(value=[1])
        image = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
        cache.put("a", image, stats)
        found_image, found_stats = cache.get("a")
        found_stats.value.append(2)
        self.assertIs(found_image, image)
        self.assertEqual(cache.get("a")[1].value, [1])
        cache.put("b", Image.new("RGBA", (6, 6)), SimpleNamespace(value=[]))
        self.assertLessEqual(cache.total_bytes, cache.max_bytes)

    def test_fast_sync_keeps_per_instance_state_and_reuses_token(self):
        shape = ui_browser.ShapeDef(2, (0.0, 0.0, 10.0, 10.0))
        sprite = ui_browser.SpriteDef(
            1,
            2,
            [_place2(1, 2, "inside"), (ui_browser.TAG_SHOW_FRAME, b"")],
            {},
        )
        movie = SimpleNamespace(
            definitions={1: sprite, 2: shape},
            root_tags=[_place2(3, 1, "clip"), (ui_browser.TAG_SHOW_FRAME, b"")],
            frame_count=1,
            symbol_classes={},
            ui_state_overrides={},
            ui_timeline_states={},
        )
        owner = SimpleNamespace(
            _current_movie=movie,
            _ui_timeline_states=movie.ui_timeline_states,
            _ui_state_overrides={},
            _ui_override_revision=0,
            frame_var=_Var(1),
        )
        original = override_patch._ORIGINAL_BUILD_DISPLAY_LIST
        base = original or ui_browser.build_display_list
        calls = []

        def builder(tags, frame):
            calls.append((id(tags), frame))
            return base(tags, frame)

        override_patch._ORIGINAL_BUILD_DISPLAY_LIST = builder
        try:
            first = patch.fast_sync_timeline_instances(owner)
            count = len(calls)
            second = patch.fast_sync_timeline_instances(owner)
        finally:
            override_patch._ORIGINAL_BUILD_DISPLAY_LIST = original
        self.assertEqual(first, ("root/3:clip",))
        self.assertEqual(second, first)
        self.assertEqual(len(calls), count)
        self.assertEqual(owner._ui_timeline_states["root/3:clip"]["frame_count"], 2)

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_scaled_render_reduces_stage_pixels(self):
        movie = SimpleNamespace(
            background=(0, 0, 0, 255),
            width=100,
            height=50,
            stage_bounds=(0.0, 0.0, 100.0, 50.0),
            root_tags=[(ui_browser.TAG_SHOW_FRAME, b"")],
            frame_count=1,
            definitions={},
            preview_rotate_180=False,
        )
        renderer = ui_browser.UIRenderer(movie, SimpleNamespace())
        image, _stats = patch._scaled_render(renderer, 1, 0.5)
        self.assertEqual(image.size, (50, 25))


if __name__ == "__main__":
    unittest.main()
