"""Nintendo Switch NSO0 parsing and address translation.

This module is deliberately independent from the PAK reader. It provides the
foundation for the ExeFS Lab: validated NSO metadata, segment extraction and
safe translation between file offsets, module-relative virtual addresses and
runtime addresses.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Iterable, Optional


NSO_MAGIC = b"NSO0"
NSO_HEADER_SIZE = 0x100
DEFAULT_RUNTIME_BASE = 0x7100000000


class NsoError(ValueError):
    """Raised when an NSO file is malformed or an address cannot be parsed."""


@dataclass(frozen=True)
class NsoSegment:
    name: str
    file_offset: Optional[int]
    memory_offset: int
    memory_size: int
    stored_size: int
    compressed: bool = False
    hash_enabled: bool = False
    expected_hash: bytes = b""

    @property
    def file_end(self) -> Optional[int]:
        if self.file_offset is None:
            return None
        return self.file_offset + self.stored_size

    @property
    def memory_end(self) -> int:
        return self.memory_offset + self.memory_size

    def contains_file_offset(self, value: int) -> bool:
        return (
            self.file_offset is not None
            and self.stored_size > 0
            and self.file_offset <= value < self.file_offset + self.stored_size
        )

    def contains_memory_offset(self, value: int) -> bool:
        return self.memory_size > 0 and self.memory_offset <= value < self.memory_end


@dataclass(frozen=True)
class AddressTranslation:
    input_kind: str
    input_value: int
    segment: Optional[str]
    file_offset: Optional[int]
    memory_offset: Optional[int]
    runtime_address: Optional[int]
    exact_file_mapping: bool
    note: str = ""

    def format_lines(self) -> list[str]:
        def fmt(value: Optional[int]) -> str:
            return "—" if value is None else f"0x{value:X}"

        return [
            f"Segment: {self.segment or 'außerhalb der gemappten Segmente'}",
            f"Dateioffset: {fmt(self.file_offset)}",
            f"NSO-VA: {fmt(self.memory_offset)}",
            f"Runtime-Adresse: {fmt(self.runtime_address)}",
            f"Exakte Dateizuordnung: {'ja' if self.exact_file_mapping else 'nein'}",
            *([f"Hinweis: {self.note}"] if self.note else []),
        ]


@dataclass(frozen=True)
class NsoImage:
    path: Optional[Path]
    raw: bytes
    version: int
    flags: int
    module_name: str
    build_id: bytes
    bss_size: int
    segments: tuple[NsoSegment, ...]
    file_sha256: str

    @classmethod
    def from_file(cls, path: str | Path) -> "NsoImage":
        source = Path(path)
        try:
            raw = source.read_bytes()
        except OSError as exc:
            raise NsoError(f"NSO-Datei konnte nicht gelesen werden: {exc}") from exc
        return cls.from_bytes(raw, path=source)

    @classmethod
    def from_bytes(cls, raw: bytes, path: str | Path | None = None) -> "NsoImage":
        raw = bytes(raw)
        if len(raw) < NSO_HEADER_SIZE:
            raise NsoError(
                f"Datei ist zu klein für einen NSO0-Header: {len(raw)} < {NSO_HEADER_SIZE} Bytes"
            )
        if raw[:4] != NSO_MAGIC:
            shown = raw[:4].hex(" ").upper()
            raise NsoError(f"Ungültige NSO-Signatur: {shown}; erwartet 4E 53 4F 30")

        version, _reserved, flags = struct.unpack_from("<III", raw, 0x04)
        module_name_offset = _u32(raw, 0x1C)
        module_name_size = _u32(raw, 0x2C)
        bss_size = _u32(raw, 0x3C)
        build_id = raw[0x40:0x60]
        stored_sizes = (_u32(raw, 0x60), _u32(raw, 0x64), _u32(raw, 0x68))
        segment_specs = (
            ("text", 0x10, 0),
            ("rodata", 0x20, 1),
            ("data", 0x30, 2),
        )
        hash_offsets = (0xA0, 0xC0, 0xE0)

        segments: list[NsoSegment] = []
        for (name, header_offset, flag_index), stored_size, hash_offset in zip(
            segment_specs, stored_sizes, hash_offsets
        ):
            file_offset, memory_offset, memory_size = struct.unpack_from(
                "<III", raw, header_offset
            )
            compressed = bool(flags & (1 << (flag_index * 4)))
            hash_enabled = bool(flags & (1 << (12 + flag_index * 4)))
            if memory_size and stored_size == 0:
                raise NsoError(f"Segment {name} hat Größe, aber keine gespeicherte Länge")
            if stored_size and file_offset < NSO_HEADER_SIZE:
                raise NsoError(
                    f"Segment {name} beginnt im NSO-Header: Dateioffset 0x{file_offset:X}"
                )
            if file_offset + stored_size > len(raw):
                raise NsoError(
                    f"Segment {name} überschreitet die Datei: "
                    f"0x{file_offset:X}+0x{stored_size:X} > 0x{len(raw):X}"
                )
            if not compressed and stored_size != memory_size:
                raise NsoError(
                    f"Unkomprimiertes Segment {name} hat unterschiedliche Datei-/Speichergröße: "
                    f"0x{stored_size:X} != 0x{memory_size:X}"
                )
            segments.append(
                NsoSegment(
                    name=name,
                    file_offset=file_offset,
                    memory_offset=memory_offset,
                    memory_size=memory_size,
                    stored_size=stored_size,
                    compressed=compressed,
                    hash_enabled=hash_enabled,
                    expected_hash=raw[hash_offset:hash_offset + 0x20],
                )
            )

        data_segment = segments[2]
        if bss_size:
            segments.append(
                NsoSegment(
                    name="bss",
                    file_offset=None,
                    memory_offset=data_segment.memory_end,
                    memory_size=bss_size,
                    stored_size=0,
                )
            )

        _validate_memory_ranges(segments)
        _validate_file_ranges(segments)
        module_name = _read_module_name(raw, module_name_offset, module_name_size)
        return cls(
            path=Path(path) if path is not None else None,
            raw=raw,
            version=version,
            flags=flags,
            module_name=module_name,
            build_id=build_id,
            bss_size=bss_size,
            segments=tuple(segments),
            file_sha256=hashlib.sha256(raw).hexdigest(),
        )

    @property
    def build_id_hex(self) -> str:
        return self.build_id.hex().upper()

    def segment(self, name: str) -> NsoSegment:
        key = str(name).strip().lower()
        aliases = {
            "ro": "rodata",
            ".rodata": "rodata",
            ".text": "text",
            ".data": "data",
        }
        key = aliases.get(key, key)
        for segment in self.segments:
            if segment.name == key:
                return segment
        raise NsoError(f"Unbekanntes NSO-Segment: {name}")

    def read_segment(self, name: str, verify_hash: bool = False) -> bytes:
        segment = self.segment(name)
        if segment.file_offset is None:
            return bytes(segment.memory_size)
        stored = self.raw[segment.file_offset:segment.file_offset + segment.stored_size]
        if segment.compressed:
            result = _lz4_decompress_block(stored, segment.memory_size)
        else:
            result = stored
        if len(result) != segment.memory_size:
            raise NsoError(
                f"Segment {segment.name} dekomprimierte auf {len(result)} statt "
                f"{segment.memory_size} Bytes"
            )
        if verify_hash and segment.hash_enabled:
            actual = hashlib.sha256(result).digest()
            if actual != segment.expected_hash:
                raise NsoError(
                    f"SHA-256-Prüfung für Segment {segment.name} fehlgeschlagen: "
                    f"{actual.hex().upper()} != {segment.expected_hash.hex().upper()}"
                )
        return result

    def verify_enabled_hashes(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for segment in self.segments:
            if segment.file_offset is None or not segment.hash_enabled:
                continue
            actual = hashlib.sha256(self.read_segment(segment.name)).digest()
            result[segment.name] = actual == segment.expected_hash
        return result

    def translate_file_offset(
        self, file_offset: int, runtime_base: int = DEFAULT_RUNTIME_BASE
    ) -> AddressTranslation:
        value = _require_non_negative(file_offset, "Dateioffset")
        for segment in self.segments:
            if not segment.contains_file_offset(value):
                continue
            if segment.compressed:
                return AddressTranslation(
                    input_kind="file",
                    input_value=value,
                    segment=segment.name,
                    file_offset=value,
                    memory_offset=None,
                    runtime_address=None,
                    exact_file_mapping=False,
                    note=(
                        "Das Segment ist komprimiert. Ein Byte innerhalb des komprimierten "
                        "Datenstroms besitzt keine eindeutige NSO-VA."
                    ),
                )
            delta = value - int(segment.file_offset)
            memory_offset = segment.memory_offset + delta
            return AddressTranslation(
                input_kind="file",
                input_value=value,
                segment=segment.name,
                file_offset=value,
                memory_offset=memory_offset,
                runtime_address=runtime_base + memory_offset,
                exact_file_mapping=True,
            )
        return AddressTranslation(
            input_kind="file",
            input_value=value,
            segment=None,
            file_offset=value,
            memory_offset=None,
            runtime_address=None,
            exact_file_mapping=False,
            note="Der Dateioffset liegt in keinem gespeicherten NSO-Segment.",
        )

    def translate_memory_offset(
        self, memory_offset: int, runtime_base: int = DEFAULT_RUNTIME_BASE
    ) -> AddressTranslation:
        value = _require_non_negative(memory_offset, "NSO-VA")
        for segment in self.segments:
            if not segment.contains_memory_offset(value):
                continue
            delta = value - segment.memory_offset
            if segment.file_offset is None:
                return AddressTranslation(
                    input_kind="memory",
                    input_value=value,
                    segment=segment.name,
                    file_offset=None,
                    memory_offset=value,
                    runtime_address=runtime_base + value,
                    exact_file_mapping=False,
                    note="BSS ist nur im Speicher vorhanden und besitzt keine Dateibytes.",
                )
            if segment.compressed:
                return AddressTranslation(
                    input_kind="memory",
                    input_value=value,
                    segment=segment.name,
                    file_offset=None,
                    memory_offset=value,
                    runtime_address=runtime_base + value,
                    exact_file_mapping=False,
                    note=(
                        "Das Segment ist komprimiert. Die NSO-VA ist exakt, aber es gibt "
                        "keinen direkten Dateioffset für dieses dekomprimierte Byte."
                    ),
                )
            file_offset = segment.file_offset + delta
            return AddressTranslation(
                input_kind="memory",
                input_value=value,
                segment=segment.name,
                file_offset=file_offset,
                memory_offset=value,
                runtime_address=runtime_base + value,
                exact_file_mapping=True,
            )
        return AddressTranslation(
            input_kind="memory",
            input_value=value,
            segment=None,
            file_offset=None,
            memory_offset=value,
            runtime_address=runtime_base + value,
            exact_file_mapping=False,
            note="Die NSO-VA liegt außerhalb von text, rodata, data und bss.",
        )

    def translate_runtime_address(
        self, runtime_address: int, runtime_base: int = DEFAULT_RUNTIME_BASE
    ) -> AddressTranslation:
        address = _require_non_negative(runtime_address, "Runtime-Adresse")
        base = _require_non_negative(runtime_base, "Runtime-Basis")
        if address < base:
            raise NsoError(
                f"Runtime-Adresse 0x{address:X} liegt unter der Basis 0x{base:X}"
            )
        result = self.translate_memory_offset(address - base, runtime_base=base)
        return AddressTranslation(
            input_kind="runtime",
            input_value=address,
            segment=result.segment,
            file_offset=result.file_offset,
            memory_offset=result.memory_offset,
            runtime_address=address,
            exact_file_mapping=result.exact_file_mapping,
            note=result.note,
        )

    def summary_lines(self) -> list[str]:
        source = str(self.path) if self.path is not None else "<Speicher>"
        return [
            f"Datei: {source}",
            f"Dateigröße: {len(self.raw)} Bytes (0x{len(self.raw):X})",
            f"SHA-256: {self.file_sha256}",
            f"NSO-Version: {self.version}",
            f"Flags: 0x{self.flags:08X}",
            f"Modulname: {self.module_name or '—'}",
            f"Build ID: {self.build_id_hex}",
            f"BSS-Größe: {self.bss_size} Bytes (0x{self.bss_size:X})",
        ]


def parse_int(value: str | int, label: str = "Wert") -> int:
    if isinstance(value, int):
        return _require_non_negative(value, label)
    text = str(value).strip().replace("_", "")
    if not text:
        raise NsoError(f"{label} fehlt")
    try:
        if text.lower().startswith("0d"):
            parsed = int(text[2:], 10)
        elif text.lower().startswith(("0x", "+0x")):
            parsed = int(text, 16)
        else:
            # Reverse-engineering addresses are hexadecimal by default. Decimal
            # input remains available explicitly through the 0d prefix.
            parsed = int(text, 16)
    except ValueError as exc:
        raise NsoError(f"{label} ist keine gültige Zahl: {value!r}") from exc
    return _require_non_negative(parsed, label)


def _u32(raw: bytes, offset: int) -> int:
    return struct.unpack_from("<I", raw, offset)[0]


def _require_non_negative(value: int, label: str) -> int:
    if not isinstance(value, int):
        raise NsoError(f"{label} muss eine Ganzzahl sein")
    if value < 0:
        raise NsoError(f"{label} darf nicht negativ sein")
    return value


def _read_module_name(raw: bytes, offset: int, size: int) -> str:
    if size == 0 or offset == 0:
        return ""
    # Some valid NSOs use placeholder values when no useful module name is
    # present. The field is informational and must not prevent analysis of
    # otherwise valid executable segments.
    if offset < NSO_HEADER_SIZE or offset + size > len(raw):
        return ""
    value = raw[offset:offset + size].split(b"\0", 1)[0]
    return value.decode("utf-8", errors="replace")


def _validate_memory_ranges(segments: Iterable[NsoSegment]) -> None:
    active = sorted(
        (segment for segment in segments if segment.memory_size),
        key=lambda segment: segment.memory_offset,
    )
    for previous, current in zip(active, active[1:]):
        if previous.memory_end > current.memory_offset:
            raise NsoError(
                f"Speichersegmente überlappen: {previous.name} endet bei "
                f"0x{previous.memory_end:X}, {current.name} beginnt bei "
                f"0x{current.memory_offset:X}"
            )


def _validate_file_ranges(segments: Iterable[NsoSegment]) -> None:
    active = sorted(
        (
            segment
            for segment in segments
            if segment.file_offset is not None and segment.stored_size
        ),
        key=lambda segment: int(segment.file_offset),
    )
    for previous, current in zip(active, active[1:]):
        if int(previous.file_end) > int(current.file_offset):
            raise NsoError(
                f"Dateisegmente überlappen: {previous.name} endet bei "
                f"0x{int(previous.file_end):X}, {current.name} beginnt bei "
                f"0x{int(current.file_offset):X}"
            )


def _lz4_decompress_block(data: bytes, expected_size: int) -> bytes:
    """Decode a raw LZ4 block as used by compressed NSO segments."""
    source = memoryview(data)
    source_pos = 0
    output = bytearray()

    while source_pos < len(source):
        token = int(source[source_pos])
        source_pos += 1
        literal_length = token >> 4
        if literal_length == 15:
            while True:
                if source_pos >= len(source):
                    raise NsoError("Abgeschnittener LZ4-Literal-Längenwert")
                extra = int(source[source_pos])
                source_pos += 1
                literal_length += extra
                if extra != 255:
                    break
        literal_end = source_pos + literal_length
        if literal_end > len(source):
            raise NsoError("LZ4-Literalbereich überschreitet das Segment")
        output.extend(source[source_pos:literal_end])
        source_pos = literal_end

        if source_pos == len(source):
            break
        if source_pos + 2 > len(source):
            raise NsoError("Abgeschnittener LZ4-Match-Offset")
        match_offset = int(source[source_pos]) | (int(source[source_pos + 1]) << 8)
        source_pos += 2
        if match_offset == 0 or match_offset > len(output):
            raise NsoError(f"Ungültiger LZ4-Match-Offset: {match_offset}")

        match_length = token & 0x0F
        if match_length == 15:
            while True:
                if source_pos >= len(source):
                    raise NsoError("Abgeschnittener LZ4-Match-Längenwert")
                extra = int(source[source_pos])
                source_pos += 1
                match_length += extra
                if extra != 255:
                    break
        match_length += 4
        match_pos = len(output) - match_offset
        for _ in range(match_length):
            output.append(output[match_pos])
            match_pos += 1
        if len(output) > expected_size:
            raise NsoError(
                f"LZ4-Ausgabe überschreitet die erwartete Größe {expected_size}"
            )

    if len(output) != expected_size:
        raise NsoError(
            f"LZ4-Ausgabe hat {len(output)} statt {expected_size} Bytes"
        )
    return bytes(output)
