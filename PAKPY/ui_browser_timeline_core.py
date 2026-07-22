"""Core state model for running nested Scaleform timelines in the UI Browser."""
from __future__ import annotations

import ui_browser
import ui_browser_scale9_blend_patch as scale9_patch
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as override_patch


_INSTALLED = False
_ORIGINAL_INSPECT_WITH_OVERRIDES = None
_ORIGINAL_MAKE_PRESET = None
_ORIGINAL_NORMALIZE_PRESET = None


def normalize_timeline_instance(value, frame_count=1):
    count = max(1, int(frame_count or 1))
    value = value if isinstance(value, dict) else {}
    try:
        frame = int(value.get("frame", 1))
    except Exception:
        frame = 1
    return {
        "frame": max(1, min(count, frame)),
        "playing": bool(value.get("playing", True)),
        "frame_count": count,
    }


def normalize_playback_preset(value):
    value = value if isinstance(value, dict) else {}
    try:
        speed = float(value.get("speed", 1.0))
    except Exception:
        speed = 1.0
    speed = max(0.05, min(8.0, speed))
    instances = {}
    raw_instances = value.get("instances", {})
    if isinstance(raw_instances, dict):
        for path, raw in raw_instances.items():
            if not isinstance(raw, dict):
                continue
            try:
                frame = max(1, int(raw.get("frame", 1)))
            except Exception:
                frame = 1
            instances[str(path)] = {
                "frame": frame,
                "playing": bool(raw.get("playing", True)),
            }
    return {
        "speed": speed,
        "playing": bool(value.get("playing", False)),
        "instances": instances,
    }


def advance_timeline_instance(state, steps=1, force=False):
    count = max(1, int(state.get("frame_count", 1) or 1))
    frame = max(1, min(count, int(state.get("frame", 1) or 1)))
    if (force or state.get("playing", True)) and count > 1:
        frame = ((frame - 1 + int(steps)) % count) + 1
    state["frame"] = frame
    state["frame_count"] = count
    return frame


def manual_frame_override(overrides, path):
    override = override_patch.normalize_override((overrides or {}).get(path, {}))
    return override.get("sprite_frame")


def timeline_frame_for_path(definition, path, overrides):
    manual = manual_frame_override(overrides, path)
    count = max(1, int(getattr(definition, "frame_count", 1) or 1))
    if manual is not None:
        return max(1, min(count, int(manual)))
    movie = getattr(definition, "_ui_timeline_movie", None)
    states = getattr(movie, "ui_timeline_states", {}) if movie is not None else {}
    state = states.get(path)
    if state is None:
        return 1
    clean = normalize_timeline_instance(state, count)
    state.update(clean)
    return clean["frame"]


def register_movie(movie, states=None):
    if movie is None:
        return
    if states is None:
        states = getattr(movie, "ui_timeline_states", {})
    movie.ui_timeline_states = states
    for definition in getattr(movie, "definitions", {}).values():
        if isinstance(definition, ui_browser.SpriteDef):
            definition._ui_timeline_movie = movie


def walk_nodes(nodes):
    for node in tuple(nodes or ()):
        yield node
        yield from walk_nodes(node.children)


