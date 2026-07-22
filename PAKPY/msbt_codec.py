"""Bounded read-only parser for Nintendo Message Studio Binary Text (MSBT).

The parser accepts the big- and little-endian ``MsgStdBn`` variants used by
Tropical Freeze, validates section boundaries and exposes labels, texts and
raw attributes without modifying source data.
"""
from __future__ import annotations

from dataclasses import dataclass


class MsbtError(Exception):
    pass


_MAX_SECTIONS = 64
_MAX_MESSAGES = 1_000_000
_MAX_SECTION_BYTES = 256 * 1024 * 1024
_MAX_LABEL_BYTES = 4096
_MAX_TEXT_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class MsbtSection:
    tag: str
    offset: int
    size: int
    data: bytes


@dataclass(frozen=True)
class MsbtMessage:
    index: int
    label: str
    text: str
    attribute: bytes = b""


@dataclass(frozen=True)
class MsbtDocument:
    byte_order: str
    encoding: str
    encoding_code: int
    version: int
    file_size: int
    sections: tuple[MsbtSection, ...]
    messages: tuple[MsbtMessage, ...]

    @property
    def by_label(self):
        return {message.label: message for message in self.messages if message.label}


def _align(value: int, alignment: int = 16) -> int:
    return (int(value) + alignment - 1) & ~(alignment - 1)


def _uint(data: bytes, offset: int, size: int, byte_order: str, label: str) -> int:
    end = offset + size
    if offset < 0 or end > len(data):
        raise MsbtError(f"{label} ist abgeschnitten")
    return int.from_bytes(data[offset:end], byte_order)


def _encoding_name(code: int, byte_order: str) -> str:
    if code == 0:
        return "utf-8"
    if code == 1:
        return "utf-16-le" if byte_order == "little" else "utf-16-be"
    if code == 2:
        return "utf-32-le" if byte_order == "little" else "utf-32-be"
    raise MsbtError(f"Nicht unterstützte MSBT-Zeichenkodierung {code}")


def _decode_plain(raw: bytes, encoding: str, unit: int) -> str:
    if not raw:
        return ""
    usable = len(raw) - (len(raw) % unit)
    if usable <= 0:
        return ""
    return raw[:usable].decode(encoding, "replace")


def _decode_utf16_message(raw: bytes, byte_order: str, encoding: str) -> str:
    """Decode UTF-16 and preserve Message Studio control tags diagnostically."""
    out: list[str] = []
    plain = bytearray()
    p = 0

    def flush():
        if plain:
            out.append(_decode_plain(bytes(plain), encoding, 2))
            plain.clear()

    while p + 2 <= len(raw):
        code = int.from_bytes(raw[p:p + 2], byte_order)
        if code == 0:
            break
        if code == 0x000E:
            flush()
            if p + 8 > len(raw):
                out.append("<tag:truncated>")
                break
            group = int.from_bytes(raw[p + 2:p + 4], byte_order)
            kind = int.from_bytes(raw[p + 4:p + 6], byte_order)
            size = int.from_bytes(raw[p + 6:p + 8], byte_order)
            payload_start = p + 8
            payload_end = payload_start + size
            if payload_end > len(raw):
                out.append(f"<tag:{group}:{kind}:truncated>")
                break
            payload = raw[payload_start:payload_end]
            out.append(f"<tag:{group}:{kind}:{payload.hex()}>")
            p = payload_end
            if p & 1:
                p += 1
            continue
        if code == 0x000F:
            flush()
            out.append("</tag>")
            p += 2
            continue
        plain += raw[p:p + 2]
        p += 2
    flush()
    return "".join(out)


def _message_end(payload: bytes, start: int, limit: int, code: int) -> int:
    unit = 1 if code == 0 else 2 if code == 1 else 4
    p = start
    while p + unit <= limit:
        if payload[p:p + unit] == b"\x00" * unit:
            return p
        p += unit
    return limit


