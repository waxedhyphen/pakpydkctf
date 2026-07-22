"""Commit timeline changes made by AVM2 event handlers on nested MovieClips."""
from __future__ import annotations

import ui_browser_avm2_lifecycle_patch as lifecycle

_INSTALLED = False
_BASE_INVOKE = None


def invoke(movie, listener, event, arguments=None):
    context = _BASE_INVOKE(movie, listener, event, arguments)
    if listener.path != "root":
        state = (getattr(movie, "ui_timeline_states", {}) or {}).get(listener.path)
        if isinstance(state, dict):
            state["frame"] = max(1, min(context.frame_count, int(context.frame)))
            state["playing"] = bool(context.playing)
            state.pop("_avm2_runtime_token", None)
    return context


def install():
    global _INSTALLED, _BASE_INVOKE
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_INVOKE = lifecycle._invoke
    lifecycle._invoke = invoke
