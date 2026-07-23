"""Searchable universal UI for validated SWF timeline instance insertion."""
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
_DASH = "—"


def _context(owner):
    return movie_tool._selection_context(owner)


def _base_movie(owner):
    _key, _source, _index, container, record = _context(owner)
    patches = tuple(movie_tool.current_patches(owner))
    movie_data = (
        movie_tool.apply_movie_patches(record.data, patches).movie_data
        if patches else record.data
    )
    return record, container, movie_data, len(patches)


def _result(owner, spec):
    _record, _container, movie_data, patch_count = _base_movie(owner)
    result = timeline.copy_instance(movie_data, spec)
    report = dict(result.report)
    report["active_avm2_patches_included"] = patch_count
    return timeline.TimelinePatchResult(result.movie_data, report, result.signature)


def _gfx(owner, result):
    _key, source, index, _container, _record = _context(owner)
    asset = pak_core.get_entry_asset(source.parsed, source.entry)
    return gfx_repack.rebuild_gfx_asset(asset, index, result.movie_data)


def _report_text(report):
    before = ", ".join(
        f"{item['name']}@{item['depth']}→Char {item['character_id']}"
        for item in report["target_before"]
    ) or "leer"
    after = ", ".join(
        f"{item['name']}@{item['depth']}→Char {item['character_id']}"
        for item in report.get("target_after", ())
    ) or "noch nicht eingesetzt"
    return "\n".join((
        f"Quelle: Sprite {report['source_sprite_id']} / {report['source_name']} / Character {report['character_id']}",
        f"Ziel: Sprite {report['target_sprite_id']} / Name {report['target_name']}",
        f"Positionsanker: {report['anchor_name'] or 'Quellmatrix'} ({report['matrix_hex'] or '00'})",
        f"Tiefe: {report['target_depth']} ({report['depth_reason']})",
        f"Vorher: {before}",
        f"Danach: {after}",
        f"AVM2-Patches einbezogen: {report.get('active_avm2_patches_included', 0)}",
        f"Strukturprüfung: {report.get('structural_validation', 'noch nicht ausgeführt')}",
        "Spielwirkung: nicht bestätigt",
    ))


def _placement_dict(depth, item):
    return {
        "depth": depth,
        "name": item.name,
        "character_id": item.character_id,
        "matrix_hex": item.matrix.hex(" ").upper(),
    }


def _inspect_movie(movie_data):
    structure = timeline.inspect_sprites(movie_data)
    _data, _signature, _start, root_records, _tail = timeline._root(movie_data)
    root_items = tuple(
        _placement_dict(depth, item)
        for depth, item in sorted(timeline._first_frame(root_records).items())
    )
    return structure, root_items


def _unique(values):
    return tuple(dict.fromkeys(value for value in values if value))


def _reference_map(structure, root_items=()):
    references = {sprite_id: [] for sprite_id in structure}
    for parent_sprite_id, items in [(None, root_items), *sorted(structure.items())]:
        for item in items:
            character_id = item.get("character_id")
            if character_id not in references:
                continue
            references[character_id].append({
                "parent_sprite_id": parent_sprite_id,
                "depth": item.get("depth"),
                "name": item.get("name") or "",
                "matrix_hex": item.get("matrix_hex") or "",
            })
    return {key: tuple(value) for key, value in references.items()}


def _reference_location(reference):
    parent = (
        "ROOT" if reference["parent_sprite_id"] is None
        else f"Sprite {reference['parent_sprite_id']}"
    )
    return f"{parent}@Tiefe {reference['depth']}"


def _search_blob(*values):
    return " ".join(str(value) for value in values if value is not None).casefold()


def _matches(blob, query):
    return all(term in blob for term in str(query).casefold().split())


