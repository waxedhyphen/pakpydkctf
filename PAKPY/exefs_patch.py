"""Validated ARM64 patch previews and Atmosphere IPS32 export for NSO modules."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

from exefs_arm64 import decode_word
from exefs_nso import NSO_HEADER_SIZE, NsoError, NsoImage


IPS32_HEADER = b"IPS32"
IPS32_FOOTER = b"EEOF"


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
        # Atmosphere protects the 0x100-byte NSO header and subtracts 0x100
        # before copying into the decompressed mapped module.
        return NSO_HEADER_SIZE + self.memory_offset


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
    name: str
    build_id: str
    source_sha256: str
    entries: tuple[PatchEntryPreview, ...]

    @property
    def valid(self) -> bool:
        return bool(self.entries) and all(item.valid for item in self.entries)

    def format_lines(self) -> list[str]:
        lines = [
            f"Patchprojekt: {self.name}",
            f"Build ID: {self.build_id}",
            f"main SHA-256: {self.source_sha256}",
            f"Status: {'VALIDIERT' if self.valid else 'NICHT EXPORTIERBAR'}",
            "",
        ]
        for index, item in enumerate(self.entries, 1):
            lines.append(f"Eintrag {index}")
            lines.extend(item.format_lines())
            lines.append("")
        return lines


def hardmode_keep_p2_active_entries() -> tuple[ExeFsPatchEntry, ...]:
    return (
        ExeFsPatchEntry(
            memory_offset=0x1E7018,
            expected=bytes.fromhex("29 15 1E 12"),
            replacement=bytes.fromhex("29 19 1F 12"),
            description=(
                "Hard Mode: aktives P2-Bit erhalten. "
                "(flags & 0xFC) | 1 wird zu (flags & 0xFE) | 1."
            ),
        ),
    )


def preview_project(
    image: NsoImage,
    name: str,
    entries: Iterable[ExeFsPatchEntry],
) -> PatchProjectPreview:
    entries = tuple(entries)
    _validate_non_overlapping(entries)
    previews = tuple(_preview_entry(image, entry) for entry in entries)
    return PatchProjectPreview(
        name=str(name),
        build_id=image.build_id_hex,
        source_sha256=image.file_sha256,
        entries=previews,
    )


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
        raise NsoError("Patchprojekt ist nicht vollständig gegen die Originalbytes validiert")
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


def export_atmosphere_patch(
    preview: PatchProjectPreview,
    destination: str | Path,
    patch_group: str,
) -> dict[str, str]:
    if not preview.valid:
        raise NsoError("Ungültiges Patchprojekt kann nicht exportiert werden")
    group = _safe_group_name(patch_group)
    root = Path(destination)
    patch_dir = root / "atmosphere" / "exefs_patches" / group
    patch_dir.mkdir(parents=True, exist_ok=True)
    patch_path = patch_dir / f"{preview.build_id}.ips"
    patch_path.write_bytes(build_ips32(preview))

    manifest = {
        "name": preview.name,
        "build_id": preview.build_id,
        "source_sha256": preview.source_sha256,
        "format": "IPS32",
        "atmosphere_offset_rule": "ips_offset = nso_memory_offset + 0x100",
        "entries": [
            {
                "memory_offset": f"0x{item.entry.memory_offset:X}",
                "ips_offset": f"0x{item.entry.ips_offset:X}",
                "expected": item.entry.expected.hex(" ").upper(),
                "replacement": item.entry.replacement.hex(" ").upper(),
                "description": item.entry.description,
                "before": list(item.before_disassembly),
                "after": list(item.after_disassembly),
            }
            for item in preview.entries
        ],
    }
    manifest_path = patch_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    report_path = patch_dir / "README.md"
    report_path.write_text(
        "# " + preview.name + "\n\n```text\n" + "\n".join(preview.format_lines()) + "```\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "patch": str(patch_path),
        "manifest": str(manifest_path),
        "report": str(report_path),
    }


def _validate_non_overlapping(entries: tuple[ExeFsPatchEntry, ...]) -> None:
    ordered = sorted(entries, key=lambda item: item.memory_offset)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.end > current.memory_offset:
            raise NsoError(
                f"Patches überlappen: 0x{previous.memory_offset:X} und 0x{current.memory_offset:X}"
            )


def _safe_group_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(value).strip())
    text = text.strip("_")
    if not text:
        raise NsoError("Patchgruppenname fehlt")
    return text
