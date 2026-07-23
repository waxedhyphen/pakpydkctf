"""Complete the bounded AVM2 Graphics/BitmapData preview implementation.

Adds drawPath, drawTriangles, bitmap fills, gradient/bitmap line paints, isolated
BitmapData/Bitmap objects, and graphics overlays on existing timeline Shape/Sprite
instances. All data remains in the per-movie preview runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_graphics_patch as graphics
import ui_browser_graphics_model as model
import ui_browser_graphics_complete_model as complete
import ui_browser_hit_geometry as hit_geometry
import ui_browser_hit_geometry_base as hit_base
import ui_browser_precise_hit as precise
import ui_browser_shape_patch as shape_patch
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as overrides_patch
import ui_browser_visual_formats_patch as visual_patch
import ui_browser_classic_button as classic

try:
    from PIL import Image, ImageChops, ImageDraw
except Exception:
    Image = None
    ImageChops = None
    ImageDraw = None


_INSTALLED = False
_BASE = {}
_MAX_STATIC_GRAPHICS_PATHS = 2048
_MAX_TRIANGLE_SAMPLE_PIXELS = 4_000_000


@dataclass(frozen=True)
class CompleteGraphicsProxy:
    movie: object
    path: str
    target: dynamic.DynamicDisplayObject | None = None
    static: bool = False


def _short(value):
    return str(value or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]


def _static_store(movie):
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    value = getattr(movie, "ui_avm2_static_graphics", None)
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {"generation": generation, "states": {}, "revision": 0}
        movie.ui_avm2_static_graphics = value
    return value


def _state_for_proxy(proxy, create=True):
    if proxy.target is not None:
        return graphics._graphics_state(proxy.target, create)
    store = _static_store(proxy.movie)
    states = store["states"]
    state = states.get(str(proxy.path))
    if not isinstance(state, model.GraphicsState) and create:
        if len(states) >= _MAX_STATIC_GRAPHICS_PATHS:
            return None
        state = model.GraphicsState()
        states[str(proxy.path)] = state
    return state if isinstance(state, model.GraphicsState) else None


def _static_state(movie, path):
    return _static_store(movie)["states"].get(str(path))


def _bitmap_from(movie, value):
    if isinstance(value, complete.PreviewBitmapData):
        return value
    if isinstance(value, dynamic.DynamicDisplayObject):
        bitmap = value.extras.get("bitmapData")
        return bitmap if isinstance(bitmap, complete.PreviewBitmapData) else None
    if isinstance(value, runtime.RuntimeRef):
        try:
            obj = dynamic._dynamic_for_path(movie, value.path)
        except Exception:
            obj = None
        if obj is not None:
            bitmap = obj.extras.get("bitmapData")
            return bitmap if isinstance(bitmap, complete.PreviewBitmapData) else None
    return None


def _matrix_tuple(context, value):
    return graphics._matrix_tuple(context, value)


def _gradient_fill(context, args):
    state = model.GraphicsState()
    model.begin_gradient_fill(
        state,
        args[0] if args else "linear",
        graphics._sequence(args[1]) if len(args) > 1 else (),
        graphics._sequence(args[2]) if len(args) > 2 else (),
        graphics._sequence(args[3]) if len(args) > 3 else (),
        _matrix_tuple(context, args[4]) if len(args) > 4 else None,
        args[5] if len(args) > 5 else "pad",
        args[6] if len(args) > 6 else "rgb",
        args[7] if len(args) > 7 else 0.0,
    )
    return state.fill


def _touch_proxy(proxy):
    values = graphics._movie_state(proxy.movie)
    values["revision"] = int(values.get("revision", 0)) + 1
    if proxy.static:
        store = _static_store(proxy.movie)
        store["revision"] = int(store.get("revision", 0)) + 1
    dynamic._touch(proxy.movie)
    precise.clear_geometry_cache()


def _invoke_graphics(context, proxy, name, args):
    state = _state_for_proxy(proxy)
    values = graphics._movie_state(proxy.movie)
    if state is None:
        values["rejected"] = int(values.get("rejected", 0)) + 1
        return runtime._UNDEFINED
    lower = _short(name).lower()
    values["calls"] = int(values.get("calls", 0)) + 1
    before_rejected = int(state.rejected)

    if lower == "clear":
        model.clear(state)
    elif lower == "beginfill":
        model.begin_fill(state, args[0] if args else 0, args[1] if len(args) > 1 else 1.0)
    elif lower == "begingradientfill":
        model.begin_gradient_fill(
            state,
            args[0] if args else "linear",
            graphics._sequence(args[1]) if len(args) > 1 else (),
            graphics._sequence(args[2]) if len(args) > 2 else (),
            graphics._sequence(args[3]) if len(args) > 3 else (),
            _matrix_tuple(context, args[4]) if len(args) > 4 else None,
            args[5] if len(args) > 5 else "pad",
            args[6] if len(args) > 6 else "rgb",
            args[7] if len(args) > 7 else 0.0,
        )
    elif lower == "beginbitmapfill":
        complete.begin_bitmap_fill(
            state,
            _bitmap_from(context.movie, args[0]) if args else None,
            _matrix_tuple(context, args[1]) if len(args) > 1 else None,
            args[2] if len(args) > 2 else True,
            args[3] if len(args) > 3 else False,
        )
    elif lower == "endfill":
        model.end_fill(state)
    elif lower == "linestyle":
        model.line_style(
            state,
            args[0] if args else None,
            args[1] if len(args) > 1 else 0,
            args[2] if len(args) > 2 else 1.0,
            args[3] if len(args) > 3 else False,
            args[4] if len(args) > 4 else "normal",
            args[5] if len(args) > 5 else "round",
            args[6] if len(args) > 6 else "round",
            args[7] if len(args) > 7 else 3.0,
        )
    elif lower == "linegradientstyle":
        complete.line_gradient_style(state, _gradient_fill(context, args))
    elif lower == "linebitmapstyle":
        complete.line_bitmap_style(
            state,
            _bitmap_from(context.movie, args[0]) if args else None,
            _matrix_tuple(context, args[1]) if len(args) > 1 else None,
            args[2] if len(args) > 2 else True,
            args[3] if len(args) > 3 else False,
        )
    elif lower == "moveto" and len(args) >= 2:
        model.move_to(state, args[0], args[1])
    elif lower == "lineto" and len(args) >= 2:
        model.line_to(state, args[0], args[1])
    elif lower == "curveto" and len(args) >= 4:
        model.curve_to(state, args[0], args[1], args[2], args[3])
    elif lower == "cubiccurveto" and len(args) >= 6:
        model.cubic_curve_to(state, *args[:6])
    elif lower == "drawrect" and len(args) >= 4:
        model.draw_rect(state, *args[:4])
    elif lower == "drawroundrect" and len(args) >= 5:
        model.draw_round_rect(
            state, args[0], args[1], args[2], args[3], args[4],
            args[5] if len(args) > 5 else None,
        )
    elif lower == "drawcircle" and len(args) >= 3:
        model.draw_circle(state, *args[:3])
    elif lower == "drawellipse" and len(args) >= 4:
        model.draw_ellipse(state, *args[:4])
    elif lower == "drawpath" and len(args) >= 2:
        complete.draw_path(
            state, graphics._sequence(args[0]), graphics._sequence(args[1]),
            args[2] if len(args) > 2 else "evenOdd",
        )
    elif lower == "drawtriangles" and args:
        complete.draw_triangles(
            state,
            graphics._sequence(args[0]),
            graphics._sequence(args[1]) if len(args) > 1 and args[1] not in (None, runtime._UNDEFINED) else None,
            graphics._sequence(args[2]) if len(args) > 2 and args[2] not in (None, runtime._UNDEFINED) else None,
            args[3] if len(args) > 3 else "none",
        )
    else:
        values["rejected"] = int(values.get("rejected", 0)) + 1
        return runtime._UNDEFINED

    if state.rejected > before_rejected:
        values["rejected"] = int(values.get("rejected", 0)) + state.rejected - before_rejected
    context.writes += 1
    _touch_proxy(proxy)
    runtime._log(
        proxy.movie, "graphics-complete", path=proxy.path, method=_short(name),
        commands=int(state.command_count), primitives=len(state.primitives),
        static=bool(proxy.static),
    )
    return runtime._UNDEFINED


def _construct_bitmap(context, args):
    bitmap = _bitmap_from(context.movie, args[0]) if args else None
    token = dynamic._next_token(context.movie)
    obj = dynamic.DynamicDisplayObject(token, "Bitmap", "flash.display.Bitmap")
    obj.name = f"Bitmap{token}"
    obj.width = float(bitmap.width if bitmap is not None else 1)
    obj.height = float(bitmap.height if bitmap is not None else 1)
    obj.extras.update(
        bitmapData=bitmap,
        pixelSnapping=str(args[1] if len(args) > 1 else "auto"),
        smoothing=bool(args[2]) if len(args) > 2 else False,
    )
    if not dynamic._register_object(context.movie, obj, context.path):
        return runtime._UNDEFINED
    return obj


def _bitmap_call(context, bitmap, lower, args):
    mutation = False
    try:
        if lower == "getpixel" and len(args) >= 2:
            return bitmap.get_pixel(args[0], args[1], False)
        if lower == "getpixel32" and len(args) >= 2:
            return bitmap.get_pixel(args[0], args[1], True)
        if lower == "setpixel" and len(args) >= 3:
            mutation = bitmap.set_pixel(args[0], args[1], args[2], False)
        elif lower == "setpixel32" and len(args) >= 3:
            mutation = bitmap.set_pixel(args[0], args[1], args[2], True)
        elif lower == "fillrect" and len(args) >= 2:
            mutation = bitmap.fill_rect(args[0], args[1])
        elif lower == "copypixels" and len(args) >= 3:
            source = _bitmap_from(context.movie, args[0])
            mutation = bitmap.copy_pixels(
                source, args[1], args[2], bool(args[5]) if len(args) > 5 else False,
            ) if source is not None else False
        elif lower == "draw" and args:
            source = _bitmap_from(context.movie, args[0])
            mutation = bitmap.draw_bitmap(
                source,
                _matrix_tuple(context, args[1]) if len(args) > 1 else None,
                bool(args[5]) if len(args) > 5 else False,
                args[4] if len(args) > 4 else None,
            ) if source is not None else False
        elif lower == "scroll" and len(args) >= 2:
            bitmap.scroll(args[0], args[1])
            mutation = True
        elif lower == "floodfill" and len(args) >= 3:
            mutation = bitmap.flood_fill(args[0], args[1], args[2])
        elif lower == "clone":
            return bitmap.clone()
        elif lower == "dispose":
            bitmap.dispose()
            mutation = True
        elif lower == "lock":
            bitmap.locked = True
            return runtime._UNDEFINED
        elif lower == "unlock":
            bitmap.locked = False
            bitmap.touch()
            mutation = True
        else:
            return None
    except Exception as exc:
        runtime._error(context.movie, context.path, f"BitmapData.{lower}", exc)
        return runtime._UNDEFINED
    if mutation:
        dynamic._touch(context.movie)
        precise.clear_geometry_cache()
    return runtime._UNDEFINED


def _is_graphics_definition(definition):
    vector_type = getattr(ui_browser, "VectorShapeDef", ())
    return isinstance(definition, (ui_browser.SpriteDef, ui_browser.ShapeDef)) or (
        bool(vector_type) and isinstance(definition, vector_type)
    )


def get_property(context, receiver, name):
    short = _short(name)
    lower = short.lower()
    if isinstance(receiver, complete.PreviewBitmapData):
        if lower == "width":
            return int(receiver.width)
        if lower == "height":
            return int(receiver.height)
        if lower == "transparent":
            return bool(receiver.transparent)
        if lower == "rect":
            return dict(receiver.rect)
    if isinstance(receiver, runtime.RuntimeRef):
        try:
            obj = dynamic._dynamic_for_path(context.movie, receiver.path)
        except Exception:
            obj = None
        if obj is not None:
            receiver = obj
        elif lower == "graphics" and _is_graphics_definition(receiver.definition):
            return CompleteGraphicsProxy(context.movie, receiver.path, None, True)
    if isinstance(receiver, dynamic.DynamicDisplayObject):
        if lower == "graphics" and receiver.kind in ("Shape", "MovieClip", "DisplayObject"):
            return CompleteGraphicsProxy(context.movie, receiver.path, receiver, False)
        if receiver.kind == "Bitmap":
            if lower == "bitmapdata":
                return receiver.extras.get("bitmapData", runtime._UNDEFINED)
            if lower == "smoothing":
                return bool(receiver.extras.get("smoothing", False))
            if lower == "pixelsnapping":
                return str(receiver.extras.get("pixelSnapping", "auto"))
    return _BASE["get"](context, receiver, name)


def set_property(context, reference, name, value):
    lower = _short(name).lower()
    target = reference
    if isinstance(reference, runtime.RuntimeRef):
        try:
            target = dynamic._dynamic_for_path(context.movie, reference.path) or reference
        except Exception:
            target = reference
    if isinstance(target, dynamic.DynamicDisplayObject) and target.kind == "Bitmap":
        if lower == "bitmapdata":
            bitmap = _bitmap_from(context.movie, value)
            target.extras["bitmapData"] = bitmap
            target.width = float(bitmap.width if bitmap is not None else 1)
            target.height = float(bitmap.height if bitmap is not None else 1)
            context.writes += 1
            dynamic._touch(context.movie)
            precise.clear_geometry_cache()
            return True
        if lower in ("smoothing", "pixelsnapping"):
            target.extras["smoothing" if lower == "smoothing" else "pixelSnapping"] = (
                bool(value) if lower == "smoothing" else str(value or "auto")
            )
            context.writes += 1
            dynamic._touch(context.movie)
            return True
    return _BASE["set"](context, reference, name, value)


def call_value(context, receiver, name, args):
    lower = _short(name).lower()
    args = tuple(args or ())
    if isinstance(receiver, runtime.RuntimeGlobal):
        if lower == "bitmapdata":
            try:
                return complete.PreviewBitmapData(
                    args[0] if args else 1,
                    args[1] if len(args) > 1 else 1,
                    bool(args[2]) if len(args) > 2 else True,
                    args[3] if len(args) > 3 else 0xFFFFFFFF,
                )
            except Exception as exc:
                runtime._error(context.movie, context.path, "BitmapData", exc)
                return runtime._UNDEFINED
        if lower == "bitmap":
            return _construct_bitmap(context, args)
    if isinstance(receiver, complete.PreviewBitmapData):
        result = _bitmap_call(context, receiver, lower, args)
        if result is not None:
            return result
    if isinstance(receiver, CompleteGraphicsProxy):
        return _invoke_graphics(context, receiver, name, args)
    if isinstance(receiver, graphics.GraphicsProxy):
        return _invoke_graphics(
            context, CompleteGraphicsProxy(receiver.movie, receiver.path, receiver.target, False),
            name, args,
        )
    return _BASE["call"](context, receiver, name, args)


def _paint_bitmap_layer(paint, size, origin, supersample):
    if Image is None or not isinstance(paint, complete.BitmapPaint):
        return None
    bitmap = paint.bitmap
    if bitmap.disposed or bitmap.image is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    source = bitmap.image
    matrix = paint.matrix or (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    inverse = ui_browser.Affine(*matrix).inverse_pillow()
    if inverse is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    ia, ib, ic, id_, ie, iff = inverse
    affine = (
        ia / supersample, ib / supersample,
        ia * origin[0] + ib * origin[1] + ic,
        id_ / supersample, ie / supersample,
        id_ * origin[0] + ie * origin[1] + iff,
    )
    if paint.repeat:
        corners = ((0.0, 0.0), (size[0], 0.0), (size[0], size[1]), (0.0, size[1]))
        mapped = [
            (affine[0] * x + affine[1] * y + affine[2], affine[3] * x + affine[4] * y + affine[5])
            for x, y in corners
        ]
        left = math.floor(min(value[0] for value in mapped) / source.width) * source.width
        top = math.floor(min(value[1] for value in mapped) / source.height) * source.height
        right = math.ceil(max(value[0] for value in mapped) / source.width) * source.width + source.width
        bottom = math.ceil(max(value[1] for value in mapped) / source.height) * source.height + source.height
        width, height = max(1, int(right - left)), max(1, int(bottom - top))
        tile_count = ((width + source.width - 1) // source.width) * ((height + source.height - 1) // source.height)
        if (
            width > complete.MAX_BITMAP_DIMENSION or height > complete.MAX_BITMAP_DIMENSION
            or width * height > complete.MAX_BITMAP_PIXELS or tile_count > 65_536
        ):
            return Image.new("RGBA", size, (0, 0, 0, 0))
        tiled = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        for y in range(0, height, source.height):
            for x in range(0, width, source.width):
                tiled.alpha_composite(source, (x, y))
        source = tiled
        affine = (affine[0], affine[1], affine[2] - left, affine[3], affine[4], affine[5] - top)
    transform_mode = getattr(getattr(Image, "Transform", Image), "AFFINE")
    resampling_group = getattr(Image, "Resampling", Image)
    resampling = getattr(resampling_group, "BILINEAR" if paint.smooth else "NEAREST")
    return source.transform(size, transform_mode, affine, resample=resampling)


def _fill_mask(size, contours, origin, supersample, winding="evenOdd"):
    if Image is None or ImageDraw is None:
        return None
    if str(winding).lower() == "nonzero" or ImageChops is None:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        for points, _closed in contours:
            if len(points) >= 3:
                draw.polygon(
                    [((x - origin[0]) * supersample, (y - origin[1]) * supersample) for x, y in points],
                    fill=255,
                )
        return mask
    return graphics._fill_mask(size, contours, origin, supersample)


def _triangle_bitmap_layer(paint, metadata, size, origin, supersample):
    if Image is None or not isinstance(paint, complete.BitmapPaint):
        return None
    bitmap = paint.bitmap
    if bitmap.disposed or bitmap.image is None:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    points = tuple(metadata.get("triangle", ()))
    uvt = tuple(metadata.get("uvt", ()))
    if len(points) != 3 or len(uvt) != 3:
        return None
    destination = [((x - origin[0]) * supersample, (y - origin[1]) * supersample) for x, y in points]
    min_x = max(0, int(math.floor(min(point[0] for point in destination))))
    max_x = min(size[0] - 1, int(math.ceil(max(point[0] for point in destination))))
    min_y = max(0, int(math.floor(min(point[1] for point in destination))))
    max_y = min(size[1] - 1, int(math.ceil(max(point[1] for point in destination))))
    if max_x < min_x or max_y < min_y:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    if (max_x - min_x + 1) * (max_y - min_y + 1) > _MAX_TRIANGLE_SAMPLE_PIXELS:
        return None
    x0, y0 = destination[0]
    x1, y1 = destination[1]
    x2, y2 = destination[2]
    denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
    if abs(denominator) < 1e-12:
        return Image.new("RGBA", size, (0, 0, 0, 0))
    source = bitmap.image
    output = Image.new("RGBA", size, (0, 0, 0, 0))
    pixels = output.load()
    source_pixels = source.load()
    for py in range(min_y, max_y + 1):
        for px in range(min_x, max_x + 1):
            sample_x, sample_y = px + 0.5, py + 0.5
            w0 = ((y1 - y2) * (sample_x - x2) + (x2 - x1) * (sample_y - y2)) / denominator
            w1 = ((y2 - y0) * (sample_x - x2) + (x0 - x2) * (sample_y - y2)) / denominator
            w2 = 1.0 - w0 - w1
            if w0 < -1e-7 or w1 < -1e-7 or w2 < -1e-7:
                continue
            perspective = w0 * uvt[0][2] + w1 * uvt[1][2] + w2 * uvt[2][2]
            if abs(perspective) < 1e-12:
                continue
            u = (w0 * uvt[0][0] * uvt[0][2] + w1 * uvt[1][0] * uvt[1][2] + w2 * uvt[2][0] * uvt[2][2]) / perspective
            v = (w0 * uvt[0][1] * uvt[0][2] + w1 * uvt[1][1] * uvt[1][2] + w2 * uvt[2][1] * uvt[2][2]) / perspective
            if paint.repeat:
                u, v = u % 1.0, v % 1.0
            elif not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
                continue
            sx = max(0, min(source.width - 1, int(round(u * max(0, source.width - 1)))))
            sy = max(0, min(source.height - 1, int(round(v * max(0, source.height - 1)))))
            pixels[px, py] = source_pixels[sx, sy]
    return output


def _paint_layer(paint, bounds, size, origin, supersample, metadata=None):
    if isinstance(paint, complete.BitmapPaint):
        triangle = _triangle_bitmap_layer(paint, metadata or {}, size, origin, supersample)
        return triangle if triangle is not None else _paint_bitmap_layer(paint, size, origin, supersample)
    if getattr(paint, "kind", "") == "solid":
        return Image.new("RGBA", size, graphics._rgba(paint.color, paint.alpha))
    if paint is not None:
        return visual_patch.gradient_layer(graphics._gradient_style(paint, bounds), size, origin, supersample)
    return Image.new("RGBA", size, (0, 0, 0, 0))


def rasterize(state):
    if Image is None or ImageDraw is None:
        return None
    model.seal(state)
    key = (id(state), int(state.revision), complete.state_resource_revision(state), "complete")
    cached = graphics._RASTER_CACHE.get(key)
    if cached is not None and cached[0] is state:
        graphics._RASTER_CACHE.move_to_end(key)
        return cached[1], cached[2], cached[3], True
    bounds = model.state_bounds(state)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    origin = (float(math.floor(left)), float(math.floor(top)))
    width = max(1, int(math.ceil(right - origin[0])))
    height = max(1, int(math.ceil(bottom - origin[1])))
    if (
        width > graphics._MAX_RASTER_DIMENSION or height > graphics._MAX_RASTER_DIMENSION
        or width * height > graphics._MAX_RASTER_PIXELS
    ):
        return None
    supersample = 2
    if width * supersample > graphics._MAX_RASTER_DIMENSION or height * supersample > graphics._MAX_RASTER_DIMENSION:
        supersample = 1
    size = (width * supersample, height * supersample)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))

    for primitive in state.primitives:
        contours = model.flatten_primitive(primitive)
        metadata = complete.primitive_metadata(state, primitive)
        if primitive.fill is not None:
            layer = _paint_layer(primitive.fill, bounds, size, origin, supersample, metadata)
            if layer is not None:
                if isinstance(primitive.fill, complete.BitmapPaint) and metadata.get("uvt"):
                    canvas.alpha_composite(layer)
                else:
                    mask = _fill_mask(size, contours, origin, supersample, metadata.get("winding", "evenOdd"))
                    if mask is not None and mask.getbbox() is not None:
                        alpha = layer.getchannel("A")
                        alpha = ImageChops.multiply(alpha, mask) if ImageChops is not None else mask
                        layer.putalpha(alpha)
                        canvas.alpha_composite(layer)
        if primitive.line is not None:
            line = primitive.line
            line_width = max(1, int(round(float(line.thickness) * supersample)))
            mask = Image.new("L", size, 0)
            draw = ImageDraw.Draw(mask)
            for points, closed in contours:
                if len(points) < 2:
                    continue
                scaled = [((x - origin[0]) * supersample, (y - origin[1]) * supersample) for x, y in points]
                try:
                    draw.line(scaled, fill=255, width=line_width, joint="curve")
                except TypeError:
                    draw.line(scaled, fill=255, width=line_width)
                if closed and scaled[-1] != scaled[0]:
                    draw.line((scaled[-1], scaled[0]), fill=255, width=line_width)
            paint = getattr(line, "paint", None)
            stroke = (
                Image.new("RGBA", size, graphics._rgba(line.color, line.alpha))
                if paint is None else _paint_layer(paint, bounds, size, origin, supersample, metadata)
            )
            if stroke is not None and mask.getbbox() is not None:
                alpha = stroke.getchannel("A")
                alpha = ImageChops.multiply(alpha, mask) if ImageChops is not None else mask
                stroke.putalpha(alpha)
                canvas.alpha_composite(stroke)

    if supersample > 1:
        canvas = canvas.resize(
            (width, height), getattr(getattr(Image, "Resampling", Image), "LANCZOS"),
        )
    local_bounds = (origin[0], origin[1], origin[0] + canvas.width, origin[1] + canvas.height)
    old = graphics._RASTER_CACHE.pop(key, None)
    if old is not None:
        graphics._RASTER_CACHE_BYTES -= old[1].width * old[1].height * 4
    graphics._RASTER_CACHE[key] = (state, canvas, origin, local_bounds)
    graphics._RASTER_CACHE.move_to_end(key)
    graphics._RASTER_CACHE_BYTES += canvas.width * canvas.height * 4
    while graphics._RASTER_CACHE and graphics._RASTER_CACHE_BYTES > graphics._RASTER_CACHE_MAX_BYTES:
        _old_key, old = graphics._RASTER_CACHE.popitem(last=False)
        graphics._RASTER_CACHE_BYTES -= old[1].width * old[1].height * 4
    return canvas, origin, local_bounds, False


def _draw_state(renderer, canvas, state, matrix, color):
    value = rasterize(state)
    if value is None:
        return False
    image, origin, _bounds, cache_hit = value
    image = renderer._apply_color(image, color)
    shape_patch._draw_transformed_image(
        renderer, canvas, image,
        matrix.then(ui_browser.Affine(1, 0, 0, 1, origin[0], origin[1])),
    )
    renderer.stats.graphics_static_objects = getattr(renderer.stats, "graphics_static_objects", 0) + 1
    if cache_hit:
        renderer.stats.graphics_static_cache_hits = getattr(renderer.stats, "graphics_static_cache_hits", 0) + 1
    return True


def draw_display(renderer, canvas, display, parent_matrix, parent_color, stack, level):
    result = _BASE["draw_display"](
        renderer, canvas, display, parent_matrix, parent_color, stack, level,
    )
    parent_path = getattr(renderer, "_ui_state_parent_path", "root") or "root"
    normalized = overrides_patch.normalize_overrides(
        getattr(renderer.movie, "ui_state_overrides", {}) or {},
    )
    for depth in sorted(display):
        raw = display[depth]
        try:
            item, path, _manual = overrides_patch.apply_item_override(
                renderer.movie, parent_path, depth, raw, normalized,
            )
        except Exception:
            item = raw
            path = overrides_patch.state_item_path(renderer.movie, parent_path, depth, raw)
        if not bool(getattr(item, "visible", True)):
            continue
        clip_depth = getattr(item, "clip_depth", None)
        if clip_depth is not None and int(clip_depth) > int(depth):
            continue
        state = _static_state(renderer.movie, path)
        if not isinstance(state, model.GraphicsState) or not (state.primitives or state.current_commands):
            continue
        matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
        color = parent_color.combine(getattr(item, "color", ui_browser.IDENTITY_COLOR))
        _draw_state(renderer, canvas, state, matrix, color)
    return result


def draw_dynamic(renderer, canvas, obj, parent_matrix, parent_color, stack, level):
    if obj.kind != "Bitmap":
        return _BASE["draw_dynamic"](renderer, canvas, obj, parent_matrix, parent_color, stack, level)
    bitmap = obj.extras.get("bitmapData")
    if isinstance(bitmap, complete.PreviewBitmapData) and not bitmap.disposed and bitmap.image is not None and obj.visible:
        matrix = parent_matrix.then(dynamic._matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation))
        color = parent_color.combine(ui_browser.ColorTransform(a_mult=max(0.0, min(1.0, obj.alpha))))
        image = renderer._apply_color(bitmap.image, color)
        shape_patch._draw_transformed_image(renderer, canvas, image, matrix)
        renderer.stats.bitmapdata_objects = getattr(renderer.stats, "bitmapdata_objects", 0) + 1
    old = renderer.show_placeholders
    renderer.show_placeholders = False
    try:
        return _BASE["draw_dynamic"](renderer, canvas, obj, parent_matrix, parent_color, stack, level)
    finally:
        renderer.show_placeholders = old


def geometry_display(collector, display, parent_matrix, parent_path, inherited_clips, stack,
                     sink=None, owner_path=None):
    result = _BASE["geometry_display"](
        collector, display, parent_matrix, parent_path, inherited_clips, stack, sink, owner_path,
    )
    target_sink = collector.geometries if sink is None else sink
    active_masks = []
    for depth in sorted(display):
        active_masks = [value for value in active_masks if int(depth) <= value[0]]
        raw = display[depth]
        try:
            item, path, _manual = overrides_patch.apply_item_override(
                collector.movie, parent_path, depth, raw, collector.overrides,
            )
        except Exception:
            item = raw
            path = overrides_patch.state_item_path(collector.movie, parent_path, depth, raw)
        if not bool(getattr(item, "visible", True)):
            continue
        matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
        character_id = getattr(item, "character_id", None)
        definition = collector.movie.definitions.get(character_id) if character_id is not None else None
        clips = tuple(inherited_clips) + tuple(value[1] for value in active_masks)
        clip_depth = getattr(item, "clip_depth", None)
        if clip_depth is not None and int(clip_depth) > int(depth):
            geoms = collector._mask_geometry(item, definition, matrix, path, clips, stack)
            if geoms:
                active_masks.append((int(clip_depth), classic.HitClip(geoms, "clipDepth")))
            continue
        state = _static_state(collector.movie, path)
        if not isinstance(state, model.GraphicsState) or not (state.primitives or state.current_commands):
            continue
        value = rasterize(state)
        if value is None:
            continue
        image, origin, bounds, _cache_hit = value
        object_clips = hit_base._scroll_clip(collector.movie, path, matrix, clips)
        geometry = hit_base._alpha_geometry(
            path, matrix, bounds, image.getchannel("A"), origin,
            object_clips, "static-graphics-alpha", character_id,
        )
        before = len(collector.geometries)
        collector.add(
            geometry, getattr(item, "name", ""),
            bool(getattr(item, "_ui_enabled", True) and getattr(item, "_ui_mouse_enabled", True)),
            bool(getattr(item, "_ui_tab_enabled", False)), False,
        )
        if target_sink is not collector.geometries and len(collector.geometries) > before:
            target_sink.extend(collector.geometries[before:])
            del collector.geometries[before:]
        collector.static_graphics_count = int(getattr(collector, "static_graphics_count", 0)) + 1
    return result


def dynamic_children_geometry(collector, parent_path, parent_matrix, clips, stack, sink):
    result = _BASE["dynamic_geometry"](
        collector, parent_path, parent_matrix, clips, stack, sink,
    )
    target_sink = collector.geometries if sink is None else sink
    for obj in dynamic._children(collector.movie, parent_path):
        if obj.kind != "Bitmap" or not bool(getattr(obj, "visible", True)):
            continue
        bitmap = obj.extras.get("bitmapData")
        if not isinstance(bitmap, complete.PreviewBitmapData) or bitmap.disposed or bitmap.image is None:
            continue
        matrix = parent_matrix.then(dynamic._matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation))
        object_clips = hit_base._scroll_clip(collector.movie, obj.path, matrix, clips)
        target_sink[:] = [
            value for value in target_sink
            if not (str(getattr(value, "path", "")) == obj.path and str(getattr(value, "kind", "")) == "dynamic-bounds")
        ]
        bounds = (0.0, 0.0, float(bitmap.width), float(bitmap.height))
        geometry = hit_base._alpha_geometry(
            obj.path, matrix, bounds, bitmap.image.getchannel("A"), (0.0, 0.0),
            object_clips, "bitmapdata-alpha", None,
        )
        before = len(collector.geometries)
        collector.add(
            geometry, obj.name, obj.enabled and obj.mouse_enabled,
            obj.tab_enabled, True,
        )
        if target_sink is not collector.geometries and len(collector.geometries) > before:
            target_sink.extend(collector.geometries[before:])
            del collector.geometries[before:]
    return result


def _decorate_nodes(movie, nodes):
    states = _static_store(movie)["states"]
    result = []
    for node in tuple(nodes or ()):
        metadata = dict(node.metadata)
        children = _decorate_nodes(movie, node.children)
        state = states.get(node.path)
        if isinstance(state, model.GraphicsState) and (state.primitives or state.current_commands):
            model.seal(state)
            metadata["graphics_complete"] = {
                "commands": int(state.command_count),
                "primitives": len(state.primitives),
                "bounds": model.state_bounds(state),
                "rejected": int(state.rejected),
                "static": True,
            }
        result.append(inspector.StateNode(
            node.path, node.depth, node.label, node.kind, node.visible,
            node.character_id, node.class_name, metadata, children,
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    return _decorate_nodes(movie, _BASE["inspect"](movie, frame, max_depth))


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    value = node.metadata.get("graphics_complete")
    if not value:
        if node.kind == "DynamicBitmap":
            return text + "\n\nBitmapData-Instanz"
        return text
    return text + "\n\nAVM2 Graphics (Timeline-Instanz):\n" + (
        f"- Befehle: {value.get('commands', 0)}\n"
        f"- Primitive: {value.get('primitives', 0)}\n"
        f"- Bounds: {value.get('bounds')}\n"
        f"- Abgewiesen: {value.get('rejected', 0)}"
    )


def format_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    static_states = [
        value for value in _static_store(movie)["states"].values()
        if isinstance(value, model.GraphicsState) and (value.primitives or value.current_commands)
    ]
    bitmaps = 0
    bitmap_bytes = 0
    for obj in dynamic._state(movie)["objects"].values():
        bitmap = obj.extras.get("bitmapData")
        if isinstance(bitmap, complete.PreviewBitmapData) and not bitmap.disposed:
            bitmaps += 1
            bitmap_bytes += int(bitmap.width) * int(bitmap.height) * 4
    if not static_states and not bitmaps:
        return text
    return text + "\n\nGraphics-Abschluss:\n" + (
        f"- Timeline-Graphics: {len(static_states)}\n"
        f"- BitmapData-Objekte: {bitmaps} ({bitmap_bytes / 1048576.0:.2f} MiB)\n"
        f"- Gerenderte Timeline-Overlays: {getattr(stats, 'graphics_static_objects', 0)}\n"
        f"- Gerenderte Bitmap-Objekte: {getattr(stats, 'bitmapdata_objects', 0)}"
    )


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_avm2_static_graphics = None
    clear_complete_graphics_cache()
    return _BASE["reset"](owner)


def clear_complete_graphics_cache():
    graphics.clear_graphics_cache()
    precise.clear_geometry_cache()


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        get=runtime._get_property,
        set=runtime._set_property,
        call=runtime._call,
        draw_display=ui_browser.UIRenderer._draw_display,
        draw_dynamic=dynamic._draw_dynamic,
        geometry_display=hit_geometry.GeometryCollector._display,
        dynamic_geometry=hit_geometry.GeometryCollector._dynamic_children,
        inspect=inspector.inspect_movie_state,
        format_node=inspector.format_state_node,
        info=ui_browser.UIBrowser._format_info,
        reset=runtime.reset_runtime,
    )

    runtime._get_property = get_property
    runtime._set_property = set_property
    runtime._call = call_value
    graphics._rasterize = rasterize
    ui_browser.UIRenderer._draw_display = draw_display
    dynamic._draw_dynamic = draw_dynamic
    hit_geometry.GeometryCollector._display = geometry_display
    hit_geometry.GeometryCollector._dynamic_children = dynamic_children_geometry
    inspector.inspect_movie_state = inspect_movie_state
    inspector.format_state_node = format_state_node
    ui_browser.inspect_movie_state = inspect_movie_state
    ui_browser.UIBrowser._format_info = format_info
    runtime.reset_runtime = reset_runtime
    try:
        import ui_browser_avm2_lifecycle_patch as lifecycle
        lifecycle.reset_runtime = reset_runtime
    except Exception:
        pass
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime
    ui_browser.CompleteAVM2GraphicsProxy = CompleteGraphicsProxy
    ui_browser.PreviewBitmapData = complete.PreviewBitmapData
    ui_browser.clear_ui_graphics_complete_cache = clear_complete_graphics_cache
