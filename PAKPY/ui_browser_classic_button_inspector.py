"""Inspector and browser controls for classic buttons and precise HitTests."""
from __future__ import annotations

import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

import ui_browser
import ui_browser_classic_button as classic
import ui_browser_classic_button_runtime as button_runtime
import ui_browser_precise_hit as precise
import ui_browser_state_inspector_patch as inspector

_BASE = {}


def inspect_movie_state(movie, frame, max_depth=64):
    nodes = _BASE["inspect"](movie, frame, max_depth)

    def decorate(values):
        result = []
        for node in values:
            metadata = dict(node.metadata)
            definition = movie.definitions.get(node.character_id) if node.character_id is not None else None
            if isinstance(definition, classic.ClassicButtonDef):
                metadata["classic_button"] = {
                    "version": definition.button_version,
                    "track_as_menu": definition.track_as_menu,
                    "records": len(definition.records),
                    "hit_records": len(definition.hit_records),
                    "action_bindings": len(definition.button_actions),
                    "actions": sum(len(value.actions) for value in definition.button_actions),
                    "bounds": tuple(definition.bounds),
                }
            result.append(inspector.StateNode(
                node.path, node.depth, node.label, node.kind, node.visible,
                node.character_id, node.class_name, metadata, decorate(node.children),
            ))
        return tuple(result)
    return decorate(nodes)


def format_state_node(node, resolver=None):
    text = _BASE["format_node"](node, resolver)
    value = node.metadata.get("classic_button")
    if not value:
        return text
    return text + "\n\nKlassischer SWF-Button:\n" + (
        f"- DefineButton-Version: {value['version']}\n"
        f"- Records / Hit-Records: {value['records']} / {value['hit_records']}\n"
        f"- Action-Blöcke / Aktionen: {value['action_bindings']} / {value['actions']}\n"
        f"- TrackAsMenu: {'ja' if value['track_as_menu'] else 'nein'}"
    )


def classic_snapshot(movie):
    definitions = []
    for character_id, definition in sorted(movie.definitions.items()):
        if not isinstance(definition, classic.ClassicButtonDef):
            continue
        definitions.append({
            "character_id": character_id, "version": definition.button_version,
            "track_as_menu": definition.track_as_menu, "bounds": list(definition.bounds),
            "records": [
                {"character_id": value.character_id, "depth": value.depth,
                 "states": list(value.states), "blend_mode": value.blend_mode,
                 "filter_bytes": len(value.raw_filters)}
                for value in definition.records
            ],
            "actions": [
                {"conditions": list(binding.conditions), "key_code": binding.key_code,
                 "actions": [
                     {"code": action.code, "name": action.name,
                      "argument": action.argument, "safe": action.safe}
                     for action in binding.actions
                 ]}
                for binding in definition.button_actions
            ],
        })
    return {
        "schema": 1, "buttons": definitions,
        "parse_errors": list(getattr(movie, "ui_classic_button_parse_errors", ()) or ()),
        "hit_test": dict(getattr(movie, "ui_precise_hit_diagnostics", {}) or {}),
        "runtime": dict(button_runtime._classic_state(movie)),
    }


