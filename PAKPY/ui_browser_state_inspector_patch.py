"""Add a recursive display-list/state inspector to the static UI Browser.

The inspector exposes the exact display state currently rendered by the preview:
root frame, nested sprite frame 1, depths, instance names, character/class IDs,
visibility, transforms, color transforms, clip depths, Scale9 grids, filters,
blend modes, font classes and initial text.  It is intentionally read-only; the
next phase adds manual overrides and reusable state presets.

All changes are preview-only. GFX/SWF/TXTR/MSBT bytes and repacking are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk

import ui_browser


_INSTALLED = False


@dataclass(frozen=True)
class StateNode:
    path: str
    depth: int
    label: str
    kind: str
    visible: bool
    character_id: int | None = None
    class_name: str = ""
    metadata: dict = field(default_factory=dict)
    children: tuple["StateNode", ...] = ()


def _short_name(value):
    text = str(value or "")
    return text.rsplit("::", 1)[-1].rsplit(".", 1)[-1] if text else ""


def _matrix_dict(matrix):
    return {
        "a": float(getattr(matrix, "a", 1.0)),
        "b": float(getattr(matrix, "b", 0.0)),
        "c": float(getattr(matrix, "c", 0.0)),
        "d": float(getattr(matrix, "d", 1.0)),
        "tx": float(getattr(matrix, "tx", 0.0)),
        "ty": float(getattr(matrix, "ty", 0.0)),
    }


def _color_dict(color):
    return {
        "r_mult": float(getattr(color, "r_mult", 1.0)),
        "g_mult": float(getattr(color, "g_mult", 1.0)),
        "b_mult": float(getattr(color, "b_mult", 1.0)),
        "a_mult": float(getattr(color, "a_mult", 1.0)),
        "r_add": int(getattr(color, "r_add", 0)),
        "g_add": int(getattr(color, "g_add", 0)),
        "b_add": int(getattr(color, "b_add", 0)),
        "a_add": int(getattr(color, "a_add", 0)),
    }


def _filter_metadata(item):
    result = []
    for record in tuple(getattr(item, "filters", ()) or ()):
        result.append({
            "id": int(getattr(record, "filter_id", -1)),
            "name": str(getattr(record, "name", f"Filter{getattr(record, 'filter_id', '?')}")),
            "size": len(bytes(getattr(record, "raw", b""))),
        })
    return result


def _definition_kind(definition):
    vector_type = getattr(ui_browser, "VectorShapeDef", ())
    if isinstance(definition, ui_browser.SpriteDef):
        return "MovieClip"
    if isinstance(definition, ui_browser.EditTextDef):
        return "EditText"
    if vector_type and isinstance(definition, vector_type):
        return "VectorShape"
    if isinstance(definition, ui_browser.ShapeDef):
        return "Shape"
    if definition is None:
        return "Unbekannt"
    return type(definition).__name__


def _node_label(movie, item, definition):
    if getattr(item, "name", ""):
        return str(item.name)
    if getattr(item, "class_name", ""):
        return _short_name(item.class_name)
    character_id = getattr(item, "character_id", None)
    symbol = getattr(movie, "symbol_classes", {}).get(character_id, "") if character_id is not None else ""
    if symbol:
        return _short_name(symbol)
    if isinstance(definition, ui_browser.EditTextDef):
        return str(getattr(definition, "variable_name", "") or f"Text {character_id}")
    return f"depth {int(getattr(item, 'depth', 0))}"


def _metadata_for(movie, item, definition, sprite_frame):
    character_id = getattr(item, "character_id", None)
    blend_mode = int(getattr(item, "blend_mode", 0) or 0)
    blend_names = getattr(ui_browser, "BLEND_NAMES", {})
    metadata = {
        "depth": int(getattr(item, "depth", 0)),
        "instance_name": str(getattr(item, "name", "") or ""),
        "character_id": character_id,
        "class_name": str(getattr(item, "class_name", "") or ""),
        "symbol_class": str(getattr(movie, "symbol_classes", {}).get(character_id, "") or ""),
        "visible": bool(getattr(item, "visible", True)),
        "matrix": _matrix_dict(getattr(item, "matrix", ui_browser.Affine())),
        "color_transform": _color_dict(getattr(item, "color", ui_browser.IDENTITY_COLOR)),
        "clip_depth": getattr(item, "clip_depth", None),
        "blend_mode": {"id": blend_mode, "name": str(blend_names.get(blend_mode, blend_mode))},
        "filters": _filter_metadata(item),
        "ratio": getattr(item, "ratio", None),
        "cache_as_bitmap": getattr(item, "cache_as_bitmap", None),
        "opaque_background": getattr(item, "opaque_background", None),
    }
    grids = getattr(movie, "scaling_grids", {})
    grid = grids.get(character_id) if character_id is not None else None
    if grid is not None:
        metadata["scale9_grid"] = tuple(getattr(grid, "rect", ()))

    if isinstance(definition, ui_browser.SpriteDef):
        metadata.update({
            "sprite_frame": int(sprite_frame),
            "sprite_frame_count": int(getattr(definition, "frame_count", 1)),
            "sprite_labels": dict(getattr(definition, "labels", {}) or {}),
        })
    elif isinstance(definition, ui_browser.EditTextDef):
        text = str(getattr(definition, "initial_text", "") or "")
        metadata.update({
            "bounds": tuple(getattr(definition, "bounds", ())),
            "variable_name": str(getattr(definition, "variable_name", "") or ""),
            "text": text,
            "display_text": text or f"[{getattr(definition, 'variable_name', '') or 'Text'}]",
            "font_class": str(getattr(definition, "font_class", "") or ""),
            "font_height": float(getattr(definition, "font_height", 0.0) or 0.0),
            "html": bool(getattr(definition, "html", False)),
            "multiline": bool(getattr(definition, "multiline", False)),
            "word_wrap": bool(getattr(definition, "word_wrap", False)),
            "align": getattr(definition, "align", 0),
        })
    elif definition is not None and hasattr(definition, "bounds"):
        metadata["bounds"] = tuple(getattr(definition, "bounds", ()))
    return metadata


def inspect_display_state(movie, display, path_prefix="root", stack=(), level=0, max_depth=64):
    """Return recursive StateNode objects for one already-built display list."""
    if level > max_depth:
        return ()
    result = []
    for depth in sorted(display):
        item = display[depth]
        character_id = getattr(item, "character_id", None)
        definition = movie.definitions.get(character_id) if character_id is not None else None
        kind = "External" if getattr(item, "class_name", "") else _definition_kind(definition)
        label = _node_label(movie, item, definition)
        segment = f"{int(depth)}:{label}"
        path = f"{path_prefix}/{segment}"
        metadata = _metadata_for(movie, item, definition, 1)
        children = ()
        if isinstance(definition, ui_browser.SpriteDef):
            if character_id in stack:
                metadata["cycle"] = True
            elif level >= max_depth:
                metadata["max_depth_reached"] = True
            else:
                child_display = ui_browser.build_display_list(definition.tags, 1)
                children = inspect_display_state(
                    movie,
                    child_display,
                    path,
                    stack + (character_id,),
                    level + 1,
                    max_depth,
                )
        result.append(StateNode(
            path=path,
            depth=int(depth),
            label=label,
            kind=kind,
            visible=bool(getattr(item, "visible", True)),
            character_id=character_id,
            class_name=str(getattr(item, "class_name", "") or ""),
            metadata=metadata,
            children=children,
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    frame = max(1, min(int(frame), int(getattr(movie, "frame_count", 1) or 1)))
    display = ui_browser.build_display_list(movie.root_tags, frame)
    return inspect_display_state(movie, display, "root", (), 0, max_depth)


def node_to_dict(node):
    return {
        "path": node.path,
        "depth": node.depth,
        "label": node.label,
        "kind": node.kind,
        "visible": node.visible,
        "character_id": node.character_id,
        "class_name": node.class_name,
        "metadata": node.metadata,
        "children": [node_to_dict(child) for child in node.children],
    }


def state_snapshot(movie, frame, nodes=None):
    nodes = inspect_movie_state(movie, frame) if nodes is None else tuple(nodes)
    return {
        "frame": int(frame),
        "frame_count": int(getattr(movie, "frame_count", 1)),
        "frame_rate": float(getattr(movie, "frame_rate", 0.0)),
        "stage_bounds": tuple(getattr(movie, "stage_bounds", ())),
        "nodes": [node_to_dict(node) for node in nodes],
    }


def _node_search_text(node):
    try:
        metadata = json.dumps(node.metadata, ensure_ascii=False, sort_keys=True)
    except Exception:
        metadata = str(node.metadata)
    return " ".join((
        node.path,
        node.label,
        node.kind,
        node.class_name,
        str(node.character_id),
        metadata,
    )).lower()


def filter_state_nodes(nodes, query="", visible_only=False):
    query = str(query or "").strip().lower()
    result = []
    for node in tuple(nodes or ()):
        children = filter_state_nodes(node.children, query, visible_only)
        own_match = not query or query in _node_search_text(node)
        visible_match = node.visible or not visible_only
        if (own_match and visible_match) or children:
            result.append(StateNode(
                node.path, node.depth, node.label, node.kind, node.visible,
                node.character_id, node.class_name, node.metadata, children,
            ))
    return tuple(result)


def format_state_node(node, resolver=None):
    meta = node.metadata
    lines = [
        f"Pfad: {node.path}",
        f"Tiefe: {node.depth}",
        f"Typ: {node.kind}",
        f"Sichtbar: {'ja' if node.visible else 'nein'}",
        f"Instanz: {meta.get('instance_name') or '-'}",
        f"Character-ID: {node.character_id if node.character_id is not None else '-'}",
        f"Klasse: {node.class_name or meta.get('symbol_class') or '-'}",
    ]
    matrix = meta.get("matrix", {})
    lines.extend([
        "",
        "Matrix:",
        f"- a={matrix.get('a', 1):.6g}, b={matrix.get('b', 0):.6g}",
        f"- c={matrix.get('c', 0):.6g}, d={matrix.get('d', 1):.6g}",
        f"- x={matrix.get('tx', 0):.3f}, y={matrix.get('ty', 0):.3f}",
    ])
    color = meta.get("color_transform", {})
    lines.extend([
        "",
        "ColorTransform:",
        f"- Mult: {color.get('r_mult', 1):.4g}, {color.get('g_mult', 1):.4g}, "
        f"{color.get('b_mult', 1):.4g}, {color.get('a_mult', 1):.4g}",
        f"- Add: {color.get('r_add', 0)}, {color.get('g_add', 0)}, "
        f"{color.get('b_add', 0)}, {color.get('a_add', 0)}",
    ])
    if meta.get("clip_depth") is not None:
        lines.append(f"ClipDepth: {meta['clip_depth']}")
    blend = meta.get("blend_mode", {})
    if int(blend.get("id", 0) or 0) not in (0, 1):
        lines.append(f"Blend Mode: {blend.get('name')} ({blend.get('id')})")
    if meta.get("filters"):
        lines.extend(["", "Filter:"])
        lines.extend(f"- {item['name']} (ID {item['id']}, {item['size']} Bytes)" for item in meta["filters"])
    if meta.get("scale9_grid"):
        lines.append(f"Scale9: {meta['scale9_grid']}")
    if node.kind == "MovieClip":
        lines.extend([
            "",
            f"MovieClip-Frame: {meta.get('sprite_frame', 1)} / {meta.get('sprite_frame_count', 1)}",
        ])
        labels = meta.get("sprite_labels", {})
        if labels:
            lines.append("Labels:")
            lines.extend(f"- {name}: {frame}" for name, frame in sorted(labels.items(), key=lambda item: item[1]))
    if node.kind == "EditText":
        lines.extend([
            "",
            f"Variable: {meta.get('variable_name') or '-'}",
            f"Fontklasse: {meta.get('font_class') or '-'}",
            f"Fontgröße: {meta.get('font_height', 0):g}",
            f"HTML: {'ja' if meta.get('html') else 'nein'}",
            "Text:",
            str(meta.get("display_text", "")),
        ])
    if node.class_name and resolver is not None:
        try:
            lookup = resolver.get(node.class_name)
            lines.extend([
                "",
                "Externe Ressource:",
                f"- UUID: {getattr(lookup, 'uuid_hex', '') or '-'}",
                f"- Quelle: {getattr(lookup, 'source', '') or '-'}",
            ])
            image = getattr(lookup, "image", None)
            if image is not None:
                lines.append(f"- Bild: {image.width} × {image.height}")
            if getattr(lookup, "error", ""):
                lines.append(f"- Fehler: {lookup.error}")
        except Exception as exc:
            lines.extend(["", f"Ressourcenauflösung: {exc}"])
    if meta.get("cycle"):
        lines.extend(["", "Hinweis: Rekursive Sprite-Referenz; Unterbaum wurde beendet."])
    lines.append(f"Unterobjekte: {len(node.children)}")
    return "\n".join(lines)


class StateInspectorWindow(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI State Inspector")
        self.geometry("1220x760")
        self.minsize(860, 520)
        self.transient(owner)
        self.query_var = tk.StringVar()
        self.visible_only_var = tk.BooleanVar(value=False)
        self.summary_var = tk.StringVar(value="Kein UI-State geladen")
        self._all_nodes = ()
        self._node_by_iid = {}
        self._iid_by_path = {}

        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")
        ttk.Label(toolbar, text="Suche:").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.query_var, width=34)
        search.pack(side="left", padx=(5, 10))
        ttk.Checkbutton(
            toolbar, text="Nur sichtbare",
            variable=self.visible_only_var, command=self.rebuild_tree,
        ).pack(side="left")
        ttk.Button(toolbar, text="Aktualisieren", command=self.refresh).pack(side="left", padx=(10, 0))
        ttk.Button(toolbar, text="Alles öffnen", command=lambda: self._set_open(True)).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Alles schließen", command=lambda: self._set_open(False)).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="JSON speichern", command=self.save_json).pack(side="right")
        ttk.Label(self, textvariable=self.summary_var, padding=(8, 0, 8, 5)).pack(fill="x")

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        left = ttk.Frame(main)
        self.tree = ttk.Treeview(
            left,
            columns=("depth", "kind", "visible", "id"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Instanzpfad")
        self.tree.heading("depth", text="Tiefe")
        self.tree.heading("kind", text="Typ")
        self.tree.heading("visible", text="Sichtbar")
        self.tree.heading("id", text="Char/Klasse")
        self.tree.column("#0", width=330, stretch=True)
        self.tree.column("depth", width=58, anchor="e", stretch=False)
        self.tree.column("kind", width=105, stretch=False)
        self.tree.column("visible", width=65, anchor="center", stretch=False)
        self.tree.column("id", width=180, stretch=True)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _event: self.copy_selected_path())
        main.add(left, weight=1)

        right = ttk.Frame(main)
        self.details = tk.Text(right, width=55, wrap="word", state="disabled")
        self.details.pack(side="left", fill="both", expand=True)
        details_scroll = ttk.Scrollbar(right, orient="vertical", command=self.details.yview)
        details_scroll.pack(side="left", fill="y")
        self.details.configure(yscrollcommand=details_scroll.set)
        main.add(right, weight=1)

        bottom = ttk.Frame(self, padding=(8, 0, 8, 8))
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Pfad kopieren", command=self.copy_selected_path).pack(side="right")

        self.query_var.trace_add("write", lambda *_args: self.rebuild_tree())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<F5>", lambda _event: self.refresh())
        search.focus_set()
        self.refresh()

    def close(self):
        if getattr(self.owner, "_state_inspector_window", None) is self:
            self.owner._state_inspector_window = None
        self.destroy()

    def _owner_state(self):
        movie = getattr(self.owner, "_current_movie", None)
        frame_var = getattr(self.owner, "frame_var", None)
        frame = int(frame_var.get()) if frame_var is not None else 1
        return movie, frame

    def refresh(self):
        movie, frame = self._owner_state()
        if movie is None:
            self._all_nodes = ()
            self.summary_var.set("Kein GFX-Film ausgewählt")
        else:
            self._all_nodes = inspect_movie_state(movie, frame)
            total = sum(1 for _ in self._walk(self._all_nodes))
            visible = sum(1 for node in self._walk(self._all_nodes) if node.visible)
            self.summary_var.set(
                f"Root-Frame {frame} / {movie.frame_count} | "
                f"{total} Instanzen | {visible} sichtbar"
            )
        self.rebuild_tree()

    @staticmethod
    def _walk(nodes):
        for node in nodes:
            yield node
            yield from StateInspectorWindow._walk(node.children)

    def rebuild_tree(self):
        if not self.winfo_exists():
            return
        selected_path = ""
        selection = self.tree.selection()
        if selection:
            selected = self._node_by_iid.get(selection[0])
            selected_path = selected.path if selected is not None else ""
        open_paths = {
            node.path for iid, node in self._node_by_iid.items()
            if self.tree.exists(iid) and self.tree.item(iid, "open")
        }
        self.tree.delete(*self.tree.get_children(""))
        self._node_by_iid.clear()
        self._iid_by_path.clear()
        nodes = filter_state_nodes(
            self._all_nodes,
            self.query_var.get(),
            self.visible_only_var.get(),
        )
        movie, frame = self._owner_state()
        root_label = f"Root Frame {frame}" if movie is not None else "Kein Film"
        root_iid = self.tree.insert("", "end", text=root_label, open=True, values=("", "Root", "ja", ""))
        for node in nodes:
            self._insert_node(root_iid, node, open_paths)
        iid = self._iid_by_path.get(selected_path)
        if iid:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        elif self.tree.get_children(root_iid):
            first = self.tree.get_children(root_iid)[0]
            self.tree.selection_set(first)
            self.tree.focus(first)
            self._on_select()
        else:
            self._set_details("Keine Instanz entspricht dem Filter.")

    def _insert_node(self, parent, node, open_paths):
        iid = f"state_{len(self._node_by_iid)}"
        char_or_class = node.class_name or (
            str(node.character_id) if node.character_id is not None else ""
        )
        self.tree.insert(
            parent,
            "end",
            iid=iid,
            text=node.label,
            open=node.path in open_paths,
            values=(node.depth, node.kind, "ja" if node.visible else "nein", char_or_class),
        )
        self._node_by_iid[iid] = node
        self._iid_by_path[node.path] = iid
        for child in node.children:
            self._insert_node(iid, child, open_paths)

    def _on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        node = self._node_by_iid.get(selection[0])
        if node is None:
            return
        resolver = getattr(self.owner, "_current_resolver", None)
        self._set_details(format_state_node(node, resolver))

    def _set_details(self, text):
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _set_open(self, state):
        def recurse(iid):
            self.tree.item(iid, open=state)
            for child in self.tree.get_children(iid):
                recurse(child)
        for iid in self.tree.get_children(""):
            recurse(iid)

    def copy_selected_path(self):
        selection = self.tree.selection()
        if not selection:
            return
        node = self._node_by_iid.get(selection[0])
        if node is None:
            return
        self.clipboard_clear()
        self.clipboard_append(node.path)

    def save_json(self):
        movie, frame = self._owner_state()
        if movie is None:
            return
        record = getattr(self.owner, "_current_movie_record", None)
        name = getattr(record, "name", "ui_state")
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(name))
        path = filedialog.asksaveasfilename(
            parent=self,
            title="UI-State-Snapshot speichern",
            defaultextension=".json",
            initialfile=f"{safe}_frame_{frame:03d}_state.json",
            filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        snapshot = state_snapshot(movie, frame, self._all_nodes)
        snapshot["movie"] = str(name)
        source = getattr(self.owner, "_current_source", None)
        snapshot["pak"] = str(getattr(source, "source_label", "") or "")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_init = ui_browser.UIBrowser.__init__
    original_render = ui_browser.UIBrowser._render
    original_close = ui_browser.UIBrowser.close

    def browser_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._state_inspector_window = None
        bar = ttk.Frame(self, padding=(8, 0, 8, 5))
        bar.pack(fill="x")
        ttk.Button(
            bar,
            text="State Inspector",
            command=self.open_state_inspector,
        ).pack(side="left")
        ttk.Label(
            bar,
            text="F6: Display-List und aktuellen UI-State untersuchen",
        ).pack(side="left", padx=(10, 0))
        self.bind("<F6>", lambda _event: self.open_state_inspector())

    def open_state_inspector(self):
        window = getattr(self, "_state_inspector_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.deiconify()
                    window.lift()
                    window.focus_force()
                    window.refresh()
                    return window
            except Exception:
                pass
        window = StateInspectorWindow(self)
        self._state_inspector_window = window
        return window

    def browser_render(self):
        result = original_render(self)
        window = getattr(self, "_state_inspector_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.refresh()
            except Exception:
                pass
        return result

    def browser_close(self):
        window = getattr(self, "_state_inspector_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except Exception:
                pass
        self._state_inspector_window = None
        return original_close(self)

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser.open_state_inspector = open_state_inspector
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser.close = browser_close
    ui_browser.StateNode = StateNode
    ui_browser.inspect_movie_state = inspect_movie_state
    ui_browser.state_snapshot = state_snapshot