def sync_timeline_instances(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return ()
    states = getattr(owner, "_ui_timeline_states", {})
    register_movie(movie, states)
    frame_var = getattr(owner, "frame_var", None)
    root_frame = int(frame_var.get()) if frame_var is not None else 1
    try:
        nodes = inspector.inspect_movie_state(movie, root_frame)
    except Exception:
        return ()
    active = []
    for node in walk_nodes(nodes):
        if node.kind != "MovieClip":
            continue
        count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
        state = states.get(node.path)
        if state is None:
            state = normalize_timeline_instance(
                {"frame": node.metadata.get("sprite_frame", 1)}, count,
            )
            states[node.path] = state
        else:
            state.update(normalize_timeline_instance(state, count))
        active.append(node.path)
    movie.ui_timeline_states = states
    return tuple(active)


def movie_key(owner):
    helper = getattr(override_patch, "_browser_movie_key", None)
    return helper(owner) if callable(helper) else ""


def attach_timeline_state(owner):
    key = movie_key(owner)
    owner._ui_current_timeline_key = key
    states = owner._ui_timeline_states_by_movie.setdefault(key, {}) if key else {}
    owner._ui_timeline_states = states
    register_movie(getattr(owner, "_current_movie", None), states)
    sync_timeline_instances(owner)


def clear_scale9_cache():
    try:
        scale9_patch._SCALE9_CACHE.clear()
    except Exception:
        pass


def request_timeline_render(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_timeline_states = getattr(owner, "_ui_timeline_states", {})
        movie.ui_timeline_revision = int(getattr(movie, "ui_timeline_revision", 0)) + 1
    clear_scale9_cache()
    owner.request_render()


def set_root_frame(owner, frame):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    frame = max(1, min(int(movie.frame_count), int(frame)))
    owner.frame_var.set(frame)
    owner.frame_scale.set(frame)
    owner._update_frame_text()


def _decorate_nodes(movie, nodes, overrides):
    states = getattr(movie, "ui_timeline_states", {})
    result = []
    for node in nodes:
        metadata = dict(node.metadata)
        children = _decorate_nodes(movie, node.children, overrides)
        if node.kind == "MovieClip":
            state = states.get(node.path)
            manual = manual_frame_override(overrides, node.path)
            metadata["timeline_playing"] = bool(state.get("playing", True)) if state else True
            metadata["timeline_manual_frame"] = manual is not None
            metadata["timeline_frame"] = int(metadata.get("sprite_frame", 1))
        result.append(inspector.StateNode(
            node.path, node.depth, node.label, node.kind, node.visible,
            node.character_id, node.class_name, metadata, children,
        ))
    return tuple(result)


def inspect_movie_state_with_playback(movie, frame, overrides=None, max_depth=64):
    register_movie(movie, getattr(movie, "ui_timeline_states", {}))
    nodes = _ORIGINAL_INSPECT_WITH_OVERRIDES(movie, frame, overrides, max_depth)
    effective = override_patch.normalize_overrides(
        getattr(movie, "ui_state_overrides", {}) if overrides is None else overrides,
    )
    return _decorate_nodes(movie, nodes, effective)


def make_preset_with_playback(owner):
    result = _ORIGINAL_MAKE_PRESET(owner)
    states = {}
    for path, raw in getattr(owner, "_ui_timeline_states", {}).items():
        clean = normalize_timeline_instance(raw, raw.get("frame_count", 1))
        states[str(path)] = {"frame": clean["frame"], "playing": clean["playing"]}
    result["playback"] = {
        "speed": float(getattr(owner, "_ui_playback_speed", 1.0)),
        "playing": bool(getattr(owner, "_ui_playback_running", False)),
        "instances": states,
    }
    return result


def normalize_preset_with_playback(data):
    result = _ORIGINAL_NORMALIZE_PRESET(data)
    result["playback"] = normalize_playback_preset(
        data.get("playback", {}) if isinstance(data, dict) else {},
    )
    return result


def install():
    global _INSTALLED, _ORIGINAL_INSPECT_WITH_OVERRIDES
    global _ORIGINAL_MAKE_PRESET, _ORIGINAL_NORMALIZE_PRESET
    if _INSTALLED:
        return
    _INSTALLED = True
    _ORIGINAL_INSPECT_WITH_OVERRIDES = override_patch.inspect_movie_state_with_overrides
    _ORIGINAL_MAKE_PRESET = override_patch.make_preset
    _ORIGINAL_NORMALIZE_PRESET = override_patch.normalize_preset

    override_patch.sprite_frame_for_path = timeline_frame_for_path
    override_patch.inspect_movie_state_with_overrides = inspect_movie_state_with_playback
    override_patch.make_preset = make_preset_with_playback
    override_patch.normalize_preset = normalize_preset_with_playback

    def inspect_movie_state(movie, frame, max_depth=64):
        return inspect_movie_state_with_playback(movie, frame, None, max_depth)

    inspector.inspect_movie_state = inspect_movie_state
    ui_browser.inspect_movie_state = inspect_movie_state

    original_format_node = inspector.format_state_node

    def format_state_node(node, resolver=None):
        text = original_format_node(node, resolver)
        if node.kind != "MovieClip":
            return text
        meta = node.metadata
        lines = ["", "Timeline-Vorschau:"]
        lines.append(f"- Frame: {meta.get('timeline_frame', meta.get('sprite_frame', 1))}")
        if meta.get("timeline_manual_frame"):
            lines.append("- Quelle: manueller Frame-Override")
        else:
            lines.append(f"- Wiedergabe: {'läuft' if meta.get('timeline_playing', True) else 'pausiert'}")
        return text + "\n" + "\n".join(lines)

    inspector.format_state_node = format_state_node
    ui_browser.normalize_ui_timeline_instance = normalize_timeline_instance
    ui_browser.advance_ui_timeline_instance = advance_timeline_instance
    ui_browser.normalize_ui_playback_preset = normalize_playback_preset
    ui_browser.make_ui_state_preset = make_preset_with_playback
    ui_browser.normalize_ui_state_preset = normalize_preset_with_playback
