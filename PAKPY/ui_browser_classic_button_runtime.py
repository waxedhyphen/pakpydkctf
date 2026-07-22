"""Classic SWF button parsing, safe AVM1 timeline actions and input transitions."""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_button_navigation_patch as button
import ui_browser_classic_button as classic
import ui_browser_precise_hit as precise
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core

_BASE = {}
_MAX_ACTION_LOG = 500


def parse_swf_movie(raw):
    movie = _BASE["parse"](raw)
    definitions, errors = classic.parse_button_tags(getattr(movie, "root_tags", ()))
    movie.definitions.update(definitions)
    classic.finalize_button_bounds(movie)
    movie.ui_classic_button_parse_errors = tuple(errors)
    movie.ui_classic_button_count = len(definitions)
    movie.ui_classic_button_revision = 0
    return movie


def _classic_state(movie):
    value = getattr(movie, "ui_classic_button_runtime", None)
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {"generation": generation, "executed": 0, "blocked": 0, "log": []}
        movie.ui_classic_button_runtime = value
    return value


def _definition_for_path(owner, path):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return None
    try:
        node = button._node_index(owner, movie).get(str(path))
    except Exception:
        node = None
    character_id = getattr(node, "character_id", None) if node is not None else None
    definition = movie.definitions.get(character_id) if character_id is not None else None
    return definition if isinstance(definition, classic.ClassicButtonDef) else None


def _target_info(owner, button_path):
    movie = getattr(owner, "_current_movie", None)
    parent = str(button_path).rsplit("/", 1)[0] if "/" in str(button_path) else "root"
    if parent == "root":
        return parent, max(1, int(movie.frame_count)), dict(getattr(movie, "labels", {}) or {})
    try:
        node = button._node_index(owner, movie).get(parent)
        count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
        labels = dict(node.metadata.get("sprite_labels", {}) or {})
        return parent, count, labels
    except Exception:
        return parent, 1, {}


def _set_target_frame(owner, parent, count, frame, playing=None):
    movie = getattr(owner, "_current_movie", None)
    frame = max(1, min(int(count), int(frame)))
    if parent == "root":
        timeline_core.set_root_frame(owner, frame)
        if playing is True:
            timeline_browser.play(owner)
        elif playing is False:
            timeline_browser.pause(owner)
        return
    states = getattr(movie, "ui_timeline_states", None)
    if not isinstance(states, dict):
        states = {}
        movie.ui_timeline_states = states
    state = states.setdefault(parent, timeline_core.normalize_timeline_instance({}, count))
    state.update(frame=frame, frame_count=count)
    if playing is not None:
        state["playing"] = bool(playing)
    state.pop("_avm2_runtime_token", None)


def _execute_action(owner, button_path, condition, action):
    movie = getattr(owner, "_current_movie", None)
    state = _classic_state(movie)
    parent, count, labels = _target_info(owner, button_path)
    executed = False
    if action.name == "NextFrame":
        current = int(owner.frame_var.get()) if parent == "root" else int(
            getattr(movie, "ui_timeline_states", {}).get(parent, {}).get("frame", 1)
        )
        _set_target_frame(owner, parent, count, min(count, current + 1), False)
        executed = True
    elif action.name == "PreviousFrame":
        current = int(owner.frame_var.get()) if parent == "root" else int(
            getattr(movie, "ui_timeline_states", {}).get(parent, {}).get("frame", 1)
        )
        _set_target_frame(owner, parent, count, max(1, current - 1), False)
        executed = True
    elif action.name == "Play":
        if parent == "root":
            timeline_browser.play(owner)
        else:
            current = int(getattr(movie, "ui_timeline_states", {}).get(parent, {}).get("frame", 1))
            _set_target_frame(owner, parent, count, current, True)
        executed = True
    elif action.name == "Stop":
        if parent == "root":
            timeline_browser.pause(owner)
        else:
            current = int(getattr(movie, "ui_timeline_states", {}).get(parent, {}).get("frame", 1))
            _set_target_frame(owner, parent, count, current, False)
        executed = True
    elif action.name == "GotoFrame" and isinstance(action.argument, int):
        _set_target_frame(owner, parent, count, action.argument)
        executed = True
    elif action.name == "GotoLabel" and isinstance(action.argument, str):
        frame = labels.get(action.argument)
        if frame is not None:
            _set_target_frame(owner, parent, count, frame)
            executed = True

    record = {
        "path": str(button_path), "condition": str(condition),
        "action": action.name, "argument": action.argument,
        "executed": executed,
    }
    state["log"].append(record)
    del state["log"][:-_MAX_ACTION_LOG]
    state["executed" if executed else "blocked"] += 1
    runtime._log(movie, "classic-button-action", **record)
    return executed


