"""Safe AVM2 constructors, EventDispatcher listeners and timeline-clock timers."""
from __future__ import annotations

from dataclasses import dataclass, field

import ui_browser
import ui_browser_avm2_patch as avm2
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_state_override_patch as overrides_patch
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core

_INSTALLED = False
_BASE = {}
_UNDEFINED = runtime._UNDEFINED
_MAX_TIMER_FIRES = 32


@dataclass
class RuntimeEvent:
    type: str
    bubbles: bool = False
    cancelable: bool = False
    data: object = None
    target: object = None
    current_target: object = None
    default_prevented: bool = False
    stop_now: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class RuntimeDispatcher:
    token: int
    owner_path: str = "root"


@dataclass
class RuntimeTimer:
    token: int
    delay: float
    repeat_count: int = 0
    current_count: int = 0
    running: bool = False
    next_fire_ms: float = 0.0
    owner_path: str = "root"
    callback: object = None
    callback_args: tuple = ()
    callback_context: tuple = ()
    interval: bool = False


@dataclass
class Listener:
    event_type: str
    method: object
    abc: object
    class_name: str
    path: str
    definition: object
    trait_methods: dict
    slot_names: dict
    owner: object
    priority: int = 0


_CONSTANTS = {
    "ENTER_FRAME": "enterFrame", "EXIT_FRAME": "exitFrame",
    "ADDED": "added", "ADDED_TO_STAGE": "addedToStage",
    "REMOVED": "removed", "REMOVED_FROM_STAGE": "removedFromStage",
    "CHANGE": "change", "COMPLETE": "complete", "SELECT": "select",
    "TIMER": "timer", "TIMER_COMPLETE": "timerComplete",
    "CLICK": "click", "MOUSE_DOWN": "mouseDown", "MOUSE_UP": "mouseUp",
    "KEY_DOWN": "keyDown", "KEY_UP": "keyUp",
    "FOCUS_IN": "focusIn", "FOCUS_OUT": "focusOut",
}


def _state(movie):
    value = getattr(movie, "ui_avm2_lifecycle_state", None)
    if not isinstance(value, dict):
        value = {
            "modules": set(), "classes": set(), "instances": set(),
            "objects": {}, "listeners": {}, "timers": {},
            "clock_ms": 0.0, "next_token": 1,
            "constructors": 0, "events": 0,
        }
        movie.ui_avm2_lifecycle_state = value
    return value


def _next_token(movie):
    state = _state(movie)
    value = int(state["next_token"])
    state["next_token"] = value + 1
    return value


def _enabled(movie):
    return bool(getattr(movie, "ui_avm2_runtime_enabled", True))


def _root_frame(owner):
    try:
        return max(1, int(owner.frame_var.get()))
    except Exception:
        return 1


def _key(value):
    if isinstance(value, runtime.RuntimeRef):
        return ("path", value.path)
    if isinstance(value, RuntimeDispatcher):
        return ("dispatcher", value.token)
    if isinstance(value, RuntimeTimer):
        return ("timer", value.token)
    if isinstance(value, runtime.RuntimeGlobal):
        return ("global", value.name)
    return None


def _event_name(value):
    if isinstance(value, RuntimeEvent):
        return value.type
    if isinstance(value, runtime.RuntimeGlobal):
        return value.name.rsplit(".", 1)[-1]
    return str(value or "")


def _traits(abc, owner):
    methods = avm2._trait_method_map(abc, owner) if owner is not None else {}
    slots = {}
    for trait in getattr(owner, "traits", ()) or ():
        if trait.kind in (0, 6) and trait.slot_id:
            slots[int(trait.slot_id)] = avm2._short_name(abc.multiname_name(trait.name_index))
    return methods, slots


def _context(owner, movie, abc, class_name, path, definition, frame, playing, traits):
    methods, slots = _traits(abc, traits)
    return runtime.RuntimeContext(
        movie, abc, str(class_name), str(path), definition,
        max(1, int(frame)), bool(playing),
        max(1, int(getattr(definition, "frame_count", getattr(movie, "frame_count", 1)) or 1)),
        dict(getattr(definition, "labels", getattr(movie, "labels", {})) or {}),
        owner, methods, slots,
    )


