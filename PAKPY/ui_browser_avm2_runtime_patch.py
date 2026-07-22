"""Bounded AVM2 frame-script runtime for existing UI display objects.

This follow-up executes a controlled subset of already parsed frame-script methods:
locals, operand stack, simple branches, same-class helper calls, timeline calls,
DisplayObject visibility/alpha and EditText text/htmlText. Native calls are restricted to
an explicit registry plus read-only Game-State-Mock values. Manual Inspector overrides
always retain precedence. No arbitrary host API is exposed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import math
import re
import tkinter as tk
from tkinter import ttk

import ui_browser
import ui_browser_avm2_patch as avm2
import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as overrides_patch
import ui_browser_timeline_core as timeline_core

try:
    import ui_browser_game_state_patch as game_state
except Exception:
    game_state = None
try:
    import ui_browser_performance_patch as performance
except Exception:
    performance = None


_INSTALLED = False
_UNDEFINED = object()
_MAX_STEPS = 8192
_MAX_DEPTH = 16
_MAX_LOG = 1000

_BASE_APPLY_ITEM = None
_BASE_TEXT_DEF = None
_BASE_INSPECT = None
_BASE_FORMAT_NODE = None
_BASE_INIT = None
_BASE_SELECT = None
_BASE_RENDER = None
_BASE_INFO = None
_BASE_CLOSE = None
_STATIC_NESTED = None
_STATIC_ROOT = None
_BASE_CACHE_KEY = None


@dataclass
class RuntimeRef:
    path: str
    item: object | None = None
    definition: object | None = None
    frame: int = 1
    root: bool = False


@dataclass(frozen=True)
class RuntimeGlobal:
    name: str


@dataclass(frozen=True)
class RuntimeMethod:
    index: int
    receiver: object | None = None


@dataclass
class RuntimeContext:
    movie: object
    abc: object
    class_name: str
    path: str
    definition: object | None
    frame: int
    playing: bool
    frame_count: int
    labels: dict
    owner: object | None = None
    trait_methods: dict = field(default_factory=dict)
    slot_names: dict = field(default_factory=dict)
    arguments: tuple = ()
    depth: int = 0
    steps: int = 0
    jumped: bool = False
    writes: int = 0
    callbacks: int = 0
    return_value: object = _UNDEFINED

    def this_ref(self):
        return RuntimeRef(self.path, definition=self.definition, frame=self.frame, root=self.path == "root")


SAFE_CALLBACKS = {}


def _compact(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def register_native_callback(name, callback, aliases=()):
    if not callable(callback):
        raise TypeError("callback must be callable")
    for value in (name, *tuple(aliases or ())):
        key = _compact(value)
        if key:
            SAFE_CALLBACKS[key] = callback
    return callback


def unregister_native_callback(name):
    SAFE_CALLBACKS.pop(_compact(name), None)


def _enabled(movie):
    return bool(getattr(movie, "ui_avm2_runtime_enabled", True))


def _properties(movie):
    value = getattr(movie, "ui_avm2_runtime_properties", None)
    if not isinstance(value, dict):
        value = {}
        movie.ui_avm2_runtime_properties = value
    return value


def _log(movie, kind, **data):
    values = getattr(movie, "ui_avm2_runtime_log", None)
    if not isinstance(values, list):
        values = []
        movie.ui_avm2_runtime_log = values
    values.append({"kind": kind, **data})
    if len(values) > _MAX_LOG:
        del values[:len(values) - _MAX_LOG]


def _error(movie, path, method, message):
    values = getattr(movie, "ui_avm2_runtime_errors", None)
    if not isinstance(values, list):
        values = []
        movie.ui_avm2_runtime_errors = values
    item = {"path": str(path), "method": str(method), "message": str(message)}
    if not values or values[-1] != item:
        values.append(item)
    if len(values) > 500:
        del values[:len(values) - 500]


def _touch(movie):
    movie.ui_avm2_runtime_revision = int(getattr(movie, "ui_avm2_runtime_revision", 0)) + 1


def _manual(movie, path):
    raw = (getattr(movie, "ui_state_overrides", {}) or {}).get(path, {})
    return overrides_patch.normalize_override(raw)


def _set_property(context, reference, name, value):
    if not isinstance(reference, RuntimeRef):
        return False
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    key = {"htmltext": "htmlText", "visible": "visible", "alpha": "alpha", "text": "text"}.get(short.lower())
    if key is None:
        return False
    if key == "visible":
        value = bool(value)
    elif key == "alpha":
        try:
            value = max(0.0, min(1.0, float(value)))
        except Exception:
            value = 1.0
    else:
        value = "" if value is None or value is _UNDEFINED else str(value)
    all_values = _properties(context.movie)
    current = dict(all_values.get(reference.path, {}) or {})
    if current.get(key, _UNDEFINED) == value:
        return True
    current[key] = value
    all_values[reference.path] = current
    context.writes += 1
    _touch(context.movie)
    _log(context.movie, "property", path=reference.path, property=key, value=value)
    return True


def apply_item_override(movie, parent_path, depth, item, overrides):
    result, path, manual = _BASE_APPLY_ITEM(movie, parent_path, depth, item, overrides)
    runtime = dict(_properties(movie).get(path, {}) or {}) if _enabled(movie) else {}
    if not runtime:
        return result, path, manual
    clone = copy.copy(result)
    if "visible" in runtime and "visible" not in manual:
        clone.visible = bool(runtime["visible"])
    if "alpha" in runtime:
        color = getattr(clone, "color", ui_browser.IDENTITY_COLOR)
        clone.color = ui_browser.ColorTransform(
            color.r_mult, color.g_mult, color.b_mult, float(runtime["alpha"]),
            color.r_add, color.g_add, color.b_add, 0,
        )
    clone._ui_avm2_runtime = runtime
    clone._ui_state_path = path
    return clone, path, manual


def text_definition_for_path(definition, path, overrides):
    result = _BASE_TEXT_DEF(definition, path, overrides)
    movie = getattr(definition, "_ui_game_state_movie", None)
    if movie is None or not _enabled(movie):
        return result
    if "text" in overrides_patch.normalize_override((overrides or {}).get(path, {})):
        return result
    runtime = dict(_properties(movie).get(path, {}) or {})
    if "htmlText" not in runtime and "text" not in runtime:
        return result
    clone = copy.copy(result)
    if "htmlText" in runtime:
        clone.initial_text = str(runtime["htmlText"])
        if hasattr(clone, "html"):
            clone.html = True
    else:
        clone.initial_text = str(runtime["text"])
        if hasattr(clone, "html"):
            clone.html = False
    clone._ui_avm2_runtime = runtime
    return clone


def _builder():
    return overrides_patch._ORIGINAL_BUILD_DISPLAY_LIST or ui_browser.build_display_list


def _sprite_frame(movie, path, definition):
    manual = timeline_core.manual_frame_override(getattr(movie, "ui_state_overrides", {}) or {}, path)
    count = max(1, int(getattr(definition, "frame_count", 1) or 1))
    if manual is not None:
        return max(1, min(count, int(manual)))
    state = (getattr(movie, "ui_timeline_states", {}) or {}).get(path, {})
    try:
        return max(1, min(count, int(state.get("frame", 1))))
    except Exception:
        return 1


def _display_for(context, reference):
    if reference.root:
        return _builder()(context.movie.root_tags, max(1, int(reference.frame)))
    if isinstance(reference.definition, ui_browser.SpriteDef):
        return _builder()(reference.definition.tags, _sprite_frame(context.movie, reference.path, reference.definition))
    return {}


def _names(movie, item, definition):
    result = []
    for value in (
        getattr(item, "name", ""), inspector._node_label(movie, item, definition),
        getattr(item, "class_name", ""),
        getattr(movie, "symbol_classes", {}).get(getattr(item, "character_id", None), ""),
        getattr(definition, "variable_name", ""),
    ):
        text = str(value or "")
        if text:
            result.extend((text, text.rsplit("::", 1)[-1].rsplit(".", 1)[-1]))
    return tuple(dict.fromkeys(result))


def _child(context, reference, name):
    if not isinstance(reference, RuntimeRef):
        return None
    wanted = str(name or "")
    for depth, item in sorted(_display_for(context, reference).items()):
        definition = context.movie.definitions.get(getattr(item, "character_id", None))
        names = _names(context.movie, item, definition)
        if wanted not in names and wanted.lower() not in {value.lower() for value in names}:
            continue
        path = overrides_patch.state_item_path(context.movie, reference.path, depth, item)
        frame = _sprite_frame(context.movie, path, definition) if isinstance(definition, ui_browser.SpriteDef) else 1
        return RuntimeRef(path, item, definition, frame)
    return None


def _get_property(context, receiver, name):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if isinstance(receiver, RuntimeRef):
        runtime = _properties(context.movie).get(receiver.path, {}) or {}
        manual = _manual(context.movie, receiver.path)
        lower = short.lower()
        if lower == "visible":
            if "visible" in manual:
                return bool(manual["visible"])
            return bool(runtime.get("visible", getattr(receiver.item, "visible", True)))
        if lower == "alpha":
            return float(runtime.get("alpha", getattr(getattr(receiver.item, "color", None), "a_mult", 1.0)))
        if lower in ("text", "htmltext"):
            if "text" in manual:
                return manual["text"]
            if lower == "htmltext" and "htmlText" in runtime:
                return runtime["htmlText"]
            if "text" in runtime:
                return runtime["text"]
            return str(getattr(receiver.definition, "initial_text", "") or "")
        if lower == "currentframe":
            return int(receiver.frame)
        if lower == "totalframes":
            return int(getattr(receiver.definition, "frame_count", getattr(context.movie, "frame_count", 1)) or 1)
        found = _child(context, receiver, short)
        if found is not None:
            return found
        method = context.trait_methods.get(short)
        if method is not None and receiver.path == context.path:
            return RuntimeMethod(int(method), receiver)
        return _UNDEFINED
    if isinstance(receiver, RuntimeGlobal):
        return RuntimeGlobal(f"{receiver.name}.{short}")
    if isinstance(receiver, dict):
        return receiver.get(short, _UNDEFINED)
    if isinstance(receiver, (list, tuple)) and short == "length":
        return len(receiver)
    return _UNDEFINED


def _truth(value):
    return False if value is _UNDEFINED or value is None or (isinstance(value, float) and math.isnan(value)) else bool(value)


def _number(value):
    if value is _UNDEFINED or value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        return float(value)
    except Exception:
        return float("nan")


def _int(value):
    try:
        value = int(_number(value)) & 0xFFFFFFFF
    except Exception:
        value = 0
    return value - 0x100000000 if value & 0x80000000 else value


def _callback_role(name):
    if game_state is None:
        return None
    wanted = _compact(name)
    for field in getattr(game_state, "MOCK_FIELDS", ()):
        values = [field.key, field.label, *tuple(field.aliases or ())]
        aliases = {_compact(value) for value in values}
        aliases |= {f"get{value}" for value in aliases} | {f"read{value}" for value in aliases}
        if wanted in aliases:
            return field.key
    return None


def _native(context, name, args):
    key = _compact(name)
    callback = SAFE_CALLBACKS.get(key)
    result = _UNDEFINED
    status = "nicht registriert"
    if callback is not None:
        try:
            result = callback(context, tuple(args))
            status = "Registry"
        except Exception as exc:
            _error(context.movie, context.path, name, exc)
            status = "Fehler"
    else:
        role = _callback_role(name)
        active = set(getattr(context.movie, "ui_game_mock_roles", ()) or ())
        values = getattr(context.movie, "ui_game_mock_values", {}) or {}
        if bool(getattr(context.movie, "ui_game_mock_enabled", False)) and role in active and role in values:
            result = values[role]
            status = f"Game-Mock:{role}"
    context.callbacks += 1
    _log(context.movie, "callback", name=str(name), status=status, result=repr(result), path=context.path)
    return result


def _call(context, receiver, name, args):
    short = str(name or "").rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if isinstance(receiver, RuntimeRef):
        if short == "stop" and not args:
            context.playing = False
            return _UNDEFINED
        if short == "play" and not args:
            context.playing = True
            return _UNDEFINED
        if short in ("gotoAndStop", "gotoAndPlay") and args:
            target = avm2.resolve_action_target(args[0], context.frame_count, context.labels)
            if target is not None:
                context.frame = int(target)
                context.playing = short == "gotoAndPlay"
                context.jumped = True
            return _UNDEFINED
        method = context.trait_methods.get(short)
        if method is not None and receiver.path == context.path:
            return execute_method(context, int(method), args, receiver)
    if isinstance(receiver, RuntimeMethod):
        return execute_method(context, receiver.index, args, receiver.receiver)
    if isinstance(receiver, RuntimeGlobal):
        root = receiver.name.rsplit(".", 1)[-1]
        if short == "call" and _compact(root) in ("externalinterface", "externalinterfaceas3"):
            return _native(context, args[0], args[1:]) if args else _UNDEFINED
        return _native(context, short, args)
    return _UNDEFINED


def _binary(name, left, right):
    if name in ("add", "add_i"):
        if isinstance(left, str) or isinstance(right, str):
            return str(left) + str(right)
        value = _number(left) + _number(right)
        return _int(value) if name.endswith("_i") else value
    if name in ("subtract", "subtract_i"):
        value = _number(left) - _number(right)
        return _int(value) if name.endswith("_i") else value
    if name in ("multiply", "multiply_i"):
        value = _number(left) * _number(right)
        return _int(value) if name.endswith("_i") else value
    if name == "divide":
        try:
            return _number(left) / _number(right)
        except Exception:
            return float("nan")
    if name == "modulo":
        try:
            return _number(left) % _number(right)
        except Exception:
            return float("nan")
    if name == "equals":
        return left == right
    if name == "strictequals":
        return type(left) is type(right) and left == right
    if name == "lessthan":
        return left < right
    if name == "lessequals":
        return left <= right
    if name == "greaterthan":
        return left > right
    if name == "greaterequals":
        return left >= right
    return _UNDEFINED


def _branch(name, pop):
    if name in ("iftrue", "iffalse"):
        value = _truth(pop())
        return value if name == "iftrue" else not value
    right, left = pop(), pop()
    if name in ("ifeq", "ifne"):
        value = left == right
        return value if name == "ifeq" else not value
    if name in ("ifstricteq", "ifstrictne"):
        value = type(left) is type(right) and left == right
        return value if name == "ifstricteq" else not value
    try:
        values = {
            "iflt": left < right, "ifle": left <= right, "ifgt": left > right, "ifge": left >= right,
            "ifnlt": not (left < right), "ifnle": not (left <= right),
            "ifngt": not (left > right), "ifnge": not (left >= right),
        }
        return bool(values[name])
    except Exception:
        return False


def execute_instructions(context, instructions, locals_=None):
    instructions = tuple(instructions or ())
    by_offset = {item.offset: index for index, item in enumerate(instructions)}
    stack, scopes = [], []
    locals_ = list(locals_ or [context.this_ref(), *context.arguments])

    def pop(default=_UNDEFINED):
        return stack.pop() if stack else default

    def local(index):
        while len(locals_) <= index:
            locals_.append(_UNDEFINED)
        return locals_[index]

    pc = 0
    while 0 <= pc < len(instructions):
        item = instructions[pc]
        name = item.name.split(" ", 1)[0]
        context.steps += 1
        if context.steps > _MAX_STEPS:
            _error(context.movie, context.path, context.class_name, "Schrittlimit erreicht")
            break
        next_pc = pc + 1
        try:
            if name in ("nop", "label", "debug", "debugline", "debugfile", "bkpt", "bkptline"):
                pass
            elif name == "getlocal_0":
                stack.append(local(0))
            elif name in ("getlocal_1", "getlocal_2", "getlocal_3"):
                stack.append(local(int(name[-1])))
            elif name == "getlocal":
                stack.append(local(int(item.operands[0])))
            elif name in ("setlocal_0", "setlocal_1", "setlocal_2", "setlocal_3"):
                index = int(name[-1])
                local(index)
                locals_[index] = pop()
            elif name == "setlocal":
                index = int(item.operands[0])
                local(index)
                locals_[index] = pop()
            elif name == "kill":
                index = int(item.operands[0])
                local(index)
                locals_[index] = _UNDEFINED
            elif name in ("pushbyte", "pushshort", "pushint", "pushuint", "pushdouble", "pushstring", "pushtrue", "pushfalse", "pushnull"):
                stack.append(avm2._literal_from_instruction(context.abc, item))
            elif name == "pushundefined":
                stack.append(_UNDEFINED)
            elif name == "pushnan":
                stack.append(float("nan"))
            elif name == "pop":
                pop()
            elif name == "dup":
                stack.append(stack[-1] if stack else _UNDEFINED)
            elif name == "swap" and len(stack) >= 2:
                stack[-1], stack[-2] = stack[-2], stack[-1]
            elif name in ("pushscope", "pushwith"):
                scopes.append(pop())
            elif name == "popscope" and scopes:
                scopes.pop()
            elif name == "getscopeobject":
                index = int(item.operands[0])
                stack.append(scopes[index] if index < len(scopes) else _UNDEFINED)
            elif name in ("getglobalscope", "getouterscope"):
                stack.append(RuntimeGlobal("global"))
            elif name in ("findproperty", "findpropstrict", "finddef", "findpropglobal", "findpropglobalstrict"):
                stack.append(context.this_ref())
            elif name == "getlex":
                stack.append(RuntimeGlobal(context.abc.multiname_name(item.operands[0])))
            elif name in ("getproperty", "getsuper"):
                stack.append(_get_property(context, pop(), context.abc.multiname_name(item.operands[0])))
            elif name in ("setproperty", "initproperty", "setsuper"):
                value, receiver = pop(), pop()
                _set_property(context, receiver, context.abc.multiname_name(item.operands[0]), value)
            elif name == "newfunction":
                stack.append(RuntimeMethod(int(item.operands[0]), context.this_ref()))
            elif name in ("callproperty", "callproplex", "callpropvoid", "callsuper", "callsupervoid"):
                argc = int(item.operands[1])
                args = [pop() for _ in range(argc)][::-1]
                receiver = pop()
                result = _call(context, receiver, context.abc.multiname_name(item.operands[0]), args)
                if name in ("callproperty", "callproplex", "callsuper"):
                    stack.append(result)
            elif name == "callstatic":
                method, argc = map(int, item.operands)
                args = [pop() for _ in range(argc)][::-1]
                pop()
                stack.append(execute_method(context, method, args))
            elif name == "call":
                argc = int(item.operands[0])
                args = [pop() for _ in range(argc)][::-1]
                receiver, function = pop(), pop()
                stack.append(execute_method(context, function.index, args, function.receiver or receiver) if isinstance(function, RuntimeMethod) else _UNDEFINED)
            elif name in ("construct", "constructsuper"):
                argc = int(item.operands[0])
                [pop() for _ in range(argc)]
                pop()
                if name == "construct":
                    stack.append({})
            elif name == "newarray":
                count = int(item.operands[0])
                stack.append([pop() for _ in range(count)][::-1])
            elif name == "newobject":
                count = int(item.operands[0])
                result = {}
                for _ in range(count):
                    value, key = pop(), pop()
                    result[str(key)] = value
                stack.append(result)
            elif name in ("newactivation", "newcatch", "newclass"):
                stack.append({})
            elif name in ("convert_s", "coerce_s"):
                stack.append(str(pop()))
            elif name in ("convert_i", "coerce_i"):
                stack.append(_int(pop()))
            elif name in ("convert_u", "coerce_u"):
                stack.append(_int(pop()) & 0xFFFFFFFF)
            elif name in ("convert_d", "coerce_d"):
                stack.append(_number(pop()))
            elif name in ("convert_b", "coerce_b"):
                stack.append(_truth(pop()))
            elif name in ("convert_o", "coerce_o", "coerce", "coerce_a", "astype", "checkfilter"):
                pass
            elif name in ("negate", "negate_i", "increment", "increment_i", "decrement", "decrement_i", "not", "bitnot"):
                value = pop()
                if name.startswith("negate"):
                    stack.append(_int(-_number(value)) if name.endswith("_i") else -_number(value))
                elif name.startswith("increment"):
                    stack.append(_int(_number(value) + 1) if name.endswith("_i") else _number(value) + 1)
                elif name.startswith("decrement"):
                    stack.append(_int(_number(value) - 1) if name.endswith("_i") else _number(value) - 1)
                elif name == "not":
                    stack.append(not _truth(value))
                else:
                    stack.append(_int(~_int(value)))
            elif name in ("add", "add_i", "subtract", "subtract_i", "multiply", "multiply_i", "divide", "modulo", "equals", "strictequals", "lessthan", "lessequals", "greaterthan", "greaterequals"):
                right, left = pop(), pop()
                stack.append(_binary(name, left, right))
            elif name == "jump":
                target = item.offset + item.size + int(item.operands[0])
                next_pc = by_offset.get(target, len(instructions))
            elif name in ("iftrue", "iffalse", "ifeq", "ifne", "iflt", "ifle", "ifgt", "ifge", "ifnlt", "ifnle", "ifngt", "ifnge", "ifstricteq", "ifstrictne"):
                if _branch(name, pop):
                    target = item.offset + item.size + int(item.operands[0])
                    next_pc = by_offset.get(target, len(instructions))
            elif name == "lookupswitch":
                index = _int(pop())
                default, cases = item.operands[0]
                branch = cases[index] if 0 <= index < len(cases) else default
                next_pc = by_offset.get(item.offset + int(branch), len(instructions))
            elif name == "returnvalue":
                context.return_value = pop()
                break
            elif name == "returnvoid":
                context.return_value = _UNDEFINED
                break
            elif name == "throw":
                raise RuntimeError(f"ActionScript throw: {pop()!r}")
            elif name in ("getslot", "setslot"):
                slot = int(item.operands[0])
                prop = context.slot_names.get(slot)
                if name == "getslot":
                    stack.append(_get_property(context, pop(), prop) if prop else _UNDEFINED)
                else:
                    value, receiver = pop(), pop()
                    if prop:
                        _set_property(context, receiver, prop, value)
            else:
                _error(context.movie, context.path, context.class_name, f"Opcode {name} nicht im sicheren Teilumfang")
                break
        except Exception as exc:
            _error(context.movie, context.path, context.class_name, f"{name}: {exc}")
            break
        pc = next_pc
    return context.return_value


def execute_method(context, method_index, arguments=(), receiver=None):
    if context.depth >= _MAX_DEPTH:
        _error(context.movie, context.path, context.class_name, "Aufruftiefenlimit erreicht")
        return _UNDEFINED
    body = context.abc.method_body(method_index)
    if body is None:
        return _UNDEFINED
    child = RuntimeContext(
        context.movie, context.abc, context.class_name, context.path, context.definition,
        context.frame, context.playing, context.frame_count, context.labels, context.owner,
        context.trait_methods, context.slot_names, tuple(arguments), context.depth + 1,
    )
    locals_ = [receiver if receiver is not None else context.this_ref(), *tuple(arguments)]
    while len(locals_) < max(1, int(body.local_count)):
        locals_.append(_UNDEFINED)
    result = execute_instructions(child, avm2.disassemble_method(context.abc, method_index), locals_)
    context.steps += child.steps
    context.frame, context.playing = child.frame, child.playing
    context.jumped = context.jumped or child.jumped
    context.writes += child.writes
    context.callbacks += child.callbacks
    context.return_value = result
    return result


def _module(movie, binding):
    for module in getattr(movie, "avm2_modules", ()) or ():
        if module.name == binding.module_name and module.abc is not None and module.abc.method_body(binding.method_index):
            return module
    return None


def _instance(module, class_name):
    wanted, short = avm2._canonical_name(class_name), avm2._short_name(class_name)
    for index, value in enumerate(module.abc.instances):
        name = avm2._canonical_name(module.abc.class_name(index))
        if name == wanted or avm2._short_name(name) == short:
            return value
    return None


def _bindings(movie, class_name, frame):
    wanted, short = avm2._canonical_name(class_name), avm2._short_name(class_name)
    values = (getattr(movie, "avm2_bindings_by_class", {}) or {}).get(wanted)
    if values is None:
        values = next((value for key, value in (getattr(movie, "avm2_bindings_by_class", {}) or {}).items() if avm2._short_name(key) == short), ())
    return tuple(value for value in values or () if int(value.frame) == int(frame))


def _run_binding(owner, movie, path, definition, frame, playing, binding):
    module = _module(movie, binding)
    if module is None:
        return frame, playing, False
    instance = _instance(module, binding.class_name)
    traits = avm2._trait_method_map(module.abc, instance) if instance is not None else {}
    slots = {}
    if instance is not None:
        for trait in instance.traits:
            if trait.kind in (0, 6) and trait.slot_id:
                slots[int(trait.slot_id)] = avm2._short_name(module.abc.multiname_name(trait.name_index))
    context = RuntimeContext(
        movie, module.abc, binding.class_name, path, definition, int(frame), bool(playing),
        max(1, int(getattr(definition, "frame_count", getattr(movie, "frame_count", 1)) or 1)),
        dict(getattr(definition, "labels", getattr(movie, "labels", {})) or {}), owner, traits, slots,
    )
    execute_method(context, binding.method_index)
    return context.frame, context.playing, context.jumped


def timeline_frame_for_path(definition, path, overrides):
    movie = getattr(definition, "_ui_timeline_movie", None)
    if movie is None or not _enabled(movie):
        return _STATIC_NESTED(definition, path, overrides)
    if timeline_core.manual_frame_override(overrides, path) is not None:
        return avm2._BASE_TIMELINE_FRAME_FOR_PATH(definition, path, overrides)
    frame = avm2._BASE_TIMELINE_FRAME_FOR_PATH(definition, path, overrides)
    states = getattr(movie, "ui_timeline_states", {}) or {}
    state = states.setdefault(path, timeline_core.normalize_timeline_instance({"frame": frame}, definition.frame_count))
    class_name = str((getattr(movie, "symbol_classes", {}) or {}).get(definition.character_id, "") or "")
    if not class_name:
        return frame
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    for _ in range(8):
        bindings = _bindings(movie, class_name, frame)
        token = (avm2._canonical_name(class_name), int(frame), tuple(value.method_index for value in bindings), generation)
        if state.get("_avm2_runtime_token") == token:
            break
        state["_avm2_runtime_token"] = token
        if not bindings:
            break
        jumped = False
        for binding in bindings:
            frame, state["playing"], did_jump = _run_binding(
                getattr(movie, "_ui_avm2_runtime_owner", None), movie, path, definition,
                frame, state.get("playing", True), binding,
            )
            state["frame"] = int(frame)
            jumped = jumped or did_jump
        if not jumped:
            break
    return max(1, min(int(definition.frame_count), int(frame)))


def apply_root_frame_script(owner, force=False):
    movie = attach(owner)
    if movie is None:
        return False
    if not _enabled(movie):
        return _STATIC_ROOT(owner, force)
    class_name = str((getattr(movie, "symbol_classes", {}) or {}).get(0, "") or "")
    if not class_name:
        return False
    frame, playing = int(owner.frame_var.get()), bool(getattr(owner, "_ui_playback_running", False))
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    changed = False
    for _ in range(8):
        bindings = _bindings(movie, class_name, frame)
        token = (avm2._canonical_name(class_name), frame, tuple(value.method_index for value in bindings), generation)
        if not force and getattr(movie, "_ui_avm2_runtime_root_token", None) == token:
            break
        movie._ui_avm2_runtime_root_token = token
        if not bindings:
            break
        jumped = False
        before = int(getattr(movie, "ui_avm2_runtime_revision", 0))
        for binding in bindings:
            frame, playing, did_jump = _run_binding(owner, movie, "root", None, frame, playing, binding)
            jumped = jumped or did_jump
        if frame != int(owner.frame_var.get()):
            timeline_core.set_root_frame(owner, frame)
            changed = True
        if playing != bool(getattr(owner, "_ui_playback_running", False)):
            (avm2._BASE_TIMELINE_PLAY if playing else avm2._BASE_TIMELINE_PAUSE)(owner)
            changed = True
        changed = changed or before != int(getattr(movie, "ui_avm2_runtime_revision", 0))
        if not jumped:
            break
        force = True
    return changed


def _decorate(movie, nodes):
    values = _properties(movie) if _enabled(movie) else {}
    result = []
    for node in nodes or ():
        meta = dict(node.metadata)
        runtime = dict(values.get(node.path, {}) or {})
        visible = node.visible
        if runtime:
            meta["avm2_runtime"] = runtime
            manual = overrides_patch.normalize_override(meta.get("override", {}))
            if "visible" in runtime and "visible" not in manual:
                visible = bool(runtime["visible"])
                meta["visible"] = visible
            if "alpha" in runtime:
                color = dict(meta.get("color_transform", {}))
                color["a_mult"] = float(runtime["alpha"])
                color["a_add"] = 0
                meta["color_transform"] = color
            if node.kind == "EditText" and "text" not in manual:
                if "htmlText" in runtime:
                    meta.update(text=str(runtime["htmlText"]), display_text=str(runtime["htmlText"]), html=True)
                elif "text" in runtime:
                    meta.update(text=str(runtime["text"]), display_text=str(runtime["text"]), html=False)
        result.append(inspector.StateNode(
            node.path, node.depth, node.label, node.kind, visible,
            node.character_id, node.class_name, meta, _decorate(movie, node.children),
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    return _decorate(movie, _BASE_INSPECT(movie, frame, max_depth))


def format_state_node(node, resolver=None):
    text = _BASE_FORMAT_NODE(node, resolver)
    runtime = node.metadata.get("avm2_runtime")
    if not runtime:
        return text
    return text + "\n\nAVM2-Runtime:\n" + "\n".join(f"- {key}: {value}" for key, value in sorted(runtime.items()))


def attach(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return None
    if not hasattr(movie, "ui_avm2_runtime_enabled"):
        movie.ui_avm2_runtime_enabled = True
    _properties(movie)
    if not isinstance(getattr(movie, "ui_avm2_runtime_log", None), list):
        movie.ui_avm2_runtime_log = []
    if not isinstance(getattr(movie, "ui_avm2_runtime_errors", None), list):
        movie.ui_avm2_runtime_errors = []
    movie.ui_avm2_runtime_revision = int(getattr(movie, "ui_avm2_runtime_revision", 0))
    movie.ui_avm2_runtime_generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    movie._ui_avm2_runtime_owner = owner
    variable = getattr(owner, "avm2_runtime_enabled_var", None)
    if variable is not None and bool(variable.get()) != _enabled(movie):
        variable.set(_enabled(movie))
    return movie


def _clear_tokens(movie):
    movie._ui_avm2_runtime_root_token = None
    for state in (getattr(movie, "ui_timeline_states", {}) or {}).values():
        if isinstance(state, dict):
            state.pop("_avm2_runtime_token", None)


def reset_runtime(owner):
    movie = attach(owner)
    if movie is None:
        return
    _properties(movie).clear()
    movie.ui_avm2_runtime_log.clear()
    movie.ui_avm2_runtime_errors.clear()
    movie.ui_avm2_runtime_generation += 1
    _touch(movie)
    _clear_tokens(movie)
    if performance is not None:
        try:
            performance.clear_performance_caches()
        except Exception:
            pass
    owner.request_render()


def set_enabled(owner):
    movie = attach(owner)
    if movie is None:
        return
    movie.ui_avm2_runtime_enabled = bool(owner.avm2_runtime_enabled_var.get())
    movie.ui_avm2_runtime_generation += 1
    _touch(movie)
    _clear_tokens(movie)
    owner.request_render()


def browser_init(owner, *args, **kwargs):
    _BASE_INIT(owner, *args, **kwargs)
    owner.avm2_runtime_enabled_var = tk.BooleanVar(value=True)
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Checkbutton(
        bar, text="AVM2 Runtime", variable=owner.avm2_runtime_enabled_var,
        command=lambda: set_enabled(owner),
    ).pack(side="left")
    ttk.Button(bar, text="Runtime neu ausführen", command=lambda: reset_runtime(owner)).pack(side="left", padx=(6, 0))
    ttk.Label(bar, text="Sicherer Teilumfang: Branches, Properties und Game-Mock-Callbacks").pack(side="left", padx=(10, 0))
    owner.bind("<F10>", lambda _event: reset_runtime(owner))
    attach(owner)


def browser_select(owner, event=None):
    result = _BASE_SELECT(owner, event)
    attach(owner)
    return result


def browser_render(owner):
    attach(owner)
    return _BASE_RENDER(owner)


def browser_info(owner, stats):
    text = _BASE_INFO(owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    callbacks = sum(1 for item in getattr(movie, "ui_avm2_runtime_log", ()) if item.get("kind") == "callback")
    props = _properties(movie)
    return text + "\n\nAVM2 Runtime:\n" + (
        f"- Aktiv: {'ja' if _enabled(movie) else 'nein'}\n"
        f"- Property-Pfade: {len(props)}\n"
        f"- Property-Werte: {sum(len(value) for value in props.values())}\n"
        f"- Callback-Aufrufe: {callbacks}\n"
        f"- Abgebrochene Methoden: {len(getattr(movie, 'ui_avm2_runtime_errors', ()))}"
    )


def browser_close(owner):
    return _BASE_CLOSE(owner)


def _cache_key(renderer, frame, scale):
    return tuple(_BASE_CACHE_KEY(renderer, frame, scale)) + (
        _enabled(renderer.movie), int(getattr(renderer.movie, "ui_avm2_runtime_revision", 0)),
    )


def install():
    global _INSTALLED, _BASE_APPLY_ITEM, _BASE_TEXT_DEF, _BASE_INSPECT, _BASE_FORMAT_NODE
    global _BASE_INIT, _BASE_SELECT, _BASE_RENDER, _BASE_INFO, _BASE_CLOSE
    global _STATIC_NESTED, _STATIC_ROOT, _BASE_CACHE_KEY
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_APPLY_ITEM = overrides_patch.apply_item_override
    _BASE_TEXT_DEF = overrides_patch.text_definition_for_path
    _BASE_INSPECT = inspector.inspect_movie_state
    _BASE_FORMAT_NODE = inspector.format_state_node
    _BASE_INIT = ui_browser.UIBrowser.__init__
    _BASE_SELECT = ui_browser.UIBrowser._on_tree_select
    _BASE_RENDER = ui_browser.UIBrowser._render
    _BASE_INFO = ui_browser.UIBrowser._format_info
    _BASE_CLOSE = ui_browser.UIBrowser.close
    _STATIC_NESTED = timeline_core.timeline_frame_for_path
    _STATIC_ROOT = avm2.apply_root_frame_script

    overrides_patch.apply_item_override = apply_item_override
    overrides_patch.text_definition_for_path = text_definition_for_path
    timeline_core.timeline_frame_for_path = timeline_frame_for_path
    overrides_patch.sprite_frame_for_path = timeline_frame_for_path
    avm2.timeline_frame_for_path = timeline_frame_for_path
    avm2.apply_root_frame_script = apply_root_frame_script
    inspector.inspect_movie_state = inspect_movie_state
    inspector.format_state_node = format_state_node
    ui_browser.inspect_movie_state = inspect_movie_state

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = browser_select
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser._format_info = browser_info
    ui_browser.UIBrowser.close = browser_close
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime

    if performance is not None:
        _BASE_CACHE_KEY = performance._render_cache_key
        performance._render_cache_key = _cache_key

    ui_browser.AVM2_SAFE_NATIVE_CALLBACKS = SAFE_CALLBACKS
    ui_browser.register_avm2_native_callback = register_native_callback
    ui_browser.unregister_avm2_native_callback = unregister_native_callback
    ui_browser.execute_avm2_runtime_instructions = execute_instructions
