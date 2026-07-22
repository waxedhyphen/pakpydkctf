"""Preserve input hit regions across frame-cache hits and keep display hit order."""
from __future__ import annotations

import copy

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_performance_patch as performance
import ui_browser_state_override_patch as overrides_patch


_INSTALLED = False
_BASE_KEY = None
_BASE_GET = None
_BASE_PUT = None
_BASE_CLEAR = None
_CACHE_MOVIES = {}
_CACHE_HITS = {}


def cache_key(renderer, frame, scale):
    key = _BASE_KEY(renderer, frame, scale)
    _CACHE_MOVIES[key] = renderer.movie
    return key


def cache_get(key):
    result = _BASE_GET(key)
    if result is not None:
        movie = _CACHE_MOVIES.get(key)
        if movie is not None:
            movie.ui_input_hit_regions = list(_CACHE_HITS.get(key, ()))
    return result


def cache_put(key, image, stats):
    result = _BASE_PUT(key, image, stats)
    movie = _CACHE_MOVIES.get(key)
    if movie is not None:
        _CACHE_HITS[key] = tuple(copy.copy(value) for value in getattr(movie, "ui_input_hit_regions", ()) or ())
    live = set(getattr(performance.RENDER_FRAME_CACHE, "_items", {}).keys())
    for value in tuple(_CACHE_HITS):
        if value not in live:
            _CACHE_HITS.pop(value, None)
            _CACHE_MOVIES.pop(value, None)
    return result


def cache_clear():
    _CACHE_HITS.clear()
    _CACHE_MOVIES.clear()
    return _BASE_CLEAR()


def draw_display(renderer, canvas, display, parent_matrix, parent_color, stack, level):
    if level == 0:
        renderer.movie.ui_input_hit_regions = []
    parent_path = getattr(renderer, "_ui_state_parent_path", "root") or "root"
    result = dynamic._BASE["draw"](
        renderer, canvas, display, parent_matrix, parent_color, stack, level,
    )
    overrides = overrides_patch.normalize_overrides(
        getattr(renderer.movie, "ui_state_overrides", {}),
    )
    # The base renderer has already recursed into children. Recording the current
    # display afterwards keeps later sibling depths above nested content in hit order.
    for depth in sorted(display):
        item, path, _manual = overrides_patch.apply_item_override(
            renderer.movie, parent_path, depth, display[depth], overrides,
        )
        if not getattr(item, "visible", True):
            continue
        definition = renderer.movie.definitions.get(getattr(item, "character_id", None))
        matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
        dynamic._record_hit(
            renderer, path, matrix, dynamic._bounds_for_static(renderer, item, definition),
            getattr(item, "name", ""),
            getattr(item, "_ui_enabled", True) and getattr(item, "_ui_mouse_enabled", True),
            getattr(item, "_ui_tab_enabled", False), False,
        )
    for obj in dynamic._children(renderer.movie, parent_path):
        dynamic._draw_dynamic(renderer, canvas, obj, parent_matrix, parent_color, stack, level)
    return result


def install():
    global _INSTALLED, _BASE_KEY, _BASE_GET, _BASE_PUT, _BASE_CLEAR
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_KEY = performance._render_cache_key
    _BASE_GET = performance.RENDER_FRAME_CACHE.get
    _BASE_PUT = performance.RENDER_FRAME_CACHE.put
    _BASE_CLEAR = performance.RENDER_FRAME_CACHE.clear
    performance._render_cache_key = cache_key
    performance.RENDER_FRAME_CACHE.get = cache_get
    performance.RENDER_FRAME_CACHE.put = cache_put
    performance.RENDER_FRAME_CACHE.clear = cache_clear
    dynamic.draw_display = draw_display
    ui_browser.UIRenderer._draw_display = draw_display
