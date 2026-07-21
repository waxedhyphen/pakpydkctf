"""Install the Scaleform UI Browser in the main PAK GUI."""
import tkinter as tk
from tkinter import messagebox

from pak_core import PakError
from ui_browser import open_ui_browser


def _is_gfx_entry(entry):
    return str(entry.get("type", "")).strip().upper() == "GFX"


def install(App):
    original_init = App.__init__
    original_show_selected = App.show_selected
    original_clear_all = App.clear_all

    def __init__(self, root):
        original_init(self, root)
        anchor = _find_button(self.root, "Mesh Viewer")
        if anchor is None:
            anchor = _find_button(self.root, "Modellpaket exportieren")
        parent = anchor.master if anchor is not None else self.root
        self.ui_browser_button = tk.Button(
            parent,
            text="UI Browser",
            command=self.open_ui_browser,
            width=16,
            state="disabled",
        )
        if anchor is not None:
            try:
                self.ui_browser_button.pack(side="left", padx=(8, 0), after=anchor)
            except Exception:
                self.ui_browser_button.pack(side="left", padx=(8, 0))
        else:
            self.ui_browser_button.pack(side="bottom", pady=(0, 8))
        self.update_ui_browser_state()

    def _find_selected_gfx_entry(self):
        if self.parsed is None:
            return None
        try:
            item = self.get_selected_item()
        except Exception:
            return None
        if item.get("kind") == "entry":
            entry = item.get("entry")
            if entry and _is_gfx_entry(entry):
                return entry
        return None

    def update_ui_browser_state(self):
        button = getattr(self, "ui_browser_button", None)
        if button is None:
            return
        has_gfx = False
        if self.parsed is not None:
            has_gfx = any(_is_gfx_entry(entry) for entry in self.parsed.get("entries", []))
            if not has_gfx:
                store = getattr(self, "require_store", None)
                for item in getattr(store, "required_paks", []) if store is not None else []:
                    parsed = item.get("parsed") or {}
                    if any(_is_gfx_entry(entry) for entry in parsed.get("entries", [])):
                        has_gfx = True
                        break
        try:
            button.configure(state="normal" if has_gfx else "disabled")
        except Exception:
            pass

    def open_ui_browser_window(self):
        if self.parsed is None:
            messagebox.showinfo("UI Browser", "Bitte zuerst eine PAK-Datei einlesen.")
            return
        try:
            open_ui_browser(
                self.root,
                self.parsed,
                entry=self._find_selected_gfx_entry(),
                require_store=getattr(self, "require_store", None),
            )
        except PakError as exc:
            messagebox.showerror("UI Browser", str(exc))
        except Exception as exc:
            messagebox.showerror("UI Browser", f"UI Browser konnte nicht geöffnet werden:\n{exc}")

    def show_selected(self, event=None):
        try:
            return original_show_selected(self, event)
        finally:
            self.update_ui_browser_state()

    def clear_all(self):
        try:
            return original_clear_all(self)
        finally:
            self.update_ui_browser_state()

    App.__init__ = __init__
    App._find_selected_gfx_entry = _find_selected_gfx_entry
    App.update_ui_browser_state = update_ui_browser_state
    App.open_ui_browser = open_ui_browser_window
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
