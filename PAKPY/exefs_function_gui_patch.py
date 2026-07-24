"""GUI for ExeFS function, callgraph, local dataflow and object-field analysis."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from exefs_dataflow import trace_function
from exefs_functions import analyze_function, scan_direct_calls, scan_memory_accesses
from exefs_nso import DEFAULT_RUNTIME_BASE, NsoError, NsoImage, parse_int


_INSTALLED = False
_BASE = {}


class ExeFsFunctionWindow:
    def __init__(self, app):
        self.app = app
        self.image = None
        self.direct_calls = None
        self.window = tk.Toplevel(app.root)
        self.window.title("PAKPY ExeFS Lab – Funktion / Datenfluss")
        self.window.geometry("1050x760")
        self.window.minsize(820, 580)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.path_var = tk.StringVar()
        self.runtime_base_var = tk.StringVar(value=f"0x{DEFAULT_RUNTIME_BASE:X}")
        self.function_address_var = tk.StringVar(value="0x0")
        self.function_limit_var = tk.StringVar(value="4096")
        self.field_offset_var = tk.StringVar(value="0x840")
        self.field_32bit_var = tk.BooleanVar(value=True)
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
        ttk.Button(file_row, text="Aus ExeFS Lab", command=self.use_main_lab).pack(
            side="left", padx=(8, 0)
        )

        function_group = ttk.LabelFrame(outer, text="Funktion", padding=8)
        function_group.pack(fill="x", pady=(10, 0))
        ttk.Label(function_group, text="Start-VA").pack(side="left")
        function_entry = ttk.Entry(
            function_group, textvariable=self.function_address_var, width=18
        )
        function_entry.pack(side="left", padx=(6, 12))
        ttk.Label(function_group, text="Max. Instruktionen").pack(side="left")
        ttk.Entry(function_group, textvariable=self.function_limit_var, width=9).pack(
            side="left", padx=(6, 12)
        )
        ttk.Label(function_group, text="Runtime-Basis").pack(side="left")
        ttk.Entry(function_group, textvariable=self.runtime_base_var, width=18).pack(
            side="left", padx=(6, 12)
        )
        ttk.Button(
            function_group, text="Analysieren", command=self.analyze_function_view
        ).pack(side="right")
        function_entry.bind("<Return>", lambda _event: self.analyze_function_view())

        field_group = ttk.LabelFrame(outer, text="Objektfeld-Zugriffe", padding=8)
        field_group.pack(fill="x", pady=(8, 0))
        ttk.Label(field_group, text="Offset").pack(side="left")
        field_entry = ttk.Entry(field_group, textvariable=self.field_offset_var, width=16)
        field_entry.pack(side="left", padx=(6, 12))
        ttk.Checkbutton(
            field_group, text="nur 32-Bit", variable=self.field_32bit_var
        ).pack(side="left")
        ttk.Button(
            field_group, text="Alle Zugriffe suchen", command=self.scan_field_accesses
        ).pack(side="right")
        field_entry.bind("<Return>", lambda _event: self.scan_field_accesses())

        self.output = ScrolledText(outer, wrap="none", font=("TkFixedFont", 9))
        self.output.pack(fill="both", expand=True, pady=(10, 0))
        self.output.configure(state="disabled")

        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(
            fill="x", pady=(8, 0)
        )

        self.use_main_lab(silent=True)

    def close(self):
        try:
            self.app._exefs_function_window = None
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
            path = self.app.ask_open_file("exefs_function_nso", **options)
        else:
            path = filedialog.askopenfilename(**options)
        if path:
            self.path_var.set(path)
            self.load_file()

    def use_main_lab(self, silent=False):
        main_lab = getattr(self.app, "_exefs_lab_window", None)
        image = getattr(main_lab, "image", None) if main_lab is not None else None
        if image is None:
            if not silent:
                messagebox.showerror(
                    "ExeFS-Funktionsanalyse",
                    "Im normalen ExeFS Lab ist keine NSO-Datei geladen.",
                    parent=self.window,
                )
            return
        self._accept_image(image)

    def load_file(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror(
                "ExeFS-Funktionsanalyse", "Bitte zuerst eine NSO-Datei auswählen.",
                parent=self.window,
            )
            return
        try:
            image = NsoImage.from_file(path)
        except NsoError as exc:
            messagebox.showerror("NSO-Fehler", str(exc), parent=self.window)
            return
        self._accept_image(image)

    def _accept_image(self, image):
        self.image = image
        self.direct_calls = None
        if image.path is not None:
            self.path_var.set(str(image.path))
        suggested = image.suggested_code_start()
        self.function_address_var.set(f"0x{suggested:X}")
        self._set_output(
            "NSO geladen. Funktionsstart eingeben oder im String-/Callback-Tracer "
            "die native Callback-Adresse übernehmen."
        )
        self.status_var.set(
            f"Geladen: {Path(image.path).name if image.path else '<Speicher>'} · "
            f"Build ID {image.build_id_hex}"
        )

    def analyze_function_view(self):
        if self.image is None:
            messagebox.showerror(
                "ExeFS-Funktionsanalyse", "Zuerst eine NSO-Datei einlesen.",
                parent=self.window,
            )
            return
        try:
            start = parse_int(self.function_address_var.get(), "Funktionsstart")
            limit = parse_int(self.function_limit_var.get(), "Instruktionslimit")
            runtime_base = parse_int(self.runtime_base_var.get(), "Runtime-Basis")
            if self.direct_calls is None:
                self.status_var.set("Direkter Call-Index wird aufgebaut …")
                self.window.update_idletasks()
                self.direct_calls = scan_direct_calls(self.image)
            summary = analyze_function(
                self.image,
                start,
                max_instructions=limit,
                runtime_base=runtime_base,
                calls_index=self.direct_calls,
            )
            flow = trace_function(summary)
        except NsoError as exc:
            messagebox.showerror("Funktionsanalyse", str(exc), parent=self.window)
            return
        lines = [*summary.format_lines(), "", "---", "", *flow.format_lines()]
        self._set_output("\n".join(lines))
        self.status_var.set(
            f"Funktion 0x{start:X}: {len(summary.instructions)} Instruktionen · "
            f"{len(summary.calls)} Calls · {len(flow.conditions)} Bedingungen"
        )

    def scan_field_accesses(self):
        if self.image is None:
            messagebox.showerror(
                "ExeFS-Funktionsanalyse", "Zuerst eine NSO-Datei einlesen.",
                parent=self.window,
            )
            return
        try:
            displacement = parse_int(self.field_offset_var.get(), "Objektfeld-Offset")
            accesses = scan_memory_accesses(self.image, displacement=displacement)
        except NsoError as exc:
            messagebox.showerror("Objektfeldsuche", str(exc), parent=self.window)
            return
        if self.field_32bit_var.get():
            accesses = tuple(item for item in accesses if item.width == 4)
        lines = [
            f"Zugriffe auf Offset 0x{displacement:X}: {len(accesses)}",
            f"Filter 32-Bit: {'ja' if self.field_32bit_var.get() else 'nein'}",
            "",
        ]
        lines.extend(item.format_line() for item in accesses)
        if not accesses:
            lines.append("Keine Zugriffe gefunden.")
        self._set_output("\n".join(lines))
        self.status_var.set(f"{len(accesses)} Zugriffe auf Objektfeld +0x{displacement:X}")

    def _set_output(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")


def open_exefs_function_lab(app):
    current = getattr(app, "_exefs_function_window", None)
    if current is not None:
        try:
            current.focus()
            return current
        except Exception:
            app._exefs_function_window = None
    window = ExeFsFunctionWindow(app)
    app._exefs_function_window = window
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
        tools.add_command(
            label="ExeFS Funktion / Datenfluss",
            command=lambda: open_exefs_function_lab(self),
        )
        root.bind(
            "<Control-Shift-F>", lambda _event: open_exefs_function_lab(self), add="+"
        )

    App.__init__ = patched_init
