"""GUI integration for ExeFS Lab step 1: NSO metadata and address translation."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from exefs_nso import DEFAULT_RUNTIME_BASE, NsoError, NsoImage, parse_int


_INSTALLED = False
_BASE = {}


class ExeFsLabWindow:
    def __init__(self, app):
        self.app = app
        self.image = None
        self.window = tk.Toplevel(app.root)
        self.window.title("PAKPY ExeFS Lab – Schritt 1: NSO")
        self.window.geometry("1080x760")
        self.window.minsize(880, 620)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.path_var = tk.StringVar()
        self.runtime_base_var = tk.StringVar(value=f"0x{DEFAULT_RUNTIME_BASE:X}")
        self.address_var = tk.StringVar()
        self.address_kind_var = tk.StringVar(value="NSO-VA")
        self.status_var = tk.StringVar(value="Keine NSO-Datei geladen")

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)

        file_row = ttk.Frame(outer)
        file_row.pack(fill="x")
        ttk.Label(file_row, text="ExeFS main / NSO").pack(side="left")
        ttk.Entry(file_row, textvariable=self.path_var).pack(
            side="left", fill="x", expand=True, padx=(8, 8)
        )
        ttk.Button(file_row, text="Auswählen", command=self.choose_file).pack(side="left")
        ttk.Button(file_row, text="Einlesen", command=self.load_file).pack(
            side="left", padx=(8, 0)
        )

        translate_row = ttk.LabelFrame(outer, text="Adressübersetzung", padding=8)
        translate_row.pack(fill="x", pady=(10, 0))
        ttk.Label(translate_row, text="Eingabe").pack(side="left")
        ttk.Combobox(
            translate_row,
            textvariable=self.address_kind_var,
            values=("Dateioffset", "NSO-VA", "Runtime-Adresse"),
            state="readonly",
            width=18,
        ).pack(side="left", padx=(8, 8))
        address_entry = ttk.Entry(translate_row, textvariable=self.address_var, width=22)
        address_entry.pack(side="left")
        ttk.Label(translate_row, text="Runtime-Basis").pack(side="left", padx=(18, 0))
        ttk.Entry(translate_row, textvariable=self.runtime_base_var, width=18).pack(
            side="left", padx=(8, 8)
        )
        ttk.Button(translate_row, text="Übersetzen", command=self.translate).pack(side="left")
        address_entry.bind("<Return>", lambda _event: self.translate())

        pane = ttk.Panedwindow(outer, orient="vertical")
        pane.pack(fill="both", expand=True, pady=(10, 0))

        top = ttk.Frame(pane)
        bottom = ttk.Frame(pane)
        pane.add(top, weight=3)
        pane.add(bottom, weight=2)

        summary_group = ttk.LabelFrame(top, text="NSO-Informationen", padding=6)
        summary_group.pack(side="left", fill="both", expand=True)
        self.summary = ScrolledText(summary_group, wrap="word", height=14)
        self.summary.pack(fill="both", expand=True)
        self.summary.configure(state="disabled")

        segment_group = ttk.LabelFrame(top, text="Segmente", padding=6)
        segment_group.pack(side="left", fill="both", expand=True, padx=(10, 0))
        columns = ("file", "memory", "size", "stored", "compression", "hash")
        self.segment_tree = ttk.Treeview(
            segment_group, columns=columns, show="tree headings", height=12
        )
        self.segment_tree.heading("#0", text="Segment")
        self.segment_tree.heading("file", text="Dateibereich")
        self.segment_tree.heading("memory", text="NSO-VA-Bereich")
        self.segment_tree.heading("size", text="Speichergröße")
        self.segment_tree.heading("stored", text="Dateigröße")
        self.segment_tree.heading("compression", text="Komprimiert")
        self.segment_tree.heading("hash", text="Hash")
        self.segment_tree.column("#0", width=80, stretch=False)
        self.segment_tree.column("file", width=170)
        self.segment_tree.column("memory", width=170)
        self.segment_tree.column("size", width=100, anchor="e")
        self.segment_tree.column("stored", width=100, anchor="e")
        self.segment_tree.column("compression", width=90, anchor="center")
        self.segment_tree.column("hash", width=70, anchor="center")
        self.segment_tree.pack(fill="both", expand=True)

        result_group = ttk.LabelFrame(bottom, text="Übersetzung", padding=6)
        result_group.pack(fill="both", expand=True)
        self.result = ScrolledText(result_group, wrap="word", height=9)
        self.result.pack(fill="both", expand=True)
        self.result.configure(state="disabled")

        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(
            fill="x", pady=(8, 0)
        )

    def close(self):
        try:
            self.app._exefs_lab_window = None
        except Exception:
            pass
        self.window.destroy()

    def focus(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def choose_file(self):
        options = {
            "title": "ExeFS-main oder NSO auswählen",
            "filetypes": (("Nintendo Switch NSO / main", "*"), ("Alle Dateien", "*.*")),
        }
        if hasattr(self.app, "ask_open_file"):
            path = self.app.ask_open_file("exefs_nso", **options)
        else:
            path = filedialog.askopenfilename(**options)
        if path:
            self.path_var.set(path)
            self.load_file()

    def load_file(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror(
                "ExeFS Lab", "Bitte zuerst eine NSO-Datei auswählen.", parent=self.window
            )
            return
        try:
            image = NsoImage.from_file(path)
        except NsoError as exc:
            messagebox.showerror("NSO-Fehler", str(exc), parent=self.window)
            self.status_var.set("NSO konnte nicht eingelesen werden")
            return
        self.image = image
        self._set_text(self.summary, "\n".join(image.summary_lines()))
        self._fill_segments(image)
        self._set_text(
            self.result,
            "Adresse eingeben und Dateioffset, NSO-VA oder Runtime-Adresse auswählen.",
        )
        self.status_var.set(
            f"Geladen: {Path(path).name} · Build ID {image.build_id_hex}"
        )

    def _fill_segments(self, image):
        for item in self.segment_tree.get_children(""):
            self.segment_tree.delete(item)
        for segment in image.segments:
            if segment.file_offset is None:
                file_range = "—"
            else:
                file_range = f"0x{segment.file_offset:X}–0x{segment.file_end:X}"
            memory_range = f"0x{segment.memory_offset:X}–0x{segment.memory_end:X}"
            hash_label = "an" if segment.hash_enabled else "aus"
            self.segment_tree.insert(
                "",
                "end",
                text=segment.name,
                values=(
                    file_range,
                    memory_range,
                    f"0x{segment.memory_size:X}",
                    f"0x{segment.stored_size:X}",
                    "ja" if segment.compressed else "nein",
                    hash_label,
                ),
            )

    def translate(self):
        if self.image is None:
            messagebox.showerror(
                "ExeFS Lab", "Zuerst eine NSO-Datei einlesen.", parent=self.window
            )
            return
        try:
            value = parse_int(self.address_var.get(), "Adresse")
            runtime_base = parse_int(self.runtime_base_var.get(), "Runtime-Basis")
            kind = self.address_kind_var.get()
            if kind == "Dateioffset":
                translation = self.image.translate_file_offset(value, runtime_base)
            elif kind == "Runtime-Adresse":
                translation = self.image.translate_runtime_address(value, runtime_base)
            else:
                translation = self.image.translate_memory_offset(value, runtime_base)
        except NsoError as exc:
            messagebox.showerror("Adressfehler", str(exc), parent=self.window)
            return
        lines = [
            f"Eingabe ({kind}): 0x{value:X}",
            f"Runtime-Basis: 0x{runtime_base:X}",
            "",
            *translation.format_lines(),
        ]
        self._set_text(self.result, "\n".join(lines))
        self.status_var.set(f"Adresse 0x{value:X} übersetzt")

    @staticmethod
    def _set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")


def _ensure_tools_menu(app):
    existing = getattr(app, "_pakpy_tools_menu", None)
    if existing is not None:
        return existing

    root = app.root
    menu = getattr(app, "_pakpy_main_menu", None)
    if menu is None:
        configured = str(root.cget("menu") or "")
        if configured:
            try:
                menu = root.nametowidget(configured)
            except Exception:
                menu = None
        if menu is None:
            menu = tk.Menu(root, tearoff=0)
            root.configure(menu=menu)
        app._pakpy_main_menu = menu

    tools = tk.Menu(menu, tearoff=0)
    menu.add_cascade(label="Werkzeuge", menu=tools)
    app._pakpy_tools_menu = tools
    return tools


def open_exefs_lab(app):
    current = getattr(app, "_exefs_lab_window", None)
    if current is not None:
        try:
            current.focus()
            return current
        except Exception:
            app._exefs_lab_window = None
    window = ExeFsLabWindow(app)
    app._exefs_lab_window = window
    return window


def install(App):
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE["init"] = App.__init__

    def patched_init(self, root, *args, **kwargs):
        _BASE["init"](self, root, *args, **kwargs)
        tools = _ensure_tools_menu(self)
        tools.add_command(label="ExeFS Lab (NSO)", command=lambda: open_exefs_lab(self))
        root.bind("<Control-Shift-E>", lambda _event: open_exefs_lab(self), add="+")

    App.__init__ = patched_init
