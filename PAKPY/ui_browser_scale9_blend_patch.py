"""Add Scale9 grids, PlaceObject3 visibility and blend modes to the UI Browser.

The patch is installed after the vector-shape renderer and before the clip-depth mask
renderer.  DefineScalingGrid sprites are rendered once at their natural size and
resized as a nine-slice image, preserving corner and edge thickness.  PlaceObject3
extension fields are parsed far enough to honor explicit visibility and blend modes;
filter lists are retained for diagnostics and for the next renderer phase.

All changes are preview-only.  GFX/SWF/TXTR bytes and repacking are unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import ui_browser
import ui_browser_shape_patch

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


TAG_DEFINE_SCALING_GRID = 78
_INSTALLED = False
_SCALE9_CACHE = {}

BLEND_NAMES = {
    0: "Normal", 1: "Normal", 2: "Layer", 3: "Multiply", 4: "Screen",
    5: "Lighten", 6: "Darken", 7: "Difference", 8: "Add",
    9: "Subtract", 10: "Invert", 11: "Alpha", 12: "Erase",
    13: "Overlay", 14: "HardLight",
}


@dataclass(frozen=True)
class ScalingGrid:
    character_id: int
    rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class FilterRecord:
    filter_id: int
    name: str
    raw: bytes


FILTER_NAMES = {
    0: "DropShadow", 1: "Blur", 2: "Glow", 3: "Bevel",
    4: "GradientGlow", 5: "Convolution", 6: "ColorMatrix",
    7: "GradientBevel",
}


def parse_scaling_grid(payload: bytes) -> ScalingGrid:
    if len(payload) < 3:
        raise ui_browser.PakError("DefineScalingGrid ist abgeschnitten")
    character_id = int.from_bytes(payload[0:2], "little")
    rect, end = ui_browser._read_rect(payload, 2)
    if end > len(payload):
        raise ui_browser.PakError("DefineScalingGrid-RECT ist abgeschnitten")
    return ScalingGrid(character_id, rect)


def _filter_end(payload: bytes, off: int, filter_id: int) -> int:
    fixed = {0: 23, 1: 9, 2: 15, 3: 27, 6: 80}
    if filter_id in fixed:
        end = off + fixed[filter_id]
    elif filter_id in (4, 7):
        if off >= len(payload):
            raise ui_browser.PakError("Gradient-Filter ist abgeschnitten")
        end = off + 1 + payload[off] * 5 + 19
    elif filter_id == 5:
        if off + 2 > len(payload):
            raise ui_browser.PakError("Convolution-Filter ist abgeschnitten")
        end = off + 15 + payload[off] * payload[off + 1] * 4
    else:
        raise ui_browser.PakError(f"Unbekannter SWF-Filter {filter_id}")
    if end > len(payload):
        raise ui_browser.PakError(f"{FILTER_NAMES.get(filter_id, 'Filter')} ist abgeschnitten")
    return end


def parse_filter_list(payload: bytes, off: int):
    if off >= len(payload):
        raise ui_browser.PakError("FilterList-Anzahl fehlt")
    count = payload[off]
    off += 1
    result = []
    for _ in range(count):
        if off >= len(payload):
            raise ui_browser.PakError("FilterList ist abgeschnitten")
        filter_id = payload[off]
        start = off
        off = _filter_end(payload, off + 1, filter_id)
        result.append(FilterRecord(
            filter_id,
            FILTER_NAMES.get(filter_id, f"Filter{filter_id}"),
            payload[start:off],
        ))
    return tuple(result), off


def parse_place_object3(payload: bytes):
    if len(payload) < 4:
        raise ui_browser.PakError("PlaceObject3 ist abgeschnitten")
    flags1, flags2 = payload[0], payload[1]
    p = 2
    depth = int.from_bytes(payload[p:p + 2], "little")
    p += 2
    has_character = bool(flags1 & 0x02)
    class_name = None
    if flags2 & 0x08 or (flags2 & 0x10 and has_character):
        class_name, p = ui_browser._read_c_string(payload, p)
    character_id = None
    if has_character:
        if p + 2 > len(payload):
            raise ui_browser.PakError("PlaceObject3-Character-ID fehlt")
        character_id = int.from_bytes(payload[p:p + 2], "little")
        p += 2
    matrix = color = name = clip_depth = None
    if flags1 & 0x04:
        matrix, p = ui_browser._read_matrix(payload, p)
    if flags1 & 0x08:
        color, p = ui_browser._read_color_transform(payload, p, True)
    ratio = None
    if flags1 & 0x10:
        if p + 2 > len(payload):
            raise ui_browser.PakError("PlaceObject3-Ratio fehlt")
        ratio = int.from_bytes(payload[p:p + 2], "little")
        p += 2
    if flags1 & 0x20:
        name, p = ui_browser._read_c_string(payload, p)
    if flags1 & 0x40:
        if p + 2 > len(payload):
            raise ui_browser.PakError("PlaceObject3-ClipDepth fehlt")
        clip_depth = int.from_bytes(payload[p:p + 2], "little")
        p += 2
    filters = ()
    if flags2 & 0x01:
        filters, p = parse_filter_list(payload, p)
    blend_mode = None
    if flags2 & 0x02:
        if p >= len(payload):
            raise ui_browser.PakError("PlaceObject3-BlendMode fehlt")
        blend_mode = payload[p]
        p += 1
    cache_as_bitmap = None
    if flags2 & 0x04:
        if p >= len(payload):
            raise ui_browser.PakError("PlaceObject3-CacheAsBitmap fehlt")
        cache_as_bitmap = payload[p]
        p += 1
    visible = None
    if flags2 & 0x20:
        if p >= len(payload):
            raise ui_browser.PakError("PlaceObject3-Visible fehlt")
        visible = bool(payload[p])
        p += 1
    opaque_background = None
    if flags2 & 0x40:
        if p + 4 > len(payload):
            raise ui_browser.PakError("PlaceObject3-OpaqueBackground fehlt")
        opaque_background = tuple(payload[p:p + 4])
        p += 4
    command = ui_browser.PlaceCommand(
        depth, bool(flags1 & 0x01), character_id, class_name,
        matrix, color, name, clip_depth, visible,
    )
    command.ratio = ratio
    command.filters = filters
    command.blend_mode = blend_mode
    command.cache_as_bitmap = cache_as_bitmap
    command.opaque_background = opaque_background
    command.place_object3_end = p
    command.place_object3_size = len(payload)
    return command


def _union_bounds(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return (
        min(left[0], right[0]), min(left[1], right[1]),
        max(left[2], right[2]), max(left[3], right[3]),
    )


def _transform_bounds(renderer, bounds, matrix):
    xmin, ymin, xmax, ymax = bounds
    points = [
        renderer._point(matrix, xmin, ymin), renderer._point(matrix, xmax, ymin),
        renderer._point(matrix, xmax, ymax), renderer._point(matrix, xmin, ymax),
    ]
    return (
        min(p[0] for p in points), min(p[1] for p in points),
        max(p[0] for p in points), max(p[1] for p in points),
    )


def _definition_bounds(renderer, character_id, stack):
    key = (id(renderer.movie), id(renderer.resolver), character_id)
    cache = getattr(renderer, "_ui_bounds_cache", None)
    if cache is None:
        renderer._ui_bounds_cache = {}
        cache = renderer._ui_bounds_cache
    if key in cache:
        return cache[key]
    if character_id in stack:
        return None
    definition = renderer.movie.definitions.get(character_id)
    result = None
    if isinstance(definition, ui_browser.SpriteDef):
        display = ui_browser.build_display_list(definition.tags, 1)
        for depth in sorted(display):
            item = display[depth]
            if item.visible:
                result = _union_bounds(
                    result,
                    _display_object_bounds(renderer, item, stack | {character_id}),
                )
    elif hasattr(ui_browser, "VectorShapeDef") and isinstance(definition, ui_browser.VectorShapeDef):
        result = tuple(getattr(definition, "edge_bounds", definition.bounds))
    elif isinstance(definition, (ui_browser.ShapeDef, ui_browser.EditTextDef)):
        result = tuple(definition.bounds)
    cache[key] = result
    return result


def _display_object_bounds(renderer, item, stack):
    bounds = None
    if item.class_name:
        try:
            lookup = renderer.resolver.get(item.class_name)
            if lookup.image is not None:
                bounds = (0.0, 0.0, float(lookup.image.width), float(lookup.image.height))
        except Exception:
            pass
    elif item.character_id is not None:
        bounds = _definition_bounds(renderer, item.character_id, stack)
    return None if bounds is None else _transform_bounds(renderer, bounds, item.matrix)


def _render_natural_sprite(renderer, definition, character_id, grid, stack, level):
    key = (id(renderer.movie), id(renderer.resolver), character_id)
    cached = _SCALE9_CACHE.get(key)
    if cached is not None and cached[0] is definition:
        return cached[1], cached[2], cached[3]
    bounds = _union_bounds(
        _definition_bounds(renderer, character_id, stack) or grid.rect,
        grid.rect,
    )
    left, top = math.floor(bounds[0]), math.floor(bounds[1])
    right, bottom = math.ceil(bounds[2]), math.ceil(bounds[3])
    image = PILImage.new(
        "RGBA", (max(1, right - left), max(1, bottom - top)),
        (0, 0, 0, 0),
    )
    display = ui_browser.build_display_list(definition.tags, 1)
    old_bounds, old_placeholders = renderer.show_bounds, renderer.show_placeholders
    renderer.show_bounds = renderer.show_placeholders = False
    try:
        renderer._draw_display(
            image, display,
            ui_browser.Affine(1, 0, 0, 1, -left, -top),
            ui_browser.IDENTITY_COLOR,
            stack | {character_id}, level + 1,
        )
    finally:
        renderer.show_bounds = old_bounds
        renderer.show_placeholders = old_placeholders
    int_bounds = (float(left), float(top), float(right), float(bottom))
    _SCALE9_CACHE[key] = (definition, image, int_bounds, grid.rect)
    return image, int_bounds, grid.rect


def _target_segments(total, first, last):
    total, first, last = max(1, int(total)), max(0, int(first)), max(0, int(last))
    fixed = first + last
    if fixed <= total:
        return first, total - fixed, last
    if fixed <= 0:
        return 0, total, 0
    first_out = max(0, min(total, int(round(total * first / fixed))))
    return first_out, 0, total - first_out


def scale9_resize(image, bounds, grid_rect, scale_x, scale_y):
    if PILImage is None:
        return image
    target_w = max(1, int(round(image.width * abs(float(scale_x)))))
    target_h = max(1, int(round(image.height * abs(float(scale_y)))))
    left, top, _right, _bottom = bounds
    gx0, gy0, gx1, gy1 = grid_rect
    x1 = max(0, min(image.width, int(round(gx0 - left))))
    x2 = max(x1, min(image.width, int(round(gx1 - left))))
    y1 = max(0, min(image.height, int(round(gy0 - top))))
    y2 = max(y1, min(image.height, int(round(gy1 - top))))
    src_x, src_y = (0, x1, x2, image.width), (0, y1, y2, image.height)
    out_l, out_c, _out_r = _target_segments(target_w, x1, image.width - x2)
    out_t, out_m, _out_b = _target_segments(target_h, y1, image.height - y2)
    dst_x, dst_y = (0, out_l, out_l + out_c, target_w), (0, out_t, out_t + out_m, target_h)
    result = PILImage.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    resampling = getattr(getattr(PILImage, "Resampling", PILImage), "BILINEAR")
    for row in range(3):
        for col in range(3):
            sw, sh = src_x[col + 1] - src_x[col], src_y[row + 1] - src_y[row]
            dw, dh = dst_x[col + 1] - dst_x[col], dst_y[row + 1] - dst_y[row]
            if min(sw, sh, dw, dh) <= 0:
                continue
            tile = image.crop((src_x[col], src_y[row], src_x[col + 1], src_y[row + 1]))
            if tile.size != (dw, dh):
                tile = tile.resize((dw, dh), resampling)
            result.alpha_composite(tile, (dst_x[col], dst_y[row]))
    transpose = getattr(PILImage, "Transpose", PILImage)
    if scale_x < 0:
        result = result.transpose(getattr(transpose, "FLIP_LEFT_RIGHT"))
    if scale_y < 0:
        result = result.transpose(getattr(transpose, "FLIP_TOP_BOTTOM"))
    return result


def _blend_channel(mode, s, d):
    if mode == 3:
        return (s * d + 127) // 255
    if mode == 4:
        return 255 - ((255 - s) * (255 - d) + 127) // 255
    if mode == 5:
        return max(s, d)
    if mode == 6:
        return min(s, d)
    if mode == 7:
        return abs(d - s)
    if mode == 8:
        return min(255, s + d)
    if mode == 9:
        return max(0, d - s)
    if mode == 10:
        return 255 - d
    if mode == 13:
        return (2 * s * d + 127) // 255 if d < 128 else 255 - (2 * (255 - s) * (255 - d) + 127) // 255
    if mode == 14:
        return (2 * s * d + 127) // 255 if s < 128 else 255 - (2 * (255 - s) * (255 - d) + 127) // 255
    return s


def blend_rgba(destination, source, mode):
    mode = int(mode or 0)
    if mode in (0, 1, 2):
        destination.alpha_composite(source)
        return destination
    bbox = source.getbbox()
    if bbox is None:
        return destination
    dst, src = destination.crop(bbox).convert("RGBA"), source.crop(bbox).convert("RGBA")
    d, s = dst.tobytes(), src.tobytes()
    out = bytearray(len(d))
    for i in range(0, len(d), 4):
        sr, sg, sb, sa8 = s[i:i + 4]
        dr, dg, db, da8 = d[i:i + 4]
        if mode == 11:
            out[i:i + 4] = bytes((dr, dg, db, (da8 * sa8 + 127) // 255))
            continue
        if mode == 12:
            out[i:i + 4] = bytes((dr, dg, db, (da8 * (255 - sa8) + 127) // 255))
            continue
        sa, da = sa8 / 255.0, da8 / 255.0
        ao = sa + da - sa * da
        if ao <= 0.0:
            continue
        blended = tuple(_blend_channel(mode, sc, dc) for sc, dc in zip((sr, sg, sb), (dr, dg, db)))
        for channel, (sc, dc, bc) in enumerate(zip((sr, sg, sb), (dr, dg, db), blended)):
            premul = (1.0 - sa) * dc * da + (1.0 - da) * sc * sa + sa * da * bc
            out[i + channel] = max(0, min(255, int(round(premul / ao))))
        out[i + 3] = max(0, min(255, int(round(ao * 255.0))))
    destination.paste(PILImage.frombytes("RGBA", dst.size, bytes(out)), bbox)
    return destination


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    if PILImage is None:
        return
    ui_browser._parse_place_object3 = parse_place_object3
    original_merge = ui_browser._merge_place

    def merge_place(old, command):
        result = original_merge(old, command)
        for attr, default in (
            ("ratio", None), ("filters", ()), ("blend_mode", 0),
            ("cache_as_bitmap", None), ("opaque_background", None),
        ):
            value = getattr(command, attr, None)
            if value is None or (attr == "filters" and not value):
                value = getattr(old, attr, default) if old is not None else default
            setattr(result, attr, value)
        return result

    ui_browser._merge_place = merge_place
    original_parse_swf = ui_browser.parse_swf_movie

    def parse_swf_movie(raw):
        movie = original_parse_swf(raw)
        grids, errors = {}, []
        for code, payload in movie.root_tags:
            if code == TAG_DEFINE_SCALING_GRID:
                try:
                    grid = parse_scaling_grid(payload)
                    grids[grid.character_id] = grid
                except Exception as exc:
                    errors.append(str(exc))
        movie.scaling_grids = grids
        movie.scaling_grid_errors = tuple(errors)
        return movie

    ui_browser.parse_swf_movie = parse_swf_movie
    base_draw = ui_browser.UIRenderer._draw_display

    def draw_display(self, canvas, display, parent_matrix, parent_color, stack, level):
        if level > 64:
            self.stats.recursion_skips += 1
            return
        grids = getattr(self.movie, "scaling_grids", {})
        for depth in sorted(display):
            item = display[depth]
            grid = grids.get(item.character_id)
            definition = self.movie.definitions.get(item.character_id) if item.character_id is not None else None
            matrix = item.matrix
            use_scale9 = (
                grid is not None and isinstance(definition, ui_browser.SpriteDef)
                and abs(matrix.b) < 1e-7 and abs(matrix.c) < 1e-7
                and (abs(abs(matrix.a) - 1.0) > 1e-5 or abs(abs(matrix.d) - 1.0) > 1e-5)
            )
            if not use_scale9:
                base_draw(self, canvas, {depth: item}, parent_matrix, parent_color, stack, level)
                continue
            if not item.visible:
                continue
            self.stats.placements += 1
            try:
                source, bounds, grid_rect = _render_natural_sprite(
                    self, definition, item.character_id, grid, stack, level,
                )
                image = scale9_resize(source, bounds, grid_rect, matrix.a, matrix.d)
                image = self._apply_color(image, parent_color.combine(item.color))
                x0 = min(matrix.tx + matrix.a * bounds[0], matrix.tx + matrix.a * bounds[2])
                y0 = min(matrix.ty + matrix.d * bounds[1], matrix.ty + matrix.d * bounds[3])
                image_matrix = parent_matrix.then(ui_browser.Affine(1, 0, 0, 1, x0, y0))
                ui_browser_shape_patch._draw_transformed_image(self, canvas, image, image_matrix)
                self.stats.scale9_placements = getattr(self.stats, "scale9_placements", 0) + 1
                if self.show_bounds:
                    self._draw_transformed_box(canvas, bounds, parent_matrix.then(matrix), f"Scale9 {item.character_id}")
            except Exception:
                self.stats.scale9_fallbacks = getattr(self.stats, "scale9_fallbacks", 0) + 1
                base_draw(self, canvas, {depth: item}, parent_matrix, parent_color, stack, level)

    ui_browser.UIRenderer._draw_display = draw_display

    def composite_ui_layer(self, canvas, layer, blend_mode=0):
        blend_rgba(canvas, layer, blend_mode)
        mode = int(blend_mode or 0)
        if mode not in (0, 1):
            counts = getattr(self.stats, "blend_modes", None)
            if counts is None:
                self.stats.blend_modes = {}
                counts = self.stats.blend_modes
            counts[mode] = counts.get(mode, 0) + 1

    ui_browser.UIRenderer._composite_ui_layer = composite_ui_layer
    ui_browser.TAG_DEFINE_SCALING_GRID = TAG_DEFINE_SCALING_GRID
    ui_browser.ScalingGrid = ScalingGrid
    ui_browser.FilterRecord = FilterRecord
    ui_browser.scale9_resize = scale9_resize
    ui_browser.blend_rgba = blend_rgba
    ui_browser.BLEND_NAMES = BLEND_NAMES
