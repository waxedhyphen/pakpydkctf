"""Safe, generic same-length AVM2 bytecode patching for Scaleform GFX movies.

The module deliberately does not assemble arbitrary ActionScript. It locates DoABC method
bodies, validates expected bytes, applies equal-length replacements, rebuilds the containing
SWF/GFX movie and can hand the rebuilt GFX asset to pak_core.rebuild_pak.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import zlib


class AVM2PatchError(Exception):
    pass


@dataclass(frozen=True)
class MethodCodeRange:
    method_index: int
    code_offset: int
    code_size: int


@dataclass(frozen=True)
class DoABCLocation:
    name: str
    source: str
    tag_payload_offset: int
    tag_payload_size: int
    abc_offset: int
    abc_size: int
    methods: tuple[MethodCodeRange, ...]


@dataclass(frozen=True)
class BytePatch:
    module_name: str
    source: str
    method_index: int
    code_offset: int
    expected: bytes
    replacement: bytes
    note: str = ""

    def __post_init__(self):
        if self.method_index < 0 or self.code_offset < 0:
            raise AVM2PatchError("Methodenindex und Code-Offset dürfen nicht negativ sein")
        if not self.expected:
            raise AVM2PatchError("Eine erwartete Bytefolge ist erforderlich")
        if len(self.expected) != len(self.replacement):
            raise AVM2PatchError("Nur gleich lange Bytecode-Ersetzungen sind zulässig")

    def to_json(self):
        return {
            "module_name": self.module_name,
            "source": self.source,
            "method_index": self.method_index,
            "code_offset": self.code_offset,
            "expected": self.expected.hex(" ").upper(),
            "replacement": self.replacement.hex(" ").upper(),
            "note": self.note,
        }

    @classmethod
    def from_json(cls, value):
        if not isinstance(value, dict):
            raise AVM2PatchError("Patch-Eintrag muss ein JSON-Objekt sein")
        return cls(
            str(value.get("module_name", "")),
            str(value.get("source", "root")),
            int(value.get("method_index", -1)),
            parse_hex_bytes(value.get("code_offset", 0), allow_integer=True),
            parse_hex_bytes(value.get("expected", "")),
            parse_hex_bytes(value.get("replacement", "")),
            str(value.get("note", "")),
        )


@dataclass(frozen=True)
class PatchResult:
    movie_data: bytes
    applied: tuple[dict, ...]
    signature: str


_HEX_TOKEN = re.compile(r"^[0-9a-fA-F]{1,2}$")


def parse_hex_bytes(value, allow_integer=False):
    if allow_integer and isinstance(value, int):
        return value
    text = str(value or "").strip()
    if allow_integer:
        try:
            return int(text, 0)
        except Exception:
            try:
                return int(text, 16)
            except Exception as exc:
                raise AVM2PatchError(f"Ungültiger Offset: {value}") from exc
    if not text:
        return b""
    text = text.replace("0x", "").replace("0X", "")
    tokens = [item for item in re.split(r"[\s,;:_-]+", text) if item]
    if len(tokens) == 1 and len(tokens[0]) > 2:
        compact = tokens[0]
        if len(compact) % 2:
            raise AVM2PatchError("Hex-Bytefolge muss eine gerade Anzahl Stellen haben")
        tokens = [compact[index:index + 2] for index in range(0, len(compact), 2)]
    if not tokens or any(not _HEX_TOKEN.fullmatch(item) for item in tokens):
        raise AVM2PatchError(f"Ungültige Hex-Bytefolge: {value}")
    return bytes(int(item, 16) for item in tokens)


def dump_patch_manifest(patches):
    return json.dumps({"schema": 1, "patches": [patch.to_json() for patch in patches]}, ensure_ascii=False, indent=2)


def load_patch_manifest(text):
    try:
        value = json.loads(text)
    except Exception as exc:
        raise AVM2PatchError(f"Patch-Profil ist kein gültiges JSON: {exc}") from exc
    if not isinstance(value, dict) or int(value.get("schema", 0)) != 1:
        raise AVM2PatchError("Nicht unterstütztes Patch-Profil")
    return tuple(BytePatch.from_json(item) for item in value.get("patches", ()))


class _Reader:
    def __init__(self, data, offset=0):
        self.data = bytes(data)
        self.offset = int(offset)

    def require(self, count):
        if count < 0 or self.offset + count > len(self.data):
            raise AVM2PatchError("ABC-Daten sind abgeschnitten")

    def u8(self):
        self.require(1)
        value = self.data[self.offset]
        self.offset += 1
        return value

    def u16(self):
        self.require(2)
        value = int.from_bytes(self.data[self.offset:self.offset + 2], "little")
        self.offset += 2
        return value

    def bytes(self, count):
        self.require(count)
        value = self.data[self.offset:self.offset + count]
        self.offset += count
        return value

    def u32(self):
        value = 0
        shift = 0
        for _ in range(5):
            byte = self.u8()
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value & 0xFFFFFFFF
            shift += 7
        return value & 0xFFFFFFFF

    def u30(self):
        value = self.u32()
        if value > 0x3FFFFFFF:
            raise AVM2PatchError(f"Ungültiger U30-Wert {value}")
        return value


def _count(reader, label):
    value = reader.u30()
    if value > 1_000_000:
        raise AVM2PatchError(f"ABC-{label}-Pool ist unrealistisch groß: {value}")
    return value


def _skip_traits(reader):
    for _ in range(_count(reader, "Trait")):
        reader.u30()
        kind_attr = reader.u8()
        kind = kind_attr & 0x0F
        attributes = kind_attr >> 4
        if kind in (0, 6):
            reader.u30(); reader.u30()
            value_index = reader.u30()
            if value_index:
                reader.u8()
        elif kind in (1, 2, 3):
            reader.u30(); reader.u30()
        elif kind in (4, 5):
            reader.u30(); reader.u30()
        else:
            raise AVM2PatchError(f"Unbekannter ABC-Trait-Typ {kind}")
        if attributes & 0x04:
            for _ in range(_count(reader, "Trait-Metadaten")):
                reader.u30()


def locate_method_code_ranges(abc_data):
    reader = _Reader(abc_data)
    reader.u16(); reader.u16()

    for label in ("Int", "UInt"):
        count = _count(reader, label)
        for _ in range(max(0, count - 1)):
            reader.u32()
    count = _count(reader, "Double")
    for _ in range(max(0, count - 1)):
        reader.bytes(8)
    count = _count(reader, "String")
    for _ in range(max(0, count - 1)):
        reader.bytes(reader.u30())
    count = _count(reader, "Namespace")
    for _ in range(max(0, count - 1)):
        reader.u8(); reader.u30()
    count = _count(reader, "Namespace-Set")
    for _ in range(max(0, count - 1)):
        for _ in range(_count(reader, "Namespace-Set-Eintrag")):
            reader.u30()
    count = _count(reader, "Multiname")
    for _ in range(max(0, count - 1)):
        kind = reader.u8()
        if kind in (0x07, 0x0D):
            reader.u30(); reader.u30()
        elif kind in (0x0F, 0x10):
            reader.u30()
        elif kind in (0x11, 0x12):
            pass
        elif kind in (0x09, 0x0E):
            reader.u30(); reader.u30()
        elif kind in (0x1B, 0x1C):
            reader.u30()
        elif kind == 0x1D:
            reader.u30()
            for _ in range(_count(reader, "TypeName-Parameter")):
                reader.u30()
        else:
            raise AVM2PatchError(f"Unbekannter Multiname-Typ 0x{kind:02X}")

    for _ in range(_count(reader, "Methoden")):
        parameter_count = _count(reader, "Methodenparameter")
        reader.u30()
        for _ in range(parameter_count):
            reader.u30()
        reader.u30()
        flags = reader.u8()
        if flags & 0x08:
            for _ in range(_count(reader, "optionale Parameter")):
                reader.u30(); reader.u8()
        if flags & 0x80:
            for _ in range(parameter_count):
                reader.u30()

    for _ in range(_count(reader, "Metadaten")):
        reader.u30()
        item_count = _count(reader, "Metadaten-Einträge")
        for _ in range(item_count * 2):
            reader.u30()

    class_count = _count(reader, "Klassen")
    for _ in range(class_count):
        reader.u30(); reader.u30()
        flags = reader.u8()
        if flags & 0x08:
            reader.u30()
        for _ in range(_count(reader, "Interfaces")):
            reader.u30()
        reader.u30()
        _skip_traits(reader)
    for _ in range(class_count):
        reader.u30()
        _skip_traits(reader)
    for _ in range(_count(reader, "Scripts")):
        reader.u30()
        _skip_traits(reader)

    ranges = []
    for _ in range(_count(reader, "Methodenbodies")):
        method_index = reader.u30()
        reader.u30(); reader.u30(); reader.u30(); reader.u30()
        code_size = reader.u30()
        code_offset = reader.offset
        reader.bytes(code_size)
        for _ in range(_count(reader, "Exceptions")):
            reader.u30(); reader.u30(); reader.u30(); reader.u30(); reader.u30()
        _skip_traits(reader)
        ranges.append(MethodCodeRange(method_index, code_offset, code_size))
    return tuple(ranges)


def _swf_header_end(data):
    if len(data) < 12:
        raise AVM2PatchError("SWF/GFX-Film ist zu klein")
    nbits = data[8] >> 3
    rect_bytes = (5 + nbits * 4 + 7) // 8
    offset = 8 + rect_bytes + 4
    if offset > len(data):
        raise AVM2PatchError("SWF-Header ist abgeschnitten")
    return offset


def _inflate_swf(raw):
    raw = bytes(raw)
    if len(raw) < 8:
        raise AVM2PatchError("SWF/GFX-Film ist zu klein")
    signature = raw[:3]
    if signature == b"CWS":
        try:
            body = zlib.decompress(raw[8:])
        except Exception as exc:
            raise AVM2PatchError(f"CWS konnte nicht entpackt werden: {exc}") from exc
        data = bytearray(b"FWS" + raw[3:8] + body)
    elif signature in (b"FWS", b"GFX"):
        data = bytearray(raw)
    else:
        raise AVM2PatchError(f"Unbekannte SWF-Signatur {signature!r}")
    expected = int.from_bytes(data[4:8], "little")
    if expected > len(data):
        raise AVM2PatchError("SWF-Dateilänge ist größer als die vorhandenen Daten")
    return data[:expected], signature


def _deflate_swf(data, signature):
    value = bytearray(data)
    value[4:8] = len(value).to_bytes(4, "little")
    if signature == b"CWS":
        return b"CWS" + bytes(value[3:8]) + zlib.compress(bytes(value[8:]), 9)
    value[:3] = signature
    return bytes(value)


def _tag_records(data, start, end, source="root"):
    result = []
    p = start
    while p + 2 <= end:
        header_offset = p
        record = int.from_bytes(data[p:p + 2], "little")
        p += 2
        code = record >> 6
        size = record & 0x3F
        if size == 0x3F:
            if p + 4 > end:
                raise AVM2PatchError("SWF-Langtag ist abgeschnitten")
            size = int.from_bytes(data[p:p + 4], "little")
            p += 4
        payload_offset = p
        payload_end = p + size
        if payload_end > end:
            raise AVM2PatchError(f"SWF-Tag {code} läuft über das Dateiende")
        result.append((code, header_offset, payload_offset, payload_end, source))
        if code == 39 and size >= 4:
            character_id = int.from_bytes(data[payload_offset:payload_offset + 2], "little")
            result.extend(_tag_records(data, payload_offset + 4, payload_end, f"sprite {character_id}"))
        p = payload_end
        if code == 0:
            break
    return result


def locate_doabc_modules(movie_data):
    data, _signature = _inflate_swf(movie_data)
    tags = _tag_records(data, _swf_header_end(data), len(data))
    modules = []
    for code, _header, payload_offset, payload_end, source in tags:
        if code != 82:
            continue
        payload = bytes(data[payload_offset:payload_end])
        if len(payload) < 5:
            raise AVM2PatchError("DoABC-Tag ist abgeschnitten")
        end = payload.find(b"\x00", 4)
        if end < 0:
            raise AVM2PatchError("DoABC-Modulname ist nicht nullterminiert")
        name = payload[4:end].decode("utf-8", "replace") or "<unbenannt>"
        abc_rel = end + 1
        abc_data = payload[abc_rel:]
        modules.append(DoABCLocation(
            name, source, payload_offset, len(payload),
            payload_offset + abc_rel, len(abc_data), locate_method_code_ranges(abc_data),
        ))
    return tuple(modules)


def _find_module(locations, patch):
    exact = [item for item in locations if item.name == patch.module_name and item.source == patch.source]
    if len(exact) == 1:
        return exact[0]
    if not exact:
        by_name = [item for item in locations if item.name == patch.module_name]
        if len(by_name) == 1:
            return by_name[0]
        if not by_name:
            raise AVM2PatchError(f"DoABC-Modul nicht gefunden: {patch.module_name} [{patch.source}]")
    raise AVM2PatchError(f"DoABC-Modul ist nicht eindeutig: {patch.module_name} [{patch.source}]")


def apply_movie_patches(movie_data, patches):
    patches = tuple(patches or ())
    data, signature = _inflate_swf(movie_data)
    locations = locate_doabc_modules(bytes(data))
    applied = []
    occupied = set()
    for patch in patches:
        module = _find_module(locations, patch)
        method = next((item for item in module.methods if item.method_index == patch.method_index), None)
        if method is None:
            raise AVM2PatchError(
                f"Methode {patch.method_index} hat in {module.name} [{module.source}] keinen Body"
            )
        end = patch.code_offset + len(patch.expected)
        if end > method.code_size:
            raise AVM2PatchError(
                f"Patch überschreitet Methode {patch.method_index}: 0x{patch.code_offset:X}+{len(patch.expected)}"
            )
        absolute = module.abc_offset + method.code_offset + patch.code_offset
        span = range(absolute, absolute + len(patch.expected))
        if any(index in occupied for index in span):
            raise AVM2PatchError("Mehrere Patches überlappen sich")
        actual = bytes(data[absolute:absolute + len(patch.expected)])
        if actual != patch.expected:
            raise AVM2PatchError(
                f"Originalbytes passen nicht bei {module.name} Methode {patch.method_index} "
                f"+0x{patch.code_offset:X}: erwartet {patch.expected.hex(' ').upper()}, "
                f"gefunden {actual.hex(' ').upper()}"
            )
        data[absolute:absolute + len(patch.replacement)] = patch.replacement
        occupied.update(span)
        applied.append({
            **patch.to_json(),
            "absolute_uncompressed_swf_offset": absolute,
        })
    result = _deflate_swf(data, signature)
    # Structural validation after patching.
    locate_doabc_modules(result)
    return PatchResult(result, tuple(applied), signature.decode("ascii", "replace"))


def _be64(data, offset):
    return int.from_bytes(data[offset:offset + 8], "big")


def _w64(data, offset, value):
    data[offset:offset + 8] = int(value).to_bytes(8, "big")


def rebuild_gfx_asset(original_asset, movie_index, new_movie_data):
    asset = bytes(original_asset)
    if len(asset) < 56 or asset[:4] != b"RFRM" or asset[20:24].strip() != b"GFX":
        raise AVM2PatchError("Ausgewähltes Asset ist kein gültiges GFX-RFRM")
    if asset[32:36].strip() != b"GFX":
        raise AVM2PatchError("GFX-Asset enthält keinen GFX-Datenchunk")
    payload_size = _be64(asset, 36)
    payload_offset = 56
    payload_end = payload_offset + payload_size
    if payload_end > len(asset):
        raise AVM2PatchError("GFX-Datenchunk läuft über das Dateiende")
    payload = asset[payload_offset:payload_end]
    if len(payload) < 36:
        raise AVM2PatchError("GFX-Payload ist zu klein")
    count_offset = 32
    count = int.from_bytes(payload[count_offset:count_offset + 4], "big")
    if not 0 <= int(movie_index) < count:
        raise AVM2PatchError(f"Ungültiger Filmindex {movie_index}; GFX enthält {count} Filme")
    table_offset = count_offset + 4
    table_end = table_offset + count * 64
    if table_end > len(payload):
        raise AVM2PatchError("GFX-Filmtabelle ist abgeschnitten")

    records = []
    for index in range(count):
        rec = table_offset + index * 64
        rel = _be64(payload, rec)
        size = _be64(payload, rec + 8)
        start = count_offset + rel
        end = start + size
        if start < table_end or end > len(payload):
            raise AVM2PatchError(f"GFX-Film {index} hat ungültige Grenzen")
        records.append((rec, start, end, payload[start:end]))

    gaps = []
    previous = table_end
    for _rec, start, end, _blob in records:
        gaps.append(payload[previous:start])
        previous = end
    suffix = payload[previous:]

    rebuilt = bytearray(payload[:table_end])
    offsets = []
    for index, ((_rec, _start, _end, blob), gap) in enumerate(zip(records, gaps)):
        rebuilt += gap
        start = len(rebuilt)
        use_blob = bytes(new_movie_data) if index == int(movie_index) else blob
        rebuilt += use_blob
        offsets.append((start, len(use_blob)))
    rebuilt += suffix

    for index, (start, size) in enumerate(offsets):
        rec = table_offset + index * 64
        _w64(rebuilt, rec, start - count_offset)
        _w64(rebuilt, rec + 8, size)

    result = bytearray(asset[:payload_offset])
    result += rebuilt
    result += asset[payload_end:]
    _w64(result, 36, len(rebuilt))
    _w64(result, 4, len(result) - 32)
    return bytes(result)


def patch_gfx_asset(original_asset, movie_index, patches):
    # Import lazily so the pure locator can be tested without loading Tk/Pillow.
    from ui_browser import parse_gfx_asset

    container = parse_gfx_asset(original_asset)
    if not 0 <= int(movie_index) < len(container.movies):
        raise AVM2PatchError(f"Ungültiger Filmindex {movie_index}")
    result = apply_movie_patches(container.movies[int(movie_index)].data, patches)
    return rebuild_gfx_asset(original_asset, movie_index, result.movie_data), result
