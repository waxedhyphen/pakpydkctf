"""Browser controls and state decoration for classic buttons and precise HitTests."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import ui_browser
import ui_browser_classic_button as classic
import ui_browser_classic_button_runtime as button_runtime
import ui_browser_precise_hit as precise
import ui_browser_classic_button_inspector as button_inspector

_BASE = {}

show_inspector = button_inspector.show_inspector
inspect_movie_state = button_inspector.inspect_movie_state
format_state_node = button_inspector.format_state_node


def controls_changed(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    movie.ui_precise_hit_enabled = bool(owner.ui_precise_hit_enabled_var.get())
    precise.clear_geometry_cache()
    owner.request_render()


def browser_init(owner, *args, **kwargs):
    owner._classic_button_window = None
    _BASE["browser_init"](owner, *args, **kwargs)
    owner.ui_precise_hit_enabled_var = tk.BooleanVar(value=True)
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Button(bar, text="Buttons / HitTests", command=lambda: show_inspector(owner)).pack(side="left")
    ttk.Checkbutton(
        bar, text="Präzise HitTests", variable=owner.ui_precise_hit_enabled_var,
        command=lambda: controls_changed(owner),
    ).pack(side="left", padx=(10, 0))
    ttk.Label(
        bar, text="Shape-/Alpha-Test · ClipDepth · scrollRect · mask · hitArea",
    ).pack(side="left", padx=(10, 0))
    owner.bind("<Control-b>", lambda _event: show_inspector(owner))


def browser_select(owner, event=None):
    result = _BASE["select"](owner, event)
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_precise_hit_enabled = bool(owner.ui_precise_hit_enabled_var.get())
    window = getattr(owner, "_classic_button_window", None)
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
    definitions = [value for value in movie.definitions.values()
                   if isinstance(value, classic.ClassicButtonDef)]
    actions = sum(len(binding.actions) for value in definitions for binding in value.button_actions)
    safe = sum(action.safe for value in definitions for binding in value.button_actions for action in binding.actions)
    diag = getattr(movie, "ui_precise_hit_diagnostics", {}) or {}
    state = button_runtime._classic_state(movie)
    return text + "\n\nKlassische Buttons / HitTests:\n" + (
        f"- DefineButton-Definitionen: {len(definitions)}\n"
        f"- Button-Aktionen: {actions} ({safe} sicher ausführbar)\n"
        f"- Präzise Geometrien / Pfade: {diag.get('geometries', 0)} / {diag.get('paths', 0)}\n"
        f"- Alpha-Geometrien: {diag.get('alpha', 0)}\n"
        f"- ClipDepth / scrollRect: {diag.get('clip_depth_masks', 0)} / {diag.get('scroll_rect_clips', 0)}\n"
        f"- Präzise Ablehnungen: {diag.get('precise_rejects', 0)}\n"
        f"- AVM1 ausgeführt / blockiert: {state['executed']} / {state['blocked']}"
    )


def browser_close(owner):
    window = getattr(owner, "_classic_button_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE["close"](owner)


def install_hooks(base_inspect, base_format_node, base_browser_init, base_select,
                  base_info, base_close):
    button_inspector._BASE.update(inspect=base_inspect, format_node=base_format_node)
    _BASE.update(
        inspect=base_inspect, format_node=base_format_node,
        browser_init=base_browser_init, select=base_select, info=base_info, close=base_close,
    )
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = browser_select
    ui_browser.UIBrowser._format_info = browser_info
    ui_browser.UIBrowser.close = browser_close
    ui_browser.UIBrowser.show_classic_buttons = show_inspector
