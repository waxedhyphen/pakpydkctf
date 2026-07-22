"""Classic SWF button records, bounded AVM1 action inventory and hit geometry helpers.

This module contains the format-facing part of the UI Browser classic-button stage. It
is intentionally independent from Tk. The integration patch installs the definitions,
input routing and inspector controls without mutating source GFX/SWF data.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import ui_browser

try:
    import ui_browser_scale9_blend_patch as scale9
except Exception:  # model tests and reduced tooling can run without the renderer patch
    scale9 = None

TAG_DEFINE_BUTTON = 7
TAG_DEFINE_BUTTON2 = 34
TAG_SHOW_FRAME = 1
TAG_REMOVE_OBJECT2 = 28
TAG_PLACE_OBJECT2 = 26
TAG_PLACE_OBJECT3 = 70
TAG_END = 0

STATE_ORDER = ("up", "over", "down", "hit")
_STATE_BITS = ((0x01, "up"), (0x02, "over"), (0x04, "down"), (0x08, "hit"))

ACTION_NAMES = {
    0x04: "NextFrame", 0x05: "PreviousFrame", 0x06: "Play", 0x07: "Stop",
    0x08: "ToggleQuality", 0x09: "StopSounds", 0x0A: "Add", 0x0B: "Subtract",
    0x0C: "Multiply", 0x0D: "Divide", 0x0E: "Equals", 0x0F: "Less",
    0x10: "And", 0x11: "Or", 0x12: "Not", 0x13: "StringEquals",
    0x14: "StringLength", 0x15: "StringExtract", 0x17: "Pop", 0x18: "ToInteger",
    0x1C: "GetVariable", 0x1D: "SetVariable", 0x20: "SetTarget2", 0x21: "StringAdd",
    0x22: "GetProperty", 0x23: "SetProperty", 0x24: "CloneSprite", 0x25: "RemoveSprite",
    0x26: "Trace", 0x27: "StartDrag", 0x28: "EndDrag", 0x29: "StringLess",
    0x2A: "Throw", 0x2B: "CastOp", 0x2C: "ImplementsOp", 0x30: "RandomNumber",
    0x31: "MBStringLength", 0x32: "CharToAscii", 0x33: "AsciiToChar",
    0x34: "GetTime", 0x35: "MBStringExtract", 0x36: "MBCharToAscii",
    0x37: "MBAsciiToChar", 0x3A: "Delete", 0x3B: "Delete2", 0x3C: "DefineLocal",
    0x3D: "CallFunction", 0x3E: "Return", 0x3F: "Modulo", 0x40: "NewObject",
    0x41: "DefineLocal2", 0x42: "InitArray", 0x43: "InitObject", 0x44: "TypeOf",
    0x45: "TargetPath", 0x46: "Enumerate", 0x47: "Add2", 0x48: "Less2",
    0x49: "Equals2", 0x4A: "ToNumber", 0x4B: "ToString", 0x4C: "PushDuplicate",
    0x4D: "StackSwap", 0x4E: "GetMember", 0x4F: "SetMember", 0x50: "Increment",
    0x51: "Decrement", 0x52: "CallMethod", 0x53: "NewMethod", 0x54: "InstanceOf",
    0x55: "Enumerate2", 0x60: "BitAnd", 0x61: "BitOr", 0x62: "BitXor",
    0x63: "BitLShift", 0x64: "BitRShift", 0x65: "BitURShift", 0x66: "StrictEquals",
    0x67: "Greater", 0x68: "StringGreater", 0x69: "Extends",
    0x81: "GotoFrame", 0x83: "GetURL", 0x87: "StoreRegister", 0x88: "ConstantPool",
    0x8A: "WaitForFrame", 0x8B: "SetTarget", 0x8C: "GotoLabel",
    0x8D: "WaitForFrame2", 0x8E: "DefineFunction2", 0x8F: "Try", 0x94: "With",
    0x96: "Push", 0x99: "Jump", 0x9A: "GetURL2", 0x9B: "DefineFunction",
    0x9D: "If", 0x9E: "Call", 0x9F: "GotoFrame2",
}

SAFE_TIMELINE_ACTIONS = frozenset({
    "NextFrame", "PreviousFrame", "Play", "Stop", "GotoFrame", "GotoLabel",
})

_CONDITION_BITS = (
    (0x8000, "idle_to_over_down"),
    (0x4000, "out_down_to_idle"),
    (0x2000, "out_down_to_over_down"),
    (0x1000, "over_down_to_out_down"),
    (0x0800, "over_down_to_over_up"),
    (0x0400, "over_up_to_over_down"),
    (0x0200, "over_up_to_idle"),
    (0x0100, "idle_to_over_up"),
    (0x0001, "over_down_to_idle"),
)


@dataclass(frozen=True)
class Avm1Action:
    code: int
    name: str
    data: bytes = b""
    argument: object | None = None

    @property
    def safe(self) -> bool:
        return self.name in SAFE_TIMELINE_ACTIONS


@dataclass(frozen=True)
class ButtonActionBinding:
    conditions: tuple[str, ...]
    key_code: int
    actions: tuple[Avm1Action, ...]
    raw_flags: int = 0


@dataclass(frozen=True)
class ButtonRecord:
    character_id: int
    depth: int
    matrix: object
    color: object
    states: tuple[str, ...]
    raw_matrix: bytes
    raw_color: bytes = b""
    raw_filters: bytes = b""
    blend_mode: int | None = None


class ClassicButtonTags:
    """Iterable synthetic timeline consumed by every existing display-list builder.

    The four frames are up, over, down and hit. Using ordinary PlaceObject/RemoveObject
    records keeps compatibility with cached builder references captured by older patches.
    """

    def __init__(self, definition: "ClassicButtonDef"):
        self.definition = definition

    @staticmethod
    def _remove(depth: int):
        return TAG_REMOVE_OBJECT2, int(depth).to_bytes(2, "little")

    @staticmethod
    def _place(record: ButtonRecord):
        if record.raw_color or record.raw_filters or record.blend_mode is not None:
            flags1 = 0x02 | 0x04 | (0x08 if record.raw_color else 0)
            flags2 = (0x01 if record.raw_filters else 0) | (0x02 if record.blend_mode is not None else 0)
            payload = bytearray((flags1, flags2))
            payload += int(record.depth).to_bytes(2, "little")
            payload += int(record.character_id).to_bytes(2, "little")
            payload += record.raw_matrix
            payload += record.raw_color
            payload += record.raw_filters
            if record.blend_mode is not None:
                payload.append(int(record.blend_mode) & 0xFF)
            return TAG_PLACE_OBJECT3, bytes(payload)
        payload = bytearray((0x02 | 0x04,))
        payload += int(record.depth).to_bytes(2, "little")
        payload += int(record.character_id).to_bytes(2, "little")
        payload += record.raw_matrix
        return TAG_PLACE_OBJECT2, bytes(payload)

    def __len__(self):
        placements = sum(
            state in record.states
            for state in STATE_ORDER
            for record in self.definition.records
        )
        removals = sum(
            state in record.states
            for state in STATE_ORDER[:-1]
            for record in self.definition.records
        )
        return 5 + placements + removals

    def __iter__(self):
        active_depths: set[int] = set()
        for state in STATE_ORDER:
            for depth in sorted(active_depths):
                yield self._remove(depth)
            active_depths.clear()
            for record in self.definition.records:
                if state in record.states:
                    yield self._place(record)
                    active_depths.add(int(record.depth))
            yield TAG_SHOW_FRAME, b""
        yield TAG_END, b""


class ClassicButtonDef(ui_browser.SpriteDef):
    """Sprite-compatible representation of DefineButton/DefineButton2."""

    def __init__(self, character_id: int, version: int, records, actions,
                 track_as_menu: bool = False, parse_errors=()):
        super().__init__(
            int(character_id), 4, [],
            {"up": 1, "over": 2, "down": 3, "hit": 4, "disabled": 1},
        )
        self.button_version = int(version)
        self.records = tuple(records)
        self.button_actions = tuple(actions)
        self.track_as_menu = bool(track_as_menu)
        self.parse_errors = tuple(str(value) for value in parse_errors if value)
        self.bounds = (0.0, 0.0, 1.0, 1.0)
        self.tags = ClassicButtonTags(self)

    @property
    def hit_records(self):
        values = tuple(record for record in self.records if "hit" in record.states)
        return values or tuple(record for record in self.records if "up" in record.states)


class ButtonParseError(getattr(ui_browser, "PakError", ValueError)):
    pass


def _need(data: bytes, off: int, size: int, label: str) -> None:
    if off < 0 or off + size > len(data):
        raise ButtonParseError(f"{label} ist abgeschnitten")


def _u16(data: bytes, off: int, label="UI16") -> int:
    _need(data, off, 2, label)
    return int.from_bytes(data[off:off + 2], "little")


def _cstring(data: bytes, off: int):
    end = data.find(b"\x00", off)
    if end < 0:
        raise ButtonParseError("AVM1-String ist nicht nullterminiert")
    return data[off:end].decode("utf-8", "replace"), end + 1


def _action_argument(code: int, data: bytes):
    if code == 0x81 and len(data) >= 2:
        return int.from_bytes(data[:2], "little") + 1
    if code == 0x8C:
        try:
            return _cstring(data, 0)[0]
        except Exception:
            return ""
    if code == 0x83:
        try:
            url, p = _cstring(data, 0)
            target, _ = _cstring(data, p)
            return {"url": url, "target": target}
        except Exception:
            return {"url": "", "target": ""}
    return None


def parse_avm1_actions(data: bytes, start=0, end=None):
    end = len(data) if end is None else min(len(data), max(start, int(end)))
    p = max(0, int(start))
    actions = []
    while p < end:
        code = data[p]
        p += 1
        if code == 0:
            break
        size = 0
        if code >= 0x80:
            _need(data, p, 2, "AVM1-Aktionslänge")
            size = int.from_bytes(data[p:p + 2], "little")
            p += 2
        _need(data, p, size, "AVM1-Aktionsdaten")
        raw = bytes(data[p:p + size])
        p += size
        name = ACTION_NAMES.get(code, f"Action0x{code:02X}")
        actions.append(Avm1Action(code, name, raw, _action_argument(code, raw)))
    return tuple(actions), p


def _parse_record(data: bytes, p: int, version: int):
    _need(data, p, 1, "ButtonRecord-Flags")
    flags = data[p]
    p += 1
    if flags == 0:
        return None, p
    states = tuple(name for bit, name in _STATE_BITS if flags & bit)
    character_id = _u16(data, p, "ButtonRecord-Character-ID")
    depth = _u16(data, p + 2, "ButtonRecord-Tiefe")
    p += 4
    matrix_start = p
    matrix, p = ui_browser._read_matrix(data, p)
    raw_matrix = bytes(data[matrix_start:p])
    color = ui_browser.IDENTITY_COLOR
    raw_color = b""
    raw_filters = b""
    blend_mode = None
    if version >= 2:
        color_start = p
        color, p = ui_browser._read_color_transform(data, p, True)
        raw_color = bytes(data[color_start:p])
        if flags & 0x10:
            if scale9 is None or not hasattr(scale9, "parse_filter_list"):
                raise ButtonParseError("Button-FilterList kann ohne Scale9/Blend-Parser nicht gelesen werden")
            filter_start = p
            _filters, p = scale9.parse_filter_list(data, p)
            raw_filters = bytes(data[filter_start:p])
        if flags & 0x20:
            _need(data, p, 1, "Button-BlendMode")
            blend_mode = data[p]
            p += 1
    return ButtonRecord(
        character_id, depth, matrix, color, states, raw_matrix, raw_color,
        raw_filters, blend_mode,
    ), p


def _parse_records(data: bytes, start: int, version: int):
    p = int(start)
    records = []
    while True:
        record, p = _parse_record(data, p, version)
        if record is None:
            break
        records.append(record)
        if len(records) > 100_000:
            raise ButtonParseError("DefineButton enthält zu viele ButtonRecords")
    return tuple(records), p


def _condition_names(flags: int):
    return tuple(name for bit, name in _CONDITION_BITS if flags & bit)


def _parse_cond_actions(payload: bytes, start: int):
    p = int(start)
    result = []
    while p < len(payload):
        block_start = p
        size = _u16(payload, p, "ButtonCondAction-Größe")
        p += 2
        flags = _u16(payload, p, "ButtonCondAction-Bedingungen")
        p += 2
        block_end = len(payload) if size == 0 else block_start + size
        if block_end < p or block_end > len(payload):
            raise ButtonParseError("ButtonCondAction besitzt ungültige Grenzen")
        actions, _ = parse_avm1_actions(payload, p, block_end)
        result.append(ButtonActionBinding(
            _condition_names(flags), (flags >> 1) & 0x7F, actions, flags,
        ))
        if size == 0:
            break
        p = block_end
        if len(result) > 100_000:
            raise ButtonParseError("DefineButton2 enthält zu viele Action-Blöcke")
    return tuple(result)


def parse_classic_button(payload: bytes, version: int):
    payload = bytes(payload)
    _need(payload, 0, 2, "Button-ID")
    character_id = _u16(payload, 0, "Button-ID")
    if int(version) == 1:
        records, p = _parse_records(payload, 2, 1)
        actions, _ = parse_avm1_actions(payload, p)
        bindings = (
            ButtonActionBinding(("over_down_to_over_up",), 0, actions, 0x0800),
        ) if actions else ()
        return ClassicButtonDef(character_id, 1, records, bindings)
    if int(version) != 2:
        raise ButtonParseError(f"Unbekannte Button-Version {version}")
    _need(payload, 2, 3, "DefineButton2-Header")
    track_as_menu = bool(payload[2] & 0x01)
    action_offset = _u16(payload, 3, "DefineButton2-ActionOffset")
    records, p = _parse_records(payload, 5, 2)
    if action_offset:
        expected = 3 + action_offset
        if expected < p or expected > len(payload):
            raise ButtonParseError("DefineButton2-ActionOffset liegt außerhalb des Datensatzes")
        p = expected
        bindings = _parse_cond_actions(payload, p)
    else:
        bindings = ()
    return ClassicButtonDef(character_id, 2, records, bindings, track_as_menu)


def parse_button_tags(tags):
    result = {}
    errors = []
    for code, payload in tuple(tags or ()):
        if code not in (TAG_DEFINE_BUTTON, TAG_DEFINE_BUTTON2):
            continue
        version = 1 if code == TAG_DEFINE_BUTTON else 2
        try:
            button = parse_classic_button(payload, version)
            result[button.character_id] = button
        except Exception as exc:
            errors.append({"tag": code, "error": str(exc)})
    return result, tuple(errors)


def _transform_bounds(bounds, matrix):
    xmin, ymin, xmax, ymax = bounds
    points = (
        (matrix.a * xmin + matrix.c * ymin + matrix.tx,
         matrix.b * xmin + matrix.d * ymin + matrix.ty),
        (matrix.a * xmax + matrix.c * ymin + matrix.tx,
         matrix.b * xmax + matrix.d * ymin + matrix.ty),
        (matrix.a * xmax + matrix.c * ymax + matrix.tx,
         matrix.b * xmax + matrix.d * ymax + matrix.ty),
        (matrix.a * xmin + matrix.c * ymax + matrix.tx,
         matrix.b * xmin + matrix.d * ymax + matrix.ty),
    )
    return (
        min(value[0] for value in points), min(value[1] for value in points),
        max(value[0] for value in points), max(value[1] for value in points),
    )


def _union(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return (
        min(left[0], right[0]), min(left[1], right[1]),
        max(left[2], right[2]), max(left[3], right[3]),
    )


def definition_local_bounds(movie, definition, stack=()):
    if definition is None:
        return None
    if isinstance(definition, ClassicButtonDef):
        if definition.character_id in stack:
            return None
        result = None
        records = definition.hit_records or definition.records
        for record in records:
            child = movie.definitions.get(record.character_id)
            bounds = definition_local_bounds(movie, child, stack + (definition.character_id,))
            if bounds is not None:
                result = _union(result, _transform_bounds(bounds, record.matrix))
        return result
    vector = getattr(ui_browser, "VectorShapeDef", ())
    if vector and isinstance(definition, vector):
        return tuple(getattr(definition, "edge_bounds", definition.bounds))
    if hasattr(definition, "bounds") and not isinstance(definition, ui_browser.SpriteDef):
        return tuple(definition.bounds)
    if isinstance(definition, ui_browser.SpriteDef):
        if definition.character_id in stack:
            return None
        result = None
        display = ui_browser.build_display_list(definition.tags, 1)
        for item in display.values():
            child = movie.definitions.get(getattr(item, "character_id", None))
            bounds = definition_local_bounds(movie, child, stack + (definition.character_id,))
            if bounds is not None:
                result = _union(result, _transform_bounds(bounds, item.matrix))
        return result
    return None


def finalize_button_bounds(movie):
    for definition in movie.definitions.values():
        if not isinstance(definition, ClassicButtonDef):
            continue
        bounds = definition_local_bounds(movie, definition)
        if bounds is not None:
            definition.bounds = tuple(float(value) for value in bounds)
    return movie


@dataclass(frozen=True)
class HitClip:
    geometries: tuple["HitGeometry", ...]
    label: str = ""

    def contains(self, point) -> bool:
        return any(value.contains(point) for value in self.geometries)


@dataclass(frozen=True)
class HitGeometry:
    path: str
    kind: str
    bounds: tuple[float, float, float, float]
    inverse: tuple[float, float, float, float, float, float] | None = None
    local_bounds: tuple[float, float, float, float] | None = None
    alpha: object | None = None
    alpha_origin: tuple[float, float] = (0.0, 0.0)
    clips: tuple[HitClip, ...] = ()
    character_id: int | None = None

    def local_point(self, point):
        if self.inverse is None:
            return point
        ia, ib, ic, id_, ie, iff = self.inverse
        x, y = point
        return ia * x + ib * y + ic, id_ * x + ie * y + iff

    def contains(self, point) -> bool:
        x, y = point
        left, top, right, bottom = self.bounds
        if not (left <= x <= right and top <= y <= bottom):
            return False
        if any(not clip.contains(point) for clip in self.clips):
            return False
        lx, ly = self.local_point(point)
        if self.local_bounds is not None:
            left, top, right, bottom = self.local_bounds
            if not (left <= lx <= right and top <= ly <= bottom):
                return False
        if self.alpha is not None:
            ox, oy = self.alpha_origin
            ix = int(math.floor(lx - ox))
            iy = int(math.floor(ly - oy))
            if ix < 0 or iy < 0 or ix >= int(self.alpha.width) or iy >= int(self.alpha.height):
                return False
            try:
                value = self.alpha.getpixel((ix, iy))
                if isinstance(value, tuple):
                    value = value[-1]
                return int(value) >= 8
            except Exception:
                return False
        return True


def normalize_rect(value):
    if value is None:
        return None
    source = value
    if hasattr(value, "properties") and isinstance(value.properties, dict):
        source = value.properties
    if isinstance(source, dict):
        if all(key in source for key in ("x", "y", "width", "height")):
            x, y = float(source["x"]), float(source["y"])
            return x, y, x + max(0.0, float(source["width"])), y + max(0.0, float(source["height"]))
        if all(key in source for key in ("left", "top", "right", "bottom")):
            return tuple(float(source[key]) for key in ("left", "top", "right", "bottom"))
    if isinstance(source, (tuple, list)) and len(source) >= 4:
        x, y, width, height = map(float, source[:4])
        return x, y, x + max(0.0, width), y + max(0.0, height)
    try:
        x, y = float(source.x), float(source.y)
        width, height = float(source.width), float(source.height)
        return x, y, x + max(0.0, width), y + max(0.0, height)
    except Exception:
        return None
