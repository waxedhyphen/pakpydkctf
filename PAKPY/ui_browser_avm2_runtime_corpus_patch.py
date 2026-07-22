"""Corpus-aware safety follow-up for the bounded AVM2 UI runtime.

The general runtime deliberately starts small. The shipped Scaleform frame scripts also
use generic Controller.GetDataValue/SetDataValue calls, casts, super calls and a few
iteration opcodes. This patch handles those patterns without exposing arbitrary native
code or weakening the interpreter limits.
"""
from __future__ import annotations

import copy
import math
import re

import ui_browser
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_state_override_patch as overrides_patch
import ui_browser_timeline_core as timeline_core

try:
    import ui_browser_game_state_patch as game_state
except Exception:
    game_state = None


_INSTALLED = False
_BASE_SET = None
_BASE_GET = None
_BASE_ROLE = None
_BASE_NATIVE = None
_BASE_CALL = None
_BASE_EXECUTE = None
_BASE_METHOD = None
_METHOD_STACK = []


def _compact(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _safe_value(value, depth=0):
    if value is runtime._UNDEFINED or depth > 8:
        return runtime._UNDEFINED
    if value is None or isinstance(value, (
        bool, int, float, str, runtime.RuntimeRef, runtime.RuntimeMethod, runtime.RuntimeGlobal,
    )):
        return value
    if isinstance(value, (list, tuple)):
        result = []
        for item in value[:256]:
            clean = _safe_value(item, depth + 1)
            result.append(None if clean is runtime._UNDEFINED else clean)
        return result
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 256:
                break
            clean = _safe_value(item, depth + 1)
            result[str(key)] = None if clean is runtime._UNDEFINED else clean
        return result
    return runtime._UNDEFINED


def set_property(context, reference, name, value):
    if _BASE_SET(context, reference, name, value):
        return True
    if not isinstance(reference, runtime.RuntimeRef):
        return False
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if not short:
        return False
    value = _safe_value(value)
    if value is runtime._UNDEFINED:
        return False
    all_values = runtime._properties(context.movie)
    current = dict(all_values.get(reference.path, {}) or {})
    if current.get(short, runtime._UNDEFINED) == value:
        return True
    current[short] = value
    all_values[reference.path] = current
    context.writes += 1
    runtime._touch(context.movie)
    runtime._log(
        context.movie, "property", path=reference.path,
        property=short, value=repr(value),
    )
    return True


def get_property(context, receiver, name):
    result = _BASE_GET(context, receiver, name)
    if result is not runtime._UNDEFINED:
        return result
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if not isinstance(receiver, runtime.RuntimeRef):
        return result
    values = runtime._properties(context.movie).get(receiver.path, {}) or {}
    if short in values:
        return values[short]
    lower = short.lower()
    if lower == "parent" and receiver.path != "root":
        return runtime.RuntimeRef(receiver.path.rsplit("/", 1)[0])
    if lower in ("root", "stage"):
        owner = context.owner or getattr(context.movie, "_ui_avm2_runtime_owner", None)
        try:
            frame = int(owner.frame_var.get())
        except Exception:
            frame = 1
        return runtime.RuntimeRef("root", frame=max(1, frame), root=True)
    if lower == "name":
        return str(getattr(receiver.item, "name", "") or "")
    return result


def callback_role(name):
    role = _BASE_ROLE(name)
    if role is not None or game_state is None:
        return role
    wanted = _compact(name)
    best = None
    for field in getattr(game_state, "MOCK_FIELDS", ()):
        aliases = {_compact(field.key), _compact(field.label)}
        aliases.update(_compact(value) for value in tuple(field.aliases or ()))
        aliases |= {f"get{value}" for value in aliases}
        aliases |= {f"read{value}" for value in aliases}
        if wanted in aliases:
            return field.key
        if best is None and any(len(alias) >= 5 and alias in wanted for alias in aliases):
            best = field.key
    if best is not None:
        return best
    special = {
        "countpuzzle": "puzzle_pieces",
        "maxpuzzle": "puzzle_total",
        "countballoons": "lives",
        "charp2": "players",
        "levelmedalpuzzle": "puzzle_pieces",
        "levelmedalkong": "kong_letters",
        "bonuspuzzle": "puzzle_pieces",
    }
    if wanted in special:
        return special[wanted]
    if "kong" in wanted and any(value in wanted for value in ("kongk", "kongo", "kongn", "kongg")):
        return "kong_letters"
    return None


def _mock_value(movie, role, callback_name=""):
    active = set(getattr(movie, "ui_game_mock_roles", ()) or ())
    values = getattr(movie, "ui_game_mock_values", {}) or {}
    if (
        not bool(getattr(movie, "ui_game_mock_enabled", False))
        or role not in active or role not in values
    ):
        return runtime._UNDEFINED
    value = values[role]
    key = _compact(callback_name)
    if role == "players" and "charp2" in key:
        return int(value) >= 2
    if role == "kong_letters":
        letters = str(value or "").upper()
        for letter in "KONG":
            if f"kong{letter.lower()}" in key:
                return letter in letters
        if "medal" in key:
            return all(letter in letters for letter in "KONG")
    if role == "puzzle_pieces" and "medal" in key:
        total = int(values.get("puzzle_total", 0) or 0)
        return total > 0 and int(value) >= total
    return value


def _native_store(movie):
    value = getattr(movie, "ui_avm2_native_data", None)
    if not isinstance(value, dict):
        value = {}
        movie.ui_avm2_native_data = value
    return value


def native_call(context, name, args):
    key = _compact(name)
    if key not in (
        "getdatavalue", "getvalue", "readdatavalue",
        "setdatavalue", "setvalue", "writedatavalue",
    ):
        result = _BASE_NATIVE(context, name, args)
        if result is not runtime._UNDEFINED:
            return result
        role = callback_role(name)
        result = _mock_value(context.movie, role, name) if role else runtime._UNDEFINED
        if result is runtime._UNDEFINED:
            return result
        log = getattr(context.movie, "ui_avm2_runtime_log", None)
        if isinstance(log, list) and log:
            log[-1]["status"] = f"Game-Mock:{role}"
            log[-1]["result"] = repr(result)
        return result

    result = runtime._UNDEFINED
    status = "nicht registriert"
    if key in ("getdatavalue", "getvalue", "readdatavalue") and args:
        field_name = str(args[-1])
        store_name = str(args[-2]) if len(args) >= 2 else ""
        data = _native_store(context.movie)
        if (store_name, field_name) in data:
            result = data[(store_name, field_name)]
            status = "Runtime-Data"
        else:
            role = callback_role(field_name)
            result = _mock_value(context.movie, role, field_name) if role else runtime._UNDEFINED
            if result is not runtime._UNDEFINED:
                status = f"Game-Mock:{role}"
    elif key in ("setdatavalue", "setvalue", "writedatavalue") and len(args) >= 2:
        field_name = str(args[-2])
        store_name = str(args[-3]) if len(args) >= 3 else ""
        result = _safe_value(args[-1])
        _native_store(context.movie)[(store_name, field_name)] = result
        status = "Runtime-Data"

    context.callbacks += 1
    runtime._log(
        context.movie, "callback", name=str(name), status=status,
        result=repr(result), path=context.path,
    )
    return result


def _timeline_states(movie):
    value = getattr(movie, "ui_timeline_states", None)
    if not isinstance(value, dict):
        value = {}
        movie.ui_timeline_states = value
    return value


def _child_timeline_call(context, receiver, operation, args):
    if not isinstance(receiver, runtime.RuntimeRef) or receiver.path == context.path:
        return False
    if timeline_core.manual_frame_override(
        getattr(context.movie, "ui_state_overrides", {}) or {}, receiver.path,
    ) is not None:
        return True

    if receiver.root:
        count = max(1, int(getattr(context.movie, "frame_count", 1) or 1))
        labels = getattr(context.movie, "labels", {}) or {}
        owner = context.owner or getattr(context.movie, "_ui_avm2_runtime_owner", None)
        try:
            current = int(owner.frame_var.get())
        except Exception:
            current = 1
        playing = bool(getattr(owner, "_ui_playback_running", False))
    elif isinstance(receiver.definition, ui_browser.SpriteDef):
        count = max(1, int(receiver.definition.frame_count or 1))
        labels = getattr(receiver.definition, "labels", {}) or {}
        state = _timeline_states(context.movie).setdefault(
            receiver.path, timeline_core.normalize_timeline_instance({}, count),
        )
        current = int(state.get("frame", 1))
        playing = bool(state.get("playing", True))
        owner = None
    else:
        return False

    if operation == "stop" and not args:
        target = current
        playing = False
    elif operation == "play" and not args:
        target = current
        playing = True
    elif operation in ("gotoAndStop", "gotoAndPlay") and args:
        target = runtime.avm2.resolve_action_target(args[0], count, labels)
        if target is None:
            return True
        playing = operation == "gotoAndPlay"
    else:
        return False

    if receiver.root:
        if owner is not None:
            timeline_core.set_root_frame(owner, int(target))
            owner._ui_playback_running = playing
    else:
        state = _timeline_states(context.movie).setdefault(
            receiver.path, timeline_core.normalize_timeline_instance({}, count),
        )
        state.update(frame=int(target), playing=playing, frame_count=count)
        state.pop("_avm2_runtime_token", None)
    runtime._log(
        context.movie, "timeline", path=receiver.path,
        operation=operation, frame=int(target), playing=playing,
    )
    return True


def call_value(context, receiver, name, args):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if _child_timeline_call(context, receiver, short, args):
        return runtime._UNDEFINED
    if isinstance(receiver, runtime.RuntimeRef):
        method = context.trait_methods.get(short)
        if method is not None and _METHOD_STACK and int(method) == int(_METHOD_STACK[-1]):
            # A callsuper opcode looks like a same-class call to the base interpreter.
            # Suppress that self-recursion rather than pretending to run a superclass.
            return runtime._UNDEFINED
        compact_short = _compact(short)
        if args and compact_short in ("movieclip", "displayobject", "sprite", "object"):
            return args[0]
        if compact_short == "event":
            return {"class": short, "arguments": list(args)}
    if short in ("toString", "valueOf"):
        return str(receiver) if short == "toString" else receiver
    if isinstance(receiver, runtime.RuntimeGlobal):
        root = receiver.name.rsplit(".", 1)[-1]
        compact_root = _compact(root)
        compact_short = _compact(short)
        cast = compact_short if compact_short in (
            "movieclip", "displayobject", "sprite", "object",
            "string", "number", "int", "uint", "boolean",
        ) else compact_root
        if args and cast in ("movieclip", "displayobject", "sprite", "object"):
            return args[0]
        if args and cast == "string":
            return str(args[0])
        if args and cast == "number":
            return runtime._number(args[0])
        if args and cast == "int":
            return runtime._int(args[0])
        if args and cast == "uint":
            return runtime._int(args[0]) & 0xFFFFFFFF
        if args and cast == "boolean":
            return runtime._truth(args[0])
    return _BASE_CALL(context, receiver, name, args)


def _instruction(item, name, operands=None):
    clone = copy.copy(item)
    clone.name = name
    if operands is not None:
        clone.operands = tuple(operands)
    return clone


def execute_instructions(context, instructions, locals_=None):
    translated = []
    for item in tuple(instructions or ()):
        name = item.name.split(" ", 1)[0]
        if name == "astypelate":
            translated.append(_instruction(item, "pop", ()))
        elif name == "constructprop":
            translated.append(_instruction(item, "callproperty"))
        elif name == "hasnext2":
            translated.append(_instruction(item, "pushfalse", ()))
        elif name in ("inclocal", "inclocal_i", "declocal", "declocal_i"):
            # The only shipped hasnext2 loop exits immediately in the safe preview.
            # Keep local mutation conservative rather than entering unknown iteration.
            translated.append(_instruction(item, "nop", ()))
        else:
            translated.append(item)
    return _BASE_EXECUTE(context, tuple(translated), locals_)


def execute_method(context, method_index, arguments=(), receiver=None):
    _METHOD_STACK.append(int(method_index))
    try:
        return _BASE_METHOD(context, method_index, arguments, receiver)
    finally:
        _METHOD_STACK.pop()


def install():
    global _INSTALLED, _BASE_SET, _BASE_GET, _BASE_ROLE, _BASE_NATIVE
    global _BASE_CALL, _BASE_EXECUTE, _BASE_METHOD
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_SET = runtime._set_property
    _BASE_GET = runtime._get_property
    _BASE_ROLE = runtime._callback_role
    _BASE_NATIVE = runtime._native
    _BASE_CALL = runtime._call
    _BASE_EXECUTE = runtime.execute_instructions
    _BASE_METHOD = runtime.execute_method

    runtime._set_property = set_property
    runtime._get_property = get_property
    runtime._callback_role = callback_role
    runtime._native = native_call
    runtime._call = call_value
    runtime.execute_instructions = execute_instructions
    runtime.execute_method = execute_method

    ui_browser.execute_avm2_runtime_instructions = execute_instructions
    ui_browser.AVM2_RUNTIME_CORPUS_TUNING = True