def _source_rows(structure, references):
    rows = []
    for sprite_id, items in sorted(structure.items()):
        refs = references.get(sprite_id, ())
        aliases = ", ".join(_unique(ref["name"] for ref in refs)) or _DASH
        locations = ", ".join(_reference_location(ref) for ref in refs) or _DASH
        for item in items:
            name = item.get("name") or ""
            if not name:
                continue
            matrix = item.get("matrix_hex") or "00"
            character_id = item.get("character_id")
            rows.append({
                "sprite_id": sprite_id,
                "name": name,
                "depth": item.get("depth"),
                "character_id": character_id,
                "values": (
                    sprite_id, aliases, name,
                    character_id if character_id is not None else _DASH,
                    item.get("depth"), matrix,
                ),
                "search": _search_blob(
                    "sprite", sprite_id, aliases, locations, name,
                    "character char", character_id,
                    "tiefe depth", item.get("depth"), matrix,
                ),
            })
    return tuple(rows)


def _target_rows(structure, references):
    rows = []
    for sprite_id, items in sorted(structure.items()):
        refs = references.get(sprite_id, ())
        aliases = ", ".join(_unique(ref["name"] for ref in refs)) or _DASH
        locations = ", ".join(_reference_location(ref) for ref in refs) or _DASH
        named = tuple(item for item in items if item.get("name"))
        contents = ", ".join(
            f"{item['name']}@{item['depth']}→Char {item.get('character_id')}"
            for item in named
        ) or "(keine benannten Instanzen)"
        details = " ".join(
            _search_blob(
                item.get("name"), item.get("depth"),
                item.get("character_id"), item.get("matrix_hex"),
            )
            for item in items
        )
        rows.append({
            "sprite_id": sprite_id,
            "values": (sprite_id, aliases, locations, len(items), contents),
            "search": _search_blob(
                "sprite", sprite_id, aliases, locations, len(items),
                contents, details,
            ),
        })
    return tuple(rows)


def _anchor_rows(structure, sprite_id):
    rows = [{
        "name": "",
        "values": ("(Quellmatrix verwenden)", _DASH, _DASH, _DASH),
        "search": _search_blob("Quellmatrix Quelle kein Anker"),
    }]
    for item in structure.get(int(sprite_id), ()):
        name = item.get("name") or ""
        if not name:
            continue
        matrix = item.get("matrix_hex") or "00"
        character_id = item.get("character_id")
        rows.append({
            "name": name,
            "values": (
                name, item.get("depth"),
                character_id if character_id is not None else _DASH,
                matrix,
            ),
            "search": _search_blob(
                name, "tiefe depth", item.get("depth"),
                "character char", character_id, matrix,
            ),
        })
    return tuple(rows)


def _sort_value(value):
    text = str(value).strip()
    try:
        return 0, int(text, 0)
    except ValueError:
        return 1, text.casefold()


def _sort_tree(tree, column, reverse=False):
    items = [(tree.set(item, column), item) for item in tree.get_children("")]
    items.sort(key=lambda pair: _sort_value(pair[0]), reverse=reverse)
    for index, (_value, item) in enumerate(items):
        tree.move(item, "", index)
    tree.heading(column, command=lambda: _sort_tree(tree, column, not reverse))


