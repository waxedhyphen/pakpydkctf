"""Route child hit regions to their nearest button-like MovieClip owner."""
from __future__ import annotations

from dataclasses import replace

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_button_navigation_patch as button


_INSTALLED = False
_BASE_DESCRIPTOR = None
_BASE_SET_STATE = None
_BASE_HIT = None


def _score(movie, node):
    if node is None:
        return 0
    kind = button._compact(getattr(node, "kind", ""))
    if "movieclip" not in kind and "simplebutton" not in kind:
        return 0
    metadata = dict(getattr(node, "metadata", {}) or {})
    labels = {
        button._compact(name)
        for name in dict(metadata.get("sprite_labels", {}) or {})
    }
    text = button._compact(
        f"{getattr(node, 'label', '')} {node.path} "
        f"{getattr(node, 'class_name', '')} {kind}"
    )
    values = dict(runtime._properties(movie).get(node.path, {}) or {})
    obj = button._dynamic_object(movie, node.path)
    score = 0
    if "simplebutton" in kind or "simplebutton" in text:
        score = max(score, 120)
    if any(
        button._compact(candidate) in labels
        for group in button._STATE_LABELS.values()
        for candidate in group
    ):
        score = max(score, 110)
    if values.get("buttonMode") or values.get("tabEnabled"):
        score = max(score, 100)
    if obj is not None and (
        obj.extras.get("buttonMode") or getattr(obj, "tab_enabled", False)
    ):
        score = max(score, 100)
    if "button" in text or "btn" in text:
        score = max(score, 90)
    if button._has_button_word(
        f"{getattr(node, 'label', '')} {node.path} "
        f"{getattr(node, 'class_name', '')} {kind}"
    ):
        score = max(score, 35)
    return score


def resolve_button_owner(owner, path):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return str(path or "")
    index = button._node_index(owner, movie)
    current = str(path or "")
    weak = ""
    while current:
        score = _score(movie, index.get(current))
        if score >= 80:
            return current
        if score >= 30 and not weak:
            weak = current
        if current == "root" or "/" not in current:
            break
        current = current.rsplit("/", 1)[0]
    return weak or str(path or "")


def descriptor(owner, path, region=None):
    resolved = resolve_button_owner(owner, path)
    result = _BASE_DESCRIPTOR(owner, resolved, None if resolved != path else region)
    if result is None or region is None:
        return result
    return replace(
        result,
        bounds=region.bounds,
        enabled=bool(result.enabled and region.enabled),
        tab_enabled=bool(result.tab_enabled or region.tab_enabled),
        dynamic=bool(result.dynamic or region.dynamic),
    )


def set_button_state(owner, path, state, request=True):
    result = descriptor(owner, path)
    target = result.path if result is not None else str(path or "")
    return _BASE_SET_STATE(owner, target, state, request)


def hit(owner, event):
    region, point = _BASE_HIT(owner, event)
    if region is None or not button._enabled(owner):
        return region, point
    result = descriptor(owner, region.path, region)
    if result is None or not button.is_button_descriptor(result):
        return region, point
    if result.path == region.path:
        return region, point
    return dynamic.HitRegion(
        result.path, region.bounds, result.name,
        result.enabled, result.tab_enabled, result.dynamic,
    ), point


def candidate_regions(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return []
    preferred = []
    fallback = []
    seen = set()
    for region in tuple(getattr(movie, "ui_input_hit_regions", ()) or ()):
        if not region.enabled:
            continue
        result = descriptor(owner, region.path, region)
        if result is None or not result.enabled or result.path in seen:
            continue
        seen.add(result.path)
        target = dynamic.HitRegion(
            result.path, region.bounds, result.name,
            result.enabled, result.tab_enabled, result.dynamic,
        )
        (preferred if button.is_button_descriptor(result) else fallback).append(target)
    return preferred or fallback


def install():
    global _INSTALLED, _BASE_DESCRIPTOR, _BASE_SET_STATE, _BASE_HIT
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_DESCRIPTOR = button._descriptor
    _BASE_SET_STATE = button._set_button_state
    _BASE_HIT = button.hit
    button._descriptor = descriptor
    button._set_button_state = set_button_state
    button._candidate_regions = candidate_regions
    button.hit = hit
    dynamic._hit = hit
    ui_browser.resolve_ui_button_owner = resolve_button_owner
    ui_browser.set_ui_button_state = set_button_state