def _find_class(movie, class_name):
    wanted, short = avm2._canonical_name(class_name), avm2._short_name(class_name)
    fallback = None
    for module in getattr(movie, "avm2_modules", ()) or ():
        abc = getattr(module, "abc", None)
        if abc is None:
            continue
        for index in range(len(abc.instances)):
            name = avm2._canonical_name(abc.class_name(index))
            if name == wanted:
                return module, index
            if fallback is None and avm2._short_name(name) == short:
                fallback = (module, index)
    return fallback


def _run_init(owner, movie, module, trait_owner, method, class_name, path, definition, frame, playing):
    if module.abc.method_body(method) is None:
        return
    context = _context(owner, movie, module.abc, class_name, path, definition, frame, playing, trait_owner)
    runtime.execute_method(context, method, receiver=context.this_ref())
    runtime._log(movie, "initializer", class_name=class_name, path=path, method=method, steps=context.steps)


def initialize_instance(owner, movie, path, definition, class_name, frame=1, playing=True):
    found = _find_class(movie, class_name) if class_name and _enabled(movie) else None
    if found is None:
        return False
    module, class_index = found
    state = _state(movie)
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    module_token = (module.name, module.source, generation)
    if module_token not in state["modules"]:
        state["modules"].add(module_token)
        for index, script in enumerate(module.abc.scripts):
            _run_init(owner, movie, module, script, script.initializer,
                      f"<script:{module.name}:{index}>", "root", None, frame, playing)
    name = avm2._canonical_name(module.abc.class_name(class_index))
    class_token = (module.name, name, generation)
    if class_token not in state["classes"]:
        state["classes"].add(class_token)
        cls = module.abc.classes[class_index]
        _run_init(owner, movie, module, cls, cls.initializer,
                  name, f"class:{name}", definition, frame, playing)
    instance_token = (str(path), name, generation)
    if instance_token in state["instances"]:
        return False
    state["instances"].add(instance_token)
    instance = module.abc.instances[class_index]
    _run_init(owner, movie, module, instance, instance.initializer,
              name, str(path), definition, frame, playing)
    state["constructors"] += 1
    return True


def set_property(context, reference, name, value):
    if isinstance(reference, runtime.RuntimeRef) and isinstance(value, (RuntimeEvent, RuntimeDispatcher, RuntimeTimer)):
        _state(context.movie)["objects"].setdefault(reference.path, {})[avm2._short_name(name)] = value
        context.writes += 1
        runtime._touch(context.movie)
        return True
    return _BASE["set"](context, reference, name, value)


def get_property(context, receiver, name):
    short = avm2._short_name(name)
    if isinstance(receiver, runtime.RuntimeGlobal):
        if short in _CONSTANTS:
            return _CONSTANTS[short]
        if short and short.upper() == short and any(ch.isalpha() for ch in short):
            return short
        for path in ("root", f"class:{avm2._canonical_name(receiver.name)}"):
            objects = _state(context.movie)["objects"].get(path, {})
            if short in objects:
                return objects[short]
    if isinstance(receiver, runtime.RuntimeRef):
        objects = _state(context.movie)["objects"].get(receiver.path, {})
        if short in objects:
            return objects[short]
    if isinstance(receiver, RuntimeEvent):
        return {
            "type": receiver.type, "bubbles": receiver.bubbles,
            "cancelable": receiver.cancelable, "data": receiver.data,
            "target": receiver.target, "currentTarget": receiver.current_target,
        }.get(short, receiver.extra.get(short, _UNDEFINED))
    if isinstance(receiver, RuntimeTimer):
        return {
            "delay": receiver.delay, "repeatCount": receiver.repeat_count,
            "currentCount": receiver.current_count, "running": receiver.running,
        }.get(short, _UNDEFINED)
    return _BASE["get"](context, receiver, name)


def _listener(context, event_type, method, priority=0):
    if not isinstance(method, runtime.RuntimeMethod):
        return None
    return Listener(
        _event_name(event_type), method, context.abc, context.class_name,
        context.path, context.definition, dict(context.trait_methods),
        dict(context.slot_names), context.owner, int(priority or 0),
    )


