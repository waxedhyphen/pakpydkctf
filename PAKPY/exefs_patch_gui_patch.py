"""Universal GUI for editable ExeFS patch projects and IPS32 export."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from exefs_nso import NsoError, NsoImage
from exefs_patch import (
    ExeFsPatchEntry,
    ExeFsPatchProject,
    export_atmosphere_patch,
    export_emulator_patch,
    load_patch_project,
    preview_patch_project,
    save_patch_project,
)


_INSTALLED = False
_BASE = {}


class PatchEntryDialog:
    def __init__(self, parent, entry=None):
        self.result = None
        self.window = tk.Toplevel(parent)
        self.window.title("ExeFS-Patcheintrag")
        self.window.transient(parent)
        self.window.grab_set()
        self.window.resizable(True, False)

        self.offset_var = tk.StringVar(value=f"0x{entry.memory_offset:X}" if entry else "")
        self.expected_var = tk.StringVar(value=entry.expected.hex(" ").upper() if entry else "")
        self.replacement_var = tk.StringVar(value=entry.replacement.hex(" ").upper() if entry else "")
        self.description_var = tk.StringVar(value=entry.description if entry else "")

        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill="both", expand=True)
        self._row(frame, 0, "NSO-VA", self.offset_var)
        self._row(frame, 1, "Erwartete Bytes", self.expected_var)
        self._row(frame, 2, "Neue Bytes", self.replacement_var)
        self._row(frame, 3, "Beschreibung", self.description_var)

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Abbrechen", command=self.window.destroy).pack(side="right")
        ttk.Button(buttons, text="Übernehmen", command=self.accept).pack(side="right", padx=(0, 8))
        self.window.bind("<Return>", lambda _event: self.accept())
        self.window.bind("<Escape>", lambda _event: self.window.destroy())
        self.window.wait_visibility()
        self.window.focus_force()
        self.window.wait_window()

    @staticmethod
    def _row(frame, row, label, variable):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=variable, width=72).grid(
            row=row, column=1, sticky="ew", padx=(10, 0), pady=4
        )
        frame.columnconfigure(1, weight=1)

    def accept(self):
        try:
            offset_text = self.offset_var.get().strip()
            if not offset_text:
                raise NsoError("NSO-VA fehlt")
            offset = int(offset_text, 0) if offset_text.lower().startswith("0x") else int(offset_text, 16)
            entry = ExeFsPatchEntry(
                memory_offset=offset,
                expected=bytes.fromhex(self.expected_var.get()),
                replacement=bytes.fromhex(self.replacement_var.get()),
                description=self.description_var.get().strip(),
            )
        except (ValueError, NsoError) as exc:
            messagebox.showerror("Ungültiger Patcheintrag", str(exc), parent=self.window)
            return
        self.result = entry
        self.window.destroy()


class ExeFsPatchWindow:
    def __init__(self, app):
        self.app = app
        self.image = None
        self.preview = None
        self.entries = []
        self.project_path = None

        self.window = tk.Toplevel(app.root)
        self.window.title("PAKPY ExeFS Patchprojekt / IPS32")
        self.window.geometry("1180x820")
        self.window.minsize(920, 650)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.path_var = tk.StringVar()
        self.project_path_var = tk.StringVar(value="Neues, ungespeichertes Projekt")
        self.name_var = tk.StringVar(value="Neues ExeFS-Patchprojekt")
        self.group_var = tk.StringVar(value="ExeFS_Patch")
        self.build_id_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Keine NSO-Datei geladen")

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)
        self._build_nso_row(outer)
        self._build_project_row(outer)
        self._build_metadata(outer)
        self._build_entries(outer)
        self._build_actions(outer)

        self.output = ScrolledText(outer, wrap="none", font=("TkFixedFont", 9), height=13)
        self.output.pack(fill="both", expand=True, pady=(10, 0))
        self.output.configure(state="disabled")
        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(fill="x", pady=(8, 0))

        for variable in (self.name_var, self.group_var, self.build_id_var, self.notes_var):
            variable.trace_add("write", lambda *_args: self.invalidate_preview())
        self.use_main_lab(silent=True)

    def _build_nso_row(self, outer):
        row = ttk.LabelFrame(outer, text="Zielmodul", padding=8)
        row.pack(fill="x")
        ttk.Label(row, text="ExeFS main / NSO").pack(side="left")
        ttk.Entry(row, textvariable=self.path_var).pack(side="left", fill="x", expand=True, padx=(8, 8))
        ttk.Button(row, text="Auswählen", command=self.choose_file).pack(side="left")
        ttk.Button(row, text="Einlesen", command=self.load_file).pack(side="left", padx=(8, 0))
        ttk.Button(row, text="Aus ExeFS Lab", command=self.use_main_lab).pack(side="left", padx=(8, 0))

    def _build_project_row(self, outer):
        row = ttk.LabelFrame(outer, text="Projektdatei", padding=8)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, textvariable=self.project_path_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Neu", command=self.new_project).pack(side="right")
        ttk.Button(row, text="JSON laden", command=self.load_project_dialog).pack(side="right", padx=(8, 0))
        ttk.Button(row, text="JSON speichern", command=self.save_project_dialog).pack(side="right", padx=(8, 0))

    def _build_metadata(self, outer):
        frame = ttk.LabelFrame(outer, text="Projektmetadaten", padding=8)
        frame.pack(fill="x", pady=(10, 0))
        ttk.Label(frame, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", padx=(8, 16))
        ttk.Label(frame, text="Patchgruppe").grid(row=0, column=2, sticky="w")
        ttk.Entry(frame, textvariable=self.group_var, width=28).grid(row=0, column=3, sticky="ew", padx=(8, 0))
        ttk.Label(frame, text="Erwartete Build ID").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.build_id_var).grid(row=1, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(8, 0))
        ttk.Label(frame, text="Notiz").grid(row=2, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(frame, textvariable=self.notes_var).grid(row=2, column=1, columnspan=3, sticky="ew", padx=(8, 0), pady=(8, 0))
        frame.columnconfigure(1, weight=3)
        frame.columnconfigure(3, weight=1)

    def _build_entries(self, outer):
        frame = ttk.LabelFrame(outer, text="Beliebige Patcheinträge", padding=8)
        frame.pack(fill="both", expand=True, pady=(10, 0))
        columns = ("offset", "expected", "replacement", "description")
        self.entry_tree = ttk.Treeview(frame, columns=columns, show="headings", height=10)
        headings = {
            "offset": "NSO-VA",
            "expected": "Erwartete Bytes",
            "replacement": "Neue Bytes",
            "description": "Beschreibung",
        }
        widths = {"offset": 110, "expected": 220, "replacement": 220, "description": 420}
        for column in columns:
            self.entry_tree.heading(column, text=headings[column])
            self.entry_tree.column(column, width=widths[column], stretch=column == "description")
        self.entry_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.entry_tree.yview)
        scroll.pack(side="left", fill="y")
        self.entry_tree.configure(yscrollcommand=scroll.set)
        self.entry_tree.bind("<Double-1>", lambda _event: self.edit_entry())

        buttons = ttk.Frame(frame)
        buttons.pack(side="left", fill="y", padx=(10, 0))
        ttk.Button(buttons, text="Hinzufügen", command=self.add_entry).pack(fill="x")
        ttk.Button(buttons, text="Bearbeiten", command=self.edit_entry).pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Entfernen", command=self.remove_entry).pack(fill="x", pady=(8, 0))

    def _build_actions(self, outer):
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(10, 0))
        ttk.Label(row, text="Die geladene main wird nie verändert. Exportiert wird nur eine validierte IPS32-Datei.").pack(side="left")
        ttk.Button(row, text="Validieren", command=self.validate_project).pack(side="right")
        self.emulator_button = ttk.Button(row, text="In Emulator-Modordner exportieren", command=self.export_emulator)
        self.emulator_button.pack(side="right", padx=(0, 8))
        self.atmosphere_button = ttk.Button(row, text="Atmosphère-Struktur exportieren", command=self.export_atmosphere)
        self.atmosphere_button.pack(side="right", padx=(0, 8))
        self._set_export_state(False)

    def close(self):
        try:
            self.app._exefs_patch_window = None
        except Exception:
            pass
        self.window.destroy()

    def focus(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def choose_file(self):
        options = {"title": "ExeFS-main oder NSO auswählen", "filetypes": (("Nintendo Switch NSO / main", "*"), ("Alle Dateien", "*.*"))}
        path = self.app.ask_open_file("exefs_patch_nso", **options) if hasattr(self.app, "ask_open_file") else filedialog.askopenfilename(**options)
        if path:
            self.path_var.set(path)
            self.load_file()

    def use_main_lab(self, silent=False):
        main_lab = getattr(self.app, "_exefs_lab_window", None)
        image = getattr(main_lab, "image", None) if main_lab is not None else None
        if image is None:
            if not silent:
                messagebox.showerror("ExeFS-Patchprojekt", "Im normalen ExeFS Lab ist keine NSO-Datei geladen.", parent=self.window)
            return
        self._accept_image(image)

    def load_file(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror("ExeFS-Patchprojekt", "Bitte zuerst eine NSO-Datei auswählen.", parent=self.window)
            return
        try:
            self._accept_image(NsoImage.from_file(path))
        except NsoError as exc:
            messagebox.showerror("NSO-Fehler", str(exc), parent=self.window)

    def _accept_image(self, image):
        self.image = image
        if image.path is not None:
            self.path_var.set(str(image.path))
        self.invalidate_preview()
        self.status_var.set(f"Geladen: {Path(image.path).name if image.path else '<Speicher>'} · Build ID {image.build_id_hex}")
        self._set_output("NSO geladen. Projekt bearbeiten oder JSON laden und anschließend validieren.")

    def new_project(self):
        self.project_path = None
        self.project_path_var.set("Neues, ungespeichertes Projekt")
        self.name_var.set("Neues ExeFS-Patchprojekt")
        self.group_var.set("ExeFS_Patch")
        self.build_id_var.set(self.image.build_id_hex if self.image is not None else "")
        self.notes_var.set("")
        self.entries = []
        self._refresh_entries()
        self.invalidate_preview()

    def load_project_dialog(self):
        options = {"title": "ExeFS-Patchprojekt laden", "filetypes": (("ExeFS-Patchprojekt", "*.json"), ("Alle Dateien", "*.*"))}
        path = self.app.ask_open_file("exefs_patch_project", **options) if hasattr(self.app, "ask_open_file") else filedialog.askopenfilename(**options)
        if not path:
            return
        try:
            project = load_patch_project(path)
        except NsoError as exc:
            messagebox.showerror("Patchprojekt", str(exc), parent=self.window)
            return
        self._load_project(project, path)

    def _load_project(self, project, path=None):
        self.project_path = Path(path) if path else None
        self.project_path_var.set(str(self.project_path) if self.project_path else "Ungespeichertes Projekt")
        self.name_var.set(project.name)
        self.group_var.set(project.patch_group)
        self.build_id_var.set(project.expected_build_id)
        self.notes_var.set(project.notes)
        self.entries = list(project.entries)
        self._refresh_entries()
        self.invalidate_preview()
        self.status_var.set(f"Projekt geladen: {project.name}")

    def save_project_dialog(self):
        try:
            project = self._project_from_ui()
        except NsoError as exc:
            messagebox.showerror("Patchprojekt", str(exc), parent=self.window)
            return
        options = {
            "title": "ExeFS-Patchprojekt speichern",
            "defaultextension": ".json",
            "filetypes": (("ExeFS-Patchprojekt", "*.json"),),
            "initialfile": self.project_path.name if self.project_path else "exefs_patch_project.json",
        }
        path = self.app.ask_save_file("exefs_patch_project", **options) if hasattr(self.app, "ask_save_file") else filedialog.asksaveasfilename(**options)
        if not path:
            return
        try:
            save_patch_project(project, path)
        except NsoError as exc:
            messagebox.showerror("Patchprojekt", str(exc), parent=self.window)
            return
        self.project_path = Path(path)
        self.project_path_var.set(str(self.project_path))
        self.status_var.set("Patchprojekt als JSON gespeichert")

    def add_entry(self):
        dialog = PatchEntryDialog(self.window)
        if dialog.result is not None:
            self.entries.append(dialog.result)
            self._refresh_entries()
            self.invalidate_preview()

    def edit_entry(self):
        selected = self.entry_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        dialog = PatchEntryDialog(self.window, self.entries[index])
        if dialog.result is not None:
            self.entries[index] = dialog.result
            self._refresh_entries(select=index)
            self.invalidate_preview()

    def remove_entry(self):
        selected = self.entry_tree.selection()
        if not selected:
            return
        for index in sorted((int(item) for item in selected), reverse=True):
            del self.entries[index]
        self._refresh_entries()
        self.invalidate_preview()

    def _refresh_entries(self, select=None):
        for item in self.entry_tree.get_children(""):
            self.entry_tree.delete(item)
        for index, entry in enumerate(self.entries):
            iid = str(index)
            self.entry_tree.insert("", "end", iid=iid, values=(f"0x{entry.memory_offset:X}", entry.expected.hex(" ").upper(), entry.replacement.hex(" ").upper(), entry.description))
        if select is not None and str(select) in self.entry_tree.get_children(""):
            self.entry_tree.selection_set(str(select))

    def _project_from_ui(self):
        return ExeFsPatchProject(
            name=self.name_var.get().strip(),
            patch_group=self.group_var.get().strip(),
            expected_build_id=self.build_id_var.get().strip(),
            notes=self.notes_var.get().strip(),
            entries=tuple(self.entries),
        )

    def invalidate_preview(self):
        self.preview = None
        if hasattr(self, "emulator_button"):
            self._set_export_state(False)

    def validate_project(self):
        if self.image is None:
            messagebox.showerror("ExeFS-Patchprojekt", "Zuerst eine NSO-Datei einlesen.", parent=self.window)
            return
        try:
            preview = preview_patch_project(self.image, self._project_from_ui())
        except NsoError as exc:
            messagebox.showerror("Patchvalidierung", str(exc), parent=self.window)
            return
        self.preview = preview
        self._set_output("\n".join(preview.format_lines()))
        self._set_export_state(preview.valid)
        self.status_var.set("Patch vollständig validiert" if preview.valid else "Build ID oder Originalbytes stimmen nicht")

    def export_emulator(self):
        if not self._require_preview():
            return
        options = {"title": "Root deines Emulator-Modordners auswählen"}
        folder = self.app.ask_directory("exefs_patch_emulator_export", **options) if hasattr(self.app, "ask_directory") else filedialog.askdirectory(**options)
        if not folder:
            return
        try:
            result = export_emulator_patch(self.preview, folder)
        except (OSError, NsoError) as exc:
            messagebox.showerror("Emulator-Export", str(exc), parent=self.window)
            return
        self._show_export("Emulator-Mod exportiert", result)

    def export_atmosphere(self):
        if not self._require_preview():
            return
        options = {"title": "Zielordner für Atmosphère-Struktur auswählen"}
        folder = self.app.ask_directory("exefs_patch_atmosphere_export", **options) if hasattr(self.app, "ask_directory") else filedialog.askdirectory(**options)
        if not folder:
            return
        try:
            result = export_atmosphere_patch(self.preview, folder)
        except (OSError, NsoError) as exc:
            messagebox.showerror("Atmosphère-Export", str(exc), parent=self.window)
            return
        self._show_export("Atmosphère-Patch exportiert", result)

    def _require_preview(self):
        if self.preview is None or not self.preview.valid:
            messagebox.showerror("ExeFS-Patchprojekt", "Zuerst das aktuelle Projekt erfolgreich validieren.", parent=self.window)
            return False
        return True

    def _show_export(self, status, result):
        self._set_output("\n".join([*self.preview.format_lines(), "Exportiert:", *result.values()]))
        self.status_var.set(status)

    def _set_export_state(self, enabled):
        state = "normal" if enabled else "disabled"
        self.emulator_button.configure(state=state)
        self.atmosphere_button.configure(state=state)

    def _set_output(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")


def open_exefs_patch_lab(app):
    current = getattr(app, "_exefs_patch_window", None)
    if current is not None:
        try:
            current.focus()
            return current
        except Exception:
            app._exefs_patch_window = None
    window = ExeFsPatchWindow(app)
    app._exefs_patch_window = window
    return window


def install(App):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE["init"] = App.__init__

    def patched_init(self, root, *args, **kwargs):
        _BASE["init"](self, root, *args, **kwargs)
        tools = getattr(self, "_pakpy_tools_menu", None)
        if tools is None:
            return
        tools.add_command(label="ExeFS Patchprojekt / IPS32", command=lambda: open_exefs_patch_lab(self))
        root.bind("<Control-Shift-P>", lambda _event: open_exefs_patch_lab(self), add="+")

    App.__init__ = patched_init
