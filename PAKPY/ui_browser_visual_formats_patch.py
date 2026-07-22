"""Integrate morph shapes, embedded bitmap fills, full gradients and Scale9 hit mapping.

Installed after the EditText stage.  The patch is preview-only: source SWF/GFX/PAK
bytes are never modified.  All parsers, caches and raster allocations are bounded.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import copy
import math

import ui_browser
import ui_browser_hit_geometry as hit_geometry
import ui_browser_hit_geometry_base as hit_base
import ui_browser_precise_hit as precise
import ui_browser_scale9_blend_patch as scale9
import ui_browser_shape_patch as shape_patch
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as overrides_patch
import ui_browser_visual_formats as visual

try:
    from PIL import Image as PILImage, ImageDraw
except Exception:
    PILImage = None
    ImageDraw = None


_INSTALLED = False
_BASE = {}
_MORPH_CACHE = OrderedDict()
_MORPH_CACHE_MAX = 512
_GRADIENT_CACHE = OrderedDict()
_GRADIENT_CACHE_MAX_BYTES = 32 * 1024 * 1024
_GRADIENT_CACHE_BYTES = 0
_RESOURCE_RASTER_CACHE = OrderedDict()
_RESOURCE_RASTER_MAX_BYTES = 128 * 1024 * 1024
_RESOURCE_RASTER_BYTES = 0
_MAX_RASTER_DIMENSION = 8192
_MAX_RASTER_PIXELS = 32_000_000


def parse_place_object2(payload: bytes):
    if len(payload) < 3:
        raise ui_browser.PakError("PlaceObject2 ist abgeschnitten")
    flags = payload[0]
    p = 1
    depth = int.from_bytes(payload[p:p + 2], "little")
    p += 2
    character_id = matrix = color = name = clip_depth = ratio = None
    if flags & 0x02:
        if p + 2 > len(payload):
            raise ui_browser.PakError("PlaceObject2-Character-ID fehlt")
        character_id = int.from_bytes(payload[p:p + 2], "little")
        p += 2
    if flags & 0x04:
        matrix, p = ui_browser._read_matrix(payload, p)
    if flags & 0x08:
        color, p = ui_browser._read_color_transform(payload, p, True)
    if flags & 0x10:
        if p + 2 > len(payload):
            raise ui_browser.PakError("PlaceObject2-Ratio fehlt")
        ratio = int.from_bytes(payload[p:p + 2], "little")
        p += 2
    if flags & 0x20:
        name, p = ui_browser._read_c_string(payload, p)
    if flags & 0x40:
        if p + 2 > len(payload):
            raise ui_browser.PakError("PlaceObject2-ClipDepth fehlt")
        clip_depth = int.from_bytes(payload[p:p + 2], "little")
        p += 2
    command = ui_browser.PlaceCommand(
        depth, bool(flags & 0x01), character_id, None,
        matrix, color, name, clip_depth,
    )
    command.ratio = ratio
    command.place_object2_end = p
    command.place_object2_size = len(payload)
    return command


def parse_swf_movie(raw):
    movie = _BASE["parse"](raw)
    bitmap_defs, bitmap_errors = visual.parse_embedded_bitmaps(movie.root_tags)
    movie.definitions.update(bitmap_defs)

    morph_count = 0
    morph_errors = []
    warnings = []
    for code, payload in movie.root_tags:
        version = 1 if code == visual.TAG_DEFINE_MORPH_SHAPE else (
            2 if code == visual.TAG_DEFINE_MORPH_SHAPE2 else 0
        )
        if not version:
            continue
        try:
            definition = visual.parse_morph_shape(payload, version)
            movie.definitions[definition.character_id] = definition
            morph_count += 1
            for warning in definition.parse_warnings:
                warnings.append({
                    "character_id": definition.character_id,
                    "warning": warning,
                })
        except Exception as exc:
            morph_errors.append(str(exc))

    movie.ui_embedded_bitmap_count = len(bitmap_defs)
    movie.ui_embedded_bitmap_errors = tuple(bitmap_errors)
    movie.ui_morph_shape_count = morph_count
    movie.ui_morph_shape_errors = tuple(morph_errors)
    movie.ui_morph_shape_warnings = tuple(warnings)
    movie.ui_visual_format_revision = 0
    return movie


def _morph_vector(definition, ratio):
    ratio = max(0, min(65535, int(ratio or 0)))
    key = (id(definition), ratio)
    cached = _MORPH_CACHE.get(key)
    if cached is not None and cached[0] is definition:
        _MORPH_CACHE.move_to_end(key)
        return cached[1]
    value = visual.interpolate_morph(definition, ratio)
    _MORPH_CACHE[key] = (definition, value)
    _MORPH_CACHE.move_to_end(key)
    while len(_MORPH_CACHE) > _MORPH_CACHE_MAX:
        _MORPH_CACHE.popitem(last=False)
    return value


def _synthetic_morph_id(movie, definition, ratio):
    stores = getattr(movie, "_ui_morph_synthetic", None)
    if not isinstance(stores, dict):
        stores = {"ids": OrderedDict(), "next": -2_000_000_000}
        movie._ui_morph_synthetic = stores
    ids = stores.get("ids")
    if not isinstance(ids, OrderedDict):
        ids = OrderedDict(ids or {})
        stores["ids"] = ids
    key = (int(definition.character_id), int(ratio or 0))
    character_id = ids.get(key)
    if character_id is None:
        character_id = int(stores["next"])
        stores["next"] = character_id + 1
        ids[key] = character_id
    else:
        ids.move_to_end(key)
    movie.definitions[character_id] = _morph_vector(definition, ratio)
    while len(ids) > 512:
        _old_key, old_id = ids.popitem(last=False)
        movie.definitions.pop(old_id, None)
    return character_id


def _prepare_morph_display(renderer, display):
    changed = False
    result = dict(display)
    for depth, item in tuple(result.items()):
        definition = renderer.movie.definitions.get(getattr(item, "character_id", None))
        if not isinstance(definition, visual.MorphShapeDef):
            continue
        clone = copy.copy(item)
        ratio = max(0, min(65535, int(getattr(item, "ratio", 0) or 0)))
        clone._ui_morph_character_id = definition.character_id
        clone._ui_morph_ratio = ratio
        clone.character_id = _synthetic_morph_id(renderer.movie, definition, ratio)
        result[depth] = clone
        changed = True
        renderer.stats.morph_placements = getattr(renderer.stats, "morph_placements", 0) + 1
    return result if changed else display


def draw_display(renderer, canvas, display, parent_matrix, parent_color, stack, level):
    return _BASE["draw_display"](
        renderer, canvas, _prepare_morph_display(renderer, display),
        parent_matrix, parent_color, stack, level,
    )


def _linear_channel(value):
    value = max(0.0, min(1.0, float(value) / 255.0))
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _srgb_channel(value):
    value = max(0.0, min(1.0, float(value)))
    value = value * 12.92 if value <= 0.0031308 else 1.055 * (value ** (1.0 / 2.4)) - 0.055
    return max(0, min(255, int(round(value * 255.0))))


def _gradient_color(style, ratio):
    stops = sorted(tuple(style.stops or ()), key=lambda item: item.ratio)
    if not stops:
        return (255, 255, 255, 255)
    ratio = max(0.0, min(255.0, float(ratio)))
    if ratio <= stops[0].ratio:
        return stops[0].color
    if ratio >= stops[-1].ratio:
        return stops[-1].color
    for left, right in zip(stops, stops[1:]):
        if left.ratio <= ratio <= right.ratio:
            span = max(1.0, float(right.ratio - left.ratio))
            t = (ratio - left.ratio) / span
            if int(getattr(style, "interpolation_mode", 0) or 0) == 1:
                rgb = [
                    _srgb_channel(_linear_channel(a) + (_linear_channel(b) - _linear_channel(a)) * t)
                    for a, b in zip(left.color[:3], right.color[:3])
                ]
                alpha = int(round(left.color[3] + (right.color[3] - left.color[3]) * t))
                return tuple(rgb + [max(0, min(255, alpha))])
            return tuple(
                max(0, min(255, int(round(a + (b - a) * t))))
                for a, b in zip(left.color, right.color)
            )
    return stops[-1].color


def _gradient_key(style):
    return (
        str(style.kind),
        tuple((int(stop.ratio), tuple(stop.color)) for stop in style.stops),
        int(getattr(style, "spread_mode", 0) or 0),
        int(getattr(style, "interpolation_mode", 0) or 0),
        round(float(getattr(style, "focal_point", 0.0) or 0.0), 6),
    )


def _gradient_source(style):
    global _GRADIENT_CACHE_BYTES
    if PILImage is None:
        return None
    key = _gradient_key(style)
    cached = _GRADIENT_CACHE.get(key)
    if cached is not None:
        _GRADIENT_CACHE.move_to_end(key)
        return cached
    size = 512
    half = size / 2.0
    pixels = []
    focal = float(getattr(style, "focal_point", 0.0) or 0.0)
    spread = int(getattr(style, "spread_mode", 0) or 0)
    for y in range(size):
        ny = ((y + 0.5) - half) / half
        for x in range(size):
            nx = ((x + 0.5) - half) / half
            value = visual.gradient_parameter(style.kind, nx, ny, focal)
            value = visual.spread_unit(value, spread)
            pixels.append(_gradient_color(style, value * 255.0))
    image = PILImage.new("RGBA", (size, size))
    image.putdata(pixels)
    _GRADIENT_CACHE[key] = image
    _GRADIENT_CACHE.move_to_end(key)
    _GRADIENT_CACHE_BYTES += size * size * 4
    while _GRADIENT_CACHE and _GRADIENT_CACHE_BYTES > _GRADIENT_CACHE_MAX_BYTES:
        _old_key, old = _GRADIENT_CACHE.popitem(last=False)
        _GRADIENT_CACHE_BYTES -= old.width * old.height * 4
    return image


def gradient_layer(style, size, origin, supersample):
    if PILImage is None:
        raise ui_browser.PakError("Pillow fehlt für Gradients")
    if not style.stops or style.matrix is None:
        return PILImage.new("RGBA", size, style.color)
    source = _gradient_source(style)
    inverse = style.matrix.inverse_pillow()
    if source is None or inverse is None:
        return PILImage.new("RGBA", size, _gradient_color(style, 128))
    ia, ib, ic, id_, ie, iff = inverse
    half = (source.width - 1) * 0.5
    factor = half / float(shape_patch._GRADIENT_RADIUS_PIXELS)
    a = ia * factor / supersample
    b = ib * factor / supersample
    c = (ia * origin[0] + ib * origin[1] + ic) * factor + half
    d = id_ * factor / supersample
    e = ie * factor / supersample
    f = (id_ * origin[0] + ie * origin[1] + iff) * factor + half
    transform_mode = getattr(getattr(PILImage, "Transform", PILImage), "AFFINE")
    resampling = getattr(getattr(PILImage, "Resampling", PILImage), "BILINEAR")
    return source.transform(size, transform_mode, (a, b, c, d, e, f), resample=resampling)


def _bitmap_definition(renderer, bitmap_id):
    value = renderer.movie.definitions.get(int(bitmap_id or 0))
    return value if isinstance(value, visual.EmbeddedBitmapDef) else None


def _bitmap_layer(renderer, style, size, origin, supersample):
    if PILImage is None:
        raise ui_browser.PakError("Pillow fehlt für Bitmap-Fills")
    definition = _bitmap_definition(renderer, style.bitmap_id)
    if definition is None or style.matrix is None:
        renderer.stats.missing_bitmap_fills = getattr(renderer.stats, "missing_bitmap_fills", 0) + 1
        return PILImage.new("RGBA", size, (190, 80, 190, 100))
    image = definition.image
    inverse = style.matrix.inverse_pillow()
    if inverse is None:
        return PILImage.new("RGBA", size, (190, 80, 190, 100))
    ia, ib, ic, id_, ie, iff = inverse
    affine = (
        ia / supersample, ib / supersample,
        ia * origin[0] + ib * origin[1] + ic,
        id_ / supersample, ie / supersample,
        id_ * origin[0] + ie * origin[1] + iff,
    )
    repeated = int(style.fill_type) in (0x40, 0x42)
    smoothed = int(style.fill_type) in (0x40, 0x41)
    source = image
    if repeated:
        corners = (
            (0.0, 0.0), (float(size[0]), 0.0),
            (float(size[0]), float(size[1])), (0.0, float(size[1])),
        )
        mapped = [
            (
                affine[0] * x + affine[1] * y + affine[2],
                affine[3] * x + affine[4] * y + affine[5],
            )
            for x, y in corners
        ]
        left = math.floor(min(value[0] for value in mapped) / image.width) * image.width
        top = math.floor(min(value[1] for value in mapped) / image.height) * image.height
        right = math.ceil(max(value[0] for value in mapped) / image.width) * image.width + image.width
        bottom = math.ceil(max(value[1] for value in mapped) / image.height) * image.height + image.height
        width = max(1, int(right - left))
        height = max(1, int(bottom - top))
        tile_count = (
            ((width + image.width - 1) // image.width)
            * ((height + image.height - 1) // image.height)
        )
        if (
            width <= _MAX_RASTER_DIMENSION
            and height <= _MAX_RASTER_DIMENSION
            and width * height <= _MAX_RASTER_PIXELS
            and tile_count <= 65_536
        ):
            source = PILImage.new("RGBA", (width, height), (0, 0, 0, 0))
            for y in range(0, height, image.height):
                for x in range(0, width, image.width):
                    source.alpha_composite(image, (x, y))
            affine = (
                affine[0], affine[1], affine[2] - left,
                affine[3], affine[4], affine[5] - top,
            )
        else:
            renderer.stats.bitmap_repeat_fallbacks = getattr(renderer.stats, "bitmap_repeat_fallbacks", 0) + 1
            return PILImage.new("RGBA", size, (190, 80, 190, 100))
    transform_mode = getattr(getattr(PILImage, "Transform", PILImage), "AFFINE")
    resampling_group = getattr(PILImage, "Resampling", PILImage)
    resampling = getattr(resampling_group, "BILINEAR" if smoothed else "NEAREST")
    renderer.stats.bitmap_fills = getattr(renderer.stats, "bitmap_fills", 0) + 1
    return source.transform(size, transform_mode, affine, resample=resampling)


def _resource_raster_key(renderer, definition):
    bitmap_tokens = []
    for style in tuple(definition.fills[1:] if len(definition.fills) > 1 else ()):
        if style is None or style.kind != "bitmap":
            continue
        bitmap = _bitmap_definition(renderer, style.bitmap_id)
        bitmap_tokens.append((
            int(style.bitmap_id), id(getattr(bitmap, "image", None)),
        ))
    return id(definition), tuple(bitmap_tokens)


def _resource_raster_get(renderer, definition):
    key = _resource_raster_key(renderer, definition)
    cached = _RESOURCE_RASTER_CACHE.get(key)
    if cached is not None and cached[0] is definition:
        _RESOURCE_RASTER_CACHE.move_to_end(key)
        return cached[1], cached[2]
    return None


def _resource_raster_put(renderer, definition, image, origin):
    global _RESOURCE_RASTER_BYTES
    key = _resource_raster_key(renderer, definition)
    previous = _RESOURCE_RASTER_CACHE.pop(key, None)
    if previous is not None:
        _RESOURCE_RASTER_BYTES -= previous[1].width * previous[1].height * 4
    _RESOURCE_RASTER_CACHE[key] = (definition, image, origin)
    _RESOURCE_RASTER_CACHE.move_to_end(key)
    _RESOURCE_RASTER_BYTES += image.width * image.height * 4
    while _RESOURCE_RASTER_CACHE and _RESOURCE_RASTER_BYTES > _RESOURCE_RASTER_MAX_BYTES:
        _old_key, old = _RESOURCE_RASTER_CACHE.popitem(last=False)
        _RESOURCE_RASTER_BYTES -= old[1].width * old[1].height * 4


def _rasterize_with_resources(renderer, definition, supersample=2):
    cached = _resource_raster_get(renderer, definition)
    if cached is not None:
        return cached
    if PILImage is None or ImageDraw is None:
        raise ui_browser.PakError("Pillow fehlt für Vektor-Shapes")
    max_line = max((line.width for line in definition.lines[1:] if line is not None), default=0.0)
    pad = max(2.0, max_line * 0.6 + 1.0)
    xmin, ymin, xmax, ymax = definition.edge_bounds
    origin_x = math.floor(xmin - pad)
    origin_y = math.floor(ymin - pad)
    width = max(1, int(math.ceil(xmax + pad - origin_x)))
    height = max(1, int(math.ceil(ymax + pad - origin_y)))
    if width > _MAX_RASTER_DIMENSION or height > _MAX_RASTER_DIMENSION or width * height > _MAX_RASTER_PIXELS:
        raise ui_browser.PakError("Shape-Raster überschreitet das Sicherheitslimit")
    high_size = (max(1, width * supersample), max(1, height * supersample))
    if high_size[0] > _MAX_RASTER_DIMENSION or high_size[1] > _MAX_RASTER_DIMENSION:
        supersample = 1
        high_size = (width, height)
    canvas = PILImage.new("RGBA", high_size, (0, 0, 0, 0))

    for style_index in sorted(definition.fill_edges):
        if style_index <= 0 or style_index >= len(definition.fills):
            continue
        style = definition.fills[style_index]
        if style is None:
            continue
        paths = shape_patch._join_edges(definition.fill_edges[style_index])
        mask = shape_patch._mask_for_paths(
            high_size, paths, (origin_x, origin_y), supersample,
            definition.uses_fill_winding_rule,
        )
        if mask is None or mask.getbbox() is None:
            continue
        if style.kind == "solid":
            layer = PILImage.new("RGBA", high_size, style.color)
        elif style.kind.endswith("gradient"):
            layer = gradient_layer(style, high_size, (origin_x, origin_y), supersample)
        elif style.kind == "bitmap":
            layer = _bitmap_layer(renderer, style, high_size, (origin_x, origin_y), supersample)
        else:
            layer = PILImage.new("RGBA", high_size, (190, 80, 190, 100))
        canvas.alpha_composite(shape_patch._apply_mask(layer, mask))

    draw = ImageDraw.Draw(canvas, "RGBA")
    for style_index in sorted(definition.line_edges):
        if style_index <= 0 or style_index >= len(definition.lines):
            continue
        style = definition.lines[style_index]
        if style is None:
            continue
        width_px = max(1, int(round(style.width * supersample)))
        for chain in shape_patch._join_edges(definition.line_edges[style_index]):
            points = shape_patch._sample_path(chain, supersample)
            if len(points) < 2:
                continue
            scaled = [
                ((x - origin_x) * supersample, (y - origin_y) * supersample)
                for x, y in points
            ]
            try:
                draw.line(scaled, fill=style.color, width=width_px, joint="curve")
            except TypeError:
                draw.line(scaled, fill=style.color, width=width_px)

    if supersample > 1:
        resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS")
        canvas = canvas.resize((width, height), resampling)
    origin = (float(origin_x), float(origin_y))
    _resource_raster_put(renderer, definition, canvas, origin)
    return canvas, origin


def draw_vector_shape(renderer, canvas, definition, matrix, color):
    renderer.stats.shapes_drawn += 1
    image, origin = _rasterize_with_resources(renderer, definition)
    image = renderer._apply_color(image, color)
    local = ui_browser.Affine(1, 0, 0, 1, origin[0], origin[1])
    shape_patch._draw_transformed_image(renderer, canvas, image, matrix.then(local))
    if renderer.show_bounds:
        renderer._draw_transformed_box(
            canvas, definition.bounds, matrix, f"Shape {definition.character_id}",
        )


@dataclass(frozen=True)
class Scale9MappedGeometry:
    path: str
    kind: str
    bounds: tuple[float, float, float, float]
    natural: object
    outer_clips: tuple
    parent_inverse: tuple[float, float, float, float, float, float] | None
    x0: float
    y0: float
    source_bounds: tuple[float, float, float, float]
    grid_rect: tuple[float, float, float, float]
    target_width: float
    target_height: float
    flip_x: bool = False
    flip_y: bool = False
    character_id: int | None = None
    inverse: object | None = None
    local_bounds: object | None = None
    alpha: object | None = None
    alpha_origin: tuple[float, float] = (0.0, 0.0)
    clips: tuple = ()

    def local_point(self, point):
        if self.parent_inverse is None:
            return point
        ia, ib, ic, id_, ie, iff = self.parent_inverse
        x, y = point
        px = ia * x + ib * y + ic
        py = id_ * x + ie * y + iff
        left, top, right, bottom = self.source_bounds
        gx0, gy0, gx1, gy1 = self.grid_rect
        sx = visual.scale9_inverse_coordinate(
            px - self.x0, right - left, gx0 - left, right - gx1,
            self.target_width, self.flip_x,
        )
        sy = visual.scale9_inverse_coordinate(
            py - self.y0, bottom - top, gy0 - top, bottom - gy1,
            self.target_height, self.flip_y,
        )
        return left + sx, top + sy

    def contains(self, point):
        x, y = point
        left, top, right, bottom = self.bounds
        if not (left <= x <= right and top <= y <= bottom):
            return False
        if any(not clip.contains(point) for clip in self.outer_clips):
            return False
        return bool(self.natural.contains(self.local_point(point)))


def _is_scale9(definition, grid, matrix):
    return bool(
        grid is not None and isinstance(definition, ui_browser.SpriteDef)
        and abs(matrix.b) < 1e-7 and abs(matrix.c) < 1e-7
        and (
            abs(abs(matrix.a) - 1.0) > 1e-5
            or abs(abs(matrix.d) - 1.0) > 1e-5
        )
    )


def _collect_scale9(collector, definition, item, parent_matrix, path, clips, stack,
                    sink, owner_path, name, enabled, tab_enabled):
    grid = getattr(collector.movie, "scaling_grids", {}).get(item.character_id)
    if not _is_scale9(definition, grid, item.matrix):
        return False
    bounds = scale9._definition_bounds(collector.renderer, item.character_id, stack) or grid.rect
    left = float(math.floor(bounds[0]))
    top = float(math.floor(bounds[1]))
    right = float(math.ceil(bounds[2]))
    bottom = float(math.ceil(bounds[3]))
    source_width = max(1.0, right - left)
    source_height = max(1.0, bottom - top)
    target_width = max(1.0, float(round(source_width * abs(item.matrix.a))))
    target_height = max(1.0, float(round(source_height * abs(item.matrix.d))))
    x0 = min(item.matrix.tx + item.matrix.a * left, item.matrix.tx + item.matrix.a * right)
    y0 = min(item.matrix.ty + item.matrix.d * top, item.matrix.ty + item.matrix.d * bottom)
    parent_inverse = parent_matrix.inverse_pillow()
    if parent_inverse is None:
        return False

    natural = []
    _BASE["geometry_definition"](
        collector, definition, ui_browser.Affine(), path, (), stack,
        natural, owner_path, name, enabled, tab_enabled, False,
    )
    if not natural:
        return False
    world_bounds = hit_base._world_bounds(
        parent_matrix, (x0, y0, x0 + target_width, y0 + target_height),
    )
    wrapped = [
        Scale9MappedGeometry(
            path=value.path,
            kind=f"scale9-{value.kind}",
            bounds=world_bounds,
            natural=value,
            outer_clips=tuple(clips),
            parent_inverse=parent_inverse,
            x0=x0,
            y0=y0,
            source_bounds=(left, top, right, bottom),
            grid_rect=tuple(grid.rect),
            target_width=target_width,
            target_height=target_height,
            flip_x=item.matrix.a < 0,
            flip_y=item.matrix.d < 0,
            character_id=getattr(value, "character_id", item.character_id),
        )
        for value in natural
    ]
    sink.extend(wrapped)
    collector.scale9_count = int(getattr(collector, "scale9_count", 0)) + len(wrapped)
    return True


def geometry_leaf(collector, definition, matrix, path, clips, character_id=None, name="",
                  enabled=True, tab_enabled=False, dynamic_flag=False):
    if isinstance(definition, visual.EmbeddedBitmapDef):
        image = definition.image
        alpha = image.getchannel("A")
        collector.add(
            hit_base._alpha_geometry(
                path, matrix, (0.0, 0.0, float(image.width), float(image.height)),
                alpha, (0.0, 0.0), clips, "embedded-bitmap-alpha", character_id,
            ),
            name, enabled, tab_enabled, dynamic_flag,
        )
        return
    vector_type = getattr(ui_browser, "VectorShapeDef", ())
    if vector_type and isinstance(definition, vector_type):
        try:
            image, origin = _rasterize_with_resources(collector.renderer, definition)
            alpha = image.getchannel("A")
            bounds = (
                float(origin[0]), float(origin[1]),
                float(origin[0] + image.width), float(origin[1] + image.height),
            )
            collector.add(
                hit_base._alpha_geometry(
                    path, matrix, bounds, alpha, origin, clips,
                    "vector-resource-alpha", character_id,
                ),
                name, enabled, tab_enabled, dynamic_flag,
            )
            return
        except Exception:
            pass
    return _BASE["geometry_leaf"](
        collector, definition, matrix, path, clips, character_id,
        name, enabled, tab_enabled, dynamic_flag,
    )


def geometry_display(collector, display, parent_matrix, parent_path, inherited_clips,
                     stack, sink=None, owner_path=None):
    sink = collector.geometries if sink is None else sink
    active_masks = []
    for depth in sorted(display):
        active_masks = [value for value in active_masks if int(depth) <= value[0]]
        raw_item = display[depth]
        try:
            item, path, _override = overrides_patch.apply_item_override(
                collector.movie, parent_path, depth, raw_item, collector.overrides,
            )
        except Exception:
            item = raw_item
            label = getattr(item, "name", "") or f"depth {depth}"
            path = f"{parent_path}/{int(depth)}:{label}"
        if not bool(getattr(item, "visible", True)):
            continue
        matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
        character_id = getattr(item, "character_id", None)
        definition = collector.movie.definitions.get(character_id) if character_id is not None else None
        if isinstance(definition, visual.MorphShapeDef):
            definition = _morph_vector(definition, getattr(item, "ratio", 0))
        clips = tuple(inherited_clips) + tuple(value[1] for value in active_masks)
        clip_depth = getattr(item, "clip_depth", None)
        if clip_depth is not None and int(clip_depth) > int(depth):
            geoms = collector._mask_geometry(item, definition, matrix, path, clips, stack)
            if geoms:
                active_masks.append((int(clip_depth), hit_geometry.classic.HitClip(geoms, "clipDepth")))
                collector.mask_count += 1
            continue
        name = str(getattr(item, "name", "") or path.rsplit(":", 1)[-1])
        enabled = bool(
            getattr(item, "_ui_enabled", True)
            and getattr(item, "_ui_mouse_enabled", True)
        )
        tab_enabled = bool(getattr(item, "_ui_tab_enabled", False))
        output_path = owner_path or path

        original_definition = collector.movie.definitions.get(character_id) if character_id is not None else None
        if (
            character_id is not None
            and isinstance(original_definition, ui_browser.SpriteDef)
            and _collect_scale9(
                collector, original_definition, item, parent_matrix, path, clips,
                stack, sink, owner_path, name, enabled, tab_enabled,
            )
        ):
            continue

        if getattr(item, "class_name", ""):
            before = len(collector.geometries)
            collector._external(item, matrix, output_path, clips, name, enabled, tab_enabled)
            if sink is not collector.geometries and len(collector.geometries) > before:
                sink.extend(collector.geometries[before:])
                del collector.geometries[before:]
        elif definition is not None:
            collector._definition(
                definition, matrix, path, clips, stack, sink,
                owner_path, name, enabled, tab_enabled, False,
            )
    if owner_path is None:
        collector._dynamic_children(parent_path, parent_matrix, inherited_clips, stack, sink)


def build_precise_hit_map(renderer, frame):
    result = _BASE["precise_map"](renderer, frame)
    diagnostics = getattr(renderer.movie, "ui_precise_hit_diagnostics", None)
    if isinstance(diagnostics, dict):
        mapping = getattr(renderer.movie, "ui_precise_hit_geometries", {}) or {}
        scale9_count = sum(
            1 for values in mapping.values() for value in values
            if isinstance(value, Scale9MappedGeometry)
        )
        diagnostics["scale9_geometries"] = scale9_count
    return result


def definition_kind(definition):
    if isinstance(definition, visual.MorphShapeDef):
        return "MorphShape"
    if isinstance(definition, visual.EmbeddedBitmapDef):
        return "EmbeddedBitmap"
    return _BASE["definition_kind"](definition)


def metadata_for(movie, item, definition, sprite_frame):
    metadata = _BASE["metadata_for"](movie, item, definition, sprite_frame)
    if isinstance(definition, visual.MorphShapeDef):
        metadata.update({
            "morph_ratio": int(getattr(item, "ratio", 0) or 0),
            "morph_start_bounds": tuple(definition.start_bounds),
            "morph_end_bounds": tuple(definition.end_bounds),
            "morph_start_records": len(definition.start_records),
            "morph_end_records": len(definition.end_records),
            "morph_warnings": tuple(definition.parse_warnings),
        })
    elif isinstance(definition, visual.EmbeddedBitmapDef):
        metadata.update({
            "bounds": (0.0, 0.0, float(definition.image.width), float(definition.image.height)),
            "bitmap_format": definition.format_name,
            "bitmap_tag": definition.source_tag,
        })
    return metadata


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    if node.kind == "MorphShape":
        ratio = int(node.metadata.get("morph_ratio", 0) or 0)
        return text + "\n\nMorphShape:\n" + (
            f"- Ratio: {ratio} / 65535 ({ratio / 65535.0:.3%})\n"
            f"- Kanten: {node.metadata.get('morph_start_records', 0)} / "
            f"{node.metadata.get('morph_end_records', 0)}\n"
            f"- StartBounds: {node.metadata.get('morph_start_bounds')}\n"
            f"- EndBounds: {node.metadata.get('morph_end_bounds')}"
        )
    if node.kind == "EmbeddedBitmap":
        return text + "\n\nEingebettetes Bitmap:\n" + (
            f"- Format: {node.metadata.get('bitmap_format', '-')}\n"
            f"- Tag: {node.metadata.get('bitmap_tag', '-')}\n"
            f"- Bounds: {node.metadata.get('bounds')}"
        )
    return text


def format_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    morphs = int(getattr(movie, "ui_morph_shape_count", 0) or 0)
    bitmaps = int(getattr(movie, "ui_embedded_bitmap_count", 0) or 0)
    errors = len(tuple(getattr(movie, "ui_morph_shape_errors", ()) or ())) + len(
        tuple(getattr(movie, "ui_embedded_bitmap_errors", ()) or ())
    )
    if not any((
        morphs, bitmaps, errors,
        getattr(stats, "morph_placements", 0),
        getattr(stats, "bitmap_fills", 0),
        getattr(stats, "missing_bitmap_fills", 0),
    )):
        return text
    diagnostics = getattr(movie, "ui_precise_hit_diagnostics", {}) or {}
    return text + "\n\nVisuelle Sonderformate:\n" + (
        f"- MorphShape-Definitionen / Placements: {morphs} / "
        f"{getattr(stats, 'morph_placements', 0)}\n"
        f"- Eingebettete Bitmaps: {bitmaps}\n"
        f"- Bitmap-Fills / fehlend: {getattr(stats, 'bitmap_fills', 0)} / "
        f"{getattr(stats, 'missing_bitmap_fills', 0)}\n"
        f"- Scale9-Hit-Geometrien: {diagnostics.get('scale9_geometries', 0)}\n"
        f"- Parserfehler: {errors}"
    )


def clear_visual_caches():
    global _GRADIENT_CACHE_BYTES, _RESOURCE_RASTER_BYTES
    _MORPH_CACHE.clear()
    _GRADIENT_CACHE.clear()
    _RESOURCE_RASTER_CACHE.clear()
    _GRADIENT_CACHE_BYTES = 0
    _RESOURCE_RASTER_BYTES = 0
    shape_patch._RASTER_CACHE.clear()
    precise.clear_geometry_cache()


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        parse=ui_browser.parse_swf_movie,
        place2=ui_browser._parse_place_object2,
        draw_display=ui_browser.UIRenderer._draw_display,
        draw_vector=shape_patch._draw_vector_shape,
        geometry_leaf=hit_geometry.GeometryCollector._leaf,
        geometry_definition=hit_geometry.GeometryCollector._definition,
        geometry_display=hit_geometry.GeometryCollector._display,
        precise_map=precise.build_precise_hit_map,
        definition_kind=inspector._definition_kind,
        metadata_for=inspector._metadata_for,
        format_node=inspector.format_state_node,
        info=ui_browser.UIBrowser._format_info,
    )

    shape_patch._read_fill_style = visual.read_vector_fill_style
    shape_patch._gradient_layer = gradient_layer
    shape_patch._draw_vector_shape = draw_vector_shape
    shape_patch._RASTER_CACHE.clear()

    ui_browser._parse_place_object2 = parse_place_object2
    ui_browser.parse_swf_movie = parse_swf_movie
    ui_browser.UIRenderer._draw_display = draw_display

    hit_geometry.GeometryCollector._leaf = geometry_leaf
    hit_geometry.GeometryCollector._display = geometry_display
    precise.build_precise_hit_map = build_precise_hit_map

    inspector._definition_kind = definition_kind
    inspector._metadata_for = metadata_for
    inspector.format_state_node = format_state_node
    ui_browser.UIBrowser._format_info = format_info

    ui_browser.EmbeddedBitmapDef = visual.EmbeddedBitmapDef
    ui_browser.MorphShapeDef = visual.MorphShapeDef
    ui_browser.parse_morph_shape = visual.parse_morph_shape
    ui_browser.interpolate_morph_shape = visual.interpolate_morph
    ui_browser.Scale9MappedHitGeometry = Scale9MappedGeometry
    ui_browser.clear_ui_visual_format_caches = clear_visual_caches
