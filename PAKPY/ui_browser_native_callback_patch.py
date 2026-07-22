"""DKCTF native-callback inventory and safe preview implementations.

This patch inventories calls that cross the Scaleform/host boundary, exposes the call sites
in a dedicated inspector and implements a deterministic preview-only subset.  Every write
is kept on the current SwfMovie object.  No file, process, network, audio-device or game
process API is reachable from this module.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ui_browser
import ui_browser_avm2_patch as avm2
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_state_inspector_patch as state_inspector
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_core as timeline_core
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_inspector_patch as timeline_inspector

try:
    import ui_browser_game_state_patch as game_state
except Exception:
    game_state = None

from ui_browser_native_callback_catalog import (
    CallbackSpec, KNOWN_CATEGORIES, callback_spec, compact_name,
)


_INSTALLED = False
_BASE = {}
_UNDEFINED = runtime._UNDEFINED
_MAX_CALL_LOG = 2000
_MAX_BUCKET = 500
_MAX_OVERRIDES = 256
_DYNAMIC_ARGUMENT = "<dynamic>"

_BRIDGE_ROOTS = {
    "externalinterface", "externalinterfaceas3", "controller", "model",
    "getdatavalue", "setdatavalue", "initdatavalue", "notifydatavalue",
    "listenfordata", "getvalue", "getdictionary", "filldatadictionary",
}
_DIRECT_BRIDGE_CALLS = {
    "getdatavalue", "fgetdatavalue", "setdatavalue", "fsetdatavalue",
    "initdatavalue", "finitdatavalue", "notifydatavalue", "listenfordata",
    "getvalue", "getdictionary", "filldatadictionary", "playsound",
    "debugsoundplay", "logevent", "errorevent",
}


@dataclass(frozen=True)
class NativeCallbackSite:
    callback: str
    bridge: str
    category: str
    module: str
    source: str
    class_name: str
    method_name: str
    method_index: int
    offset: int
    arguments: tuple = ()
    dynamic_name: bool = False


@dataclass(frozen=True)
class NativeCallbackSummary:
    name: str
    category: str
    behavior: str
    return_policy: str
    implemented: bool
    count: int
    bridges: tuple = ()
    argument_samples: tuple = ()
    sites: tuple[NativeCallbackSite, ...] = field(default_factory=tuple)


def _json_safe(value, depth=0):
    if value is _UNDEFINED:
        return None
    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, runtime.RuntimeRef):
        return {"path": value.path}
    if hasattr(ui_browser, "DynamicAVM2DisplayObject") and isinstance(
        value, getattr(ui_browser, "DynamicAVM2DisplayObject")
    ):
        return {"path": value.path, "class": value.class_name, "name": value.name}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item, depth + 1) for item in list(value)[:256]]
    if isinstance(value, dict):
        result = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 256:
                break
            result[str(key)] = _json_safe(item, depth + 1)
        return result
    return repr(value)


def _bounded_append(values, item, limit=_MAX_BUCKET):
    values.append(item)
    if len(values) > limit:
        del values[:len(values) - limit]


def _receiver_path(value):
    if not isinstance(value, tuple) or not value:
        return ""
    kind = value[0]
    if kind == "lex":
        return str(value[1])
    if kind == "property":
        parent = _receiver_path(value[1])
        name = str(value[2])
        return f"{parent}.{name}" if parent else name
    if kind == "this":
        return "this"
    if kind == "literal":
        return repr(value[1])
    if kind == "local":
        return f"<local:{value[1]}>"
    if kind == "call-result":
        return f"<result:{value[1]}>"
    return f"<{kind}>"


def _abstract_argument(value):
    literal = avm2._stack_literal(value)
    if literal is not None or (isinstance(value, tuple) and value and value[0] == "literal"):
        return _json_safe(literal)
    return _DYNAMIC_ARGUMENT


def _method_owners(abc):
    owners = defaultdict(list)
    for class_index, instance in enumerate(abc.instances):
        class_name = avm2._canonical_name(abc.class_name(class_index))
        owners[instance.initializer].append((class_name, "<instance initializer>"))
        for trait in instance.traits:
            if trait.method_index >= 0:
                owners[trait.method_index].append((
                    class_name, avm2._short_name(abc.multiname_name(trait.name_index)),
                ))
        if class_index < len(abc.classes):
            class_info = abc.classes[class_index]
            owners[class_info.initializer].append((class_name, "<class initializer>"))
            for trait in class_info.traits:
                if trait.method_index >= 0:
                    owners[trait.method_index].append((
                        class_name,
                        "static " + avm2._short_name(abc.multiname_name(trait.name_index)),
                    ))
    for script_index, script in enumerate(abc.scripts):
        script_name = f"<script {script_index}>"
        owners[script.initializer].append((script_name, "<script initializer>"))
        for trait in script.traits:
            if trait.method_index >= 0:
                owners[trait.method_index].append((
                    script_name, avm2._short_name(abc.multiname_name(trait.name_index)),
                ))
    return owners


def _callback_from_call(property_name, arguments, receiver):
    bridge = _receiver_path(receiver)
    root = compact_name(bridge.split(".", 1)[0])
    prop_key = compact_name(property_name)
    abstract_args = tuple(_abstract_argument(value) for value in arguments)
    if prop_key == "call" and root in ("externalinterface", "externalinterfaceas3"):
        if abstract_args and isinstance(abstract_args[0], str) and abstract_args[0] != _DYNAMIC_ARGUMENT:
            return str(abstract_args[0]), bridge, abstract_args[1:], False
        return "<dynamic ExternalInterface.call>", bridge, abstract_args[1:], True
    if root in _BRIDGE_ROOTS:
        # Controller.mEventDispatcher is an ActionScript EventDispatcher object, not a
        # host bridge. Cast-like Controller.int calls are local AVM2 helpers as well.
        if root == "controller" and (
            "meventdispatcher" in compact_name(bridge)
            or prop_key in {"addeventlistener", "removeeventlistener", "haseventlistener", "dispatchevent", "int", "uint", "number", "string", "boolean"}
        ):
            return None
        return str(property_name), bridge or "global", abstract_args, False
    if prop_key in _DIRECT_BRIDGE_CALLS and (not bridge or bridge.startswith("<")):
        return str(property_name), bridge or "global", abstract_args, False
    return None


def extract_callback_sites(module):
    abc = getattr(module, "abc", None)
    if abc is None:
        return ()
    owners = _method_owners(abc)
    sites = []
    seen = set()
    for method_index in range(len(abc.methods)):
        contexts = owners.get(method_index) or [("<unknown>", abc.method_name(method_index))]
        class_name, method_name = contexts[0]
        try:
            calls = avm2._simulate_calls(abc, method_index, {})
        except Exception:
            calls = ()
        for property_name, arguments, receiver, instruction in calls:
            found = _callback_from_call(property_name, arguments, receiver)
            if found is None:
                continue
            callback, bridge, callback_args, dynamic_name = found
            key = (callback, bridge, method_index, int(instruction.offset), callback_args)
            if key in seen:
                continue
            seen.add(key)
            spec = callback_spec(callback)
            sites.append(NativeCallbackSite(
                callback=callback,
                bridge=bridge,
                category=spec.category,
                module=str(getattr(module, "name", "") or "<unnamed>"),
                source=str(getattr(module, "source", "") or "root"),
                class_name=class_name,
                method_name=method_name,
                method_index=int(method_index),
                offset=int(instruction.offset),
                arguments=callback_args,
                dynamic_name=dynamic_name,
            ))
    return tuple(sites)


def summarize_callback_sites(sites):
    grouped = defaultdict(list)
    for site in tuple(sites or ()):
        grouped[site.callback].append(site)
    result = []
    for name, values in grouped.items():
        spec = callback_spec(name)
        samples = []
        for site in values:
            if site.arguments not in samples:
                samples.append(site.arguments)
            if len(samples) >= 8:
                break
        implemented = spec.category != "unknown" and spec.behavior != "log-only"
        result.append(NativeCallbackSummary(
            name=name,
            category=spec.category,
            behavior=spec.behavior,
            return_policy=spec.return_policy,
            implemented=implemented,
            count=len(values),
            bridges=tuple(sorted({site.bridge for site in values})),
            argument_samples=tuple(samples),
            sites=tuple(values),
        ))
    return tuple(sorted(result, key=lambda item: (item.category, item.name.lower())))


def attach_native_callback_inventory(movie):
    modules = tuple(getattr(movie, "avm2_modules", ()) or ())
    token = tuple((id(module), id(getattr(module, "abc", None))) for module in modules)
    if getattr(movie, "_ui_native_callback_inventory_token", None) == token:
        return movie
    sites = []
    for module in modules:
        sites.extend(extract_callback_sites(module))
    movie.ui_native_callback_sites = tuple(sites)
    movie.ui_native_callback_summaries = summarize_callback_sites(sites)
    movie._ui_native_callback_inventory_token = token
    movie.ui_native_callback_inventory_revision = int(
        getattr(movie, "ui_native_callback_inventory_revision", 0)
    ) + 1
    _ensure_config(movie)
    return movie


def _ensure_config(movie):
    if str(getattr(movie, "ui_native_callback_mode", "")) not in ("simulate", "observe"):
        movie.ui_native_callback_mode = "simulate"
    raw = getattr(movie, "ui_native_callback_overrides", None)
    if not isinstance(raw, dict):
        movie.ui_native_callback_overrides = {}
    return movie


def _callback_state(movie):
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    value = getattr(movie, "ui_native_callback_state", None)
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {
            "generation": generation,
            "calls": [],
            "counts": {},
            "category_counts": {},
            "unknown": [],
            "audio_requests": [],
            "telemetry": [],
            "navigation": [],
            "gameplay_events": [],
            "subscriptions": {},
            "dictionaries": {},
            "controller": {
                "dynamic_mode": False,
                "reassigning": False,
                "player1_mode": 0,
                "player2_mode": 0,
                "player1_motion": False,
                "player2_motion": False,
                "swap_active": False,
            },
            "save": {"selected_slot": 0, "slots": {}, "funky_mode": False, "flags": {}},
            "shop": {"selected_item": None, "purchases": [], "figurine_status": 0},
            "extras": {"unlocked": True, "category_unlocked": True, "new_items": {}, "new_categories": {}, "active": {}},
            "leaderboard": {"entries": [], "queries": [], "replay": False},
            "transition": {"prepared": False, "states": {}, "current": ""},
            "lifecycle": {},
        }
        movie.ui_native_callback_state = value
    return value


def _runtime_time(movie):
    lifecycle = getattr(movie, "ui_avm2_lifecycle_state", None)
    if isinstance(lifecycle, dict):
        try:
            return float(lifecycle.get("clock_ms", 0.0))
        except Exception:
            pass
    return 0.0


def _native_data(movie):
    value = getattr(movie, "ui_avm2_native_data", None)
    if not isinstance(value, dict):
        value = {}
        movie.ui_avm2_native_data = value
    return value


def _mock_snapshot(movie):
    if not bool(getattr(movie, "ui_game_mock_enabled", False)):
        return {}
    active = set(getattr(movie, "ui_game_mock_roles", ()) or ())
    values = getattr(movie, "ui_game_mock_values", {}) or {}
    return {key: _json_safe(value) for key, value in values.items() if key in active}


def _safe_index(value, default=0):
    try:
        return max(0, int(value))
    except Exception:
        return int(default)


def _find_override(movie, name):
    wanted = compact_name(name)
    for key, value in (getattr(movie, "ui_native_callback_overrides", {}) or {}).items():
        if compact_name(key) == wanted:
            return True, value
    return False, _UNDEFINED


def _record_callback(context, name, args, spec, source, result):
    movie = context.movie
    state = _callback_state(movie)
    counts = state["counts"]
    counts[name] = int(counts.get(name, 0)) + 1
    categories = state["category_counts"]
    categories[spec.category] = int(categories.get(spec.category, 0)) + 1
    record = {
        "name": str(name),
        "category": spec.category,
        "source": source,
        "arguments": _json_safe(args),
        "result": _json_safe(result),
        "path": str(context.path),
        "time_ms": _runtime_time(movie),
    }
    _bounded_append(state["calls"], record, _MAX_CALL_LOG)
    if spec.category == "unknown":
        _bounded_append(state["unknown"], record, _MAX_BUCKET)
    logs = getattr(movie, "ui_avm2_runtime_log", None)
    if isinstance(logs, list):
        wanted = compact_name(name)
        for item in reversed(logs[-12:]):
            if item.get("kind") == "callback" and compact_name(item.get("name")) == wanted:
                item["status"] = source
                item["result"] = repr(result)
                item["category"] = spec.category
                break
    return result


def _base_data_call(context, name, args):
    return _BASE["native"](context, name, args)


def _data_address(args):
    values = list(args)
    dictionary = ""
    field_name = ""
    for index, item in enumerate(values):
        if isinstance(item, str) and item.startswith("m"):
            dictionary = item
            if index + 1 < len(values) and isinstance(values[index + 1], str):
                field_name = values[index + 1]
            break
    return dictionary, field_name


def _mock_data_value(movie, field_name):
    try:
        role = runtime._callback_role(field_name)
    except Exception:
        role = None
    active = set(getattr(movie, "ui_game_mock_roles", ()) or ())
    values = getattr(movie, "ui_game_mock_values", {}) or {}
    if bool(getattr(movie, "ui_game_mock_enabled", False)) and role in active and role in values:
        return values[role]
    return _UNDEFINED


def _data_handler(context, name, args, spec):
    key = compact_name(name)
    state = _callback_state(context.movie)
    if key in ("getdatavalue", "readdatavalue", "getvalue", "setdatavalue", "writedatavalue"):
        return _UNDEFINED
    if key in ("fgetdatavalue", "fsetdatavalue"):
        dictionary, field_name = _data_address(args)
        if not dictionary or not field_name:
            return _UNDEFINED
        store = _native_data(context.movie)
        if key == "fgetdatavalue":
            if (dictionary, field_name) in store:
                return store[(dictionary, field_name)]
            return _mock_data_value(context.movie, field_name)
        value = _json_safe(args[-1] if args else None)
        store[(dictionary, field_name)] = value
        state["dictionaries"].setdefault(dictionary, {})[field_name] = value
        return value
    if key == "getislandsummaryentry":
        return {}
    if key == "filldatadictionary":
        for item in args:
            if isinstance(item, str) and item:
                state["dictionaries"].setdefault(item, {})
        return True
    if key == "getdictionary":
        name_value = next((str(item) for item in reversed(args) if isinstance(item, str) and item), "")
        return dict(state["dictionaries"].get(name_value, {}))
    if key in ("initdatavalue", "finitdatavalue"):
        strings = [item for item in args if isinstance(item, str)]
        dictionary = next((item for item in strings if item.startswith("m")), strings[0] if strings else "")
        field_name = ""
        if dictionary in args:
            position = list(args).index(dictionary)
            if position + 1 < len(args) and isinstance(args[position + 1], str):
                field_name = args[position + 1]
        default = args[-1] if args else None
        if dictionary and field_name:
            store = _native_data(context.movie)
            store.setdefault((dictionary, field_name), _json_safe(default))
            state["dictionaries"].setdefault(dictionary, {})[field_name] = store[(dictionary, field_name)]
            return store[(dictionary, field_name)]
        return _json_safe(default)
    if key == "notifydatavalue":
        if len(args) >= 2:
            field_name = str(args[-2])
            value = _json_safe(args[-1])
            _bounded_append(state["gameplay_events"], {
                "type": "data-notify", "field": field_name, "value": value,
            })
        return True
    if key == "listenfordata":
        field_name = str(args[0]) if args else ""
        descriptor = _json_safe(args[1] if len(args) > 1 else None)
        values = state["subscriptions"].setdefault(field_name, [])
        if descriptor not in values:
            values.append(descriptor)
            if len(values) > 64:
                del values[:-64]
        return True
    return _UNDEFINED


def _audio_handler(context, name, args):
    state = _callback_state(context.movie)
    sound = next((item for item in args if isinstance(item, str) and item), "")
    event = {
        "callback": str(name), "sound": sound, "arguments": _json_safe(args),
        "path": context.path, "time_ms": _runtime_time(context.movie),
    }
    _bounded_append(state["audio_requests"], event)
    return True


def _telemetry_handler(context, name, args):
    state = _callback_state(context.movie)
    _bounded_append(state["telemetry"], {
        "callback": str(name), "arguments": _json_safe(args),
        "path": context.path, "time_ms": _runtime_time(context.movie),
    })
    return _UNDEFINED


def _controller_handler(context, name, args):
    key = compact_name(name)
    values = _callback_state(context.movie)["controller"]
    if key == "isdynamiccontrollermodeactive":
        return bool(values["dynamic_mode"])
    if key == "getprimarycontrollertype":
        return values.get("player1_mode", 0)
    if key == "getcontrollertypefromplayer":
        player = _safe_index(args[0] if args else 1, 1)
        return values.get("player2_mode" if player == 2 else "player1_mode", 0)
    if key in ("isplayer1controlleridx", "isplayer2controlleridx"):
        return True
    mapping = {
        "setreassigningcontrollerindices": "reassigning",
        "setplayer1controllermotionenabled": "player1_motion",
        "setplayer2controllermotionenabled": "player2_motion",
        "setplayer1controllermode": "player1_mode",
        "setplayer2controllermode": "player2_mode",
    }
    if key in mapping:
        values[mapping[key]] = _json_safe(args[-1] if args else True)
        if key.endswith("mode"):
            values["dynamic_mode"] = True
        return True
    if key == "startcontrollerswap":
        values["swap_active"] = True
        return True
    if key == "stopcontrollerswap":
        values["swap_active"] = False
        return True
    if key == "setmodeandcontrollers":
        values["dynamic_mode"] = True
        return True
    if key == "enteredmodeselectscreen":
        values["mode_screen_entered"] = True
        return True
    return _UNDEFINED


def _save_handler(context, name, args):
    key = compact_name(name)
    values = _callback_state(context.movie)["save"]
    slot = _safe_index(args[0] if args else values.get("selected_slot", 0), values.get("selected_slot", 0))
    slots = values["slots"]
    if key == "newsavegame":
        funky = bool(args[1]) if len(args) > 1 else False
        slots[slot] = {
            "slot": slot, "funky_mode": funky, "mock_values": _mock_snapshot(context.movie),
            "created_in_preview": True,
        }
        values["selected_slot"] = slot
        values["funky_mode"] = funky
        return True
    if key == "selectsavegame":
        values["selected_slot"] = slot
        slots.setdefault(slot, {"slot": slot, "mock_values": _mock_snapshot(context.movie)})
        return True
    if key == "copysavegame":
        source = _safe_index(args[0] if args else 0)
        target = _safe_index(args[1] if len(args) > 1 else source + 1)
        slots[target] = dict(slots.get(source, {"slot": source, "mock_values": _mock_snapshot(context.movie)}))
        slots[target]["slot"] = target
        slots[target]["copied_from"] = source
        return True
    if key == "deletesavegame":
        slots.pop(slot, None)
        return True
    if key in ("populatesavedata", "initslotdata"):
        for index in range(3):
            slots.setdefault(index, {"slot": index, "empty": True})
        return [dict(slots[index]) for index in sorted(slots)]
    if key == "setisfunkymode":
        values["funky_mode"] = bool(args[-1]) if args else True
        return True
    if key == "setballooncount":
        values["balloon_count"] = _safe_index(args[0] if args else 0)
        return True
    if key == "setcurrentworld":
        values["current_world"] = _json_safe(args[0] if args else None)
        return True
    if key.startswith("set"):
        values["flags"][str(name)] = _json_safe(args[-1] if args else True)
        return True
    return _UNDEFINED


def _shop_handler(context, name, args):
    key = compact_name(name)
    values = _callback_state(context.movie)["shop"]
    if key in ("getshoptext", "getuitext"):
        text_key = str(args[-1]) if args else ""
        texts = getattr(context.movie, "ui_native_text_values", {}) or {}
        return str(texts.get(text_key, ""))
    if key == "selectshopitem":
        values["selected_item"] = _json_safe(args[0] if args else None)
        return True
    if key == "purchaseshopitem":
        purchase = {"arguments": _json_safe(args), "mock_values": _mock_snapshot(context.movie)}
        _bounded_append(values["purchases"], purchase, 128)
        return True
    if key == "getfigurinestatus":
        return int(values.get("figurine_status", 0))
    if key == "getnewfigurine":
        return int(values.get("new_figurine", -1))
    if key == "ishealthboostactive":
        return bool(values.get("health_boost", False))
    if key == "shopevent":
        _bounded_append(values.setdefault("events", []), _json_safe(args), 128)
        return True
    return _UNDEFINED


def _extras_handler(context, name, args):
    key = compact_name(name)
    values = _callback_state(context.movie)["extras"]
    item_key = str(args[-1]) if args else ""
    if key == "getextrasunlockstate":
        return bool(values.get("unlocked", True))
    if key == "getextrascategoryunlocked":
        return bool(values.get("category_unlocked", True))
    if key == "getisnewextraitem":
        return bool(values["new_items"].get(item_key, False))
    if key == "clearisnewextraitem":
        values["new_items"][item_key] = False
        return True
    if key == "getisnewextracategory":
        return bool(values["new_categories"].get(item_key, False))
    if key == "clearisnewextracategory":
        values["new_categories"][item_key] = False
        return True
    if key == "isunitloaded":
        return bool(values.setdefault("loaded_units", {}).get(item_key, True))
    if key in ("startload", "startunload"):
        values.setdefault("loads", []).append({"operation": key, "arguments": _json_safe(args)})
        return True
    if key.startswith("start"):
        values["active"][key[5:] or "extras"] = _json_safe(args) or True
        return True
    if key.startswith("stop"):
        values["active"].pop(key[4:] or "extras", None)
        return True
    if key in ("chooseextrasimage", "playcreditssequence"):
        values["last_action"] = {"name": str(name), "arguments": _json_safe(args)}
        return True
    return _UNDEFINED


def _leaderboard_handler(context, name, args):
    key = compact_name(name)
    values = _callback_state(context.movie)["leaderboard"]
    if key in ("isinleaderboardreplay", "isinleaderboardreplay"):
        return bool(values.get("replay", False))
    if key in ("fillleaderboard", "startfillingleaderboard"):
        count = _safe_index(args[0] if args else 8, 8)
        if not values["entries"]:
            values["entries"] = [
                {"rank": index + 1, "name": f"CPU {index + 1}", "score": max(0, 100000 - index * 5000)}
                for index in range(min(count, 32))
            ]
        return list(values["entries"])
    if key == "createleaderboardentry":
        entry = {"arguments": _json_safe(args)}
        values["entries"].append(entry)
        return entry
    if key == "cancelqueries":
        values["queries"].clear()
        return True
    if key in ("fetchreplay", "inittransitiontoreplay"):
        values["replay"] = True
        return True
    if key.startswith(("post", "internet", "set")):
        _bounded_append(values["queries"], {"name": str(name), "arguments": _json_safe(args)}, 128)
        return True
    return _UNDEFINED


def _navigation_handler(context, name, args):
    state = _callback_state(context.movie)
    transition = state["transition"]
    key = compact_name(name)
    record = {
        "name": str(name), "arguments": _json_safe(args), "path": context.path,
        "time_ms": _runtime_time(context.movie),
    }
    _bounded_append(state["navigation"], record)
    if key == "preparefortransition":
        transition["prepared"] = True
    elif key == "transitionstate":
        transition_name = str(args[0]) if args else ""
        transition_value = _json_safe(args[1] if len(args) > 1 else None)
        transition["states"][transition_name] = transition_value
        transition["current"] = transition_name
    else:
        transition["current"] = str(name)
        transition["arguments"] = _json_safe(args)
    return True


def _lifecycle_handler(context, name, args):
    key = compact_name(name)
    values = _callback_state(context.movie)["lifecycle"]
    if key == "areswfsloaded":
        return True
    if key == "shouldprompt":
        return bool(values.get("should_prompt", False))
    if key == "showprompt":
        values["prompt_visible"] = True
        return True
    if key == "hideprompt":
        values["prompt_visible"] = False
        return True
    values[str(name)] = _json_safe(args) if args else True
    return True


def _gameplay_handler(context, name, args):
    values = _callback_state(context.movie)["gameplay_events"]
    _bounded_append(values, {
        "name": str(name), "arguments": _json_safe(args), "path": context.path,
        "time_ms": _runtime_time(context.movie),
    })
    return True


def _policy_default(spec):
    if spec.return_policy == "true":
        return True
    if spec.return_policy == "false":
        return False
    if spec.return_policy == "zero":
        return 0
    if spec.return_policy == "empty-string":
        return ""
    return _UNDEFINED


def _simulate_callback(context, name, args, spec):
    if spec.category in ("data-read", "data-write", "data-listen"):
        return _data_handler(context, name, args, spec)
    if spec.category == "audio":
        return _audio_handler(context, name, args)
    if spec.category == "telemetry":
        return _telemetry_handler(context, name, args)
    if spec.category == "controller":
        result = _controller_handler(context, name, args)
    elif spec.category == "save/profile":
        result = _save_handler(context, name, args)
    elif spec.category == "shop":
        result = _shop_handler(context, name, args)
    elif spec.category == "extras":
        result = _extras_handler(context, name, args)
    elif spec.category == "leaderboard":
        result = _leaderboard_handler(context, name, args)
    elif spec.category == "navigation":
        result = _navigation_handler(context, name, args)
    elif spec.category == "lifecycle":
        result = _lifecycle_handler(context, name, args)
    elif spec.category == "gameplay-event":
        result = _gameplay_handler(context, name, args)
    else:
        result = _UNDEFINED
    return _policy_default(spec) if result is _UNDEFINED else result


def native_call(context, name, args):
    attach_native_callback_inventory(context.movie)
    _ensure_config(context.movie)
    spec = callback_spec(name)
    base_result = _base_data_call(context, name, args)
    overridden, override_value = _find_override(context.movie, name)
    if overridden:
        result, source = _json_safe(override_value), "Native-Override"
    elif base_result is not _UNDEFINED:
        result, source = base_result, "Basis/Registry"
    elif getattr(context.movie, "ui_native_callback_mode", "simulate") == "simulate":
        result = _simulate_callback(context, name, tuple(args), spec)
        source = f"DKCTF-Simulation:{spec.category}" if result is not _UNDEFINED else "Nicht implementiert"
    else:
        result, source = _UNDEFINED, "Nur beobachtet"
    return _record_callback(context, str(name), tuple(args), spec, source, result)


def normalize_native_callback_config(value):
    value = value if isinstance(value, dict) else {}
    mode = str(value.get("mode", "simulate") or "simulate")
    if mode not in ("simulate", "observe"):
        mode = "simulate"
    overrides = {}
    raw = value.get("overrides", {})
    if isinstance(raw, dict):
        for index, (name, item) in enumerate(raw.items()):
            if index >= _MAX_OVERRIDES:
                break
            name = str(name).strip()
            if name:
                overrides[name] = _json_safe(item)
    return {"mode": mode, "overrides": overrides}


def current_native_callback_config(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return {"mode": "simulate", "overrides": {}}
    _ensure_config(movie)
    return normalize_native_callback_config({
        "mode": movie.ui_native_callback_mode,
        "overrides": movie.ui_native_callback_overrides,
    })


def apply_native_callback_config(owner, value):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    clean = normalize_native_callback_config(value)
    movie.ui_native_callback_mode = clean["mode"]
    movie.ui_native_callback_overrides = dict(clean["overrides"])
    runtime._touch(movie)
    variable = getattr(owner, "native_callback_mode_var", None)
    if variable is not None:
        variable.set("Sicher simulieren" if clean["mode"] == "simulate" else "Nur beobachten")
    window = getattr(owner, "_native_callback_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.refresh()
    except Exception:
        pass


def make_preset(owner):
    result = _BASE["make_preset"](owner)
    result["native_callbacks"] = current_native_callback_config(owner)
    return result


def normalize_preset(data):
    result = _BASE["normalize_preset"](data)
    result["native_callbacks"] = normalize_native_callback_config(
        data.get("native_callbacks", {}) if isinstance(data, dict) else {}
    )
    return result


def load_preset(window):
    path = filedialog.askopenfilename(
        parent=window, title="UI-State-Preset laden",
        filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
    )
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            preset = normalize_preset(json.load(handle))
    except Exception as exc:
        messagebox.showerror("UI-Preset", str(exc), parent=window)
        return
    current = make_preset(window.owner)
    if preset.get("movie") and current.get("movie") and preset["movie"] != current["movie"]:
        messagebox.showwarning(
            "UI-Preset",
            f"Preset gehört zu {preset['movie']}, aktuell geöffnet ist {current['movie']}. "
            "Die Pfade werden trotzdem geladen.", parent=window,
        )
    overrides = window.owner._ui_state_overrides
    overrides.clear()
    overrides.update(preset["overrides"])
    movie = getattr(window.owner, "_current_movie", None)
    if movie is not None:
        timeline_core.set_root_frame(
            window.owner, min(int(movie.frame_count), int(preset["root_frame"])),
        )
    timeline_browser.apply_loaded_playback(window.owner, preset["playback"])
    if game_state is not None:
        game_state.apply_game_state_data(window.owner, preset["game_state"])
    apply_native_callback_config(window.owner, preset["native_callbacks"])
    override_patch._invalidate_overrides(window.owner)
    window.override_status_var.set(f"Preset geladen: {Path(path).name}")
    window.refresh()


def native_callback_inventory(movie, include_sites=True):
    attach_native_callback_inventory(movie)
    summaries = []
    for summary in getattr(movie, "ui_native_callback_summaries", ()):
        item = {
            "name": summary.name,
            "category": summary.category,
            "behavior": summary.behavior,
            "return_policy": summary.return_policy,
            "implemented": summary.implemented,
            "count": summary.count,
            "bridges": list(summary.bridges),
            "argument_samples": _json_safe(summary.argument_samples),
        }
        if include_sites:
            item["sites"] = [
                {
                    "module": site.module, "source": site.source,
                    "class": site.class_name, "method": site.method_name,
                    "method_index": site.method_index, "offset": site.offset,
                    "bridge": site.bridge, "arguments": _json_safe(site.arguments),
                    "dynamic_name": site.dynamic_name,
                }
                for site in summary.sites
            ]
        summaries.append(item)
    state = _callback_state(movie)
    return {
        "schema": 1,
        "mode": getattr(movie, "ui_native_callback_mode", "simulate"),
        "overrides": _json_safe(getattr(movie, "ui_native_callback_overrides", {})),
        "summary": {
            "callbacks": len(summaries),
            "call_sites": len(getattr(movie, "ui_native_callback_sites", ())),
            "implemented_callbacks": sum(1 for item in summaries if item["implemented"]),
            "runtime_calls": len(state["calls"]),
            "unknown_runtime_calls": len(state["unknown"]),
        },
        "callbacks": summaries,
        "runtime": _json_safe(state),
        "preview_data": [
            {"dictionary": str(key[0]), "field": str(key[1]), "value": _json_safe(value)}
            for key, value in _native_data(movie).items()
            if isinstance(key, tuple) and len(key) == 2
        ],
    }


class NativeCallbackInspectorWindow(tk.Toplevel):
    MODE_LABELS = {"Sicher simulieren": "simulate", "Nur beobachten": "observe"}

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI Native Callbacks")
        self.geometry("1320x850")
        self.minsize(980, 620)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._items = {}
        self._selected_callback = ""

        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="DKCTF-Callback-Inventar und sichere Vorschauimplementierungen").pack(side="left")
        ttk.Button(toolbar, text="JSON speichern", command=self.save_json).pack(side="right")
        ttk.Button(toolbar, text="Aktualisieren", command=self.refresh).pack(side="right", padx=(0, 6))
        ttk.Label(toolbar, text="Modus:").pack(side="left", padx=(18, 4))
        self.mode_var = tk.StringVar(value="Sicher simulieren")
        mode = ttk.Combobox(
            toolbar, textvariable=self.mode_var,
            values=tuple(self.MODE_LABELS), state="readonly", width=18,
        )
        mode.pack(side="left")
        mode.bind("<<ComboboxSelected>>", self.change_mode)

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(pane)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        pane.add(left, weight=0)

        right = ttk.Frame(pane)
        self.details = tk.Text(right, wrap="none", state="disabled")
        self.details.pack(side="left", fill="both", expand=True)
        yscroll = ttk.Scrollbar(right, orient="vertical", command=self.details.yview)
        yscroll.pack(side="right", fill="y")
        xscroll = ttk.Scrollbar(right, orient="horizontal", command=self.details.xview)
        xscroll.pack(side="bottom", fill="x")
        self.details.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        pane.add(right, weight=1)

        override_bar = ttk.Frame(self, padding=(8, 0, 8, 6))
        override_bar.pack(fill="x")
        ttk.Label(override_bar, text="Rückgabe-Override (JSON):").pack(side="left")
        self.override_var = tk.StringVar()
        ttk.Entry(override_bar, textvariable=self.override_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(override_bar, text="Setzen", command=self.set_override).pack(side="left")
        ttk.Button(override_bar, text="Löschen", command=self.clear_override).pack(side="left", padx=(5, 0))

        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        self.refresh()

    def _set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _movie(self):
        return getattr(self.owner, "_current_movie", None)

    def refresh(self):
        movie = self._movie()
        self.tree.delete(*self.tree.get_children())
        self._items.clear()
        self._selected_callback = ""
        if movie is None:
            self._set_details("Kein UI-Film ausgewählt.")
            self.status_var.set("Keine Callback-Daten")
            return
        attach_native_callback_inventory(movie)
        _ensure_config(movie)
        self.mode_var.set("Sicher simulieren" if movie.ui_native_callback_mode == "simulate" else "Nur beobachten")
        root = self.tree.insert("", "end", text="Native Callbacks", open=True)
        self._items[root] = ("summary", movie)
        by_category = defaultdict(list)
        for summary in movie.ui_native_callback_summaries:
            by_category[summary.category].append(summary)
        for category in KNOWN_CATEGORIES:
            values = by_category.get(category, ())
            if not values:
                continue
            category_iid = self.tree.insert(root, "end", text=f"{category} ({len(values)})", open=category != "unknown")
            self._items[category_iid] = ("category", category, tuple(values))
            for summary in values:
                marker = "✓" if summary.implemented else "·"
                iid = self.tree.insert(category_iid, "end", text=f"{marker} {summary.name} ({summary.count})")
                self._items[iid] = ("callback", summary)
                for site in summary.sites:
                    site_iid = self.tree.insert(
                        iid, "end", text=f"{site.class_name}.{site.method_name} @ {site.offset:04X}",
                    )
                    self._items[site_iid] = ("site", site)
        self.tree.selection_set(root)
        self.on_select()
        state = _callback_state(movie)
        self.status_var.set(
            f"{len(movie.ui_native_callback_summaries)} Namen | "
            f"{len(movie.ui_native_callback_sites)} statische Call-Sites | "
            f"{len(state['calls'])} Runtime-Aufrufe | {len(state['unknown'])} unbekannt"
        )

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        item = self._items.get(selection[0])
        if item is None:
            return
        movie = self._movie()
        kind = item[0]
        self._selected_callback = ""
        self.override_var.set("")
        if kind == "summary":
            snapshot = native_callback_inventory(movie, include_sites=False)
            self._set_details(json.dumps(snapshot, ensure_ascii=False, indent=2))
        elif kind == "category":
            category, values = item[1], item[2]
            self._set_details(
                f"Kategorie: {category}\nCallbacks: {len(values)}\nCall-Sites: {sum(value.count for value in values)}\n\n" +
                "\n".join(f"- {value.name}: {value.count}" for value in values)
            )
        elif kind == "callback":
            summary = item[1]
            self._selected_callback = summary.name
            override = next((
                value for key, value in movie.ui_native_callback_overrides.items()
                if compact_name(key) == compact_name(summary.name)
            ), _UNDEFINED)
            if override is not _UNDEFINED:
                self.override_var.set(json.dumps(_json_safe(override), ensure_ascii=False))
            runtime_count = _callback_state(movie)["counts"].get(summary.name, 0)
            lines = [
                f"Callback: {summary.name}",
                f"Kategorie: {summary.category}",
                f"Verhalten: {summary.behavior}",
                f"Standard-Rückgabe: {summary.return_policy}",
                f"Sicher implementiert: {'ja' if summary.implemented else 'nein'}",
                f"Statische Call-Sites: {summary.count}",
                f"Runtime-Aufrufe: {runtime_count}",
                f"Brücken: {', '.join(summary.bridges)}", "",
                callback_spec(summary.name).description, "", "Argumentbeispiele:",
            ]
            lines.extend(f"- {json.dumps(_json_safe(value), ensure_ascii=False)}" for value in summary.argument_samples)
            self._set_details("\n".join(lines))
        elif kind == "site":
            site = item[1]
            self._selected_callback = site.callback
            self._set_details(
                f"Callback: {site.callback}\nKategorie: {site.category}\nBrücke: {site.bridge}\n"
                f"Modul: {site.module}\nQuelle: {site.source}\nKlasse: {site.class_name}\n"
                f"Methode: {site.method_name} (Index {site.method_index})\n"
                f"Bytecode-Offset: 0x{site.offset:04X}\nDynamischer Name: {'ja' if site.dynamic_name else 'nein'}\n\n"
                f"Argumente:\n{json.dumps(_json_safe(site.arguments), ensure_ascii=False, indent=2)}"
            )

    def change_mode(self, _event=None):
        movie = self._movie()
        if movie is None:
            return
        movie.ui_native_callback_mode = self.MODE_LABELS.get(self.mode_var.get(), "simulate")
        variable = getattr(self.owner, "native_callback_mode_var", None)
        if variable is not None:
            variable.set(self.mode_var.get())
        runtime._touch(movie)
        self.owner.request_render()

    def set_override(self):
        movie = self._movie()
        if movie is None or not self._selected_callback:
            return
        try:
            value = json.loads(self.override_var.get())
        except Exception as exc:
            messagebox.showerror("Native Callback", f"Ungültiges JSON: {exc}", parent=self)
            return
        movie.ui_native_callback_overrides[self._selected_callback] = _json_safe(value)
        runtime._touch(movie)
        self.status_var.set(f"Override gesetzt: {self._selected_callback}")
        self.owner.request_render()
        self.on_select()

    def clear_override(self):
        movie = self._movie()
        if movie is None or not self._selected_callback:
            return
        wanted = compact_name(self._selected_callback)
        for key in tuple(movie.ui_native_callback_overrides):
            if compact_name(key) == wanted:
                movie.ui_native_callback_overrides.pop(key, None)
        runtime._touch(movie)
        self.override_var.set("")
        self.status_var.set(f"Override gelöscht: {self._selected_callback}")
        self.owner.request_render()
        self.on_select()

    def save_json(self):
        movie = self._movie()
        if movie is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Native-Callback-Inventar speichern",
            defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(native_callback_inventory(movie), handle, ensure_ascii=False, indent=2)

    def close(self):
        self.owner._native_callback_window = None
        self.destroy()


def show_native_callback_inspector(owner):
    window = getattr(owner, "_native_callback_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh()
            return window
    except Exception:
        pass
    owner._native_callback_window = NativeCallbackInspectorWindow(owner)
    return owner._native_callback_window


def _mode_changed(owner, _event=None):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    label = owner.native_callback_mode_var.get()
    movie.ui_native_callback_mode = "observe" if label == "Nur beobachten" else "simulate"
    runtime._touch(movie)
    owner.request_render()


def browser_init(owner, *args, **kwargs):
    _BASE["browser_init"](owner, *args, **kwargs)
    owner._native_callback_window = None
    owner.native_callback_mode_var = tk.StringVar(value="Sicher simulieren")
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Button(
        bar, text="Native Callbacks", command=lambda: show_native_callback_inspector(owner),
    ).pack(side="left")
    ttk.Label(bar, text="F11 öffnet Inventar, Runtime-Zustand und Rückgabe-Overrides").pack(side="left", padx=(10, 0))
    ttk.Label(bar, text="Modus:").pack(side="right", padx=(8, 4))
    mode = ttk.Combobox(
        bar, textvariable=owner.native_callback_mode_var,
        values=("Sicher simulieren", "Nur beobachten"), state="readonly", width=18,
    )
    mode.pack(side="right")
    mode.bind("<<ComboboxSelected>>", lambda event: _mode_changed(owner, event))
    owner.bind("<F11>", lambda _event: show_native_callback_inspector(owner))


def browser_select(owner, event=None):
    result = _BASE["select"](owner, event)
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        attach_native_callback_inventory(movie)
        _ensure_config(movie)
        owner.native_callback_mode_var.set(
            "Sicher simulieren" if movie.ui_native_callback_mode == "simulate" else "Nur beobachten"
        )
    window = getattr(owner, "_native_callback_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.refresh()
    except Exception:
        pass
    return result


def browser_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    attach_native_callback_inventory(movie)
    summaries = tuple(getattr(movie, "ui_native_callback_summaries", ()))
    if not summaries:
        return text + "\n\nNative Callbacks:\n- Keine Brückenaufrufe erkannt"
    state = _callback_state(movie)
    implemented = sum(1 for item in summaries if item.implemented)
    return text + "\n\nNative Callbacks:\n" + (
        f"- Modus: {'sicher simulieren' if movie.ui_native_callback_mode == 'simulate' else 'nur beobachten'}\n"
        f"- Namen / Call-Sites: {len(summaries)} / {len(movie.ui_native_callback_sites)}\n"
        f"- Sicher klassifiziert: {implemented}\n"
        f"- Runtime-Aufrufe: {len(state['calls'])}\n"
        f"- Unbekannte Runtime-Aufrufe: {len(state['unknown'])}\n"
        f"- Audio / Navigation / Telemetrie: {len(state['audio_requests'])} / {len(state['navigation'])} / {len(state['telemetry'])}\n"
        f"- Rückgabe-Overrides: {len(movie.ui_native_callback_overrides)}"
    )


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_native_callback_state = None
    return _BASE["reset"](owner)


def browser_close(owner):
    window = getattr(owner, "_native_callback_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE["close"](owner)


def attach_avm2_inventory(movie):
    result = _BASE["attach"](movie)
    return attach_native_callback_inventory(result)


def parse_swf_movie(raw):
    movie = _BASE["parse"](raw)
    return attach_native_callback_inventory(movie)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        native=runtime._native,
        attach=avm2.attach_avm2_inventory,
        parse=ui_browser.parse_swf_movie,
        browser_init=ui_browser.UIBrowser.__init__,
        select=ui_browser.UIBrowser._on_tree_select,
        info=ui_browser.UIBrowser._format_info,
        close=ui_browser.UIBrowser.close,
        reset=runtime.reset_runtime,
        make_preset=override_patch.make_preset,
        normalize_preset=override_patch.normalize_preset,
    )

    runtime._native = native_call
    avm2.attach_avm2_inventory = attach_avm2_inventory
    ui_browser.parse_swf_movie = parse_swf_movie
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = browser_select
    ui_browser.UIBrowser._format_info = browser_info
    ui_browser.UIBrowser.close = browser_close
    runtime.reset_runtime = reset_runtime
    try:
        import ui_browser_avm2_lifecycle_patch as lifecycle
        lifecycle.reset_runtime = reset_runtime
    except Exception:
        pass
    ui_browser.UIBrowser.reset_avm2_runtime = reset_runtime
    ui_browser.UIBrowser.show_native_callbacks = show_native_callback_inspector

    override_patch.make_preset = make_preset
    override_patch.normalize_preset = normalize_preset
    timeline_core.make_preset_with_playback = make_preset
    timeline_core.normalize_preset_with_playback = normalize_preset
    ui_browser.make_ui_state_preset = make_preset
    ui_browser.normalize_ui_state_preset = normalize_preset
    if game_state is not None:
        game_state.make_preset = make_preset
        game_state.normalize_preset = normalize_preset
        game_state.load_preset = load_preset
    timeline_inspector.load_preset = load_preset
    state_inspector.StateInspectorWindow.load_override_preset = load_preset

    ui_browser.NativeCallbackSite = NativeCallbackSite
    ui_browser.NativeCallbackSummary = NativeCallbackSummary
    ui_browser.classify_ui_native_callback = callback_spec
    ui_browser.attach_ui_native_callback_inventory = attach_native_callback_inventory
    ui_browser.ui_native_callback_inventory = native_callback_inventory
    ui_browser.normalize_ui_native_callback_config = normalize_native_callback_config
    ui_browser.apply_ui_native_callback_config = apply_native_callback_config