def trigger_condition(owner, path, condition, key_code=0):
    definition = _definition_for_path(owner, path)
    if definition is None:
        return 0
    executed = 0
    for binding in definition.button_actions:
        if key_code:
            if int(binding.key_code) != int(key_code):
                continue
        elif condition not in binding.conditions:
            continue
        for action in binding.actions:
            executed += int(_execute_action(owner, path, condition, action))
    if executed:
        movie = getattr(owner, "_current_movie", None)
        movie.ui_classic_button_revision = int(getattr(movie, "ui_classic_button_revision", 0)) + 1
        precise.clear_geometry_cache()
        timeline_core.request_timeline_render(owner)
    return executed


def dispatch_path(movie, path, event, bubble=False):
    result = _BASE["dispatch"](movie, path, event, bubble)
    owner = getattr(movie, "_ui_avm2_runtime_owner", None)
    if owner is None:
        return result
    event_type = str(getattr(event, "type", "") or "")
    pressed = dynamic._state(movie).get("pressed_path", "")
    condition = None
    if event_type == "mouseOver":
        condition = "out_down_to_over_down" if pressed == path else "idle_to_over_up"
    elif event_type == "mouseOut":
        condition = "over_down_to_out_down" if pressed == path else "over_up_to_idle"
    elif event_type == "mouseDown":
        condition = "over_up_to_over_down"
    elif event_type == "mouseUp":
        condition = "over_down_to_over_up"
    if condition:
        trigger_condition(owner, path, condition)
    return result


def mouse_event(owner, event, event_type):
    movie = getattr(owner, "_current_movie", None)
    pressed = dynamic._state(movie).get("pressed_path", "") if movie is not None else ""
    result = _BASE["mouse_event"](owner, event, event_type)
    if movie is not None and event_type == "mouseUp" and pressed:
        hover = dynamic._state(movie).get("hover_path", "")
        if hover != pressed:
            trigger_condition(owner, pressed, "over_down_to_out_down")
            trigger_condition(owner, pressed, "out_down_to_idle")
    return result


def _swf_key_code(event):
    key = str(getattr(event, "keysym", "") or "").lower()
    special = {
        "left": 1, "right": 2, "home": 3, "end": 4, "insert": 5,
        "delete": 6, "backspace": 8, "return": 13, "kp_enter": 13,
        "up": 14, "down": 15, "prior": 16, "next": 17, "tab": 18,
        "escape": 19, "space": 32,
    }
    if key in special:
        return special[key]
    char = str(getattr(event, "char", "") or "")
    return ord(char[0]) & 0x7F if char else 0


def key_event(owner, event, down):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None and down:
        path = dynamic._state(movie).get("focus_path", "")
        code = _swf_key_code(event)
        if path and code:
            trigger_condition(owner, path, "key_press", code)
    return _BASE["key_event"](owner, event, down)


def activate_focus(owner, event=None):
    movie = getattr(owner, "_current_movie", None)
    path = dynamic._state(movie).get("focus_path", "") if movie is not None else ""
    if path:
        trigger_condition(owner, path, "over_up_to_over_down")
    result = _BASE["activate_focus"](owner, event)
    if path:
        trigger_condition(owner, path, "over_down_to_over_up")
    return result


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_classic_button_runtime = None
        precise.reset_movie(movie)
    return _BASE["reset"](owner)


def install_hooks(base_parse, base_dispatch, base_mouse_event, base_key_event,
                  base_activate_focus, base_reset):
    _BASE.update(
        parse=base_parse, dispatch=base_dispatch, mouse_event=base_mouse_event,
        key_event=base_key_event, activate_focus=base_activate_focus, reset=base_reset,
    )
