"""Install MSBT language selection and localized runtime text in the UI Browser."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ui_browser
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_native_callback_patch as native
import ui_browser_state_inspector_patch as state_inspector
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core
import ui_browser_localization as localization

try:
    import ui_browser_game_state_patch as game_state
except Exception:
    game_state = None
try:
    import ui_browser_async_audio_gui as audio_gui
except Exception:
    audio_gui = None
try:
    import ui_browser_async_audio_patch as audio_patch
except Exception:
    audio_patch = None


_INSTALLED = False
_BASE = {}
_TEXT_CALLBACK_PARTS = (
    "text", "string", "message", "caption", "subtitle", "title", "description", "localized",
)


def _movie_key(owner):
    try:
        return override_patch._browser_movie_key(owner)
    except Exception:
        record = getattr(owner, "_current_movie_record", None)
        source = getattr(owner, "_current_source", None)
        return f"{getattr(source, 'source_label', '')}|{getattr(record, 'name', '')}"


def _current_config(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return localization.normalize_localization_config({})
    return localization.ensure_localization_config(movie)


def _save_config(owner):
    key = str(getattr(owner, "_ui_current_localization_key", "") or "")
    movie = getattr(owner, "_current_movie", None)
    if key and movie is not None:
        owner._ui_localization_by_movie[key] = dict(_current_config(owner))


def _language_label(code):
    return f"{code} – {localization.LANGUAGE_NAMES.get(code, code)}"


def _code_from_label(value):
    return str(value or "").split("–", 1)[0].strip().upper()


def _sync_controls(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    catalog = localization.attach_localization_catalog(owner, movie)
    config = localization.ensure_localization_config(movie)
    labels = tuple(_language_label(code) for code in catalog.get("languages", ()))
    combo = getattr(owner, "ui_localization_combo", None)
    if combo is not None:
        combo.configure(values=labels)
    variable = getattr(owner, "ui_localization_language_var", None)
    if variable is not None:
        variable.set(_language_label(config["language"]))
    enabled = getattr(owner, "ui_localization_enabled_var", None)
    if enabled is not None:
        enabled.set(config["enabled"])
    status = getattr(owner, "ui_localization_status_var", None)
    if status is not None:
        links = localization.attach_localization_links(movie)
        status.set(
            f"{len(catalog.get('records', ()))} Texte | {len(links)} Laufzeit-Links | "
            f"Fallback {config['fallback']}"
        )


def attach_localization(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return None
    key = _movie_key(owner)
    owner._ui_current_localization_key = key
    catalog = localization.attach_localization_catalog(owner, movie)
    stored = owner._ui_localization_by_movie.get(key)
    if stored is not None:
        clean = localization.normalize_localization_config(stored, catalog.get("languages", ()))
        movie.ui_localization_enabled = clean["enabled"]
        movie.ui_localization_language = clean["language"]
        movie.ui_localization_fallback = clean["fallback"]
    else:
        owner._ui_localization_by_movie[key] = dict(localization.ensure_localization_config(movie))
    _sync_controls(owner)
    return movie


def _runtime_source_state(movie):
    value = getattr(movie, "ui_localized_runtime_sources", None)
    if not isinstance(value, dict):
        value = {}
        movie.ui_localized_runtime_sources = value
    return value


def _reference_path(reference, context):
    if isinstance(reference, runtime.RuntimeRef):
        return reference.path
    value = getattr(reference, "path", None)
    return str(value) if value else str(getattr(context, "path", "root") or "root")


def set_property(context, reference, name, value):
    short = str(name).rsplit("::", 1)[-1].rsplit(".", 1)[-1]
    if short in ("text", "htmlText") and isinstance(value, str):
        resolution = localization.resolve_text_id(context.movie, value)
        key = (_reference_path(reference, context), short)
        sources = _runtime_source_state(context.movie)
        if resolution is not None:
            sources[key] = {"raw": value, "reference": reference}
            value = resolution.text
        else:
            sources.pop(key, None)
    return _BASE["set_property"](context, reference, name, value)


def _last_callback_record(movie):
    calls = native._callback_state(movie).get("calls", ())
    return calls[-1] if calls and isinstance(calls[-1], dict) else None


def _semantic_text_callback(name):
    key = native.compact_name(name)
    return any(part in key for part in _TEXT_CALLBACK_PARTS)


def native_call(context, name, args):
    result = _BASE["native"](context, name, args)
    if not bool(getattr(context.movie, "ui_localization_enabled", True)):
        return result
    record = _last_callback_record(context.movie)
    if record and record.get("source") == "Native-Override":
        return result
    resolution = localization.resolve_text_id(context.movie, result) if isinstance(result, str) else None
    if resolution is None and _semantic_text_callback(name) and result in (None, "", runtime._UNDEFINED):
        for value in tuple(args or ()):
            resolution = localization.resolve_text_id(context.movie, value)
            if resolution is not None:
                break
    if resolution is None:
        return result
    if record is not None:
        record["source"] = f"MSBT:{resolution.language}"
        record["result"] = resolution.text
        record["text_id"] = resolution.requested
        record["fallback"] = resolution.fallback_used
    return resolution.text


def text_definition_for_path(definition, path, overrides):
    result = _BASE["text_definition"](definition, path, overrides)
    manual = override_patch.normalize_override((overrides or {}).get(path, {}))
    if "text" in manual:
        return result
    original = str(getattr(definition, "initial_text", "") or "")
    current = str(getattr(result, "initial_text", "") or "")
    if current != original:
        return result
    movie = getattr(definition, "_ui_localization_movie", None)
    if movie is None:
        return result
    candidates = (
        original, str(getattr(definition, "variable_name", "") or ""),
        path.rsplit(":", 1)[-1],
    )
    resolution = next((localization.resolve_text_id(movie, value) for value in candidates if value), None)
    if resolution is None:
        return result
    clone = copy.copy(result)
    clone.initial_text = resolution.text
    clone._ui_localization = {
        "id": resolution.requested, "language": resolution.language,
        "bundle": resolution.record.bundle, "fallback": resolution.fallback_used,
    }
    return clone


def _bind_definitions(movie):
    for definition in (getattr(movie, "definitions", {}) or {}).values():
        if hasattr(definition, "initial_text"):
            try:
                definition._ui_localization_movie = movie
            except Exception:
                pass


def _decorate_nodes(movie, nodes):
    sources = _runtime_source_state(movie)
    result = []
    for node in tuple(nodes or ()):
        meta = dict(node.metadata)
        children = _decorate_nodes(movie, node.children)
        higher = bool(
            (meta.get("override") or {}).get("text") is not None
            or meta.get("mock_role")
            or (isinstance(meta.get("avm2_runtime"), dict) and any(
                key in meta["avm2_runtime"] for key in ("text", "htmlText")
            ))
        )
        source = sources.get((node.path, "htmlText")) or sources.get((node.path, "text"))
        resolution = None
        if source:
            resolution = localization.resolve_text_id(movie, source.get("raw", ""))
        elif not higher and node.kind == "EditText":
            for value in (
                meta.get("display_text", ""), meta.get("text", ""),
                meta.get("variable_name", ""), node.label,
            ):
                resolution = localization.resolve_text_id(movie, value)
                if resolution is not None:
                    break
        if resolution is not None:
            meta["localization"] = {
                "id": resolution.requested, "language": resolution.language,
                "bundle": resolution.record.bundle, "source": resolution.record.source_label,
                "fallback": resolution.fallback_used,
            }
            if not higher or source:
                meta["text"] = resolution.text
                meta["display_text"] = resolution.text
        result.append(state_inspector.StateNode(
            node.path, node.depth, node.label, node.kind, node.visible,
            node.character_id, node.class_name, meta, children,
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    return _decorate_nodes(movie, _BASE["inspect"](movie, frame, max_depth))


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    item = node.metadata.get("localization")
    if not item:
        return text
    return text + "\n\nMSBT-Lokalisierung:\n" + (
        f"- ID: {item.get('id', '')}\n"
        f"- Sprache: {item.get('language', '')}\n"
        f"- Bundle: {item.get('bundle', '')}\n"
        f"- Quelle: {item.get('source', '')}\n"
        f"- Fallback: {'ja' if item.get('fallback') else 'nein'}"
    )


def _reapply_runtime_texts(movie):
    properties = getattr(runtime, "_properties", lambda _movie: {})(movie)
    for (path, prop), item in list(_runtime_source_state(movie).items()):
        resolution = localization.resolve_text_id(movie, item.get("raw", ""))
        if resolution is None:
            continue
        reference = item.get("reference")
        if hasattr(reference, prop):
            try:
                setattr(reference, prop, resolution.text)
            except Exception:
                pass
        if isinstance(properties, dict):
            properties.setdefault(path, {})[prop] = resolution.text


def _invalidate(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_localization_revision = int(getattr(movie, "ui_localization_revision", 0)) + 1
        _reapply_runtime_texts(movie)
        runtime._touch(movie)
    _save_config(owner)
    try:
        override_patch._invalidate_overrides(owner)
    except Exception:
        owner.request_render()
    window = getattr(owner, "_localization_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.refresh()
    except Exception:
        pass
    _sync_controls(owner)


def _controls_changed(owner, _event=None):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    movie.ui_localization_enabled = bool(owner.ui_localization_enabled_var.get())
    code = _code_from_label(owner.ui_localization_language_var.get())
    if code:
        movie.ui_localization_language = code
    _invalidate(owner)


def apply_localization_config(owner, value):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    catalog = localization.attach_localization_catalog(owner, movie)
    clean = localization.normalize_localization_config(value, catalog.get("languages", ()))
    movie.ui_localization_enabled = clean["enabled"]
    movie.ui_localization_language = clean["language"]
    movie.ui_localization_fallback = clean["fallback"]
    _invalidate(owner)


def current_localization_config(owner):
    return dict(_current_config(owner))


class LocalizationInspector(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI MSBT / Laufzeittexte")
        self.geometry("1320x840")
        self.minsize(960, 620)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._records = {}
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.text_tab = ttk.Frame(notebook)
        self.link_tab = ttk.Frame(notebook)
        self.diag_tab = ttk.Frame(notebook)
        notebook.add(self.text_tab, text="MSBT-Texte")
        notebook.add(self.link_tab, text="Laufzeit-Links")
        notebook.add(self.diag_tab, text="Diagnose")
        self._build_text_tab()
        self._build_link_tab()
        self.diag = tk.Text(self.diag_tab, wrap="none", state="disabled")
        self.diag.pack(fill="both", expand=True, padx=6, pady=6)
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        self.refresh()

    def movie(self):
        return getattr(self.owner, "_current_movie", None)

    @staticmethod
    def _set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _build_text_tab(self):
        bar = ttk.Frame(self.text_tab, padding=6)
        bar.pack(fill="x")
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.search_var = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.search_var, width=36)
        search.pack(side="left", padx=5)
        search.bind("<KeyRelease>", lambda _event: self.refresh_texts())
        ttk.Button(bar, text="JSON exportieren", command=self.export_json).pack(side="right")
        pane = ttk.PanedWindow(self.text_tab, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        left = ttk.Frame(pane)
        self.text_tree = ttk.Treeview(left, columns=("bundle", "language", "text"), show="tree headings")
        for column, label, width in (
            ("#0", "Text-ID", 300), ("bundle", "Bundle", 120),
            ("language", "Sprache", 75), ("text", "Text", 420),
        ):
            self.text_tree.heading(column, text=label)
            self.text_tree.column(column, width=width)
        self.text_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.text_tree.yview)
        scroll.pack(side="right", fill="y")
        self.text_tree.configure(yscrollcommand=scroll.set)
        self.text_tree.bind("<<TreeviewSelect>>", self.on_text_select)
        pane.add(left, weight=2)
        self.details = tk.Text(pane, wrap="word", state="disabled", width=55)
        pane.add(self.details, weight=1)

    def _build_link_tab(self):
        self.link_tree = ttk.Treeview(
            self.link_tab, columns=("kind", "count", "source"), show="tree headings",
        )
        for column, label, width in (
            ("#0", "Text-ID", 310), ("kind", "Quelle", 100),
            ("count", "Anzahl", 70), ("source", "Fundstellen", 650),
        ):
            self.link_tree.heading(column, text=label)
            self.link_tree.column(column, width=width)
        self.link_tree.pack(fill="both", expand=True, padx=6, pady=6)

    def refresh(self):
        movie = self.movie()
        if movie is None:
            self.status_var.set("Kein UI-Film ausgewählt")
            return
        catalog = localization.attach_localization_catalog(self.owner, movie)
        self.refresh_texts()
        self.link_tree.delete(*self.link_tree.get_children())
        for index, link in enumerate(localization.attach_localization_links(movie)):
            self.link_tree.insert("", "end", iid=f"link_{index}", text=link.text_id,
                                  values=(link.source_kind, link.count, link.source))
        snapshot = localization.localization_snapshot(movie, include_texts=False)
        self._set_text(self.diag, json.dumps(snapshot, ensure_ascii=False, indent=2))
        self.status_var.set(
            f"{len(catalog.get('documents', ()))} MSBT-Sprachdateien | "
            f"{len(catalog.get('records', ()))} Texte | "
            f"{len(catalog.get('errors', ()))} Parserfehler | "
            f"{len(localization.attach_localization_links(movie))} Laufzeit-Links"
        )

    def refresh_texts(self):
        movie = self.movie()
        self.text_tree.delete(*self.text_tree.get_children())
        self._records.clear()
        if movie is None:
            return
        catalog = localization.attach_localization_catalog(self.owner, movie)
        language = localization.ensure_localization_config(movie)["language"]
        wanted = self.search_var.get().casefold().strip()
        seen = set()
        for record in catalog.get("records", ()):
            if record.language != language:
                continue
            key = (record.bundle, record.label)
            if key in seen:
                continue
            seen.add(key)
            haystack = f"{record.label}\n{record.text}\n{record.bundle}".casefold()
            if wanted and wanted not in haystack:
                continue
            iid = f"text_{len(self._records)}"
            preview = record.text.replace("\n", " ↵ ")[:160]
            self.text_tree.insert("", "end", iid=iid, text=record.label,
                                  values=(record.bundle, record.language, preview))
            self._records[iid] = record

    def on_text_select(self, _event=None):
        selection = self.text_tree.selection()
        record = self._records.get(selection[0]) if selection else None
        movie = self.movie()
        if record is None or movie is None:
            return
        translations = localization.available_translations(movie, record.label, record.bundle)
        lines = [
            f"ID: {record.label}", f"Bundle: {record.bundle}",
            f"Quelle: {record.source_label}", f"Index: {record.message_index}", "",
        ]
        for code in localization.language_chain(movie):
            item = translations.get(code)
            if item is not None:
                lines.extend((f"[{code} – {localization.LANGUAGE_NAMES.get(code, code)}]", item.text, ""))
        self._set_text(self.details, "\n".join(lines))

    def export_json(self):
        movie = self.movie()
        if movie is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="MSBT-Inventar speichern", defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            Path(path).write_text(
                json.dumps(localization.localization_snapshot(movie, True), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    def close(self):
        self.owner._localization_window = None
        self.destroy()


def show_localization_inspector(owner):
    window = getattr(owner, "_localization_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh()
            return window
    except Exception:
        pass
    owner._localization_window = LocalizationInspector(owner)
    return owner._localization_window


def make_preset(owner):
    result = _BASE["make_preset"](owner)
    result["localization"] = current_localization_config(owner)
    return result


def normalize_preset(data):
    result = _BASE["normalize_preset"](data)
    result["localization"] = localization.normalize_localization_config(
        data.get("localization", {}) if isinstance(data, dict) else {}
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
    if audio_gui is not None:
        audio_gui.apply_audio_config(window.owner, preset["audio_preview"])
    apply_localization_config(window.owner, preset["localization"])
    override_patch._invalidate_overrides(window.owner)
    window.override_status_var.set(f"Preset geladen: {Path(path).name}")
    window.refresh()


def browser_init(owner, *args, **kwargs):
    owner._ui_localization_by_movie = {}
    owner._ui_current_localization_key = ""
    owner._localization_window = None
    _BASE["browser_init"](owner, *args, **kwargs)
    owner.ui_localization_enabled_var = tk.BooleanVar(value=True)
    owner.ui_localization_language_var = tk.StringVar(value=_language_label(localization.DEFAULT_LANGUAGE))
    owner.ui_localization_status_var = tk.StringVar(value="MSBT wird geladen")
    bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
    bar.pack(fill="x")
    ttk.Button(bar, text="MSBT / Texte", command=lambda: show_localization_inspector(owner)).pack(side="left")
    ttk.Checkbutton(
        bar, text="Lokalisieren", variable=owner.ui_localization_enabled_var,
        command=lambda: _controls_changed(owner),
    ).pack(side="left", padx=(10, 0))
    ttk.Label(bar, text="Sprache:").pack(side="left", padx=(10, 4))
    owner.ui_localization_combo = ttk.Combobox(
        bar, textvariable=owner.ui_localization_language_var, state="readonly", width=23,
    )
    owner.ui_localization_combo.pack(side="left")
    owner.ui_localization_combo.bind(
        "<<ComboboxSelected>>", lambda event: _controls_changed(owner, event),
    )
    ttk.Label(bar, textvariable=owner.ui_localization_status_var).pack(side="right")
    owner.bind("<Control-l>", lambda _event: show_localization_inspector(owner))
    attach_localization(owner)


def browser_select(owner, event=None):
    _save_config(owner)
    result = _BASE["select"](owner, event)
    movie = attach_localization(owner)
    if movie is not None:
        _bind_definitions(movie)
    window = getattr(owner, "_localization_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.refresh()
    except Exception:
        pass
    return result


def browser_render(owner):
    movie = attach_localization(owner)
    if movie is not None:
        _bind_definitions(movie)
    return _BASE["render"](owner)


def browser_info(owner, stats):
    text = _BASE["info"](owner, stats)
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return text
    catalog = localization.attach_localization_catalog(owner, movie)
    config = localization.ensure_localization_config(movie)
    links = localization.attach_localization_links(movie)
    fallbacks = 0
    for link in links:
        resolution = localization.resolve_text_id(movie, link.text_id)
        if resolution is not None and resolution.fallback_used:
            fallbacks += 1
    return text + "\n\nMSBT / Laufzeittexte:\n" + (
        f"- Aktiv: {'ja' if config['enabled'] else 'nein'}\n"
        f"- Sprache / Fallback: {config['language']} / {config['fallback']}\n"
        f"- Sprachdateien / Texte: {len(catalog.get('documents', ()))} / {len(catalog.get('records', ()))}\n"
        f"- Laufzeit-Links: {len(links)} ({fallbacks} über Fallback)\n"
        f"- Parserfehler: {len(catalog.get('errors', ()))}"
    )


def browser_close(owner):
    _save_config(owner)
    window = getattr(owner, "_localization_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE["close"](owner)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE.update(
        native=runtime._native,
        set_property=runtime._set_property,
        text_definition=override_patch.text_definition_for_path,
        inspect=state_inspector.inspect_movie_state,
        format_node=state_inspector.format_state_node,
        browser_init=ui_browser.UIBrowser.__init__,
        select=ui_browser.UIBrowser._on_tree_select,
        render=ui_browser.UIBrowser._render,
        info=ui_browser.UIBrowser._format_info,
        close=ui_browser.UIBrowser.close,
        make_preset=override_patch.make_preset,
        normalize_preset=override_patch.normalize_preset,
    )
    runtime._native = native_call
    runtime._set_property = set_property
    override_patch.text_definition_for_path = text_definition_for_path
    state_inspector.inspect_movie_state = inspect_movie_state
    state_inspector.format_state_node = format_state_node
    ui_browser.inspect_movie_state = inspect_movie_state
    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = browser_select
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser._format_info = browser_info
    ui_browser.UIBrowser.close = browser_close
    ui_browser.UIBrowser.show_ui_localization = show_localization_inspector

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
    if audio_gui is not None:
        audio_gui.make_preset = make_preset
        audio_gui.normalize_preset = normalize_preset
        audio_gui.load_preset = load_preset
    if audio_patch is not None:
        audio_patch.normalize_preset = normalize_preset
    native.make_preset = make_preset
    native.normalize_preset = normalize_preset
    native.load_preset = load_preset
    try:
        import ui_browser_timeline_inspector_patch as timeline_inspector
        timeline_inspector.load_preset = load_preset
    except Exception:
        pass
    state_inspector.StateInspectorWindow.load_override_preset = load_preset

    ui_browser.LocalizationRecord = localization.LocalizationRecord
    ui_browser.resolve_ui_localized_text = localization.resolve_text_id
    ui_browser.build_ui_localization_catalog = localization.build_localization_catalog
    ui_browser.ui_localization_snapshot = localization.localization_snapshot
    ui_browser.normalize_ui_localization_config = localization.normalize_localization_config
