"""Render the Scaleform filters used by Tropical Freeze UI placements.

The current UI corpus primarily uses Glow and DropShadow, with a small number of
Blur and Bevel records. Filters are applied to an isolated placement layer before
clip-depth masking and blend-mode composition. Unsupported filter types remain
available as diagnostics instead of breaking the frame.

This patch only changes previews. GFX/SWF/TXTR bytes and repacking are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import struct

import ui_browser

try:
    from PIL import Image as PILImage, ImageChops, ImageFilter
except Exception:
    PILImage = None
    ImageChops = None
    ImageFilter = None


_INSTALLED = False


@dataclass(frozen=True)
class ParsedFilter:
    filter_id: int
    name: str
    color: tuple[int, int, int, int] = (0, 0, 0, 255)
    highlight_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    blur_x: float = 0.0
    blur_y: float = 0.0
    angle: float = 0.0
    distance: float = 0.0
    strength: float = 1.0
    inner: bool = False
    knockout: bool = False
    composite_source: bool = True
    on_top: bool = False
    passes: int = 1


def _require(data: bytes, size: int, name: str) -> None:
    if len(data) < size:
        raise ui_browser.PakError(f"{name} ist abgeschnitten")


def _fixed(data: bytes, off: int) -> float:
    _require(data[off:], 4, "FIXED")
    return struct.unpack_from("<i", data, off)[0] / 65536.0


def _fixed8(data: bytes, off: int) -> float:
    _require(data[off:], 2, "FIXED8")
    return struct.unpack_from("<H", data, off)[0] / 256.0


def parse_filter_record(record) -> ParsedFilter:
    """Decode one FilterRecord produced by ui_browser_scale9_blend_patch."""
    raw = bytes(getattr(record, "raw", b""))
    filter_id = int(getattr(record, "filter_id", raw[0] if raw else -1))
    if not raw:
        raise ui_browser.PakError("Leerer SWF-Filterdatensatz")
    if raw[0] == filter_id:
        data = raw[1:]
    else:
        data = raw

    name = str(getattr(record, "name", f"Filter{filter_id}"))
    if filter_id == 0:
        _require(data, 23, "DropShadow")
        flags = data[22]
        return ParsedFilter(
            filter_id, name,
            color=tuple(data[0:4]),
            blur_x=max(0.0, _fixed(data, 4)),
            blur_y=max(0.0, _fixed(data, 8)),
            angle=_fixed(data, 12),
            distance=_fixed(data, 16),
            strength=max(0.0, _fixed8(data, 20)),
            inner=bool(flags & 0x80),
            knockout=bool(flags & 0x40),
            composite_source=bool(flags & 0x20),
            passes=max(1, flags & 0x1F),
        )
    if filter_id == 1:
        _require(data, 9, "Blur")
        return ParsedFilter(
            filter_id, name,
            blur_x=max(0.0, _fixed(data, 0)),
            blur_y=max(0.0, _fixed(data, 4)),
            passes=max(1, data[8] >> 3),
            composite_source=False,
        )
    if filter_id == 2:
        _require(data, 15, "Glow")
        flags = data[14]
        return ParsedFilter(
            filter_id, name,
            color=tuple(data[0:4]),
            blur_x=max(0.0, _fixed(data, 4)),
            blur_y=max(0.0, _fixed(data, 8)),
            strength=max(0.0, _fixed8(data, 12)),
            inner=bool(flags & 0x80),
            knockout=bool(flags & 0x40),
            composite_source=bool(flags & 0x20),
            passes=max(1, flags & 0x1F),
        )
    if filter_id == 3:
        _require(data, 27, "Bevel")
        flags = data[26]
        return ParsedFilter(
            filter_id, name,
            color=tuple(data[0:4]),
            highlight_color=tuple(data[4:8]),
            blur_x=max(0.0, _fixed(data, 8)),
            blur_y=max(0.0, _fixed(data, 12)),
            angle=_fixed(data, 16),
            distance=_fixed(data, 20),
            strength=max(0.0, _fixed8(data, 24)),
            inner=bool(flags & 0x80),
            knockout=bool(flags & 0x40),
            composite_source=bool(flags & 0x20),
            on_top=bool(flags & 0x10),
            passes=max(1, flags & 0x0F),
        )
    raise ui_browser.PakError(f"{name} wird im UI-Corpus nicht visuell benötigt")


def _alpha_lut(scale: float):
    scale = max(0.0, float(scale))
    return [max(0, min(255, int(round(value * scale)))) for value in range(256)]


def _scale_alpha(alpha, scale: float):
    return alpha.point(_alpha_lut(scale))


def _blur_radius(item: ParsedFilter) -> float:
    # Flash blurX/blurY describe the filter extent. Pillow's Gaussian radius is
    # closer to half that extent. Multiple passes increase the effective radius.
    extent = math.hypot(item.blur_x, item.blur_y) / math.sqrt(2.0)
    return max(0.0, 0.5 * extent * math.sqrt(max(1, min(item.passes, 4))))


def _blur_channel(alpha, item: ParsedFilter):
    if ImageFilter is None:
        return alpha
    radius = _blur_radius(item)
    if radius <= 1e-6:
        return alpha.copy()
    return alpha.filter(ImageFilter.GaussianBlur(radius=radius))


def _blur_rgba(image, item: ParsedFilter):
    if ImageFilter is None:
        return image.copy()
    radius = _blur_radius(item)
    if radius <= 1e-6:
        return image.copy()
    return image.filter(ImageFilter.GaussianBlur(radius=radius))


def _shift_alpha(alpha, dx: float, dy: float):
    x = int(round(dx))
    y = int(round(dy))
    result = PILImage.new("L", alpha.size, 0)
    width = alpha.width - abs(x)
    height = alpha.height - abs(y)
    if width <= 0 or height <= 0:
        return result
    src_left = max(0, -x)
    src_top = max(0, -y)
    dst_left = max(0, x)
    dst_top = max(0, y)
    crop = alpha.crop((src_left, src_top, src_left + width, src_top + height))
    result.paste(crop, (dst_left, dst_top))
    return result


def _colorize(alpha, color):
    base_alpha = max(0, min(255, int(color[3])))
    if base_alpha != 255:
        alpha = _scale_alpha(alpha, base_alpha / 255.0)
    result = PILImage.new("RGBA", alpha.size, tuple(color))
    result.putalpha(alpha)
    return result


def _compose(source, effect, item: ParsedFilter, effect_on_top: bool = False):
    if item.knockout or not item.composite_source:
        return effect
    if item.inner or item.on_top or effect_on_top:
        result = source.copy()
        result.alpha_composite(effect)
        return result
    result = effect.copy()
    result.alpha_composite(source)
    return result


def _apply_glow(source, item: ParsedFilter):
    alpha = source.getchannel("A")
    blurred = _blur_channel(alpha, item)
    if item.inner and ImageChops is not None:
        blurred = ImageChops.subtract(alpha, blurred)
    effect_alpha = _scale_alpha(blurred, item.strength)
    effect = _colorize(effect_alpha, item.color)
    return _compose(source, effect, item, effect_on_top=item.inner)


def _apply_drop_shadow(source, item: ParsedFilter):
    alpha = source.getchannel("A")
    dx = math.cos(item.angle) * item.distance
    dy = math.sin(item.angle) * item.distance
    shifted = _shift_alpha(alpha, dx, dy)
    blurred = _blur_channel(shifted, item)
    if item.inner and ImageChops is not None:
        blurred = ImageChops.multiply(alpha, ImageChops.invert(blurred))
    effect_alpha = _scale_alpha(blurred, item.strength)
    effect = _colorize(effect_alpha, item.color)
    return _compose(source, effect, item, effect_on_top=item.inner)


def _apply_bevel(source, item: ParsedFilter):
    alpha = source.getchannel("A")
    dx = math.cos(item.angle) * item.distance
    dy = math.sin(item.angle) * item.distance
    forward = _shift_alpha(alpha, dx, dy)
    backward = _shift_alpha(alpha, -dx, -dy)
    if ImageChops is None:
        return source
    if item.inner:
        highlight_alpha = ImageChops.subtract(alpha, forward)
        shadow_alpha = ImageChops.subtract(alpha, backward)
    else:
        highlight_alpha = ImageChops.subtract(backward, alpha)
        shadow_alpha = ImageChops.subtract(forward, alpha)
    highlight_alpha = _scale_alpha(_blur_channel(highlight_alpha, item), item.strength)
    shadow_alpha = _scale_alpha(_blur_channel(shadow_alpha, item), item.strength)
    effect = PILImage.new("RGBA", source.size, (0, 0, 0, 0))
    effect.alpha_composite(_colorize(shadow_alpha, item.color))
    effect.alpha_composite(_colorize(highlight_alpha, item.highlight_color))
    return _compose(source, effect, item, effect_on_top=item.inner or item.on_top)


def _filter_margin(item: ParsedFilter) -> int:
    return max(2, int(math.ceil(_blur_radius(item) * 3.0 + abs(item.distance) + 2.0)))


def apply_parsed_filter(image, item: ParsedFilter):
    if PILImage is None:
        return image
    source = image.convert("RGBA")
    bbox = source.getbbox()
    if bbox is None:
        return source
    margin = _filter_margin(item)
    left = max(0, bbox[0] - margin)
    top = max(0, bbox[1] - margin)
    right = min(source.width, bbox[2] + margin)
    bottom = min(source.height, bbox[3] + margin)
    cropped = source.crop((left, top, right, bottom))
    if item.filter_id == 0:
        filtered = _apply_drop_shadow(cropped, item)
    elif item.filter_id == 1:
        filtered = _blur_rgba(cropped, item)
    elif item.filter_id == 2:
        filtered = _apply_glow(cropped, item)
    elif item.filter_id == 3:
        filtered = _apply_bevel(cropped, item)
    else:
        filtered = cropped
    result = PILImage.new("RGBA", source.size, (0, 0, 0, 0))
    result.alpha_composite(filtered, (left, top))
    return result


def apply_filter_chain(image, records, stats=None):
    """Apply SWF filters in file order and retain unsupported records as diagnostics."""
    result = image
    for record in tuple(records or ()):
        try:
            item = parse_filter_record(record)
            result = apply_parsed_filter(result, item)
            if stats is not None:
                counts = getattr(stats, "filter_effects", None)
                if counts is None:
                    stats.filter_effects = {}
                    counts = stats.filter_effects
                counts[item.name] = counts.get(item.name, 0) + 1
        except Exception:
            if stats is not None:
                name = str(getattr(record, "name", f"Filter{getattr(record, 'filter_id', '?')}"))
                unsupported = getattr(stats, "filter_unsupported", None)
                if unsupported is None:
                    stats.filter_unsupported = {}
                    unsupported = stats.filter_unsupported
                unsupported[name] = unsupported.get(name, 0) + 1
    return result


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    if PILImage is None:
        return

    original_format_info = ui_browser.UIBrowser._format_info

    def apply_ui_filters(self, layer, records):
        result = apply_filter_chain(layer, records, self.stats)
        self.stats.filtered_placements = getattr(self.stats, "filtered_placements", 0) + 1
        return result

    def format_info(self, stats):
        text = original_format_info(self, stats)
        effects = getattr(stats, "filter_effects", {})
        unsupported = getattr(stats, "filter_unsupported", {})
        placements = getattr(stats, "filtered_placements", 0)
        if not effects and not unsupported and not placements:
            return text
        lines = ["", "Filter:", f"- Gefilterte Placements: {placements}"]
        for name, count in sorted(effects.items()):
            lines.append(f"- {name}: {count}")
        if unsupported:
            lines.append("- Nicht gerendert:")
            for name, count in sorted(unsupported.items()):
                lines.append(f"  - {name}: {count}")
        return text + "\n" + "\n".join(lines)

    ui_browser.UIRenderer._apply_ui_filters = apply_ui_filters
    ui_browser.UIBrowser._format_info = format_info
    ui_browser.ParsedFilter = ParsedFilter
    ui_browser.parse_ui_filter_record = parse_filter_record
    ui_browser.apply_ui_filter_chain = apply_filter_chain