class ButtonHitInspector(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("Klassische Buttons / Präzise HitTests")
        self.geometry("1280x820")
        self.minsize(940, 600)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._items = {}
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.button_tab = ttk.Frame(notebook)
        self.hit_tab = ttk.Frame(notebook)
        notebook.add(self.button_tab, text="DefineButton / DefineButton2")
        notebook.add(self.hit_tab, text="Hit-Geometrien")
        self._build_buttons()
        self._build_hits()
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, padding=(8, 0, 8, 8)).pack(fill="x")
        self.refresh()

    def movie(self):
        return getattr(self.owner, "_current_movie", None)

    @staticmethod
    def _set_text(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _build_buttons(self):
        bar = ttk.Frame(self.button_tab, padding=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="JSON exportieren", command=self.export_json).pack(side="right")
        pane = ttk.PanedWindow(self.button_tab, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        left = ttk.Frame(pane)
        self.button_tree = ttk.Treeview(left, columns=("version", "records", "actions"), show="tree headings")
        for column, label, width in (
            ("#0", "Character-ID", 180), ("version", "Version", 90),
            ("records", "Records", 90), ("actions", "Aktionen", 90),
        ):
            self.button_tree.heading(column, text=label)
            self.button_tree.column(column, width=width)
        self.button_tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.button_tree.yview)
        scroll.pack(side="right", fill="y")
        self.button_tree.configure(yscrollcommand=scroll.set)
        self.button_tree.bind("<<TreeviewSelect>>", self.on_button)
        pane.add(left, weight=1)
        self.details = tk.Text(pane, wrap="word", state="disabled")
        pane.add(self.details, weight=2)

    def _build_hits(self):
        self.hit_tree = ttk.Treeview(
            self.hit_tab, columns=("kind", "bounds", "clips"), show="tree headings",
        )
        for column, label, width in (
            ("#0", "Pfad", 520), ("kind", "Geometrie", 150),
            ("bounds", "Bounds", 260), ("clips", "Clips", 70),
        ):
            self.hit_tree.heading(column, text=label)
            self.hit_tree.column(column, width=width)
        self.hit_tree.pack(fill="both", expand=True, padx=6, pady=6)

    def refresh(self):
        movie = self.movie()
        self.button_tree.delete(*self.button_tree.get_children())
        self.hit_tree.delete(*self.hit_tree.get_children())
        self._items.clear()
        if movie is None:
            self.status_var.set("Kein UI-Film ausgewählt")
            return
        for character_id, definition in sorted(movie.definitions.items()):
            if not isinstance(definition, classic.ClassicButtonDef):
                continue
            iid = f"button_{character_id}"
            action_count = sum(len(value.actions) for value in definition.button_actions)
            self.button_tree.insert("", "end", iid=iid, text=str(character_id), values=(
                f"DefineButton{definition.button_version if definition.button_version > 1 else ''}",
                len(definition.records), action_count,
            ))
            self._items[iid] = definition
        mapping = getattr(movie, "ui_precise_hit_geometries", {}) or {}
        for path in (region.path for region in getattr(movie, "ui_input_hit_regions", ()) or ()):
            for geometry in mapping.get(path, ()):
                self.hit_tree.insert("", "end", iid=f"hit_{len(self.hit_tree.get_children())}",
                                     text=path, values=(geometry.kind,
                                     ", ".join(f"{value:.1f}" for value in geometry.bounds),
                                     len(geometry.clips)))
        diag = getattr(movie, "ui_precise_hit_diagnostics", {}) or {}
        self.status_var.set(
            f"{len(self._items)} klassische Buttons | {diag.get('geometries', 0)} Geometrien | "
            f"{diag.get('clip_depth_masks', 0)} ClipDepth-Masken | {diag.get('scroll_rect_clips', 0)} ScrollRects"
        )

    def on_button(self, _event=None):
        selection = self.button_tree.selection()
        definition = self._items.get(selection[0]) if selection else None
        if definition is None:
            return
        lines = [
            f"Character-ID: {definition.character_id}",
            f"Version: {definition.button_version}",
            f"TrackAsMenu: {definition.track_as_menu}",
            f"Bounds: {definition.bounds}", "", "Records:",
        ]
        for record in definition.records:
            lines.append(
                f"- Tiefe {record.depth}, Character {record.character_id}: {', '.join(record.states)}"
            )
        lines.extend(("", "Action-Blöcke:"))
        for binding in definition.button_actions:
            trigger = ", ".join(binding.conditions) or f"Taste {binding.key_code}"
            lines.append(f"- {trigger}")
            for action in binding.actions:
                lines.append(
                    f"    {action.name} {action.argument if action.argument is not None else ''} "
                    f"[{'ausführbar' if action.safe else 'nur Inventar'}]"
                )
        self._set_text(self.details, "\n".join(lines))

    def export_json(self):
        movie = self.movie()
        if movie is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="Button-/HitTest-Inventar speichern", defaultextension=".json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            Path(path).write_text(
                json.dumps(classic_snapshot(movie), ensure_ascii=False, indent=2), encoding="utf-8",
            )

    def close(self):
        self.owner._classic_button_window = None
        self.destroy()


def show_inspector(owner):
    window = getattr(owner, "_classic_button_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh()
            return window
    except Exception:
        pass
    owner._classic_button_window = ButtonHitInspector(owner)
    return owner._classic_button_window
