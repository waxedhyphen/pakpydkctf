"""Three-way PAK and IPS merger for PAKPY.

The PAK merger uses an untouched original PAK as the common ancestor. It compares
resources by UUID, accepts every resource type, and keeps each one byte-for-byte
unless one or both mods changed it. Conflicting GFX resources are merged per movie
and, where necessary, recursively per SWF tag. Other resources use a generic binary
three-way merge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

from pak_core import PakError, get_entry_asset, parse_pak, rebuild_pak


class PakMergeError(PakError):
    pass


@dataclass(frozen=True)
class MergeConflict:
    scope: str
    reason: str


@dataclass(frozen=True)
class MergeItem:
    uuid_hex: str
    asset_type: str
    name: str
    status: str
    detail: str
    original_size: int
    a_size: int
    b_size: int
    merged_size: int | None


@dataclass
class PakMergePlan:
    original_path: str
    pak_a_path: str
    pak_b_path: str
    original_parsed: dict
    replacements: dict[int, dict] = field(default_factory=dict)
    items: list[MergeItem] = field(default_factory=list)
    conflicts: list[MergeConflict] = field(default_factory=list)

    @property
    def can_build(self) -> bool:
        return not self.conflicts

    def write(self, out_path: str | Path) -> str:
        if self.conflicts:
            details = "\n".join(f"- {item.scope}: {item.reason}" for item in self.conflicts)
            raise PakMergeError(f"Der PAK-Merge enthält ungelöste Konflikte:\n{details}")
        return rebuild_pak(self.original_parsed, self.replacements, out_path)

    def summary_lines(self) -> list[str]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.status] = counts.get(item.status, 0) + 1
        lines = [
            f"Original: {self.original_path}",
            f"PAK A:    {self.pak_a_path}",
            f"PAK B:    {self.pak_b_path}",
            f"Einträge: {len(self.items)}",
            f"Konflikte: {len(self.conflicts)}",
            "",
        ]
        for status, count in sorted(counts.items()):
            lines.append(f"{status}: {count}")
        if self.conflicts:
            lines.extend(("", "Konflikte:"))
            lines.extend(f"- {item.scope}: {item.reason}" for item in self.conflicts)
        return lines


@dataclass(frozen=True)
class IpsMergeResult:
    data: bytes | None
    conflicts: tuple[MergeConflict, ...]
    source_a_records: int
    source_b_records: int
    merged_bytes: int

    @property
    def can_build(self) -> bool:
        return self.data is not None and not self.conflicts


@dataclass(frozen=True)
class _Edit:
    start: int
    end: int
    replacement: bytes
    source: str


@dataclass(frozen=True)
class _SwfTag:
    code: int
    payload: bytes


_DEFINITION_CODES = {
    2, 6, 7, 10, 11, 14, 20, 21, 22, 32, 33, 34, 35, 36, 37, 39, 46, 48,
    75, 83, 84, 87, 88, 90, 91,
}
_MAX_SEQUENCE_MATCHER_SIZE = 512 * 1024


def _entry_map(parsed: dict, label: str) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for entry in parsed["entries"]:
        uuid_hex = entry["uuid_hex"]
        if uuid_hex in result:
            raise PakMergeError(f"{label} enthält die UUID {uuid_hex} mehrfach")
        result[uuid_hex] = entry
    return result


def _validate_same_directory(original: dict, variant: dict, label: str) -> None:
    original_map = _entry_map(original, "Original")
    variant_map = _entry_map(variant, label)
    missing = sorted(set(original_map) - set(variant_map))
    added = sorted(set(variant_map) - set(original_map))
    if missing or added:
        parts = []
        if missing:
            parts.append(f"{len(missing)} Original-UUIDs fehlen")
        if added:
            parts.append(f"{len(added)} zusätzliche UUIDs")
        raise PakMergeError(
            f"{label} hat eine andere PAK-Verzeichnisstruktur ({', '.join(parts)}). "
            "Der Merger kann geänderte Ressourcen zusammenführen, aber keine "
            "Top-Level-Assets hinzufügen oder entfernen."
        )
    for uuid_hex, original_entry in original_map.items():
        variant_entry = variant_map[uuid_hex]
        if variant_entry["type"] != original_entry["type"]:
            raise PakMergeError(
                f"{label}: UUID {uuid_hex} hat Typ {variant_entry['type']} "
                f"statt {original_entry['type']}"
            )


def _bytewise_equal_length_merge(base: bytes, a: bytes, b: bytes, scope: str) -> bytes:
    out = bytearray(len(base))
    conflict_start = None
    conflicts: list[tuple[int, int]] = []
    for index, original in enumerate(base):
        av = a[index]
        bv = b[index]
        if av == bv:
            out[index] = av
            conflict = False
        elif av == original:
            out[index] = bv
            conflict = False
        elif bv == original:
            out[index] = av
            conflict = False
        else:
            out[index] = original
            conflict = True
        if conflict and conflict_start is None:
            conflict_start = index
        elif not conflict and conflict_start is not None:
            conflicts.append((conflict_start, index))
            conflict_start = None
    if conflict_start is not None:
        conflicts.append((conflict_start, len(base)))
    if conflicts:
        preview = ", ".join(
            f"0x{start:X}-0x{end - 1:X}" for start, end in conflicts[:8]
        )
        if len(conflicts) > 8:
            preview += f", ... {len(conflicts) - 8} weitere"
        raise PakMergeError(
            f"{scope}: beide Mods schreiben unterschiedliche Bytes in {preview}"
        )
    return bytes(out)


def _single_span_edit(base: bytes, variant: bytes, source: str) -> _Edit | None:
    if base == variant:
        return None
    prefix = 0
    limit = min(len(base), len(variant))
    while prefix < limit and base[prefix] == variant[prefix]:
        prefix += 1
    suffix = 0
    max_suffix = min(len(base) - prefix, len(variant) - prefix)
    while (
        suffix < max_suffix
        and base[len(base) - 1 - suffix] == variant[len(variant) - 1 - suffix]
    ):
        suffix += 1
    end = len(base) - suffix
    replacement_end = len(variant) - suffix
    return _Edit(prefix, end, variant[prefix:replacement_end], source)


def _sequence_edits(base: bytes, variant: bytes, source: str) -> list[_Edit]:
    matcher = SequenceMatcher(None, base, variant, autojunk=False)
    edits = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            edits.append(_Edit(i1, i2, variant[j1:j2], source))
    return edits


def _edits_conflict(left: _Edit, right: _Edit) -> bool:
    if left.start == left.end and right.start == right.end:
        return left.start == right.start
    if left.start == left.end:
        return right.start < left.start < right.end
    if right.start == right.end:
        return left.start < right.start < left.end
    return max(left.start, right.start) < min(left.end, right.end)


def _merge_edit_lists(
    base: bytes,
    edits_a: Iterable[_Edit],
    edits_b: Iterable[_Edit],
    scope: str,
) -> bytes:
    merged: list[_Edit] = list(edits_a)
    for edit in edits_b:
        duplicate = next(
            (
                current
                for current in merged
                if current.start == edit.start
                and current.end == edit.end
                and current.replacement == edit.replacement
            ),
            None,
        )
        if duplicate is not None:
            continue
        conflict = next(
            (current for current in merged if _edits_conflict(current, edit)),
            None,
        )
        if conflict is not None:
            raise PakMergeError(
                f"{scope}: überlappende Binäränderungen von {conflict.source} "
                f"und {edit.source} bei 0x{max(conflict.start, edit.start):X}"
            )
        merged.append(edit)
    merged.sort(key=lambda item: (item.start, item.end, item.source))
    out = bytearray()
    cursor = 0
    for edit in merged:
        if edit.start < cursor:
            raise PakMergeError(f"{scope}: interne Edit-Überlappung")
        out.extend(base[cursor:edit.start])
        out.extend(edit.replacement)
        cursor = edit.end
    out.extend(base[cursor:])
    return bytes(out)


def merge_binary(base: bytes, a: bytes, b: bytes, scope: str) -> bytes:
    base = bytes(base)
    a = bytes(a)
    b = bytes(b)
    if a == b:
        return a
    if a == base:
        return b
    if b == base:
        return a
    if len(base) == len(a) == len(b):
        return _bytewise_equal_length_merge(base, a, b, scope)
    if max(len(base), len(a), len(b)) <= _MAX_SEQUENCE_MATCHER_SIZE:
        return _merge_edit_lists(
            base,
            _sequence_edits(base, a, "PAK A"),
            _sequence_edits(base, b, "PAK B"),
            scope,
        )
    edit_a = _single_span_edit(base, a, "PAK A")
    edit_b = _single_span_edit(base, b, "PAK B")
    return _merge_edit_lists(
        base,
        [edit_a] if edit_a else [],
        [edit_b] if edit_b else [],
        scope,
    )


def _decode_c_string(data: bytes, offset: int) -> tuple[str, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        return "", len(data)
    return data[offset:end].decode("utf-8", "replace"), end + 1


def _matrix_end(data: bytes, offset: int) -> int:
    bit = offset * 8

    def read(count: int) -> int:
        nonlocal bit
        if bit + count > len(data) * 8:
            raise PakMergeError("SWF-MATRIX ist abgeschnitten")
        value = 0
        for _ in range(count):
            value = (
                (value << 1)
                | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
            )
            bit += 1
        return value

    if read(1):
        count = read(5)
        read(count * 2)
    if read(1):
        count = read(5)
        read(count * 2)
    count = read(5)
    read(count * 2)
    return (bit + 7) // 8


def _cxform_end(data: bytes, offset: int) -> int:
    bit = offset * 8

    def read(count: int) -> int:
        nonlocal bit
        if bit + count > len(data) * 8:
            raise PakMergeError("SWF-CXFORM ist abgeschnitten")
        value = 0
        for _ in range(count):
            value = (
                (value << 1)
                | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
            )
            bit += 1
        return value

    has_add = read(1)
    has_mult = read(1)
    count = read(4)
    if has_mult:
        read(count * 4)
    if has_add:
        read(count * 4)
    return (bit + 7) // 8


def _placement_identity(tag: _SwfTag) -> tuple | None:
    data = tag.payload
    if tag.code == 26:
        if len(data) < 3:
            return None
        flags = data[0]
        flags2 = 0
        depth = int.from_bytes(data[1:3], "little")
        offset = 3
    elif tag.code == 70:
        if len(data) < 4:
            return None
        flags = data[0]
        flags2 = data[1]
        depth = int.from_bytes(data[2:4], "little")
        offset = 4
        if flags2 & 0x08 or ((flags2 & 0x10) and (flags & 0x02)):
            _class_name, offset = _decode_c_string(data, offset)
    else:
        return None
    character_id = None
    name = ""
    if flags & 0x02:
        if offset + 2 > len(data):
            return ("place", depth, "", None)
        character_id = int.from_bytes(data[offset:offset + 2], "little")
        offset += 2
    if flags & 0x04:
        offset = _matrix_end(data, offset)
    if flags & 0x08:
        offset = _cxform_end(data, offset)
    if flags & 0x10:
        offset += 2
    if flags & 0x20:
        name, offset = _decode_c_string(data, offset)
    return ("place", depth, name, character_id)


def _tag_base_key(tag: _SwfTag) -> tuple:
    payload = tag.payload
    if tag.code == 39 and len(payload) >= 2:
        return ("sprite", int.from_bytes(payload[:2], "little"))
    if tag.code == 82:
        name, _ = (
            _decode_c_string(payload, 4)
            if len(payload) >= 5
            else ("", 0)
        )
        return ("doabc", name)
    if tag.code in (26, 70):
        identity = _placement_identity(tag)
        if identity is not None:
            return identity
    if tag.code == 43:
        name, _ = _decode_c_string(payload, 0)
        return ("frame-label", name)
    if tag.code in _DEFINITION_CODES and len(payload) >= 2:
        return (
            "definition",
            tag.code,
            int.from_bytes(payload[:2], "little"),
        )
    if tag.code == 76:
        return ("symbol-class",)
    return ("tag", tag.code)


def _tag_keys(tags: list[_SwfTag]) -> list[tuple]:
    counts: dict[tuple, int] = {}
    result = []
    for tag in tags:
        base = _tag_base_key(tag)
        occurrence = counts.get(base, 0)
        counts[base] = occurrence + 1
        result.append((base, occurrence))
    return result


def _parse_tag_stream(data: bytes) -> tuple[list[_SwfTag], bytes]:
    tags = []
    offset = 0
    while offset + 2 <= len(data):
        word = int.from_bytes(data[offset:offset + 2], "little")
        offset += 2
        code = word >> 6
        size = word & 0x3F
        if size == 0x3F:
            if offset + 4 > len(data):
                raise PakMergeError("SWF-Langtag ist abgeschnitten")
            size = int.from_bytes(data[offset:offset + 4], "little")
            offset += 4
        end = offset + size
        if end > len(data):
            raise PakMergeError(
                f"SWF-Tag {code} läuft über das Dateiende"
            )
        tags.append(_SwfTag(code, data[offset:end]))
        offset = end
        if code == 0:
            break
    return tags, data[offset:]


def _encode_tag(tag: _SwfTag) -> bytes:
    payload = bytes(tag.payload)
    if len(payload) < 63:
        return (
            ((tag.code << 6) | len(payload)).to_bytes(2, "little")
            + payload
        )
    return (
        ((tag.code << 6) | 63).to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
        + payload
    )


def _align_tags(
    base: list[_SwfTag],
    variant: list[_SwfTag],
) -> tuple[dict[int, _SwfTag | None], dict[int, list[_SwfTag]]]:
    base_keys = _tag_keys(base)
    variant_keys = _tag_keys(variant)
    matcher = SequenceMatcher(None, base_keys, variant_keys, autojunk=False)
    mapping: dict[int, _SwfTag | None] = {
        index: None for index in range(len(base))
    }
    insertions: dict[int, list[_SwfTag]] = {
        index: [] for index in range(len(base) + 1)
    }
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for offset in range(i2 - i1):
                mapping[i1 + offset] = variant[j1 + offset]
        elif op == "insert":
            insertions[i1].extend(variant[j1:j2])
        elif op == "delete":
            continue
        else:
            base_block = list(range(i1, i2))
            variant_block = list(range(j1, j2))
            used_variant: set[int] = set()
            for base_index in base_block:
                base_key = _tag_base_key(base[base_index])
                candidates = [
                    variant_index
                    for variant_index in variant_block
                    if variant_index not in used_variant
                    and _tag_base_key(variant[variant_index]) == base_key
                ]
                if len(candidates) == 1:
                    variant_index = candidates[0]
                    mapping[base_index] = variant[variant_index]
                    used_variant.add(variant_index)
            remaining_base = [
                index for index in base_block if mapping[index] is None
            ]
            remaining_variant = [
                index
                for index in variant_block
                if index not in used_variant
            ]
            if len(remaining_base) == len(remaining_variant):
                for base_index, variant_index in zip(
                    remaining_base,
                    remaining_variant,
                ):
                    if base[base_index].code == variant[variant_index].code:
                        mapping[base_index] = variant[variant_index]
                        used_variant.add(variant_index)
            insertions[i1].extend(
                variant[index]
                for index in remaining_variant
                if index not in used_variant
            )
    return mapping, insertions


def _tag_collision_key(tag: _SwfTag) -> tuple | None:
    if tag.code in (26, 70):
        identity = _placement_identity(tag)
        if identity is not None:
            return ("display-depth", identity[1])
    if tag.code in _DEFINITION_CODES and len(tag.payload) >= 2:
        return (
            "character-id",
            int.from_bytes(tag.payload[:2], "little"),
        )
    if tag.code == 82:
        name, _ = (
            _decode_c_string(tag.payload, 4)
            if len(tag.payload) >= 5
            else ("", 0)
        )
        return ("doabc", name)
    return None


def _merge_insertions(
    a: list[_SwfTag],
    b: list[_SwfTag],
    scope: str,
) -> list[_SwfTag]:
    if not a:
        return list(b)
    if not b:
        return list(a)
    if a == b:
        return list(a)
    result = list(a)
    by_key = {_tag_base_key(tag): tag for tag in result}
    collisions = {
        key: tag
        for tag in result
        if (key := _tag_collision_key(tag)) is not None
    }
    for tag in b:
        key = _tag_base_key(tag)
        existing = by_key.get(key)
        collision_key = _tag_collision_key(tag)
        collision = (
            collisions.get(collision_key)
            if collision_key is not None
            else None
        )
        if existing is not None:
            if existing != tag:
                raise PakMergeError(
                    f"{scope}: beide Mods fügen unterschiedliche SWF-Tags "
                    f"mit Schlüssel {key!r} ein"
                )
            continue
        if collision is not None and collision != tag:
            raise PakMergeError(
                f"{scope}: SWF-Einfügungen kollidieren bei "
                f"{collision_key!r}; Character-IDs und Display-Tiefen "
                "müssen eindeutig sein"
            )
        result.append(tag)
        by_key[key] = tag
        if collision_key is not None:
            collisions[collision_key] = tag
    return result


def _merge_scalar(base, a, b, scope: str):
    if a == b:
        return a
    if a == base:
        return b
    if b == base:
        return a
    raise PakMergeError(
        f"{scope}: beide Mods ändern denselben Wert unterschiedlich"
    )


def _merge_tag(
    base: _SwfTag,
    a: _SwfTag,
    b: _SwfTag,
    scope: str,
) -> _SwfTag:
    if a == b:
        return a
    if a == base:
        return b
    if b == base:
        return a
    if not (base.code == a.code == b.code):
        raise PakMergeError(
            f"{scope}: SWF-Tag-Typ wurde auf beiden Seiten "
            "unterschiedlich ersetzt"
        )
    if (
        base.code == 39
        and min(len(base.payload), len(a.payload), len(b.payload)) >= 4
    ):
        sprite_id = int.from_bytes(base.payload[:2], "little")
        if (
            int.from_bytes(a.payload[:2], "little") != sprite_id
            or int.from_bytes(b.payload[:2], "little") != sprite_id
        ):
            raise PakMergeError(f"{scope}: DefineSprite-ID wurde geändert")
        frame_count = _merge_scalar(
            int.from_bytes(base.payload[2:4], "little"),
            int.from_bytes(a.payload[2:4], "little"),
            int.from_bytes(b.payload[2:4], "little"),
            f"{scope}/Sprite {sprite_id}/FrameCount",
        )
        merged_stream = _merge_tag_stream(
            base.payload[4:],
            a.payload[4:],
            b.payload[4:],
            f"{scope}/Sprite {sprite_id}",
        )
        return _SwfTag(
            39,
            sprite_id.to_bytes(2, "little")
            + int(frame_count).to_bytes(2, "little")
            + merged_stream,
        )
    payload = merge_binary(
        base.payload,
        a.payload,
        b.payload,
        f"{scope}/Tag {base.code}",
    )
    return _SwfTag(base.code, payload)


def _merge_tag_stream(
    base_data: bytes,
    a_data: bytes,
    b_data: bytes,
    scope: str,
) -> bytes:
    if a_data == b_data:
        return a_data
    if a_data == base_data:
        return b_data
    if b_data == base_data:
        return a_data
    base_tags, base_tail = _parse_tag_stream(base_data)
    a_tags, a_tail = _parse_tag_stream(a_data)
    b_tags, b_tail = _parse_tag_stream(b_data)
    map_a, insert_a = _align_tags(base_tags, a_tags)
    map_b, insert_b = _align_tags(base_tags, b_tags)
    merged: list[_SwfTag] = []
    for index, base_tag in enumerate(base_tags):
        merged.extend(
            _merge_insertions(
                insert_a[index],
                insert_b[index],
                f"{scope}/vor Tag {index}",
            )
        )
        tag_a = map_a[index]
        tag_b = map_b[index]
        if tag_a is None and tag_b is None:
            continue
        if tag_a is None:
            if tag_b == base_tag:
                continue
            raise PakMergeError(
                f"{scope}/Tag {index}: PAK A löscht den Tag, "
                "PAK B verändert ihn"
            )
        if tag_b is None:
            if tag_a == base_tag:
                continue
            raise PakMergeError(
                f"{scope}/Tag {index}: PAK B löscht den Tag, "
                "PAK A verändert ihn"
            )
        merged.append(
            _merge_tag(
                base_tag,
                tag_a,
                tag_b,
                f"{scope}/Tag {index}",
            )
        )
    merged.extend(
        _merge_insertions(
            insert_a[len(base_tags)],
            insert_b[len(base_tags)],
            f"{scope}/Dateiende",
        )
    )
    tail = merge_binary(base_tail, a_tail, b_tail, f"{scope}/Tail")
    return b"".join(_encode_tag(tag) for tag in merged) + tail


def _merge_swf_movie(
    base_movie: bytes,
    a_movie: bytes,
    b_movie: bytes,
    scope: str,
) -> bytes:
    from ui_browser_avm2_repack import (
        _deflate_swf,
        _inflate_swf,
        _swf_header_end,
    )

    base_data, base_signature = _inflate_swf(base_movie)
    a_data, a_signature = _inflate_swf(a_movie)
    b_data, b_signature = _inflate_swf(b_movie)
    signature = _merge_scalar(
        base_signature,
        a_signature,
        b_signature,
        f"{scope}/Kompression",
    )
    base_start = _swf_header_end(base_data)
    a_start = _swf_header_end(a_data)
    b_start = _swf_header_end(b_data)
    if base_start != a_start or base_start != b_start:
        raise PakMergeError(f"{scope}: SWF-Headerlänge wurde verändert")
    base_header = bytearray(base_data[:base_start])
    a_header = bytes(a_data[:a_start])
    b_header = bytes(b_data[:b_start])
    base_header[4:8] = b"\x00\x00\x00\x00"
    a_header = a_header[:4] + b"\x00\x00\x00\x00" + a_header[8:]
    b_header = b_header[:4] + b"\x00\x00\x00\x00" + b_header[8:]
    merged_header = merge_binary(
        bytes(base_header),
        a_header,
        b_header,
        f"{scope}/Header",
    )
    merged_stream = _merge_tag_stream(
        bytes(base_data[base_start:]),
        bytes(a_data[a_start:]),
        bytes(b_data[b_start:]),
        scope,
    )
    return _deflate_swf(merged_header + merged_stream, signature)


def _gfx_movie_signature(container) -> tuple[tuple[str, int], ...]:
    return tuple(
        (movie.name, index)
        for index, movie in enumerate(container.movies)
    )


def _merge_gfx_asset(
    base_asset: bytes,
    a_asset: bytes,
    b_asset: bytes,
    scope: str,
) -> tuple[bytes, str]:
    from ui_browser import parse_gfx_asset
    from ui_browser_avm2_repack import rebuild_gfx_asset

    base = parse_gfx_asset(base_asset)
    a = parse_gfx_asset(a_asset)
    b = parse_gfx_asset(b_asset)
    if (
        _gfx_movie_signature(base) != _gfx_movie_signature(a)
        or _gfx_movie_signature(base) != _gfx_movie_signature(b)
    ):
        raise PakMergeError(
            f"{scope}: GFX-Filmtabelle wurde strukturell verändert"
        )
    normalized_a = a_asset
    normalized_b = b_asset
    for index, base_movie in enumerate(base.movies):
        normalized_a = rebuild_gfx_asset(
            normalized_a,
            index,
            base_movie.data,
        )
        normalized_b = rebuild_gfx_asset(
            normalized_b,
            index,
            base_movie.data,
        )
    merged_asset = merge_binary(
        base_asset,
        normalized_a,
        normalized_b,
        f"{scope}/GFX-Container",
    )
    merged_movies = 0
    for index, (base_movie, a_movie, b_movie) in enumerate(
        zip(base.movies, a.movies, b.movies)
    ):
        movie_scope = f"{scope}/{base_movie.name or index}"
        if a_movie.data == b_movie.data:
            merged = a_movie.data
        elif a_movie.data == base_movie.data:
            merged = b_movie.data
        elif b_movie.data == base_movie.data:
            merged = a_movie.data
        else:
            merged = _merge_swf_movie(
                base_movie.data,
                a_movie.data,
                b_movie.data,
                movie_scope,
            )
            merged_movies += 1
        if merged != base_movie.data:
            merged_asset = rebuild_gfx_asset(
                merged_asset,
                index,
                merged,
            )
    return (
        merged_asset,
        "GFX/SWF-Strukturmerge "
        f"({merged_movies} Filmkonflikte automatisch kombiniert)",
    )


def _choose_conflict(
    policy: str,
    a: bytes,
    b: bytes,
    scope: str,
    reason: str,
) -> tuple[bytes | None, str, MergeConflict | None]:
    if policy == "a":
        return a, "forced-a", None
    if policy == "b":
        return b, "forced-b", None
    return None, "conflict", MergeConflict(scope, reason)


def plan_pak_merge(
    original_path: str | Path,
    pak_a_path: str | Path,
    pak_b_path: str | Path,
    conflict_policy: str = "error",
) -> PakMergePlan:
    if conflict_policy not in {"error", "a", "b"}:
        raise PakMergeError(
            f"Unbekannte Konfliktstrategie: {conflict_policy}"
        )
    original = parse_pak(original_path)
    pak_a = parse_pak(pak_a_path)
    pak_b = parse_pak(pak_b_path)
    _validate_same_directory(original, pak_a, "PAK A")
    _validate_same_directory(original, pak_b, "PAK B")
    map_a = _entry_map(pak_a, "PAK A")
    map_b = _entry_map(pak_b, "PAK B")
    plan = PakMergePlan(
        str(original_path),
        str(pak_a_path),
        str(pak_b_path),
        original,
    )
    for original_entry in original["entries_by_offset"]:
        uuid_hex = original_entry["uuid_hex"]
        entry_a = map_a[uuid_hex]
        entry_b = map_b[uuid_hex]
        base_asset = get_entry_asset(original, original_entry)
        asset_a = get_entry_asset(pak_a, entry_a)
        asset_b = get_entry_asset(pak_b, entry_b)
        asset_type = original_entry["type"].strip()
        name = (
            original_entry.get("display_name")
            or original_entry.get("name")
            or uuid_hex
        )
        scope = f"{asset_type} {name} [{uuid_hex}]"
        merged: bytes | None
        detail: str
        conflict: MergeConflict | None = None
        if asset_a == base_asset and asset_b == base_asset:
            merged, status, detail = (
                base_asset,
                "unchanged",
                "In beiden Mods unverändert",
            )
        elif asset_a == asset_b:
            merged, status, detail = (
                asset_a,
                "same-change",
                "Beide Mods enthalten exakt dieselbe Änderung",
            )
        elif asset_a == base_asset:
            merged, status, detail = (
                asset_b,
                "from-b",
                "Nur PAK B geändert",
            )
        elif asset_b == base_asset:
            merged, status, detail = (
                asset_a,
                "from-a",
                "Nur PAK A geändert",
            )
        else:
            try:
                if asset_type == "GFX":
                    merged, detail = _merge_gfx_asset(
                        base_asset,
                        asset_a,
                        asset_b,
                        scope,
                    )
                    status = "auto-merged"
                else:
                    merged = merge_binary(
                        base_asset,
                        asset_a,
                        asset_b,
                        scope,
                    )
                    detail = "Generischer Binär-Dreiwegemerge"
                    status = "auto-merged"
            except Exception as exc:
                merged, status, conflict = _choose_conflict(
                    conflict_policy,
                    asset_a,
                    asset_b,
                    scope,
                    str(exc),
                )
                detail = (
                    f"Konflikt zugunsten PAK "
                    f"{'A' if conflict_policy == 'a' else 'B'} "
                    f"entschieden: {exc}"
                    if merged is not None
                    else str(exc)
                )
        if conflict is not None:
            plan.conflicts.append(conflict)
        if merged is not None and merged != base_asset:
            plan.replacements[original_entry["index"]] = {
                "asset_bytes": merged,
            }
        plan.items.append(
            MergeItem(
                uuid_hex=uuid_hex,
                asset_type=asset_type,
                name=name,
                status=status,
                detail=detail,
                original_size=len(base_asset),
                a_size=len(asset_a),
                b_size=len(asset_b),
                merged_size=(len(merged) if merged is not None else None),
            )
        )
    return plan


def _parse_ips(data: bytes, label: str) -> tuple[dict[int, int], int]:
    data = bytes(data)
    if data.startswith(b"IPS32"):
        offset_size = 4
        footer = b"EEOF"
        cursor = 5
    elif data.startswith(b"PATCH"):
        offset_size = 3
        footer = b"EOF"
        cursor = 5
    else:
        raise PakMergeError(f"{label} ist weder IPS noch IPS32")
    writes: dict[int, int] = {}
    records = 0
    while True:
        if data[cursor:cursor + len(footer)] == footer:
            cursor += len(footer)
            break
        if cursor + offset_size + 2 > len(data):
            raise PakMergeError(f"{label}: IPS-Datei ist abgeschnitten")
        offset = int.from_bytes(
            data[cursor:cursor + offset_size],
            "big",
        )
        cursor += offset_size
        size = int.from_bytes(data[cursor:cursor + 2], "big")
        cursor += 2
        if size == 0:
            if cursor + 3 > len(data):
                raise PakMergeError(
                    f"{label}: IPS-RLE-Eintrag ist abgeschnitten"
                )
            run_size = int.from_bytes(data[cursor:cursor + 2], "big")
            value = data[cursor + 2]
            cursor += 3
            payload = bytes([value]) * run_size
        else:
            if cursor + size > len(data):
                raise PakMergeError(
                    f"{label}: IPS-Eintrag ist abgeschnitten"
                )
            payload = data[cursor:cursor + size]
            cursor += size
        for index, value in enumerate(payload):
            absolute = offset + index
            previous = writes.get(absolute)
            if previous is not None and previous != value:
                raise PakMergeError(
                    f"{label}: widersprüchliche interne "
                    f"IPS-Schreibvorgänge bei 0x{absolute:X}"
                )
            writes[absolute] = value
        records += 1
    if cursor != len(data):
        remainder = data[cursor:]
        if not (offset_size == 3 and len(remainder) == 3):
            raise PakMergeError(
                f"{label}: unerwartete {len(remainder)} Restbytes "
                "hinter dem Footer"
            )
    return writes, records


def _build_ips32(writes: dict[int, int]) -> bytes:
    output = bytearray(b"IPS32")
    offsets = sorted(writes)
    index = 0
    while index < len(offsets):
        start = offsets[index]
        values = bytearray([writes[start]])
        index += 1
        while (
            index < len(offsets)
            and offsets[index] == start + len(values)
            and len(values) < 0xFFFF
        ):
            values.append(writes[offsets[index]])
            index += 1
        if start > 0xFFFFFFFF:
            raise PakMergeError(
                f"IPS32-Offset 0x{start:X} überschreitet 32 Bit"
            )
        output.extend(start.to_bytes(4, "big"))
        output.extend(len(values).to_bytes(2, "big"))
        output.extend(values)
    output.extend(b"EEOF")
    return bytes(output)


def merge_ips(
    ips_a_path: str | Path | None,
    ips_b_path: str | Path | None,
    conflict_policy: str = "error",
) -> IpsMergeResult:
    if conflict_policy not in {"error", "a", "b"}:
        raise PakMergeError(
            f"Unbekannte Konfliktstrategie: {conflict_policy}"
        )
    path_a = Path(ips_a_path) if ips_a_path else None
    path_b = Path(ips_b_path) if ips_b_path else None
    writes_a, records_a = (
        _parse_ips(path_a.read_bytes(), "IPS A")
        if path_a
        else ({}, 0)
    )
    writes_b, records_b = (
        _parse_ips(path_b.read_bytes(), "IPS B")
        if path_b
        else ({}, 0)
    )
    if not writes_a and not writes_b:
        return IpsMergeResult(None, (), records_a, records_b, 0)
    merged = dict(writes_a)
    conflicts = []
    for offset, value in writes_b.items():
        previous = merged.get(offset)
        if previous is None or previous == value:
            merged[offset] = value
            continue
        if conflict_policy == "a":
            continue
        if conflict_policy == "b":
            merged[offset] = value
            continue
        conflicts.append(
            MergeConflict(
                f"IPS32 0x{offset:X}",
                f"IPS A schreibt {previous:02X}, "
                f"IPS B schreibt {value:02X}",
            )
        )
    if conflicts:
        return IpsMergeResult(
            None,
            tuple(conflicts),
            records_a,
            records_b,
            len(merged),
        )
    return IpsMergeResult(
        _build_ips32(merged),
        (),
        records_a,
        records_b,
        len(merged),
    )


def write_ips_result(
    result: IpsMergeResult,
    out_path: str | Path,
) -> str:
    if not result.can_build:
        if result.conflicts:
            details = "\n".join(
                f"- {item.scope}: {item.reason}"
                for item in result.conflicts
            )
            raise PakMergeError(
                f"Der IPS-Merge enthält ungelöste Konflikte:\n{details}"
            )
        raise PakMergeError("Es wurden keine IPS-Dateien ausgewählt")
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(result.data or b"")
    return str(target)
