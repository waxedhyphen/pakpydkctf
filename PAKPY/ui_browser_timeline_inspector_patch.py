"""Per-instance MovieClip controls and playback-aware preset loading."""
from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ui_browser_state_inspector_patch as inspector
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_browser_patch as browser_patch
import ui_browser_timeline_core as core


_INSTALLED = False


def selected_movieclip(window):
    node = override_patch._selected_inspector_node(window)
    return node if node is not None and node.kind == "MovieClip" else None


def sync_controls(window):
    if not hasattr(window, "timeline_instance_frame_var"):
        return
    node = selected_movieclip(window)
    if node is None:
        window.timeline_instance_frame_var.set("-")
        window.timeline_instance_status_var.set("Kein MovieClip ausgewählt")
        window.timeline_instance_label_combo.configure(values=())
        window.timeline_instance_label_var.set("")
        return
    states = getattr(window.owner, "_ui_timeline_states", {})
    count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
    state = states.setdefault(
        node.path,
        core.normalize_timeline_instance({"frame": node.metadata.get("sprite_frame", 1)}, count),
    )
    state.update(core.normalize_timeline_instance(state, count))
    frame = int(node.metadata.get("sprite_frame", state["frame"]))
    window.timeline_instance_frame_var.set(f"{frame} / {count}")
    labels = dict(node.metadata.get("sprite_labels", {}) or {})
    ordered = tuple(name for name, _frame in sorted(labels.items(), key=lambda item: item[1]))
    window.timeline_instance_label_combo.configure(values=ordered)
    if window.timeline_instance_label_var.get() not in ordered:
        current = next((name for name, number in labels.items() if int(number) == frame), "")
        window.timeline_instance_label_var.set(current or (ordered[0] if ordered else ""))
    manual = core.manual_frame_override(getattr(window.owner, "_ui_state_overrides", {}), node.path)
    if manual is not None:
        status = f"Manueller Frame-Override {manual}; Timeline ist fixiert"
    else:
        status = f"Instanz {'läuft' if state.get('playing', True) else 'pausiert'}: {node.path}"
    window.timeline_instance_status_var.set(status)


def change_frame(window, delta):
    node = selected_movieclip(window)
    if node is None:
        return
    if core.manual_frame_override(getattr(window.owner, "_ui_state_overrides", {}), node.path) is not None:
        window.timeline_instance_status_var.set("Zuerst den manuellen MovieClip-Frame-Override löschen")
        return
    count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
    state = window.owner._ui_timeline_states.setdefault(node.path, core.normalize_timeline_instance({}, count))
    state.update(core.normalize_timeline_instance(state, count))
    core.advance_timeline_instance(state, int(delta), force=True)
    core.request_timeline_render(window.owner)
    window.refresh()


def toggle_selected(window):
    node = selected_movieclip(window)
    if node is None:
        return
    count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
    state = window.owner._ui_timeline_states.setdefault(node.path, core.normalize_timeline_instance({}, count))
    state.update(core.normalize_timeline_instance(state, count))
    state["playing"] = not state["playing"]
    sync_controls(window)


def reset_selected(window):
    node = selected_movieclip(window)
    if node is None:
        return
    count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
    state = window.owner._ui_timeline_states.setdefault(node.path, core.normalize_timeline_instance({}, count))
    state.update(core.normalize_timeline_instance(state, count))
    state["frame"] = 1
    core.request_timeline_render(window.owner)
    window.refresh()


def jump_selected_label(window):
    node = selected_movieclip(window)
    if node is None:
        return
    if core.manual_frame_override(getattr(window.owner, "_ui_state_overrides", {}), node.path) is not None:
        window.timeline_instance_status_var.set("Zuerst den manuellen MovieClip-Frame-Override löschen")
        return
    labels = dict(node.metadata.get("sprite_labels", {}) or {})
    frame = labels.get(window.timeline_instance_label_var.get())
    if frame is None:
        return
    count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
    state = window.owner._ui_timeline_states.setdefault(node.path, core.normalize_timeline_instance({}, count))
    state.update(core.normalize_timeline_instance(state, count))
    state["frame"] = max(1, min(count, int(frame)))
    core.request_timeline_render(window.owner)
    window.refresh()


def load_preset(window):
    path = filedialog.askopenfilename(
        parent=window,
        title="UI-State-Preset laden",
        filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
    )
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            preset = core.normalize_preset_with_playback(json.load(handle))
    except Exception as exc:
        messagebox.showerror("UI-Preset", str(exc), parent=window)
        return
    current = core.make_preset_with_playback(window.owner)
    if preset.get("movie") and current.get("movie") and preset["movie"] != current["movie"]:
        messagebox.showwarning(
            "UI-Preset",
            f"Preset gehört zu {preset['movie']}, aktuell geöffnet ist {current['movie']}. "
            "Die Pfade werden trotzdem geladen.",
            parent=window,
        )
    overrides = window.owner._ui_state_overrides
    overrides.clear()
    overrides.update(preset["overrides"])
    movie = getattr(window.owner, "_current_movie", None)
    if movie is not None:
        core.set_root_frame(window.owner, min(int(movie.frame_count), int(preset["root_frame"])))
    browser_patch.apply_loaded_playback(window.owner, preset["playback"])
    override_patch._invalidate_overrides(window.owner)
    window.override_status_var.set(f"Preset geladen: {Path(path).name}")
    window.refresh()


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    cls = inspector.StateInspectorWindow
    original_init = cls.__init__
    original_select = cls._on_select
    original_refresh = cls.refresh

    def window_init(self, owner):
        original_init(self, owner)
        self.geometry("1220x1060")
        self.timeline_instance_frame_var = tk.StringVar(value="-")
        self.timeline_instance_label_var = tk.StringVar()
        self.timeline_instance_status_var = tk.StringVar(value="Kein MovieClip ausgewählt")
        box = ttk.LabelFrame(self, text="MovieClip-Timeline", padding=8)
        box.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(box, text="Frame:").pack(side="left")
        ttk.Label(box, textvariable=self.timeline_instance_frame_var, width=12).pack(side="left", padx=(5, 10))
        ttk.Button(box, text="◀", width=3, command=lambda: change_frame(self, -1)).pack(side="left")
        ttk.Button(box, text="▶", width=3, command=lambda: change_frame(self, 1)).pack(side="left", padx=(4, 0))
        ttk.Button(box, text="Play/Pause Instanz", command=lambda: toggle_selected(self)).pack(side="left", padx=(10, 0))
        ttk.Button(box, text="Reset Instanz", command=lambda: reset_selected(self)).pack(side="left", padx=(5, 0))
        ttk.Label(box, text="Label:").pack(side="left", padx=(16, 4))
        self.timeline_instance_label_combo = ttk.Combobox(
            box, textvariable=self.timeline_instance_label_var, state="readonly", width=23,
        )
        self.timeline_instance_label_combo.pack(side="left")
        ttk.Button(box, text="Springen", command=lambda: jump_selected_label(self)).pack(side="left", padx=(5, 0))
        ttk.Label(self, textvariable=self.timeline_instance_status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        sync_controls(self)

    def on_select(self, event=None):
        result = original_select(self, event)
        sync_controls(self)
        return result

    def refresh(self):
        result = original_refresh(self)
        sync_controls(self)
        return result

    cls.__init__ = window_init
    cls._on_select = on_select
    cls.refresh = refresh
    cls.load_override_preset = load_preset
    cls._sync_timeline_controls = sync_controls
