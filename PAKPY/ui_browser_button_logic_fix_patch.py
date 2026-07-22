"""Correct button-name tokenization and directional navigation cones."""
from __future__ import annotations

import math
import re

import ui_browser
import ui_browser_button_navigation_patch as button


_INSTALLED = False


def name_tokens(value):
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return tuple(part.lower() for part in re.findall(r"[A-Za-z0-9]+", text))


def has_button_word(value):
    tokens = name_tokens(value)
    token_set = set(tokens)
    if any(token == "btn" or token.startswith("btn") or token == "button" for token in tokens):
        return True
    if "menu" in token_set and "item" in token_set:
        return True
    return any(word.replace("_", "") in token_set for word in button._BUTTON_WORDS)


def is_button_descriptor(descriptor):
    if descriptor is None:
        return False
    labels = {button._compact(name) for name, _frame in descriptor.labels}
    semantic = any(
        button._compact(candidate) in labels
        for group in button._STATE_LABELS.values()
        for candidate in group
    )
    named = has_button_word(
        f"{descriptor.name} {descriptor.path} {descriptor.kind}"
    )
    return bool(
        descriptor.button_mode or descriptor.tab_enabled or semantic or named
    )


def _center(region):
    left, top, right, bottom = region.bounds
    return ((left + right) * 0.5, (top + bottom) * 0.5)


def directional_target(regions, current_path, direction):
    values = [region for region in regions if getattr(region, "enabled", True)]
    if not values:
        return None
    current = next((region for region in values if region.path == current_path), None)
    if current is None:
        ordered = sorted(
            values,
            key=lambda value: (_center(value)[1], _center(value)[0], value.path),
        )
        return ordered[-1] if direction in ("left", "up") else ordered[0]
    cx, cy = _center(current)
    vector = {
        "left": (-1.0, 0.0), "right": (1.0, 0.0),
        "up": (0.0, -1.0), "down": (0.0, 1.0),
    }.get(direction)
    if vector is None:
        return None
    dx_axis, dy_axis = vector
    best = None
    for region in values:
        if region.path == current.path:
            continue
        x, y = _center(region)
        dx, dy = x - cx, y - cy
        primary = dx * dx_axis + dy * dy_axis
        if primary <= 1e-6:
            continue
        perpendicular = abs(dx * dy_axis - dy * dx_axis)
        if primary < perpendicular * 0.25:
            continue
        distance = math.hypot(dx, dy)
        score = primary + perpendicular * 2.25 + distance * 0.05
        key = (score, perpendicular, distance, region.path)
        if best is None or key < best[0]:
            best = (key, region)
    return best[1] if best else None


def looks_button_region(movie, region):
    values = button._runtime_values(movie, region.path)
    obj = button._dynamic_object(movie, region.path)
    return bool(
        region.tab_enabled
        or values.get("buttonMode", False)
        or (obj is not None and obj.extras.get("buttonMode", False))
        or has_button_word(f"{region.name} {region.path}")
    )


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    button._has_button_word = has_button_word
    button.is_button_descriptor = is_button_descriptor
    button.directional_target = directional_target
    button._looks_button_region = looks_button_region
    ui_browser.infer_ui_button_frame = button.infer_button_frame
    ui_browser.choose_directional_ui_target = directional_target
