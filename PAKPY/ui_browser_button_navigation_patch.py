"""Automatic button states, directional focus and controller-style input for the UI Browser.

The patch builds on the bounded dynamic-display input layer. It recognizes button-like
MovieClips and dynamic objects, maps semantic labels such as ``up``, ``over`` and
``down`` to timeline frames, keeps navigation deterministic, and emits safe controller
events. All state remains preview-only.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import tkinter as tk
from tkinter import ttk

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as overrides_patch
import ui_browser_timeline_core as timeline_core


_INSTALLED = False
_BASE = {}
_UNDEFINED = runtime._UNDEFINED

_STATE_LABELS = {
    "up": (
        "up", "default", "normal", "idle", "unpressed", "unhighlighted",
        "startunhighlight", "startunhighlighted",
    ),
    "over": (
        "over", "hover", "highlight", "highlighted", "selected", "focused",
        "focus", "starthighlight", "starthighlighted",
    ),
    "down": (
        "down", "pressed", "press", "selectedpressed", "startpressed",
        "startpress",
    ),
    "disabled": (
        "disabled", "disable", "inactive", "locked", "unavailable",
    ),
    "hit": (
        "hit", "hittest", "hitarea",
    ),
}

_BUTTON_WORDS = (
    "button", "btn", "option", "menuitem", "menu_item", "choice", "toggle",
    "checkbox", "radio", "arrow", "confirm", "cancel", "back", "next",
    "previous", "select", "control", "tab", "slot", "entry",
)

_DIRECTION_KEYS = {
    "left": "left", "a": "left",
    "right": "right", "d": "right",
    "up": "up", "w": "up",
    "down": "down", "s": "down",
}

_ACCEPT_KEYS = {"return", "kp_enter", "space"}
_CANCEL_KEYS = {"escape", "backspace"}


@dataclass(frozen=True)
class ButtonDescriptor:
    path: str
    name: str
    frame_count: int = 1
    labels: tuple = ()
    enabled: bool = True
    tab_enabled: bool = False
    button_mode: bool = False
    dynamic: bool = False
    kind: str = ""
    bounds: tuple | None = None

    @property
    def label_map(self):
        return dict(self.labels)


def _compact(value):
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _button_state_store(movie):
    value = getattr(movie, "ui_button_navigation_state", None)
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {
            "generation": generation,
            "states": {},
            "descriptors": {},
            "focus_moves": 0,
            "button_transitions": 0,
            "controller_events": 0,
            "last_direction": "",
        }
        movie.ui_button_navigation_state = value
    return value


def _node_token(owner, movie):
    try:
        root_frame = int(owner.frame_var.get())
    except Exception:
        root_frame = 1
    dynamic_state = dynamic._state(movie)
    region_paths = tuple(
        value.path for value in getattr(movie, "ui_input_hit_regions", ()) or ()
    )
    return (
        root_frame,
        int(dynamic_state.get("created", 0)),
        int(dynamic_state.get("removed", 0)),
        int(getattr(movie, "ui_override_revision", 0)),
        hash(region_paths),
    )


def _walk_nodes(nodes):
    for node in tuple(nodes or ()):
        yield node
        yield from _walk_nodes(node.children)


def _node_index(owner, movie):
    store = _button_state_store(movie)
    token = _node_token(owner, movie)
    cached = store.get("node_index")
    if isinstance(cached, dict) and store.get("node_token") == token:
        return cached
    try:
        frame = int(owner.frame_var.get())
        nodes = inspector.inspect_movie_state(movie, frame)
        cached = {node.path: node for node in _walk_nodes(nodes)}
    except Exception:
        cached = {}
    store["node_index"] = cached
    store["node_token"] = token
    return cached


def _runtime_values(movie, path):
    return dict(runtime._properties(movie).get(str(path), {}) or {})


def _dynamic_object(movie, path):
    try:
        return dynamic._dynamic_for_path(movie, path)
    except Exception:
        return None


def _descriptor(owner, path, region=None):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return None
    store = _button_state_store(movie)
    cache = store["descriptors"]
    token = _node_token(owner, movie)
    cached = cache.get(path)
    if cached is not None and cached[0] == token:
        return cached[1]

    node = _node_index(owner, movie).get(path)
    values = _runtime_values(movie, path)
    obj = _dynamic_object(movie, path)
    metadata = dict(getattr(node, "metadata", {}) or {}) if node is not None else {}
    labels = dict(metadata.get("sprite_labels", {}) or {})
    frame_count = int(metadata.get("sprite_frame_count", 1) or 1)
    kind = str(getattr(node, "kind", "") or "")
    name = str(
        getattr(region, "name", "") or
        metadata.get("instance_name", "") or
        getattr(node, "label", "") or
        getattr(obj, "name", "") or
        path.rsplit(":", 1)[-1]
    )
    enabled = bool(
        getattr(region, "enabled", True) and
        values.get("enabled", getattr(obj, "enabled", metadata.get("enabled", True)))
    )
    tab_enabled = bool(
        getattr(region, "tab_enabled", False) or
        values.get("tabEnabled", getattr(obj, "tab_enabled", metadata.get("tab_enabled", False)))
    )
    button_mode = bool(
        values.get("buttonMode", getattr(obj, "extras", {}).get("buttonMode", False) if obj is not None else False)
    )
    dynamic_flag = bool(getattr(region, "dynamic", False) or metadata.get("dynamic") or obj is not None)
    bounds = getattr(region, "bounds", None)
    result = ButtonDescriptor(
        str(path), name, max(1, frame_count),
        tuple(sorted((str(key), int(value)) for key, value in labels.items())),
        enabled, tab_enabled, button_mode, dynamic_flag, kind, bounds,
    )
    cache[path] = (token, result)
    return result


def label_frame(labels, state):
    """Resolve a semantic button state to a labeled frame."""
    labels = dict(labels or {})
    compact = {_compact(name): int(frame) for name, frame in labels.items()}
    for candidate in _STATE_LABELS.get(str(state), ()):
        value = compact.get(_compact(candidate))
        if value is not None:
            return max(1, value)
    return None


def infer_button_frame(descriptor, state):
    """Return the best timeline frame for a descriptor and semantic state."""
    if descriptor is None:
        return None
    frame = label_frame(descriptor.label_map, state)
    if frame is not None:
        return max(1, min(descriptor.frame_count, frame))
    if descriptor.frame_count <= 1:
        return None
    fallback = {"up": 1, "over": 2, "down": 3, "disabled": 4}.get(str(state))
    if fallback is None or fallback > descriptor.frame_count:
        return None
    return fallback


def is_button_descriptor(descriptor):
    if descriptor is None:
        return False
    labels = {_compact(name) for name, _frame in descriptor.labels}
    semantic = any(
        _compact(candidate) in labels
        for values in _STATE_LABELS.values()
        for candidate in values
    )
    text = _compact(f"{descriptor.name} {descriptor.path} {descriptor.kind}")
    named = any(_compact(word) in text for word in _BUTTON_WORDS)
    return bool(
        descriptor.button_mode or descriptor.tab_enabled or semantic or named
    )


def _manual_frame(movie, path):
    return timeline_core.manual_frame_override(
        getattr(movie, "ui_state_overrides", {}) or {}, path,
    )


def _set_button_state(owner, path, state, request=True):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not path:
        return False
    region = next(
        (value for value in getattr(movie, "ui_input_hit_regions", ()) or () if value.path == path),
        None,
    )
    descriptor = _descriptor(owner, path, region)
    if descriptor is None or not is_button_descriptor(descriptor):
        return False
    if not descriptor.enabled:
        state = "disabled"
    store = _button_state_store(movie)
    record = store["states"].setdefault(path, {})
    state = str(state)
    frame = infer_button_frame(descriptor, state)
    if record.get("state") == state and record.get("frame") == frame:
        return False

    record.update(state=state, frame=frame, name=descriptor.name)
    values = runtime._properties(movie).setdefault(path, {})
    values["buttonState"] = state
    obj = _dynamic_object(movie, path)
    changed = True

    if frame is not None and _manual_frame(movie, path) is None:
        if obj is not None:
            obj.current_frame = max(1, min(descriptor.frame_count, int(frame)))
            obj.playing = False
            obj.extras["buttonState"] = state
        else:
            timeline = getattr(movie, "ui_timeline_states", None)
            if not isinstance(timeline, dict):
                timeline = {}
                movie.ui_timeline_states = timeline
            current = timeline.setdefault(
                path, timeline_core.normalize_timeline_instance({}, descriptor.frame_count),
            )
            current.update(frame=int(frame), playing=False, frame_count=descriptor.frame_count)
            current.pop("_avm2_runtime_token", None)

    store["button_transitions"] += 1
    runtime._log(movie, "button-state", path=path, state=state, frame=frame)
    dynamic._touch(movie)
    if request:
        try:
            owner.request_render()
        except Exception:
            pass
    return changed


def _resting_state(movie, path):
    state = dynamic._state(movie)
    if state.get("pressed_path") == path:
        return "down"
    if state.get("hover_path") == path or state.get("focus_path") == path:
        return "over"
    return "up"


def _sync_disabled(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    for region in tuple(getattr(movie, "ui_input_hit_regions", ()) or ()):
        descriptor = _descriptor(owner, region.path, region)
        if descriptor is not None and is_button_descriptor(descriptor) and not descriptor.enabled:
            _set_button_state(owner, region.path, "disabled", request=False)


def _mouse_children_enabled(movie, path):
    obj = _dynamic_object(movie, path)
    if obj is not None:
        return bool(obj.extras.get("mouseChildren", True))
    return bool(_runtime_values(movie, path).get("mouseChildren", True))


def _region_for_path(movie, path):
    for region in reversed(tuple(getattr(movie, "ui_input_hit_regions", ()) or ())):
        if region.path == path:
            return region
    return None


def _collapse_mouse_children(movie, region):
    if region is None:
        return None
    path = str(region.path)
    current = path
    while "/" in current:
        current = current.rsplit("/", 1)[0]
        if current and not _mouse_children_enabled(movie, current):
            parent = _region_for_path(movie, current)
            if parent is not None:
                return parent
            return dynamic.HitRegion(
                current, region.bounds, current.rsplit(":", 1)[-1],
                region.enabled, region.tab_enabled, region.dynamic,
            )
        if current == "root":
            break
    return region


def hit(owner, event):
    region, point = _BASE["hit"](owner, event)
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        region = _collapse_mouse_children(movie, region)
    return region, point


def set_property(context, reference, name, value):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if short == "mouseChildren":
        if isinstance(reference, dynamic.DynamicDisplayObject):
            reference.extras["mouseChildren"] = bool(value)
            context.writes += 1
            dynamic._touch(context.movie)
            return True
        if isinstance(reference, runtime.RuntimeRef):
            runtime._properties(context.movie).setdefault(reference.path, {})["mouseChildren"] = bool(value)
            context.writes += 1
            dynamic._touch(context.movie)
            return True
    return _BASE["set"](context, reference, name, value)


def get_property(context, receiver, name):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if short == "mouseChildren":
        if isinstance(receiver, dynamic.DynamicDisplayObject):
            return bool(receiver.extras.get("mouseChildren", True))
        if isinstance(receiver, runtime.RuntimeRef):
            return bool(_runtime_values(context.movie, receiver.path).get("mouseChildren", True))
    if short == "buttonState":
        path = getattr(receiver, "path", "")
        if path:
            return _button_state_store(context.movie)["states"].get(path, {}).get("state", "up")
    return _BASE["get"](context, receiver, name)


def _candidate_regions(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return []
    seen = set()
    preferred = []
    fallback = []
    for region in tuple(getattr(movie, "ui_input_hit_regions", ()) or ()):
        if not region.enabled or region.path in seen:
            continue
        seen.add(region.path)
        descriptor = _descriptor(owner, region.path, region)
        if descriptor is None or not descriptor.enabled:
            continue
        target = preferred if is_button_descriptor(descriptor) else fallback
        target.append(region)
    return preferred or fallback


def _center(region):
    left, top, right, bottom = region.bounds
    return ((left + right) * 0.5, (top + bottom) * 0.5)


def directional_target(regions, current_path, direction):
    """Choose the nearest region in a direction using a stable geometric score."""
    values = [region for region in regions if getattr(region, "enabled", True)]
    if not values:
        return None
    current = next((region for region in values if region.path == current_path), None)
    if current is None:
        ordered = sorted(values, key=lambda value: (_center(value)[1], _center(value)[0], value.path))
        return ordered[-1] if direction in ("left", "up") else ordered[0]
    cx, cy = _center(current)
    vector = {
        "left": (-1.0, 0.0), "right": (1.0, 0.0),
        "up": (0.0, -1.0), "down": (0.0, 1.0),
    }.get(direction)
    if vector is None:
        return None
    dx_axis, dy_axis = vector
    best = None
    for region in values:
        if region.path == current.path:
            continue
        x, y = _center(region)
        dx, dy = x - cx, y - cy
        primary = dx * dx_axis + dy * dy_axis
        if primary <= 1e-6:
            continue
        perpendicular = abs(dx * dy_axis - dy * dx_axis)
        distance = math.hypot(dx, dy)
        score = primary + perpendicular * 2.25 + distance * 0.05
        key = (score, perpendicular, distance, region.path)
        if best is None or key < best[0]:
            best = (key, region)
    return best[1] if best else None


def _dispatch_controller(movie, path, event_type, action, key=""):
    event = lifecycle.RuntimeEvent(event_type, bubbles=True)
    event.extra.update(action=str(action), key=str(key), controller="keyboard")
    delivered = dynamic._dispatch_path(movie, path or "root", event, True)
    store = _button_state_store(movie)
    store["controller_events"] += delivered
    return delivered


def move_focus(owner, direction):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return False
    regions = _candidate_regions(owner)
    current = dynamic._state(movie).get("focus_path", "")
    target = directional_target(regions, current, direction)
    if target is None:
        return False
    dynamic._set_focus(movie, target.path)
    _set_button_state(owner, target.path, "over", request=False)
    store = _button_state_store(movie)
    store["focus_moves"] += 1
    store["last_direction"] = direction
    _dispatch_controller(movie, target.path, "controllerNavigate", direction)
    owner.request_render()
    return True


def set_focus(movie, path):
    old = dynamic._state(movie).get("focus_path", "")
    result = _BASE["focus"](movie, path)
    owner = getattr(movie, "_ui_avm2_runtime_owner", None)
    if owner is not None and _enabled(owner):
        if old and old != path:
            _set_button_state(owner, old, _resting_state(movie, old), request=False)
        if path:
            _set_button_state(owner, path, "over", request=False)
    return result


def motion(owner, event):
    movie = getattr(owner, "_current_movie", None)
    old = dynamic._state(movie).get("hover_path", "") if movie is not None else ""
    result = _BASE["motion"](owner, event)
    if movie is None:
        return result
    new = dynamic._state(movie).get("hover_path", "")
    if old and old != new:
        _set_button_state(owner, old, _resting_state(movie, old), request=False)
    if new:
        _set_button_state(owner, new, "over", request=False)
    if old != new:
        owner.request_render()
    return result


def mouse_event(owner, event, event_type):
    movie = getattr(owner, "_current_movie", None)
    pressed = dynamic._state(movie).get("pressed_path", "") if movie is not None else ""
    result = _BASE["mouse"](owner, event, event_type)
    if movie is None:
        return result
    state = dynamic._state(movie)
    if event_type == "mouseDown":
        path = state.get("pressed_path", "")
        if path:
            _set_button_state(owner, path, "down", request=False)
    elif event_type == "mouseUp":
        if pressed:
            _set_button_state(owner, pressed, _resting_state(movie, pressed), request=False)
        hover = state.get("hover_path", "")
        if hover:
            _set_button_state(owner, hover, "over", request=False)
    owner.request_render()
    return result


def key_event(owner, event, down):
    movie = getattr(owner, "_current_movie", None)
    keysym = str(getattr(event, "keysym", "") or "").lower()
    direction = _DIRECTION_KEYS.get(keysym)
    base_result = _BASE["key"](owner, event, down)

    if movie is not None and down and direction and move_focus(owner, direction):
        _dispatch_controller(
            movie, dynamic._state(movie).get("focus_path", "root"),
            "controllerButtonDown", direction, keysym,
        )
        return "break"

    if movie is not None:
        focus = dynamic._state(movie).get("focus_path", "") or "root"
        if keysym in _ACCEPT_KEYS:
            if down:
                _set_button_state(owner, focus, "down", request=False)
                _dispatch_controller(movie, focus, "controllerButtonDown", "accept", keysym)
            else:
                _set_button_state(owner, focus, _resting_state(movie, focus), request=False)
                _dispatch_controller(movie, focus, "controllerButtonUp", "accept", keysym)
            owner.request_render()
        elif keysym in _CANCEL_KEYS:
            _dispatch_controller(
                movie, focus,
                "controllerButtonDown" if down else "controllerButtonUp",
                "cancel", keysym,
            )
            if down:
                _dispatch_controller(movie, focus, "controllerCancel", "cancel", keysym)
            return "break"

    return base_result


def activate_focus(owner, event=None):
    movie = getattr(owner, "_current_movie", None)
    path = dynamic._state(movie).get("focus_path", "") if movie is not None else ""
    if movie is not None and path:
        _set_button_state(owner, path, "down", request=False)
        _dispatch_controller(movie, path, "controllerAccept", "accept",
                             str(getattr(event, "keysym", "") or ""))
    result = _BASE["activate"](owner, event)
    if movie is not None and path:
        def release():
            if getattr(owner, "_closed", False):
                return
            _set_button_state(owner, path, _resting_state(movie, path))
        try:
            owner.after(90, release)
        except Exception:
            release()
    return result


def browser_init(owner, *args, **kwargs):
    _BASE["browser_init"](owner, *args, **kwargs)
    owner.button_navigation_enabled_var = tk.BooleanVar(value=True)
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Checkbutton(
        bar, text="Button States + Navigation",
        variable=owner.button_navigation_enabled_var,
    ).pack(side="left")
    ttk.Label(
        bar,
        text="Pfeile/WASD = Fokus · Enter/Leertaste = OK · Esc/Backspace = Zurück",
    ).pack(side="left", padx=(10, 0))


def _enabled(owner):
    variable = getattr(owner, "button_navigation_enabled_var", None)
    return bool(variable is None or variable.get())


def guarded_motion(owner, event):
    return motion(owner, event) if _enabled(owner) else _BASE["motion"](owner, event)


def guarded_mouse(owner, event, event_type):
    return mouse_event(owner, event, event_type) if _enabled(owner) else _BASE["mouse"](owner, event, event_type)


def guarded_key(owner, event, down):
    return key_event(owner, event, down) if _enabled(owner) else _BASE["key"](owner, event, down)


def guarded_activate(owner, event=None):
    return activate_focus(owner, event) if _enabled(owner) else _BASE["activate"](owner, event)


def inspect_movie_state(movie, frame, max_depth=64):
    nodes = _BASE["inspect"](movie, frame, max_depth)
    states = _button_state_store(movie)["states"]

    def decorate(values):
        result = []
        for node in values:
            metadata = dict(node.metadata)
            record = states.get(node.path)
            if record:
                metadata["button_state"] = record.get("state", "up")
                metadata["button_frame"] = record.get("frame")
            result.append(inspector.StateNode(
                node.path, node.depth, node.label, node.kind, node.visible,
                node.character_id, node.class_name, metadata, decorate(node.children),
            ))
        return tuple(result)

    return decorate(nodes)


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    state = node.metadata.get("button_state")
    if not state:
        return text
    frame = node.metadata.get("button_frame")
    suffix = f"\n- Ziel-Frame: {frame}" if frame is not None else ""
    return text + "\n\nButton / Navigation:\n" + f"- Zustand: {state}" + suffix


def _looks_button_region(movie, region):
    values = _runtime_values(movie, region.path)
    obj = _dynamic_object(movie, region.path)
    text = _compact(f"{region.name} {region.path}")
    return bool(
        region.tab_enabled
        or values.get("buttonMode", False)
        or (obj is not None and obj.extras.get("buttonMode", False))
        or any(_compact(word) in text for word in _BUTTON_WORDS)
    )


def format_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    store = _button_state_store(movie)
    states = store["states"]
    buttons = sum(
        1 for region in getattr(movie, "ui_input_hit_regions", ()) or ()
        if _looks_button_region(movie, region)
    )
    return text + "\n\nButton / Navigation:\n" + (
        f"- Erkannte Button-Ziele: {buttons}\n"
        f"- Aktive Zustände: {len(states)}\n"
        f"- Zustandswechsel: {store['button_transitions']}\n"
        f"- Richtungs-Fokuswechsel: {store['focus_moves']}\n"
        f"- Controller-Listener: {store['controller_events']}\n"
        f"- Letzte Richtung: {store['last_direction'] or '-'}"
    )


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_button_navigation_state = None
    return _BASE["reset"](owner)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        hit=dynamic._hit,
        focus=dynamic._set_focus,
        motion=dynamic._motion,
        mouse=dynamic._mouse_event,
        key=dynamic._key_event,
        activate=dynamic._activate_focus,
        set=runtime._set_property,
        get=runtime._get_property,
        browser_init=ui_browser.UIBrowser.__init__,
        info=ui_browser.UIBrowser._format_info,
        inspect=inspector.inspect_movie_state,
        format_node=inspector.format_state_node,
        reset=runtime.reset_runtime,
    )
    dynamic._hit = hit
    dynamic._set_focus = set_focus
    dynamic._motion = guarded_motion
    dynamic._mouse_event = guarded_mouse
    dynamic._key_event = guarded_key
    dynamic._activate_focus = guarded_activate
    runtime._set_property = set_property
    runtime._get_property = get_property
    inspector.inspect_movie_state = inspect_movie_state
    ui_browser.inspect_movie_state = inspect_movie_state
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._format_info = format_info
    runtime.reset_runtime = reset_runtime
    lifecycle.reset_runtime = reset_runtime
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime
    ui_browser.infer_ui_button_frame = infer_button_frame
    ui_browser.choose_directional_ui_target = directional_target
    ui_browser.set_ui_button_state = _set_button_state