class SearchTree(ttk.Frame):
    def __init__(self, parent, columns, on_select, summary=None):
        super().__init__(parent)
        self.rows = ()
        self.visible = {}
        self.selected_key = None
        self.key_getter = lambda row: None
        self.on_select = on_select
        self.query = tk.StringVar()
        self.count = tk.StringVar()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        search = ttk.Frame(self)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text="Suchen:").grid(row=0, column=0, sticky="w")
        ttk.Entry(search, textvariable=self.query).grid(
            row=0, column=1, sticky="ew", padx=6,
        )
        ttk.Button(search, text="Leeren", command=lambda: self.query.set("")).grid(
            row=0, column=2,
        )
        ttk.Label(search, textvariable=self.count).grid(
            row=0, column=3, sticky="e", padx=(8, 0),
        )
        if summary is not None:
            ttk.Label(self, textvariable=summary).grid(
                row=1, column=0, sticky="ew", pady=(0, 5),
            )

        holder = ttk.Frame(self)
        holder.grid(row=2, column=0, sticky="nsew")
        holder.columnconfigure(0, weight=1)
        holder.rowconfigure(0, weight=1)
        names = tuple(column[0] for column in columns)
        self.tree = ttk.Treeview(
            holder, columns=names, show="headings", selectmode="browse",
        )
        for name, title, width, anchor, stretch in columns:
            self.tree.heading(
                name, text=title,
                command=lambda key=name: _sort_tree(self.tree, key),
            )
            self.tree.column(
                name, width=width, minwidth=55,
                anchor=anchor, stretch=stretch,
            )
        yscroll = ttk.Scrollbar(holder, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(holder, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", self._selected)
        self.query.trace_add("write", lambda *_args: self.refresh())

    def set_rows(self, rows, key_getter, selected_key=None, select_first=False):
        self.rows = tuple(rows)
        self.key_getter = key_getter
        self.selected_key = selected_key
        self.refresh(select_first=select_first)

    def refresh(self, select_first=False):
        children = self.tree.get_children("")
        if children:
            self.tree.delete(*children)
        self.visible = {}
        visible = [row for row in self.rows if _matches(row["search"], self.query.get())]
        selected_iid = None
        for index, row in enumerate(visible):
            iid = f"row:{index}"
            self.visible[iid] = row
            self.tree.insert("", "end", iid=iid, values=row["values"])
            if self.key_getter(row) == self.selected_key:
                selected_iid = iid
        self.count.set(f"{len(visible)} / {len(self.rows)}")
        if selected_iid is not None:
            self.tree.selection_set(selected_iid)
            self.tree.see(selected_iid)
        elif select_first and visible:
            first = "row:0"
            self.tree.selection_set(first)
            self.tree.see(first)
            self._selected()

    def _selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        row = self.visible.get(selection[0])
        if row is None:
            return
        self.selected_key = self.key_getter(row)
        self.on_select(row)


class TimelineEditorDialog(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.structure = {}
        self.root_items = ()
        self.references = {}
        self.title("SWF-Timeline-Editor")
        self.geometry("1280x840")
        self.minsize(980, 680)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=2)
        self.rowconfigure(3, weight=1)

        self.status = tk.StringVar(value="Noch nichts verändert")
        self.source_summary = tk.StringVar(value="Keine Quellinstanz ausgewählt")
        self.target_summary = tk.StringVar(value="Kein Ziel-Sprite ausgewählt")
        self.source_sprite = tk.StringVar()
        self.source_name = tk.StringVar()
        self.target_sprite = tk.StringVar()
        self.target_name = tk.StringVar()
        self.anchor_name = tk.StringVar()
        self.depth = tk.StringVar()
        self.replace_existing = tk.BooleanVar(value=False)

        header = ttk.Frame(self, padding=(10, 10, 10, 6))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self.status).grid(row=0, column=0, sticky="w")
        ttk.Button(
            header, text="Struktur neu einlesen", command=self.refresh_structure,
        ).grid(row=0, column=1, sticky="e")

        browser = ttk.Panedwindow(self, orient="horizontal")
        browser.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        source_frame = ttk.LabelFrame(browser, text="1. Quellinstanz auswählen", padding=8)
        target_frame = ttk.LabelFrame(browser, text="2. Ziel-Sprite auswählen", padding=8)
        browser.add(source_frame, weight=1)
        browser.add(target_frame, weight=1)
        self.source_browser = SearchTree(
            source_frame,
            (
                ("sprite", "Quell-Sprite", 85, "e", False),
                ("alias", "Sprite referenziert als", 150, "w", True),
                ("name", "Instanzname", 150, "w", True),
                ("character", "Character-ID", 90, "e", False),
                ("depth", "Tiefe", 65, "e", False),
                ("matrix", "Matrix", 250, "w", True),
            ),
            self._source_selected,
            self.source_summary,
        )
        self.source_browser.pack(fill="both", expand=True)
        self.target_browser = SearchTree(
            target_frame,
            (
                ("sprite", "Ziel-Sprite", 80, "e", False),
                ("alias", "Referenziert als", 160, "w", True),
                ("location", "Referenzort", 145, "w", True),
                ("count", "Elemente", 65, "e", False),
                ("contents", "Benannte Inhalte", 300, "w", True),
            ),
            self._target_selected,
            self.target_summary,
        )
        self.target_browser.pack(fill="both", expand=True)

        options = ttk.LabelFrame(self, text="3. Zielposition und Instanzname", padding=8)
        options.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 8))
        options.columnconfigure(0, weight=3)
        options.columnconfigure(1, weight=2)
        options.rowconfigure(0, weight=1)
        self.anchor_browser = SearchTree(
            options,
            (
                ("name", "Positionsanker", 190, "w", True),
                ("depth", "Tiefe", 65, "e", False),
                ("character", "Character-ID", 90, "e", False),
                ("matrix", "Matrix", 300, "w", True),
            ),
            self._anchor_selected,
        )
        self.anchor_browser.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._build_options(options)

        report_frame = ttk.LabelFrame(self, text="Prüfbericht", padding=6)
        report_frame.grid(row=3, column=0, sticky="nsew", padx=10)
        report_frame.columnconfigure(0, weight=1)
        report_frame.rowconfigure(0, weight=1)
        self.report = tk.Text(report_frame, wrap="word", height=7, state="disabled")
        report_scroll = ttk.Scrollbar(
            report_frame, orient="vertical", command=self.report.yview,
        )
        self.report.configure(yscrollcommand=report_scroll.set)
        self.report.grid(row=0, column=0, sticky="nsew")
        report_scroll.grid(row=0, column=1, sticky="ns")

        buttons = ttk.Frame(self, padding=10)
        buttons.grid(row=4, column=0, sticky="ew")
        ttk.Button(buttons, text="Plan prüfen", command=self.plan).pack(side="left")
        ttk.Button(buttons, text="Vorschau anwenden", command=self.preview).pack(
            side="left", padx=6,
        )
        ttk.Button(buttons, text="Vorschau zurücksetzen", command=self.restore).pack(
            side="left",
        )
        ttk.Button(buttons, text="GFX speichern…", command=self.save_gfx).pack(side="right")
        ttk.Button(buttons, text="PAK neu bauen…", command=self.save_pak).pack(
            side="right", padx=6,
        )
        self._show(
            "Links kann nach Instanzname, Sprite-ID, Character-ID, Tiefe oder Matrix gesucht werden. "
            "Rechts kann nach Sprite-ID, externem Instanznamen oder enthaltenen Instanzen gesucht werden."
        )
        self.refresh_structure()

    def _build_options(self, parent):
        form = ttk.Frame(parent, padding=(8, 4, 0, 0))
        form.grid(row=0, column=1, sticky="nsew")
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text="Ausgewählte Quelle:").grid(row=0, column=0, sticky="nw", pady=4)
        ttk.Label(form, textvariable=self.source_summary, wraplength=390).grid(
            row=0, column=1, sticky="nw", pady=4,
        )
        ttk.Label(form, text="Ausgewähltes Ziel:").grid(row=1, column=0, sticky="nw", pady=4)
        ttk.Label(form, textvariable=self.target_summary, wraplength=390).grid(
            row=1, column=1, sticky="nw", pady=4,
        )
        ttk.Label(form, text="Neuer Instanzname:").grid(row=2, column=0, sticky="w", pady=4)
        name_row = ttk.Frame(form)
        name_row.grid(row=2, column=1, sticky="ew", pady=4)
        name_row.columnconfigure(0, weight=1)
        ttk.Entry(name_row, textvariable=self.target_name).grid(row=0, column=0, sticky="ew")
        ttk.Button(
            name_row, text="Quellname übernehmen",
            command=lambda: self.target_name.set(self.source_name.get()),
        ).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(form, text="Zieltiefe:").grid(row=3, column=0, sticky="w", pady=4)
        depth_row = ttk.Frame(form)
        depth_row.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Entry(depth_row, textvariable=self.depth, width=18).pack(side="left")
        ttk.Label(depth_row, text="leer = automatisch; Dezimal oder 0xHex").pack(
            side="left", padx=(8, 0),
        )
        ttk.Checkbutton(
            form,
            text="Vorhandene gleichnamige Zielinstanz ersetzen",
            variable=self.replace_existing,
        ).grid(row=4, column=1, sticky="w", pady=(7, 1))

    def _show(self, value):
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", str(value))
        self.report.configure(state="disabled")

    def _source_selected(self, row):
        self.source_sprite.set(str(row["sprite_id"]))
        self.source_name.set(row["name"])
        self.target_name.set(row["name"])
        self.source_summary.set(
            f"Sprite {row['sprite_id']} / {row['name']} / "
            f"Character {row['character_id']} / Tiefe {row['depth']}"
        )

    def _target_selected(self, row):
        self.target_sprite.set(str(row["sprite_id"]))
        self.target_summary.set(
            f"Sprite {row['sprite_id']} / referenziert als {row['values'][1]}"
        )
        valid = {
            item.get("name") for item in self.structure.get(row["sprite_id"], ())
            if item.get("name")
        }
        if self.anchor_name.get() not in valid:
            self.anchor_name.set("")
        self.anchor_browser.set_rows(
            _anchor_rows(self.structure, row["sprite_id"]),
            lambda item: item["name"],
            self.anchor_name.get(),
            select_first=True,
        )

    def _anchor_selected(self, row):
        self.anchor_name.set(row["name"])

    def refresh_structure(self):
        try:
            _record, _container, movie_data, patch_count = _base_movie(self.owner)
            old_source = (self.source_sprite.get(), self.source_name.get())
            old_target = self.target_sprite.get()
            old_anchor = self.anchor_name.get()
            structure, root_items = _inspect_movie(movie_data)
            references = _reference_map(structure, root_items)
            source_rows = _source_rows(structure, references)
            target_rows = _target_rows(structure, references)
            if not source_rows:
                raise timeline.TimelinePatchError(
                    "Der ausgewählte Film enthält keine benannte Quellinstanz"
                )
            if not target_rows:
                raise timeline.TimelinePatchError(
                    "Der ausgewählte Film enthält kein DefineSprite"
                )
            self.structure = structure
            self.root_items = root_items
            self.references = references
            source_exists = any(
                old_source == (str(row["sprite_id"]), row["name"])
                for row in source_rows
            )
            target_exists = any(old_target == str(row["sprite_id"]) for row in target_rows)
            if not source_exists:
                self.source_sprite.set("")
                self.source_name.set("")
                self.source_summary.set("Keine Quellinstanz ausgewählt")
            if not target_exists:
                self.target_sprite.set("")
                self.target_summary.set("Kein Ziel-Sprite ausgewählt")
            self.anchor_name.set(old_anchor if target_exists else "")
            self.source_browser.set_rows(
                source_rows,
                lambda row: (str(row["sprite_id"]), row["name"]),
                old_source if source_exists else None,
                select_first=not source_exists,
            )
            self.target_browser.set_rows(
                target_rows,
                lambda row: str(row["sprite_id"]),
                old_target if target_exists else None,
                select_first=not target_exists,
            )
            if target_exists:
                self.anchor_browser.set_rows(
                    _anchor_rows(structure, old_target),
                    lambda row: row["name"],
                    self.anchor_name.get(),
                    select_first=True,
                )
            reference_count = sum(len(items) for items in references.values())
            self.status.set(
                f"Struktur eingelesen: {len(source_rows)} benannte Quellinstanzen, "
                f"{len(target_rows)} Ziel-Sprites, {reference_count} Sprite-Referenzen; "
                f"{patch_count} AVM2-Patches berücksichtigt"
            )
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def _spec(self):
        source_sprite = self.source_sprite.get().strip()
        source_name = self.source_name.get().strip()
        target_sprite = self.target_sprite.get().strip()
        target_name = self.target_name.get().strip()
        if not source_sprite or not source_name:
            raise timeline.TimelinePatchError(
                "In der linken Tabelle muss eine Quellinstanz ausgewählt sein"
            )
        if not target_sprite:
            raise timeline.TimelinePatchError(
                "In der rechten Tabelle muss ein Ziel-Sprite ausgewählt sein"
            )
        if not target_name:
            raise timeline.TimelinePatchError("Der neue Instanzname ist erforderlich")
        depth_text = self.depth.get().strip()
        try:
            depth = int(depth_text, 0) if depth_text else None
        except ValueError as exc:
            raise timeline.TimelinePatchError(
                f"Ungültige Zieltiefe: {depth_text!r}"
            ) from exc
        return timeline.TimelineCopySpec(
            source_sprite_id=int(source_sprite),
            source_name=source_name,
            target_sprite_id=int(target_sprite),
            target_name=target_name,
            anchor_name=self.anchor_name.get().strip(),
            depth=depth,
            replace_existing=bool(self.replace_existing.get()),
        )

    def plan(self):
        try:
            _record, _container, movie_data, patch_count = _base_movie(self.owner)
            report = timeline.plan_copy_instance(movie_data, self._spec())
            report["active_avm2_patches_included"] = patch_count
            self._show(_report_text(report))
            self.status.set("Plan geprüft; noch nichts verändert")
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def preview(self):
        try:
            record, container, _movie_data, _patch_count = _base_movie(self.owner)
            result = _result(self.owner, self._spec())
            movie_tool._preview_from_movie_data(
                self.owner, record, result.movie_data, container,
            )
            self._show(_report_text(result.report))
            self.status.set("Vorschau aktiv; PAK unverändert")
        except Exception as exc:
            self._show(exc)
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def restore(self):
        try:
            record, container, _movie_data, _patch_count = _base_movie(self.owner)
            movie_tool._preview_from_movie_data(
                self.owner, record, record.data, container,
            )
            self.status.set("Vorschau zurückgesetzt")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def save_gfx(self):
        try:
            _key, source, _index, _container, _record = _context(self.owner)
            asset = _gfx(self.owner, _result(self.owner, self._spec()))
            name = Path(
                source.entry.get("display_name")
                or source.entry.get("name")
                or "UI"
            ).stem
            path = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".GFX",
                initialfile=name + "_timeline_patched.GFX",
            )
            if path:
                Path(path).write_bytes(asset)
                self.status.set(f"GFX gespeichert: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def save_pak(self):
        try:
            _key, source, _index, _container, _record = _context(self.owner)
            asset = _gfx(self.owner, _result(self.owner, self._spec()))
            src = Path(source.parsed.get("path", "UIPak.pak"))
            path = filedialog.asksaveasfilename(
                parent=self,
                defaultextension=".pak",
                initialfile=src.stem + "_timeline_patched.pak",
            )
            if path:
                pak_core.rebuild_pak(
                    source.parsed,
                    {int(source.entry["index"]): {"asset_bytes": asset}},
                    path,
                )
                self.status.set(
                    f"PAK gespeichert: {Path(path).name}; Spielwirkung nicht bestätigt"
                )
        except Exception as exc:
            messagebox.showerror("SWF-Timeline", str(exc), parent=self)

    def close(self):
        self.owner._timeline_editor_dialog = None
        self.destroy()


def show_dialog(owner):
    window = getattr(owner, "_timeline_editor_dialog", None)
    if window is not None:
        try:
            if window.winfo_exists():
                window.lift()
                return window
        except Exception:
            pass
    owner._timeline_editor_dialog = TimelineEditorDialog(owner)
    return owner._timeline_editor_dialog


def _init(self, *args, **kwargs):
    _BASE_INIT(self, *args, **kwargs)
    self._timeline_editor_dialog = None
    bar = ttk.Frame(self, padding=(8, 0, 8, 6))
    bar.pack(fill="x")
    ttk.Button(
        bar,
        text="SWF-Timeline-Editor…",
        command=lambda: show_dialog(self),
    ).pack(side="left")
    ttk.Label(
        bar,
        text="Durchsuchbare Quellen, Ziel-Sprites und Positionsanker",
    ).pack(side="left", padx=10)


def _close(self):
    window = getattr(self, "_timeline_editor_dialog", None)
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
