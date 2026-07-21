"""Static Scaleform/GFX browser for Tropical Freeze UI assets.

The first implementation intentionally does not execute ActionScript. It parses the
GFX container and enough of the SWF display list to render imported TXTR-backed
sprites, simple shape bounds, and edit-text placeholders. The stage is always fit
inside the Tk canvas while preserving the movie's native aspect ratio.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import math
import tkinter as tk
from tkinter import filedialog, ttk
import zlib

from pak_core import PakError, get_entry_asset

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
except Exception:
    Image = None
    ImageDraw = None
    ImageFont = None
    ImageTk = None

try:
    from txtrpreview import decode_txtr_image, parse_txtr_asset
except Exception:
    decode_txtr_image = None
    parse_txtr_asset = None


GFX_TYPE = "GFX"
GFXL_TYPE = "GFXL"


def _be32(data, off):
    return int.from_bytes(data[off:off + 4], "big")


def _be64(data, off):
    return int.from_bytes(data[off:off + 8], "big")


def _le16(data, off):
    return int.from_bytes(data[off:off + 2], "little")


def _le32(data, off):
    return int.from_bytes(data[off:off + 4], "little")


def _tag4(data, off):
    return data[off:off + 4].decode("ascii", "replace")


def _read_c_string(data, off):
    end = data.find(b"\x00", off)
    if end < 0:
        raise PakError("SWF-String ist nicht nullterminiert")
    return data[off:end].decode("utf-8", "replace"), end + 1


def _entry_name(entry):
    return entry.get("display_name") or entry.get("name") or entry.get("uuid_hex", "UI")


def _normal_type(entry):
    return str(entry.get("type", "")).strip().upper()


@dataclass
class GfxMovieRecord:
    name: str
    data: bytes
    offset: int
    size: int


@dataclass
class GfxContainer:
    library_uuid: str
    movies: list


@dataclass
class GfxLibrary:
    name: str
    mappings: dict
    movie_data: bytes
    source: str = ""
    entry_uuid: str = ""


def _asset_chunk_payload(asset, expected_tag):
    if len(asset) < 56 or asset[:4] != b"RFRM":
        raise PakError(f"{expected_tag} hat keinen gültigen RFRM-Wrapper")
    if _tag4(asset, 20).strip() != expected_tag.strip():
        raise PakError(f"Erwartet {expected_tag}, gefunden {_tag4(asset, 20)}")
    if _tag4(asset, 32).strip() != expected_tag.strip():
        raise PakError(f"{expected_tag}-Asset enthält keinen passenden Daten-Chunk")
    size = _be64(asset, 36)
    payload_off = 56
    payload_end = payload_off + size
    if payload_end > len(asset):
        raise PakError(f"{expected_tag}-Chunk läuft über das Dateiende")
    return payload_off, payload_end


def parse_gfx_asset(asset):
    payload_off, payload_end = _asset_chunk_payload(asset, "GFX")
    payload = asset[payload_off:payload_end]
    if len(payload) < 36:
        raise PakError("GFX-Payload ist zu klein")
    library_uuid = payload[:16].hex()
    count_off = 32
    count = _be32(payload, count_off)
    table_off = count_off + 4
    table_end = table_off + count * 64
    if table_end > len(payload):
        raise PakError("GFX-Filmtabelle ist abgeschnitten")
    movies = []
    for index in range(count):
        rec_off = table_off + index * 64
        rel_off = _be64(payload, rec_off)
        size = _be64(payload, rec_off + 8)
        name = payload[rec_off + 16:rec_off + 64].split(b"\x00", 1)[0].decode("utf-8", "replace")
        movie_off = count_off + rel_off
        movie_end = movie_off + size
        if movie_off < table_end or movie_end > len(payload):
            raise PakError(f"GFX-Film {name or index} hat ungültige Grenzen")
        movies.append(GfxMovieRecord(name or f"Movie {index + 1}", payload[movie_off:movie_end], movie_off, size))
    return GfxContainer(library_uuid, movies)


def parse_gfxl_asset(asset, source="", entry_uuid=""):
    payload_off, payload_end = _asset_chunk_payload(asset, "GFXL")
    payload = asset[payload_off:payload_end]
    if len(payload) < 4:
        raise PakError("GFXL-Payload ist zu klein")
    count = _be32(payload, 0)
    p = 4
    mappings = {}
    for index in range(count):
        if p + 20 > len(payload):
            raise PakError(f"GFXL-Zuordnung {index} ist abgeschnitten")
        uuid_hex = payload[p:p + 16].hex()
        name_len = _be32(payload, p + 16)
        p += 20
        if p + name_len > len(payload):
            raise PakError(f"GFXL-Name {index} ist abgeschnitten")
        name = payload[p:p + name_len].decode("utf-8", "replace")
        p += name_len
        mappings[name] = uuid_hex
    if p + 4 > len(payload):
        raise PakError("GFXL hat keinen Library-Namen")
    name_len = _be32(payload, p)
    p += 4
    if p + name_len > len(payload):
        raise PakError("GFXL-Library-Name ist abgeschnitten")
    name = payload[p:p + name_len].decode("utf-8", "replace")
    p += name_len
    return GfxLibrary(name, mappings, payload[p:], source, entry_uuid)


class _BitReader:
    def __init__(self, data, byte_off=0):
        self.data = data
        self.bit_pos = byte_off * 8

    def read_u(self, count):
        value = 0
        for _ in range(count):
            byte_index = self.bit_pos >> 3
            if byte_index >= len(self.data):
                raise PakError("SWF-Bitfeld ist abgeschnitten")
            shift = 7 - (self.bit_pos & 7)
            value = (value << 1) | ((self.data[byte_index] >> shift) & 1)
            self.bit_pos += 1
        return value

    def read_s(self, count):
        value = self.read_u(count)
        if count and value & (1 << (count - 1)):
            value -= 1 << count
        return value

    def align(self):
        self.bit_pos = (self.bit_pos + 7) & ~7

    @property
    def byte_pos(self):
        return (self.bit_pos + 7) >> 3


@dataclass(frozen=True)
class Affine:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    tx: float = 0.0
    ty: float = 0.0

    def then(self, local):
        return Affine(
            self.a * local.a + self.c * local.b,
            self.b * local.a + self.d * local.b,
            self.a * local.c + self.c * local.d,
            self.b * local.c + self.d * local.d,
            self.a * local.tx + self.c * local.ty + self.tx,
            self.b * local.tx + self.d * local.ty + self.ty,
        )

    def inverse_pillow(self):
        det = self.a * self.d - self.b * self.c
        if abs(det) < 1e-12:
            return None
        ia = self.d / det
        ib = -self.c / det
        id_ = -self.b / det
        ie = self.a / det
        ic = -(ia * self.tx + ib * self.ty)
        iff = -(id_ * self.tx + ie * self.ty)
        return ia, ib, ic, id_, ie, iff


@dataclass(frozen=True)
class ColorTransform:
    r_mult: float = 1.0
    g_mult: float = 1.0
    b_mult: float = 1.0
    a_mult: float = 1.0
    r_add: int = 0
    g_add: int = 0
    b_add: int = 0
    a_add: int = 0

    def combine(self, local):
        return ColorTransform(
            self.r_mult * local.r_mult,
            self.g_mult * local.g_mult,
            self.b_mult * local.b_mult,
            self.a_mult * local.a_mult,
            int(self.r_add * local.r_mult + local.r_add),
            int(self.g_add * local.g_mult + local.g_add),
            int(self.b_add * local.b_mult + local.b_add),
            int(self.a_add * local.a_mult + local.a_add),
        )


IDENTITY_COLOR = ColorTransform()


@dataclass
class PlaceCommand:
    depth: int
    move: bool
    character_id: int | None = None
    class_name: str | None = None
    matrix: Affine | None = None
    color: ColorTransform | None = None
    name: str | None = None
    clip_depth: int | None = None
    visible: bool | None = None


@dataclass
class DisplayObject:
    depth: int
    character_id: int | None = None
    class_name: str | None = None
    matrix: Affine = Affine()
    color: ColorTransform = IDENTITY_COLOR
    name: str = ""
    clip_depth: int | None = None
    visible: bool = True


@dataclass
class ShapeDef:
    character_id: int
    bounds: tuple


@dataclass
class EditTextDef:
    character_id: int
    bounds: tuple
    variable_name: str
    initial_text: str
    color: tuple
    font_height: float
    border: bool


@dataclass
class SpriteDef:
    character_id: int
    frame_count: int
    tags: list
    labels: dict = field(default_factory=dict)


@dataclass
class SwfMovie:
    version: int
    stage_bounds: tuple
    frame_rate: float
    frame_count: int
    root_tags: list
    definitions: dict
    background: tuple
    symbol_classes: dict
    imports: list
    labels: dict

    @property
    def width(self):
        return max(1, int(round(self.stage_bounds[2] - self.stage_bounds[0])))

    @property
    def height(self):
        return max(1, int(round(self.stage_bounds[3] - self.stage_bounds[1])))


TAG_END = 0
TAG_SHOW_FRAME = 1
TAG_DEFINE_SHAPE = 2
TAG_REMOVE_OBJECT = 5
TAG_SET_BACKGROUND = 9
TAG_DEFINE_SHAPE2 = 22
TAG_PLACE_OBJECT2 = 26
TAG_REMOVE_OBJECT2 = 28
TAG_DEFINE_SHAPE3 = 32
TAG_DEFINE_EDIT_TEXT = 37
TAG_DEFINE_SPRITE = 39
TAG_FRAME_LABEL = 43
TAG_IMPORT_ASSETS = 57
TAG_PLACE_OBJECT3 = 70
TAG_IMPORT_ASSETS2 = 71
TAG_SYMBOL_CLASS = 76
TAG_DEFINE_SHAPE4 = 83


def _read_rect(data, off):
    reader = _BitReader(data, off)
    nbits = reader.read_u(5)
    xmin = reader.read_s(nbits) / 20.0
    xmax = reader.read_s(nbits) / 20.0
    ymin = reader.read_s(nbits) / 20.0
    ymax = reader.read_s(nbits) / 20.0
    reader.align()
    return (xmin, ymin, xmax, ymax), reader.byte_pos


def _read_matrix(data, off):
    reader = _BitReader(data, off)
    scale_x = scale_y = 1.0
    rotate_0 = rotate_1 = 0.0
    if reader.read_u(1):
        nbits = reader.read_u(5)
        scale_x = reader.read_s(nbits) / 65536.0
        scale_y = reader.read_s(nbits) / 65536.0
    if reader.read_u(1):
        nbits = reader.read_u(5)
        rotate_0 = reader.read_s(nbits) / 65536.0
        rotate_1 = reader.read_s(nbits) / 65536.0
    nbits = reader.read_u(5)
    tx = reader.read_s(nbits) / 20.0 if nbits else 0.0
    ty = reader.read_s(nbits) / 20.0 if nbits else 0.0
    reader.align()
    return Affine(scale_x, rotate_0, rotate_1, scale_y, tx, ty), reader.byte_pos


def _read_color_transform(data, off, with_alpha=True):
    reader = _BitReader(data, off)
    has_add = bool(reader.read_u(1))
    has_mult = bool(reader.read_u(1))
    nbits = reader.read_u(4)
    count = 4 if with_alpha else 3
    mult = [256] * count
    add = [0] * count
    if has_mult:
        mult = [reader.read_s(nbits) for _ in range(count)]
    if has_add:
        add = [reader.read_s(nbits) for _ in range(count)]
    reader.align()
    if not with_alpha:
        mult.append(256)
        add.append(0)
    return ColorTransform(
        mult[0] / 256.0, mult[1] / 256.0, mult[2] / 256.0, mult[3] / 256.0,
        add[0], add[1], add[2], add[3],
    ), reader.byte_pos


def _decompress_swf(raw):
    if len(raw) < 8:
        raise PakError("SWF/GFX-Film ist zu klein")
    signature = raw[:3]
    if signature == b"CWS":
        try:
            body = zlib.decompress(raw[8:])
        except Exception as exc:
            raise PakError(f"CWS konnte nicht entpackt werden: {exc}") from exc
        data = b"FWS" + raw[3:8] + body
    elif signature in (b"FWS", b"GFX"):
        data = raw
    else:
        raise PakError(f"Unbekannte SWF-Signatur {signature!r}")
    expected = _le32(data, 4)
    if expected > len(data):
        raise PakError("SWF-Dateilänge ist größer als die vorhandenen Daten")
    return data[:expected]


def _iter_tags(data, off, end=None):
    end = len(data) if end is None else min(end, len(data))
    result = []
    p = off
    while p + 2 <= end:
        record = _le16(data, p)
        p += 2
        code = record >> 6
        length = record & 0x3F
        if length == 0x3F:
            if p + 4 > end:
                raise PakError("SWF-Langtag ist abgeschnitten")
            length = _le32(data, p)
            p += 4
        payload_end = p + length
        if payload_end > end:
            raise PakError(f"SWF-Tag {code} läuft über das Dateiende")
        result.append((code, data[p:payload_end]))
        p = payload_end
        if code == TAG_END:
            break
    return result


def _parse_frame_labels(tags):
    labels = {}
    frame = 1
    for code, payload in tags:
        if code == TAG_FRAME_LABEL:
            try:
                name, _ = _read_c_string(payload, 0)
                labels[name] = frame
            except Exception:
                pass
        elif code == TAG_SHOW_FRAME:
            frame += 1
    return labels


def _parse_edit_text(payload):
    if len(payload) < 4:
        raise PakError("DefineEditText ist abgeschnitten")
    character_id = _le16(payload, 0)
    bounds, p = _read_rect(payload, 2)
    if p + 2 > len(payload):
        raise PakError("DefineEditText-Flags fehlen")
    flags1 = payload[p]
    flags2 = payload[p + 1]
    p += 2
    has_text = bool(flags1 & 0x80)
    has_text_color = bool(flags1 & 0x04)
    has_max_length = bool(flags1 & 0x02)
    has_font = bool(flags1 & 0x01)
    has_font_class = bool(flags2 & 0x80)
    has_layout = bool(flags2 & 0x20)
    border = bool(flags2 & 0x08)
    if has_font:
        p += 2
    if has_font_class:
        _, p = _read_c_string(payload, p)
    font_height = 18.0
    if has_font:
        font_height = _le16(payload, p) / 20.0
        p += 2
    color = (255, 255, 255, 255)
    if has_text_color:
        color = tuple(payload[p:p + 4])
        p += 4
    if has_max_length:
        p += 2
    if has_layout:
        p += 9
    variable_name, p = _read_c_string(payload, p)
    initial_text = ""
    if has_text and p < len(payload):
        initial_text, p = _read_c_string(payload, p)
    return EditTextDef(character_id, bounds, variable_name, initial_text, color, font_height, border)


def _parse_symbol_class(payload):
    result = {}
    if len(payload) < 2:
        return result
    count = _le16(payload, 0)
    p = 2
    for _ in range(count):
        if p + 2 > len(payload):
            break
        character_id = _le16(payload, p)
        p += 2
        try:
            name, p = _read_c_string(payload, p)
        except Exception:
            break
        result[character_id] = name
    return result


def parse_swf_movie(raw):
    data = _decompress_swf(raw)
    version = data[3]
    stage_bounds, p = _read_rect(data, 8)
    if p + 4 > len(data):
        raise PakError("SWF-Header ist abgeschnitten")
    frame_rate = _le16(data, p) / 256.0
    frame_count = _le16(data, p + 2)
    root_tags = _iter_tags(data, p + 4)
    definitions = {}
    background = (0, 0, 0, 0)
    symbol_classes = {}
    imports = []
    for code, payload in root_tags:
        try:
            if code in (TAG_DEFINE_SHAPE, TAG_DEFINE_SHAPE2, TAG_DEFINE_SHAPE3, TAG_DEFINE_SHAPE4):
                character_id = _le16(payload, 0)
                bounds, _ = _read_rect(payload, 2)
                definitions[character_id] = ShapeDef(character_id, bounds)
            elif code == TAG_DEFINE_EDIT_TEXT:
                definition = _parse_edit_text(payload)
                definitions[definition.character_id] = definition
            elif code == TAG_DEFINE_SPRITE:
                if len(payload) < 4:
                    continue
                character_id = _le16(payload, 0)
                sprite_frames = _le16(payload, 2)
                sprite_tags = _iter_tags(payload, 4)
                definitions[character_id] = SpriteDef(character_id, sprite_frames, sprite_tags, _parse_frame_labels(sprite_tags))
            elif code == TAG_SET_BACKGROUND and len(payload) >= 3:
                background = (payload[0], payload[1], payload[2], 255)
            elif code == TAG_SYMBOL_CLASS:
                symbol_classes.update(_parse_symbol_class(payload))
            elif code in (TAG_IMPORT_ASSETS, TAG_IMPORT_ASSETS2):
                url, _ = _read_c_string(payload, 0)
                if url and url not in imports:
                    imports.append(url)
        except Exception:
            continue
    return SwfMovie(
        version, stage_bounds, frame_rate, max(1, frame_count), root_tags,
        definitions, background, symbol_classes, imports, _parse_frame_labels(root_tags),
    )


def _parse_place_object2(payload):
    if len(payload) < 3:
        raise PakError("PlaceObject2 ist abgeschnitten")
    flags = payload[0]
    p = 1
    depth = _le16(payload, p)
    p += 2
    character_id = matrix = color = name = clip_depth = None
    if flags & 0x02:
        character_id = _le16(payload, p)
        p += 2
    if flags & 0x04:
        matrix, p = _read_matrix(payload, p)
    if flags & 0x08:
        color, p = _read_color_transform(payload, p, True)
    if flags & 0x10:
        p += 2
    if flags & 0x20:
        name, p = _read_c_string(payload, p)
    if flags & 0x40:
        clip_depth = _le16(payload, p)
    return PlaceCommand(depth, bool(flags & 1), character_id, None, matrix, color, name, clip_depth)


def _parse_place_object3(payload):
    if len(payload) < 4:
        raise PakError("PlaceObject3 ist abgeschnitten")
    flags1 = payload[0]
    flags2 = payload[1]
    p = 2
    depth = _le16(payload, p)
    p += 2
    has_character = bool(flags1 & 0x02)
    class_name = None
    if flags2 & 0x08 or (flags2 & 0x10 and has_character):
        class_name, p = _read_c_string(payload, p)
    character_id = None
    if has_character:
        character_id = _le16(payload, p)
        p += 2
    matrix = color = name = clip_depth = None
    if flags1 & 0x04:
        matrix, p = _read_matrix(payload, p)
    if flags1 & 0x08:
        color, p = _read_color_transform(payload, p, True)
    if flags1 & 0x10:
        p += 2
    if flags1 & 0x20:
        name, p = _read_c_string(payload, p)
    if flags1 & 0x40:
        clip_depth = _le16(payload, p)
    return PlaceCommand(depth, bool(flags1 & 1), character_id, class_name, matrix, color, name, clip_depth)


def _merge_place(old, command):
    if old is None:
        old = DisplayObject(command.depth)
    return DisplayObject(
        command.depth,
        command.character_id if command.character_id is not None else old.character_id,
        command.class_name if command.class_name is not None else old.class_name,
        command.matrix if command.matrix is not None else old.matrix,
        command.color if command.color is not None else old.color,
        command.name if command.name is not None else old.name,
        command.clip_depth if command.clip_depth is not None else old.clip_depth,
        command.visible if command.visible is not None else old.visible,
    )


def build_display_list(tags, target_frame):
    display = {}
    frame = 1
    target_frame = max(1, target_frame)
    for code, payload in tags:
        try:
            if code == TAG_PLACE_OBJECT2:
                command = _parse_place_object2(payload)
                display[command.depth] = _merge_place(display.get(command.depth), command)
            elif code == TAG_PLACE_OBJECT3:
                command = _parse_place_object3(payload)
                display[command.depth] = _merge_place(display.get(command.depth), command)
            elif code == TAG_REMOVE_OBJECT2 and len(payload) >= 2:
                display.pop(_le16(payload, 0), None)
            elif code == TAG_REMOVE_OBJECT and len(payload) >= 4:
                display.pop(_le16(payload, 2), None)
            elif code == TAG_SHOW_FRAME:
                if frame >= target_frame:
                    return dict(display)
                frame += 1
            elif code == TAG_END:
                break
        except Exception:
            continue
    return dict(display)


@dataclass
class TextureLookup:
    image: object | None
    uuid_hex: str = ""
    source: str = ""
    error: str = ""


class TextureResolver:
    def __init__(self, parsed, require_store=None, preferred_library_uuid="", imports=None):
        self.parsed = parsed
        self.require_store = require_store
        self.preferred_library_uuid = preferred_library_uuid
        self.imports = list(imports or [])
        self.libraries = self._collect_libraries()
        self.name_index = {}
        for library in self.libraries:
            for name, uuid_hex in library.mappings.items():
                self.name_index.setdefault(name, []).append((library, uuid_hex))
        self.cache = {}

    def _collect_libraries(self):
        libraries = []
        seen = set()
        sources = [(self.parsed, Path(self.parsed.get("path", "PAK")).name)]
        if self.require_store is not None:
            for item in getattr(self.require_store, "required_paks", []):
                source_parsed = item.get("parsed")
                if source_parsed is not None:
                    sources.append((source_parsed, Path(item.get("path", "Require")).name))
        for source_parsed, source_label in sources:
            for entry in source_parsed.get("entries", []):
                if _normal_type(entry) != GFXL_TYPE:
                    continue
                key = (source_label, entry.get("uuid_hex", ""))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    libraries.append(parse_gfxl_asset(
                        get_entry_asset(source_parsed, entry), source_label, entry.get("uuid_hex", ""),
                    ))
                except Exception:
                    continue
        import_order = {name: index for index, name in enumerate(self.imports)}
        libraries.sort(key=lambda lib: (
            0 if lib.entry_uuid == self.preferred_library_uuid else 1,
            import_order.get(lib.name, import_order.get(Path(lib.name).name, 1000)),
            lib.name.lower(),
        ))
        return libraries

    def _resolve_asset(self, uuid_hex):
        entry = self.parsed.get("uuid_to_entry", {}).get(uuid_hex)
        if entry is not None:
            return get_entry_asset(self.parsed, entry), entry, Path(self.parsed.get("path", "PAK")).name
        if self.require_store is not None:
            try:
                asset, entry, source_kind = self.require_store.resolve_asset(self.parsed, uuid_hex)
                if asset is not None and entry is not None:
                    source = self.require_store.get_required_source(uuid_hex) if source_kind == "require" else self.parsed.get("path", "")
                    return asset, entry, Path(source or source_kind).name
            except Exception:
                pass
        return None, None, ""

    def get(self, name):
        if name in self.cache:
            return self.cache[name]
        candidates = self.name_index.get(name, [])
        if not candidates:
            short = name.rsplit(".", 1)[-1].rsplit("::", 1)[-1]
            candidates = self.name_index.get(short, [])
        if not candidates:
            result = TextureLookup(None, error=f"Keine GFXL-Zuordnung für {name}")
            self.cache[name] = result
            return result
        errors = []
        for library, uuid_hex in candidates:
            try:
                asset, entry, source = self._resolve_asset(uuid_hex)
                if asset is None:
                    errors.append(f"{library.name}: TXTR {uuid_hex} fehlt")
                    continue
                if parse_txtr_asset is None or decode_txtr_image is None or Image is None:
                    raise PakError("Pillow/TXTR-Decoder ist nicht verfügbar")
                info = parse_txtr_asset(asset)
                image, _ = decode_txtr_image(info, "Auto")
                result = TextureLookup(image.convert("RGBA"), uuid_hex, source or library.source, "")
                self.cache[name] = result
                return result
            except Exception as exc:
                errors.append(f"{library.name}: {exc}")
        result = TextureLookup(None, candidates[0][1], candidates[0][0].source, "; ".join(errors))
        self.cache[name] = result
        return result


@dataclass
class RenderStats:
    placements: int = 0
    textures_drawn: int = 0
    shapes_drawn: int = 0
    text_fields_drawn: int = 0
    missing: list = field(default_factory=list)
    recursion_skips: int = 0


class UIRenderer:
    def __init__(self, movie, resolver, show_bounds=False, show_placeholders=True):
        if Image is None or ImageDraw is None:
            raise PakError("Pillow wird für den UI Browser benötigt")
        self.movie = movie
        self.resolver = resolver
        self.show_bounds = show_bounds
        self.show_placeholders = show_placeholders
        self.stats = RenderStats()
        self._font = ImageFont.load_default() if ImageFont is not None else None

    def render(self, frame):
        background = self.movie.background
        if background[3] == 0:
            background = (28, 31, 38, 255)
        canvas = Image.new("RGBA", (self.movie.width, self.movie.height), background)
        root = build_display_list(self.movie.root_tags, min(max(1, frame), self.movie.frame_count))
        stage = Affine(1, 0, 0, 1, -self.movie.stage_bounds[0], -self.movie.stage_bounds[1])
        self._draw_display(canvas, root, stage, IDENTITY_COLOR, set(), 0)
        return canvas, self.stats

    def _draw_display(self, canvas, display, parent_matrix, parent_color, stack, level):
        if level > 64:
            self.stats.recursion_skips += 1
            return
        for depth in sorted(display):
            item = display[depth]
            if not item.visible:
                continue
            self.stats.placements += 1
            matrix = parent_matrix.then(item.matrix)
            color = parent_color.combine(item.color)
            if item.class_name:
                self._draw_external(canvas, item.class_name, matrix, color)
                continue
            if item.character_id is None:
                if self.show_placeholders:
                    self._draw_placeholder(canvas, matrix, item.name or f"depth {depth}", (120, 120, 120, 150))
                continue
            definition = self.movie.definitions.get(item.character_id)
            if isinstance(definition, SpriteDef):
                if item.character_id in stack:
                    self.stats.recursion_skips += 1
                    continue
                child = build_display_list(definition.tags, 1)
                self._draw_display(canvas, child, matrix, color, stack | {item.character_id}, level + 1)
            elif isinstance(definition, EditTextDef):
                self._draw_edit_text(canvas, definition, matrix, color)
            elif isinstance(definition, ShapeDef):
                self._draw_shape(canvas, definition, matrix)
            elif self.show_placeholders:
                self._draw_placeholder(canvas, matrix, item.name or f"char {item.character_id}", (100, 90, 130, 145))

    def _apply_color(self, image, color):
        if color == IDENTITY_COLOR:
            return image
        channels = image.convert("RGBA").split()
        mult = (color.r_mult, color.g_mult, color.b_mult, color.a_mult)
        add = (color.r_add, color.g_add, color.b_add, color.a_add)
        adjusted = []
        for channel, scale, bias in zip(channels, mult, add):
            adjusted.append(channel.point(lambda value, s=scale, b=bias: max(0, min(255, int(value * s + b)))))
        return Image.merge("RGBA", adjusted)

    @staticmethod
    def _point(matrix, x, y):
        return matrix.a * x + matrix.c * y + matrix.tx, matrix.b * x + matrix.d * y + matrix.ty

    def _draw_external(self, canvas, class_name, matrix, color):
        lookup = self.resolver.get(class_name)
        if lookup.image is None:
            if class_name not in self.stats.missing:
                self.stats.missing.append(class_name)
            if self.show_placeholders:
                self._draw_placeholder(canvas, matrix, class_name, (150, 55, 70, 180))
            return
        image = self._apply_color(lookup.image, color)
        inverse = matrix.inverse_pillow()
        if inverse is None:
            return
        corners = [
            self._point(matrix, 0, 0), self._point(matrix, image.width, 0),
            self._point(matrix, image.width, image.height), self._point(matrix, 0, image.height),
        ]
        left = max(0, int(math.floor(min(point[0] for point in corners))))
        top = max(0, int(math.floor(min(point[1] for point in corners))))
        right = min(canvas.width, int(math.ceil(max(point[0] for point in corners))))
        bottom = min(canvas.height, int(math.ceil(max(point[1] for point in corners))))
        if right <= left or bottom <= top:
            return
        ia, ib, ic, id_, ie, iff = inverse
        crop_inverse = (ia, ib, ia * left + ib * top + ic, id_, ie, id_ * left + ie * top + iff)
        resampling = getattr(getattr(Image, "Resampling", Image), "BILINEAR")
        transformed = image.transform((right - left, bottom - top), Image.AFFINE, crop_inverse, resample=resampling)
        canvas.alpha_composite(transformed, (left, top))
        self.stats.textures_drawn += 1
        if self.show_bounds:
            self._draw_transformed_box(canvas, (0, 0, image.width, image.height), matrix, class_name)

    def _draw_transformed_box(self, canvas, bounds, matrix, label=""):
        draw = ImageDraw.Draw(canvas, "RGBA")
        xmin, ymin, xmax, ymax = bounds
        points = [
            self._point(matrix, xmin, ymin), self._point(matrix, xmax, ymin),
            self._point(matrix, xmax, ymax), self._point(matrix, xmin, ymax),
        ]
        draw.line(points + [points[0]], fill=(70, 220, 255, 180), width=1)
        if label and self._font is not None:
            draw.text(points[0], label[:48], font=self._font, fill=(210, 245, 255, 220))

    def _draw_shape(self, canvas, definition, matrix):
        self.stats.shapes_drawn += 1
        if not (self.show_bounds or self.show_placeholders):
            return
        draw = ImageDraw.Draw(canvas, "RGBA")
        xmin, ymin, xmax, ymax = definition.bounds
        points = [
            self._point(matrix, xmin, ymin), self._point(matrix, xmax, ymin),
            self._point(matrix, xmax, ymax), self._point(matrix, xmin, ymax),
        ]
        if self.show_placeholders:
            draw.polygon(points, fill=(75, 85, 105, 80))
        if self.show_bounds:
            draw.line(points + [points[0]], fill=(255, 205, 80, 180), width=1)

    def _draw_edit_text(self, canvas, definition, matrix, color):
        self.stats.text_fields_drawn += 1
        xmin, ymin, xmax, ymax = definition.bounds
        points = [
            self._point(matrix, xmin, ymin), self._point(matrix, xmax, ymin),
            self._point(matrix, xmax, ymax), self._point(matrix, xmin, ymax),
        ]
        draw = ImageDraw.Draw(canvas, "RGBA")
        if definition.border or self.show_bounds:
            draw.line(points + [points[0]], fill=(150, 210, 255, 130), width=1)
        text = definition.initial_text or (f"[{definition.variable_name}]" if definition.variable_name else "[Text]")
        base = definition.color
        text_color = (
            max(0, min(255, int(base[0] * color.r_mult + color.r_add))),
            max(0, min(255, int(base[1] * color.g_mult + color.g_add))),
            max(0, min(255, int(base[2] * color.b_mult + color.b_add))),
            max(0, min(255, int(base[3] * color.a_mult + color.a_add))),
        )
        if self._font is not None:
            draw.text(points[0], text[:120], fill=text_color, font=self._font)

    def _draw_placeholder(self, canvas, matrix, label, fill):
        draw = ImageDraw.Draw(canvas, "RGBA")
        x, y = self._point(matrix, 0, 0)
        draw.rounded_rectangle((x, y, x + 150, y + 36), radius=4, fill=fill, outline=(230, 230, 230, 150), width=1)
        if self._font is not None:
            draw.text((x + 5, y + 5), label[:28], fill=(255, 255, 255, 230), font=self._font)


def find_preview_frame(movie):
    best_frame = 1
    best_score = -1
    for frame in range(1, movie.frame_count + 1):
        score = len(build_display_list(movie.root_tags, frame))
        if score >= best_score:
            best_score = score
            best_frame = frame
    return best_frame


@dataclass
class _GfxSource:
    parsed: dict
    entry: dict
    source_label: str


class UIBrowser(tk.Toplevel):
    def __init__(self, parent, parsed, entry=None, require_store=None):
        super().__init__(parent)
        if Image is None or ImageTk is None:
            raise PakError("Pillow wird für den UI Browser benötigt")
        self.parsed = parsed
        self.require_store = require_store
        self.title("UI Browser")
        self.geometry("1450x880")
        self.minsize(900, 600)
        self.transient(parent)
        self._sources = self._collect_sources()
        self._tree_data = {}
        self._container_cache = {}
        self._current_source = None
        self._current_container = None
        self._current_movie_record = None
        self._current_movie = None
        self._current_resolver = None
        self._stage_image = None
        self._display_image = None
        self._photo = None
        self._render_pending = False
        self._closed = False
        self.frame_var = tk.IntVar(value=1)
        self.frame_text_var = tk.StringVar(value="Frame 1 / 1")
        self.status_var = tk.StringVar(value="UI auswählen")
        self.show_bounds_var = tk.BooleanVar(value=False)
        self.show_placeholders_var = tk.BooleanVar(value=True)
        self.nearest_var = tk.BooleanVar(value=False)

        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="PNG speichern", command=self.save_png).pack(side="left")
        ttk.Checkbutton(toolbar, text="Bounds", variable=self.show_bounds_var, command=self.request_render).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(toolbar, text="Platzhalter", variable=self.show_placeholders_var, command=self.request_render).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(toolbar, text="Pixel-Skalierung", variable=self.nearest_var, command=self._draw_scaled).pack(side="left", padx=(10, 0))
        ttk.Label(toolbar, textvariable=self.status_var).pack(side="right")

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        left = ttk.Frame(main, width=290)
        ttk.Label(left, text="GFX und Filme").pack(anchor="w", pady=(0, 4))
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        main.add(left, weight=0)

        center = ttk.Frame(main)
        frame_row = ttk.Frame(center)
        frame_row.pack(fill="x", pady=(0, 4))
        ttk.Label(frame_row, textvariable=self.frame_text_var, width=18).pack(side="left")
        self.frame_scale = ttk.Scale(frame_row, from_=1, to=1, orient="horizontal", command=self._on_frame_scale)
        self.frame_scale.pack(side="left", fill="x", expand=True)
        ttk.Button(frame_row, text="◀", width=3, command=lambda: self._step_frame(-1)).pack(side="left", padx=(6, 0))
        ttk.Button(frame_row, text="▶", width=3, command=lambda: self._step_frame(1)).pack(side="left", padx=(4, 0))
        self.canvas = tk.Canvas(center, background="#11151b", highlightthickness=1, highlightbackground="#5b6572")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._draw_scaled)
        main.add(center, weight=1)

        right = ttk.Frame(main, width=310)
        ttk.Label(right, text="Analyse").pack(anchor="w", pady=(0, 4))
        self.info = tk.Text(right, width=42, wrap="word", state="disabled")
        self.info.pack(side="left", fill="both", expand=True)
        info_scroll = ttk.Scrollbar(right, orient="vertical", command=self.info.yview)
        info_scroll.pack(side="left", fill="y")
        self.info.configure(yscrollcommand=info_scroll.set)
        main.add(right, weight=0)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _event: self.close())
        self.bind("<Left>", lambda _event: self._step_frame(-1))
        self.bind("<Right>", lambda _event: self._step_frame(1))
        self._populate_tree(entry)

    def _collect_sources(self):
        result = []
        current_label = Path(self.parsed.get("path", "Aktuelles PAK")).name
        for entry in self.parsed.get("entries", []):
            if _normal_type(entry) == GFX_TYPE:
                result.append(_GfxSource(self.parsed, entry, current_label))
        if self.require_store is not None:
            for item in getattr(self.require_store, "required_paks", []):
                source_parsed = item.get("parsed")
                if source_parsed is None:
                    continue
                label = Path(item.get("path", "Require")).name
                for entry in source_parsed.get("entries", []):
                    if _normal_type(entry) == GFX_TYPE:
                        result.append(_GfxSource(source_parsed, entry, label))
        result.sort(key=lambda item: (item.source_label.lower(), _entry_name(item.entry).lower(), item.entry.get("index", 0)))
        return result

    def _container_for(self, source):
        key = (source.source_label, source.entry.get("uuid_hex", ""))
        container = self._container_cache.get(key)
        if container is None:
            container = parse_gfx_asset(get_entry_asset(source.parsed, source.entry))
            self._container_cache[key] = container
        return container

    def _populate_tree(self, initial_entry):
        groups = {}
        initial_iid = ""
        for source_index, source in enumerate(self._sources):
            group_iid = groups.get(source.source_label)
            if group_iid is None:
                group_iid = f"source_{len(groups)}"
                groups[source.source_label] = group_iid
                self.tree.insert("", "end", iid=group_iid, text=source.source_label, open=True)
            entry_iid = f"gfx_{source_index}"
            self.tree.insert(group_iid, "end", iid=entry_iid, text=_entry_name(source.entry), open=True)
            self._tree_data[entry_iid] = (source, None)
            try:
                container = self._container_for(source)
                for movie_index, movie in enumerate(container.movies):
                    movie_iid = f"gfx_{source_index}_movie_{movie_index}"
                    self.tree.insert(entry_iid, "end", iid=movie_iid, text=movie.name)
                    self._tree_data[movie_iid] = (source, movie_index)
                    if initial_entry is not None and source.entry.get("uuid_hex") == initial_entry.get("uuid_hex") and not initial_iid:
                        initial_iid = movie_iid
            except Exception as exc:
                self.tree.insert(entry_iid, "end", text=f"Fehler: {exc}")
        if not initial_iid:
            initial_iid = next((iid for iid, value in self._tree_data.items() if value[1] is not None), "")
        if initial_iid:
            self.tree.selection_set(initial_iid)
            self.tree.focus(initial_iid)
            self.tree.see(initial_iid)
            self.after_idle(self._on_tree_select)
        elif not self._sources:
            self._set_info("Keine GFX-Einträge im aktuellen oder requireten PAK gefunden.")

    def _on_tree_select(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        data = self._tree_data.get(selection[0])
        if data is None or data[1] is None:
            return
        source, movie_index = data
        try:
            container = self._container_for(source)
            record = container.movies[movie_index]
            movie = parse_swf_movie(record.data)
            resolver = TextureResolver(self.parsed, self.require_store, container.library_uuid, movie.imports)
            self._current_source = source
            self._current_container = container
            self._current_movie_record = record
            self._current_movie = movie
            self._current_resolver = resolver
            preview_frame = find_preview_frame(movie)
            self.frame_scale.configure(from_=1, to=max(1, movie.frame_count))
            self.frame_scale.set(preview_frame)
            self.frame_var.set(preview_frame)
            self._update_frame_text()
            self.request_render()
        except Exception as exc:
            self._current_movie = None
            self._stage_image = None
            self.canvas.delete("all")
            self.status_var.set("UI konnte nicht geladen werden")
            self._set_info(str(exc))

    def _on_frame_scale(self, value):
        try:
            frame = int(round(float(value)))
        except Exception:
            frame = 1
        if frame != self.frame_var.get():
            self.frame_var.set(frame)
            self._update_frame_text()
            self.request_render()

    def _step_frame(self, delta):
        if self._current_movie is None:
            return
        frame = max(1, min(self._current_movie.frame_count, self.frame_var.get() + delta))
        self.frame_var.set(frame)
        self.frame_scale.set(frame)
        self._update_frame_text()
        self.request_render()

    def _update_frame_text(self):
        total = self._current_movie.frame_count if self._current_movie is not None else 1
        frame = max(1, min(total, self.frame_var.get()))
        label = ""
        if self._current_movie is not None:
            labels = [name for name, number in self._current_movie.labels.items() if number == frame]
            if labels:
                label = f" | {labels[0]}"
        self.frame_text_var.set(f"Frame {frame} / {total}{label}")

    def request_render(self, _event=None):
        if self._closed or self._render_pending:
            return
        self._render_pending = True
        self.after_idle(self._render)

    def _render(self):
        self._render_pending = False
        if self._closed or self._current_movie is None or self._current_resolver is None:
            return
        try:
            renderer = UIRenderer(
                self._current_movie, self._current_resolver,
                self.show_bounds_var.get(), self.show_placeholders_var.get(),
            )
            self._stage_image, stats = renderer.render(self.frame_var.get())
            self.status_var.set(
                f"{self._current_movie.width}×{self._current_movie.height} | "
                f"{stats.textures_drawn} TXTR | {len(stats.missing)} fehlend"
            )
            self._set_info(self._format_info(stats))
            self._draw_scaled()
        except Exception as exc:
            self.status_var.set("Renderfehler")
            self._set_info(str(exc))

    @staticmethod
    def _fit_size(source_width, source_height, target_width, target_height):
        if source_width <= 0 or source_height <= 0:
            return 1, 1
        scale = min(target_width / float(source_width), target_height / float(source_height))
        return max(1, int(round(source_width * scale))), max(1, int(round(source_height * scale)))

    def _draw_scaled(self, _event=None):
        self.canvas.delete("all")
        if self._stage_image is None:
            return
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        margin = 18
        draw_width, draw_height = self._fit_size(
            self._stage_image.width, self._stage_image.height,
            max(1, canvas_width - margin * 2), max(1, canvas_height - margin * 2),
        )
        resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST" if self.nearest_var.get() else "LANCZOS")
        self._display_image = self._stage_image.resize((draw_width, draw_height), resampling)
        self._photo = ImageTk.PhotoImage(self._display_image)
        x = (canvas_width - draw_width) // 2
        y = (canvas_height - draw_height) // 2
        self.canvas.create_rectangle(x - 1, y - 1, x + draw_width + 1, y + draw_height + 1, outline="#8090a0")
        self.canvas.create_image(x, y, anchor="nw", image=self._photo)

    def _format_info(self, stats):
        movie = self._current_movie
        record = self._current_movie_record
        source = self._current_source
        resolver = self._current_resolver
        if movie is None or record is None or source is None or resolver is None:
            return ""
        aspect = movie.width / float(movie.height) if movie.height else 0.0
        lines = [
            f"PAK: {source.source_label}", f"GFX: {_entry_name(source.entry)}", f"Film: {record.name}", "",
            f"Stage: {movie.width} × {movie.height}", f"Seitenverhältnis: {aspect:.5f}:1",
            f"FPS: {movie.frame_rate:g}", f"Frames: {movie.frame_count}", f"SWF-Version: {movie.version}",
            f"Definitionen: {len(movie.definitions)}", "", f"Placements: {stats.placements}",
            f"TXTR gezeichnet: {stats.textures_drawn}", f"Shapes: {stats.shapes_drawn}",
            f"Textfelder: {stats.text_fields_drawn}", f"GFXL-Bibliotheken: {len(resolver.libraries)}",
        ]
        if movie.imports:
            lines.extend(["", "Imports:"])
            lines.extend(f"- {name}" for name in movie.imports)
        if movie.labels:
            lines.extend(["", "Frame-Labels:"])
            lines.extend(f"- {name}: {frame}" for name, frame in sorted(movie.labels.items(), key=lambda item: item[1]))
        if stats.missing:
            lines.extend(["", f"Fehlende Symbole ({len(stats.missing)}):"])
            lines.extend(f"- {name}" for name in stats.missing[:100])
            if len(stats.missing) > 100:
                lines.append(f"... {len(stats.missing) - 100} weitere")
        lines.extend(["", "Hinweis:", "Statische SWF-Display-List; ActionScript wird noch nicht ausgeführt."])
        return "\n".join(lines)

    def _set_info(self, text):
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", text)
        self.info.configure(state="disabled")

    def save_png(self):
        if self._stage_image is None or self._current_movie_record is None:
            return
        safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in self._current_movie_record.name)
        path = filedialog.asksaveasfilename(
            parent=self, title="UI-Frame als PNG speichern", defaultextension=".png",
            initialfile=f"{safe}_frame_{self.frame_var.get():03d}.png",
            filetypes=[("PNG-Dateien", "*.png"), ("Alle Dateien", "*.*")],
        )
        if path:
            self._stage_image.save(path, "PNG")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.destroy()


def open_ui_browser(parent, parsed, entry=None, require_store=None):
    return UIBrowser(parent, parsed, entry, require_store)
