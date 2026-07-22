"""Render SWF/Scaleform clip-depth masks in the static UI Browser.

A display object with ``clip_depth`` is a mask source. It is not drawn into the
final frame; instead, its rendered alpha clips subsequent display-list objects at
depths greater than the mask depth and up to the inclusive clip depth. Multiple
active masks intersect, and masks inside sprites are handled recursively.

Placement filters are applied to isolated layers before clip-depth masking and
blend-mode composition. The patch is display-only; GFX/SWF data and repacking are
unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

import ui_browser

try:
    from PIL import Image as PILImage, ImageChops
except Exception:
    PILImage = None
    ImageChops = None


_INSTALLED = False


@dataclass(frozen=True)
class ActiveClipMask:
    source_depth: int
    end_depth: int
    alpha: object


def _new_layer(canvas):
    if PILImage is None:
        raise ui_browser.PakError("Pillow fehlt für UI-Masken")
    return PILImage.new("RGBA", canvas.size, (0, 0, 0, 0))


def _multiply_alpha(left, right):
    if ImageChops is not None:
        return ImageChops.multiply(left, right)
    return PILImage.frombytes(
        "L",
        left.size,
        bytes((a * b + 127) // 255 for a, b in zip(left.tobytes(), right.tobytes())),
    )


def intersect_mask_alpha(alpha, masks):
    result = alpha
    for mask in masks:
        result = _multiply_alpha(result, mask.alpha)
    return result


def apply_clip_masks(layer, masks):
    if not masks:
        return layer
    layer.putalpha(intersect_mask_alpha(layer.getchannel("A"), masks))
    return layer


def active_masks_at_depth(masks, depth):
    return [mask for mask in masks if depth <= mask.end_depth]


def _apply_item_filters(renderer, layer, item):
    filters = tuple(getattr(item, "filters", ()) or ())
    if not filters:
        return layer
    applier = getattr(renderer, "_apply_ui_filters", None)
    if applier is None:
        renderer.stats.unrendered_filter_placements = getattr(
            renderer.stats, "unrendered_filter_placements", 0,
        ) + 1
        return layer
    return applier(layer, filters)


def _render_mask_source(renderer, draw_unmasked, canvas, item, parent_matrix, parent_color, stack, level):
    layer = _new_layer(canvas)
    old_bounds = renderer.show_bounds
    old_placeholders = renderer.show_placeholders
    renderer.show_bounds = False
    renderer.show_placeholders = False
    try:
        draw_unmasked(renderer, layer, {item.depth: item}, parent_matrix, parent_color, stack, level)
    finally:
        renderer.show_bounds = old_bounds
        renderer.show_placeholders = old_placeholders
    return _apply_item_filters(renderer, layer, item)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    if PILImage is None:
        return

    draw_unmasked = ui_browser.UIRenderer._draw_display
    original_format_info = ui_browser.UIBrowser._format_info

    def draw_display(self, canvas, display, parent_matrix, parent_color, stack, level):
        if level > 64:
            self.stats.recursion_skips += 1
            return
        active_masks = []
        for depth in sorted(display):
            active_masks = active_masks_at_depth(active_masks, depth)
            item = display[depth]
            if not item.visible:
                continue
            clip_depth = item.clip_depth
            if clip_depth is not None and int(clip_depth) > int(depth):
                mask_layer = _render_mask_source(
                    self, draw_unmasked, canvas, item,
                    parent_matrix, parent_color, stack, level,
                )
                alpha = mask_layer.getchannel("A")
                if active_masks:
                    alpha = intersect_mask_alpha(alpha, active_masks)
                active_masks.append(ActiveClipMask(int(depth), int(clip_depth), alpha))
                self.stats.masks_defined = getattr(self.stats, "masks_defined", 0) + 1
                if alpha.getbbox() is None:
                    self.stats.empty_masks = getattr(self.stats, "empty_masks", 0) + 1
                continue

            blend_mode = int(getattr(item, "blend_mode", 0) or 0)
            filters = tuple(getattr(item, "filters", ()) or ())
            if active_masks or blend_mode not in (0, 1) or filters:
                layer = _new_layer(canvas)
                draw_unmasked(
                    self, layer, {depth: item},
                    parent_matrix, parent_color, stack, level,
                )
                if filters:
                    layer = _apply_item_filters(self, layer, item)
                if active_masks:
                    apply_clip_masks(layer, active_masks)
                    self.stats.masked_placements = getattr(self.stats, "masked_placements", 0) + 1
                compositor = getattr(self, "_composite_ui_layer", None)
                if compositor is not None:
                    compositor(canvas, layer, blend_mode)
                else:
                    canvas.alpha_composite(layer)
            else:
                draw_unmasked(
                    self, canvas, {depth: item},
                    parent_matrix, parent_color, stack, level,
                )

    def format_info(self, stats):
        text = original_format_info(self, stats)
        masks = getattr(stats, "masks_defined", 0)
        masked = getattr(stats, "masked_placements", 0)
        empty = getattr(stats, "empty_masks", 0)
        scale9 = getattr(stats, "scale9_placements", 0)
        fallbacks = getattr(stats, "scale9_fallbacks", 0)
        blend_modes = getattr(stats, "blend_modes", {})
        unavailable_filters = getattr(stats, "unrendered_filter_placements", 0)
        if not masks and not masked and not empty and not scale9 and not fallbacks and not blend_modes and not unavailable_filters:
            return text
        lines = []
        if masks or masked or empty:
            lines.extend([
                "", "Masken:",
                f"- ClipDepth-Masken: {masks}",
                f"- Maskierte Placements: {masked}",
            ])
        if empty:
            lines.append(f"- Leere Masken: {empty}")
        if scale9 or fallbacks:
            lines.extend(["", "Scale9:", f"- Nine-slice Placements: {scale9}"])
            if fallbacks:
                lines.append(f"- Fallbacks: {fallbacks}")
        if blend_modes:
            lines.extend(["", "Blend Modes:"])
            names = getattr(ui_browser, "BLEND_NAMES", {})
            for mode, count in sorted(blend_modes.items()):
                lines.append(f"- {names.get(mode, mode)}: {count}")
        if unavailable_filters:
            lines.extend(["", "Filter:", f"- Renderer nicht installiert: {unavailable_filters}"])
        return text + "\n" + "\n".join(lines)

    ui_browser.UIRenderer._draw_display = draw_display
    ui_browser.UIBrowser._format_info = format_info
    ui_browser.ActiveClipMask = ActiveClipMask
    ui_browser.apply_clip_masks = apply_clip_masks
