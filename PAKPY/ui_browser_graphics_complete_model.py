"""Tk-independent completion helpers for the bounded AVM2 Graphics preview runtime.

The module adds drawPath/drawTriangles, bitmap and gradient stroke paints, and an
isolated in-memory BitmapData implementation. No host resources are accessed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import ui_browser_graphics_model as base

try:
    from PIL import Image, ImageChops, ImageDraw
except Exception:  # pragma: no cover - exercised by integration fallback
    Image = None
    ImageChops = None
    ImageDraw = None

MAX_BITMAP_DIMENSION = 8192
MAX_BITMAP_PIXELS = 32_000_000
MAX_BITMAP_BYTES = 256 * 1024 * 1024
MAX_DRAW_PATH_COMMANDS = 10_000
MAX_DRAW_PATH_DATA = 80_000
MAX_DRAW_TRIANGLES = 32_768
MAX_BITMAP_OPERATION_PIXELS = 32_000_000

GRAPHICS_PATH_NO_OP = 0
GRAPHICS_PATH_MOVE_TO = 1
GRAPHICS_PATH_LINE_TO = 2
GRAPHICS_PATH_CURVE_TO = 3
GRAPHICS_PATH_WIDE_MOVE_TO = 4
GRAPHICS_PATH_WIDE_LINE_TO = 5
GRAPHICS_PATH_CUBIC_CURVE_TO = 6


def _require_pillow():
    if Image is None:
        raise RuntimeError("Pillow wird für BitmapData benötigt")


def _bounded_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _rect_tuple(value, default=(0, 0, 0, 0)):
    if isinstance(value, dict):
        x = value.get("x", default[0])
        y = value.get("y", default[1])
        width = value.get("width", default[2])
        height = value.get("height", default[3])
        return (_bounded_int(x), _bounded_int(y), _bounded_int(width), _bounded_int(height))
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return tuple(_bounded_int(item) for item in value[:4])
    return tuple(default)


def _point_tuple(value, default=(0, 0)):
    if isinstance(value, dict):
        return (_bounded_int(value.get("x", default[0])), _bounded_int(value.get("y", default[1])))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_bounded_int(value[0]), _bounded_int(value[1]))
    return tuple(default)


def argb_to_rgba(value, transparent=True):
    value = _bounded_int(value, 0xFFFFFFFF) & 0xFFFFFFFF
    alpha = (value >> 24) & 0xFF if transparent else 0xFF
    return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF, alpha)


def rgba_to_argb(value):
    red, green, blue, alpha = tuple(value)[:4]
    return ((int(alpha) & 0xFF) << 24) | ((int(red) & 0xFF) << 16) | ((int(green) & 0xFF) << 8) | (int(blue) & 0xFF)


@dataclass
class PreviewBitmapData:
    width: int
    height: int
    transparent: bool = True
    fill_color: int = 0xFFFFFFFF
    image: object | None = None
    disposed: bool = False
    locked: bool = False
    revision: int = 0

    def __post_init__(self):
        _require_pillow()
        self.width = max(1, min(MAX_BITMAP_DIMENSION, _bounded_int(self.width, 1)))
        self.height = max(1, min(MAX_BITMAP_DIMENSION, _bounded_int(self.height, 1)))
        if self.width * self.height > MAX_BITMAP_PIXELS:
            raise ValueError("BitmapData überschreitet das Pixellimit")
        if self.width * self.height * 4 > MAX_BITMAP_BYTES:
            raise ValueError("BitmapData überschreitet das Speicherlimit")
        self.transparent = bool(self.transparent)
        self.fill_color = _bounded_int(self.fill_color, 0xFFFFFFFF) & 0xFFFFFFFF
        if self.image is None:
            self.image = Image.new("RGBA", (self.width, self.height), argb_to_rgba(self.fill_color, self.transparent))
        else:
            image = self.image.convert("RGBA")
            if image.size != (self.width, self.height):
                image = image.resize((self.width, self.height))
            if not self.transparent:
                image.putalpha(255)
            self.image = image

    @property
    def rect(self):
        return {"x": 0, "y": 0, "width": self.width, "height": self.height}

    def _check(self):
        if self.disposed or self.image is None:
            raise ValueError("BitmapData wurde verworfen")

    def touch(self):
        self.revision += 1

    def clone(self):
        self._check()
        return PreviewBitmapData(
            self.width, self.height, self.transparent, self.fill_color,
            self.image.copy(), False, False, self.revision,
        )

    def dispose(self):
        self.image = None
        self.disposed = True
        self.touch()

    def get_pixel(self, x, y, include_alpha=False):
        self._check()
        x, y = _bounded_int(x), _bounded_int(y)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return 0
        red, green, blue, alpha = self.image.getpixel((x, y))
        if include_alpha:
            return ((alpha & 0xFF) << 24) | ((red & 0xFF) << 16) | ((green & 0xFF) << 8) | (blue & 0xFF)
        return ((red & 0xFF) << 16) | ((green & 0xFF) << 8) | (blue & 0xFF)

    def set_pixel(self, x, y, color, include_alpha=False):
        self._check()
        x, y = _bounded_int(x), _bounded_int(y)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        old = self.image.getpixel((x, y))
        if include_alpha:
            rgba = argb_to_rgba(color, self.transparent)
        else:
            value = _bounded_int(color) & 0xFFFFFF
            rgba = ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF, old[3] if self.transparent else 255)
        self.image.putpixel((x, y), rgba)
        self.touch()
        return True

    def fill_rect(self, rect, color):
        self._check()
        x, y, width, height = _rect_tuple(rect, (0, 0, self.width, self.height))
        if width < 0:
            x, width = x + width, -width
        if height < 0:
            y, height = y + height, -height
        left, top = max(0, x), max(0, y)
        right, bottom = min(self.width, x + width), min(self.height, y + height)
        if right <= left or bottom <= top:
            return False
        if (right - left) * (bottom - top) > MAX_BITMAP_OPERATION_PIXELS:
            raise ValueError("BitmapData-Operation überschreitet das Pixellimit")
        ImageDraw.Draw(self.image).rectangle((left, top, right - 1, bottom - 1), fill=argb_to_rgba(color, self.transparent))
        self.touch()
        return True

    def copy_pixels(self, source, source_rect, dest_point, merge_alpha=False):
        self._check()
        if not isinstance(source, PreviewBitmapData):
            return False
        source._check()
        sx, sy, width, height = _rect_tuple(source_rect, (0, 0, source.width, source.height))
        dx, dy = _point_tuple(dest_point)
        if width < 0:
            sx, width = sx + width, -width
        if height < 0:
            sy, height = sy + height, -height
        width = min(width, source.width - max(0, sx), self.width - max(0, dx))
        height = min(height, source.height - max(0, sy), self.height - max(0, dy))
        if width <= 0 or height <= 0:
            return False
        sx, sy, dx, dy = max(0, sx), max(0, sy), max(0, dx), max(0, dy)
        if width * height > MAX_BITMAP_OPERATION_PIXELS:
            raise ValueError("BitmapData-Operation überschreitet das Pixellimit")
        crop = source.image.crop((sx, sy, sx + width, sy + height))
        if merge_alpha and self.transparent:
            self.image.alpha_composite(crop, (dx, dy))
        else:
            if not self.transparent:
                crop.putalpha(255)
            self.image.paste(crop, (dx, dy))
        self.touch()
        return True

    def draw_bitmap(self, source, matrix=None, smoothing=False, clip_rect=None):
        self._check()
        if isinstance(source, PreviewBitmapData):
            source._check()
            image = source.image
        elif Image is not None and isinstance(source, Image.Image):
            image = source.convert("RGBA")
        else:
            return False
        if matrix is None:
            transformed = image
            offset = (0, 0)
        else:
            try:
                a, b, c, d, tx, ty = tuple(float(value) for value in tuple(matrix)[:6])
            except Exception:
                return False
            det = a * d - b * c
            if abs(det) < 1e-12:
                return False
            ia, ib = d / det, -c / det
            id_, ie = -b / det, a / det
            ic = -(ia * tx + ib * ty)
            iff = -(id_ * tx + ie * ty)
            resampling_group = getattr(Image, "Resampling", Image)
            resampling = getattr(resampling_group, "BILINEAR" if smoothing else "NEAREST")
            transform_mode = getattr(getattr(Image, "Transform", Image), "AFFINE")
            transformed = image.transform(self.image.size, transform_mode, (ia, ib, ic, id_, ie, iff), resample=resampling)
            offset = (0, 0)
        if clip_rect is not None:
            x, y, width, height = _rect_tuple(clip_rect)
            mask = Image.new("L", self.image.size, 0)
            ImageDraw.Draw(mask).rectangle((x, y, x + width, y + height), fill=255)
            alpha = transformed.getchannel("A")
            if ImageChops is not None:
                alpha = ImageChops.multiply(alpha, mask)
            transformed = transformed.copy()
            transformed.putalpha(alpha)
        self.image.alpha_composite(transformed, offset)
        if not self.transparent:
            self.image.putalpha(255)
        self.touch()
        return True

    def scroll(self, dx, dy):
        self._check()
        dx, dy = _bounded_int(dx), _bounded_int(dy)
        moved = Image.new("RGBA", self.image.size, (0, 0, 0, 0 if self.transparent else 255))
        moved.paste(self.image, (dx, dy))
        self.image = moved
        self.touch()

    def flood_fill(self, x, y, color):
        self._check()
        x, y = _bounded_int(x), _bounded_int(y)
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        replacement = argb_to_rgba(color, self.transparent)
        target = self.image.getpixel((x, y))
        if target == replacement:
            return False
        pixels = self.image.load()
        queue = [(x, y)]
        visited = set()
        while queue:
            px, py = queue.pop()
            if (px, py) in visited or not (0 <= px < self.width and 0 <= py < self.height):
                continue
            visited.add((px, py))
            if len(visited) > MAX_BITMAP_OPERATION_PIXELS:
                raise ValueError("floodFill überschreitet das Pixellimit")
            if pixels[px, py] != target:
                continue
            pixels[px, py] = replacement
            queue.extend(((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)))
        self.touch()
        return True


@dataclass(frozen=True)
class BitmapPaint:
    kind: str
    bitmap: PreviewBitmapData
    matrix: tuple[float, float, float, float, float, float] | None = None
    repeat: bool = True
    smooth: bool = False


@dataclass(frozen=True)
class PaintedLineStyle:
    thickness: float
    color: int = 0
    alpha: float = 1.0
    pixel_hinting: bool = False
    scale_mode: str = "normal"
    caps: str = "round"
    joints: str = "round"
    miter_limit: float = 3.0
    paint: object | None = None


def _meta(state):
    value = getattr(state, "_complete_graphics_meta", None)
    if not isinstance(value, dict):
        value = {"primitive": {}, "draw_path_calls": 0, "draw_triangle_calls": 0}
        state._complete_graphics_meta = value
    return value


def primitive_metadata(state, primitive):
    return dict(_meta(state)["primitive"].get(id(primitive), {}) or {})


def _mark_new_primitives(state, start, **values):
    for primitive in state.primitives[start:]:
        _meta(state)["primitive"][id(primitive)] = dict(values)


def state_resource_revision(state):
    result = []
    for primitive in tuple(state.primitives):
        for paint in (getattr(primitive, "fill", None), getattr(getattr(primitive, "line", None), "paint", None)):
            bitmap = getattr(paint, "bitmap", None)
            if isinstance(bitmap, PreviewBitmapData):
                result.append((id(bitmap), int(bitmap.revision), bool(bitmap.disposed)))
    return tuple(result)


def has_extended_content(state):
    if _meta(state)["primitive"]:
        return True
    for primitive in tuple(state.primitives):
        if isinstance(getattr(primitive, "fill", None), BitmapPaint):
            return True
        if isinstance(getattr(primitive, "line", None), PaintedLineStyle):
            return True
    return False


def begin_bitmap_fill(state, bitmap, matrix=None, repeat=True, smooth=False):
    if not isinstance(bitmap, PreviewBitmapData) or bitmap.disposed:
        state.rejected += 1
        return False
    base.seal(state)
    clean_matrix = None
    if matrix is not None:
        try:
            values = tuple(float(value) for value in tuple(matrix)[:6])
            clean_matrix = values if len(values) == 6 else None
        except Exception:
            clean_matrix = None
    state.fill = BitmapPaint("bitmap", bitmap, clean_matrix, bool(repeat), bool(smooth))
    state.touch()
    return True


def line_gradient_style(state, gradient_fill):
    if state.line is None:
        state.rejected += 1
        return False
    base.seal(state)
    line = state.line
    state.line = PaintedLineStyle(
        line.thickness, line.color, line.alpha, line.pixel_hinting,
        line.scale_mode, line.caps, line.joints, line.miter_limit,
        gradient_fill,
    )
    state.touch()
    return True


def line_bitmap_style(state, bitmap, matrix=None, repeat=True, smooth=False):
    if state.line is None or not isinstance(bitmap, PreviewBitmapData) or bitmap.disposed:
        state.rejected += 1
        return False
    clean_matrix = None
    if matrix is not None:
        try:
            values = tuple(float(value) for value in tuple(matrix)[:6])
            clean_matrix = values if len(values) == 6 else None
        except Exception:
            clean_matrix = None
    return line_gradient_style(state, BitmapPaint("bitmap", bitmap, clean_matrix, bool(repeat), bool(smooth)))


def _sequence(value, limit):
    if value is None:
        return ()
    if isinstance(value, dict):
        indexed = []
        for key, item in value.items():
            try:
                indexed.append((int(key), item))
            except Exception:
                continue
        return tuple(item for _key, item in sorted(indexed)[:limit])
    try:
        return tuple(value)[:limit]
    except Exception:
        return ()


def draw_path(state, commands, data, winding="evenOdd"):
    command_values = _sequence(commands, MAX_DRAW_PATH_COMMANDS + 1)
    data_values = _sequence(data, MAX_DRAW_PATH_DATA + 1)
    if len(command_values) > MAX_DRAW_PATH_COMMANDS or len(data_values) > MAX_DRAW_PATH_DATA:
        state.rejected += 1
        return 0
    winding_value = "nonZero" if str(winding or "").lower().replace("_", "") == "nonzero" else "evenOdd"
    base.seal(state)
    start = len(state.primitives)
    cursor = 0
    accepted = 0

    def take(count):
        nonlocal cursor
        if cursor + count > len(data_values):
            raise IndexError
        values = data_values[cursor:cursor + count]
        cursor += count
        return values

    try:
        for raw in command_values:
            command = _bounded_int(raw)
            if command == GRAPHICS_PATH_NO_OP:
                continue
            if command == GRAPHICS_PATH_MOVE_TO:
                x, y = take(2)
                base.move_to(state, x, y)
            elif command == GRAPHICS_PATH_LINE_TO:
                x, y = take(2)
                base.line_to(state, x, y)
            elif command == GRAPHICS_PATH_CURVE_TO:
                cx, cy, ax, ay = take(4)
                base.curve_to(state, cx, cy, ax, ay)
            elif command == GRAPHICS_PATH_WIDE_MOVE_TO:
                _discard_x, _discard_y, x, y = take(4)
                base.move_to(state, x, y)
            elif command == GRAPHICS_PATH_WIDE_LINE_TO:
                _discard_x, _discard_y, x, y = take(4)
                base.line_to(state, x, y)
            elif command == GRAPHICS_PATH_CUBIC_CURVE_TO:
                values = take(6)
                base.cubic_curve_to(state, *values)
            else:
                state.rejected += 1
                continue
            accepted += 1
    except IndexError:
        state.rejected += 1
    base.seal(state)
    _mark_new_primitives(state, start, winding=winding_value, source="drawPath")
    _meta(state)["draw_path_calls"] += 1
    return accepted


def _triangle_area(left, middle, right):
    return (middle[0] - left[0]) * (right[1] - left[1]) - (middle[1] - left[1]) * (right[0] - left[0])


def draw_triangles(state, vertices, indices=None, uvt_data=None, culling="none"):
    raw_vertices = _sequence(vertices, MAX_DRAW_TRIANGLES * 6 + 2)
    vertex_count = len(raw_vertices) // 2
    points = [
        (base._number(raw_vertices[index * 2]), base._number(raw_vertices[index * 2 + 1]))
        for index in range(vertex_count)
    ]
    if indices is None:
        raw_indices = tuple(range(vertex_count))
    else:
        raw_indices = _sequence(indices, MAX_DRAW_TRIANGLES * 3 + 1)
    triangle_count = min(MAX_DRAW_TRIANGLES, len(raw_indices) // 3)
    if len(raw_indices) // 3 > MAX_DRAW_TRIANGLES:
        state.rejected += 1
    uv_values = _sequence(uvt_data, vertex_count * 3 + 1) if uvt_data is not None else ()
    stride = 3 if len(uv_values) >= vertex_count * 3 else (2 if len(uv_values) >= vertex_count * 2 else 0)
    cull = str(culling or "none").lower()
    base.seal(state)
    accepted = 0
    for triangle in range(triangle_count):
        try:
            ids = tuple(_bounded_int(raw_indices[triangle * 3 + index]) for index in range(3))
            if any(index < 0 or index >= vertex_count for index in ids):
                raise IndexError
            triangle_points = tuple(points[index] for index in ids)
        except Exception:
            state.rejected += 1
            continue
        area = _triangle_area(*triangle_points)
        if abs(area) < 1e-12:
            continue
        if (cull == "positive" and area > 0) or (cull == "negative" and area < 0):
            continue
        if len(state.primitives) >= base.MAX_GRAPHICS_PRIMITIVES:
            state.rejected += 1
            break
        before = len(state.primitives)
        base._append_closed(state, (
            ("M", *triangle_points[0]),
            ("L", *triangle_points[1]),
            ("L", *triangle_points[2]),
            ("Z",),
        ))
        if len(state.primitives) == before:
            continue
        primitive = state.primitives[-1]
        metadata = {"source": "drawTriangles", "winding": "nonZero", "triangle": triangle_points}
        if stride:
            values = []
            for index in ids:
                offset = index * stride
                u = base._number(uv_values[offset])
                v = base._number(uv_values[offset + 1])
                t = base._number(uv_values[offset + 2], 1.0) if stride == 3 else 1.0
                values.append((u, v, t))
            metadata["uvt"] = tuple(values)
        _meta(state)["primitive"][id(primitive)] = metadata
        accepted += 1
    _meta(state)["draw_triangle_calls"] += 1
    return accepted
