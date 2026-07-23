"""UI integration for the generic SWF timeline writer."""
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
DIDDY = timeline.TimelineCopySpec(12, "diddy", 15, "diddy", "fk")


def _context(owner):
    return movie_tool._selection_context(owner)


def _result(owner):
    _key, _source, _index, _container, record = _context(owner)
    patches = tuple(movie_tool.current_patches(owner))
    base = movie_tool.apply_movie_patches(record.data, patches).movie_data if patches else record.data
    result = timeline.copy_instance(base, DIDDY)
    report = dict(result.report)
    report["active_avm2_patches_included"] = len(patches)
    return timeline.TimelinePatchResult(result.movie_data, report, result.signature)


def _gfx(owner, result):
    _key, source, index, _container, _record = _context(owner)
    asset = pak_core.get_entry_asset(source.parsed, source.entry)
    return gfx_repack.rebuild_gfx_asset(asset, index, result.movie_data)


def _text(report):
    before = ", ".join(f"{x['name']}@{x['depth']}→Char {x['character_id']}" for x in report["target_before"])
    after = ", ".join(f"{x['name']}@{x['depth']}→Char {x['character_id']}" for x in report.get("target_after", ())) or "noch nicht eingesetzt"
    return "\n".join((
        f"Quelle: Sprite {report['source_sprite_id']} / {report['source_name']} / Character {report['character_id']}",
        f"Ziel: Sprite {report['target_sprite_id']} / {report['target_name']}",
        f"Position: Matrix von {report['anchor_name']} ({report['matrix_hex'] or '00'})",
        f"Tiefe: {report['target_depth']} ({report['depth_reason']})",
        f"Vorher: {before}",
        f"Danach: {after}",
        f"AVM2-Patches einbezogen: {report.get('active_avm2_patches_included', 0)}",
        f"Strukturprüfung: {report.get('structural_validation', 'noch nicht ausgeführt')}",
        "Spielwirkung: nicht bestätigt",
    ))


class DiddyTimelineDialog(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("P1-Diddy statisch einsetzen")
        self.geometry("720x440")
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Noch nichts verändert")
        ttk.Label(self, textvariable=self.status).pack(anchor="w", padx=10, pady=10)
        self.report = tk.Text(self, wrap="word", state="disabled")
        self.report.pack(fill="both", expand=True, padx=10)
        row = ttk.Frame(self, padding=10)
        row.pack(fill="x")
        ttk.Button(row, text="Plan prüfen", command=self.plan).pack(side="left")
        ttk.Button(row, text="Vorschau anwenden", command=self.preview).pack(side="left", padx=6)
        ttk.Button(row, text="Vorschau zurücksetzen", command=self.restore).pack(side="left")
        ttk.Button(row, text="GFX speichern…", command=self.save_gfx).pack(side="right")
        ttk.Button(row, text="PAK neu bauen…", command=self.save_pak).pack(side="right", padx=6)
        self.plan()

    def _show(self, value):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", str(value))
        self.report.configure(state="disabled")

    def _selected(self):
        _key, _source, _index, _container, record = _context(self.owner)
        if record.name != "MenuCharacter.swf":
            raise timeline.TimelinePatchError("Zuerst MenuCharacter.swf auswählen")
        return record

    def plan(self):
        try:
            record = self._selected()
            patches = tuple(movie_tool.current_patches(self.owner))
            base = movie_tool.apply_movie_patches(record.data, patches).movie_data if patches else record.data
            report = timeline.plan_copy_instance(base, DIDDY)
            report["active_avm2_patches_included"] = len(patches)
            self._show(_text(report))
            self.status.set("Plan geprüft; noch nichts verändert")
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def preview(self):
        try:
            record = self._selected()
            _key, _source, _index, container, _record = _context(self.owner)
            result = _result(self.owner)
            movie_tool._preview_from_movie_data(self.owner, record, result.movie_data, container)
            self._show(_text(result.report))
            self.status.set("Vorschau aktiv; PAK unverändert")
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def restore(self):
        try:
            record = self._selected()
            _key, _source, _index, container, _record = _context(self.owner)
            movie_tool._preview_from_movie_data(self.owner, record, record.data, container)
            self.status.set("Vorschau zurückgesetzt")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def save_gfx(self):
        try:
            _key, source, _index, _container, _record = _context(self.owner)
            asset = _gfx(self.owner, _result(self.owner))
            name = Path(source.entry.get("display_name") or source.entry.get("name") or "UI").stem
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".GFX", initialfile=name + "_timeline_patched.GFX")
            if path:
                Path(path).write_bytes(asset)
                self.status.set(f"GFX gespeichert: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def save_pak(self):
        try:
            _key, source, _index, _container, _record = _context(self.owner)
            asset = _gfx(self.owner, _result(self.owner))
            src = Path(source.parsed.get("path", "UIPak.pak"))
            path = filedialog.asksaveasfilename(parent=self, defaultextension=".pak", initialfile=src.stem + "_timeline_patched.pak")
            if path:
                pak_core.rebuild_pak(source.parsed, {int(source.entry["index"]): {"asset_bytes": asset}}, path)
                self.status.set(f"PAK gespeichert: {Path(path).name}; Spielwirkung nicht bestätigt")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def close(self):
        self.owner._diddy_timeline_dialog = None
        self.destroy()


def show_dialog(owner):
    window = getattr(owner, "_diddy_timeline_dialog", None)
    if window is not None:
        try:
            if window.winfo_exists():
                window.lift()
                return window
        except Exception:
            pass
    owner._diddy_timeline_dialog = DiddyTimelineDialog(owner)
    return owner._diddy_timeline_dialog


def _init(self, *args, **kwargs):
    _BASE_INIT(self, *args, **kwargs)
    self._diddy_timeline_dialog = None
    bar = ttk.Frame(self, padding=(8, 0, 8, 6))
    bar.pack(fill="x")
    ttk.Button(bar, text="P1-Diddy statisch einsetzen…", command=lambda: show_dialog(self)).pack(side="left")
    ttk.Label(bar, text="SWF-Timeline; Vorschau und PAK-Bau getrennt").pack(side="left", padx=10)


def _close(self):
    window = getattr(self, "_diddy_timeline_dialog", None)
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