def add_listener(context, dispatcher, event_type, method, priority=0):
    key, listener = _key(dispatcher), _listener(context, event_type, method, priority)
    if key is None or listener is None or not listener.event_type:
        return False
    values = _state(context.movie)["listeners"].setdefault(key, {}).setdefault(listener.event_type, [])
    identity = (listener.method.index, _key(listener.method.receiver))
    if not any((item.method.index, _key(item.method.receiver)) == identity for item in values):
        values.append(listener)
        values.sort(key=lambda item: item.priority, reverse=True)
    return True


def remove_listener(context, dispatcher, event_type, method):
    key = _key(dispatcher)
    if key is None or not isinstance(method, runtime.RuntimeMethod):
        return False
    groups = _state(context.movie)["listeners"].get(key, {})
    event_type = _event_name(event_type)
    identity = (method.index, _key(method.receiver))
    groups[event_type] = [item for item in groups.get(event_type, ())
                          if (item.method.index, _key(item.method.receiver)) != identity]
    if not groups[event_type]:
        groups.pop(event_type, None)
    if not groups:
        _state(context.movie)["listeners"].pop(key, None)
    return True


def _invoke(movie, listener, event, arguments=None):
    owner = listener.owner or getattr(movie, "_ui_avm2_runtime_owner", None)
    if listener.path == "root":
        frame, playing = _root_frame(owner), bool(getattr(owner, "_ui_playback_running", False))
    else:
        state = (getattr(movie, "ui_timeline_states", {}) or {}).get(listener.path, {})
        frame, playing = int(state.get("frame", 1)), bool(state.get("playing", True))
    context = runtime.RuntimeContext(
        movie, listener.abc, listener.class_name, listener.path, listener.definition,
        frame, playing,
        max(1, int(getattr(listener.definition, "frame_count", getattr(movie, "frame_count", 1)) or 1)),
        dict(getattr(listener.definition, "labels", getattr(movie, "labels", {})) or {}),
        owner, listener.trait_methods, listener.slot_names,
    )
    runtime.execute_method(
        context, listener.method.index,
        tuple(arguments) if arguments is not None else (event,),
        listener.method.receiver or context.this_ref(),
    )
    if listener.path == "root" and owner is not None:
        if context.frame != _root_frame(owner):
            timeline_core.set_root_frame(owner, context.frame)
        owner._ui_playback_running = bool(context.playing)
    return context


def _dispatch_key(movie, key, event):
    groups = _state(movie)["listeners"].get(key, {})
    event.target = event.target or key
    event.current_target = key
    delivered = 0
    for listener in list(groups.get(event.type, ())):
        _invoke(movie, listener, event)
        delivered += 1
        if event.stop_now:
            break
    _state(movie)["events"] += delivered
    if delivered:
        runtime._log(movie, "event", target=repr(key), event=event.type, listeners=delivered)
    return delivered


def dispatch_event(context, dispatcher, event):
    event = event if isinstance(event, RuntimeEvent) else RuntimeEvent(_event_name(event))
    key = _key(dispatcher)
    if key is None:
        return False
    _dispatch_key(context.movie, key, event)
    return not event.default_prevented


def _new_timer(context, args):
    try:
        delay = max(1.0, float(args[0])) if args else 1000.0
    except Exception:
        delay = 1000.0
    try:
        repeat = max(0, int(args[1])) if len(args) > 1 else 0
    except Exception:
        repeat = 0
    timer = RuntimeTimer(_next_token(context.movie), delay, repeat, owner_path=context.path)
    _state(context.movie)["timers"][timer.token] = timer
    return timer


def _resolve_global(context, receiver):
    if not isinstance(receiver, runtime.RuntimeGlobal):
        return receiver
    short = receiver.name.rsplit(".", 1)[-1]
    for path in ("root", f"class:{avm2._canonical_name(receiver.name)}"):
        value = _state(context.movie)["objects"].get(path, {}).get(short, _UNDEFINED)
        if value is not _UNDEFINED:
            return value
    return receiver


