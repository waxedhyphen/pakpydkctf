"""Validated SWF timeline instance copier for Scaleform UI movies."""
from __future__ import annotations

from dataclasses import dataclass

import ui_browser_avm2_repack as repack


END = 0
SHOW_FRAME = 1
REMOVE_OBJECT = 5
PLACE_OBJECT2 = 26
REMOVE_OBJECT2 = 28
DEFINE_SPRITE = 39
PLACE_OBJECT3 = 70


class TimelinePatchError(ValueError):
    pass


@dataclass(frozen=True)
class Tag:
    code: int
    payload: bytes


@dataclass(frozen=True)
class Placement:
    depth: int
    character_id: int | None
    name: str
    matrix: bytes
    move: bool


@dataclass(frozen=True)
class TimelineCopySpec:
    source_sprite_id: int
    source_name: str
    target_sprite_id: int
    target_name: str
    anchor_name: str = ""
    depth: int | None = None
    replace_existing: bool = False


@dataclass(frozen=True)
class TimelinePatchResult:
    movie_data: bytes
    report: dict
    signature: str


def _tag(code, payload):
    payload = bytes(payload)
    if len(payload) < 63:
        return ((int(code) << 6) | len(payload)).to_bytes(2, "little") + payload
    return (
        ((int(code) << 6) | 63).to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
        + payload
    )


def _tags(data):
    data = bytes(data)
    out = []
    p = 0
    while p + 2 <= len(data):
        word = int.from_bytes(data[p:p + 2], "little")
        p += 2
        code = word >> 6
        size = word & 0x3F
        if size == 0x3F:
            if p + 4 > len(data):
                raise TimelinePatchError("SWF-Langtag ist abgeschnitten")
            size = int.from_bytes(data[p:p + 4], "little")
            p += 4
        end = p + size
        if end > len(data):
            raise TimelinePatchError(f"SWF-Tag {code} läuft über das Dateiende")
        out.append(Tag(code, data[p:end]))
        p = end
        if code == END:
            break
    return out, data[p:]


def _tag_stream(records, tail=b""):
    return b"".join(_tag(item.code, item.payload) for item in records) + bytes(tail)


def _string(data, p, label):
    end = data.find(b"\x00", p)
    if end < 0:
        raise TimelinePatchError(f"{label} ist nicht nullterminiert")
    return data[p:end].decode("utf-8", "replace"), end + 1


