"""Cache precise UI hit maps and connect them to AVM2 input properties."""
from __future__ import annotations

from collections import OrderedDict

import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_performance_patch as performance
import ui_browser_hit_geometry as geometry

_BASE = {}
_GEOMETRY_CACHE = OrderedDict()
_GEOMETRY_CACHE_MAX = 128


def _geometry_key(renderer, frame):
    movie = renderer.movie
    dynamic_state = dynamic._state(movie)
    return (
        id(movie), id(renderer.resolver), int(frame),
        int(getattr(movie, "ui_override_revision", 0)),
        performance._visual_timeline_signature(getattr(movie, "ui_timeline_states", {})),
        int(getattr(movie, "ui_avm2_runtime_revision", 0)),
        int(dynamic_state.get("revision", 0)),
        int(getattr(movie, "ui_classic_button_revision", 0)),
    )


def _restore_geometry(movie, cached):
    mapping, regions, diagnostics = cached
    movie.ui_precise_hit_geometries = mapping
    movie.ui_input_hit_regions = list(regions)
    movie.ui_precise_hit_diagnostics = dict(diagnostics)


def build_precise_hit_map(renderer, frame):
    key = _geometry_key(renderer, frame)
    cached = _GEOMETRY_CACHE.get(key)
    if cached is not None:
        _GEOMETRY_CACHE.move_to_end(key)
        _restore_geometry(renderer.movie, cached)
        return cached

    old_regions = tuple(getattr(renderer.movie, "ui_input_hit_regions", ()) or ())
    old_meta = {region.path: region for region in old_regions}
    collector = geometry.GeometryCollector(renderer, frame)
    values = collector.collect()
    order = []
    grouped = {}
    for value in values:
        path = str(value.path)
        grouped.setdefault(path, []).append(value)
        if path in order:
            order.remove(path)
        order.append(path)
    mapping = geometry._apply_runtime_masks(renderer.movie, grouped)
    mapping = geometry._apply_hit_areas(renderer.movie, mapping, order)

    regions = []
    for path in order:
        geoms = tuple(mapping.get(path, ()))
        bounds = geometry._union_bounds(value.bounds for value in geoms)
        if bounds is None:
            continue
        previous = old_meta.get(path)
        meta = collector.meta.get(path, {})
        enabled = bool(getattr(previous, "enabled", meta.get("enabled", True)))
        tab_enabled = bool(getattr(previous, "tab_enabled", meta.get("tab_enabled", False)))
        dynamic_flag = bool(getattr(previous, "dynamic", meta.get("dynamic", False)))
        name = str(getattr(previous, "name", "") or meta.get("name", path.rsplit(":", 1)[-1]))
        regions.append(dynamic.HitRegion(path, bounds, name, enabled, tab_enabled, dynamic_flag))

    diagnostics = {
        "geometries": sum(len(value) for value in mapping.values()),
        "paths": len(mapping), "alpha": collector.alpha_count,
        "clip_depth_masks": collector.mask_count,
        "scroll_rect_clips": len(collector.scroll_paths),
        "truncated": collector.truncated,
        "cache_hit": False,
    }
    cached = (mapping, tuple(regions), diagnostics)
    _GEOMETRY_CACHE[key] = cached
    _GEOMETRY_CACHE.move_to_end(key)
    while len(_GEOMETRY_CACHE) > _GEOMETRY_CACHE_MAX:
        _GEOMETRY_CACHE.popitem(last=False)
    _restore_geometry(renderer.movie, cached)
    return cached


def renderer_render(renderer, frame):
    result = _BASE["render"](renderer, frame)
    owner = getattr(renderer.movie, "_ui_avm2_runtime_owner", None)
    enabled = bool(getattr(renderer.movie, "ui_precise_hit_enabled", True))
    variable = getattr(owner, "ui_precise_hit_enabled_var", None) if owner is not None else None
    if variable is not None:
        try:
            enabled = bool(variable.get())
        except Exception:
            pass
    renderer.movie.ui_precise_hit_enabled = enabled
    if enabled:
        build_precise_hit_map(renderer, frame)
    return result


def precise_raw_hit(owner, event):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not bool(getattr(movie, "ui_precise_hit_enabled", True)):
        return _BASE["raw_hit"](owner, event)
    point = dynamic._stage_point(owner, event)
    if point is None:
        return None, point
    mapping = getattr(movie, "ui_precise_hit_geometries", {}) or {}
    diagnostics = getattr(movie, "ui_precise_hit_diagnostics", {}) or {}
    diagnostics["tests"] = int(diagnostics.get("tests", 0)) + 1
    for region in reversed(tuple(getattr(movie, "ui_input_hit_regions", ()) or ()):
        if not region.enabled:
            continue
        left, top, right, bottom = region.bounds
        if not (left <= point[0] <= right and top <= point[1] <= bottom):
            continue
        geoms = tuple(mapping.get(region.path, ()))
        if geoms and not any(value.contains(point) for value in geoms):
            diagnostics["precise_rejects"] = int(diagnostics.get("precise_rejects", 0)) + 1
            continue
        diagnostics["hits"] = int(diagnostics.get("hits", 0)) + 1
        movie.ui_precise_hit_diagnostics = diagnostics
        return region, point
    movie.ui_precise_hit_diagnostics = diagnostics
    return None, point


def set_property(context, reference, name, value):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if short not in ("scrollRect", "mask", "hitArea"):
        return _BASE["set_property"](context, reference, name, value)
    if isinstance(reference, dynamic.DynamicDisplayObject):
        target = reference.extras
    elif isinstance(reference, runtime.RuntimeRef):
        target = runtime._properties(context.movie).setdefault(reference.path, {})
    else:
        return _BASE["set_property"](context, reference, name, value)
    if value is None or value is runtime._UNDEFINED:
        target.pop(short, None)
    else:
        target[short] = value
    context.writes += 1
    dynamic._touch(context.movie)
    _GEOMETRY_CACHE.clear()
    return True


def get_property(context, receiver, name):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if short in ("scrollRect", "mask", "hitArea"):
        if isinstance(receiver, dynamic.DynamicDisplayObject):
            return receiver.extras.get(short, runtime._UNDEFINED)
        if isinstance(receiver, runtime.RuntimeRef):
            return runtime._properties(context.movie).get(receiver.path, {}).get(short, runtime._UNDEFINED)
    return _BASE["get_property"](context, receiver, name)


def clear_geometry_cache():
    _GEOMETRY_CACHE.clear()


def reset_movie(movie):
    if movie is not None:
        movie.ui_precise_hit_geometries = {}
        movie.ui_precise_hit_diagnostics = {}
    clear_geometry_cache()


def install_hooks(base_render, base_raw_hit, base_set_property, base_get_property):
    _BASE.update(
        render=base_render, raw_hit=base_raw_hit,
        set_property=base_set_property, get_property=base_get_property,
    )
