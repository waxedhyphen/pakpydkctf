"""GUI integration for the three-way PAK/IPS merger."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from pak_merger import (
    PakMergeError,
    merge_ips,
    plan_pak_merge,
    write_ips_result,
)


_INSTALLED = False
_BASE_INIT = None
_POLICY_LABELS = {
    "Bei Konflikt abbrechen": "error",
    "PAK A bevorzugen": "a",
    "PAK B bevorzugen": "b",
}


class PakMergerWindow:
    def __init__(self, app):
        self.app = app
        self.plan = None
        self.ips_result = None
        self.analysis_signature = None

        self.window = tk.Toplevel(app.root)
        self.window.title("PAKPY PAK-/IPS-Dreiwegemerge")
        self.window.geometry("1280x860")
        self.window.minsize(960, 680)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.original_var = tk.StringVar()
        self.pak_a_var = tk.StringVar()
        self.pak_b_var = tk.StringVar()
        self.ips_a_var = tk.StringVar()
        self.ips_b_var = tk.StringVar()
        self.out_pak_var = tk.StringVar()
        self.out_ips_var = tk.StringVar()
        self.policy_var = tk.StringVar(value="Bei Konflikt abbrechen")
        self.status_var = tk.StringVar(
            value="Original-PAK, PAK A und PAK B auswählen"
        )

        outer = ttk.Frame(self.window, padding=12)
        outer.pack(fill="both", expand=True)

        files = ttk.LabelFrame(outer, text="Eingaben", padding=8)
        files.pack(fill="x")
        self._path_row(
            files,
            0,
            "Original-PAK",
            self.original_var,
            "pak_merge_original",
            self._pak_types(),
        )
        self._path_row(
            files,
            1,
            "PAK A",
            self.pak_a_var,
            "pak_merge_a",
            self._pak_types(),
        )
        self._path_row(
            files,
            2,
            "PAK B",
            self.pak_b_var,
            "pak_merge_b",
            self._pak_types(),
        )
        self._path_row(
            files,
            3,
            "IPS A (optional)",
            self.ips_a_var,
            "pak_merge_ips_a",
            self._ips_types(),
            optional=True,
        )
        self._path_row(
            files,
            4,
            "IPS B (optional)",
            self.ips_b_var,
            "pak_merge_ips_b",
            self._ips_types(),
            optional=True,
        )

        options = ttk.Frame(outer)
        options.pack(fill="x", pady=(10, 0))
        ttk.Label(options, text="Unauflösbare Konflikte:").pack(
            side="left"
        )
        ttk.Combobox(
            options,
            textvariable=self.policy_var,
            values=tuple(_POLICY_LABELS),
            state="readonly",
            width=26,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            options,
            text=(
                "Getrennte PAK-Ressourcen, Binärbereiche und "
                "GFX/SWF-Tags werden automatisch kombiniert."
            ),
        ).pack(side="left", padx=(16, 0))
        ttk.Button(
            options,
            text="Analysieren",
            command=self.analyze,
        ).pack(side="right")

        result_frame = ttk.LabelFrame(
            outer,
            text="Merge-Ergebnis pro PAK-Ressource",
            padding=8,
        )
        result_frame.pack(
            fill="both",
            expand=True,
            pady=(10, 0),
        )
        columns = ("type", "name", "status", "sizes", "detail")
        self.tree = ttk.Treeview(
            result_frame,
            columns=columns,
            show="headings",
            height=17,
        )
        settings = {
            "type": ("Typ", 70, False),
            "name": ("Name / UUID", 270, True),
            "status": ("Status", 110, False),
            "sizes": ("Original / A / B / Merge", 180, False),
            "detail": ("Details", 520, True),
        }
        for key, (title, width, stretch) in settings.items():
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, stretch=stretch)
        self.tree.tag_configure("conflict", foreground="#b00020")
        self.tree.tag_configure("auto-merged", foreground="#006400")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(
            result_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        scrollbar.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)

        output_frame = ttk.LabelFrame(
            outer,
            text="Bericht",
            padding=6,
        )
        output_frame.pack(
            fill="both",
            expand=False,
            pady=(10, 0),
        )
        self.output = ScrolledText(
            output_frame,
            wrap="word",
            height=10,
            font=("TkFixedFont", 9),
        )
        self.output.pack(fill="both", expand=True)
        self.output.configure(state="disabled")

        destinations = ttk.LabelFrame(
            outer,
            text="Ausgaben",
            padding=8,
        )
        destinations.pack(fill="x", pady=(10, 0))
        self._save_row(
            destinations,
            0,
            "Zusammengeführte PAK",
            self.out_pak_var,
            "pak_merge_output",
            self._pak_types(),
        )
        self._save_row(
            destinations,
            1,
            "Zusammengeführte IPS32",
            self.out_ips_var,
            "pak_merge_ips_output",
            self._ips_types(),
            optional=True,
        )

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Label(
            actions,
            textvariable=self.status_var,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            actions,
            text="Schließen",
            command=self.close,
        ).pack(side="right")
        ttk.Button(
            actions,
            text="Zusammenführen und speichern",
            command=self.build,
        ).pack(side="right", padx=(0, 8))

        for variable in (
            self.original_var,
            self.pak_a_var,
            self.pak_b_var,
            self.ips_a_var,
            self.ips_b_var,
            self.policy_var,
        ):
            variable.trace_add(
                "write",
                lambda *_args: self.invalidate(),
            )

    @staticmethod
    def _pak_types():
        return (
            ("DKCTF PAK", "*.pak"),
            ("Alle Dateien", "*.*"),
        )

    @staticmethod
    def _ips_types():
        return (
            ("IPS / IPS32", "*.ips"),
            ("Alle Dateien", "*.*"),
        )

    def _open_file(self, key, **options):
        if hasattr(self.app, "ask_open_file"):
            return self.app.ask_open_file(
                key,
                parent=self.window,
                **options,
            )
        return filedialog.askopenfilename(
            parent=self.window,
            **options,
        )

    def _save_file(self, key, **options):
        if hasattr(self.app, "ask_save_file"):
            return self.app.ask_save_file(
                key,
                parent=self.window,
                **options,
            )
        return filedialog.asksaveasfilename(
            parent=self.window,
            **options,
        )

    def _path_row(
        self,
        parent,
        row,
        label,
        variable,
        key,
        filetypes,
        optional=False,
    ):
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            pady=3,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(8, 8),
            pady=3,
        )

        def choose():
            path = self._open_file(
                key,
                title=f"{label} auswählen",
                filetypes=filetypes,
            )
            if path:
                variable.set(path)
                if row == 0 and not self.out_pak_var.get():
                    source = Path(path)
                    self.out_pak_var.set(
                        str(
                            source.with_name(
                                source.stem + "_merged.pak"
                            )
                        )
                    )

        ttk.Button(
            parent,
            text="Auswählen",
            command=choose,
            width=12,
        ).grid(row=row, column=2, pady=3)
        if optional:
            ttk.Button(
                parent,
                text="Leeren",
                command=lambda: variable.set(""),
                width=9,
            ).grid(
                row=row,
                column=3,
                padx=(6, 0),
                pady=3,
            )
        parent.columnconfigure(1, weight=1)

    def _save_row(
        self,
        parent,
        row,
        label,
        variable,
        key,
        filetypes,
        optional=False,
    ):
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            pady=3,
        )
        ttk.Entry(parent, textvariable=variable).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(8, 8),
            pady=3,
        )

        def choose():
            path = self._save_file(
                key,
                title=f"{label} speichern",
                filetypes=filetypes,
                defaultextension=(
                    ".ips" if "IPS" in label else ".pak"
                ),
            )
            if path:
                variable.set(path)

        ttk.Button(
            parent,
            text="Auswählen",
            command=choose,
            width=12,
        ).grid(row=row, column=2, pady=3)
        if optional:
            ttk.Button(
                parent,
                text="Leeren",
                command=lambda: variable.set(""),
                width=9,
            ).grid(
                row=row,
                column=3,
                padx=(6, 0),
                pady=3,
            )
        parent.columnconfigure(1, weight=1)

    def _signature(self):
        return (
            self.original_var.get().strip(),
            self.pak_a_var.get().strip(),
            self.pak_b_var.get().strip(),
            self.ips_a_var.get().strip(),
            self.ips_b_var.get().strip(),
            _POLICY_LABELS.get(
                self.policy_var.get(),
                "error",
            ),
        )

    def invalidate(self):
        self.plan = None
        self.ips_result = None
        self.analysis_signature = None
        self.status_var.set(
            "Eingaben geändert; erneut analysieren"
        )

    def _required_paths(self):
        original, pak_a, pak_b, ips_a, ips_b, policy = (
            self._signature()
        )
        if not original or not pak_a or not pak_b:
            raise PakMergeError(
                "Original-PAK, PAK A und PAK B sind erforderlich"
            )
        for label, value in (
            ("Original-PAK", original),
            ("PAK A", pak_a),
            ("PAK B", pak_b),
        ):
            if not Path(value).is_file():
                raise PakMergeError(
                    f"{label} wurde nicht gefunden: {value}"
                )
        for label, value in (
            ("IPS A", ips_a),
            ("IPS B", ips_b),
        ):
            if value and not Path(value).is_file():
                raise PakMergeError(
                    f"{label} wurde nicht gefunden: {value}"
                )
        return original, pak_a, pak_b, ips_a, ips_b, policy

    def analyze(self):
        try:
            (
                original,
                pak_a,
                pak_b,
                ips_a,
                ips_b,
                policy,
            ) = self._required_paths()
            self.status_var.set(
                "PAKs werden eingelesen und verglichen …"
            )
            self.window.update_idletasks()
            plan = plan_pak_merge(
                original,
                pak_a,
                pak_b,
                policy,
            )
            ips_result = merge_ips(
                ips_a or None,
                ips_b or None,
                policy,
            )
        except Exception as exc:
            self.status_var.set("Analyse fehlgeschlagen")
            messagebox.showerror(
                "PAK-/IPS-Merger",
                str(exc),
                parent=self.window,
            )
            return False
        self.plan = plan
        self.ips_result = ips_result
        self.analysis_signature = self._signature()
        self._show_results()
        return True

    def _show_results(self):
        self.tree.delete(*self.tree.get_children())
        for index, item in enumerate(
            self.plan.items if self.plan else ()
        ):
            sizes = (
                f"{item.original_size} / {item.a_size} / "
                f"{item.b_size} / "
                f"{item.merged_size if item.merged_size is not None else '—'}"
            )
            tag = (
                item.status
                if item.status in {"conflict", "auto-merged"}
                else ""
            )
            self.tree.insert(
                "",
                "end",
                iid=f"merge_{index}",
                values=(
                    item.asset_type,
                    item.name,
                    item.status,
                    sizes,
                    item.detail,
                ),
                tags=(tag,) if tag else (),
            )
        lines = self.plan.summary_lines() if self.plan else []
        if self.ips_result is not None:
            lines.extend(
                (
                    "",
                    "IPS:",
                    "- Records A/B: "
                    f"{self.ips_result.source_a_records} / "
                    f"{self.ips_result.source_b_records}",
                    "- Zusammengeführte Bytes: "
                    f"{self.ips_result.merged_bytes}",
                    f"- Konflikte: {len(self.ips_result.conflicts)}",
                )
            )
            lines.extend(
                f"  - {item.scope}: {item.reason}"
                for item in self.ips_result.conflicts
            )
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", "\n".join(lines))
        self.output.configure(state="disabled")
        total_conflicts = len(
            self.plan.conflicts if self.plan else ()
        ) + len(
            self.ips_result.conflicts if self.ips_result else ()
        )
        self.status_var.set(
            "Analyse abgeschlossen; bereit zum Speichern"
            if total_conflicts == 0
            else (
                "Analyse abgeschlossen: "
                f"{total_conflicts} ungelöste Konflikte"
            )
        )

    def build(self):
        if (
            self.analysis_signature != self._signature()
            or self.plan is None
            or self.ips_result is None
        ):
            if not self.analyze():
                return
        try:
            if self.plan.conflicts:
                raise PakMergeError(
                    "Der PAK-Merge enthält ungelöste Konflikte. "
                    "Konfliktstrategie ändern oder Mods getrennt prüfen."
                )
            if self.ips_result.conflicts:
                raise PakMergeError(
                    "Der IPS-Merge enthält ungelöste Konflikte. "
                    "Konfliktstrategie ändern oder IPS-Dateien prüfen."
                )
            out_pak = self.out_pak_var.get().strip()
            if not out_pak:
                out_pak = self._save_file(
                    "pak_merge_output",
                    title="Zusammengeführte PAK speichern",
                    filetypes=self._pak_types(),
                    defaultextension=".pak",
                )
                if not out_pak:
                    return
                self.out_pak_var.set(out_pak)
            self.status_var.set("PAK wird neu gebaut …")
            self.window.update_idletasks()
            pak_path = self.plan.write(out_pak)
            ips_path = ""
            if self.ips_result.data is not None:
                out_ips = self.out_ips_var.get().strip()
                if not out_ips:
                    out_ips = str(Path(out_pak).with_suffix(".ips"))
                    self.out_ips_var.set(out_ips)
                ips_path = write_ips_result(
                    self.ips_result,
                    out_ips,
                )
        except Exception as exc:
            self.status_var.set("Merge fehlgeschlagen")
            messagebox.showerror(
                "PAK-/IPS-Merger",
                str(exc),
                parent=self.window,
            )
            return
        message = f"PAK geschrieben:\n{pak_path}"
        if ips_path:
            message += f"\n\nIPS32 geschrieben:\n{ips_path}"
        self.status_var.set("Merge erfolgreich gespeichert")
        messagebox.showinfo(
            "PAK-/IPS-Merger",
            message,
            parent=self.window,
        )

    def focus(self):
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def close(self):
        try:
            self.app._pak_merger_window = None
        except Exception:
            pass
        self.window.destroy()


def show_pak_merger(app):
    window = getattr(app, "_pak_merger_window", None)
    try:
        if window is not None and window.window.winfo_exists():
            window.focus()
            return window
    except Exception:
        pass
    app._pak_merger_window = PakMergerWindow(app)
    return app._pak_merger_window


def install(app_class):
    global _INSTALLED, _BASE_INIT
    if _INSTALLED:
        return
    _BASE_INIT = app_class.__init__

    def patched_init(self, *args, **kwargs):
        _BASE_INIT(self, *args, **kwargs)
        self._pak_merger_window = None
        bar = ttk.Frame(
            self.root,
            padding=(14, 0, 14, 10),
        )
        bar.pack(fill="x")
        ttk.Label(bar, text="Mod-Werkzeuge:").pack(side="left")
        ttk.Button(
            bar,
            text="PAK-/IPS-Merger",
            command=lambda: show_pak_merger(self),
        ).pack(side="left", padx=(8, 0))
        self.root.bind(
            "<Control-Shift-M>",
            lambda _event: show_pak_merger(self),
            add="+",
        )

    app_class.__init__ = patched_init
    _INSTALLED = True
