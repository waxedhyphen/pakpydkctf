"""Deterministic native completion queue layered on the AVM2 timeline clock."""
from __future__ import annotations

import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_native_callback_patch as native
from ui_audio_codec import decode_csmp_pcm
from ui_browser_native_callback_catalog import callback_spec, compact_name
import ui_browser_audio_preview as audio

try:
    import ui_browser_avm2_dynamic_patch as dynamic
except Exception:
    dynamic = None

_MAX_PENDING = 256
_MAX_COMPLETIONS_PER_TICK = 32
_MAX_COMPLETED = 500
_BASE_NATIVE = None
_BASE_CLOCK = None
_BASE_RESET = None


def set_preview_data(movie, dictionary, field_name, value):
    clean = native._json_safe(value)
    native._native_data(movie)[(str(dictionary), str(field_name))] = clean
    native._callback_state(movie)["dictionaries"].setdefault(str(dictionary), {})[
        str(field_name)
    ] = clean


def queue_completion(movie, callback, args=(), result=None, path="root", delay_ms=0.0,
                     events=(), data_updates=(), kind="completion"):
    state = audio.async_audio_state(movie)
    if len(state["pending"]) >= _MAX_PENDING:
        state["pending"].pop(0)
    request_id = int(state["next_id"])
    state["next_id"] = request_id + 1
    item = {
        "id": request_id, "kind": str(kind), "callback": str(callback),
        "arguments": native._json_safe(args), "result": native._json_safe(result),
        "path": str(path or "root"), "queued_ms": native._runtime_time(movie),
        "due_ms": native._runtime_time(movie) + max(0.0, float(delay_ms)),
        "events": [str(value) for value in events if value],
        "data_updates": [
            {"dictionary": str(dictionary), "field": str(field),
             "value": native._json_safe(value)}
            for dictionary, field, value in data_updates
        ],
    }
    state["pending"].append(item)
    state["queued"] += 1
    return request_id


def _dispatch(movie, item, event_type, data=None):
    delivered = 0
    extra = {
        "requestId": item["id"], "callback": item["callback"], "success": True,
        "arguments": item["arguments"], "result": item["result"],
        "source": "native-preview",
    }
    if item.get("data_updates"):
        extra["dataUpdates"] = item["data_updates"]
    for key in (("global", "Controller.mEventDispatcher"), ("global", "Controller")):
        event = lifecycle.RuntimeEvent(str(event_type), bubbles=False, data=data)
        event.extra.update(extra)
        delivered += lifecycle._dispatch_key(movie, key, event)
    if dynamic is not None:
        try:
            event = lifecycle.RuntimeEvent(str(event_type), bubbles=True, data=data)
            event.extra.update(extra)
            delivered += dynamic._dispatch_path(
                movie, item.get("path") or "root", event, True,
            )
        except Exception:
            pass
    return delivered


def process_async_queue(owner, complete_all=False):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return 0
    state = audio.async_audio_state(movie)
    now = native._runtime_time(movie)
    pending = sorted(state["pending"], key=lambda item: (item["due_ms"], item["id"]))
    due = pending if complete_all else [item for item in pending if item["due_ms"] <= now]
    due = due[:_MAX_PENDING if complete_all else _MAX_COMPLETIONS_PER_TICK]
    if not due:
        return 0
    due_ids = {item["id"] for item in due}
    state["pending"] = [item for item in state["pending"] if item["id"] not in due_ids]
    delivered = 0
    for source_item in due:
        event_data = source_item.get("result")
        for update in source_item.get("data_updates", ()):
            set_preview_data(movie, update["dictionary"], update["field"], update["value"])
            event_data = update["value"]
        item_delivered = sum(
            _dispatch(movie, source_item, event_type, event_data)
            for event_type in source_item.get("events", ())
        )
        delivered += item_delivered
        item = dict(source_item)
        item["completed_ms"] = now
        item["listeners"] = item_delivered
        native._bounded_append(state["completed"], item, _MAX_COMPLETED)
    state["dispatched"] += delivered
    runtime._touch(movie)
    try:
        owner.request_render()
    except Exception:
        pass
    return len(due)


def _last_source(movie):
    calls = native._callback_state(movie).get("calls", ())
    item = calls[-1] if calls else None
    return str(item.get("source", "")) if isinstance(item, dict) else ""


def _queue_data_notification(context, name, args, result):
    dictionary, field_name = native._data_address(args)
    if not field_name and compact_name(name) == "notifydatavalue" and len(args) >= 2:
        field_name = str(args[-2])
    if not field_name:
        return
    value = args[-1] if args else result
    queue_completion(
        context.movie, name, args, value, context.path, 0.0,
        (field_name, "dataValueChanged"),
        ((dictionary or "mRuntimeData", field_name, value),),
        "data-notification",
    )
    audio.async_audio_state(context.movie)["data_notifications"] += 1


