"""Universal position transforms and unnamed visual copies for the SWF timeline editor.

This module extends the existing generic timeline instance copier. It does not contain
any game-specific sprite IDs, depths, matrices or names.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import tkinter as tk
from tkinter import ttk

import ui_browser
import ui_browser_timeline_patch_tool as tool
import ui_browser_timeline_repack as timeline


_INSTALLED = False
_BASE_SPEC_CLASS = timeline.TimelineCopySpec
_BASE_PLAN = timeline.plan_copy_instance
_BASE_COPY = timeline.copy_instance
_BASE_BUILD_OPTIONS = tool.TimelineEditorDialog._build_options
_BASE_DIALOG_SPEC = tool.TimelineEditorDialog._spec
_BASE_REPORT_TEXT = tool._report_text


@dataclass(frozen=True)
class TimelineTransformCopySpec(_BASE_SPEC_CLASS):
    translate_x_twips: int = 0
    translate_y_twips: int = 0
    allow_unnamed: bool = False


def _signed_bits(value: int) -> int:
    value = int(value)
    for count in range(1, 33):
        if -(1 << (count - 1)) <= value <= (1 << (count - 1)) - 1:
            return count
    raise timeline.TimelinePatchError(f"MATRIX-Wert liegt außerhalb von 32 Bit: {value}")


def _read_bits(data: bytes, bit: int, count: int, signed: bool = False):
    value = 0
    for _ in range(count):
        if bit >= len(data) * 8:
            raise timeline.TimelinePatchError("MATRIX ist abgeschnitten")
        value = (value << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
        bit += 1
    if signed and count and value & (1 << (count - 1)):
        value -= 1 << count
    return value, bit


def _append_bits(bits: list[int], value: int, count: int) -> None:
    value = int(value) & ((1 << count) - 1)
    bits.extend((value >> shift) & 1 for shift in range(count - 1, -1, -1))


def _pack_bits(bits: list[int]) -> bytes:
    while len(bits) % 8:
        bits.append(0)
    result = bytearray(len(bits) // 8)
    for index, value in enumerate(bits):
        result[index >> 3] |= int(value) << (7 - (index & 7))
    return bytes(result)


def decode_matrix(matrix: bytes) -> dict:
    data = bytes(matrix or b"\x00")
    bit = 0
    has_scale, bit = _read_bits(data, bit, 1)
    scale = None
    if has_scale:
        count, bit = _read_bits(data, bit, 5)
        scale_x, bit = _read_bits(data, bit, count, True)
        scale_y, bit = _read_bits(data, bit, count, True)
        scale = (scale_x, scale_y)

    has_rotate, bit = _read_bits(data, bit, 1)
    rotate = None
    if has_rotate:
        count, bit = _read_bits(data, bit, 5)
        rotate_0, bit = _read_bits(data, bit, count, True)
        rotate_1, bit = _read_bits(data, bit, count, True)
        rotate = (rotate_0, rotate_1)

    count, bit = _read_bits(data, bit, 5)
    translate_x, bit = _read_bits(data, bit, count, True)
    translate_y, bit = _read_bits(data, bit, count, True)
    return {
        "scale": scale,
        "rotate": rotate,
        "translate_x_twips": translate_x,
        "translate_y_twips": translate_y,
    }


def encode_matrix(value: dict) -> bytes:
    scale = value.get("scale")
    rotate = value.get("rotate")
    translate_x = int(value.get("translate_x_twips", 0))
    translate_y = int(value.get("translate_y_twips", 0))
    bits: list[int] = []

    _append_bits(bits, 1 if scale else 0, 1)
    if scale:
        count = max(_signed_bits(scale[0]), _signed_bits(scale[1]))
        _append_bits(bits, count, 5)
        _append_bits(bits, scale[0], count)
        _append_bits(bits, scale[1], count)

    _append_bits(bits, 1 if rotate else 0, 1)
    if rotate:
        count = max(_signed_bits(rotate[0]), _signed_bits(rotate[1]))
        _append_bits(bits, count, 5)
        _append_bits(bits, rotate[0], count)
        _append_bits(bits, rotate[1], count)

    count = max(_signed_bits(translate_x), _signed_bits(translate_y))
    _append_bits(bits, count, 5)
    _append_bits(bits, translate_x, count)
    _append_bits(bits, translate_y, count)
    return _pack_bits(bits)


def translate_matrix(matrix: bytes, x_twips: int = 0, y_twips: int = 0) -> bytes:
    value = decode_matrix(matrix)
    value["translate_x_twips"] += int(x_twips)
    value["translate_y_twips"] += int(y_twips)
    return encode_matrix(value)


def _coerce_spec(spec) -> TimelineTransformCopySpec:
    if isinstance(spec, TimelineTransformCopySpec):
        return spec
    if isinstance(spec, _BASE_SPEC_CLASS):
        return TimelineTransformCopySpec(
            source_sprite_id=spec.source_sprite_id,
            source_name=spec.source_name,
            target_sprite_id=spec.target_sprite_id,
            target_name=spec.target_name,
            anchor_name=spec.anchor_name,
            depth=spec.depth,
            replace_existing=spec.replace_existing,
        )
    try:
        return TimelineTransformCopySpec(**dict(spec))
    except Exception as exc:
        raise timeline.TimelinePatchError(f"Ungültige Timeline-Kopierspezifikation: {exc}") from exc


def plan_copy_instance(movie_data, spec):
    spec = _coerce_spec(spec)
    if not spec.source_name:
        raise timeline.TimelinePatchError("Der Quellname darf nicht leer sein")
    if not spec.target_name and not spec.allow_unnamed:
        raise timeline.TimelinePatchError(
            "Der Zielname darf nur bei ausdrücklich aktivierter unbenannter Kopie leer sein"
        )
    if not spec.target_name and spec.replace_existing:
        raise timeline.TimelinePatchError(
            "Eine unbenannte Kopie kann keine gleichnamige Zielinstanz ersetzen"
        )

    if (
        spec.target_name
        and not spec.translate_x_twips
        and not spec.translate_y_twips
        and not spec.allow_unnamed
    ):
        return _BASE_PLAN(movie_data, spec)

    _data, signature, _start, records, _tail = timeline._root(movie_data)
    sprites = timeline._sprites(records)
    source_records = sprites.get(int(spec.source_sprite_id))
    target_records = sprites.get(int(spec.target_sprite_id))
    if source_records is None or target_records is None:
        missing = spec.source_sprite_id if source_records is None else spec.target_sprite_id
        raise timeline.TimelinePatchError(f"Sprite {missing} wurde nicht gefunden")

    source_state = timeline._first_frame(source_records)
    target_state = timeline._first_frame(target_records)
    source = timeline._named(source_state, spec.source_name, spec.source_sprite_id)
    if source.character_id is None:
        raise timeline.TimelinePatchError("Quellinstanz hat keine Character-ID")

    existing = (
        [item for item in target_state.values() if item.name == spec.target_name]
        if spec.target_name else []
    )
    if existing and not spec.replace_existing:
        raise timeline.TimelinePatchError(f"Ziel enthält {spec.target_name!r} bereits")

    anchor = (
        timeline._named(target_state, spec.anchor_name, spec.target_sprite_id)
        if spec.anchor_name else None
    )
    matrix = (anchor.matrix if anchor else source.matrix) or b"\x00"
    matrix = translate_matrix(matrix, spec.translate_x_twips, spec.translate_y_twips)

    used = set(target_state)
    if existing and spec.replace_existing:
        used.discard(existing[0].depth)
    if spec.depth is not None:
        depth = int(spec.depth)
        reason = "manuell"
    elif source.depth not in used:
        depth = source.depth
        reason = "freie Quelltiefe"
    else:
        depth = max(used or {0}) + 1
        reason = "erste Tiefe oberhalb des Zielbestands"
    if not 1 <= depth <= 0xFFFF or depth in used:
        raise timeline.TimelinePatchError(f"Zieltiefe {depth} ist ungültig oder belegt")

    return {
        "signature": signature.decode("ascii", "replace"),
        "source_sprite_id": int(spec.source_sprite_id),
        "source_name": spec.source_name,
        "source_depth": source.depth,
        "character_id": source.character_id,
        "target_sprite_id": int(spec.target_sprite_id),
        "target_name": spec.target_name,
        "allow_unnamed": bool(spec.allow_unnamed),
        "anchor_name": spec.anchor_name,
        "anchor_depth": anchor.depth if anchor else None,
        "translate_x_twips": int(spec.translate_x_twips),
        "translate_y_twips": int(spec.translate_y_twips),
        "matrix_hex": matrix.hex(" ").upper(),
        "target_depth": depth,
        "depth_reason": reason,
        "replace_existing": bool(spec.replace_existing),
        "target_before": tuple(
            {"depth": item.depth, "name": item.name, "character_id": item.character_id}
            for item in sorted(target_state.values(), key=lambda value: value.depth)
        ),
    }


def _new_place(character_id: int, depth: int, matrix: bytes, name: str):
    name_bytes = str(name).encode("utf-8")
    if b"\x00" in name_bytes:
        raise timeline.TimelinePatchError("Zielname enthält ein Nullbyte")
    has_name = bool(name_bytes)
    flags = b"\x26" if has_name else b"\x06"
    payload = (
        flags
        + int(depth).to_bytes(2, "little")
        + int(character_id).to_bytes(2, "little")
        + bytes(matrix or b"\x00")
        + (name_bytes + b"\x00" if has_name else b"")
    )
    check = timeline._place(timeline.Tag(timeline.PLACE_OBJECT2, payload))
    if (
        check is None
        or check.name != str(name)
        or check.depth != int(depth)
        or check.character_id != int(character_id)
    ):
        raise timeline.TimelinePatchError("Neuer PlaceObject2-Eintrag ist ungültig")
    return timeline.Tag(timeline.PLACE_OBJECT2, payload)


def copy_instance(movie_data, spec):
    spec = _coerce_spec(spec)
    if (
        spec.target_name
        and not spec.translate_x_twips
        and not spec.translate_y_twips
        and not spec.allow_unnamed
    ):
        return _BASE_COPY(movie_data, spec)

    plan = plan_copy_instance(movie_data, spec)
    insertion = _new_place(
        plan["character_id"],
        plan["target_depth"],
        bytes.fromhex(plan["matrix_hex"]),
        spec.target_name,
    )
    data, signature, start, records, tail = timeline._root(movie_data)
    rewritten, changed, found = timeline._rewrite(records, spec, insertion)
    if not found or not changed:
        raise timeline.TimelinePatchError("Ziel-Sprite wurde nicht verändert")

    rebuilt = bytearray(data[:start])
    rebuilt += timeline._tag_stream(rewritten, tail)
    result = timeline.repack._deflate_swf(rebuilt, signature)
    target_after = timeline.inspect_sprites(result).get(int(spec.target_sprite_id), ())
    matches = [
        item for item in target_after
        if item["depth"] == plan["target_depth"]
        and item["character_id"] == plan["character_id"]
        and item["name"] == spec.target_name
    ]
    if len(matches) != 1:
        raise timeline.TimelinePatchError("Nachprüfung: Zielinstanz ist nicht eindeutig")

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


def _find_options_form(parent):
    for child in parent.winfo_children():
        info = child.grid_info()
        if str(info.get("column")) == "1":
            return child
    raise timeline.TimelinePatchError("Optionsformular des Timeline-Editors wurde nicht gefunden")


def _build_options(self, parent):
    _BASE_BUILD_OPTIONS(self, parent)
    self.translate_x_pixels = tk.StringVar(value="0")
    self.translate_y_pixels = tk.StringVar(value="0")
    self.allow_unnamed = tk.BooleanVar(value=False)
    form = _find_options_form(parent)

    ttk.Label(form, text="X-Verschiebung:").grid(row=5, column=0, sticky="w", pady=4)
    x_row = ttk.Frame(form)
    x_row.grid(row=5, column=1, sticky="ew", pady=4)
    ttk.Entry(x_row, textvariable=self.translate_x_pixels, width=18).pack(side="left")
    ttk.Label(x_row, text="Pixel; negativ = links").pack(side="left", padx=(8, 0))

    ttk.Label(form, text="Y-Verschiebung:").grid(row=6, column=0, sticky="w", pady=4)
    y_row = ttk.Frame(form)
    y_row.grid(row=6, column=1, sticky="ew", pady=4)
    ttk.Entry(y_row, textvariable=self.translate_y_pixels, width=18).pack(side="left")
    ttk.Label(y_row, text="Pixel; negativ = oben").pack(side="left", padx=(8, 0))

    ttk.Checkbutton(
        form,
        text="Ohne Instanznamen einfügen (sicherer reiner Sichttest)",
        variable=self.allow_unnamed,
    ).grid(row=7, column=1, sticky="w", pady=(7, 1))


def _pixels_to_twips(value: str, label: str) -> int:
    text = str(value).strip() or "0"
    try:
        number = float(text.replace(",", "."))
    except ValueError as exc:
        raise timeline.TimelinePatchError(f"Ungültige {label}: {text!r}") from exc
    if not math.isfinite(number):
        raise timeline.TimelinePatchError(f"Ungültige {label}: {text!r}")
    return int(round(number * 20.0))


def _dialog_spec(self):
    allow_unnamed = bool(self.allow_unnamed.get())
    old_name = self.target_name.get()
    if allow_unnamed and not old_name.strip():
        self.target_name.set("__unnamed_visual_copy__")
    try:
        base = _BASE_DIALOG_SPEC(self)
    finally:
        self.target_name.set(old_name)
    return TimelineTransformCopySpec(
        source_sprite_id=base.source_sprite_id,
        source_name=base.source_name,
        target_sprite_id=base.target_sprite_id,
        target_name="" if allow_unnamed else base.target_name,
        anchor_name=base.anchor_name,
        depth=base.depth,
        replace_existing=base.replace_existing,
        translate_x_twips=_pixels_to_twips(self.translate_x_pixels.get(), "X-Verschiebung"),
        translate_y_twips=_pixels_to_twips(self.translate_y_pixels.get(), "Y-Verschiebung"),
        allow_unnamed=allow_unnamed,
    )


def _report_text(report):
    text = _BASE_REPORT_TEXT(report)
    x_twips = int(report.get("translate_x_twips", 0))
    y_twips = int(report.get("translate_y_twips", 0))
    name = report.get("target_name") or "(unbenannt)"
    return "\n".join((
        text,
        f"Zielinstanz: {name}",
        f"Verschiebung: X {x_twips / 20:g}px / Y {y_twips / 20:g}px",
    ))


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    timeline.TimelineCopySpec = TimelineTransformCopySpec
    timeline.plan_copy_instance = plan_copy_instance
    timeline.copy_instance = copy_instance
    tool.TimelineEditorDialog._build_options = _build_options
    tool.TimelineEditorDialog._spec = _dialog_spec
    tool._report_text = _report_text
    ui_browser.copy_timeline_instance = copy_instance
    ui_browser.plan_timeline_instance_copy = plan_copy_instance
