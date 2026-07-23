"""Place timeline-instance Graphics inside the existing mask/filter render transaction.

The state-override renderer already processes one placement at a time. This follow-up
replaces its captured unmasked draw callback so runtime Graphics are painted immediately
before the placement's original definition, preserving sibling depth, masks, filters and
blend modes without changing stable instance paths.
"""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_graphics_complete_patch as complete_patch
import ui_browser_graphics_model as model

_INSTALLED = False
_ORIGINAL_UNMASKED = None
_PATCHED_CELL = None


def _draw_unmasked_with_graphics(renderer, canvas, display, parent_matrix, parent_color, stack, level):
    if len(display) == 1:
        _depth, item = next(iter(display.items()))
        path = str(getattr(renderer, "_ui_current_path", "") or "")
        state = complete_patch._static_state(renderer.movie, path) if path else None
        if isinstance(state, model.GraphicsState) and (state.primitives or state.current_commands):
            matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
            color = parent_color.combine(getattr(item, "color", ui_browser.IDENTITY_COLOR))
            complete_patch._draw_state(renderer, canvas, state, matrix, color)
    return _ORIGINAL_UNMASKED(
        renderer, canvas, display, parent_matrix, parent_color, stack, level,
    )


def _patch_state_draw_cell():
    global _ORIGINAL_UNMASKED, _PATCHED_CELL
    state_draw = dynamic._BASE.get("draw")
    closure = getattr(state_draw, "__closure__", None)
    freevars = getattr(getattr(state_draw, "__code__", None), "co_freevars", ())
    if not callable(state_draw) or not closure:
        return False
    for name, cell in zip(freevars, closure):
        if name != "draw_unmasked":
            continue
        original = cell.cell_contents
        if not callable(original):
            return False
        _ORIGINAL_UNMASKED = original
        _PATCHED_CELL = cell
        cell.cell_contents = _draw_unmasked_with_graphics
        return True
    return False


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    previous = complete_patch._BASE.get("draw_display")
    if callable(previous):
        ui_browser.UIRenderer._draw_display = previous
    if not _patch_state_draw_cell():
        # Conservative fallback when an unexpected earlier patch removed the known
        # state-renderer closure.
        ui_browser.UIRenderer._draw_display = complete_patch.draw_display
    ui_browser.UI_GRAPHICS_TIMELINE_ORDER_EXACT = bool(_PATCHED_CELL is not None)
