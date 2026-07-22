"""Follow-up fixes for EditText path resolution during render and inspection."""
from __future__ import annotations

import copy

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_edit_text_model as model
import ui_browser_edit_text_patch as edit
import ui_browser_state_inspector_patch as inspector


_INSTALLED = False


def target(owner, path, require_editable=True, node=None, definition=None):
    movie = getattr(owner, "_current_movie", None)
    path = str(path or "")
    if movie is None or not path:
        return None
    obj = edit._dynamic_object(movie, path)
    if definition is None:
        if obj is not None:
            definition = getattr(obj, "definition", None)
        elif node is not None:
            character_id = getattr(node, "character_id", None)
            definition = movie.definitions.get(character_id) if character_id is not None else None
        else:
            node = edit._node(owner, path)
            character_id = getattr(node, "character_id", None) if node is not None else None
            definition = movie.definitions.get(character_id) if character_id is not None else None
    if obj is None and not isinstance(definition, ui_browser.EditTextDef):
        return None
    if obj is not None and obj.kind != "TextField" and not isinstance(definition, ui_browser.EditTextDef):
        return None
    if edit._manual_text(movie, path):
        return None

    values = runtime._properties(movie).get(path, {}) or {}
    extras = obj.extras if obj is not None else {}
    field_type = str(extras.get(
        "type", values.get("type", edit._default_input_type(definition)),
    ) or "dynamic").lower()
    selectable_default = not bool(getattr(definition, "no_select", False))
    selectable = bool(extras.get("selectable", values.get("selectable", selectable_default)))
    editable = field_type == "input" and selectable
    if require_editable and not editable:
        return None

    if node is None and obj is None:
        node = edit._node(owner, path)
    metadata = dict(getattr(node, "metadata", {}) or {}) if node is not None else {}
    if obj is not None:
        text = str(obj.html_text or obj.text or "")
        variable_name = str(obj.name or getattr(definition, "variable_name", "") or "")
    else:
        text = values.get("htmlText", values.get("text", None))
        if text is None:
            # Use the real text value, not State Inspector's visual placeholder.
            text = metadata.get("text", getattr(definition, "initial_text", ""))
        text = str(text or "")
        variable_name = str(getattr(definition, "variable_name", "") or metadata.get("variable_name", ""))

    max_chars = extras.get("maxChars", values.get("maxChars", getattr(definition, "max_length", 0)))
    try:
        max_chars = max(0, min(model.MAX_TEXT_CHARS, int(max_chars or 0)))
    except Exception:
        max_chars = 0
    restrict = str(extras.get("restrict", values.get("restrict", "")) or "")[:model.MAX_RESTRICT_PATTERN]
    multiline = bool(extras.get(
        "multiline", values.get("multiline", getattr(definition, "multiline", False)),
    ))
    password = bool(extras.get(
        "displayAsPassword", values.get("displayAsPassword", getattr(definition, "password", False)),
    ))
    return model.EditableTarget(
        path=path, text=text, multiline=multiline, selectable=selectable,
        max_chars=max_chars, restrict=restrict, password=password,
        dynamic=obj is not None, variable_name=variable_name,
    )


def decorate_nodes(owner, movie, nodes):
    session = edit._active(movie)
    result = []
    for node in tuple(nodes or ()):
        metadata = dict(node.metadata)
        children = decorate_nodes(owner, movie, node.children)
        definition = movie.definitions.get(node.character_id) if node.character_id is not None else None
        item = target(owner, node.path, False, node=node, definition=definition) \
            if node.kind in ("EditText", "DynamicTextField") else None
        if item is not None:
            metadata["edit_text"] = {
                "editable": target(owner, node.path, True, node=node, definition=definition) is not None,
                "selectable": item.selectable,
                "multiline": item.multiline,
                "max_chars": item.max_chars,
                "restrict": item.restrict,
                "password": item.password,
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


def draw_edit_text(renderer, canvas, definition, matrix, color):
    path = str(getattr(renderer, "_ui_current_path", "") or "")
    movie = renderer.movie
    owner = getattr(movie, "_ui_avm2_runtime_owner", None)
    session = edit._active(movie)
    item = target(owner, path, False, definition=definition) if owner is not None and path else None
    rendered = definition
    if item is not None and (item.password or (session is not None and session.path == path)):
        rendered = copy.copy(definition)
        raw = session.text if session is not None and session.path == path else item.text
        rendered.initial_text = model.display_text(raw, item.password)
        if hasattr(rendered, "html"):
            rendered.html = False
    result = edit._BASE["draw_edit_text"](renderer, canvas, rendered, matrix, color)
    if session is not None and session.path == path and item is not None:
        edit._overlay(renderer, canvas, rendered, matrix, session, item)
        renderer.stats.editable_text_active = getattr(renderer.stats, "editable_text_active", 0) + 1
    return result


def _text_receiver(context, receiver):
    owner = getattr(context.movie, "_ui_avm2_runtime_owner", None)
    path = edit._receiver_path(receiver)
    return target(owner, path, False) if owner is not None and path else None


def set_property(context, reference, name, value):
    short = edit._short(name)
    if short in edit._TEXT_PROPERTIES and _text_receiver(context, reference) is None:
        return edit._BASE["set"](context, reference, name, value)
    return edit.set_property(context, reference, name, value)


def get_property(context, receiver, name):
    short = edit._short(name)
    if short in edit._TEXT_PROPERTIES | {"selectedText"} and _text_receiver(context, receiver) is None:
        return edit._BASE["get"](context, receiver, name)
    return edit.get_property(context, receiver, name)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    edit._target = target
    edit._decorate_nodes = decorate_nodes
    edit.draw_edit_text = draw_edit_text
    ui_browser.UIRenderer._draw_edit_text = draw_edit_text
    runtime._set_property = set_property
    runtime._get_property = get_property
