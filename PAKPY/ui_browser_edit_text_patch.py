"""Editable TextField input, selection and bounded clipboard support for the UI Browser.

The patch is installed after the classic-button/precise-hit layer.  It keeps all text
changes in the per-movie preview runtime, never mutates SWF/GFX resources and only reads
or writes the platform clipboard in direct response to Ctrl+C/X/V.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import filedialog, ttk

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_button_navigation_patch as button
import ui_browser_precise_hit as precise
import ui_browser_shape_patch as shape_patch
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as overrides_patch
import ui_browser_text_patch as text_patch
import ui_browser_edit_text_model as model

try:
    from PIL import Image, ImageDraw
except Exception:
    Image = None
    ImageDraw = None


_INSTALLED = False
_BASE = {}
_MAX_EDIT_LOG = 500
_TEXT_PROPERTIES = {
    "type", "selectable", "maxChars", "restrict", "displayAsPassword",
    "multiline", "wordWrap", "selectionBeginIndex", "selectionEndIndex",
    "caretIndex",
}


def _short(value):
    return str(value or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]


def _state(movie):
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    value = getattr(movie, "ui_edit_text_state", None)
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {
            "generation": generation,
            "active": None,
            "revision": 0,
            "starts": 0,
            "commits": 0,
            "cancels": 0,
            "changes": 0,
            "clipboard_reads": 0,
            "clipboard_writes": 0,
            "blocked": 0,
            "log": [],
        }
        movie.ui_edit_text_state = value
    return value


def _log(movie, action, **values):
    state = _state(movie)
    record = {"action": str(action), **{str(k): v for k, v in values.items()}}
    state["log"].append(record)
    del state["log"][:-_MAX_EDIT_LOG]
    runtime._log(movie, "edit-text", **record)


def _touch(movie):
    state = _state(movie)
    state["revision"] = int(state.get("revision", 0)) + 1
    dynamic._touch(movie)


def _enabled(owner):
    variable = getattr(owner, "edit_text_input_enabled_var", None)
    return bool(variable is None or variable.get())


def _node(owner, path):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return None
    try:
        return button._node_index(owner, movie).get(str(path))
    except Exception:
        return None


def _definition(owner, path):
    movie = getattr(owner, "_current_movie", None)
    node = _node(owner, path)
    character_id = getattr(node, "character_id", None) if node is not None else None
    return movie.definitions.get(character_id) if movie is not None and character_id is not None else None


def _manual_text(movie, path):
    value = overrides_patch.normalize_override(
        (getattr(movie, "ui_state_overrides", {}) or {}).get(str(path), {}),
    )
    return "text" in value


def _property_store(movie, path):
    return runtime._properties(movie).setdefault(str(path), {})


def _dynamic_object(movie, path):
    try:
        return dynamic._dynamic_for_path(movie, path)
    except Exception:
        return None


def _runtime_value(movie, path, name, default=None):
    obj = _dynamic_object(movie, path)
    if obj is not None and name in obj.extras:
        return obj.extras.get(name, default)
    return (runtime._properties(movie).get(str(path), {}) or {}).get(name, default)


def _default_input_type(definition):
    if isinstance(definition, ui_browser.EditTextDef) and not bool(getattr(definition, "read_only", True)):
        return "input"
    return "dynamic"


def _target(owner, path, require_editable=True):
    movie = getattr(owner, "_current_movie", None)
    path = str(path or "")
    if movie is None or not path:
        return None
    obj = _dynamic_object(movie, path)
    definition = getattr(obj, "definition", None) if obj is not None else _definition(owner, path)
    if obj is None and not isinstance(definition, ui_browser.EditTextDef):
        return None
    if obj is not None and obj.kind != "TextField" and not isinstance(definition, ui_browser.EditTextDef):
        return None
    if _manual_text(movie, path):
        return None

    values = runtime._properties(movie).get(path, {}) or {}
    extras = obj.extras if obj is not None else {}
    field_type = str(extras.get("type", values.get("type", _default_input_type(definition))) or "dynamic").lower()
    selectable_default = not bool(getattr(definition, "no_select", False))
    selectable = bool(extras.get("selectable", values.get("selectable", selectable_default)))
    editable = field_type == "input" and selectable
    if require_editable and not editable:
        return None

    node = _node(owner, path)
    node_meta = dict(getattr(node, "metadata", {}) or {}) if node is not None else {}
    if obj is not None:
        text = str(obj.html_text or obj.text or "")
        variable_name = str(obj.name or getattr(definition, "variable_name", "") or "")
    else:
        text = values.get("htmlText", values.get("text", None))
        if text is None:
            text = node_meta.get("display_text", getattr(definition, "initial_text", ""))
        text = str(text or "")
        variable_name = str(getattr(definition, "variable_name", "") or node_meta.get("variable_name", ""))

    max_chars = extras.get("maxChars", values.get("maxChars", getattr(definition, "max_length", 0)))
    try:
        max_chars = max(0, min(model.MAX_TEXT_CHARS, int(max_chars or 0)))
    except Exception:
        max_chars = 0
    restrict = str(extras.get("restrict", values.get("restrict", "")) or "")[:model.MAX_RESTRICT_PATTERN]
    multiline = bool(extras.get("multiline", values.get("multiline", getattr(definition, "multiline", False))))
    password = bool(extras.get(
        "displayAsPassword", values.get("displayAsPassword", getattr(definition, "password", False)),
    ))
    return model.EditableTarget(
        path=path, text=text, multiline=multiline, selectable=selectable,
        max_chars=max_chars, restrict=restrict, password=password,
        dynamic=obj is not None, variable_name=variable_name,
    )


def _active(movie):
    value = _state(movie).get("active")
    return value if isinstance(value, model.EditSession) and value.active else None


def _sync_selection(movie, session):
    values = _property_store(movie, session.path)
    start, end = session.selection
    values["selectionBeginIndex"] = start
    values["selectionEndIndex"] = end
    values["caretIndex"] = session.caret
    obj = _dynamic_object(movie, session.path)
    if obj is not None:
        obj.extras.update(
            selectionBeginIndex=start, selectionEndIndex=end, caretIndex=session.caret,
        )


def _clear_localization_source(movie, path):
    values = getattr(movie, "ui_localized_runtime_sources", None)
    if isinstance(values, dict):
        values.pop((str(path), "text"), None)
        values.pop((str(path), "htmlText"), None)


def _write_text(owner, target, session, dispatch_change=True):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return False
    text = str(session.text)[:target.bounded_max_chars]
    session.text = text
    obj = _dynamic_object(movie, target.path)
    if obj is not None:
        obj.text = text
        obj.html_text = ""
    else:
        values = _property_store(movie, target.path)
        values["text"] = text
        values.pop("htmlText", None)
    _clear_localization_source(movie, target.path)
    _sync_selection(movie, session)
    _touch(movie)
    if dispatch_change:
        event = lifecycle.RuntimeEvent("change", bubbles=True)
        event.extra.update(text=text, caretIndex=session.caret,
                           selectionBeginIndex=session.selection[0],
                           selectionEndIndex=session.selection[1])
        dynamic._dispatch_path(movie, target.path, event, True)
        _state(movie)["changes"] += 1
    try:
        owner.request_render()
    except Exception:
        pass
    return True


def _dispatch_key(movie, path, event, down):
    value = lifecycle.RuntimeEvent("keyDown" if down else "keyUp", bubbles=True)
    char = str(getattr(event, "char", "") or "")
    value.extra.update(
        keyCode=int(getattr(event, "keycode", 0) or 0),
        charCode=ord(char[0]) if char else 0,
        key=str(getattr(event, "keysym", "") or ""),
        shiftKey=bool(int(getattr(event, "state", 0) or 0) & 0x0001),
        ctrlKey=bool(int(getattr(event, "state", 0) or 0) & 0x0004),
        altKey=bool(int(getattr(event, "state", 0) or 0) & 0x0008),
    )
    dynamic._dispatch_path(movie, path, value, True)


def _dispatch_text_input(movie, path, text):
    event = lifecycle.RuntimeEvent("textInput", bubbles=True, cancelable=True)
    event.extra.update(text=str(text), data=str(text))
    dynamic._dispatch_path(movie, path, event, True)
    return not event.default_prevented


def _font_for(owner, definition):
    resolver = getattr(owner, "_current_resolver", None)
    if resolver is None or definition is None:
        return None
    try:
        return text_patch._font_for(SimpleNamespace(resolver=resolver), definition)
    except Exception:
        return None


def _definition_proxy(owner, target):
    definition = _definition(owner, target.path)
    obj = _dynamic_object(getattr(owner, "_current_movie", None), target.path)
    if definition is None and obj is not None:
        definition = getattr(obj, "definition", None)
    if definition is not None and hasattr(definition, "bounds"):
        return definition
    width = float(getattr(obj, "width", 160.0) if obj is not None else 160.0)
    height = float(getattr(obj, "height", 32.0) if obj is not None else 32.0)
    return SimpleNamespace(
        bounds=(0.0, 0.0, max(1.0, width), max(1.0, height)),
        font_height=18.0, left_margin=0.0, right_margin=0.0, indent=0.0,
        leading=0.0, align=0, word_wrap=False,
    )


def _advance(font, char, size):
    if font is not None:
        try:
            return max(0.0, float(font.advance(ord(char), size)))
        except Exception:
            pass
    return max(1.0, float(size) * (0.32 if char.isspace() else 0.55))


def _visual_lines(definition, text, font):
    xmin, ymin, xmax, ymax = tuple(getattr(definition, "bounds", (0.0, 0.0, 160.0, 32.0)))
    size = max(1.0, float(getattr(definition, "font_height", 18.0) or 18.0))
    left = float(getattr(definition, "left_margin", 0.0) or 0.0)
    right = float(getattr(definition, "right_margin", 0.0) or 0.0)
    available = max(1.0, xmax - xmin - left - right)
    line_height = max(1.0, size * 1.08 + float(getattr(definition, "leading", 0.0) or 0.0))
    wrap = bool(getattr(definition, "word_wrap", False))
    lines = []
    start = 0
    positions = [left]
    width = 0.0
    for index, char in enumerate(str(text)):
        if char == "\n":
            lines.append((start, index, positions, width))
            start = index + 1
            positions = [left]
            width = 0.0
            continue
        advance = _advance(font, char, size)
        if wrap and width > 0.0 and width + advance > available:
            lines.append((start, index, positions, width))
            start = index
            positions = [left]
            width = 0.0
        width += advance
        positions.append(left + width)
    lines.append((start, len(str(text)), positions, width))
    result = []
    align_value = getattr(definition, "align", 0)
    for line_index, (line_start, line_end, xs, line_width) in enumerate(lines):
        if align_value in (2, "center"):
            offset = max(0.0, (available - line_width) * 0.5)
        elif align_value in (1, "right"):
            offset = max(0.0, available - line_width)
        else:
            offset = float(getattr(definition, "indent", 0.0) or 0.0) if line_index == 0 else 0.0
        xs = [xmin + value + offset for value in xs]
        result.append({
            "start": line_start, "end": line_end, "xs": xs,
            "top": ymin + line_index * line_height,
            "bottom": ymin + (line_index + 1) * line_height,
        })
    return result


def _caret_from_point(owner, target, point):
    if point is None:
        return len(target.text)
    movie = getattr(owner, "_current_movie", None)
    geometries = tuple((getattr(movie, "ui_precise_hit_geometries", {}) or {}).get(target.path, ()))
    local = point
    if geometries:
        try:
            local = geometries[0].local_point(point)
        except Exception:
            local = point
    definition = _definition_proxy(owner, target)
    font = _font_for(owner, definition)
    lines = _visual_lines(definition, model.display_text(target.text, target.password), font)
    if not lines:
        return len(target.text)
    x, y = local
    line = min(lines, key=lambda item: 0.0 if item["top"] <= y <= item["bottom"] else
               min(abs(y - item["top"]), abs(y - item["bottom"])))
    xs = line["xs"]
    if not xs:
        return line["start"]
    offset = min(range(len(xs)), key=lambda index: abs(xs[index] - x))
    return max(line["start"], min(line["end"], line["start"] + offset))


def begin_edit(owner, path, point=None):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not _enabled(owner):
        return None
    target = _target(owner, path, True)
    if target is None:
        return None
    state = _state(movie)
    current = _active(movie)
    if current is not None and current.path != target.path:
        commit_edit(owner, "focus-change")
    current = _active(movie)
    caret = _caret_from_point(owner, target, point)
    if current is None:
        current = model.EditSession(target.path, target.text, target.text, caret, caret)
        state["active"] = current
        state["starts"] += 1
        _log(movie, "begin", path=target.path, length=len(target.text))
    else:
        current.anchor = current.caret = caret
        current.dragging = bool(point is not None)
    _sync_selection(movie, current)
    _touch(movie)
    try:
        owner.request_render()
    except Exception:
        pass
    return current


def commit_edit(owner, reason="commit"):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return False
    session = _active(movie)
    if session is None:
        return False
    session.active = False
    session.dragging = False
    _state(movie)["active"] = None
    _state(movie)["commits"] += 1
    _log(movie, "commit", path=session.path, reason=str(reason), length=len(session.text))
    _touch(movie)
    return True


def cancel_edit(owner, reason="cancel"):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return False
    session = _active(movie)
    if session is None:
        return False
    target = _target(owner, session.path, False)
    session.text = session.original_text
    session.anchor = session.caret = len(session.text)
    if target is not None:
        _write_text(owner, target, session, dispatch_change=True)
    session.active = False
    session.dragging = False
    _state(movie)["active"] = None
    _state(movie)["cancels"] += 1
    _log(movie, "cancel", path=session.path, reason=str(reason))
    _touch(movie)
    return True


def _selection_changed(owner, session):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    _sync_selection(movie, session)
    event = lifecycle.RuntimeEvent("select", bubbles=False)
    event.extra.update(selectionBeginIndex=session.selection[0],
                       selectionEndIndex=session.selection[1], caretIndex=session.caret)
    dynamic._dispatch_path(movie, session.path, event, False)
    _touch(movie)
    try:
        owner.request_render()
    except Exception:
        pass


def _mutate(owner, operation, inserted_text=None):
    movie = getattr(owner, "_current_movie", None)
    session = _active(movie) if movie is not None else None
    if session is None:
        return False
    target = _target(owner, session.path, True)
    if target is None:
        commit_edit(owner, "target-gone")
        return False
    if inserted_text is not None and not _dispatch_text_input(movie, session.path, inserted_text):
        _state(movie)["blocked"] += 1
        _log(movie, "blocked", path=session.path, text=str(inserted_text)[:80])
        return False
    changed = bool(operation(session, target))
    if changed:
        _write_text(owner, target, session, dispatch_change=True)
    else:
        _selection_changed(owner, session)
    return changed


def _clipboard_write(owner, text):
    movie = getattr(owner, "_current_movie", None)
    try:
        owner.clipboard_clear()
        owner.clipboard_append(str(text)[:model.MAX_CLIPBOARD_CHARS])
        owner.update_idletasks()
        if movie is not None:
            _state(movie)["clipboard_writes"] += 1
        return True
    except Exception as exc:
        if movie is not None:
            _log(movie, "clipboard-error", operation="write", error=str(exc))
        return False


def _clipboard_read(owner, multiline):
    movie = getattr(owner, "_current_movie", None)
    try:
        value = owner.clipboard_get()
        if movie is not None:
            _state(movie)["clipboard_reads"] += 1
        return model.sanitize_clipboard(value, multiline)
    except Exception as exc:
        if movie is not None:
            _log(movie, "clipboard-error", operation="read", error=str(exc))
        return ""


def _modifiers(event):
    state = int(getattr(event, "state", 0) or 0)
    return bool(state & 0x0001), bool(state & 0x0004), bool(state & 0x0008)


def _handle_edit_key(owner, event, down):
    movie = getattr(owner, "_current_movie", None)
    session = _active(movie) if movie is not None else None
    if session is None:
        focus = dynamic._state(movie).get("focus_path", "") if movie is not None else ""
        if focus:
            session = begin_edit(owner, focus)
    if session is None:
        return None
    _dispatch_key(movie, session.path, event, down)
    if not down:
        return "break"

    target = _target(owner, session.path, True)
    if target is None:
        return None
    key = str(getattr(event, "keysym", "") or "").lower()
    char = str(getattr(event, "char", "") or "")
    shift, control, alt = _modifiers(event)

    if control and key in ("a",):
        model.select_all(session)
        _selection_changed(owner, session)
        return "break"
    if control and key in ("c", "insert"):
        if target.selectable and not target.password:
            _clipboard_write(owner, session.selected_text)
        return "break"
    if control and key == "x":
        if target.selectable and not target.password and session.selected_text:
            _clipboard_write(owner, session.selected_text)
            _mutate(owner, lambda value, item: model.replace_selection(value, item, ""), "")
        return "break"
    if control and key == "v":
        value = _clipboard_read(owner, target.multiline)
        if value:
            _mutate(owner, lambda current, item, value=value: model.insert_text(current, item, value), value)
        return "break"
    if control and key == "z":
        changed = session.redo_once() if shift else session.undo_once()
        if changed:
            _write_text(owner, target, session, dispatch_change=True)
        return "break"
    if control and key == "y":
        if session.redo_once():
            _write_text(owner, target, session, dispatch_change=True)
        return "break"

    directions = {
        "left": "left", "right": "right", "home": "home", "end": "end",
        "up": "up", "down": "down",
    }
    if key in directions:
        model.move_caret(session, directions[key], extend=shift, by_word=control)
        _selection_changed(owner, session)
        return "break"
    if key == "backspace":
        _mutate(owner, lambda value, item: model.delete_backward(value, item, control))
        return "break"
    if key == "delete":
        _mutate(owner, lambda value, item: model.delete_forward(value, item, control))
        return "break"
    if key in ("return", "kp_enter"):
        if target.multiline and not control:
            _mutate(owner, lambda value, item: model.insert_text(value, item, "\n"), "\n")
        else:
            commit_edit(owner, "enter")
        return "break"
    if key == "escape":
        cancel_edit(owner, "escape")
        return "break"
    if key in ("tab", "iso_left_tab"):
        commit_edit(owner, "tab")
        return None
    if char and not control and not alt and (ord(char[0]) >= 32 or char in "\t"):
        value = char[0]
        _mutate(owner, lambda current, item, value=value: model.insert_text(current, item, value), value)
        return "break"
    return "break"


def key_event(owner, event, down):
    result = _handle_edit_key(owner, event, down)
    if result is not None:
        return result
    return _BASE["key"](owner, event, down)


def activate_focus(owner, event=None):
    movie = getattr(owner, "_current_movie", None)
    session = _active(movie) if movie is not None else None
    if session is None and movie is not None:
        focus = dynamic._state(movie).get("focus_path", "")
        if focus:
            session = begin_edit(owner, focus)
    if session is None:
        return _BASE["activate"](owner, event)
    target = _target(owner, session.path, True)
    key = str(getattr(event, "keysym", "") or "").lower()
    if key == "space":
        _mutate(owner, lambda value, item: model.insert_text(value, item, " "), " ")
    elif target is not None and target.multiline:
        _mutate(owner, lambda value, item: model.insert_text(value, item, "\n"), "\n")
    else:
        commit_edit(owner, "activate")
    return "break"


def mouse_event(owner, event, event_type):
    result = _BASE["mouse"](owner, event, event_type)
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not _enabled(owner):
        return result
    state = dynamic._state(movie)
    if event_type == "mouseDown":
        path = state.get("pressed_path", "")
        if path:
            session = begin_edit(owner, path, dynamic._stage_point(owner, event))
            if session is not None:
                session.dragging = True
                return "break"
        commit_edit(owner, "mouse-outside")
    elif event_type == "mouseUp":
        session = _active(movie)
        if session is not None:
            session.dragging = False
    return result


def motion(owner, event):
    result = _BASE["motion"](owner, event)
    movie = getattr(owner, "_current_movie", None)
    session = _active(movie) if movie is not None else None
    if session is None or not session.dragging:
        return result
    target = _target(owner, session.path, True)
    point = dynamic._stage_point(owner, event)
    if target is None or point is None:
        return result
    caret = _caret_from_point(owner, model.EditableTarget(
        target.path, session.text, target.multiline, target.selectable,
        target.max_chars, target.restrict, target.password, target.dynamic,
        target.variable_name,
    ), point)
    if caret != session.caret:
        session.caret = caret
        _selection_changed(owner, session)
    return "break"


def set_focus(movie, path):
    owner = getattr(movie, "_ui_avm2_runtime_owner", None)
    current = _active(movie)
    if current is not None and str(path or "") != current.path and owner is not None:
        commit_edit(owner, "focus-change")
    return _BASE["focus"](movie, path)


def focus_cycle(owner, reverse=False):
    commit_edit(owner, "focus-cycle")
    return _BASE["focus_cycle"](owner, reverse)


def _receiver_path(receiver):
    if isinstance(receiver, dynamic.DynamicDisplayObject):
        return receiver.path
    if isinstance(receiver, runtime.RuntimeRef):
        return receiver.path
    return ""


def _store_text_property(movie, receiver, short, value):
    path = _receiver_path(receiver)
    obj = _dynamic_object(movie, path)
    if obj is not None:
        obj.extras[short] = value
    elif path:
        _property_store(movie, path)[short] = value
    return path


def set_property(context, reference, name, value):
    short = _short(name)
    if short in _TEXT_PROPERTIES:
        if short == "type":
            value = "input" if str(value).lower() == "input" else "dynamic"
        elif short in ("selectable", "displayAsPassword", "multiline", "wordWrap"):
            value = bool(value)
        elif short in ("maxChars", "selectionBeginIndex", "selectionEndIndex", "caretIndex"):
            try:
                value = max(0, min(model.MAX_TEXT_CHARS, int(value or 0)))
            except Exception:
                value = 0
        elif short == "restrict":
            value = str(value or "")[:model.MAX_RESTRICT_PATTERN]
        path = _store_text_property(context.movie, reference, short, value)
        session = _active(context.movie)
        if session is not None and session.path == path:
            if short == "selectionBeginIndex":
                session.anchor = model.clamp_index(session.text, value)
            elif short in ("selectionEndIndex", "caretIndex"):
                session.caret = model.clamp_index(session.text, value)
            _sync_selection(context.movie, session)
        context.writes += 1
        _touch(context.movie)
        return True
    result = _BASE["set"](context, reference, name, value)
    if short in ("text", "htmlText"):
        path = _receiver_path(reference)
        session = _active(context.movie)
        if session is not None and session.path == path:
            session.text = str(value or "")[:model.MAX_TEXT_CHARS]
            session.anchor = session.caret = len(session.text)
            _sync_selection(context.movie, session)
    return result


def get_property(context, receiver, name):
    short = _short(name)
    path = _receiver_path(receiver)
    if path and short in _TEXT_PROPERTIES | {"selectedText"}:
        owner = getattr(context.movie, "_ui_avm2_runtime_owner", None)
        target = _target(owner, path, False) if owner is not None else None
        session = _active(context.movie)
        values = runtime._properties(context.movie).get(path, {}) or {}
        obj = _dynamic_object(context.movie, path)
        extras = obj.extras if obj is not None else {}
        if short == "selectedText":
            return session.selected_text if session is not None and session.path == path else ""
        if short == "selectionBeginIndex":
            return session.selection[0] if session is not None and session.path == path else int(extras.get(short, values.get(short, 0)) or 0)
        if short == "selectionEndIndex":
            return session.selection[1] if session is not None and session.path == path else int(extras.get(short, values.get(short, 0)) or 0)
        if short == "caretIndex":
            return session.caret if session is not None and session.path == path else int(extras.get(short, values.get(short, 0)) or 0)
        if short == "type":
            return str(extras.get(short, values.get(short, _default_input_type(_definition(owner, path) if owner is not None else None))))
        if short == "selectable":
            default = bool(target.selectable) if target is not None else True
            return bool(extras.get(short, values.get(short, default)))
        if short == "maxChars":
            return int(extras.get(short, values.get(short, target.max_chars if target is not None else 0)) or 0)
        if short == "restrict":
            return str(extras.get(short, values.get(short, target.restrict if target is not None else "")) or "")
        if short == "displayAsPassword":
            return bool(extras.get(short, values.get(short, target.password if target is not None else False)))
        if short == "multiline":
            return bool(extras.get(short, values.get(short, target.multiline if target is not None else False)))
        if short == "wordWrap":
            return bool(extras.get(short, values.get(short, False)))
    return _BASE["get"](context, receiver, name)


def _programmatic_session(context, receiver):
    path = _receiver_path(receiver)
    owner = getattr(context.movie, "_ui_avm2_runtime_owner", None)
    target = _target(owner, path, False) if owner is not None else None
    if target is None:
        return owner, target, None
    session = model.EditSession(path, target.text, target.text, len(target.text), len(target.text))
    begin = int(_runtime_value(context.movie, path, "selectionBeginIndex", len(target.text)) or 0)
    end = int(_runtime_value(context.movie, path, "selectionEndIndex", begin) or begin)
    session.anchor = model.clamp_index(session.text, begin)
    session.caret = model.clamp_index(session.text, end)
    return owner, target, session


def call_value(context, receiver, name, args):
    lower = _short(name).lower()
    if lower not in ("setselection", "replaceselectedtext", "replacetext", "appendtext"):
        return _BASE["call"](context, receiver, name, args)
    owner, target, session = _programmatic_session(context, receiver)
    if owner is None or target is None or session is None:
        return runtime._UNDEFINED
    if lower == "setselection" and len(args) >= 2:
        session.anchor = model.clamp_index(session.text, args[0])
        session.caret = model.clamp_index(session.text, args[1])
        _sync_selection(context.movie, session)
        _touch(context.movie)
        return runtime._UNDEFINED
    changed = False
    if lower == "replaceselectedtext" and args:
        changed = model.replace_selection(session, target, str(args[0] or ""))
    elif lower == "replacetext" and len(args) >= 3:
        changed = model.replace_text(session, target, args[0], args[1], str(args[2] or ""))
    elif lower == "appendtext" and args:
        session.anchor = session.caret = len(session.text)
        changed = model.insert_text(session, target, str(args[0] or ""))
    if changed:
        _write_text(owner, target, session, dispatch_change=False)
        context.writes += 1
    return runtime._UNDEFINED


def parse_edit_text(payload):
    definition = _BASE["parse_edit_text"](payload)
    try:
        _bounds, p = ui_browser._read_rect(payload, 2)
        flags1 = payload[p]
        definition.password = bool(flags1 & 0x10)
        definition.selectable = not bool(getattr(definition, "no_select", False))
    except Exception:
        definition.password = False
        definition.selectable = not bool(getattr(definition, "no_select", False))
    return definition


def _overlay(renderer, canvas, definition, matrix, session, target):
    if Image is None or ImageDraw is None:
        return
    bounds = tuple(getattr(definition, "bounds", (0.0, 0.0, 1.0, 1.0)))
    xmin, ymin, xmax, ymax = bounds
    width = max(1, int(round(xmax - xmin)))
    height = max(1, int(round(ymax - ymin)))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer, "RGBA")
    font = None
    try:
        font = text_patch._font_for(renderer, definition)
    except Exception:
        pass
    shown = model.display_text(session.text, target.password)
    lines = _visual_lines(definition, shown, font)
    start, end = session.selection
    for line in lines:
        selected_start = max(start, line["start"])
        selected_end = min(end, line["end"])
        if selected_start < selected_end:
            left_index = selected_start - line["start"]
            right_index = selected_end - line["start"]
            xs = line["xs"]
            left = xs[min(left_index, len(xs) - 1)] - xmin
            right = xs[min(right_index, len(xs) - 1)] - xmin
            draw.rectangle((left, line["top"] - ymin, right, line["bottom"] - ymin),
                           fill=(70, 130, 230, 105))
    caret_line = next((line for line in lines if line["start"] <= session.caret <= line["end"]), lines[-1] if lines else None)
    if caret_line is not None:
        index = max(0, min(len(caret_line["xs"]) - 1, session.caret - caret_line["start"]))
        x = caret_line["xs"][index] - xmin
        draw.line((x, caret_line["top"] - ymin + 1, x, caret_line["bottom"] - ymin - 1),
                  fill=(255, 255, 255, 235), width=1)
    local = ui_browser.Affine(1, 0, 0, 1, xmin, ymin)
    shape_patch._draw_transformed_image(renderer, canvas, layer, matrix.then(local))


def draw_edit_text(renderer, canvas, definition, matrix, color):
    path = str(getattr(renderer, "_ui_current_path", "") or "")
    movie = renderer.movie
    owner = getattr(movie, "_ui_avm2_runtime_owner", None)
    session = _active(movie)
    target = _target(owner, path, False) if owner is not None and path else None
    rendered = definition
    if target is not None and (target.password or (session is not None and session.path == path)):
        rendered = copy.copy(definition)
        raw = session.text if session is not None and session.path == path else target.text
        rendered.initial_text = model.display_text(raw, target.password)
        if hasattr(rendered, "html"):
            rendered.html = False
    result = _BASE["draw_edit_text"](renderer, canvas, rendered, matrix, color)
    if session is not None and session.path == path and target is not None:
        _overlay(renderer, canvas, rendered, matrix, session, target)
        renderer.stats.editable_text_active = getattr(renderer.stats, "editable_text_active", 0) + 1
    return result


def _decorate_nodes(owner, movie, nodes):
    session = _active(movie)
    result = []
    for node in tuple(nodes or ()):
        metadata = dict(node.metadata)
        children = _decorate_nodes(owner, movie, node.children)
        target = _target(owner, node.path, False) if node.kind in ("EditText", "DynamicTextField") else None
        if target is not None:
            metadata["edit_text"] = {
                "editable": _target(owner, node.path, True) is not None,
                "selectable": target.selectable,
                "multiline": target.multiline,
                "max_chars": target.max_chars,
                "restrict": target.restrict,
                "password": target.password,
                "active": session is not None and session.path == node.path,
            }
            if session is not None and session.path == node.path:
                metadata["edit_text"].update(
                    caret=session.caret, selection=session.selection,
                    selected_length=len(session.selected_text),
                )
        result.append(inspector.StateNode(
            node.path, node.depth, node.label, node.kind, node.visible,
            node.character_id, node.class_name, metadata, children,
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    owner = getattr(movie, "_ui_avm2_runtime_owner", None)
    nodes = _BASE["inspect"](movie, frame, max_depth)
    return _decorate_nodes(owner, movie, nodes) if owner is not None else nodes


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    item = node.metadata.get("edit_text")
    if not item:
        return text
    lines = [
        "", "EditText-Eingabe:",
        f"- Editierbar: {'ja' if item.get('editable') else 'nein'}",
        f"- Selektierbar: {'ja' if item.get('selectable') else 'nein'}",
        f"- Mehrzeilig: {'ja' if item.get('multiline') else 'nein'}",
        f"- Passwortdarstellung: {'ja' if item.get('password') else 'nein'}",
        f"- MaxChars: {item.get('max_chars') or 'unbegrenzt'}",
        f"- Restrict: {item.get('restrict') or '-'}",
        f"- Aktiv: {'ja' if item.get('active') else 'nein'}",
    ]
    if item.get("active"):
        lines.extend((
            f"- Caret: {item.get('caret', 0)}",
            f"- Auswahl: {item.get('selection', (0, 0))}",
        ))
    return text + "\n".join(lines)


class EditTextInspector(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI EditText-Eingabe")
        self.geometry("1180x720")
        self.minsize(820, 520)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        bar = ttk.Frame(self, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=self.search_var, width=36)
        entry.pack(side="left", padx=5)
        entry.bind("<KeyRelease>", lambda _event: self.refresh())
        ttk.Button(bar, text="Aktive Eingabe abschließen", command=lambda: self._finish(False)).pack(side="right")
        ttk.Button(bar, text="Abbrechen", command=lambda: self._finish(True)).pack(side="right", padx=(0, 5))
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(pane)
        self.tree = ttk.Treeview(left, columns=("editable", "flags", "text"), show="tree headings")
        for column, label, width in (
            ("#0", "Pfad", 430), ("editable", "Eingabe", 80),
            ("flags", "Flags", 190), ("text", "Text", 280),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._select)
        pane.add(left, weight=3)
        self.details = tk.Text(pane, wrap="word", state="disabled", width=45)
        pane.add(self.details, weight=1)
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        self._nodes = {}
        self.refresh()

    def _set_details(self, value):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", value)
        self.details.configure(state="disabled")

    def _finish(self, cancel):
        cancel_edit(self.owner, "inspector") if cancel else commit_edit(self.owner, "inspector")
        self.refresh()
        self.owner.request_render()

    def _select(self, _event=None):
        selection = self.tree.selection()
        node = self._nodes.get(selection[0]) if selection else None
        if node is None:
            return
        self._set_details(format_state_node(node, getattr(self.owner, "_current_resolver", None)))

    def refresh(self):
        movie = getattr(self.owner, "_current_movie", None)
        self.tree.delete(*self.tree.get_children())
        self._nodes.clear()
        if movie is None:
            self.status_var.set("Kein UI-Film ausgewählt")
            return
        try:
            frame = int(self.owner.frame_var.get())
            nodes = inspect_movie_state(movie, frame)
        except Exception:
            nodes = ()
        wanted = self.search_var.get().casefold().strip()

        def walk(values):
            for node in values:
                item = node.metadata.get("edit_text")
                if item:
                    text = str(node.metadata.get("display_text", node.metadata.get("text", "")) or "")
                    haystack = f"{node.path}\n{text}\n{node.label}\n{item}".casefold()
                    if not wanted or wanted in haystack:
                        iid = f"edit_{len(self._nodes)}"
                        flags = ", ".join(value for value, active in (
                            ("multiline", item.get("multiline")),
                            ("password", item.get("password")),
                            ("selectable", item.get("selectable")),
                            ("active", item.get("active")),
                        ) if active)
                        self.tree.insert("", "end", iid=iid, text=node.path, values=(
                            "ja" if item.get("editable") else "nein", flags or "-",
                            model.display_text(text, item.get("password", False))[:160],
                        ))
                        self._nodes[iid] = node
                walk(node.children)
        walk(nodes)
        state = _state(movie)
        active = _active(movie)
        self.status_var.set(
            f"{len(self._nodes)} Textfelder | Aktiv: {active.path if active else '-'} | "
            f"Änderungen: {state['changes']} | Clipboard: {state['clipboard_reads']}/{state['clipboard_writes']}"
        )

    def export_json(self):
        movie = getattr(self.owner, "_current_movie", None)
        if movie is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="EditText-Diagnose speichern", defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            state = _state(movie)
            payload = {key: value for key, value in state.items() if key != "active"}
            active = _active(movie)
            payload["active"] = None if active is None else {
                "path": active.path, "length": len(active.text), "caret": active.caret,
                "selection": active.selection,
            }
            Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self):
        self.owner._edit_text_window = None
        self.destroy()


def show_edit_text_inspector(owner):
    window = getattr(owner, "_edit_text_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh()
            return window
    except Exception:
        pass
    owner._edit_text_window = EditTextInspector(owner)
    return owner._edit_text_window


def browser_init(owner, *args, **kwargs):
    owner._edit_text_window = None
    _BASE["browser_init"](owner, *args, **kwargs)
    owner.edit_text_input_enabled_var = tk.BooleanVar(value=True)
    owner.edit_text_status_var = tk.StringVar(value="Keine Texteingabe aktiv")
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Checkbutton(
        bar, text="EditText-Eingabe", variable=owner.edit_text_input_enabled_var,
        command=lambda: commit_edit(owner, "disabled") if not owner.edit_text_input_enabled_var.get() else None,
    ).pack(side="left")
    ttk.Button(bar, text="Textfelder…", command=lambda: show_edit_text_inspector(owner)).pack(side="left", padx=(8, 0))
    ttk.Label(
        bar, text="Klick = Caret · Shift = Auswahl · Ctrl+A/C/X/V/Z/Y · Esc = Abbrechen",
    ).pack(side="left", padx=(10, 0))
    ttk.Label(bar, textvariable=owner.edit_text_status_var).pack(side="right")
    owner.bind("<Control-e>", lambda _event: show_edit_text_inspector(owner))


def browser_render(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        active = _active(movie)
        variable = getattr(owner, "edit_text_status_var", None)
        if variable is not None:
            variable.set(
                f"Eingabe: {active.path} [{active.selection[0]}:{active.selection[1]}]"
                if active is not None else "Keine Texteingabe aktiv"
            )
    return _BASE["render"](owner)


def format_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    state = _state(movie)
    active = _active(movie)
    return text + "\n\nEditText-Eingabe:\n" + (
        f"- Aktiviert: {'ja' if _enabled(owner) else 'nein'}\n"
        f"- Aktives Feld: {active.path if active else '-'}\n"
        f"- Starts / Commits / Abbrüche: {state['starts']} / {state['commits']} / {state['cancels']}\n"
        f"- Änderungen / blockierte textInput-Events: {state['changes']} / {state['blocked']}\n"
        f"- Clipboard Reads / Writes: {state['clipboard_reads']} / {state['clipboard_writes']}"
    )


def browser_close(owner):
    commit_edit(owner, "close")
    window = getattr(owner, "_edit_text_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE["close"](owner)


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_edit_text_state = None
    return _BASE["reset"](owner)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        parse_edit_text=ui_browser._parse_edit_text,
        draw_edit_text=ui_browser.UIRenderer._draw_edit_text,
        focus=dynamic._set_focus,
        focus_cycle=dynamic._focus_cycle,
        mouse=button.mouse_event,
        motion=button.motion,
        key=button.key_event,
        activate=button.activate_focus,
        set=runtime._set_property,
        get=runtime._get_property,
        call=runtime._call,
        inspect=inspector.inspect_movie_state,
        format_node=inspector.format_state_node,
        browser_init=ui_browser.UIBrowser.__init__,
        render=ui_browser.UIBrowser._render,
        info=ui_browser.UIBrowser._format_info,
        close=ui_browser.UIBrowser.close,
        reset=runtime.reset_runtime,
    )
    ui_browser._parse_edit_text = parse_edit_text
    ui_browser.UIRenderer._draw_edit_text = draw_edit_text
    dynamic._set_focus = set_focus
    dynamic._focus_cycle = focus_cycle
    button.mouse_event = mouse_event
    button.motion = motion
    button.key_event = key_event
    button.activate_focus = activate_focus
    runtime._set_property = set_property
    runtime._get_property = get_property
    runtime._call = call_value
    inspector.inspect_movie_state = inspect_movie_state
    inspector.format_state_node = format_state_node
    ui_browser.inspect_movie_state = inspect_movie_state
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser._format_info = format_info
    ui_browser.UIBrowser.close = browser_close
    runtime.reset_runtime = reset_runtime
    lifecycle.reset_runtime = reset_runtime
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime

    ui_browser.EditTextSession = model.EditSession
    ui_browser.EditableTextTarget = model.EditableTarget
    ui_browser.begin_ui_text_edit = begin_edit
    ui_browser.commit_ui_text_edit = commit_edit
    ui_browser.cancel_ui_text_edit = cancel_edit
    ui_browser.show_ui_edit_text_inspector = show_edit_text_inspector
