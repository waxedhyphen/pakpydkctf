"""GUI for validated ExeFS patch previews and Atmosphere IPS32 export."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from exefs_nso import NsoError, NsoImage
from exefs_patch import export_atmosphere_patch, hardmode_keep_p2_active_entries, preview_project


_INSTALLED = False
_BASE = {}


PROFILES = {
    "Hard Mode: P2 aktiv halten – Test 1": (
        "DKCTF Hard Mode – P2 active test 1",
        hardmode_keep_p2_active_entries,
        "DKCTF_HardMode_P2_Test1",
    ),
}


class ExeFsPatchWindow:
    def __init__(self, app):
        self.app = app
        self.image = None
        self.preview = None
        self.window = tk.Toplevel(app.root)
        self.window.title("PAKPY ExeFS Patchvorschau / IPS32")
        self.window.geometry("980x700")
        self.window.minsize(780, 560)
        self.window.protocol("WM_DELETE_WINDOW", self.close)

        self.path_var = tk.StringVar()
        self.profile_var = tk.StringVar(value=next(iter(PROFILES)))
        self.group_var = tk.StringVar(value=PROFILES[self.profile_var.get()][2])
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

        profile_row = ttk.LabelFrame(outer, text="Patchprofil", padding=8)
        profile_row.pack(fill="x", pady=(10, 0))
        ttk.Label(profile_row, text="Profil").pack(side="left")
        combo = ttk.Combobox(
            profile_row,
            textvariable=self.profile_var,
            values=tuple(PROFILES),
            state="readonly",
            width=40,
        )
        combo.pack(side="left", padx=(8, 12))
        combo.bind("<<ComboboxSelected>>", self.on_profile_changed)
        ttk.Label(profile_row, text="Patchgruppe").pack(side="left")
        ttk.Entry(profile_row, textvariable=self.group_var, width=30).pack(
            side="left", fill="x", expand=True, padx=(8, 12)
        )
        ttk.Button(profile_row, text="Validieren", command=self.validate_profile).pack(
            side="right"
        )

        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=(8, 0))
        ttk.Label(
            action_row,
            text=(
                "Es wird nie die geladene main verändert. Export erzeugt nur "
                "atmosphere/exefs_patches/..."
            ),
        ).pack(side="left")
        self.export_button = ttk.Button(
            action_row, text="Atmosphère-Patch exportieren", command=self.export_patch
        )
        self.export_button.pack(side="right")
        self.export_button.configure(state="disabled")

        self.output = ScrolledText(outer, wrap="none", font=("TkFixedFont", 9))
        self.output.pack(fill="both", expand=True, pady=(10, 0))
        self.output.configure(state="disabled")

        ttk.Label(outer, textvariable=self.status_var, anchor="w").pack(
            fill="x", pady=(8, 0)
        )
        self.use_main_lab(silent=True)

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
        options = {
            "title": "ExeFS-main oder NSO auswählen",
            "filetypes": (("Nintendo Switch NSO / main", "*"), ("Alle Dateien", "*.*")),
        }
        if hasattr(self.app, "ask_open_file"):
            path = self.app.ask_open_file("exefs_patch_nso", **options)
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
                    "ExeFS-Patchvorschau",
                    "Im normalen ExeFS Lab ist keine NSO-Datei geladen.",
                    parent=self.window,
                )
            return
        self._accept_image(image)

    def load_file(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror(
                "ExeFS-Patchvorschau", "Bitte zuerst eine NSO-Datei auswählen.",
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
        self.preview = None
        self.export_button.configure(state="disabled")
        if image.path is not None:
            self.path_var.set(str(image.path))
        self._set_output(
            "NSO geladen. Das gewählte Profil muss zuerst exakt gegen die "
            "Originalbytes validiert werden."
        )
        self.status_var.set(
            f"Geladen: {Path(image.path).name if image.path else '<Speicher>'} · "
            f"Build ID {image.build_id_hex}"
        )

    def on_profile_changed(self, _event=None):
        _name, _factory, group = PROFILES[self.profile_var.get()]
        self.group_var.set(group)
        self.preview = None
        self.export_button.configure(state="disabled")

    def validate_profile(self):
        if self.image is None:
            messagebox.showerror(
                "ExeFS-Patchvorschau", "Zuerst eine NSO-Datei einlesen.",
                parent=self.window,
            )
            return
        try:
            project_name, factory, _group = PROFILES[self.profile_var.get()]
            preview = preview_project(self.image, project_name, factory())
        except (KeyError, NsoError) as exc:
            messagebox.showerror("Patchvalidierung", str(exc), parent=self.window)
            return
        self.preview = preview
        self._set_output("\n".join(preview.format_lines()))
        self.export_button.configure(state="normal" if preview.valid else "disabled")
        self.status_var.set(
            "Patch vollständig validiert" if preview.valid else "Originalbytes stimmen nicht"
        )

    def export_patch(self):
        if self.preview is None or not self.preview.valid:
            messagebox.showerror(
                "ExeFS-Patchvorschau", "Zuerst das Profil erfolgreich validieren.",
                parent=self.window,
            )
            return
        options = {"title": "Zielordner für Atmosphère-Struktur auswählen"}
        if hasattr(self.app, "ask_directory"):
            folder = self.app.ask_directory("exefs_patch_export", **options)
        else:
            folder = filedialog.askdirectory(**options)
        if not folder:
            return
        try:
            result = export_atmosphere_patch(self.preview, folder, self.group_var.get())
        except (OSError, NsoError) as exc:
            messagebox.showerror("IPS32-Export", str(exc), parent=self.window)
            return
        self._set_output(
            "\n".join(
                [
                    *self.preview.format_lines(),
                    "Exportiert:",
                    result["patch"],
                    result["manifest"],
                    result["report"],
                ]
            )
        )
        self.status_var.set("Atmosphère-IPS32-Patch exportiert")

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
        tools.add_command(
            label="ExeFS Patchvorschau / IPS32",
            command=lambda: open_exefs_patch_lab(self),
        )
        root.bind(
            "<Control-Shift-P>", lambda _event: open_exefs_patch_lab(self), add="+"
        )

    App.__init__ = patched_init
