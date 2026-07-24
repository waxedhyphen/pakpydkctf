"""Universal validated ARM64 patch projects and IPS32 export for NSO modules.

The engine contains no game-specific addresses or byte sequences. Concrete mods are
stored as external JSON project files and can also be created or edited in the GUI.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable

from exefs_arm64 import decode_word
from exefs_nso import NSO_HEADER_SIZE, NsoError, NsoImage


IPS32_HEADER = b"IPS32"
IPS32_FOOTER = b"EEOF"
PROJECT_SCHEMA_VERSION = 1
_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")


@dataclass(frozen=True)
class ExeFsPatchEntry:
    memory_offset: int
    expected: bytes
    replacement: bytes
    description: str = ""

    def __post_init__(self):
        if self.memory_offset < 0:
            raise NsoError("Patchadresse darf nicht negativ sein")
        if not self.expected:
            raise NsoError("Erwartete Originalbytes fehlen")
        if len(self.expected) != len(self.replacement):
            raise NsoError("ExeFS-Patches dürfen die Modulgröße nicht verändern")

    @property
    def end(self) -> int:
        return self.memory_offset + len(self.expected)

    @property
    def ips_offset(self) -> int:
        return NSO_HEADER_SIZE + self.memory_offset

    def to_dict(self) -> dict:
        return {
            "memory_offset": f"0x{self.memory_offset:X}",
            "expected": self.expected.hex(" ").upper(),
            "replacement": self.replacement.hex(" ").upper(),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, value: dict) -> "ExeFsPatchEntry":
        if not isinstance(value, dict):
            raise NsoError("Patcheintrag muss ein JSON-Objekt sein")
        return cls(
            memory_offset=_parse_offset(value.get("memory_offset")),
            expected=_parse_hex_bytes(value.get("expected"), "expected"),
            replacement=_parse_hex_bytes(value.get("replacement"), "replacement"),
            description=str(value.get("description", "") or ""),
        )


@dataclass(frozen=True)
class ExeFsPatchProject:
    name: str
    patch_group: str
    entries: tuple[ExeFsPatchEntry, ...]
    expected_build_id: str = ""
    notes: str = ""
    schema_version: int = PROJECT_SCHEMA_VERSION

    def __post_init__(self):
        if int(self.schema_version) != PROJECT_SCHEMA_VERSION:
            raise NsoError(
                f"Nicht unterstützte Patchprojekt-Version: {self.schema_version}; "
                f"erwartet {PROJECT_SCHEMA_VERSION}"
            )
        if not str(self.name).strip():
            raise NsoError("Patchprojektname fehlt")
        _safe_group_name(self.patch_group)
        if not self.entries:
            raise NsoError("Patchprojekt enthält keine Patcheinträge")
        normalized = _normalize_build_id(self.expected_build_id, allow_empty=True)
        object.__setattr__(self, "expected_build_id", normalized)
        object.__setattr__(self, "entries", tuple(self.entries))
        _validate_non_overlapping(self.entries)

    def to_dict(self) -> dict:
        return {
            "schema_version": PROJECT_SCHEMA_VERSION,
            "name": self.name,
            "patch_group": self.patch_group,
            "expected_build_id": self.expected_build_id,
            "notes": self.notes,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, value: dict) -> "ExeFsPatchProject":
        if not isinstance(value, dict):
            raise NsoError("Patchprojekt muss ein JSON-Objekt sein")
        raw_entries = value.get("entries")
        if not isinstance(raw_entries, list):
            raise NsoError("Patchprojektfeld 'entries' muss eine Liste sein")
        return cls(
            name=str(value.get("name", "") or ""),
            patch_group=str(value.get("patch_group", "") or ""),
            expected_build_id=str(value.get("expected_build_id", "") or ""),
            notes=str(value.get("notes", "") or ""),
            schema_version=int(value.get("schema_version", PROJECT_SCHEMA_VERSION)),
            entries=tuple(ExeFsPatchEntry.from_dict(item) for item in raw_entries),
        )


@dataclass(frozen=True)
class PatchEntryPreview:
    entry: ExeFsPatchEntry
    segment: str
    actual: bytes
    valid: bool
    before_disassembly: tuple[str, ...]
    after_disassembly: tuple[str, ...]

    def format_lines(self) -> list[str]:
        status = "OK" if self.valid else "FEHLER"
        lines = [
            f"[{status}] NSO-VA 0x{self.entry.memory_offset:X} / IPS32 0x{self.entry.ips_offset:X}",
            f"  {self.entry.description or '—'}",
            f"  Segment: {self.segment}",
            f"  Erwartet: {self.entry.expected.hex(' ').upper()}",
            f"  Gefunden: {self.actual.hex(' ').upper()}",
            f"  Neu:      {self.entry.replacement.hex(' ').upper()}",
        ]
        if self.before_disassembly:
            lines.append("  Vorher:   " + " | ".join(self.before_disassembly))
        if self.after_disassembly:
            lines.append("  Nachher:  " + " | ".join(self.after_disassembly))
        return lines


@dataclass(frozen=True)
class PatchProjectPreview:
    project: ExeFsPatchProject
    build_id: str
    source_sha256: str
    build_id_valid: bool
    entries: tuple[PatchEntryPreview, ...]

    @property
    def name(self) -> str:
        return self.project.name

    @property
    def patch_group(self) -> str:
        return self.project.patch_group

    @property
    def valid(self) -> bool:
        return self.build_id_valid and bool(self.entries) and all(item.valid for item in self.entries)

    def format_lines(self) -> list[str]:
        expected = self.project.expected_build_id or "nicht festgelegt"
        lines = [
            f"Patchprojekt: {self.project.name}",
            f"Patchgruppe: {self.project.patch_group}",
            f"Build ID geladen:  {self.build_id}",
            f"Build ID erwartet: {expected}",
            f"Build-ID-Prüfung: {'OK' if self.build_id_valid else 'FEHLER'}",
            f"main SHA-256: {self.source_sha256}",
            f"Status: {'VALIDIERT' if self.valid else 'NICHT EXPORTIERBAR'}",
            "",
        ]
        for index, item in enumerate(self.entries, 1):
            lines.append(f"Eintrag {index}")
            lines.extend(item.format_lines())
            lines.append("")
        return lines


def load_patch_project(path: str | Path) -> ExeFsPatchProject:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise NsoError(f"Patchprojekt konnte nicht gelesen werden: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise NsoError(
            f"Ungültiges Patchprojekt-JSON in Zeile {exc.lineno}, Spalte {exc.colno}: {exc.msg}"
        ) from exc
    return ExeFsPatchProject.from_dict(value)


def save_patch_project(project: ExeFsPatchProject, path: str | Path) -> str:
    destination = Path(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(project.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise NsoError(f"Patchprojekt konnte nicht gespeichert werden: {exc}") from exc
    return str(destination)


def preview_patch_project(image: NsoImage, project: ExeFsPatchProject) -> PatchProjectPreview:
    _validate_non_overlapping(project.entries)
    expected = project.expected_build_id
    build_id_valid = not expected or image.build_id_hex.upper() == expected.upper()
    previews = tuple(_preview_entry(image, entry) for entry in project.entries)
    return PatchProjectPreview(
        project=project,
        build_id=image.build_id_hex,
        source_sha256=image.file_sha256,
        build_id_valid=build_id_valid,
        entries=previews,
    )


def preview_project(
    image: NsoImage,
    name: str,
    entries: Iterable[ExeFsPatchEntry],
    expected_build_id: str = "",
    patch_group: str = "ExeFS_Patch",
) -> PatchProjectPreview:
    project = ExeFsPatchProject(
        name=str(name),
        patch_group=patch_group,
        expected_build_id=expected_build_id,
        entries=tuple(entries),
    )
    return preview_patch_project(image, project)


def _preview_entry(image: NsoImage, entry: ExeFsPatchEntry) -> PatchEntryPreview:
    segment = None
    for candidate in image.segments:
        if (
            candidate.memory_size
            and candidate.memory_offset <= entry.memory_offset
            and entry.end <= candidate.memory_end
        ):
            segment = candidate
            break
    if segment is None:
        raise NsoError(
            f"Patch 0x{entry.memory_offset:X}–0x{entry.end:X} liegt in keinem Segment"
        )
    if segment.name == "bss":
        raise NsoError("BSS kann nicht mit einem statischen IPS-Patch beschrieben werden")
    data = image.read_segment(segment.name)
    local = entry.memory_offset - segment.memory_offset
    actual = data[local:local + len(entry.expected)]
    return PatchEntryPreview(
        entry=entry,
        segment=segment.name,
        actual=actual,
        valid=actual == entry.expected,
        before_disassembly=_disassemble_bytes(entry.memory_offset, actual),
        after_disassembly=_disassemble_bytes(entry.memory_offset, entry.replacement),
    )


def _disassemble_bytes(memory_offset: int, data: bytes) -> tuple[str, ...]:
    if memory_offset % 4 or len(data) % 4:
        return ()
    lines = []
    for index in range(0, len(data), 4):
        word = int.from_bytes(data[index:index + 4], "little")
        mnemonic, operands, target, _call, _ret = decode_word(word, memory_offset + index)
        text = mnemonic + ((" " + operands) if operands else "")
        if target is not None and "0x" not in operands:
            text += f" -> 0x{target:X}"
        lines.append(text)
    return tuple(lines)


def build_ips32(preview: PatchProjectPreview) -> bytes:
    if not preview.valid:
        raise NsoError("Patchprojekt ist nicht vollständig gegen Build ID und Originalbytes validiert")
    output = bytearray(IPS32_HEADER)
    for item in preview.entries:
        entry = item.entry
        cursor = 0
        while cursor < len(entry.replacement):
            chunk = entry.replacement[cursor:cursor + 0xFFFF]
            current_offset = entry.ips_offset + cursor
            if current_offset > 0xFFFFFFFF:
                raise NsoError("IPS32-Offset überschreitet 32 Bit")
            output.extend(current_offset.to_bytes(4, "big"))
            output.extend(len(chunk).to_bytes(2, "big"))
            output.extend(chunk)
            cursor += len(chunk)
    output.extend(IPS32_FOOTER)
    return bytes(output)


def export_ips32_file(
    preview: PatchProjectPreview,
    destination: str | Path,
    filename: str | None = None,
) -> str:
    if not preview.valid:
        raise NsoError("Ungültiges Patchprojekt kann nicht exportiert werden")
    target = Path(destination)
    if target.suffix.lower() != ".ips":
        target.mkdir(parents=True, exist_ok=True)
        target = target / (filename or f"{preview.build_id}.ips")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(build_ips32(preview))
    except OSError as exc:
        raise NsoError(f"IPS32-Datei konnte nicht geschrieben werden: {exc}") from exc
    return str(target)


def export_emulator_patch(
    preview: PatchProjectPreview,
    mod_root: str | Path,
    filename: str | None = None,
) -> dict[str, str]:
    root = Path(mod_root)
    exefs_dir = root / "exefs"
    patch_path = Path(export_ips32_file(preview, exefs_dir, filename))
    manifest_path, report_path = _write_metadata(preview, exefs_dir)
    return {
        "patch": str(patch_path),
        "manifest": str(manifest_path),
        "report": str(report_path),
    }


def export_atmosphere_patch(
    preview: PatchProjectPreview,
    destination: str | Path,
    patch_group: str | None = None,
) -> dict[str, str]:
    if not preview.valid:
        raise NsoError("Ungültiges Patchprojekt kann nicht exportiert werden")
    group = _safe_group_name(patch_group or preview.patch_group)
    root = Path(destination)
    patch_dir = root / "atmosphere" / "exefs_patches" / group
    patch_path = Path(export_ips32_file(preview, patch_dir))
    manifest_path, report_path = _write_metadata(preview, patch_dir)
    return {
        "patch": str(patch_path),
        "manifest": str(manifest_path),
        "report": str(report_path),
    }


def _write_metadata(preview: PatchProjectPreview, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": preview.name,
        "patch_group": preview.patch_group,
        "expected_build_id": preview.project.expected_build_id,
        "loaded_build_id": preview.build_id,
        "source_sha256": preview.source_sha256,
        "format": "IPS32",
        "atmosphere_offset_rule": "ips_offset = nso_memory_offset + 0x100",
        "notes": preview.project.notes,
        "entries": [
            {
                **item.entry.to_dict(),
                "ips_offset": f"0x{item.entry.ips_offset:X}",
                "before": list(item.before_disassembly),
                "after": list(item.after_disassembly),
            }
            for item in preview.entries
        ],
    }
    manifest_path = directory / "manifest.json"
    report_path = directory / "README.md"
    try:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        report_path.write_text(
            "# " + preview.name + "\n\n```text\n" + "\n".join(preview.format_lines()) + "```\n",
            encoding="utf-8",
            newline="\n",
        )
    except OSError as exc:
        raise NsoError(f"Patchmetadaten konnten nicht geschrieben werden: {exc}") from exc
    return manifest_path, report_path


def _validate_non_overlapping(entries: tuple[ExeFsPatchEntry, ...]) -> None:
    ordered = sorted(entries, key=lambda item: item.memory_offset)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end > current.memory_offset:
            raise NsoError(
                f"Patches überlappen: 0x{previous.memory_offset:X} und 0x{current.memory_offset:X}"
            )


def _parse_offset(value) -> int:
    if isinstance(value, bool):
        raise NsoError("memory_offset darf kein Boolean sein")
    if isinstance(value, int):
        result = value
    elif isinstance(value, str):
        text = value.strip().replace("_", "")
        if not text:
            raise NsoError("memory_offset fehlt")
        try:
            result = int(text, 0) if text.lower().startswith(("0x", "+0x")) else int(text, 16)
        except ValueError as exc:
            raise NsoError(f"Ungültiger memory_offset: {value!r}") from exc
    else:
        raise NsoError("memory_offset muss Zahl oder Hex-String sein")
    if result < 0:
        raise NsoError("memory_offset darf nicht negativ sein")
    return result


def _parse_hex_bytes(value, field: str) -> bytes:
    if not isinstance(value, str):
        raise NsoError(f"{field} muss ein Hex-String sein")
    compact = value.replace("0x", "").replace("0X", "")
    compact = "".join(compact.split()).replace("_", "")
    if not compact:
        raise NsoError(f"{field} fehlt")
    if len(compact) % 2 or not _HEX_RE.fullmatch(compact):
        raise NsoError(f"Ungültige Hexbytes in {field}: {value!r}")
    return bytes.fromhex(compact)


def _normalize_build_id(value: str, allow_empty: bool = False) -> str:
    text = "".join(str(value or "").split()).upper()
    if not text and allow_empty:
        return ""
    if len(text) != 64 or not _HEX_RE.fullmatch(text):
        raise NsoError("Build ID muss exakt 32 Bytes / 64 Hexzeichen enthalten")
    return text


def _safe_group_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(value).strip())
    text = text.strip("_")
    if not text:
        raise NsoError("Patchgruppenname fehlt")
    return text
