"""String catalog, pointer references and native callback-table discovery for NSO files."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from exefs_nso import NsoError, NsoImage


@dataclass(frozen=True)
class NsoString:
    text: str
    encoding: str
    segment: str
    memory_offset: int
    segment_offset: int
    byte_length: int


@dataclass(frozen=True)
class PointerReference:
    segment: str
    memory_offset: int
    target: int
    width: int = 8


@dataclass(frozen=True)
class CodeReference:
    memory_offset: int
    kind: str
    target: int
    instruction_offsets: tuple[int, ...]
    register: Optional[int] = None


@dataclass(frozen=True)
class CallbackRecord:
    record_address: int
    name_address: int
    name: str
    flags: int
    function_address: int
    reserved: int


@dataclass(frozen=True)
class StringTraceResult:
    query: str
    strings: tuple[NsoString, ...]
    pointer_references: tuple[PointerReference, ...]
    code_references: tuple[CodeReference, ...]
    callbacks: tuple[CallbackRecord, ...]

    def format_lines(self) -> list[str]:
        lines = [f"Suche: {self.query!r}", f"Stringtreffer: {len(self.strings)}", ""]
        for item in self.strings:
            lines.extend([
                f"[{item.segment}] 0x{item.memory_offset:X}  {item.encoding}  {item.text!r}",
                f"  Segmentoffset: 0x{item.segment_offset:X}; Bytes: {item.byte_length}",
            ])
        if not self.strings:
            lines.append("Keine passenden Strings gefunden.")

        lines.extend(["", f"Pointerreferenzen: {len(self.pointer_references)}"])
        for ref in self.pointer_references:
            lines.append(
                f"  [{ref.segment}] 0x{ref.memory_offset:X} -> 0x{ref.target:X} ({ref.width * 8}-Bit)"
            )

        lines.extend(["", f"ARM64-Referenzen: {len(self.code_references)}"])
        for ref in self.code_references:
            sites = ", ".join(f"0x{x:X}" for x in ref.instruction_offsets)
            lines.append(f"  0x{ref.memory_offset:X}: {ref.kind} -> 0x{ref.target:X} ({sites})")

        lines.extend(["", f"Callback-Kandidaten: {len(self.callbacks)}"])
        for callback in self.callbacks:
            lines.extend([
                f"  {callback.name}",
                f"    Record:   0x{callback.record_address:X}",
                f"    Name:     0x{callback.name_address:X}",
                f"    Funktion: 0x{callback.function_address:X}",
                f"    Flags:    0x{callback.flags:X}",
            ])
        return lines


def catalog_strings(
    image: NsoImage,
    minimum_length: int = 4,
    segments: Iterable[str] = ("rodata", "data"),
    include_utf16: bool = True,
) -> tuple[NsoString, ...]:
    if minimum_length < 2:
        raise NsoError("Minimale Stringlänge muss mindestens 2 sein")
    found: list[NsoString] = []
    for segment_name in segments:
        segment = image.segment(segment_name)
        data = image.read_segment(segment_name)
        found.extend(_ascii_strings(data, segment_name, segment.memory_offset, minimum_length))
        if include_utf16:
            found.extend(_utf16le_strings(data, segment_name, segment.memory_offset, minimum_length))
    found.sort(key=lambda item: (item.memory_offset, item.encoding, item.text))
    return tuple(found)


def find_strings(
    image: NsoImage,
    query: str,
    exact: bool = False,
    case_sensitive: bool = True,
    catalog: Optional[tuple[NsoString, ...]] = None,
) -> tuple[NsoString, ...]:
    text = str(query)
    if not text:
        raise NsoError("String-Suchbegriff fehlt")
    values = catalog if catalog is not None else catalog_strings(image)
    needle = text if case_sensitive else text.casefold()
    result = []
    for item in values:
        candidate = item.text if case_sensitive else item.text.casefold()
        matches = candidate == needle if exact else needle in candidate
        if matches:
            result.append(item)
    return tuple(result)


def trace_string(
    image: NsoImage,
    query: str,
    exact: bool = True,
    case_sensitive: bool = True,
    catalog: Optional[tuple[NsoString, ...]] = None,
) -> StringTraceResult:
    catalog = catalog if catalog is not None else catalog_strings(image)
    strings = find_strings(
        image, query, exact=exact, case_sensitive=case_sensitive, catalog=catalog
    )
    target_addresses = {item.memory_offset for item in strings}
    pointers = find_pointer_references(image, target_addresses)
    pointer_addresses = {item.memory_offset for item in pointers}
    callbacks = find_callback_records(image, catalog=catalog, names=target_addresses)
    callback_addresses = {item.record_address for item in callbacks}
    reference_targets = target_addresses | pointer_addresses | callback_addresses
    code_refs = find_code_references(image, reference_targets)
    return StringTraceResult(
        query=str(query),
        strings=strings,
        pointer_references=pointers,
        code_references=code_refs,
        callbacks=callbacks,
    )


def find_pointer_references(
    image: NsoImage,
    targets: set[int],
    segments: Iterable[str] = ("rodata", "data"),
) -> tuple[PointerReference, ...]:
    if not targets:
        return ()
    result: list[PointerReference] = []
    for segment_name in segments:
        segment = image.segment(segment_name)
        data = image.read_segment(segment_name)
        alignment = (-segment.memory_offset) & 7
        for offset in range(alignment, len(data) - 7, 8):
            value = int.from_bytes(data[offset:offset + 8], "little")
            if value in targets:
                result.append(
                    PointerReference(
                        segment=segment_name,
                        memory_offset=segment.memory_offset + offset,
                        target=value,
                    )
                )
    return tuple(result)


def find_callback_records(
    image: NsoImage,
    catalog: Optional[tuple[NsoString, ...]] = None,
    names: Optional[set[int]] = None,
) -> tuple[CallbackRecord, ...]:
    strings = catalog if catalog is not None else catalog_strings(image)
    by_address = {item.memory_offset: item for item in strings}
    text_segment = image.segment("text")
    data_segment = image.segment("data")
    data = image.read_segment("data")
    result: list[CallbackRecord] = []
    alignment = (-data_segment.memory_offset) & 7
    for offset in range(alignment, len(data) - 31, 8):
        name_address = int.from_bytes(data[offset:offset + 8], "little")
        if name_address not in by_address:
            continue
        if names is not None and name_address not in names:
            continue
        flags = int.from_bytes(data[offset + 8:offset + 16], "little")
        function_address = int.from_bytes(data[offset + 16:offset + 24], "little")
        reserved = int.from_bytes(data[offset + 24:offset + 32], "little")
        if not text_segment.contains_memory_offset(function_address):
            continue
        if flags > 0xFFFF:
            continue
        if reserved != 0:
            continue
        name = by_address[name_address].text
        if not _looks_callback_name(name):
            continue
        result.append(
            CallbackRecord(
                record_address=data_segment.memory_offset + offset,
                name_address=name_address,
                name=name,
                flags=flags,
                function_address=function_address,
                reserved=reserved,
            )
        )
    return tuple(result)


def find_code_references(image: NsoImage, targets: set[int]) -> tuple[CodeReference, ...]:
    if not targets:
        return ()
    text_segment = image.segment("text")
    text = image.read_segment("text")
    result: list[CodeReference] = []
    seen = set()

    for offset in range(0, len(text) - 3, 4):
        address = text_segment.memory_offset + offset
        word = int.from_bytes(text[offset:offset + 4], "little")

        adr = _decode_adr_target(word, address)
        if adr is not None and adr[1] in targets:
            register, target, kind = adr
            key = (address, kind, target)
            if key not in seen:
                seen.add(key)
                result.append(CodeReference(address, kind, target, (address,), register))

        adrp = _decode_adrp_target(word, address)
        if adrp is None:
            continue
        register, page = adrp
        for distance in range(1, 9):
            next_offset = offset + distance * 4
            if next_offset + 4 > len(text):
                break
            next_address = text_segment.memory_offset + next_offset
            next_word = int.from_bytes(text[next_offset:next_offset + 4], "little")
            add = _decode_add_immediate(next_word)
            if add is not None:
                rd, rn, immediate = add
                if rn == register:
                    target = page + immediate
                    if target in targets:
                        key = (address, next_address, "ADRP+ADD", target)
                        if key not in seen:
                            seen.add(key)
                            result.append(
                                CodeReference(
                                    address,
                                    "ADRP+ADD",
                                    target,
                                    (address, next_address),
                                    rd,
                                )
                            )
            load = _decode_unsigned_load_store(next_word)
            if load is not None:
                _rt, rn, immediate, mnemonic = load
                if rn == register:
                    target = page + immediate
                    if target in targets:
                        key = (address, next_address, f"ADRP+{mnemonic}", target)
                        if key not in seen:
                            seen.add(key)
                            result.append(
                                CodeReference(
                                    address,
                                    f"ADRP+{mnemonic}",
                                    target,
                                    (address, next_address),
                                    register,
                                )
                            )
    result.sort(key=lambda item: (item.memory_offset, item.target, item.kind))
    return tuple(result)


def _ascii_strings(data: bytes, segment: str, base: int, minimum: int):
    result = []
    start = None
    for index, value in enumerate(data + b"\0"):
        printable = 0x20 <= value <= 0x7E or value in (0x09, 0x0A, 0x0D)
        if printable:
            if start is None:
                start = index
            continue
        if start is not None and index - start >= minimum:
            raw = data[start:index]
            result.append(
                NsoString(
                    text=raw.decode("utf-8", errors="replace"),
                    encoding="ascii/utf-8",
                    segment=segment,
                    memory_offset=base + start,
                    segment_offset=start,
                    byte_length=len(raw),
                )
            )
        start = None
    return result


def _utf16le_strings(data: bytes, segment: str, base: int, minimum: int):
    result = []
    for parity in (0, 1):
        start = None
        index = parity
        while index + 1 < len(data):
            low, high = data[index], data[index + 1]
            printable = high == 0 and (0x20 <= low <= 0x7E)
            if printable:
                if start is None:
                    start = index
            else:
                if start is not None:
                    length = (index - start) // 2
                    if length >= minimum:
                        raw = data[start:index]
                        result.append(
                            NsoString(
                                text=raw.decode("utf-16le", errors="replace"),
                                encoding="utf-16le",
                                segment=segment,
                                memory_offset=base + start,
                                segment_offset=start,
                                byte_length=len(raw),
                            )
                        )
                start = None
            index += 2
    return result


def _looks_callback_name(value: str) -> bool:
    if not value or len(value) > 160:
        return False
    if any(ch.isspace() for ch in value):
        return False
    return all(ch.isalnum() or ch in "_:." for ch in value)


def _decode_adr_target(word: int, address: int):
    if (word & 0x1F000000) != 0x10000000:
        return None
    page = bool((word >> 31) & 1)
    immlo = (word >> 29) & 3
    immhi = (word >> 5) & 0x7FFFF
    immediate = _sign_extend((immhi << 2) | immlo, 21)
    register = word & 31
    if page:
        return register, ((address & ~0xFFF) + (immediate << 12)) & 0xFFFFFFFFFFFFFFFF, "ADRP"
    return register, (address + immediate) & 0xFFFFFFFFFFFFFFFF, "ADR"


def _decode_adrp_target(word: int, address: int):
    decoded = _decode_adr_target(word, address)
    if decoded is None or decoded[2] != "ADRP":
        return None
    return decoded[0], decoded[1]


def _decode_add_immediate(word: int):
    if (word & 0x1F000000) != 0x11000000:
        return None
    if (word >> 30) & 1:
        return None
    if (word >> 29) & 1:
        return None
    shift = 12 if ((word >> 22) & 1) else 0
    immediate = ((word >> 10) & 0xFFF) << shift
    rn = (word >> 5) & 31
    rd = word & 31
    return rd, rn, immediate


def _decode_unsigned_load_store(word: int):
    if (word & 0x3B000000) != 0x39000000:
        return None
    if (word >> 26) & 1:
        return None
    size = (word >> 30) & 3
    opc = (word >> 22) & 3
    immediate = ((word >> 10) & 0xFFF) * (1 << size)
    rn = (word >> 5) & 31
    rt = word & 31
    mnemonic = "LDR" if opc in (1, 2) else "STR"
    return rt, rn, immediate, mnemonic


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)
