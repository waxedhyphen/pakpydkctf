"""Validated renaming of an existing SWF timeline instance by depth.

The operation adds a PlaceObject2 move record that changes only the instance name.
Character, matrix and every other property of the existing display object remain intact.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pak_core
import ui_browser
import ui_browser_avm2_patch_tool as movie_tool
import ui_browser_timeline_patch_tool as tool
import ui_browser_timeline_repack as timeline


_INSTALLED = False
_BASE_BUILD_OPTIONS = None


@dataclass(frozen=True)
class TimelineRenameSpec:
    target_sprite_id: int
    depth: int
    target_name: str
    require_unnamed: bool = True
    # ui_browser_timeline_repack._rewrite reads these two attributes.
    replace_existing: bool = False


def _coerce_spec(spec) -> TimelineRenameSpec:
    if isinstance(spec, TimelineRenameSpec):
        return spec
    try:
        return TimelineRenameSpec(**dict(spec))
    except Exception as exc:
        raise timeline.TimelinePatchError(
            f"Ungültige Timeline-Umbenennungsspezifikation: {exc}"
        ) from exc


def plan_rename_instance(movie_data, spec):
    spec = _coerce_spec(spec)
    target_name = str(spec.target_name).strip()
    if not target_name:
        raise timeline.TimelinePatchError("Der neue Instanzname ist erforderlich")
    name_bytes = target_name.encode("utf-8")
    if b"\x00" in name_bytes:
        raise timeline.TimelinePatchError("Der neue Instanzname enthält ein Nullbyte")

    depth = int(spec.depth)
    if not 1 <= depth <= 0xFFFF:
        raise timeline.TimelinePatchError(f"Zieltiefe {depth} ist ungültig")

    _data, signature, _start, records, _tail = timeline._root(movie_data)
    sprites = timeline._sprites(records)
    target_records = sprites.get(int(spec.target_sprite_id))
    if target_records is None:
        raise timeline.TimelinePatchError(
            f"Sprite {spec.target_sprite_id} wurde nicht gefunden"
        )

    target_state = timeline._first_frame(target_records)
    current = target_state.get(depth)
    if current is None:
        raise timeline.TimelinePatchError(
            f"Sprite {spec.target_sprite_id} enthält auf Tiefe {depth} keine Instanz"
        )
    if spec.require_unnamed and current.name:
        raise timeline.TimelinePatchError(
            f"Die Instanz auf Tiefe {depth} heißt bereits {current.name!r}; "
            "die sichere Umbenennung erwartet eine unbenannte Instanz"
        )
    if current.name == target_name:
        raise timeline.TimelinePatchError(
            f"Die Instanz auf Tiefe {depth} heißt bereits {target_name!r}"
        )

    duplicates = [
        item for item_depth, item in target_state.items()
        if item_depth != depth and item.name == target_name
    ]
    if duplicates:
        raise timeline.TimelinePatchError(
            f"Sprite {spec.target_sprite_id} enthält bereits eine andere Instanz "
            f"namens {target_name!r}"
        )

    return {
        "operation": "rename_existing_instance",
        "signature": signature.decode("ascii", "replace"),
        "target_sprite_id": int(spec.target_sprite_id),
        "target_depth": depth,
        "old_name": current.name,
        "target_name": target_name,
        "character_id": current.character_id,
        "matrix_hex": current.matrix.hex(" ").upper(),
        "require_unnamed": bool(spec.require_unnamed),
        "target_before": tuple(
            {
                "depth": item.depth,
                "name": item.name,
                "character_id": item.character_id,
            }
            for item in sorted(target_state.values(), key=lambda value: value.depth)
        ),
    }


def _rename_move(depth: int, target_name: str):
    name_bytes = str(target_name).encode("utf-8")
    # 0x21 = PlaceObject2 move flag + has-name flag. No visual property is replaced.
    payload = b"\x21" + int(depth).to_bytes(2, "little") + name_bytes + b"\x00"
    record = timeline.Tag(timeline.PLACE_OBJECT2, payload)
    check = timeline._place(record)
    if (
        check is None
        or not check.move
        or check.depth != int(depth)
        or check.name != str(target_name)
        or check.character_id is not None
        or check.matrix
    ):
        raise timeline.TimelinePatchError("Umbenennungs-PlaceObject2 ist ungültig")
    return record


def rename_instance(movie_data, spec):
    spec = _coerce_spec(spec)
    plan = plan_rename_instance(movie_data, spec)
    insertion = _rename_move(plan["target_depth"], plan["target_name"])

    data, signature, start, records, tail = timeline._root(movie_data)
    rewritten, changed, found = timeline._rewrite(records, spec, insertion)
    if not found or not changed:
        raise timeline.TimelinePatchError("Ziel-Sprite wurde nicht verändert")

    rebuilt = bytearray(data[:start])
    rebuilt += timeline._tag_stream(rewritten, tail)
    result = timeline.repack._deflate_swf(rebuilt, signature)

    target_after = timeline.inspect_sprites(result).get(
        int(spec.target_sprite_id), ()
    )
    matches = [item for item in target_after if item["depth"] == plan["target_depth"]]
    if len(matches) != 1:
        raise timeline.TimelinePatchError(
            "Nachprüfung: Zielinstanz auf der gewählten Tiefe ist nicht eindeutig"
        )
    renamed = matches[0]
    if renamed["name"] != plan["target_name"]:
        raise timeline.TimelinePatchError("Nachprüfung: Instanzname wurde nicht gesetzt")
    if renamed["character_id"] != plan["character_id"]:
        raise timeline.TimelinePatchError(
            "Nachprüfung: Character-ID wurde unerwartet verändert"
        )
    if renamed["matrix_hex"] != plan["matrix_hex"]:
        raise timeline.TimelinePatchError(
            "Nachprüfung: Positionsmatrix wurde unerwartet verändert"
        )

    report = dict(plan)
    report.update({
        "target_after": tuple(target_after),
        "movie_size_before": len(movie_data),
        "movie_size_after": len(result),
        "structural_validation": "passed",
    })
    return timeline.TimelinePatchResult(
        result, report, signature.decode("ascii", "replace")
    )


def _report_text(report):
    old_name = report.get("old_name") or "(unbenannt)"
    before = ", ".join(
        f"{item['name'] or '(unbenannt)'}@{item['depth']}→Char {item['character_id']}"
        for item in report.get("target_before", ())
    ) or "leer"
    after = ", ".join(
        f"{item['name'] or '(unbenannt)'}@{item['depth']}→Char {item['character_id']}"
        for item in report.get("target_after", ())
    ) or "noch nicht angewendet"
    return "\n".join((
        f"Ziel: Sprite {report['target_sprite_id']} / Tiefe {report['target_depth']}",
        f"Umbenennung: {old_name} -> {report['target_name']}",
        f"Character-ID: {report['character_id']}",
        f"Matrix unverändert: {report['matrix_hex'] or '00'}",
        f"Vorher: {before}",
        f"Danach: {after}",
        f"Strukturprüfung: {report.get('structural_validation', 'noch nicht ausgeführt')}",
        "Spielwirkung: nicht bestätigt",
    ))


def _find_options_form(parent):
    for child in parent.winfo_children():
        info = child.grid_info()
        if str(info.get("column")) == "1":
            return child
    raise timeline.TimelinePatchError(
        "Optionsformular des Timeline-Editors wurde nicht gefunden"
    )


def _build_options(self, parent):
    _BASE_BUILD_OPTIONS(self, parent)
    form = _find_options_form(parent)
    rename_frame = ttk.LabelFrame(
        form, text="Vorhandene Instanz an Zieltiefe umbenennen", padding=6
    )
    rename_frame.grid(
        row=8, column=0, columnspan=2, sticky="ew", pady=(10, 2)
    )
    ttk.Label(
        rename_frame,
        text=(
            "Verwendet Ziel-Sprite, Zieltiefe und neuen Instanznamen. "
            "Die ausgewählte Quellinstanz wird ignoriert."
        ),
        wraplength=520,
    ).pack(anchor="w", pady=(0, 6))
    buttons = ttk.Frame(rename_frame)
    buttons.pack(fill="x")
    ttk.Button(
        buttons, text="Umbenennung prüfen", command=self.plan_existing_rename
    ).pack(side="left")
    ttk.Button(
        buttons, text="Umbenennung als Vorschau", command=self.preview_existing_rename
    ).pack(side="left", padx=6)
    ttk.Button(
        buttons, text="Umbenannte PAK bauen…", command=self.save_existing_rename_pak
    ).pack(side="left")


def _dialog_rename_spec(self):
    target_sprite = self.target_sprite.get().strip()
    target_name = self.target_name.get().strip()
    depth_text = self.depth.get().strip()
    if not target_sprite:
        raise timeline.TimelinePatchError(
            "In der rechten Tabelle muss ein Ziel-Sprite ausgewählt sein"
        )
    if not depth_text:
        raise timeline.TimelinePatchError(
            "Für die Umbenennung muss die vorhandene Zieltiefe eingetragen sein"
        )
    if not target_name:
        raise timeline.TimelinePatchError("Der neue Instanzname ist erforderlich")
    try:
        depth = int(depth_text, 0)
    except ValueError as exc:
        raise timeline.TimelinePatchError(
            f"Ungültige Zieltiefe: {depth_text!r}"
        ) from exc
    return TimelineRenameSpec(
        target_sprite_id=int(target_sprite),
        depth=depth,
        target_name=target_name,
        require_unnamed=True,
    )


def _result(owner, spec):
    _record, _container, movie_data, _patch_count = tool._base_movie(owner)
    return rename_instance(movie_data, spec)


def _plan_existing_rename(self):
    try:
        _record, _container, movie_data, patch_count = tool._base_movie(self.owner)
        report = plan_rename_instance(movie_data, _dialog_rename_spec(self))
        report["active_avm2_patches_included"] = patch_count
        self._show(_report_text(report))
        self.status.set("Umbenennung geprüft; noch nichts verändert")
    except Exception as exc:
        self._show(exc)
        messagebox.showerror("SWF-Timeline-Umbenennung", str(exc), parent=self)


def _preview_existing_rename(self):
    try:
        record, container, _movie_data, _patch_count = tool._base_movie(self.owner)
        result = _result(self.owner, _dialog_rename_spec(self))
        movie_tool._preview_from_movie_data(
            self.owner, record, result.movie_data, container
        )
        self._show(_report_text(result.report))
        self.status.set("Umbenennungs-Vorschau aktiv; PAK unverändert")
    except Exception as exc:
        self._show(exc)
        messagebox.showerror("SWF-Timeline-Umbenennung", str(exc), parent=self)


def _save_existing_rename_pak(self):
    try:
        _key, source, _index, _container, _record = tool._context(self.owner)
        result = _result(self.owner, _dialog_rename_spec(self))
        asset = tool._gfx(self.owner, result)
        src = Path(source.parsed.get("path", "UIPak.pak"))
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pak",
            initialfile=src.stem + "_timeline_renamed.pak",
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
            self._show(_report_text(result.report))
    except Exception as exc:
        messagebox.showerror("SWF-Timeline-Umbenennung", str(exc), parent=self)


def install():
    global _INSTALLED, _BASE_BUILD_OPTIONS
    if _INSTALLED:
        return
    _INSTALLED = True
    # Capture after ui_browser_timeline_transform_patch has extended the same form.
    _BASE_BUILD_OPTIONS = tool.TimelineEditorDialog._build_options
    tool.TimelineEditorDialog._build_options = _build_options
    tool.TimelineEditorDialog.plan_existing_rename = _plan_existing_rename
    tool.TimelineEditorDialog.preview_existing_rename = _preview_existing_rename
    tool.TimelineEditorDialog.save_existing_rename_pak = _save_existing_rename_pak
    ui_browser.plan_timeline_instance_rename = plan_rename_instance
    ui_browser.rename_timeline_instance = rename_instance