def _decode_message(payload: bytes, start: int, limit: int, code: int,
                    byte_order: str, encoding: str) -> str:
    if start < 0 or limit < start or limit > len(payload):
        raise MsbtError("TXT2-Textgrenze ist ungültig")
    end = _message_end(payload, start, limit, code)
    raw = payload[start:end]
    if len(raw) > _MAX_TEXT_BYTES:
        raise MsbtError("Ein MSBT-Text überschreitet das Größenlimit")
    if code == 1:
        return _decode_utf16_message(raw, byte_order, encoding)
    unit = 1 if code == 0 else 4
    return _decode_plain(raw, encoding, unit)


def _parse_sections(data: bytes, byte_order: str, section_count: int,
                    declared_size: int) -> tuple[MsbtSection, ...]:
    sections: list[MsbtSection] = []
    p = 0x20
    hard_end = min(len(data), declared_size or len(data))
    for index in range(section_count):
        if p + 16 > hard_end:
            raise MsbtError(f"MSBT-Sektion {index} hat keinen vollständigen Header")
        raw_tag = data[p:p + 4]
        try:
            tag = raw_tag.decode("ascii")
        except UnicodeDecodeError as exc:
            raise MsbtError(f"MSBT-Sektion {index} hat keinen ASCII-Tag") from exc
        size = _uint(data, p + 4, 4, byte_order, f"Größe der Sektion {tag}")
        if size > _MAX_SECTION_BYTES:
            raise MsbtError(f"MSBT-Sektion {tag} überschreitet das Größenlimit")
        start = p + 16
        end = start + size
        if end > hard_end:
            raise MsbtError(f"MSBT-Sektion {tag} läuft über das Dateiende")
        sections.append(MsbtSection(tag, p, size, bytes(data[start:end])))
        p = _align(end)
    return tuple(sections)


def _section_map(sections: tuple[MsbtSection, ...]) -> dict[str, MsbtSection]:
    result = {}
    for section in sections:
        result.setdefault(section.tag, section)
    return result


def _parse_labels(section: MsbtSection | None, byte_order: str) -> dict[int, str]:
    if section is None:
        return {}
    data = section.data
    bucket_count = _uint(data, 0, 4, byte_order, "LBL1-Bucket-Zähler")
    if bucket_count > _MAX_MESSAGES:
        raise MsbtError("LBL1 enthält zu viele Buckets")
    table_end = 4 + bucket_count * 8
    if table_end > len(data):
        raise MsbtError("LBL1-Bucket-Tabelle ist abgeschnitten")
    labels: dict[int, str] = {}
    for bucket in range(bucket_count):
        count = _uint(data, 4 + bucket * 8, 4, byte_order, "LBL1-Label-Zähler")
        offset = _uint(data, 8 + bucket * 8, 4, byte_order, "LBL1-Bucket-Offset")
        if count > _MAX_MESSAGES or offset < table_end or offset > len(data):
            raise MsbtError("LBL1-Bucket besitzt ungültige Grenzen")
        p = offset
        for _ in range(count):
            if p >= len(data):
                raise MsbtError("LBL1-Label ist abgeschnitten")
            length = data[p]
            p += 1
            if length > _MAX_LABEL_BYTES or p + length + 4 > len(data):
                raise MsbtError("LBL1-Label besitzt eine ungültige Länge")
            label = data[p:p + length].decode("utf-8", "replace")
            p += length
            index = _uint(data, p, 4, byte_order, "LBL1-Nachrichtenindex")
            p += 4
            if index >= _MAX_MESSAGES:
                raise MsbtError("LBL1-Nachrichtenindex überschreitet das Limit")
            labels[index] = label
    return labels


