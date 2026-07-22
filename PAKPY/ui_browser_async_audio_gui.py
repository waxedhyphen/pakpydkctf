"""Tk controls, inspector and preset integration for async UI audio."""
from __future__ import annotations

from collections import OrderedDict
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ui_browser
import ui_browser_audio_preview as audio
import ui_browser_async_native as async_native
import ui_browser_native_callback_patch as native
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core

try:
    import ui_browser_game_state_patch as game_state
except Exception:
    game_state = None

_BASE = {}


def current_audio_config(owner):
    movie = getattr(owner, "_current_movie", None)
    return audio.normalize_audio_preview_config({} if movie is None else {
        "enabled": getattr(movie, "ui_audio_preview_enabled", False),
        "muted": getattr(movie, "ui_audio_preview_muted", False),
        "volume": getattr(movie, "ui_audio_preview_volume", 0.65),
    })


def apply_audio_config(owner, value):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    clean = audio.normalize_audio_preview_config(value)
    movie.ui_audio_preview_enabled = clean["enabled"]
    movie.ui_audio_preview_muted = clean["muted"]
    movie.ui_audio_preview_volume = clean["volume"]
    for attr, key in (
        ("ui_audio_enabled_var", "enabled"), ("ui_audio_muted_var", "muted"),
    ):
        variable = getattr(owner, attr, None)
        if variable is not None:
            variable.set(clean[key])
    variable = getattr(owner, "ui_audio_volume_var", None)
    if variable is not None:
        variable.set(int(round(clean["volume"] * 100)))


def make_preset(owner):
    result = _BASE["make_preset"](owner)
    result["audio_preview"] = current_audio_config(owner)
    return result


