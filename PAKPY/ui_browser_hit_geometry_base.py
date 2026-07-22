"""Collect transformed UI hit geometry, alpha masks and runtime clips."""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_classic_button as classic


def _runtime_values(movie, path):
    return dict(runtime._properties(movie).get(str(path), {}) or {})


def _dynamic_object(movie, path):
    try:
        return dynamic._dynamic_for_path(movie, path)
    except Exception:
        return None


def _property(movie, path, name, default=None):
    obj = _dynamic_object(movie, path)
    if obj is not None and name in ("mask", "hitArea", "scrollRect"):
        return obj.extras.get(name, default)
    return _runtime_values(movie, path).get(name, default)


def _reference_path(value):
    if isinstance(value, dynamic.DynamicDisplayObject):
        return str(value.path or "")
    if isinstance(value, runtime.RuntimeRef):
        return str(value.path or "")
    if isinstance(value, str) and (value == "root" or value.startswith("root/")):
        return value
    return str(getattr(value, "path", "") or "")


def _world_bounds(matrix, bounds):
    xmin, ymin, xmax, ymax = bounds
    points = (
        (matrix.a * xmin + matrix.c * ymin + matrix.tx,
         matrix.b * xmin + matrix.d * ymin + matrix.ty),
        (matrix.a * xmax + matrix.c * ymin + matrix.tx,
         matrix.b * xmax + matrix.d * ymin + matrix.ty),
        (matrix.a * xmax + matrix.c * ymax + matrix.tx,
         matrix.b * xmax + matrix.d * ymax + matrix.ty),
        (matrix.a * xmin + matrix.c * ymax + matrix.tx,
         matrix.b * xmin + matrix.d * ymax + matrix.ty),
    )
    return (
        min(value[0] for value in points), min(value[1] for value in points),
        max(value[0] for value in points), max(value[1] for value in points),
    )


def _union_bounds(values):
    values = tuple(values)
    if not values:
        return None
    return (
        min(value[0] for value in values), min(value[1] for value in values),
        max(value[2] for value in values), max(value[3] for value in values),
    )


def _rect_geometry(path, matrix, bounds, clips=(), kind="rect", character_id=None):
    return classic.HitGeometry(
        str(path), str(kind), _world_bounds(matrix, bounds), matrix.inverse_pillow(),
        tuple(bounds), None, (0.0, 0.0), tuple(clips), character_id,
    )


def _alpha_geometry(path, matrix, bounds, alpha, origin, clips=(), kind="alpha", character_id=None):
    return classic.HitGeometry(
        str(path), str(kind), _world_bounds(matrix, bounds), matrix.inverse_pillow(),
        tuple(bounds), alpha, tuple(origin), tuple(clips), character_id,
    )


def _scroll_clip(movie, path, matrix, inherited):
    rect = classic.normalize_rect(_property(movie, path, "scrollRect"))
    if rect is None:
        return tuple(inherited)
    geometry = _rect_geometry(f"{path}#scrollRect", matrix, rect, inherited, "scrollRect")
    return tuple(inherited) + (classic.HitClip((geometry,), "scrollRect"),)