def _parse_texts(section: MsbtSection | None, byte_order: str, code: int,
                 encoding: str) -> tuple[str, ...]:
    if section is None:
        return ()
    data = section.data
    count = _uint(data, 0, 4, byte_order, "TXT2-Nachrichtenzähler")
    if count > _MAX_MESSAGES:
        raise MsbtError("TXT2 enthält zu viele Nachrichten")
    table_end = 4 + count * 4
    if table_end > len(data):
        raise MsbtError("TXT2-Offsettabelle ist abgeschnitten")
    offsets = [
        _uint(data, 4 + index * 4, 4, byte_order, "TXT2-Nachrichtenoffset")
        for index in range(count)
    ]
    for offset in offsets:
        if offset < table_end or offset > len(data):
            raise MsbtError("TXT2-Nachrichtenoffset liegt außerhalb der Sektion")
    texts = []
    for index, start in enumerate(offsets):
        limit = offsets[index + 1] if index + 1 < len(offsets) else len(data)
        if limit < start:
            raise MsbtError("TXT2-Nachrichtenoffsets sind nicht aufsteigend")
        texts.append(_decode_message(data, start, limit, code, byte_order, encoding))
    return tuple(texts)


def _parse_attributes(section: MsbtSection | None, byte_order: str,
                      count: int) -> tuple[bytes, ...]:
    if section is None or not section.data:
        return tuple(b"" for _ in range(count))
    data = section.data
    declared = _uint(data, 0, 4, byte_order, "ATR1-Nachrichtenzähler")
    entry_size = _uint(data, 4, 4, byte_order, "ATR1-Eintragsgröße") if len(data) >= 8 else 0
    if declared > _MAX_MESSAGES:
        raise MsbtError("ATR1 enthält zu viele Einträge")
    if entry_size == 0:
        return tuple(b"" for _ in range(count))
    end = 8 + declared * entry_size
    if end > len(data):
        raise MsbtError("ATR1-Einträge sind abgeschnitten")
    values = [bytes(data[8 + index * entry_size:8 + (index + 1) * entry_size])
              for index in range(declared)]
    if len(values) < count:
        values.extend(b"" for _ in range(count - len(values)))
    return tuple(values[:count])


def parse_msbt(data: bytes) -> MsbtDocument:
    data = bytes(data)
    if len(data) < 0x20 or data[:8] != b"MsgStdBn":
        raise MsbtError("Keine gültige MSBT-Datei mit MsgStdBn-Header")
    bom = data[8:10]
    if bom == b"\xff\xfe":
        byte_order = "little"
    elif bom == b"\xfe\xff":
        byte_order = "big"
    else:
        raise MsbtError("MSBT besitzt keine unterstützte Byte-Order-Markierung")
    encoding_code = data[12]
    encoding = _encoding_name(encoding_code, byte_order)
    version = data[13]
    section_count = _uint(data, 14, 2, byte_order, "MSBT-Sektionszähler")
    if not (1 <= section_count <= _MAX_SECTIONS):
        raise MsbtError(f"Unplausible MSBT-Sektionszahl {section_count}")
    declared_size = _uint(data, 18, 4, byte_order, "MSBT-Dateigröße")
    if declared_size and (declared_size < 0x20 or declared_size > len(data)):
        raise MsbtError("MSBT-Dateigröße liegt außerhalb der Ressource")
    sections = _parse_sections(data, byte_order, section_count, declared_size)
    by_tag = _section_map(sections)
    labels = _parse_labels(by_tag.get("LBL1"), byte_order)
    texts = _parse_texts(by_tag.get("TXT2"), byte_order, encoding_code, encoding)
    attributes = _parse_attributes(by_tag.get("ATR1"), byte_order, len(texts))
    messages = tuple(
        MsbtMessage(index, labels.get(index, f"#{index}"), text,
                    attributes[index] if index < len(attributes) else b"")
        for index, text in enumerate(texts)
    )
    return MsbtDocument(
        byte_order=byte_order,
        encoding=encoding,
        encoding_code=encoding_code,
        version=version,
        file_size=declared_size or len(data),
        sections=sections,
        messages=messages,
    )
