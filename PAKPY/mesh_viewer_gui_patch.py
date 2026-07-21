"""Install the mesh viewer button and selection-state integration."""
import tkinter as tk
from tkinter import messagebox

from pak_core import PakError
from mesh_viewer import open_mesh_viewer


MODEL_TYPES = {"CMDL", "SMDL", "WMDL"}


def install(App):
    original_init = App.__init__
    original_show_selected = App.show_selected
    original_clear_all = App.clear_all

    def __init__(self, root):
        original_init(self, root)
        self.mesh_viewer_button = tk.Button(
            self.root,
            text="Mesh Viewer",
            command=self.open_selected_mesh_viewer,
            width=16,
            state="disabled",
        )

        anchor = _find_button(self.root, "Modellpaket exportieren")
        if anchor is not None:
            self.mesh_viewer_button.configure(master=anchor.master)
            try:
                self.mesh_viewer_button.pack(side="left", padx=(8, 0), after=anchor)
            except Exception:
                self.mesh_viewer_button.pack(side="left", padx=(8, 0))
        else:
            self.mesh_viewer_button.pack(side="bottom", pady=(0, 8))
        self.update_mesh_viewer_state()

    def _find_selected_model_entry(self):
        if self.parsed is None:
            return None
        try:
            item = self.get_selected_item()
        except Exception:
            return None
        if item.get("kind") == "entry":
            entry = item.get("entry")
            if entry and entry.get("type") in MODEL_TYPES:
                return entry
        return None

    def update_mesh_viewer_state(self):
        button = getattr(self, "mesh_viewer_button", None)
        if button is None:
            return
        state = "normal" if self._find_selected_model_entry() is not None else "disabled"
        try:
            button.configure(state=state)
        except Exception:
            pass

    def open_selected_mesh_viewer(self):
        entry = self._find_selected_model_entry()
        if entry is None:
            messagebox.showinfo("Mesh Viewer", "Bitte zuerst einen CMDL-, SMDL- oder WMDL-Eintrag auswählen.")
            self.update_mesh_viewer_state()
            return
        try:
            open_mesh_viewer(self.root, self.parsed, entry)
        except PakError as exc:
            messagebox.showerror("Mesh Viewer", str(exc))
        except Exception as exc:
            messagebox.showerror("Mesh Viewer", f"Viewer konnte nicht geöffnet werden:\n{exc}")

    def show_selected(self, event=None):
        try:
            return original_show_selected(self, event)
        finally:
            self.update_mesh_viewer_state()

    def clear_all(self):
        try:
            return original_clear_all(self)
        finally:
            self.update_mesh_viewer_state()

    App.__init__ = __init__
    App._find_selected_model_entry = _find_selected_model_entry
    App.update_mesh_viewer_state = update_mesh_viewer_state
    App.open_selected_mesh_viewer = open_selected_mesh_viewer
    App.show_selected = show_selected
    App.clear_all = clear_all


def _find_button(widget, text):
    for child in widget.winfo_children():
        try:
            if isinstance(child, tk.Button) and child.cget("text") == text:
                return child
        except Exception:
            pass
        found = _find_button(child, text)
        if found is not None:
            return found
    return None
