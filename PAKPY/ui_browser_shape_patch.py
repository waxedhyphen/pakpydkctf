"""Decode and render Tropical Freeze's Scaleform DefineShape1-4 vectors.

This is the next static UI-viewer layer after GFXL image resolution. The supplied
UI corpus uses solid fills, padded linear gradients and solid line styles. Those
features are decoded from the SWF edge records and rasterized with Pillow. Curved
quadratic edges are adaptively flattened, even/odd fill contours are respected,
and the resulting local shape bitmap is transformed by the normal display-list
matrix and ColorTransform.

Unsupported fill types are retained as diagnostics/fallbacks instead of aborting
the rest of the movie. Raw GFX/SWF data is never changed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import ui_browser

try:
    from PIL import Image as PILImage, ImageChops, ImageDraw
except Exception:
    PILImage = None
    ImageChops = None
    ImageDraw = None


_INSTALLED = False
_RASTER_CACHE = {}
_GRADIENT_RADIUS_PIXELS = 16384.0 / 20.0


@dataclass(frozen=True)
class GradientStop:
    ratio: int
    color: tuple[int, int, int, int]


@dataclass(frozen=True)
class VectorFillStyle:
    kind: str
    color: tuple[int, int, int, int] = (255, 255, 255, 255)
    matrix: object | None = None
    stops: tuple[GradientStop, ...] = ()
    spread_mode: int = 0
    interpolation_mode: int = 0
    bitmap_id: int = 0
    fill_type: int = 0


@dataclass(frozen=True)
class VectorLineStyle:
    width: float
    color: tuple[int, int, int, int]
    fill: VectorFillStyle | None = None
    start_cap: int = 0
    end_cap: int = 0
    join_style: int = 0
    no_close: bool = False


@dataclass(frozen=True)
class VectorEdge:
    start: tuple[int, int]
    end: tuple[int, int]
    control: tuple[int, int] | None = None

    def reversed(self):
        return VectorEdge(self.end, self.start, self.control)


@dataclass
class VectorShapeDef:
    character_id: int
    bounds: tuple[float, float, float, float]
    edge_bounds: tuple[float, float, float, float]
    fills: tuple[VectorFillStyle | None, ...]
    lines: tuple[VectorLineStyle | None, ...]
    fill_edges: dict[int, tuple[VectorEdge, ...]]
    line_edges: dict[int, tuple[VectorEdge, ...]]
    uses_fill_winding_rule: bool = False
    unsupported_fill_types: tuple[int, ...] = ()
    record_count: int = 0


class ShapeParseError(ui_browser.PakError):
    pass


def _le16(data, off):
    if off + 2 > len(data):
        raise ShapeParseError("UI16 ist abgeschnitten")
    return int.from_bytes(data[off:off + 2], "little")


def _read_color(data, off, with_alpha):
    count = 4 if with_alpha else 3
    if off + count > len(data):
        raise ShapeParseError("Shape-Farbe ist abgeschnitten")
    values = tuple(data[off:off + count])
    if not with_alpha:
        values = values + (255,)
    return values, off + count


def _read_fill_style(data, off, version, unsupported):
    if off >= len(data):
        raise ShapeParseError("FillStyle-Typ fehlt")
    fill_type = data[off]
    off += 1
    with_alpha = version >= 3
    if fill_type == 0x00:
        color, off = _read_color(data, off, with_alpha)
        return VectorFillStyle("solid", color=color, fill_type=fill_type), off
    if fill_type in (0x10, 0x12, 0x13):
        matrix, off = ui_browser._read_matrix(data, off)
        if off >= len(data):
            raise ShapeParseError("Gradient-Header fehlt")
        flags = data[off]
        off += 1
        spread_mode = (flags >> 6) & 0x03
        interpolation_mode = (flags >> 4) & 0x03
        count = flags & 0x0F
        stops = []
        for _ in range(count):
            if off >= len(data):
                raise ShapeParseError("Gradient-Ratio fehlt")
            ratio = data[off]
            off += 1
            color, off = _read_color(data, off, with_alpha)
            stops.append(GradientStop(ratio, color))
        if fill_type == 0x13:
            if off + 2 > len(data):
                raise ShapeParseError("FocalGradient-Wert fehlt")
            off += 2
        kind = {0x10: "linear_gradient", 0x12: "radial_gradient", 0x13: "focal_gradient"}[fill_type]
        return VectorFillStyle(
            kind,
            matrix=matrix,
            stops=tuple(stops),
            spread_mode=spread_mode,
            interpolation_mode=interpolation_mode,
            fill_type=fill_type,
        ), off
    if fill_type in (0x40, 0x41, 0x42, 0x43):
        bitmap_id = _le16(data, off)
        off += 2
        matrix, off = ui_browser._read_matrix(data, off)
        return VectorFillStyle(
            "bitmap",
            matrix=matrix,
            bitmap_id=bitmap_id,
            fill_type=fill_type,
        ), off
    unsupported.add(fill_type)
    raise ShapeParseError(f"Unbekannter FillStyle 0x{fill_type:02X}")


def _read_style_count(data, off, allow_extended):
    if off >= len(data):
        raise ShapeParseError("Style-Anzahl fehlt")
    count = data[off]
    off += 1
    if count == 0xFF:
        if not allow_extended:
            raise ShapeParseError("Erweiterte Style-Anzahl in DefineShape1")
        count = _le16(data, off)
        off += 2
    return count, off


def _read_fill_array(data, off, version, unsupported):
    count, off = _read_style_count(data, off, version >= 2)
    result = []
    for _ in range(count):
        style, off = _read_fill_style(data, off, version, unsupported)
        result.append(style)
    return result, off


def _read_line_style(data, off, version, unsupported):
    width = _le16(data, off) / 20.0
    off += 2
    if version < 4:
        color, off = _read_color(data, off, version >= 3)
        return VectorLineStyle(width, color), off

    reader = ui_browser._BitReader(data, off)
    start_cap = reader.read_u(2)
    join_style = reader.read_u(2)
    has_fill = bool(reader.read_u(1))
    reader.read_u(1)
    reader.read_u(1)
    reader.read_u(1)
    reader.read_u(5)
    no_close = bool(reader.read_u(1))
    end_cap = reader.read_u(2)
    reader.align()
    off = reader.byte_pos
    if join_style == 2:
        if off + 2 > len(data):
            raise ShapeParseError("MiterLimitFactor fehlt")
        off += 2
    if has_fill:
        fill, off = _read_fill_style(data, off, version, unsupported)
        color = fill.color if fill.kind == "solid" else (fill.stops[0].color if fill.stops else (255, 255, 255, 255))
    else:
        fill = None
        color, off = _read_color(data, off, True)
    return VectorLineStyle(width, color, fill, start_cap, end_cap, join_style, no_close), off


def _read_line_array(data, off, version, unsupported):
    count, off = _read_style_count(data, off, version >= 2)
    result = []
    for _ in range(count):
        style, off = _read_line_style(data, off, version, unsupported)
        result.append(style)
    return result, off


def _style_index(raw_index, base):
    return 0 if raw_index == 0 else base + raw_index


def parse_vector_shape(payload, version):
    """Decode one DefineShape1-4 payload into vector styles and directed edges."""
    if len(payload) < 4:
        raise ShapeParseError("DefineShape ist abgeschnitten")
    character_id = _le16(payload, 0)
    bounds, off = ui_browser._read_rect(payload, 2)
    edge_bounds = bounds
    uses_fill_winding_rule = False
    if version == 4:
        edge_bounds, off = ui_browser._read_rect(payload, off)
        reader = ui_browser._BitReader(payload, off)
        reader.read_u(5)
        uses_fill_winding_rule = bool(reader.read_u(1))
        reader.read_u(1)
        reader.read_u(1)
        reader.align()
        off = reader.byte_pos

    unsupported = set()
    first_fills, off = _read_fill_array(payload, off, version, unsupported)
    first_lines, off = _read_line_array(payload, off, version, unsupported)
    fills = [None] + list(first_fills)
    lines = [None] + list(first_lines)
    fill_base = 0
    line_base = 0

    reader = ui_browser._BitReader(payload, off)
    num_fill_bits = reader.read_u(4)
    num_line_bits = reader.read_u(4)
    x = 0
    y = 0
    fill0 = 0
    fill1 = 0
    line = 0
    fill_edges = {}
    line_edges = {}
    record_count = 0

    def add_edge(style_map, style_index, edge):
        if style_index:
            style_map.setdefault(style_index, []).append(edge)

    while True:
        record_count += 1
        if reader.read_u(1):
            straight = bool(reader.read_u(1))
            nbits = reader.read_u(4) + 2
            start = (x, y)
            control = None
            if straight:
                if reader.read_u(1):
                    dx = reader.read_s(nbits)
                    dy = reader.read_s(nbits)
                elif reader.read_u(1):
                    dx = 0
                    dy = reader.read_s(nbits)
                else:
                    dx = reader.read_s(nbits)
                    dy = 0
                x += dx
                y += dy
            else:
                control_dx = reader.read_s(nbits)
                control_dy = reader.read_s(nbits)
                anchor_dx = reader.read_s(nbits)
                anchor_dy = reader.read_s(nbits)
                control = (x + control_dx, y + control_dy)
                x = control[0] + anchor_dx
                y = control[1] + anchor_dy
            edge = VectorEdge(start, (x, y), control)
            add_edge(fill_edges, fill0, edge)
            add_edge(fill_edges, fill1, edge.reversed())
            add_edge(line_edges, line, edge)
            continue

        flags = reader.read_u(5)
        if flags == 0:
            break
        if flags & 0x01:
            move_bits = reader.read_u(5)
            x = reader.read_s(move_bits) if move_bits else 0
            y = reader.read_s(move_bits) if move_bits else 0
        if flags & 0x02:
            fill0 = _style_index(reader.read_u(num_fill_bits), fill_base) if num_fill_bits else 0
        if flags & 0x04:
            fill1 = _style_index(reader.read_u(num_fill_bits), fill_base) if num_fill_bits else 0
        if flags & 0x08:
            line = _style_index(reader.read_u(num_line_bits), line_base) if num_line_bits else 0
        if flags & 0x10:
            reader.align()
            off = reader.byte_pos
            fill_base = len(fills) - 1
            line_base = len(lines) - 1
            new_fills, off = _read_fill_array(payload, off, version, unsupported)
            new_lines, off = _read_line_array(payload, off, version, unsupported)
            fills.extend(new_fills)
            lines.extend(new_lines)
            reader = ui_browser._BitReader(payload, off)
            num_fill_bits = reader.read_u(4)
            num_line_bits = reader.read_u(4)

    return VectorShapeDef(
        character_id=character_id,
        bounds=bounds,
        edge_bounds=edge_bounds,
        fills=tuple(fills),
        lines=tuple(lines),
        fill_edges={key: tuple(value) for key, value in fill_edges.items()},
        line_edges={key: tuple(value) for key, value in line_edges.items()},
        uses_fill_winding_rule=uses_fill_winding_rule,
        unsupported_fill_types=tuple(sorted(unsupported)),
        record_count=record_count,
    )


def _edge_points(edge, steps_scale=1.0):
    x0, y0 = edge.start
    x1, y1 = edge.end
    if edge.control is None:
        return [(x0 / 20.0, y0 / 20.0), (x1 / 20.0, y1 / 20.0)]
    cx, cy = edge.control
    estimate = (math.hypot(cx - x0, cy - y0) + math.hypot(x1 - cx, y1 - cy)) / 20.0
    steps = max(3, min(48, int(math.ceil(estimate * max(1.0, steps_scale) / 5.0))))
    result = []
    for index in range(steps + 1):
        t = index / float(steps)
        inv = 1.0 - t
        x = inv * inv * x0 + 2.0 * inv * t * cx + t * t * x1
        y = inv * inv * y0 + 2.0 * inv * t * cy + t * t * y1
        result.append((x / 20.0, y / 20.0))
    return result


def _join_edges(edges):
    remaining = list(edges)
    by_start = {}
    for index, edge in enumerate(remaining):
        by_start.setdefault(edge.start, []).append(index)
    used = set()
    paths = []
    for start_index, first in enumerate(remaining):
        if start_index in used:
            continue
        used.add(start_index)
        chain = [first]
        end = first.end
        while True:
            candidate = None
            for index in by_start.get(end, ()):
                if index not in used:
                    candidate = index
                    break
            if candidate is None:
                break
            used.add(candidate)
            edge = remaining[candidate]
            chain.append(edge)
            end = edge.end
            if end == chain[0].start:
                break
        paths.append(chain)
    return paths


def _sample_path(chain, supersample):
    result = []
    for edge_index, edge in enumerate(chain):
        points = _edge_points(edge, supersample)
        if edge_index:
            points = points[1:]
        result.extend(points)
    return result


def _interpolate_color(stops, ratio):
    if not stops:
        return (255, 255, 255, 255)
    ordered = sorted(stops, key=lambda item: item.ratio)
    if ratio <= ordered[0].ratio:
        return ordered[0].color
    if ratio >= ordered[-1].ratio:
        return ordered[-1].color
    for left, right in zip(ordered, ordered[1:]):
        if left.ratio <= ratio <= right.ratio:
            span = max(1, right.ratio - left.ratio)
            t = (ratio - left.ratio) / float(span)
            return tuple(int(round(a + (b - a) * t)) for a, b in zip(left.color, right.color))
    return ordered[-1].color


def _gradient_strip(style):
    image = PILImage.new("RGBA", (256, 2))
    row = [_interpolate_color(style.stops, x) for x in range(256)]
    image.putdata(row + row)
    return image


def _mask_for_paths(size, paths, origin, supersample, winding):
    if ImageDraw is None:
        return None
    if winding or ImageChops is None:
        mask = PILImage.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        for chain in paths:
            points = _sample_path(chain, supersample)
            if len(points) < 3:
                continue
            scaled = [((x - origin[0]) * supersample, (y - origin[1]) * supersample) for x, y in points]
            draw.polygon(scaled, fill=255)
        return mask

    mask_1 = PILImage.new("1", size, 0)
    for chain in paths:
        points = _sample_path(chain, supersample)
        if len(points) < 3:
            continue
        scaled = [((x - origin[0]) * supersample, (y - origin[1]) * supersample) for x, y in points]
        contour = PILImage.new("1", size, 0)
        ImageDraw.Draw(contour).polygon(scaled, fill=1)
        mask_1 = ImageChops.logical_xor(mask_1, contour)
    return mask_1.convert("L")


def _gradient_layer(style, size, origin, supersample):
    if not style.stops or style.matrix is None:
        return PILImage.new("RGBA", size, style.color)
    if style.kind != "linear_gradient":
        return PILImage.new("RGBA", size, _interpolate_color(style.stops, 128))
    inverse = style.matrix.inverse_pillow()
    if inverse is None:
        return PILImage.new("RGBA", size, _interpolate_color(style.stops, 128))
    ia, ib, ic, _id, _ie, _iff = inverse
    strip = _gradient_strip(style)
    source_scale = 255.0 / (2.0 * _GRADIENT_RADIUS_PIXELS)
    a = ia * source_scale / supersample
    b = ib * source_scale / supersample
    c = (ia * origin[0] + ib * origin[1] + ic) * source_scale + 127.5
    transform_mode = getattr(getattr(PILImage, "Transform", PILImage), "AFFINE")
    resampling = getattr(getattr(PILImage, "Resampling", PILImage), "BILINEAR")
    return strip.transform(size, transform_mode, (a, b, c, 0.0, 0.0, 0.5), resample=resampling)


def _apply_mask(layer, mask):
    alpha = layer.getchannel("A")
    if ImageChops is not None:
        alpha = ImageChops.multiply(alpha, mask)
    else:
        alpha = mask
    layer.putalpha(alpha)
    return layer


def _rasterize_shape(definition, supersample=2):
    if PILImage is None or ImageDraw is None:
        raise ShapeParseError("Pillow fehlt für Vektor-Shapes")
    max_line = max((line.width for line in definition.lines[1:] if line is not None), default=0.0)
    pad = max(2.0, max_line * 0.6 + 1.0)
    xmin, ymin, xmax, ymax = definition.edge_bounds
    origin_x = math.floor(xmin - pad)
    origin_y = math.floor(ymin - pad)
    width = max(1, int(math.ceil(xmax + pad - origin_x)))
    height = max(1, int(math.ceil(ymax + pad - origin_y)))
    high_size = (max(1, width * supersample), max(1, height * supersample))
    canvas = PILImage.new("RGBA", high_size, (0, 0, 0, 0))

    for style_index in sorted(definition.fill_edges):
        if style_index <= 0 or style_index >= len(definition.fills):
            continue
        style = definition.fills[style_index]
        if style is None:
            continue
        paths = _join_edges(definition.fill_edges[style_index])
        mask = _mask_for_paths(high_size, paths, (origin_x, origin_y), supersample, definition.uses_fill_winding_rule)
        if mask is None or mask.getbbox() is None:
            continue
        if style.kind == "solid":
            layer = PILImage.new("RGBA", high_size, style.color)
        elif style.kind.endswith("gradient"):
            layer = _gradient_layer(style, high_size, (origin_x, origin_y), supersample)
        else:
            layer = PILImage.new("RGBA", high_size, (190, 80, 190, 100))
        canvas.alpha_composite(_apply_mask(layer, mask))

    draw = ImageDraw.Draw(canvas, "RGBA")
    for style_index in sorted(definition.line_edges):
        if style_index <= 0 or style_index >= len(definition.lines):
            continue
        style = definition.lines[style_index]
        if style is None:
            continue
        width_px = max(1, int(round(style.width * supersample)))
        for chain in _join_edges(definition.line_edges[style_index]):
            points = _sample_path(chain, supersample)
            if len(points) < 2:
                continue
            scaled = [((x - origin_x) * supersample, (y - origin_y) * supersample) for x, y in points]
            try:
                draw.line(scaled, fill=style.color, width=width_px, joint="curve")
            except TypeError:
                draw.line(scaled, fill=style.color, width=width_px)

    if supersample > 1:
        resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS")
        canvas = canvas.resize((width, height), resampling)
    return canvas, (float(origin_x), float(origin_y))


def _cached_shape(definition):
    key = id(definition)
    cached = _RASTER_CACHE.get(key)
    if cached is not None and cached[0] is definition:
        return cached[1], cached[2]
    image, origin = _rasterize_shape(definition)
    _RASTER_CACHE[key] = (definition, image, origin)
    return image, origin


def _draw_transformed_image(renderer, canvas, image, matrix):
    inverse = matrix.inverse_pillow()
    if inverse is None:
        return
    corners = [
        renderer._point(matrix, 0, 0),
        renderer._point(matrix, image.width, 0),
        renderer._point(matrix, image.width, image.height),
        renderer._point(matrix, 0, image.height),
    ]
    left = max(0, int(math.floor(min(point[0] for point in corners))))
    top = max(0, int(math.floor(min(point[1] for point in corners))))
    right = min(canvas.width, int(math.ceil(max(point[0] for point in corners))))
    bottom = min(canvas.height, int(math.ceil(max(point[1] for point in corners))))
    if right <= left or bottom <= top:
        return
    ia, ib, ic, id_, ie, iff = inverse
    crop_inverse = (ia, ib, ia * left + ib * top + ic, id_, ie, id_ * left + ie * top + iff)
    transform_mode = getattr(getattr(PILImage, "Transform", PILImage), "AFFINE")
    resampling = getattr(getattr(PILImage, "Resampling", PILImage), "BILINEAR")
    transformed = image.transform((right - left, bottom - top), transform_mode, crop_inverse, resample=resampling)
    canvas.alpha_composite(transformed, (left, top))


def _draw_vector_shape(renderer, canvas, definition, matrix, color):
    renderer.stats.shapes_drawn += 1
    image, origin = _cached_shape(definition)
    image = renderer._apply_color(image, color)
    local = ui_browser.Affine(1, 0, 0, 1, origin[0], origin[1])
    image_matrix = matrix.then(local)
    _draw_transformed_image(renderer, canvas, image, image_matrix)
    if renderer.show_bounds:
        renderer._draw_transformed_box(canvas, definition.bounds, matrix, f"Shape {definition.character_id}")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_parse_swf = ui_browser.parse_swf_movie

    def parse_swf_movie(raw):
        movie = original_parse_swf(raw)
        tag_versions = {
            ui_browser.TAG_DEFINE_SHAPE: 1,
            ui_browser.TAG_DEFINE_SHAPE2: 2,
            ui_browser.TAG_DEFINE_SHAPE3: 3,
            ui_browser.TAG_DEFINE_SHAPE4: 4,
        }
        errors = []
        vector_count = 0
        for code, payload in movie.root_tags:
            version = tag_versions.get(code)
            if version is None:
                continue
            try:
                definition = parse_vector_shape(payload, version)
                movie.definitions[definition.character_id] = definition
                vector_count += 1
            except Exception as exc:
                errors.append(str(exc))
        movie.vector_shape_count = vector_count
        movie.vector_shape_errors = tuple(errors)
        return movie

    ui_browser.parse_swf_movie = parse_swf_movie

    def draw_display(self, canvas, display, parent_matrix, parent_color, stack, level):
        if level > 64:
            self.stats.recursion_skips += 1
            return
        for depth in sorted(display):
            item = display[depth]
            if not item.visible:
                continue
            self.stats.placements += 1
            matrix = parent_matrix.then(item.matrix)
            color = parent_color.combine(item.color)
            if item.class_name:
                try:
                    self._draw_external(canvas, item.class_name, matrix, color, item.name)
                except TypeError:
                    self._draw_external(canvas, item.class_name, matrix, color)
                continue
            if item.character_id is None:
                if self.show_placeholders:
                    self._draw_placeholder(canvas, matrix, item.name or f"depth {depth}", (120, 120, 120, 150))
                continue
            definition = self.movie.definitions.get(item.character_id)
            if isinstance(definition, ui_browser.SpriteDef):
                if item.character_id in stack:
                    self.stats.recursion_skips += 1
                    continue
                child = ui_browser.build_display_list(definition.tags, 1)
                self._draw_display(canvas, child, matrix, color, stack | {item.character_id}, level + 1)
            elif isinstance(definition, ui_browser.EditTextDef):
                self._draw_edit_text(canvas, definition, matrix, color)
            elif isinstance(definition, VectorShapeDef):
                _draw_vector_shape(self, canvas, definition, matrix, color)
            elif isinstance(definition, ui_browser.ShapeDef):
                self._draw_shape(canvas, definition, matrix)
            elif self.show_placeholders:
                self._draw_placeholder(canvas, matrix, item.name or f"char {item.character_id}", (100, 90, 130, 145))

    ui_browser.UIRenderer._draw_display = draw_display
    ui_browser.VectorShapeDef = VectorShapeDef
    ui_browser.parse_vector_shape = parse_vector_shape