def _schedule_completion(context, name, args, result, spec):
    movie = context.movie
    key = compact_name(name)
    if spec.category == "save/profile":
        set_preview_data(movie, "mRuntimeData", "SaveBusy", True)
        queue_completion(
            movie, name, args, True, context.path, 0.0, ("SaveBusy",),
            (("mRuntimeData", "SaveBusy", True),), "data-notification",
        )
        queue_completion(
            movie, name, args, result, context.path, 120.0,
            (f"{name}Complete", "SaveBusy", "isSaveDataPopulated", "nativeComplete"),
            (("mRuntimeData", "SaveBusy", False),
             ("mRuntimeData", "isSaveDataPopulated", True)),
        )
    elif spec.category == "leaderboard":
        queue_completion(
            movie, name, args, result, context.path, 180.0,
            (f"{name}Complete", "LeaderboardComplete", "nativeComplete"),
        )
    elif spec.category == "navigation":
        set_preview_data(movie, "mRuntimeData", "isLoadingIn", True)
        queue_completion(
            movie, name, args, result, context.path, 80.0,
            (f"{name}Complete", "TransitionComplete", "isLoadingIn", "nativeComplete"),
            (("mRuntimeData", "isLoadingIn", False),),
        )
    elif spec.category == "extras" and key in ("startload", "startunload"):
        queue_completion(
            movie, name, args, result, context.path, 120.0,
            (f"{name}Complete", "UnitLoadComplete", "nativeComplete"),
        )


def _post_audio(context, name, args):
    movie = context.movie
    owner = (
        getattr(movie, "_ui_audio_owner", None)
        or getattr(movie, "_ui_avm2_runtime_owner", None)
    )
    if owner is None:
        return
    audio.attach_audio_catalog(owner, movie)
    requests = native._callback_state(movie)["audio_requests"]
    if not requests:
        return
    request = requests[-1]
    sound = audio.sound_name(movie, args, request.get("sound", ""))
    request["sound"] = sound
    record = audio.resolve_sound(movie, sound)
    state = audio.async_audio_state(movie)
    state["last_sound"] = sound
    if record is None:
        request["resolved"] = False
        state["unresolved_audio"] += 1
        return
    request.update({
        "resolved": True, "caud_uuid": record.caud_uuid,
        "source": record.source_label, "csmp_refs": list(record.csmp_refs),
        "loop": record.loop,
    })
    state["resolved_audio"] += 1
    config = audio.ensure_audio_config(movie)
    if config["enabled"] and not config["muted"]:
        audio.play_sound(owner, record)
    try:
        _ref, asset = audio.find_csmp(owner, record, 0)
        _channels, info = decode_csmp_pcm(asset)
        if not record.loop:
            queue_completion(
                movie, name, args, True, context.path,
                info.duration_seconds * 1000.0,
                ("soundComplete", f"{sound}Complete"), kind="audio-completion",
            )
    except Exception as exc:
        native._bounded_append(state["decode_errors"], {
            "sound": sound, "error": str(exc), "time_ms": native._runtime_time(movie),
        }, 100)


def native_call(context, name, args):
    result = _BASE_NATIVE(context, name, args)
    if _last_source(context.movie) in ("Native-Override", "Nur beobachtet"):
        return result
    spec = callback_spec(name)
    key = compact_name(name)
    if key in {
        "setdatavalue", "fsetdatavalue", "writedatavalue", "initdatavalue",
        "finitdatavalue", "notifydatavalue",
    }:
        _queue_data_notification(context, name, tuple(args), result)
    _schedule_completion(context, name, tuple(args), result, spec)
    if spec.category == "audio":
        _post_audio(context, name, tuple(args))
    return result


def advance_runtime_clock(owner, milliseconds):
    return _BASE_CLOCK(owner, milliseconds) + process_async_queue(owner)


def reset_runtime(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_async_audio_state = None
    audio.stop_audio(owner)
    return _BASE_RESET(owner)


def install_hooks(base_native, base_clock, base_reset):
    global _BASE_NATIVE, _BASE_CLOCK, _BASE_RESET
    _BASE_NATIVE, _BASE_CLOCK, _BASE_RESET = base_native, base_clock, base_reset
    runtime._native = native_call
    lifecycle.advance_runtime_clock = advance_runtime_clock
    runtime.reset_runtime = reset_runtime
    lifecycle.reset_runtime = reset_runtime
