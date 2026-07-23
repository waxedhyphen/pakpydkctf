"""Universal UI for validated SWF timeline instance insertion."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pak_core
import ui_browser
import ui_browser_avm2_patch_tool as movie_tool
import ui_browser_avm2_repack as gfx_repack
import ui_browser_timeline_repack as timeline

_INSTALLED = False
_BASE_INIT = None
_BASE_CLOSE = None


def _context(owner):
    return movie_tool._selection_context(owner)


def _base_movie(owner):
    _key, _source, _index, container, record = _context(owner)
    patches = tuple(movie_tool.current_patches(owner))
    movie_data = (
        movie_tool.apply_movie_patches(record.data, patches).movie_data
        if patches else record.data
    )
    return record, container, movie_data, len(patches)


def _result(owner, spec):
    _record, _container, movie_data, patch_count = _base_movie(owner)
    result = timeline.copy_instance(movie_data, spec)
    report = dict(result.report)
    report["active_avm2_patches_included"] = patch_count
    return timeline.TimelinePatchResult(result.movie_data, report, result.signature)


def _gfx(owner, result):
    _key, source, index, _container, _record = _context(owner)
    asset = pak_core.get_entry_asset(source.parsed, source.entry)
    return gfx_repack.rebuild_gfx_asset(asset, index, result.movie_data)


def _report_text(report):
    before = ", ".join(
        f"{item['name']}@{item['depth']}→Char {item['character_id']}"
        for item in report["target_before"]
    ) or "leer"
    after = ", ".join(
        f"{item['name']}@{item['depth']}→Char {item['character_id']}"
        for item in report.get("target_after", ())
    ) or "noch nicht eingesetzt"
    return "\n".join((
        f"Quelle: Sprite {report['source_sprite_id']} / {report['source_name']} / Character {report['character_id']}",
        f"Ziel: Sprite {report['target_sprite_id']} / Name {report['target_name']}",
        f"Positionsanker: {report['anchor_name'] or 'Quellmatrix'} ({report['matrix_hex'] or '00'})",
        f"Tiefe: {report['target_depth']} ({report['depth_reason']})",
        f"Vorher: {before}",
        f"Danach: {after}",
        f"AVM2-Patches einbezogen: {report.get('active_avm2_patches_included', 0)}",
        f"Strukturprüfung: {report.get('structural_validation', 'noch nicht ausgeführt')}",
        "Spielwirkung: nicht bestätigt",
    ))


def _sprite_ids(structure):
    return tuple(
        str(sprite_id)
        for sprite_id, items in sorted(structure.items())
        if any(item.get("name") for item in items)
    )


def _names(structure, sprite_id):
    return tuple(
        item["name"]
        for item in structure.get(int(sprite_id), ())
        if item.get("name")
    )


class TimelineEditorDialog(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.structure = {}
        self.title("SWF-Timeline-Editor")
        self.geometry("820x650")
        self.minsize(720, 560)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.status = tk.StringVar(value="Noch nichts verändert")
        self.source_sprite = tk.StringVar()
        self.source_name = tk.StringVar()
        self.target_sprite = tk.StringVar()
        self.target_name = tk.StringVar()
        self.anchor_name = tk.StringVar()
        self.depth = tk.StringVar()
        self.replace_existing = tk.BooleanVar(value=False)

        ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=10, pady=(10, 6))

        form = ttk.LabelFrame(self, text="Instanz kopieren", padding=10)
        form.pack(fill="x", padx=10, pady=(0, 8))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Quell-Sprite:").grid(row=0, column=0, sticky="w", pady=3)
        self.source_sprite_box = ttk.Combobox(
            form, textvariable=self.source_sprite, state="readonly",
        )
        self.source_sprite_box.grid(row=0, column=1, sticky="ew", pady=3)
        self.source_sprite_box.bind("<<ComboboxSelected>>", self._source_changed)

        ttk.Label(form, text="Quellinstanz:").grid(row=1, column=0, sticky="w", pady=3)
        self.source_name_box = ttk.Combobox(
            form, textvariable=self.source_name, state="readonly",
        )
        self.source_name_box.grid(row=1, column=1, sticky="ew", pady=3)
        self.source_name_box.bind("<<ComboboxSelected>>", self._source_name_changed)

        ttk.Label(form, text="Ziel-Sprite:").grid(row=2, column=0, sticky="w", pady=3)
        self.target_sprite_box = ttk.Combobox(
            form, textvariable=self.target_sprite, state="readonly",
        )
        self.target_sprite_box.grid(row=2, column=1, sticky="ew", pady=3)
        self.target_sprite_box.bind("<<ComboboxSelected>>", self._target_changed)

        ttk.Label(form, text="Neuer Instanzname:").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(form, textvariable=self.target_name).grid(
            row=3, column=1, sticky="ew", pady=3,
        )

        ttk.Label(form, text="Positionsanker im Ziel:").grid(row=4, column=0, sticky="w", pady=3)
        self.anchor_box = ttk.Combobox(
            form, textvariable=self.anchor_name, state="readonly",
        )
        self.anchor_box.grid(row=4, column=1, sticky="ew", pady=3)

        ttk.Label(form, text="Zieltiefe:").grid(row=5, column=0, sticky="w", pady=3)
        depth_row = ttk.Frame(form)
        depth_row.grid(row=5, column=1, sticky="ew", pady=3)
        ttk.Entry(depth_row, textvariable=self.depth, width=18).pack(side="left")
        ttk.Label(depth_row, text="leer = automatisch; Dezimal oder 0xHex").pack(
            side="left", padx=(8, 0),
        )

        ttk.Checkbutton(
            form,
            text="Vorhandene gleichnamige Zielinstanz ersetzen",
            variable=self.replace_existing,
        ).grid(row=6, column=1, sticky="w", pady=(5, 1))

        ttk.Button(
            form, text="Struktur neu einlesen", command=self.refresh_structure,
        ).grid(row=0, column=2, rowspan=2, padx=(10, 0), sticky="n")

        self.report = tk.Text(self, wrap="word", state="disabled")
        self.report.pack(fill="both", expand=True, padx=10)

        row = ttk.Frame(self, padding=10)
        row.pack(fill="x")
        ttk.Button(row, text="Plan prüfen", command=self.plan).pack(side="left")
        ttk.Button(row, text="Vorschau anwenden", command=self.preview).pack(
            side="left", padx=6,
        )
        ttk.Button(row, text="Vorschau zurücksetzen", command=self.restore).pack(
            side="left",
        )
        ttk.Button(row, text="GFX speichern…", command=self.save_gfx).pack(side="right")
        ttk.Button(row, text="PAK neu bauen…", command=self.save_pak).pack(
            side="right", padx=6,
        )

        self.refresh_structure()

    def _show(self, value):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", str(value))
        self.report.configure(state="disabled")

    def _selected(self):
        record, _container, _movie_data, _patch_count = _base_movie(self.owner)
        return record

    def _source_changed(self, _event=None):
        names = _names(self.structure, self.source_sprite.get())
        self.source_name_box.configure(values=names)
        if self.source_name.get() not in names:
            self.source_name.set(names[0] if names else "")
        self._source_name_changed()

    def _source_name_changed(self, _event=None):
        if not self.target_name.get().strip():
            self.target_name.set(self.source_name.get())

    def _target_changed(self, _event=None):
        names = _names(self.structure, self.target_sprite.get())
        values = ("",) + names
        self.anchor_box.configure(values=values)
        if self.anchor_name.get() not in values:
            self.anchor_name.set("")

    def refresh_structure(self):
        try:
            _record, _container, movie_data, patch_count = _base_movie(self.owner)
            structure = timeline.inspect_sprites(movie_data)
            sprite_ids = _sprite_ids(structure)
            if not sprite_ids:
                raise timeline.TimelinePatchError(
                    "Der ausgewählte Film enthält keine benannten Sprite-Instanzen"
                )
            old_source = self.source_sprite.get()
            old_target = self.target_sprite.get()
            self.structure = structure
            self.source_sprite_box.configure(values=sprite_ids)
            self.target_sprite_box.configure(values=sprite_ids)
            self.source_sprite.set(old_source if old_source in sprite_ids else sprite_ids[0])
            self.target_sprite.set(old_target if old_target in sprite_ids else sprite_ids[0])
            self._source_changed()
            self._target_changed()
            self.status.set(
                f"Struktur eingelesen: {len(sprite_ids)} benannte Sprites; "
                f"{patch_count} AVM2-Patches berücksichtigt"
            )
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def _spec(self):
        source_name = self.source_name.get().strip()
        target_name = self.target_name.get().strip()
        if not source_name or not target_name:
            raise timeline.TimelinePatchError(
                "Quellinstanz und neuer Instanzname sind erforderlich"
            )
        depth_text = self.depth.get().strip()
        try:
            depth = int(depth_text, 0) if depth_text else None
        except ValueError as exc:
            raise timeline.TimelinePatchError(
                f"Ungültige Zieltiefe: {depth_text!r}"
            ) from exc
        return timeline.TimelineCopySpec(
            source_sprite_id=int(self.source_sprite.get()),
            source_name=source_name,
            target_sprite_id=int(self.target_sprite.get()),
            target_name=target_name,
            anchor_name=self.anchor_name.get().strip(),
            depth=depth,
            replace_existing=bool(self.replace_existing.get()),
        )

    def plan(self):
        try:
            _record, _container, movie_data, patch_count = _base_movie(self.owner)
            report = timeline.plan_copy_instance(movie_data, self._spec())
            report["active_avm2_patches_included"] = patch_count
            self._show(_report_text(report))
            self.status.set("Plan geprüft; noch nichts verändert")
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def preview(self):
        try:
            record, container, _movie_data, _patch_count = _base_movie(self.owner)
            result = _result(self.owner, self._spec())
            movie_tool._preview_from_movie_data(
                self.owner, record, result.movie_data, container,
            )
            self._show(_report_text(result.report))
            self.status.set("Vorschau aktiv; PAK unverändert")
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def restore(self):
        try:
            record, container, _movie_data, _patch_count = _base_movie(self.owner)
            movie_tool._preview_from_movie_data(
                self.owner, record, record.data, container,
            )
            self.status.set("Vorschau zurückgesetzt")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def save_gfx(self):
        try:
            _key, source, _index, _container, _record = _context(self.owner)
            asset = _gfx(self.owner, _result(self.owner, self._spec()))
            name = Path(
                source.entry.get("display_name")
                or source.entry.get("name")
                or "UI"
            ).stem
            path = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".GFX",
                initialfile=name + "_timeline_patched.GFX",
            )
            if path:
                Path(path).write_bytes(asset)
                self.status.set(f"GFX gespeichert: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def save_pak(self):
        try:
            _key, source, _index, _container, _record = _context(self.owner)
            asset = _gfx(self.owner, _result(self.owner, self._spec()))
            src = Path(source.parsed.get("path", "UIPak.pak"))
            path = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".pak",
                initialfile=src.stem + "_timeline_patched.pak",
            )
            if path:
                pak_core.rebuild_pak(
                    source.parsed,
                    {int(source.entry["index"]): {"asset_bytes": asset}},
                    path,
                )
                self.status.set(
                    f"PAK gespeichert: {Path(path).name}; Spielwirkung nicht bestätigt"
                )
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def close(self):
        self.owner._timeline_editor_dialog = None
        self.destroy()


def show_dialog(owner):
    window = getattr(owner, "_timeline_editor_dialog", None)
    if window is not None:
        try:
            if window.winfo_exists():
                window.lift()
                return window
        except Exception:
            pass
    owner._timeline_editor_dialog = TimelineEditorDialog(owner)
    return owner._timeline_editor_dialog


def _init(self, *args, **kwargs):
    _BASE_INIT(self, *args, **kwargs)
    self._timeline_editor_dialog = None
    bar = ttk.Frame(self, padding=(8, 0, 8, 6))
    bar.pack(fill="x")
    ttk.Button(
        bar,
        text="SWF-Timeline-Editor…",
        command=lambda: show_dialog(self),
    ).pack(side="left")
    ttk.Label(
        bar,
        text="Universell: Quelle, Ziel, Name, Anker, Tiefe und Ersetzen frei wählbar",
    ).pack(side="left", padx=10)


def _close(self):
    window = getattr(self, "_timeline_editor_dialog", None)
    try:
        if window is not None and window.winfo_exists():
            window.destroy()
    except Exception:
        pass
    return _BASE_CLOSE(self)


def install():
    global _INSTALLED, _BASE_INIT, _BASE_CLOSE
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_INIT = ui_browser.UIBrowser.__init__
    _BASE_CLOSE = ui_browser.UIBrowser.close
    ui_browser.UIBrowser.__init__ = _init
    ui_browser.UIBrowser.close = _close
    ui_browser.copy_timeline_instance = timeline.copy_instance
    ui_browser.plan_timeline_instance_copy = timeline.plan_copy_instance