def _bits(data, bit, count, label):
    if bit + count > len(data) * 8:
        raise TimelinePatchError(f"{label} ist abgeschnitten")
    value = 0
    for _ in range(count):
        value = (value << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
        bit += 1
    return value, bit


def _matrix_end(data, p):
    bit = p * 8
    present, bit = _bits(data, bit, 1, "MATRIX")
    if present:
        count, bit = _bits(data, bit, 5, "MATRIX")
        _, bit = _bits(data, bit, count * 2, "MATRIX")
    present, bit = _bits(data, bit, 1, "MATRIX")
    if present:
        count, bit = _bits(data, bit, 5, "MATRIX")
        _, bit = _bits(data, bit, count * 2, "MATRIX")
    count, bit = _bits(data, bit, 5, "MATRIX")
    _, bit = _bits(data, bit, count * 2, "MATRIX")
    return (bit + 7) // 8


def _cxform_end(data, p):
    bit = p * 8
    add, bit = _bits(data, bit, 1, "CXFORM")
    mult, bit = _bits(data, bit, 1, "CXFORM")
    count, bit = _bits(data, bit, 4, "CXFORM")
    if mult:
        _, bit = _bits(data, bit, count * 4, "CXFORM")
    if add:
        _, bit = _bits(data, bit, count * 4, "CXFORM")
    return (bit + 7) // 8


def _place(record):
    data = record.payload
    if record.code == PLACE_OBJECT2:
        if len(data) < 3:
            raise TimelinePatchError("PlaceObject2 ist abgeschnitten")
        f1, f2, p = data[0], 0, 3
        depth = int.from_bytes(data[1:3], "little")
    elif record.code == PLACE_OBJECT3:
        if len(data) < 4:
            raise TimelinePatchError("PlaceObject3 ist abgeschnitten")
        f1, f2, p = data[0], data[1], 4
        depth = int.from_bytes(data[2:4], "little")
        if f2 & 0x08 or ((f2 & 0x10) and (f1 & 0x02)):
            _, p = _string(data, p, "PlaceObject3-Klassenname")
    else:
        return None
    character_id = None
    matrix = b""
    name = ""
    if f1 & 0x02:
        if p + 2 > len(data):
            raise TimelinePatchError("PlaceObject-Character ist abgeschnitten")
        character_id = int.from_bytes(data[p:p + 2], "little")
        p += 2
    if f1 & 0x04:
        end = _matrix_end(data, p)
        matrix = data[p:end]
        p = end
    if f1 & 0x08:
        p = _cxform_end(data, p)
    if f1 & 0x10:
        p += 2
    if f1 & 0x20:
        name, p = _string(data, p, "PlaceObject-Name")
    return Placement(depth, character_id, name, matrix, bool(f1 & 0x01))


def _first_frame(records):
    display = {}
    for record in records:
        if record.code == SHOW_FRAME:
            break
        item = _place(record)
        if item is not None:
            old = display.get(item.depth)
            if item.move and old is not None:
                item = Placement(
                    item.depth,
                    item.character_id if item.character_id is not None else old.character_id,
                    item.name or old.name,
                    item.matrix or old.matrix,
                    True,
                )
            display[item.depth] = item
        elif record.code == REMOVE_OBJECT2 and len(record.payload) >= 2:
            display.pop(int.from_bytes(record.payload[:2], "little"), None)
        elif record.code == REMOVE_OBJECT and len(record.payload) >= 4:
            display.pop(int.from_bytes(record.payload[2:4], "little"), None)
    return display


def _sprites(records, found=None):
    found = {} if found is None else found
    for record in records:
        if record.code != DEFINE_SPRITE or len(record.payload) < 4:
            continue
        sprite_id = int.from_bytes(record.payload[:2], "little")
        if sprite_id in found:
            raise TimelinePatchError(f"DefineSprite {sprite_id} ist mehrfach vorhanden")
        nested, _ = _tags(record.payload[4:])
        found[sprite_id] = tuple(nested)
        _sprites(nested, found)
    return found


def _root(movie_data):
    data, signature = repack._inflate_swf(movie_data)
    start = repack._swf_header_end(data)
    records, tail = _tags(data[start:])
    return data, signature, start, records, tail


def inspect_sprites(movie_data):
    _data, _signature, _start, records, _tail = _root(movie_data)
    result = {}
    for sprite_id, nested in _sprites(records).items():
        result[sprite_id] = tuple(
            {
                "depth": depth,
                "name": item.name,
                "character_id": item.character_id,
                "matrix_hex": item.matrix.hex(" ").upper(),
            }
            for depth, item in sorted(_first_frame(nested).items())
        )
    return result


def _named(state, name, sprite_id):
    values = [item for item in state.values() if item.name == name]
    if len(values) != 1:
        word = "keine" if not values else "mehrere"
        raise TimelinePatchError(f"Sprite {sprite_id} enthält {word} Instanz namens {name!r}")
    return values[0]


def plan_copy_instance(movie_data, spec):
    if not isinstance(spec, TimelineCopySpec):
        spec = TimelineCopySpec(**dict(spec))
    if not spec.source_name or not spec.target_name:
        raise TimelinePatchError("Quell- und Zielname dürfen nicht leer sein")
    _data, signature, _start, records, _tail = _root(movie_data)
    sprites = _sprites(records)
    source_records = sprites.get(int(spec.source_sprite_id))
    target_records = sprites.get(int(spec.target_sprite_id))
    if source_records is None or target_records is None:
        missing = spec.source_sprite_id if source_records is None else spec.target_sprite_id
        raise TimelinePatchError(f"Sprite {missing} wurde nicht gefunden")
    source_state = _first_frame(source_records)
    target_state = _first_frame(target_records)
    source = _named(source_state, spec.source_name, spec.source_sprite_id)
    if source.character_id is None:
        raise TimelinePatchError("Quellinstanz hat keine Character-ID")
    existing = [item for item in target_state.values() if item.name == spec.target_name]
    if existing and not spec.replace_existing:
        raise TimelinePatchError(f"Ziel enthält {spec.target_name!r} bereits")
    anchor = _named(target_state, spec.anchor_name, spec.target_sprite_id) if spec.anchor_name else None
    matrix = (anchor.matrix if anchor else source.matrix) or b"\x00"
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
        raise TimelinePatchError(f"Zieltiefe {depth} ist ungültig oder belegt")
    return {
        "signature": signature.decode("ascii", "replace"),
        "source_sprite_id": int(spec.source_sprite_id),
        "source_name": spec.source_name,
        "source_depth": source.depth,
        "character_id": source.character_id,
        "target_sprite_id": int(spec.target_sprite_id),
        "target_name": spec.target_name,
        "anchor_name": spec.anchor_name,
        "anchor_depth": anchor.depth if anchor else None,
        "matrix_hex": matrix.hex(" ").upper(),
        "target_depth": depth,
        "depth_reason": reason,
        "replace_existing": bool(spec.replace_existing),
        "target_before": tuple(
            {"depth": item.depth, "name": item.name, "character_id": item.character_id}
            for item in sorted(target_state.values(), key=lambda value: value.depth)
        ),
    }


def _new_place(character_id, depth, matrix, name):
    name_bytes = name.encode("utf-8")
    if b"\x00" in name_bytes:
        raise TimelinePatchError("Zielname enthält ein Nullbyte")
    payload = (
        b"\x26"
        + int(depth).to_bytes(2, "little")
        + int(character_id).to_bytes(2, "little")
        + bytes(matrix or b"\x00")
        + name_bytes
        + b"\x00"
    )
    check = _place(Tag(PLACE_OBJECT2, payload))
    if check is None or check.name != name or check.depth != depth or check.character_id != character_id:
        raise TimelinePatchError("Neuer PlaceObject2-Eintrag ist ungültig")
    return Tag(PLACE_OBJECT2, payload)


def _rewrite(records, spec, insertion):
    out = []
    changed = False
    found = False
    for record in records:
        if record.code != DEFINE_SPRITE or len(record.payload) < 4:
            out.append(record)
            continue
        sprite_id = int.from_bytes(record.payload[:2], "little")
        nested, tail = _tags(record.payload[4:])
        if sprite_id == int(spec.target_sprite_id):
            if found:
                raise TimelinePatchError("Ziel-Sprite ist mehrfach vorhanden")
            found = True
            state = _first_frame(nested)
            remove_depths = {
                item.depth for item in state.values()
                if spec.replace_existing and item.name == spec.target_name
            }
            rebuilt = []
            inserted = False
            first_frame = True
            for child in nested:
                item = _place(child)
                if first_frame and item is not None and item.depth in remove_depths:
                    continue
                if child.code == SHOW_FRAME and not inserted:
                    rebuilt.append(insertion)
                    inserted = True
                    first_frame = False
                rebuilt.append(child)
            if not inserted:
                end = next((i for i, item in enumerate(rebuilt) if item.code == END), len(rebuilt))
                rebuilt.insert(end, insertion)
            out.append(Tag(DEFINE_SPRITE, record.payload[:4] + _tag_stream(rebuilt, tail)))
            changed = True
        else:
            children, child_changed, child_found = _rewrite(nested, spec, insertion)
            if child_found:
                if found:
                    raise TimelinePatchError("Ziel-Sprite ist mehrfach vorhanden")
                found = True
            if child_changed:
                out.append(Tag(DEFINE_SPRITE, record.payload[:4] + _tag_stream(children, tail)))
                changed = True
            else:
                out.append(record)
    return out, changed, found


def copy_instance(movie_data, spec):
    if not isinstance(spec, TimelineCopySpec):
        spec = TimelineCopySpec(**dict(spec))
    plan = plan_copy_instance(movie_data, spec)
    insertion = _new_place(
        plan["character_id"], plan["target_depth"],
        bytes.fromhex(plan["matrix_hex"]), spec.target_name,
    )
    data, signature, start, records, tail = _root(movie_data)
    rewritten, changed, found = _rewrite(records, spec, insertion)
    if not found or not changed:
        raise TimelinePatchError("Ziel-Sprite wurde nicht verändert")
    rebuilt = bytearray(data[:start])
    rebuilt += _tag_stream(rewritten, tail)
    result = repack._deflate_swf(rebuilt, signature)
    target_after = inspect_sprites(result).get(int(spec.target_sprite_id), ())
    matches = [item for item in target_after if item["name"] == spec.target_name]
    if len(matches) != 1:
        raise TimelinePatchError("Nachprüfung: Zielinstanz ist nicht eindeutig")
    if matches[0]["character_id"] != plan["character_id"] or matches[0]["depth"] != plan["target_depth"]:
        raise TimelinePatchError("Nachprüfung: Character-ID oder Tiefe stimmt nicht")
    report = dict(plan)
    report.update({
        "target_after": tuple(target_after),
        "movie_size_before": len(movie_data),
        "movie_size_after": len(result),
        "structural_validation": "passed",
    })
    return TimelinePatchResult(result, report, signature.decode("ascii", "replace"))