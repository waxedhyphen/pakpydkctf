"""Bounded AVM2 Graphics rendering and precise hit geometry for dynamic display objects."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_hit_geometry as hit_geometry
import ui_browser_hit_geometry_base as hit_base
import ui_browser_precise_hit as precise
import ui_browser_shape_patch as shape_patch
import ui_browser_state_inspector_patch as inspector
import ui_browser_visual_formats as visual
import ui_browser_visual_formats_patch as visual_patch
import ui_browser_graphics_model as model

try:
    from PIL import Image, ImageChops, ImageDraw
except Exception:
    Image = None
    ImageChops = None
    ImageDraw = None


_INSTALLED = False
_BASE = {}
_RASTER_CACHE = OrderedDict()
_RASTER_CACHE_BYTES = 0
_RASTER_CACHE_MAX_BYTES = 64 * 1024 * 1024
_MAX_RASTER_DIMENSION = 8192
_MAX_RASTER_PIXELS = 32_000_000


@dataclass(frozen=True)
class GraphicsProxy:
    movie: object
    path: str
    target: dynamic.DynamicDisplayObject


def _movie_state(movie):
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    value = getattr(movie, "ui_avm2_graphics_state", None)
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {
            "generation": generation,
            "revision": 0,
            "calls": 0,
            "rejected": 0,
            "rendered": 0,
            "cache_hits": 0,
        }
        movie.ui_avm2_graphics_state = value
    return value


def _graphics_state(obj, create=True):
    value = obj.extras.get("_graphics_state")
    if not isinstance(value, model.GraphicsState) and create:
        value = model.GraphicsState()
        obj.extras["_graphics_state"] = value
    return value if isinstance(value, model.GraphicsState) else None


def _touch(proxy):
    values = _movie_state(proxy.movie)
    values["revision"] = int(values.get("revision", 0)) + 1
    dynamic._touch(proxy.movie)
    precise.clear_geometry_cache()


def _short(value):
    return str(value or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]


def _sequence(value):
    if value is None or value is runtime._UNDEFINED:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    if isinstance(value, dict):
        numeric = []
        for key, item in value.items():
            try:
                numeric.append((int(key), item))
            except Exception:
                continue
        return tuple(item for _key, item in sorted(numeric))
    try:
        return tuple(value)
    except Exception:
        return ()


def _matrix_tuple(context, value):
    if value is None or value is runtime._UNDEFINED:
        return None
    if isinstance(value, ui_browser.Affine):
        return (value.a, value.b, value.c, value.d, value.tx, value.ty)
    if isinstance(value, dict):
        get = value.get
    elif isinstance(value, dynamic.DynamicDisplayObject):
        get = lambda key, default=0.0: value.extras.get(key, getattr(value, key, default))
    elif isinstance(value, runtime.RuntimeRef):
        props = runtime._properties(context.movie).get(value.path, {}) or {}
        get = props.get
    else:
        get = lambda key, default=0.0: getattr(value, key, default)
    try:
        return (
            float(get("a", 1.0)), float(get("b", 0.0)),
            float(get("c", 0.0)), float(get("d", 1.0)),
            float(get("tx", 0.0)), float(get("ty", 0.0)),
        )
    except Exception:
        return None


def get_property(context, receiver, name):
    short = _short(name)
    if short == "graphics":
        if isinstance(receiver, runtime.RuntimeRef):
            found = dynamic._dynamic_for_path(context.movie, receiver.path)
            if found is not None:
                receiver = found
        if isinstance(receiver, dynamic.DynamicDisplayObject) and receiver.kind in (
            "Shape", "MovieClip", "DisplayObject",
        ):
            return GraphicsProxy(context.movie, receiver.path, receiver)
        return runtime._UNDEFINED
    return _BASE["get"](context, receiver, name)


def _invoke_graphics(context, proxy, name, args):
    state = _graphics_state(proxy.target)
    lower = _short(name).lower()
    values = _movie_state(proxy.movie)
    values["calls"] = int(values.get("calls", 0)) + 1
    before_rejected = state.rejected

    if lower == "clear":
        model.clear(state)
    elif lower == "beginfill":
        model.begin_fill(state, args[0] if args else 0, args[1] if len(args) > 1 else 1.0)
    elif lower == "begingradientfill":
        model.begin_gradient_fill(
            state,
            args[0] if args else "linear",
            _sequence(args[1]) if len(args) > 1 else (),
            _sequence(args[2]) if len(args) > 2 else (),
            _sequence(args[3]) if len(args) > 3 else (),
            _matrix_tuple(context, args[4]) if len(args) > 4 else None,
            args[5] if len(args) > 5 else "pad",
            args[6] if len(args) > 6 else "rgb",
            args[7] if len(args) > 7 else 0.0,
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
    else:
        values["rejected"] = int(values.get("rejected", 0)) + 1
        return runtime._UNDEFINED

    if state.rejected > before_rejected:
        values["rejected"] = int(values.get("rejected", 0)) + state.rejected - before_rejected
    context.writes += 1
    _touch(proxy)
    runtime._log(
        proxy.movie, "graphics", path=proxy.path, method=_short(name),
        commands=state.command_count, primitives=len(state.primitives),
    )
    return runtime._UNDEFINED


def call_value(context, receiver, name, args):
    if isinstance(receiver, GraphicsProxy):
        return _invoke_graphics(context, receiver, name, tuple(args or ()))
    return _BASE["call"](context, receiver, name, args)


def _rgba(color, alpha):
    value = int(color or 0) & 0xFFFFFF
    return (
        (value >> 16) & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
        max(0, min(255, int(round(float(alpha) * 255.0)))),
    )


def _gradient_style(fill, bounds):
    stops = tuple(
        shape_patch.GradientStop(int(ratio), _rgba(color, alpha))
        for color, alpha, ratio in zip(fill.colors, fill.alphas, fill.ratios)
    )
    matrix = fill.matrix
    if matrix is None:
        left, top, right, bottom = bounds
        width, height = max(1.0, right - left), max(1.0, bottom - top)
        radius = float(shape_patch._GRADIENT_RADIUS_PIXELS)
        matrix = (
            width / (2.0 * radius), 0.0, 0.0, height / (2.0 * radius),
            (left + right) / 2.0, (top + bottom) / 2.0,
        )
    affine = ui_browser.Affine(*matrix)
    spread = {"pad": 0, "reflect": 1, "repeat": 2}.get(str(fill.spread).lower(), 0)
    interpolation = 1 if str(fill.interpolation).lower() in (
        "linearrgb", "linear_rgb", "linear-rgb",
    ) else 0
    kind = {
        "linear": "linear_gradient",
        "radial": "radial_gradient",
        "focal": "focal_gradient",
    }.get(fill.kind, "linear_gradient")
    return visual.EnhancedVectorFillStyle(
        kind=kind, matrix=affine, stops=stops, spread_mode=spread,
        interpolation_mode=interpolation,
        fill_type=0x13 if kind == "focal_gradient" else (
            0x12 if kind == "radial_gradient" else 0x10
        ), focal_point=float(fill.focal),
    )


def _fill_mask(size, contours, origin, supersample):
    if Image is None or ImageDraw is None:
        return None
    if ImageChops is None:
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        for points, _closed in contours:
            if len(points) >= 3:
                draw.polygon(
                    [((x - origin[0]) * supersample, (y - origin[1]) * supersample)
                     for x, y in points],
                    fill=255,
                )
        return mask
    result = Image.new("1", size, 0)
    for points, _closed in contours:
        if len(points) < 3:
            continue
        contour = Image.new("1", size, 0)
        ImageDraw.Draw(contour).polygon(
            [((x - origin[0]) * supersample, (y - origin[1]) * supersample)
             for x, y in points],
            fill=1,
        )
        result = ImageChops.logical_xor(result, contour)
    return result.convert("L")


def _rasterize(state):
    global _RASTER_CACHE_BYTES
    if Image is None or ImageDraw is None:
        return None
    model.seal(state)
    key = (id(state), int(state.revision))
    cached = _RASTER_CACHE.get(key)
    if cached is not None and cached[0] is state:
        _RASTER_CACHE.move_to_end(key)
        return cached[1], cached[2], cached[3], True

    bounds = model.state_bounds(state)
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    origin = (float(math.floor(left)), float(math.floor(top)))
    width = max(1, int(math.ceil(right - origin[0])))
    height = max(1, int(math.ceil(bottom - origin[1])))
    if (
        width > _MAX_RASTER_DIMENSION or height > _MAX_RASTER_DIMENSION
        or width * height > _MAX_RASTER_PIXELS
    ):
        return None
    supersample = 2
    if width * supersample > _MAX_RASTER_DIMENSION or height * supersample > _MAX_RASTER_DIMENSION:
        supersample = 1
    size = (width * supersample, height * supersample)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))

    for primitive in state.primitives:
        contours = model.flatten_primitive(primitive)
        if primitive.fill is not None:
            mask = _fill_mask(size, contours, origin, supersample)
            if mask is not None and mask.getbbox() is not None:
                if primitive.fill.kind == "solid":
                    layer = Image.new("RGBA", size, _rgba(primitive.fill.color, primitive.fill.alpha))
                else:
                    style = _gradient_style(primitive.fill, bounds)
                    layer = visual_patch.gradient_layer(style, size, origin, supersample)
                alpha = layer.getchannel("A")
                if ImageChops is not None:
                    alpha = ImageChops.multiply(alpha, mask)
                else:
                    alpha = mask
                layer.putalpha(alpha)
                canvas.alpha_composite(layer)
        if primitive.line is not None:
            draw = ImageDraw.Draw(canvas, "RGBA")
            line = primitive.line
            line_width = max(1, int(round(line.thickness * supersample)))
            color = _rgba(line.color, line.alpha)
            for points, _closed in contours:
                if len(points) < 2:
                    continue
                scaled = [
                    ((x - origin[0]) * supersample, (y - origin[1]) * supersample)
                    for x, y in points
                ]
                try:
                    draw.line(scaled, fill=color, width=line_width, joint="curve")
                except TypeError:
                    draw.line(scaled, fill=color, width=line_width)

    if supersample > 1:
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        canvas = canvas.resize((width, height), resampling)
    local_bounds = (
        origin[0], origin[1], origin[0] + canvas.width, origin[1] + canvas.height,
    )
    _RASTER_CACHE[key] = (state, canvas, origin, local_bounds)
    _RASTER_CACHE.move_to_end(key)
    _RASTER_CACHE_BYTES += canvas.width * canvas.height * 4
    while _RASTER_CACHE and _RASTER_CACHE_BYTES > _RASTER_CACHE_MAX_BYTES:
        _old_key, old = _RASTER_CACHE.popitem(last=False)
        _RASTER_CACHE_BYTES -= old[1].width * old[1].height * 4
    return canvas, origin, local_bounds, False


def draw_dynamic(renderer, canvas, obj, parent_matrix, parent_color, stack, level):
    state = _graphics_state(obj, False)
    if state is None or not (state.primitives or state.current_commands) or not obj.visible:
        return _BASE["draw_dynamic"](renderer, canvas, obj, parent_matrix, parent_color, stack, level)

    local = dynamic._matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation)
    matrix = parent_matrix.then(local)
    raster = _rasterize(state)
    if raster is not None:
        image, origin, _bounds, cache_hit = raster
        color = parent_color.combine(
            ui_browser.ColorTransform(a_mult=max(0.0, min(1.0, obj.alpha)))
        )
        image = renderer._apply_color(image, color)
        shape_patch._draw_transformed_image(
            renderer, canvas, image,
            matrix.then(ui_browser.Affine(1, 0, 0, 1, origin[0], origin[1])),
        )
        renderer.stats.graphics_objects = getattr(renderer.stats, "graphics_objects", 0) + 1
        renderer.stats.graphics_primitives = getattr(renderer.stats, "graphics_primitives", 0) + len(state.primitives)
        values = _movie_state(renderer.movie)
        values["rendered"] = int(values.get("rendered", 0)) + 1
        if cache_hit:
            values["cache_hits"] = int(values.get("cache_hits", 0)) + 1

    old_placeholders = renderer.show_placeholders
    renderer.show_placeholders = False
    try:
        return _BASE["draw_dynamic"](
            renderer, canvas, obj, parent_matrix, parent_color, stack, level,
        )
    finally:
        renderer.show_placeholders = old_placeholders


def dynamic_children_geometry(collector, parent_path, parent_matrix, clips, stack, sink):
    result = _BASE["dynamic_geometry"](
        collector, parent_path, parent_matrix, clips, stack, sink,
    )
    target_sink = collector.geometries if sink is None else sink
    for obj in dynamic._children(collector.movie, parent_path):
        state = _graphics_state(obj, False)
        if (
            state is None or not (state.primitives or state.current_commands)
            or not bool(getattr(obj, "visible", True))
        ):
            continue
        raster = _rasterize(state)
        if raster is None:
            continue
        image, origin, bounds, _cache_hit = raster
        matrix = parent_matrix.then(dynamic._matrix(
            obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation,
        ))
        object_clips = hit_base._scroll_clip(collector.movie, obj.path, matrix, clips)
        target_sink[:] = [
            value for value in target_sink
            if not (
                str(getattr(value, "path", "")) == obj.path
                and str(getattr(value, "kind", "")) == "dynamic-bounds"
            )
        ]
        geometry = hit_base._alpha_geometry(
            obj.path, matrix, bounds, image.getchannel("A"), origin,
            object_clips, "dynamic-graphics-alpha", None,
        )
        before = len(collector.geometries)
        collector.add(
            geometry, obj.name, obj.enabled and obj.mouse_enabled,
            obj.tab_enabled, True,
        )
        if target_sink is not collector.geometries and len(collector.geometries) > before:
            target_sink.extend(collector.geometries[before:])
            del collector.geometries[before:]
        collector.graphics_count = int(getattr(collector, "graphics_count", 0)) + 1
    return result


def dynamic_node(movie, obj, level=0):
    node = _BASE["dynamic_node"](movie, obj, level)
    state = _graphics_state(obj, False)
    if state is None or not (state.primitives or state.current_commands):
        return node
    model.seal(state)
    metadata = dict(node.metadata)
    metadata["graphics"] = {
        "commands": int(state.command_count),
        "primitives": len(state.primitives),
        "revision": int(state.revision),
        "rejected": int(state.rejected),
        "bounds": model.state_bounds(state),
    }
    return inspector.StateNode(
        node.path, node.depth, node.label, node.kind, node.visible,
        node.character_id, node.class_name, metadata, node.children,
    )


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    value = node.metadata.get("graphics")
    if not value:
        return text
    return text + "\n\nAVM2 Graphics:\n" + (
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
    values = _movie_state(movie)
    objects = 0
    primitives = 0
    for obj in dynamic._state(movie)["objects"].values():
        state = _graphics_state(obj, False)
        if state is not None and (state.primitives or state.current_commands):
            objects += 1
            primitives += len(state.primitives) + int(bool(state.current_commands))
    if not any((objects, values.get("calls"), values.get("rejected"))):
        return text
    return text + "\n\nAVM2 Graphics:\n" + (
        f"- Objekte / Primitive: {objects} / {primitives}\n"
        f"- Runtime-Aufrufe: {values.get('calls', 0)}\n"
        f"- Gerendert / Cache-Treffer: {values.get('rendered', 0)} / {values.get('cache_hits', 0)}\n"
        f"- Abgewiesene Aufrufe: {values.get('rejected', 0)}"
    )


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_avm2_graphics_state = None
        for obj in dynamic._state(movie)["objects"].values():
            obj.extras.pop("_graphics_state", None)
    clear_graphics_cache()
    return _BASE["reset"](owner)


def clear_graphics_cache():
    global _RASTER_CACHE_BYTES
    _RASTER_CACHE.clear()
    _RASTER_CACHE_BYTES = 0
    precise.clear_geometry_cache()


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        get=runtime._get_property,
        call=runtime._call,
        draw_dynamic=dynamic._draw_dynamic,
        dynamic_geometry=hit_geometry.GeometryCollector._dynamic_children,
        dynamic_node=dynamic._dynamic_node,
        format_node=inspector.format_state_node,
        info=ui_browser.UIBrowser._format_info,
        reset=runtime.reset_runtime,
    )
    runtime._get_property = get_property
    runtime._call = call_value
    dynamic._draw_dynamic = draw_dynamic
    hit_geometry.GeometryCollector._dynamic_children = dynamic_children_geometry
    dynamic._dynamic_node = dynamic_node
    inspector.format_state_node = format_state_node
    ui_browser.UIBrowser._format_info = format_info
    runtime.reset_runtime = reset_runtime
    try:
        import ui_browser_avm2_lifecycle_patch as lifecycle
        lifecycle.reset_runtime = reset_runtime
    except Exception:
        pass
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime
    ui_browser.AVM2GraphicsProxy = GraphicsProxy
    ui_browser.clear_ui_graphics_cache = clear_graphics_cache
