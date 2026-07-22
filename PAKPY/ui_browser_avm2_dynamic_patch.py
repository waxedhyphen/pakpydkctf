"""Dynamic display-list objects, transform properties and preview input events for AVM2.

The patch keeps all generated objects in an isolated per-movie preview store.  It adds a
bounded subset of DisplayObjectContainer semantics, renders linked library symbols and
safe TextField/MovieClip placeholders, and turns Tk canvas input into AVM2 events.  Source
SWF/GFX/PAK data is never mutated.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import math
import tkinter as tk
from tkinter import ttk

import ui_browser
import ui_browser_avm2_patch as avm2
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as overrides_patch
import ui_browser_performance_patch as performance
import ui_browser_timeline_browser_patch as timeline_browser

try:
    from PIL import ImageDraw
except Exception:
    ImageDraw = None


_INSTALLED = False
_BASE = {}
_UNDEFINED = runtime._UNDEFINED
_MAX_DYNAMIC_OBJECTS = 2048
_MAX_DYNAMIC_DEPTH = 64


@dataclass
class DynamicDisplayObject:
    token: int
    kind: str
    class_name: str = ""
    name: str = ""
    path: str = ""
    parent_path: str = ""
    definition: object | None = None
    x: float = 0.0
    y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0
    alpha: float = 1.0
    visible: bool = True
    enabled: bool = True
    mouse_enabled: bool = True
    tab_enabled: bool = False
    width: float = 160.0
    height: float = 32.0
    text: str = ""
    html_text: str = ""
    current_frame: int = 1
    playing: bool = True
    extras: dict = field(default_factory=dict)


@dataclass(frozen=True)
class HitRegion:
    path: str
    bounds: tuple[float, float, float, float]
    name: str = ""
    enabled: bool = True
    tab_enabled: bool = False
    dynamic: bool = False


def _state(movie):
    value = getattr(movie, "ui_avm2_dynamic_state", None)
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {
            "generation": generation,
            "objects": {},
            "by_path": {},
            "children": {},
            "next_token": 1,
            "focus_path": "",
            "hover_path": "",
            "pressed_path": "",
            "created": 0,
            "removed": 0,
            "input_events": 0,
        }
        movie.ui_avm2_dynamic_state = value
    return value


def _touch(movie):
    state = _state(movie)
    state["revision"] = int(state.get("revision", 0)) + 1
    runtime._touch(movie)


def _next_token(movie):
    state = _state(movie)
    token = int(state["next_token"])
    state["next_token"] = token + 1
    return token


def _short(value):
    return avm2._short_name(str(value or ""))


def _segment(obj):
    label = obj.name or _short(obj.class_name) or obj.kind
    label = str(label or "dynamic").replace("/", "_")
    return f"$dyn{obj.token}:{label}"


def _definition_for_class(movie, class_name):
    wanted = avm2._canonical_name(class_name)
    short = _short(class_name)
    fallback = None
    for character_id, name in (getattr(movie, "symbol_classes", {}) or {}).items():
        canonical = avm2._canonical_name(name)
        if canonical == wanted:
            return movie.definitions.get(character_id), int(character_id), str(name)
        if fallback is None and _short(canonical) == short:
            fallback = (movie.definitions.get(character_id), int(character_id), str(name))
    return fallback


def _kind_for(class_name, definition):
    short = _short(class_name).lower()
    if isinstance(definition, ui_browser.EditTextDef) or short in ("textfield", "edittext"):
        return "TextField"
    if isinstance(definition, ui_browser.SpriteDef) or short in ("movieclip", "sprite", "simplebutton"):
        return "MovieClip"
    if isinstance(definition, ui_browser.ShapeDef) or short == "shape":
        return "Shape"
    return "DisplayObject"


def _avm2_class_kind(movie, class_name):
    found = lifecycle._find_class(movie, class_name)
    if found is None:
        return None
    module, index = found
    seen = set()
    current = int(index)
    by_name = {
        avm2._canonical_name(module.abc.class_name(i)): i
        for i in range(len(module.abc.instances))
    }
    while current not in seen and 0 <= current < len(module.abc.instances):
        seen.add(current)
        instance = module.abc.instances[current]
        own = _short(module.abc.class_name(current)).lower()
        parent_name = avm2._canonical_name(module.abc.multiname_name(instance.super_name_index))
        parent = _short(parent_name).lower()
        for value in (own, parent):
            if value in ("textfield", "edittext"):
                return "TextField"
            if value in ("movieclip", "sprite", "simplebutton", "displayobjectcontainer"):
                return "MovieClip"
            if value == "shape":
                return "Shape"
            if value == "displayobject":
                return "DisplayObject"
        current = by_name.get(parent_name, -1)
    return "MovieClip"


def _register_object(movie, obj, parent_path):
    state = _state(movie)
    if len(state["objects"]) >= _MAX_DYNAMIC_OBJECTS:
        runtime._error(movie, parent_path, "dynamic-display", "Limit dynamischer DisplayObjects erreicht")
        return False
    obj.parent_path = str(parent_path or "root")
    obj.path = f"{obj.parent_path}/{_segment(obj)}"
    state["objects"][obj.token] = obj
    state["by_path"][obj.path] = obj.token
    state["created"] += 1
    _touch(movie)
    return True


def _dynamic_for_path(movie, path):
    state = _state(movie)
    token = state["by_path"].get(str(path))
    return state["objects"].get(token)


def _children(movie, parent_path):
    state = _state(movie)
    result = []
    for token in state["children"].get(str(parent_path), ()):
        obj = state["objects"].get(token)
        if obj is not None:
            result.append(obj)
    return result


def _migrate_path(movie, obj, new_parent):
    state = _state(movie)
    old_path = obj.path
    old_children = list(state["children"].pop(old_path, ()))
    state["by_path"].pop(old_path, None)
    obj.parent_path = str(new_parent)
    obj.path = f"{obj.parent_path}/{_segment(obj)}"
    state["by_path"][obj.path] = obj.token
    if old_children:
        state["children"][obj.path] = old_children
    properties = getattr(movie, "ui_avm2_runtime_properties", {}) or {}
    if old_path in properties:
        properties[obj.path] = properties.pop(old_path)
    listeners = lifecycle._state(movie).get("listeners", {})
    old_key, new_key = ("path", old_path), ("path", obj.path)
    if old_key in listeners:
        listeners[new_key] = listeners.pop(old_key)
    for child in _children(movie, obj.path):
        _migrate_path(movie, child, obj.path)


def _attach(movie, parent, child, index=None):
    if not isinstance(child, DynamicDisplayObject):
        return child
    parent_path = parent.path if isinstance(parent, DynamicDisplayObject) else getattr(parent, "path", "root")
    parent_path = str(parent_path or "root")
    state = _state(movie)
    if child.parent_path:
        old = state["children"].get(child.parent_path, [])
        if child.token in old:
            old.remove(child.token)
    if child.parent_path != parent_path:
        _migrate_path(movie, child, parent_path)
    values = state["children"].setdefault(parent_path, [])
    if child.token in values:
        values.remove(child.token)
    if index is None:
        values.append(child.token)
    else:
        values.insert(max(0, min(len(values), int(index))), child.token)
    child.parent_path = parent_path
    if child.class_name and not child.extras.get("initialized"):
        owner = getattr(movie, "_ui_avm2_runtime_owner", None)
        try:
            lifecycle.initialize_instance(owner, movie, child.path, child.definition, child.class_name,
                                          child.current_frame, child.playing)
            child.extras["initialized"] = True
        except Exception as exc:
            runtime._error(movie, child.path, "dynamic-constructor", exc)
    _touch(movie)
    return child


def _detach(movie, parent, child):
    parent_path = parent.path if isinstance(parent, DynamicDisplayObject) else getattr(parent, "path", "root")
    state = _state(movie)
    if isinstance(child, DynamicDisplayObject):
        values = state["children"].get(str(parent_path), [])
        if child.token in values:
            values.remove(child.token)
            child.parent_path = ""
            _touch(movie)
        return child
    if isinstance(child, runtime.RuntimeRef):
        runtime._properties(movie).setdefault(child.path, {})["visible"] = False
        _touch(movie)
        return child
    return _UNDEFINED


def construct_dynamic(context, class_name, args=()):
    found = _definition_for_class(context.movie, class_name)
    definition = found[0] if found else None
    canonical = found[2] if found else str(class_name or "")
    kind = _kind_for(class_name, definition)
    class_kind = _avm2_class_kind(context.movie, class_name)
    if kind == "DisplayObject" and class_kind is not None:
        kind = class_kind
    known = kind != "DisplayObject" or found is not None or class_kind is not None or _short(class_name).lower() == "displayobject"
    if not known:
        return _UNDEFINED
    token = _next_token(context.movie)
    obj = DynamicDisplayObject(token, kind, canonical or str(class_name or ""))
    obj.name = f"{_short(class_name) or kind}{token}"
    obj.definition = definition
    if isinstance(definition, ui_browser.EditTextDef):
        xmin, ymin, xmax, ymax = definition.bounds
        obj.width, obj.height = max(1.0, xmax - xmin), max(1.0, ymax - ymin)
        obj.text = str(getattr(definition, "initial_text", "") or "")
    elif isinstance(definition, ui_browser.ShapeDef):
        xmin, ymin, xmax, ymax = definition.bounds
        obj.width, obj.height = max(1.0, xmax - xmin), max(1.0, ymax - ymin)
    if args and kind == "TextField":
        obj.text = str(args[0])
    if not _register_object(context.movie, obj, context.path):
        return _UNDEFINED
    return obj


def _base_matrix_properties(item):
    matrix = getattr(item, "matrix", ui_browser.Affine())
    sx = math.hypot(matrix.a, matrix.b)
    rotation = math.degrees(math.atan2(matrix.b, matrix.a)) if sx > 1e-12 else 0.0
    det = matrix.a * matrix.d - matrix.b * matrix.c
    sy = det / sx if sx > 1e-12 else math.hypot(matrix.c, matrix.d)
    return matrix.tx, matrix.ty, sx, sy, rotation


def _matrix(x, y, scale_x, scale_y, rotation):
    angle = math.radians(float(rotation))
    cosine, sine = math.cos(angle), math.sin(angle)
    return ui_browser.Affine(
        cosine * float(scale_x), sine * float(scale_x),
        -sine * float(scale_y), cosine * float(scale_y),
        float(x), float(y),
    )


def apply_item_override(movie, parent_path, depth, item, overrides):
    result, path, manual = _BASE["apply"](movie, parent_path, depth, item, overrides)
    values = dict(runtime._properties(movie).get(path, {}) or {})
    if not any(key in values for key in ("x", "y", "scaleX", "scaleY", "rotation", "enabled", "mouseEnabled", "tabEnabled")):
        return result, path, manual
    clone = copy.copy(result)
    x, y, sx, sy, rotation = _base_matrix_properties(clone)
    clone.matrix = _matrix(
        values.get("x", x), values.get("y", y),
        values.get("scaleX", sx), values.get("scaleY", sy),
        values.get("rotation", rotation),
    )
    clone._ui_enabled = bool(values.get("enabled", True))
    clone._ui_mouse_enabled = bool(values.get("mouseEnabled", True))
    clone._ui_tab_enabled = bool(values.get("tabEnabled", False))
    return clone, path, manual


def _set_dynamic_property(context, obj, short, value):
    aliases = {
        "scaleX": "scale_x", "scaleY": "scale_y", "mouseEnabled": "mouse_enabled",
        "tabEnabled": "tab_enabled", "htmlText": "html_text", "currentFrame": "current_frame",
    }
    attr = aliases.get(short, short)
    if attr in ("x", "y", "scale_x", "scale_y", "rotation", "alpha", "width", "height"):
        try:
            value = float(value)
        except Exception:
            value = 0.0
    elif attr in ("visible", "enabled", "mouse_enabled", "tab_enabled", "playing", "buttonMode", "useHandCursor", "focusRect"):
        value = bool(value)
    elif attr in ("text", "html_text", "name"):
        value = "" if value is None or value is _UNDEFINED else str(value)
    elif attr == "current_frame":
        try:
            value = max(1, int(value))
        except Exception:
            value = 1
    elif not hasattr(obj, attr):
        obj.extras[short] = value
        _touch(context.movie)
        context.writes += 1
        return True
    setattr(obj, attr, value)
    _touch(context.movie)
    context.writes += 1
    runtime._log(context.movie, "dynamic-property", path=obj.path, property=short, value=repr(value))
    return True


def set_property(context, reference, name, value):
    short = _short(name)
    if isinstance(reference, DynamicDisplayObject):
        return _set_dynamic_property(context, reference, short, value)
    if isinstance(reference, runtime.RuntimeRef):
        obj = _dynamic_for_path(context.movie, reference.path)
        if obj is not None:
            return _set_dynamic_property(context, obj, short, value)
        if short in ("x", "y", "scaleX", "scaleY", "rotation", "enabled", "mouseEnabled", "tabEnabled", "buttonMode", "useHandCursor", "focusRect"):
            values = runtime._properties(context.movie).setdefault(reference.path, {})
            if short in ("x", "y", "scaleX", "scaleY", "rotation"):
                try:
                    value = float(value)
                except Exception:
                    value = 0.0
            elif short in ("enabled", "mouseEnabled", "tabEnabled", "buttonMode", "useHandCursor", "focusRect"):
                value = bool(value)
            values[short] = value
            context.writes += 1
            _touch(context.movie)
            return True
    return _BASE["set"](context, reference, name, value)


def _static_children(context, reference):
    if not isinstance(reference, runtime.RuntimeRef):
        return []
    result = []
    for depth, item in sorted(runtime._display_for(context, reference).items()):
        definition = context.movie.definitions.get(getattr(item, "character_id", None))
        path = overrides_patch.state_item_path(context.movie, reference.path, depth, item)
        frame = runtime._sprite_frame(context.movie, path, definition) if isinstance(definition, ui_browser.SpriteDef) else 1
        result.append(runtime.RuntimeRef(path, item, definition, frame))
    return result


def _all_children(context, receiver):
    parent_path = receiver.path if isinstance(receiver, (runtime.RuntimeRef, DynamicDisplayObject)) else ""
    result = _static_children(context, receiver) if isinstance(receiver, runtime.RuntimeRef) else []
    result.extend(_children(context.movie, parent_path))
    return result


def get_property(context, receiver, name):
    short = _short(name)
    if isinstance(receiver, runtime.RuntimeRef):
        obj = _dynamic_for_path(context.movie, receiver.path)
        if obj is not None:
            receiver = obj
    if isinstance(receiver, DynamicDisplayObject):
        values = {
            "x": receiver.x, "y": receiver.y, "scaleX": receiver.scale_x,
            "scaleY": receiver.scale_y, "rotation": receiver.rotation, "alpha": receiver.alpha,
            "visible": receiver.visible, "enabled": receiver.enabled,
            "mouseEnabled": receiver.mouse_enabled, "tabEnabled": receiver.tab_enabled,
            "buttonMode": bool(receiver.extras.get("buttonMode", False)),
            "useHandCursor": bool(receiver.extras.get("useHandCursor", False)),
            "focusRect": bool(receiver.extras.get("focusRect", False)),
            "width": receiver.width, "height": receiver.height, "text": receiver.text,
            "htmlText": receiver.html_text or receiver.text, "name": receiver.name,
            "currentFrame": receiver.current_frame,
            "totalFrames": int(getattr(receiver.definition, "frame_count", 1) or 1),
            "numChildren": len(_children(context.movie, receiver.path)),
            "parent": runtime.RuntimeRef(receiver.parent_path) if receiver.parent_path else None,
            "root": runtime.RuntimeRef("root", root=True), "stage": runtime.RuntimeRef("root", root=True),
            "focused": _state(context.movie).get("focus_path") == receiver.path,
        }
        if short in values:
            return values[short]
        if short in receiver.extras:
            return receiver.extras[short]
        for child in _children(context.movie, receiver.path):
            if child.name == short:
                return child
    if isinstance(receiver, runtime.RuntimeRef):
        if short == "numChildren":
            return len(_all_children(context, receiver))
        if short == "focused":
            return _state(context.movie).get("focus_path") == receiver.path
        values = runtime._properties(context.movie).get(receiver.path, {}) or {}
        if short in ("x", "y", "scaleX", "scaleY", "rotation", "enabled", "mouseEnabled", "tabEnabled", "buttonMode", "useHandCursor", "focusRect"):
            if short in values:
                return values[short]
            if receiver.item is not None:
                x, y, sx, sy, rotation = _base_matrix_properties(receiver.item)
                return {"x": x, "y": y, "scaleX": sx, "scaleY": sy, "rotation": rotation,
                        "enabled": True, "mouseEnabled": True, "tabEnabled": False,
                        "buttonMode": False, "useHandCursor": False, "focusRect": False}[short]
    return _BASE["get"](context, receiver, name)


def _child_by_name(context, receiver, name):
    wanted = str(name or "")
    for child in _all_children(context, receiver):
        if isinstance(child, DynamicDisplayObject):
            names = (child.name, _short(child.class_name))
        else:
            definition = child.definition
            names = runtime._names(context.movie, child.item, definition)
        if wanted in names or wanted.lower() in {str(value).lower() for value in names}:
            return child
    return _UNDEFINED


def call_value(context, receiver, name, args):
    short = _short(name)
    lower = short.lower()
    constructed = construct_dynamic(context, short, args)
    if constructed is not _UNDEFINED:
        return constructed
    if isinstance(receiver, runtime.RuntimeRef):
        obj = _dynamic_for_path(context.movie, receiver.path)
        if obj is not None:
            receiver = obj
    if isinstance(receiver, (runtime.RuntimeRef, DynamicDisplayObject)):
        if lower in ("addchild", "addchildat") and args:
            return _attach(context.movie, receiver, args[0], args[1] if lower == "addchildat" and len(args) > 1 else None)
        if lower == "removechild" and args:
            return _detach(context.movie, receiver, args[0])
        if lower == "removechildat" and args:
            children = _all_children(context, receiver)
            try:
                return _detach(context.movie, receiver, children[int(args[0])])
            except Exception:
                return _UNDEFINED
        if lower == "getchildbyname" and args:
            return _child_by_name(context, receiver, args[0])
        if lower == "getchildat" and args:
            try:
                return _all_children(context, receiver)[int(args[0])]
            except Exception:
                return _UNDEFINED
        if lower == "contains" and args:
            return args[0] in _all_children(context, receiver)
        if lower == "setchildindex" and len(args) >= 2 and isinstance(args[0], DynamicDisplayObject):
            _attach(context.movie, receiver, args[0], args[1])
            return _UNDEFINED
        if lower in ("swapchildren", "swapchildrenat") and len(args) >= 2:
            values = _state(context.movie)["children"].get(receiver.path, [])
            try:
                if lower == "swapchildren":
                    left, right = values.index(args[0].token), values.index(args[1].token)
                else:
                    left, right = int(args[0]), int(args[1])
                values[left], values[right] = values[right], values[left]
                _touch(context.movie)
            except Exception:
                pass
            return _UNDEFINED
    if isinstance(receiver, DynamicDisplayObject):
        count = max(1, int(getattr(receiver.definition, "frame_count", 1) or 1))
        labels = dict(getattr(receiver.definition, "labels", {}) or {})
        if lower == "stop":
            receiver.playing = False
            return _UNDEFINED
        if lower == "play":
            receiver.playing = True
            return _UNDEFINED
        if lower in ("gotoandstop", "gotoandplay") and args:
            target = avm2.resolve_action_target(args[0], count, labels)
            if target is not None:
                receiver.current_frame = int(target)
                receiver.playing = lower == "gotoandplay"
                _touch(context.movie)
            return _UNDEFINED
    if isinstance(receiver, runtime.RuntimeGlobal) and lower in ("setfocus", "focus") and args:
        target = args[0]
        path = target.path if isinstance(target, (runtime.RuntimeRef, DynamicDisplayObject)) else ""
        _set_focus(context.movie, path)
        return target
    return _BASE["call"](context, receiver, name, args)


def _key(value):
    if isinstance(value, DynamicDisplayObject):
        return ("path", value.path)
    return _BASE["key"](value)


def _definition_bounds(definition):
    if definition is not None and hasattr(definition, "bounds"):
        return tuple(definition.bounds)
    return None


def _bounds_for_static(renderer, item, definition):
    bounds = _definition_bounds(definition)
    if bounds is not None:
        return bounds
    if getattr(item, "class_name", ""):
        try:
            lookup = renderer.resolver.get(item.class_name)
            if lookup.image is not None:
                return (0.0, 0.0, float(lookup.image.width), float(lookup.image.height))
        except Exception:
            pass
    return None


def _world_bounds(renderer, matrix, bounds):
    xmin, ymin, xmax, ymax = bounds
    points = [
        renderer._point(matrix, xmin, ymin), renderer._point(matrix, xmax, ymin),
        renderer._point(matrix, xmax, ymax), renderer._point(matrix, xmin, ymax),
    ]
    return (
        min(point[0] for point in points), min(point[1] for point in points),
        max(point[0] for point in points), max(point[1] for point in points),
    )


def _record_hit(renderer, path, matrix, bounds, name="", enabled=True, tab_enabled=False, dynamic=False):
    if bounds is None or not enabled:
        return
    region = HitRegion(path, _world_bounds(renderer, matrix, bounds), str(name or ""), True, bool(tab_enabled), dynamic)
    renderer.movie.ui_input_hit_regions.append(region)


def _dynamic_definition(obj):
    if obj.definition is not None:
        return obj.definition
    if obj.kind == "TextField":
        try:
            return ui_browser.EditTextDef(
                -obj.token, (0.0, 0.0, max(1.0, obj.width), max(1.0, obj.height)),
                obj.name, obj.html_text or obj.text, (255, 255, 255, 255), 18.0, False,
            )
        except TypeError:
            return ui_browser.EditTextDef(
                character_id=-obj.token,
                bounds=(0.0, 0.0, max(1.0, obj.width), max(1.0, obj.height)),
                variable_name=obj.name, initial_text=obj.html_text or obj.text,
                color=(255, 255, 255, 255), font_height=18.0, border=False,
            )
    return None


def _draw_dynamic(renderer, canvas, obj, parent_matrix, parent_color, stack, level):
    if level > _MAX_DYNAMIC_DEPTH or not obj.visible:
        return
    local = _matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation)
    matrix = parent_matrix.then(local)
    color = parent_color.combine(ui_browser.ColorTransform(a_mult=max(0.0, min(1.0, obj.alpha))))
    definition = _dynamic_definition(obj)
    old_current = getattr(renderer, "_ui_current_path", "")
    old_parent = getattr(renderer, "_ui_state_parent_path", "root")
    renderer._ui_current_path = obj.path
    renderer._ui_state_parent_path = obj.path
    try:
        if isinstance(definition, ui_browser.SpriteDef):
            frame = max(1, min(int(definition.frame_count), int(obj.current_frame)))
            child = ui_browser.build_display_list(definition.tags, frame)
            renderer._draw_display(canvas, child, matrix, color, stack | {id(obj)}, level + 1)
        elif isinstance(definition, ui_browser.EditTextDef):
            clone = copy.copy(definition)
            clone.initial_text = obj.html_text or obj.text or str(getattr(definition, "initial_text", "") or "")
            if hasattr(clone, "html"):
                clone.html = bool(obj.html_text)
            renderer._draw_edit_text(canvas, clone, matrix, color)
        elif isinstance(definition, ui_browser.ShapeDef):
            renderer._draw_shape(canvas, definition, matrix)
        elif renderer.show_placeholders:
            renderer._draw_placeholder(canvas, matrix, obj.name or obj.kind, (70, 120, 165, 150))
        bounds = _definition_bounds(definition) or (0.0, 0.0, max(1.0, obj.width), max(1.0, obj.height))
        _record_hit(renderer, obj.path, matrix, bounds, obj.name, obj.enabled and obj.mouse_enabled,
                    obj.tab_enabled, True)
        if not isinstance(definition, ui_browser.SpriteDef):
            for child_obj in _children(renderer.movie, obj.path):
                _draw_dynamic(renderer, canvas, child_obj, matrix, color, stack | {id(obj)}, level + 1)
        renderer.stats.dynamic_objects_drawn = getattr(renderer.stats, "dynamic_objects_drawn", 0) + 1
    finally:
        renderer._ui_current_path = old_current
        renderer._ui_state_parent_path = old_parent


def draw_display(renderer, canvas, display, parent_matrix, parent_color, stack, level):
    if level == 0:
        renderer.movie.ui_input_hit_regions = []
    parent_path = getattr(renderer, "_ui_state_parent_path", "root") or "root"
    for depth in sorted(display):
        item, path, _manual = overrides_patch.apply_item_override(
            renderer.movie, parent_path, depth, display[depth],
            overrides_patch.normalize_overrides(getattr(renderer.movie, "ui_state_overrides", {})),
        )
        if not getattr(item, "visible", True):
            continue
        definition = renderer.movie.definitions.get(getattr(item, "character_id", None))
        matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
        _record_hit(
            renderer, path, matrix, _bounds_for_static(renderer, item, definition),
            getattr(item, "name", ""), getattr(item, "_ui_enabled", True) and getattr(item, "_ui_mouse_enabled", True),
            getattr(item, "_ui_tab_enabled", False), False,
        )
    result = _BASE["draw"](renderer, canvas, display, parent_matrix, parent_color, stack, level)
    for obj in _children(renderer.movie, parent_path):
        _draw_dynamic(renderer, canvas, obj, parent_matrix, parent_color, stack, level)
    return result


def _dynamic_node(movie, obj, level=0):
    children = tuple(_dynamic_node(movie, child, level + 1) for child in _children(movie, obj.path))
    definition = _dynamic_definition(obj)
    metadata = {
        "dynamic": True,
        "token": obj.token,
        "parent_path": obj.parent_path,
        "instance_name": obj.name,
        "class_name": obj.class_name,
        "visible": obj.visible,
        "enabled": obj.enabled,
        "mouse_enabled": obj.mouse_enabled,
        "tab_enabled": obj.tab_enabled,
        "focused": _state(movie).get("focus_path") == obj.path,
        "matrix": {"a": _matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation).a,
                   "b": _matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation).b,
                   "c": _matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation).c,
                   "d": _matrix(obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation).d,
                   "tx": obj.x, "ty": obj.y},
        "color_transform": {"r_mult": 1.0, "g_mult": 1.0, "b_mult": 1.0,
                            "a_mult": obj.alpha, "r_add": 0, "g_add": 0, "b_add": 0, "a_add": 0},
        "bounds": _definition_bounds(definition) or (0.0, 0.0, obj.width, obj.height),
        "child_count": len(children),
    }
    if obj.kind == "TextField":
        metadata.update(text=obj.html_text or obj.text, display_text=obj.html_text or obj.text,
                        html=bool(obj.html_text), variable_name=obj.name)
    if obj.kind == "MovieClip":
        metadata.update(sprite_frame=obj.current_frame,
                        sprite_frame_count=int(getattr(definition, "frame_count", 1) or 1),
                        sprite_labels=dict(getattr(definition, "labels", {}) or {}))
    return inspector.StateNode(
        obj.path, 1_000_000 + obj.token, obj.name or obj.kind,
        f"Dynamic{obj.kind}", obj.visible, getattr(definition, "character_id", None),
        obj.class_name, metadata, children,
    )


def inspect_movie_state(movie, frame, max_depth=64):
    roots = list(_BASE["inspect"](movie, frame, max_depth))
    by_parent = {path: list(_children(movie, path)) for path in _state(movie)["children"]}

    def decorate(nodes):
        result = []
        for node in nodes:
            children = list(decorate(node.children))
            children.extend(_dynamic_node(movie, obj) for obj in by_parent.get(node.path, ()))
            result.append(inspector.StateNode(
                node.path, node.depth, node.label, node.kind, node.visible,
                node.character_id, node.class_name, dict(node.metadata), tuple(children),
            ))
        return tuple(result)

    result = list(decorate(roots))
    result.extend(_dynamic_node(movie, obj) for obj in by_parent.get("root", ()))
    return tuple(result)


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    if not node.metadata.get("dynamic"):
        return text
    return text + "\n\nDynamische Display-List:\n" + (
        f"- Parent: {node.metadata.get('parent_path', '')}\n"
        f"- Kinder: {node.metadata.get('child_count', 0)}\n"
        f"- Enabled: {'ja' if node.metadata.get('enabled') else 'nein'}\n"
        f"- MouseEnabled: {'ja' if node.metadata.get('mouse_enabled') else 'nein'}\n"
        f"- Fokus: {'ja' if node.metadata.get('focused') else 'nein'}"
    )


def _dispatch_path(movie, path, event, bubble=False):
    delivered = 0
    current = str(path or "root")
    while current:
        delivered += lifecycle._dispatch_key(movie, ("path", current), event)
        if not bubble or event.stop_now or current == "root":
            break
        current = current.rsplit("/", 1)[0] if "/" in current else "root"
    _state(movie)["input_events"] += delivered
    return delivered


def _set_focus(movie, path):
    state = _state(movie)
    path = str(path or "")
    old = state.get("focus_path", "")
    if old == path:
        return
    if old:
        _dispatch_path(movie, old, lifecycle.RuntimeEvent("focusOut", bubbles=False, data={"relatedObject": path}))
    state["focus_path"] = path
    if path:
        _dispatch_path(movie, path, lifecycle.RuntimeEvent("focusIn", bubbles=False, data={"relatedObject": old}))
    _touch(movie)


def _stage_point(owner, event):
    rect = getattr(owner, "_ui_stage_canvas_rect", None)
    movie = getattr(owner, "_current_movie", None)
    if not rect or movie is None:
        return None
    x, y, width, height = rect
    if width <= 0 or height <= 0 or not (x <= event.x <= x + width and y <= event.y <= y + height):
        return None
    return ((event.x - x) * movie.width / float(width), (event.y - y) * movie.height / float(height))


def _hit(owner, event):
    point = _stage_point(owner, event)
    movie = getattr(owner, "_current_movie", None)
    if point is None or movie is None:
        return None, point
    px, py = point
    for region in reversed(tuple(getattr(movie, "ui_input_hit_regions", ()) or ())):
        left, top, right, bottom = region.bounds
        if region.enabled and left <= px <= right and top <= py <= bottom:
            return region, point
    return None, point


def _input_enabled(owner):
    variable = getattr(owner, "avm2_input_enabled_var", None)
    return bool(variable is None or variable.get())


def _mouse_event(owner, event, event_type):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not _input_enabled(owner):
        return
    region, point = _hit(owner, event)
    state = _state(movie)
    path = region.path if region is not None else ""
    if event_type == "mouseDown":
        state["pressed_path"] = path
        if path:
            _set_focus(movie, path)
            owner.canvas.focus_set()
    elif event_type == "mouseUp":
        pressed = state.get("pressed_path", "")
        state["pressed_path"] = ""
        if pressed and pressed == path:
            click = lifecycle.RuntimeEvent("click", bubbles=True, data={"stage": point})
            click.extra.update(stageX=point[0], stageY=point[1], buttonDown=False)
            _dispatch_path(movie, path, click, True)
    if path:
        value = lifecycle.RuntimeEvent(event_type, bubbles=True, data={"stage": point})
        value.extra.update(stageX=point[0], stageY=point[1], buttonDown=event_type == "mouseDown")
        _dispatch_path(movie, path, value, True)
    owner.request_render()


def _motion(owner, event):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not _input_enabled(owner):
        return
    region, point = _hit(owner, event)
    path = region.path if region else ""
    state = _state(movie)
    old = state.get("hover_path", "")
    if old == path:
        return
    if old:
        _dispatch_path(movie, old, lifecycle.RuntimeEvent("mouseOut", bubbles=True, data={"stage": point}), True)
    state["hover_path"] = path
    if path:
        _dispatch_path(movie, path, lifecycle.RuntimeEvent("mouseOver", bubbles=True, data={"stage": point}), True)


def _focus_cycle(owner, reverse=False):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return "break"
    values = [region for region in getattr(movie, "ui_input_hit_regions", ()) if region.enabled and region.tab_enabled]
    if not values:
        values = [region for region in getattr(movie, "ui_input_hit_regions", ()) if region.enabled]
    if not values:
        return "break"
    current = _state(movie).get("focus_path", "")
    paths = [region.path for region in values]
    try:
        index = paths.index(current)
        index = (index - 1 if reverse else index + 1) % len(paths)
    except ValueError:
        index = -1 if reverse else 0
    _set_focus(movie, paths[index])
    owner.request_render()
    return "break"


def _key_event(owner, event, down):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not _input_enabled(owner):
        return
    path = _state(movie).get("focus_path", "") or "root"
    value = lifecycle.RuntimeEvent("keyDown" if down else "keyUp", bubbles=True)
    value.extra.update(keyCode=int(getattr(event, "keycode", 0) or 0),
                       charCode=ord(event.char) if getattr(event, "char", "") else 0,
                       key=str(getattr(event, "keysym", "") or ""))
    _dispatch_path(movie, path, value, True)


def _activate_focus(owner, _event=None):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return "break"
    path = _state(movie).get("focus_path", "")
    if path:
        _dispatch_path(movie, path, lifecycle.RuntimeEvent("click", bubbles=True), True)
        owner.request_render()
    return "break"


def advance(owner, steps=1, force_nested=False):
    result = _BASE["advance"](owner, steps, force_nested)
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not bool(getattr(movie, "ui_avm2_runtime_enabled", True)):
        return result
    changed = False
    delta = int(steps)
    for obj in _state(movie)["objects"].values():
        count = max(1, int(getattr(obj.definition, "frame_count", 1) or 1))
        if obj.kind == "MovieClip" and obj.playing and count > 1:
            obj.current_frame = ((int(obj.current_frame) - 1 + delta) % count) + 1
            changed = True
    if changed:
        _touch(movie)
    return result


def draw_scaled(owner, event=None):
    result = _BASE["scaled"](owner, event)
    image = getattr(owner, "_display_image", None)
    if image is not None:
        width, height = image.size
        canvas_width = max(1, owner.canvas.winfo_width())
        canvas_height = max(1, owner.canvas.winfo_height())
        owner._ui_stage_canvas_rect = ((canvas_width - width) // 2, (canvas_height - height) // 2, width, height)
    else:
        owner._ui_stage_canvas_rect = None
    return result


def browser_init(owner, *args, **kwargs):
    _BASE["browser_init"](owner, *args, **kwargs)
    owner.avm2_input_enabled_var = tk.BooleanVar(value=True)
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Checkbutton(bar, text="Input Events", variable=owner.avm2_input_enabled_var).pack(side="left")
    ttk.Label(bar, text="Klick = MouseEvent · Tab = Fokus · Enter/Leertaste = Aktivieren").pack(side="left", padx=(10, 0))
    owner.canvas.configure(takefocus=True)
    owner.canvas.bind("<ButtonPress-1>", lambda event: _mouse_event(owner, event, "mouseDown"), add="+")
    owner.canvas.bind("<ButtonRelease-1>", lambda event: _mouse_event(owner, event, "mouseUp"), add="+")
    owner.canvas.bind("<Motion>", lambda event: _motion(owner, event), add="+")
    owner.canvas.bind("<Tab>", lambda _event: _focus_cycle(owner, False))
    owner.canvas.bind("<Shift-Tab>", lambda _event: _focus_cycle(owner, True))
    owner.canvas.bind("<ISO_Left_Tab>", lambda _event: _focus_cycle(owner, True))
    owner.canvas.bind("<Return>", lambda event: _activate_focus(owner, event))
    owner.canvas.bind("<space>", lambda event: _activate_focus(owner, event))
    owner.canvas.bind("<KeyPress>", lambda event: _key_event(owner, event, True), add="+")
    owner.canvas.bind("<KeyRelease>", lambda event: _key_event(owner, event, False), add="+")


def format_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    state = _state(movie)
    attached = sum(len(values) for values in state["children"].values())
    regions = len(tuple(getattr(movie, "ui_input_hit_regions", ()) or ()))
    return text + "\n\nDynamische Display-List / Input:\n" + (
        f"- Dynamische Objekte: {len(state['objects'])} ({attached} angehängt)\n"
        f"- Gezeichnet: {getattr(stats, 'dynamic_objects_drawn', 0)}\n"
        f"- Hit-Regionen: {regions}\n"
        f"- Fokus: {state.get('focus_path') or '-'}\n"
        f"- Ausgeführte Input-Listener: {state.get('input_events', 0)}"
    )


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_avm2_dynamic_state = None
        movie.ui_input_hit_regions = []
    return _BASE["reset"](owner)


def cache_key(renderer, frame, scale):
    base = tuple(_BASE["cache_key"](renderer, frame, scale))
    state = _state(renderer.movie)
    return base + (int(state.get("revision", 0)),)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        call=runtime._call, get=runtime._get_property, set=runtime._set_property,
        key=lifecycle._key, apply=overrides_patch.apply_item_override,
        draw=ui_browser.UIRenderer._draw_display,
        inspect=inspector.inspect_movie_state, format_node=inspector.format_state_node,
        browser_init=ui_browser.UIBrowser.__init__, scaled=ui_browser.UIBrowser._draw_scaled,
        info=ui_browser.UIBrowser._format_info, reset=runtime.reset_runtime,
        advance=timeline_browser.advance, cache_key=performance._render_cache_key,
    )
    runtime._call = call_value
    runtime._get_property = get_property
    runtime._set_property = set_property
    lifecycle._key = _key
    overrides_patch.apply_item_override = apply_item_override
    ui_browser.UIRenderer._draw_display = draw_display
    inspector.inspect_movie_state = inspect_movie_state
    inspector.format_state_node = format_state_node
    ui_browser.inspect_movie_state = inspect_movie_state
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._draw_scaled = draw_scaled
    ui_browser.UIBrowser._format_info = format_info
    timeline_browser.advance = advance
    runtime.reset_runtime = reset_runtime
    lifecycle.reset_runtime = reset_runtime
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime
    performance._render_cache_key = cache_key
    ui_browser.DynamicAVM2DisplayObject = DynamicDisplayObject
    ui_browser.AVM2HitRegion = HitRegion
    ui_browser.construct_dynamic_avm2_object = construct_dynamic
    ui_browser.dispatch_avm2_input_event = _dispatch_path
