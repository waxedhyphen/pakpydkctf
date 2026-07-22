"""Browser playback controls and timer for root and nested UI timelines."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

import ui_browser
import ui_browser_timeline_core as core


_INSTALLED = False
_SPEED_VALUES = ("0.25×", "0.5×", "1×", "2×", "4×")
_SPEED_MAP = {"0.25×": 0.25, "0.5×": 0.5, "1×": 1.0, "2×": 2.0, "4×": 4.0}


def speed_label(speed):
    return min(_SPEED_MAP, key=lambda label: abs(_SPEED_MAP[label] - float(speed)))


def set_status(owner):
    if not hasattr(owner, "timeline_status_var"):
        return
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        owner.timeline_status_var.set("Keine Timeline")
        return
    active = len(core.sync_timeline_instances(owner))
    state = "läuft" if getattr(owner, "_ui_playback_running", False) else "pausiert"
    owner.timeline_status_var.set(
        f"{state} | {float(getattr(owner, '_ui_playback_speed', 1.0)):g}× | {active} MovieClips"
    )


def schedule_tick(owner):
    if getattr(owner, "_closed", False) or not getattr(owner, "_ui_playback_running", False):
        owner._ui_playback_after_id = None
        return
    owner._ui_playback_after_id = owner.after(16, lambda: playback_tick(owner))


def playback_tick(owner):
    owner._ui_playback_after_id = None
    if getattr(owner, "_closed", False) or not getattr(owner, "_ui_playback_running", False):
        return
    movie = getattr(owner, "_current_movie", None)
    now = time.monotonic()
    previous = float(getattr(owner, "_ui_playback_last_time", now))
    owner._ui_playback_last_time = now
    if movie is None:
        schedule_tick(owner)
        return
    elapsed = max(0.0, min(0.25, now - previous))
    fps = max(1.0, float(getattr(movie, "frame_rate", 30.0) or 30.0))
    owner._ui_playback_accumulator = float(getattr(owner, "_ui_playback_accumulator", 0.0)) + (
        elapsed * fps * float(getattr(owner, "_ui_playback_speed", 1.0))
    )
    steps = min(8, int(owner._ui_playback_accumulator))
    if steps > 0:
        owner._ui_playback_accumulator -= steps
        advance(owner, steps)
    schedule_tick(owner)


def advance(owner, steps=1, force_nested=False):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    steps = int(steps)
    active = core.sync_timeline_instances(owner)
    root_count = max(1, int(movie.frame_count))
    root_frame = int(owner.frame_var.get())
    if root_count > 1:
        core.set_root_frame(owner, ((root_frame - 1 + steps) % root_count) + 1)
    overrides = getattr(owner, "_ui_state_overrides", {})
    states = getattr(owner, "_ui_timeline_states", {})
    for path in active:
        state = states.get(path)
        if state is None or core.manual_frame_override(overrides, path) is not None:
            continue
        core.advance_timeline_instance(state, steps, force=force_nested)
    core.sync_timeline_instances(owner)
    core.request_timeline_render(owner)
    set_status(owner)


def play(owner):
    if getattr(owner, "_current_movie", None) is None:
        return
    owner._ui_playback_running = True
    owner._ui_playback_last_time = time.monotonic()
    owner._ui_playback_accumulator = 0.0
    set_status(owner)
    if getattr(owner, "_ui_playback_after_id", None) is None:
        schedule_tick(owner)


def pause(owner):
    owner._ui_playback_running = False
    after_id = getattr(owner, "_ui_playback_after_id", None)
    if after_id is not None:
        try:
            owner.after_cancel(after_id)
        except Exception:
            pass
    owner._ui_playback_after_id = None
    set_status(owner)


def toggle(owner):
    pause(owner) if getattr(owner, "_ui_playback_running", False) else play(owner)


def reset(owner):
    pause(owner)
    core.set_root_frame(owner, 1)
    for state in getattr(owner, "_ui_timeline_states", {}).values():
        state["frame"] = 1
    core.request_timeline_render(owner)
    set_status(owner)


def step(owner, delta):
    pause(owner)
    advance(owner, int(delta), force_nested=True)


def jump_root_label(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    frame = getattr(movie, "labels", {}).get(owner.timeline_root_label_var.get().strip())
    if frame is None:
        return
    pause(owner)
    core.set_root_frame(owner, frame)
    core.sync_timeline_instances(owner)
    core.request_timeline_render(owner)
    set_status(owner)


def on_speed_change(owner, *_args):
    owner._ui_playback_speed = _SPEED_MAP.get(owner.timeline_speed_var.get(), 1.0)
    set_status(owner)


def update_root_labels(owner):
    combo = getattr(owner, "timeline_root_label_combo", None)
    if combo is None:
        return
    movie = getattr(owner, "_current_movie", None)
    labels = tuple(name for name, _frame in sorted(
        getattr(movie, "labels", {}).items() if movie is not None else (),
        key=lambda item: item[1],
    ))
    combo.configure(values=labels)
    owner.timeline_root_label_var.set(labels[0] if labels else "")


def apply_loaded_playback(owner, playback):
    playback = core.normalize_playback_preset(playback)
    states = getattr(owner, "_ui_timeline_states", {})
    states.clear()
    for path, value in playback["instances"].items():
        states[path] = {
            "frame": int(value["frame"]),
            "playing": bool(value["playing"]),
            "frame_count": max(1, int(value["frame"])),
        }
    owner._ui_playback_speed = playback["speed"]
    if hasattr(owner, "timeline_speed_var"):
        owner.timeline_speed_var.set(speed_label(playback["speed"]))
    core.register_movie(getattr(owner, "_current_movie", None), states)
    core.sync_timeline_instances(owner)
    play(owner) if playback["playing"] else pause(owner)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    original_init = ui_browser.UIBrowser.__init__
    original_tree_select = ui_browser.UIBrowser._on_tree_select
    original_render = ui_browser.UIBrowser._render
    original_close = ui_browser.UIBrowser.close
    original_format_info = ui_browser.UIBrowser._format_info

    def browser_init(self, *args, **kwargs):
        self._ui_timeline_states_by_movie = {}
        self._ui_timeline_states = {}
        self._ui_current_timeline_key = ""
        self._ui_playback_running = False
        self._ui_playback_speed = 1.0
        self._ui_playback_accumulator = 0.0
        self._ui_playback_last_time = time.monotonic()
        self._ui_playback_after_id = None
        original_init(self, *args, **kwargs)

        self.timeline_speed_var = tk.StringVar(value="1×")
        self.timeline_root_label_var = tk.StringVar()
        self.timeline_status_var = tk.StringVar(value="pausiert")
        bar = ttk.Frame(self, padding=(8, 0, 8, 5))
        bar.pack(fill="x")
        ttk.Button(bar, text="▶ Play", command=lambda: play(self)).pack(side="left")
        ttk.Button(bar, text="⏸ Pause", command=lambda: pause(self)).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="−1", width=3, command=lambda: step(self, -1)).pack(side="left", padx=(10, 0))
        ttk.Button(bar, text="+1", width=3, command=lambda: step(self, 1)).pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Reset", command=lambda: reset(self)).pack(side="left", padx=(6, 0))
        ttk.Label(bar, text="Tempo:").pack(side="left", padx=(14, 4))
        ttk.Combobox(
            bar, textvariable=self.timeline_speed_var,
            values=_SPEED_VALUES, state="readonly", width=6,
        ).pack(side="left")
        self.timeline_speed_var.trace_add("write", lambda *_args: on_speed_change(self))
        ttk.Label(bar, text="Root-Label:").pack(side="left", padx=(14, 4))
        self.timeline_root_label_combo = ttk.Combobox(
            bar, textvariable=self.timeline_root_label_var, state="readonly", width=24,
        )
        self.timeline_root_label_combo.pack(side="left")
        ttk.Button(bar, text="Springen", command=lambda: jump_root_label(self)).pack(side="left", padx=(5, 0))
        ttk.Label(bar, textvariable=self.timeline_status_var).pack(side="right")
        self.bind("<F7>", lambda _event: toggle(self))
        core.attach_timeline_state(self)
        update_root_labels(self)
        set_status(self)

    def tree_select(self, event=None):
        old_key = getattr(self, "_ui_current_timeline_key", "")
        if old_key:
            self._ui_timeline_states_by_movie[old_key] = self._ui_timeline_states
        result = original_tree_select(self, event)
        core.attach_timeline_state(self)
        update_root_labels(self)
        self._ui_playback_last_time = time.monotonic()
        set_status(self)
        return result

    def browser_render(self):
        core.sync_timeline_instances(self)
        result = original_render(self)
        set_status(self)
        return result

    def browser_close(self):
        pause(self)
        return original_close(self)

    def format_info(self, stats):
        text = original_format_info(self, stats)
        if getattr(self, "_current_movie", None) is None:
            return text
        states = getattr(self, "_ui_timeline_states", {})
        active = core.sync_timeline_instances(self)
        playing = sum(1 for path in active if states.get(path, {}).get("playing", True))
        return text + "\n\nTimeline-Vorschau:\n" + (
            f"- Global: {'läuft' if self._ui_playback_running else 'pausiert'}\n"
            f"- Tempo: {self._ui_playback_speed:g}×\n"
            f"- Aktive MovieClips: {len(active)}\n"
            f"- Laufende MovieClips: {playing}"
        )

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = tree_select
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser.close = browser_close
    ui_browser.UIBrowser._format_info = format_info
    ui_browser.UIBrowser.play_ui_timelines = play
    ui_browser.UIBrowser.pause_ui_timelines = pause
    ui_browser.UIBrowser.step_ui_timelines = step
    ui_browser.UIBrowser.reset_ui_timelines = reset
