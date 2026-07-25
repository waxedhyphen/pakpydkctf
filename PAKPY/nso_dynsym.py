from __future__ import annotations

import argparse
import struct
from dataclasses import dataclass
from pathlib import Path

import lz4.block


class NsoError(ValueError):
    pass


@dataclass(frozen=True)
class NsoSymbol:
    name: str
    value: int
    size: int
    info: int
    other: int
    section_index: int


@dataclass(frozen=True)
class NsoImage:
    memory: bytes
    symbols: tuple[NsoSymbol, ...]


_SEGMENT_HEADERS = (0x10, 0x20, 0x30)
_COMPRESSED_SIZE_OFFSETS = (0x60, 0x64, 0x68)
_DT_NULL = 0
_DT_HASH = 4
_DT_STRTAB = 5
_DT_SYMTAB = 6
_DT_SYMENT = 11


def _u32(data: bytes, offset: int) -> int:
    if offset < 0 or offset + 4 > len(data):
        raise NsoError(f"u32 outside file at 0x{offset:X}")
    return struct.unpack_from("<I", data, offset)[0]


def _segment(data: bytes, index: int, flags: int) -> tuple[int, bytes]:
    header = _SEGMENT_HEADERS[index]
    file_offset, memory_offset, memory_size = struct.unpack_from("<III", data, header)
    compressed_size = _u32(data, _COMPRESSED_SIZE_OFFSETS[index])
    end = file_offset + compressed_size
    if end > len(data):
        raise NsoError(f"segment {index} extends beyond file")
    source = data[file_offset:end]
    if flags & (1 << index):
        try:
            decoded = lz4.block.decompress(source, uncompressed_size=memory_size)
        except Exception as exc:  # lz4 exposes implementation-specific exceptions
            raise NsoError(f"segment {index} LZ4 decode failed: {exc}") from exc
    else:
        decoded = source[:memory_size]
    if len(decoded) != memory_size:
        raise NsoError(
            f"segment {index} decoded size {len(decoded)} != expected {memory_size}"
        )
    return memory_offset, decoded


def _read_c_string(memory: bytes, offset: int) -> str:
    if offset < 0 or offset >= len(memory):
        raise NsoError(f"string offset outside image: 0x{offset:X}")
    end = memory.find(b"\0", offset)
    if end < 0:
        raise NsoError(f"unterminated string at 0x{offset:X}")
    return memory[offset:end].decode("utf-8", errors="strict")


def load_nso(path: Path) -> NsoImage:
    raw = path.read_bytes()
    if len(raw) < 0x6C or raw[:4] != b"NSO0":
        raise NsoError("not an NSO0 file")

    flags = _u32(raw, 0x0C)
    segments = [_segment(raw, index, flags) for index in range(3)]
    image_size = max(offset + len(segment) for offset, segment in segments)
    memory = bytearray(image_size)
    for offset, segment in segments:
        memory[offset : offset + len(segment)] = segment

    module_offset = _u32(memory, 4)
    if memory[module_offset : module_offset + 4] != b"MOD0":
        raise NsoError(f"MOD0 not found at declared offset 0x{module_offset:X}")

    dynamic_offset = module_offset + _u32(memory, module_offset + 4)
    dynamic: dict[int, int] = {}
    cursor = dynamic_offset
    while True:
        if cursor + 16 > len(memory):
            raise NsoError("dynamic table extends beyond image")
        tag, value = struct.unpack_from("<QQ", memory, cursor)
        cursor += 16
        if tag == _DT_NULL:
            break
        dynamic[tag] = value

    for required in (_DT_HASH, _DT_STRTAB, _DT_SYMTAB):
        if required not in dynamic:
            raise NsoError(f"dynamic tag {required} missing")

    hash_offset = dynamic[_DT_HASH]
    if hash_offset + 8 > len(memory):
        raise NsoError("SysV hash header outside image")
    _bucket_count, symbol_count = struct.unpack_from("<II", memory, hash_offset)
    symbol_size = dynamic.get(_DT_SYMENT, 24)
    if symbol_size != 24:
        raise NsoError(f"unsupported ELF64 symbol size {symbol_size}")

    symbol_table = dynamic[_DT_SYMTAB]
    string_table = dynamic[_DT_STRTAB]
    symbols: list[NsoSymbol] = []
    for index in range(symbol_count):
        offset = symbol_table + index * symbol_size
        if offset + symbol_size > len(memory):
            raise NsoError(f"symbol {index} outside image")
        name_offset, info, other, section_index, value, size = struct.unpack_from(
            "<IBBHQQ", memory, offset
        )
        if name_offset == 0:
            continue
        name = _read_c_string(memory, string_table + name_offset)
        symbols.append(
            NsoSymbol(
                name=name,
                value=value,
                size=size,
                info=info,
                other=other,
                section_index=section_index,
            )
        )

    return NsoImage(memory=bytes(memory), symbols=tuple(symbols))


def main() -> int:
    parser = argparse.ArgumentParser(description="Read symbols from a Nintendo Switch NSO")
    parser.add_argument("nso", type=Path)
    parser.add_argument("terms", nargs="*")
    args = parser.parse_args()

    image = load_nso(args.nso)
    terms = tuple(args.terms)
    for symbol in image.symbols:
        if terms and not any(term in symbol.name for term in terms):
            continue
        print(f"0x{symbol.value:08X} 0x{symbol.size:X} {symbol.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