def call_value(context, receiver, name, args):
    short = avm2._short_name(name)
    lower = short.lower()
    if lower == "eventdispatcher":
        return RuntimeDispatcher(_next_token(context.movie), context.path)
    if lower == "timer":
        return _new_timer(context, args)
    if lower.endswith("event") and lower not in ("addeventlistener", "removeeventlistener", "dispatchevent", "errorevent", "logevent"):
        return RuntimeEvent(
            _event_name(args[0]) if args else short,
            bool(args[1]) if len(args) > 1 else False,
            bool(args[2]) if len(args) > 2 else False,
            args[3] if len(args) > 3 else None,
            extra={f"arg{i}": value for i, value in enumerate(args[1:], 1)},
        )
    resolved = _resolve_global(context, receiver)
    if resolved is not receiver:
        return call_value(context, resolved, name, args)
    if lower == "addeventlistener" and len(args) >= 2:
        add_listener(context, receiver, args[0], args[1], args[3] if len(args) > 3 else 0)
        return _UNDEFINED
    if lower == "removeeventlistener" and len(args) >= 2:
        remove_listener(context, receiver, args[0], args[1])
        return _UNDEFINED
    if lower in ("haseventlistener", "willtrigger") and args:
        key = _key(receiver)
        return bool(key and _state(context.movie)["listeners"].get(key, {}).get(_event_name(args[0])))
    if lower == "dispatchevent" and args:
        return dispatch_event(context, receiver, args[0])
    if isinstance(receiver, RuntimeEvent):
        if lower == "preventdefault":
            receiver.default_prevented = receiver.cancelable
            return _UNDEFINED
        if lower in ("stoppropagation", "stopimmediatepropagation"):
            receiver.stop_now = True
            return _UNDEFINED
    if isinstance(receiver, RuntimeTimer):
        now = float(_state(context.movie)["clock_ms"])
        if lower == "start":
            if not receiver.running:
                receiver.running = True
                receiver.next_fire_ms = now + receiver.delay
            return _UNDEFINED
        if lower == "stop":
            receiver.running = False
            return _UNDEFINED
        if lower == "reset":
            receiver.running = False
            receiver.current_count = 0
            receiver.next_fire_ms = 0.0
            return _UNDEFINED
    if lower == "gettimer":
        return int(_state(context.movie)["clock_ms"])
    if lower in ("settimeout", "setinterval") and len(args) >= 2:
        timer = _new_timer(context, (args[1], 0 if lower == "setinterval" else 1))
        timer.callback = args[0]
        timer.callback_args = tuple(args[2:])
        timer.callback_context = (
            context.abc, context.class_name, context.path, context.definition,
            dict(context.trait_methods), dict(context.slot_names), context.owner,
        )
        timer.interval = lower == "setinterval"
        timer.running = True
        timer.next_fire_ms = float(_state(context.movie)["clock_ms"]) + timer.delay
        return timer.token
    if lower in ("cleartimeout", "clearinterval") and args:
        try:
            _state(context.movie)["timers"].pop(int(args[0]), None)
        except Exception:
            pass
        return _UNDEFINED
    return _BASE["call"](context, receiver, name, args)


def advance_runtime_clock(owner, milliseconds):
    movie = getattr(owner, "_current_movie", None)
    if movie is None or not _enabled(movie):
        return 0
    state = _state(movie)
    state["clock_ms"] += max(0.0, float(milliseconds))
    delivered = 0
    for key, groups in list(state["listeners"].items()):
        if groups.get("enterFrame"):
            delivered += _dispatch_key(movie, key, RuntimeEvent("enterFrame"))
    now = state["clock_ms"]
    for token, timer in list(state["timers"].items()):
        fires = 0
        while timer.running and now >= timer.next_fire_ms and fires < _MAX_TIMER_FIRES:
            fires += 1
            timer.current_count += 1
            if isinstance(timer.callback, runtime.RuntimeMethod) and timer.callback_context:
                abc, class_name, path, definition, methods, slots, callback_owner = timer.callback_context
                listener = Listener("timeout", timer.callback, abc, class_name, path,
                                    definition, methods, slots, callback_owner)
                _invoke(movie, listener, None, timer.callback_args)
                delivered += 1
            else:
                delivered += _dispatch_key(movie, ("timer", token), RuntimeEvent("timer"))
            complete = bool(timer.repeat_count and timer.current_count >= timer.repeat_count)
            if complete or (timer.callback is not None and not timer.interval):
                timer.running = False
                if timer.callback is None:
                    delivered += _dispatch_key(movie, ("timer", token), RuntimeEvent("timerComplete"))
                break
            timer.next_fire_ms += timer.delay
        if not timer.running and timer.callback is not None:
            state["timers"].pop(token, None)
    if delivered:
        runtime._touch(movie)
        try:
            owner.request_render()
        except Exception:
            pass
    return delivered


