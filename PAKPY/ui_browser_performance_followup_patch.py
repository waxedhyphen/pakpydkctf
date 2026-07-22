"""Small runtime follow-up for the UI playback performance patch.

Movie registration previously walked every definition on every status/update call even
when the same state store was already attached. Pause/reset also requested an immediate
full-resolution render. Both behaviours are unnecessary and cause visible stalls.
"""
from __future__ import annotations

import inspect

import ui_browser
import ui_browser_performance_patch as performance
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core


_INSTALLED = False


def _unwrap(function, name):
    try:
        value = inspect.getclosurevars(function).nonlocals.get(name)
    except Exception:
        value = None
    return value if callable(value) else function


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_register = timeline_core.register_movie

    def register_movie(movie, states=None):
        if movie is None:
            return
        if states is None:
            states = getattr(movie, "ui_timeline_states", {})
        if getattr(movie, "_ui_registered_timeline_store", None) is states:
            movie.ui_timeline_states = states
            return
        original_register(movie, states)
        movie._ui_registered_timeline_store = states

    timeline_core.register_movie = register_movie

    base_pause = _unwrap(timeline_browser.pause, "original_pause")
    base_reset = _unwrap(timeline_browser.reset, "original_reset")

    def pause(owner):
        result = base_pause(owner)
        if not getattr(owner, "_ui_perf_step_in_progress", False):
            performance.mark_interactive(owner)
        return result

    def reset(owner):
        owner._ui_perf_step_in_progress = True
        performance.mark_interactive(owner)
        try:
            return base_reset(owner)
        finally:
            owner._ui_perf_step_in_progress = False
            performance.schedule_full_quality(owner)

    timeline_browser.pause = pause
    timeline_browser.reset = reset
    ui_browser.UIBrowser.pause_ui_timelines = pause
    ui_browser.UIBrowser.reset_ui_timelines = reset
