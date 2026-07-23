"""Integrate a generic, validated AVM2 bytecode patcher into the UI viewer."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pak_core
import ui_browser
import ui_browser_avm2_patch as avm2
from ui_browser_avm2_repack import (
    AVM2PatchError, BytePatch, apply_movie_patches, dump_patch_manifest,
    load_patch_manifest, parse_hex_bytes, patch_gfx_asset,
)


_INSTALLED = False
_BASE_INSPECTOR_INIT = None
_BASE_INSPECTOR_CLOSE = None
_BASE_INSPECTOR_REFRESH = None


def _selection_context(owner):
    selection = tuple(getattr(owner, "tree", ()).selection()) if getattr(owner, "tree", None) is not None else ()
    if not selection:
        raise AVM2PatchError("Kein UI-Film ausgewählt")
    value = getattr(owner, "_tree_data", {}).get(selection[0])
    if value is None or value[1] is None:
        raise AVM2PatchError("Bitte einen konkreten GFX-Film auswählen")
    source, movie_index = value
    container = owner._container_for(source)
    record = container.movies[int(movie_index)]
    key = (source.source_label, source.entry.get("uuid_hex", ""), int(movie_index), record.name)
    return key, source, int(movie_index), container, record


def _patch_store(owner):
    value = getattr(owner, "_ui_avm2_patch_sets", None)
    if not isinstance(value, dict):
        value = {}
        owner._ui_avm2_patch_sets = value
    return value


def current_patches(owner):
    key, _source, _index, _container, _record = _selection_context(owner)
    return _patch_store(owner).setdefault(key, [])


def _selected_method(inspector):
    selection = inspector.tree.selection()
    item = inspector._items.get(selection[0]) if selection else None
    if item is None or item[0] != "method":
        raise AVM2PatchError("Im AVM2-Inventar zuerst eine Methode auswählen")
    return item[1], int(item[2])


def _method_label(module, method_index):
    abc = module.abc
    name = abc.method_name(method_index) if abc is not None else f"method#{method_index}"
    return f"{module.name} [{module.source}] · Methode {method_index}: {name}"


def _preview_from_movie_data(owner, record, movie_data, container):
    movie = ui_browser.parse_swf_movie(movie_data)
    owner._current_movie_record = ui_browser.GfxMovieRecord(record.name, movie_data, record.offset, len(movie_data))
    owner._current_movie = movie
    owner._current_resolver = ui_browser.TextureResolver(
        owner.parsed, owner.require_store, container.library_uuid, movie.imports,
    )
    owner.frame_scale.configure(from_=1, to=max(1, movie.frame_count))
    frame = max(1, min(int(owner.frame_var.get()), int(movie.frame_count)))
    owner.frame_var.set(frame)
    owner.frame_scale.set(frame)
    owner._update_frame_text()
    reset = getattr(owner, "reset_avm2_runtime", None)
    if callable(reset):
        try:
            reset()
        except TypeError:
            try:
                reset(owner)
            except Exception:
                pass
        except Exception:
            pass
    owner.request_render()
    window = getattr(owner, "_state_inspector", None)
    try:
        if window is not None and window.winfo_exists():
            window.refresh()
    except Exception:
        pass


def validate_current(owner):
    _key, _source, _index, _container, record = _selection_context(owner)
    return apply_movie_patches(record.data, current_patches(owner))


def apply_preview(owner):
    _key, _source, _index, container, record = _selection_context(owner)
    result = apply_movie_patches(record.data, current_patches(owner))
    _preview_from_movie_data(owner, record, result.movie_data, container)
    return result


def restore_preview(owner):
    _key, _source, _index, container, record = _selection_context(owner)
    _preview_from_movie_data(owner, record, record.data, container)


def build_patched_gfx(owner):
    _key, source, movie_index, _container, _record = _selection_context(owner)
    original_asset = pak_core.get_entry_asset(source.parsed, source.entry)
    return patch_gfx_asset(original_asset, movie_index, current_patches(owner))


def save_gfx(owner, parent=None):
    _key, source, _movie_index, _container, _record = _selection_context(owner)
    patched_asset, result = build_patched_gfx(owner)
    initial = f"{Path(source.entry.get('display_name') or source.entry.get('name') or 'UI').stem}_avm2_patched.GFX"
    path = filedialog.asksaveasfilename(
        parent=parent or owner, title="Gepatchtes GFX-Asset speichern",
        defaultextension=".GFX", initialfile=initial,
        filetypes=[("GFX-Assets", "*.GFX *.gfx"), ("Alle Dateien", "*.*")],
    )
    if not path:
        return None
    Path(path).write_bytes(patched_asset)
    return path, result


def rebuild_pak(owner, parent=None):
    _key, source, _movie_index, _container, _record = _selection_context(owner)
    patched_asset, result = build_patched_gfx(owner)
    source_path = Path(source.parsed.get("path", "UIPak.pak"))
    path = filedialog.asksaveasfilename(
        parent=parent or owner, title="PAK mit AVM2-Patches speichern",
        defaultextension=".pak", initialfile=source_path.stem + "_avm2_patched.pak",
        filetypes=[("PAK-Dateien", "*.pak"), ("Alle Dateien", "*.*")],
    )
    if not path:
        return None
    pak_core.rebuild_pak(
        source.parsed,
        {int(source.entry["index"]): {"asset_bytes": patched_asset}},
        path,
    )
    return path, result


class AddPatchDialog(tk.Toplevel):
    def __init__(self, inspector, manager=None):
        self.inspector = inspector
        self.owner = inspector.owner
        self.manager = manager
        self.module, self.method_index = _selected_method(inspector)
        body = self.module.abc.method_body(self.method_index) if self.module.abc is not None else None
        if body is None:
            raise AVM2PatchError("Die ausgewählte Methode hat keinen Methodenbody")
        super().__init__(inspector)
        self.title("AVM2-Bytepatch hinzufügen")
        self.geometry("720x360")
        self.resizable(True, False)
        self.transient(inspector)
        self.grab_set()

        ttk.Label(self, text=_method_label(self.module, self.method_index), wraplength=680).pack(
            anchor="w", padx=12, pady=(12, 8),
        )
        form = ttk.Frame(self, padding=(12, 0, 12, 8))
        form.pack(fill="x")
        self.offset_var = tk.StringVar(value="0x0")
        self.expected_var = tk.StringVar()
        self.replacement_var = tk.StringVar()
        self.note_var = tk.StringVar()
        fields = (
            ("Code-Offset", self.offset_var),
            ("Erwartete Bytes", self.expected_var),
            ("Neue Bytes", self.replacement_var),
            ("Notiz", self.note_var),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(form, text=label + ":", width=18).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        helpers = ttk.LabelFrame(self, text="Sichere Vorlagen", padding=8)
        helpers.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Button(helpers, text="pushtrue", command=lambda: self.replacement_var.set("26")).pack(side="left")
        ttk.Button(helpers, text="pushfalse", command=lambda: self.replacement_var.set("27")).pack(side="left", padx=(6, 0))
        ttk.Button(helpers, text="Bedingten Sprung entfernen", command=self.remove_branch).pack(side="left", padx=(6, 0))
        ttk.Label(
            helpers,
            text="Nur gleich lange Ersetzungen; Originalbytes werden vor dem Schreiben geprüft.",
        ).pack(side="right")

        buttons = ttk.Frame(self, padding=(12, 0, 12, 12))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Hinzufügen", command=self.add).pack(side="left")
        ttk.Button(buttons, text="Abbrechen", command=self.destroy).pack(side="left", padx=(6, 0))
        ttk.Label(buttons, text=f"Methodencode: {len(body.code)} Bytes").pack(side="right")

    def remove_branch(self):
        expected = parse_hex_bytes(self.expected_var.get())
        if expected and len(expected) != 4:
            messagebox.showerror(
                "AVM2-Patch", "Ein bedingter AVM2-Sprung ist normalerweise 4 Bytes lang.", parent=self,
            )
            return
        self.replacement_var.set("29 02 02 02")

    def add(self):
        try:
            patch = BytePatch(
                self.module.name, self.module.source, self.method_index,
                parse_hex_bytes(self.offset_var.get(), allow_integer=True),
                parse_hex_bytes(self.expected_var.get()),
                parse_hex_bytes(self.replacement_var.get()),
                self.note_var.get().strip(),
            )
            values = current_patches(self.owner)
            candidate = tuple(values) + (patch,)
            _key, _source, _index, _container, record = _selection_context(self.owner)
            apply_movie_patches(record.data, candidate)
            values.append(patch)
            if self.manager is not None:
                self.manager.refresh()
            self.inspector._update_avm2_patch_status()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)


class AVM2PatchManager(tk.Toplevel):
    def __init__(self, inspector):
        super().__init__(inspector)
        self.inspector = inspector
        self.owner = inspector.owner
        self.title("AVM2-Patches")
        self.geometry("1180x620")
        self.minsize(850, 450)
        self.transient(inspector)
        self.protocol("WM_DELETE_WINDOW", self.close)

        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Patch aus Auswahl…", command=self.add).pack(side="left")
        ttk.Button(toolbar, text="Entfernen", command=self.remove).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Profil laden…", command=self.load_profile).pack(side="left", padx=(18, 0))
        ttk.Button(toolbar, text="Profil speichern…", command=self.save_profile).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Vorschau anwenden", command=self.preview).pack(side="right")
        ttk.Button(toolbar, text="Vorschau zurücksetzen", command=self.restore).pack(side="right", padx=(0, 6))

        self.tree = ttk.Treeview(
            self, columns=("module", "source", "method", "offset", "expected", "replacement", "note"),
            show="headings", selectmode="extended",
        )
        columns = (
            ("module", "Modul", 160), ("source", "Quelle", 100), ("method", "Methode", 85),
            ("offset", "Offset", 75), ("expected", "Erwartet", 145),
            ("replacement", "Neu", 145), ("note", "Notiz", 280),
        )
        for name, label, width in columns:
            self.tree.heading(name, text=label)
            self.tree.column(name, width=width, stretch=name in ("module", "note"))
        self.tree.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="GFX speichern…", command=self.export_gfx).pack(side="left")
        ttk.Button(bottom, text="PAK neu bauen…", command=self.export_pak).pack(side="left", padx=(6, 0))
        self.status_var = tk.StringVar()
        ttk.Label(bottom, textvariable=self.status_var).pack(side="right")
        self.refresh()

    def add(self):
        try:
            AddPatchDialog(self.inspector, self)
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def remove(self):
        selected = sorted((int(item) for item in self.tree.selection()), reverse=True)
        values = current_patches(self.owner)
        for index in selected:
            if 0 <= index < len(values):
                del values[index]
        self.refresh()
        self.inspector._update_avm2_patch_status()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        try:
            patches = current_patches(self.owner)
        except Exception as exc:
            self.status_var.set(str(exc))
            return
        for index, patch in enumerate(patches):
            self.tree.insert("", "end", iid=str(index), values=(
                patch.module_name, patch.source, patch.method_index, f"0x{patch.code_offset:X}",
                patch.expected.hex(" ").upper(), patch.replacement.hex(" ").upper(), patch.note,
            ))
        self.status_var.set(f"{len(patches)} Patch(es) · gleichlange, validierte Ersetzungen")

    def preview(self):
        try:
            result = apply_preview(self.owner)
            self.inspector.refresh()
            self.status_var.set(f"Vorschau aktiv: {len(result.applied)} Patch(es)")
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def restore(self):
        try:
            restore_preview(self.owner)
            self.inspector.refresh()
            self.status_var.set("Vorschau auf Original zurückgesetzt")
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def save_profile(self):
        try:
            path = filedialog.asksaveasfilename(
                parent=self, title="AVM2-Patch-Profil speichern", defaultextension=".json",
                filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
            )
            if path:
                Path(path).write_text(dump_patch_manifest(current_patches(self.owner)), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def load_profile(self):
        try:
            path = filedialog.askopenfilename(
                parent=self, title="AVM2-Patch-Profil laden",
                filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
            )
            if not path:
                return
            loaded = list(load_patch_manifest(Path(path).read_text(encoding="utf-8")))
            values = current_patches(self.owner)
            replace = messagebox.askyesno(
                "AVM2-Patches", "Vorhandene Patchliste ersetzen?\n\nNein = geladene Patches anhängen.", parent=self,
            )
            candidate = loaded if replace else list(values) + loaded
            _key, _source, _index, _container, record = _selection_context(self.owner)
            apply_movie_patches(record.data, candidate)
            values[:] = candidate
            self.refresh()
            self.inspector._update_avm2_patch_status()
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def export_gfx(self):
        try:
            result = save_gfx(self.owner, self)
            if result:
                path, report = result
                self.status_var.set(f"GFX gespeichert: {Path(path).name} · {len(report.applied)} Patch(es)")
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def export_pak(self):
        try:
            result = rebuild_pak(self.owner, self)
            if result:
                path, report = result
                self.status_var.set(f"PAK gespeichert: {Path(path).name} · {len(report.applied)} Patch(es)")
                messagebox.showinfo("AVM2-Patch", f"PAK erfolgreich gebaut:\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("AVM2-Patch", str(exc), parent=self)

    def close(self):
        self.inspector._avm2_patch_manager = None
        self.destroy()


def show_manager(inspector):
    window = getattr(inspector, "_avm2_patch_manager", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift(); window.focus_force(); window.refresh()
            return window
    except Exception:
        pass
    inspector._avm2_patch_manager = AVM2PatchManager(inspector)
    return inspector._avm2_patch_manager


def _inspector_init(self, owner):
    _BASE_INSPECTOR_INIT(self, owner)
    self._avm2_patch_manager = None
    bar = ttk.Frame(self, padding=(8, 0, 8, 8))
    bar.pack(fill="x")
    ttk.Button(bar, text="Bytepatch hinzufügen…", command=lambda: AddPatchDialog(self)).pack(side="left")
    ttk.Button(bar, text="Patchliste / Repack…", command=lambda: show_manager(self)).pack(side="left", padx=(6, 0))
    self.avm2_patch_status_var = tk.StringVar()
    ttk.Label(bar, textvariable=self.avm2_patch_status_var).pack(side="right")
    self._update_avm2_patch_status()


def _update_status(self):
    try:
        count = len(current_patches(self.owner))
        self.avm2_patch_status_var.set(f"AVM2-Patches: {count}")
    except Exception:
        self.avm2_patch_status_var.set("AVM2-Patches: kein Film")


def _inspector_refresh(self):
    result = _BASE_INSPECTOR_REFRESH(self)
    try:
        self._update_avm2_patch_status()
    except Exception:
        pass
    return result


def _inspector_close(self):
    window = getattr(self, "_avm2_patch_manager", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE_INSPECTOR_CLOSE(self)


def install():
    global _INSTALLED, _BASE_INSPECTOR_INIT, _BASE_INSPECTOR_CLOSE, _BASE_INSPECTOR_REFRESH
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_INSPECTOR_INIT = avm2.AVM2InspectorWindow.__init__
    _BASE_INSPECTOR_CLOSE = avm2.AVM2InspectorWindow.close
    _BASE_INSPECTOR_REFRESH = avm2.AVM2InspectorWindow.refresh
    avm2.AVM2InspectorWindow.__init__ = _inspector_init
    avm2.AVM2InspectorWindow.close = _inspector_close
    avm2.AVM2InspectorWindow.refresh = _inspector_refresh
    avm2.AVM2InspectorWindow._update_avm2_patch_status = _update_status
    ui_browser.apply_avm2_movie_patches = apply_movie_patches
    ui_browser.patch_gfx_avm2 = patch_gfx_asset