def normalize_preset(data):
    result = _BASE["normalize_preset"](data)
    result["audio_preview"] = audio.normalize_audio_preview_config(
        data.get("audio_preview", {}) if isinstance(data, dict) else {},
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
    native.apply_native_callback_config(window.owner, preset["native_callbacks"])
    apply_audio_config(window.owner, preset["audio_preview"])
    override_patch._invalidate_overrides(window.owner)
    window.override_status_var.set(f"Preset geladen: {Path(path).name}")
    window.refresh()


class AsyncAudioInspector(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI Audio / Async Native Events")
        self.geometry("1260x820")
        self.minsize(920, 600)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._sound_items = {}

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.audio_tab = ttk.Frame(notebook)
        self.async_tab = ttk.Frame(notebook)
        notebook.add(self.audio_tab, text="CAUD / CSMP Audio")
        notebook.add(self.async_tab, text="Async Queue")
        self._build_audio()
        self._build_async()
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        self.refresh()

    def movie(self):
        return getattr(self.owner, "_current_movie", None)

    @staticmethod
    def _set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _build_audio(self):
        bar = ttk.Frame(self.audio_tab, padding=6)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.search_var = tk.StringVar(value="UI_")
        search = ttk.Entry(bar, textvariable=self.search_var, width=32)
        search.pack(side="left", padx=5)
        search.bind("<KeyRelease>", lambda _event: self.refresh_audio())
        ttk.Button(bar, text="Abspielen", command=self.play_selected).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Stop", command=lambda: audio.stop_audio(self.owner)).pack(side="left", padx=4)
        ttk.Button(bar, text="WAV speichern", command=self.export_selected).pack(side="left")

        pane = ttk.PanedWindow(self.audio_tab, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        left = ttk.Frame(pane)
        self.sound_tree = ttk.Treeview(left, columns=("source", "refs"), show="tree headings")
        self.sound_tree.heading("#0", text="Sound")
        self.sound_tree.heading("source", text="PAK")
        self.sound_tree.heading("refs", text="CSMP")
        self.sound_tree.column("#0", width=310)
        self.sound_tree.column("source", width=150)
        self.sound_tree.column("refs", width=55, anchor="center")
        self.sound_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.sound_tree.yview)
        scroll.pack(side="right", fill="y")
        self.sound_tree.configure(yscrollcommand=scroll.set)
        self.sound_tree.bind("<<TreeviewSelect>>", self.on_sound_select)
        pane.add(left, weight=1)
        self.audio_details = tk.Text(pane, wrap="word", state="disabled", width=55)
        pane.add(self.audio_details, weight=1)

    def _build_async(self):
        bar = ttk.Frame(self.async_tab, padding=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="Fällige ausführen", command=self.process_due).pack(side="left")
        ttk.Button(bar, text="Alle abschließen", command=self.process_all).pack(side="left", padx=5)
        ttk.Button(bar, text="Queue leeren", command=self.clear_queue).pack(side="left")
        self.async_tree = ttk.Treeview(
            self.async_tab, columns=("state", "due", "events"), show="tree headings",
        )
        for column, text, width in (
            ("#0", "Callback", 260), ("state", "Status", 100),
            ("due", "Zeit", 100), ("events", "Events", 450),
        ):
            self.async_tree.heading(column, text=text)
            self.async_tree.column(column, width=width)
        self.async_tree.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def refresh(self):
        self.refresh_audio()
        self.refresh_async()
        movie = self.movie()
        if movie is None:
            self.status_var.set("Kein UI-Film ausgewählt")
            return
        state = audio.async_audio_state(movie)
        records = audio.attach_audio_catalog(self.owner, movie)
        backend = audio.owner_backend(self.owner)
        self.status_var.set(
            f"{len(records)} CAUD | {state['resolved_audio']} aufgelöst | "
            f"{len(state['pending'])} ausstehend | Audio-Backend: "
            f"{'winsound' if backend.available else 'nur WAV-Export'}"
        )

    def refresh_audio(self):
        self.sound_tree.delete(*self.sound_tree.get_children())
        self._sound_items.clear()
        movie = self.movie()
        if movie is None:
            return
        wanted = native.compact_name(self.search_var.get())
        for index, record in enumerate(audio.attach_audio_catalog(self.owner, movie)):
            if wanted and wanted not in record.normalized_name:
                continue
            iid = f"sound_{index}"
            self.sound_tree.insert(
                "", "end", iid=iid, text=record.name,
                values=(record.source_label, len(record.csmp_refs)),
            )
            self._sound_items[iid] = record

    def selected_record(self):
        selection = self.sound_tree.selection()
        return self._sound_items.get(selection[0]) if selection else None

    def on_sound_select(self, _event=None):
        record = self.selected_record()
        if record is None:
            return
        lines = [
            f"Name: {record.name}", f"Quelle: {record.source_label}",
            f"CAUD UUID: {record.caud_uuid}",
            f"CSMP-Varianten: {len(record.csmp_refs)}",
            f"Loop: {'ja' if record.loop else 'nein'}",
            f"Volume / Gain: {record.caud_info.get('volume', '-')} / {record.caud_info.get('gain', '-')}",
        ]
        lines.extend(f"- {value}" for value in record.csmp_refs)
        if record.parser_error:
            lines.extend(("", "CAUD-Fallback:", record.parser_error))
        self._set_text(self.audio_details, "\n".join(lines))

    def play_selected(self):
        record = self.selected_record()
        if record is not None:
            audio.play_sound(self.owner, record, force=True)
            self.refresh()

    def export_selected(self):
        record = self.selected_record()
        if record is None:
            return
        try:
            wav_bytes, _info, _ref = audio.decode_sound(self.owner, record)
        except Exception as exc:
            messagebox.showerror("UI Audio", str(exc), parent=self)
            return
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in record.name)
        path = filedialog.asksaveasfilename(
            parent=self, title="UI-Sound als WAV speichern", defaultextension=".wav",
            initialfile=f"{safe}.wav",
            filetypes=[("WAV-Dateien", "*.wav"), ("Alle Dateien", "*.*")],
        )
        if path:
            Path(path).write_bytes(wav_bytes)

    def refresh_async(self):
        self.async_tree.delete(*self.async_tree.get_children())
        movie = self.movie()
        if movie is None:
            return
        state = audio.async_audio_state(movie)
        for item in sorted(state["pending"], key=lambda value: (value["due_ms"], value["id"])):
            self.async_tree.insert(
                "", "end", text=item["callback"],
                values=("ausstehend", f"{item['due_ms']:.1f} ms", ", ".join(item["events"])),
            )
        for item in reversed(state["completed"][-100:]):
            self.async_tree.insert(
                "", "end", text=item["callback"],
                values=("fertig", f"{item.get('completed_ms', 0):.1f} ms", ", ".join(item["events"])),
            )

    def process_due(self):
        async_native.process_async_queue(self.owner)
        self.refresh()

    def process_all(self):
        async_native.process_async_queue(self.owner, True)
        self.refresh()

    def clear_queue(self):
        movie = self.movie()
        if movie is not None:
            audio.async_audio_state(movie)["pending"].clear()
        self.refresh()

    def close(self):
        self.owner._async_audio_window = None
        self.destroy()


def show_async_audio_inspector(owner):
    window = getattr(owner, "_async_audio_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh()
            return window
    except Exception:
        pass
    owner._async_audio_window = AsyncAudioInspector(owner)
    return owner._async_audio_window


def _controls_changed(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    movie.ui_audio_preview_enabled = bool(owner.ui_audio_enabled_var.get())
    movie.ui_audio_preview_muted = bool(owner.ui_audio_muted_var.get())
    movie.ui_audio_preview_volume = max(
        0.0, min(1.0, float(owner.ui_audio_volume_var.get()) / 100.0),
    )
    if movie.ui_audio_preview_muted:
        audio.stop_audio(owner)


def browser_init(owner, *args, **kwargs):
    _BASE["browser_init"](owner, *args, **kwargs)
    owner._async_audio_window = None
    owner._ui_audio_backend = audio.WavePreviewBackend()
    owner._ui_audio_wav_cache = OrderedDict()
    owner._ui_audio_wav_cache_bytes = 0
    owner.ui_audio_enabled_var = tk.BooleanVar(value=False)
    owner.ui_audio_muted_var = tk.BooleanVar(value=False)
    owner.ui_audio_volume_var = tk.IntVar(value=65)
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Button(
        bar, text="Audio / Async",
        command=lambda: show_async_audio_inspector(owner),
    ).pack(side="left")
    ttk.Checkbutton(
        bar, text="UI-Sounds", variable=owner.ui_audio_enabled_var,
        command=lambda: _controls_changed(owner),
    ).pack(side="left", padx=(10, 0))
    ttk.Checkbutton(
        bar, text="Stumm", variable=owner.ui_audio_muted_var,
        command=lambda: _controls_changed(owner),
    ).pack(side="left", padx=(8, 0))
    ttk.Label(bar, text="Lautstärke:").pack(side="left", padx=(10, 4))
    ttk.Scale(
        bar, from_=0, to=100, variable=owner.ui_audio_volume_var,
        command=lambda _value: _controls_changed(owner), length=130,
    ).pack(side="left")
    ttk.Label(bar, text="F12: CAUD/CSMP und Completion-Queue").pack(side="right")
    owner.bind("<F12>", lambda _event: show_async_audio_inspector(owner))


def browser_select(owner, event=None):
    result = _BASE["select"](owner, event)
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        audio.attach_audio_catalog(owner, movie)
        apply_audio_config(owner, current_audio_config(owner))
    window = getattr(owner, "_async_audio_window", None)
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
    records = audio.attach_audio_catalog(owner, movie)
    state = audio.async_audio_state(movie)
    explicit = set()
    for summary in getattr(movie, "ui_native_callback_summaries", ()) or ():
        if native.compact_name(summary.name) not in ("playsound", "debugsoundplay"):
            continue
        for sample in summary.argument_samples:
            explicit.update(
                value for value in sample
                if isinstance(value, str) and value != native._DYNAMIC_ARGUMENT
            )
    resolved = sum(audio.resolve_sound(movie, value) is not None for value in explicit)
    backend = audio.owner_backend(owner)
    return text + "\n\nAsync / UI Audio:\n" + (
        f"- CAUD-Sounds: {len(records)}\n"
        f"- Statische Soundnamen aufgelöst: {resolved} / {len(explicit)}\n"
        f"- Requests aufgelöst / offen: {state['resolved_audio']} / {state['unresolved_audio']}\n"
        f"- Dekodiert / abgespielt: {state['decoded_audio']} / {state['played_audio']}\n"
        f"- Completion-Queue: {len(state['pending'])} ausstehend, {len(state['completed'])} fertig\n"
        f"- Datenbenachrichtigungen: {state['data_notifications']}\n"
        f"- Event-Listener beliefert: {state['dispatched']}\n"
        f"- Backend: {'winsound' if backend.available else 'nur WAV-Export'}"
    )


def browser_close(owner):
    audio.stop_audio(owner)
    window = getattr(owner, "_async_audio_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE["close"](owner)


def install_hooks(base_init, base_select, base_info, base_close, base_make, base_normalize):
    _BASE.update(
        browser_init=base_init, select=base_select, info=base_info, close=base_close,
        make_preset=base_make, normalize_preset=base_normalize,
    )
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = browser_select
    ui_browser.UIBrowser._format_info = browser_info
    ui_browser.UIBrowser.close = browser_close