def advance(owner, steps=1, force_nested=False):
    result = _BASE["advance"](owner, steps, force_nested)
    movie = getattr(owner, "_current_movie", None)
    if movie is not None and _enabled(movie):
        fps = max(1.0, float(getattr(movie, "frame_rate", 30.0) or 30.0))
        for _ in range(min(32, max(1, abs(int(steps))))):
            advance_runtime_clock(owner, 1000.0 / fps)
    return result


def timeline_frame_for_path(definition, path, overrides):
    movie = getattr(definition, "_ui_timeline_movie", None)
    if movie is not None and _enabled(movie):
        class_name = str((getattr(movie, "symbol_classes", {}) or {}).get(definition.character_id, "") or "")
        initialize_instance(
            getattr(movie, "_ui_avm2_runtime_owner", None), movie, path, definition,
            class_name, avm2._BASE_TIMELINE_FRAME_FOR_PATH(definition, path, overrides), True,
        )
    return _BASE["nested"](definition, path, overrides)


def apply_root_frame_script(owner, force=False):
    movie = runtime.attach(owner)
    if movie is not None and _enabled(movie):
        class_name = str((getattr(movie, "symbol_classes", {}) or {}).get(0, "") or "")
        initialize_instance(
            owner, movie, "root", None, class_name,
            _root_frame(owner), bool(getattr(owner, "_ui_playback_running", False)),
        )
    return _BASE["root"](owner, force)


def attach(owner):
    movie = _BASE["attach"](owner)
    if movie is not None:
        _state(movie)
    return movie


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_avm2_lifecycle_state = None
    result = _BASE["reset"](owner)
    if movie is not None:
        try:
            apply_root_frame_script(owner, True)
        except Exception as exc:
            runtime._error(movie, "root", "lifecycle-reset", exc)
    return result


def format_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    state = _state(movie)
    listeners = sum(len(items) for groups in state["listeners"].values() for items in groups.values())
    running = sum(1 for timer in state["timers"].values() if timer.running)
    return text + "\n\nAVM2 Lifecycle / Events:\n" + (
        f"- Script-Module: {len(state['modules'])}\n"
        f"- Klassen: {len(state['classes'])}\n"
        f"- Instanz-Konstruktoren: {state['constructors']}\n"
        f"- Event-Listener: {listeners}\n"
        f"- Timer: {len(state['timers'])} ({running} laufend)\n"
        f"- Runtime-Uhr: {state['clock_ms']:.1f} ms\n"
        f"- Listener-Aufrufe: {state['events']}"
    )


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        call=runtime._call, get=runtime._get_property, set=runtime._set_property,
        attach=runtime.attach, reset=runtime.reset_runtime,
        root=avm2.apply_root_frame_script,
        nested=timeline_core.timeline_frame_for_path,
        advance=timeline_browser.advance,
        info=ui_browser.UIBrowser._format_info,
    )
    runtime._call = call_value
    runtime._get_property = get_property
    runtime._set_property = set_property
    runtime.attach = attach
    runtime.reset_runtime = reset_runtime
    timeline_core.timeline_frame_for_path = timeline_frame_for_path
    overrides_patch.sprite_frame_for_path = timeline_frame_for_path
    avm2.timeline_frame_for_path = timeline_frame_for_path
    avm2.apply_root_frame_script = apply_root_frame_script
    timeline_browser.advance = advance
    ui_browser.UIBrowser._format_info = format_info
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime
    ui_browser.RuntimeAVM2Event = RuntimeEvent
    ui_browser.RuntimeAVM2Timer = RuntimeTimer
    ui_browser.dispatch_avm2_event = dispatch_event
    ui_browser.advance_avm2_runtime_clock = advance_runtime_clock
    ui_browser.initialize_avm2_instance = initialize_instance
