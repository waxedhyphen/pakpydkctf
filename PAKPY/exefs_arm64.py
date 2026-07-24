"""AArch64 disassembly support for PAKPY ExeFS Lab.

The module prefers Capstone when it is installed, but includes a dependency-free
baseline decoder for the control-flow, address-generation and load/store
instructions needed by the first ExeFS tracing stages. Unknown instructions are
kept visible as ``.word`` values instead of being silently skipped.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from exefs_nso import DEFAULT_RUNTIME_BASE, NsoError, NsoImage


CONDITION_NAMES = (
    "eq", "ne", "hs", "lo", "mi", "pl", "vs", "vc",
    "hi", "ls", "ge", "lt", "gt", "le", "al", "nv",
)


@dataclass(frozen=True)
class Arm64Instruction:
    memory_offset: int
    runtime_address: int
    segment_offset: int
    raw: bytes
    word: int
    mnemonic: str
    operands: str = ""
    branch_target: Optional[int] = None
    is_call: bool = False
    is_return: bool = False
    backend: str = "builtin"

    @property
    def bytes_hex(self) -> str:
        return self.raw.hex(" ").upper()

    def format_line(self, runtime: bool = False) -> str:
        address = self.runtime_address if runtime else self.memory_offset
        text = f"{address:012X}  {self.bytes_hex:<11}  {self.mnemonic:<9}"
        if self.operands:
            text += f" {self.operands}"
        if self.branch_target is not None:
            text += f"    ; -> 0x{self.branch_target:X}"
        return text.rstrip()


@dataclass(frozen=True)
class DisassemblyResult:
    start_memory_offset: int
    runtime_base: int
    backend: str
    instructions: tuple[Arm64Instruction, ...]
    note: str = ""

    def format_lines(self, runtime: bool = False) -> list[str]:
        lines = [
            f"Backend: {self.backend}",
            f"Start NSO-VA: 0x{self.start_memory_offset:X}",
            f"Runtime-Basis: 0x{self.runtime_base:X}",
        ]
        if self.note:
            lines.append(f"Hinweis: {self.note}")
        lines.append("")
        lines.extend(item.format_line(runtime=runtime) for item in self.instructions)
        return lines


def available_backend() -> str:
    try:
        import capstone  # noqa: F401
    except Exception:
        return "builtin"
    return "capstone"


def disassemble_image(
    image: NsoImage,
    start_memory_offset: int,
    instruction_count: int = 64,
    runtime_base: int = DEFAULT_RUNTIME_BASE,
    backend: str = "auto",
) -> DisassemblyResult:
    if instruction_count <= 0:
        raise NsoError("Instruktionsanzahl muss größer als null sein")
    if instruction_count > 100000:
        raise NsoError("Instruktionsanzahl ist zu groß")
    text_segment = image.segment("text")
    start = int(start_memory_offset)
    if start % 4:
        raise NsoError(f"ARM64-Adresse muss 4-Byte-ausgerichtet sein: 0x{start:X}")
    if not text_segment.contains_memory_offset(start):
        raise NsoError(
            f"NSO-VA 0x{start:X} liegt nicht im text-Segment "
            f"0x{text_segment.memory_offset:X}–0x{text_segment.memory_end:X}"
        )
    offset = start - text_segment.memory_offset
    requested_size = instruction_count * 4
    text = image.read_segment("text")
    payload = text[offset:offset + requested_size]
    if not payload:
        raise NsoError("An der gewählten Adresse sind keine text-Bytes vorhanden")
    payload = payload[:len(payload) - (len(payload) % 4)]

    selected = available_backend() if backend == "auto" else backend.lower()
    if selected == "capstone":
        try:
            instructions = tuple(
                _disassemble_capstone(payload, start, offset, runtime_base)
            )
            note = "Capstone liefert vollständige AArch64-Mnemonics und Operanden."
        except ImportError:
            if backend != "auto":
                raise NsoError(
                    "Capstone ist nicht installiert. Installieren mit: python -m pip install capstone"
                )
            selected = "builtin"
            instructions = tuple(
                _disassemble_builtin(payload, start, offset, runtime_base)
            )
            note = _builtin_note()
    elif selected == "builtin":
        instructions = tuple(_disassemble_builtin(payload, start, offset, runtime_base))
        note = _builtin_note()
    else:
        raise NsoError(f"Unbekannter ARM64-Backend: {backend}")

    return DisassemblyResult(
        start_memory_offset=start,
        runtime_base=runtime_base,
        backend=selected,
        instructions=instructions,
        note=note,
    )


def _builtin_note() -> str:
    return (
        "Der eingebaute Decoder deckt Kontrollfluss, ADR/ADRP, Immediate-Arithmetik, "
        "Move-Wide sowie häufige Load/Store-Formen ab. Nicht erkannte Befehle bleiben "
        "als .word sichtbar. Für vollständige Disassembly kann Capstone installiert werden."
    )


def _disassemble_capstone(
    payload: bytes,
    start_memory_offset: int,
    segment_offset: int,
    runtime_base: int,
) -> Iterable[Arm64Instruction]:
    try:
        from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
        from capstone.arm64 import ARM64_GRP_CALL, ARM64_GRP_JUMP, ARM64_GRP_RET
    except Exception as exc:
        raise ImportError from exc

    engine = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    engine.detail = True
    decoded_end = 0
    for item in engine.disasm(payload, start_memory_offset):
        local = item.address - start_memory_offset
        while decoded_end < local:
            raw = payload[decoded_end:decoded_end + 4]
            address = start_memory_offset + decoded_end
            yield _unknown_instruction(raw, address, segment_offset + decoded_end, runtime_base, "capstone")
            decoded_end += 4
        raw = bytes(item.bytes)
        target = None
        if item.group(ARM64_GRP_JUMP) or item.group(ARM64_GRP_CALL):
            for operand in item.operands:
                if getattr(operand, "type", None) == 2:  # ARM64_OP_IMM
                    target = int(operand.imm)
                    break
        yield Arm64Instruction(
            memory_offset=int(item.address),
            runtime_address=runtime_base + int(item.address),
            segment_offset=segment_offset + local,
            raw=raw,
            word=int.from_bytes(raw, "little"),
            mnemonic=item.mnemonic,
            operands=item.op_str,
            branch_target=target,
            is_call=bool(item.group(ARM64_GRP_CALL)),
            is_return=bool(item.group(ARM64_GRP_RET)),
            backend="capstone",
        )
        decoded_end = local + len(raw)
    while decoded_end < len(payload):
        raw = payload[decoded_end:decoded_end + 4]
        address = start_memory_offset + decoded_end
        yield _unknown_instruction(raw, address, segment_offset + decoded_end, runtime_base, "capstone")
        decoded_end += 4


def _disassemble_builtin(
    payload: bytes,
    start_memory_offset: int,
    segment_offset: int,
    runtime_base: int,
) -> Iterable[Arm64Instruction]:
    for local in range(0, len(payload), 4):
        raw = payload[local:local + 4]
        address = start_memory_offset + local
        word = int.from_bytes(raw, "little")
        mnemonic, operands, target, is_call, is_return = decode_word(word, address)
        yield Arm64Instruction(
            memory_offset=address,
            runtime_address=runtime_base + address,
            segment_offset=segment_offset + local,
            raw=raw,
            word=word,
            mnemonic=mnemonic,
            operands=operands,
            branch_target=target,
            is_call=is_call,
            is_return=is_return,
            backend="builtin",
        )


def _unknown_instruction(raw: bytes, address: int, segment_offset: int, runtime_base: int, backend: str) -> Arm64Instruction:
    word = int.from_bytes(raw.ljust(4, b"\0"), "little")
    return Arm64Instruction(
        memory_offset=address,
        runtime_address=runtime_base + address,
        segment_offset=segment_offset,
        raw=raw,
        word=word,
        mnemonic=".word",
        operands=f"0x{word:08X}",
        backend=backend,
    )


def decode_word(word: int, address: int) -> tuple[str, str, Optional[int], bool, bool]:
    word &= 0xFFFFFFFF

    if word == 0xD503201F:
        return "nop", "", None, False, False

    if (word & 0xFFFFFC1F) == 0xD65F0000:
        rn = (word >> 5) & 31
        operands = "" if rn == 30 else _xreg(rn)
        return "ret", operands, None, False, True
    if (word & 0xFFFFFC1F) == 0xD61F0000:
        return "br", _xreg((word >> 5) & 31), None, False, False
    if (word & 0xFFFFFC1F) == 0xD63F0000:
        return "blr", _xreg((word >> 5) & 31), None, True, False

    opcode6 = (word >> 26) & 0x3F
    if opcode6 in (0b000101, 0b100101):
        displacement = _sign_extend(word & 0x03FFFFFF, 26) << 2
        target = (address + displacement) & 0xFFFFFFFFFFFFFFFF
        is_call = opcode6 == 0b100101
        return ("bl" if is_call else "b"), f"0x{target:X}", target, is_call, False

    if (word & 0xFF000010) == 0x54000000:
        displacement = _sign_extend((word >> 5) & 0x7FFFF, 19) << 2
        target = (address + displacement) & 0xFFFFFFFFFFFFFFFF
        condition = CONDITION_NAMES[word & 0xF]
        return f"b.{condition}", f"0x{target:X}", target, False, False

    if (word & 0x7E000000) == 0x34000000:
        sf = (word >> 31) & 1
        nonzero = (word >> 24) & 1
        displacement = _sign_extend((word >> 5) & 0x7FFFF, 19) << 2
        target = (address + displacement) & 0xFFFFFFFFFFFFFFFF
        reg = _reg(word & 31, sf)
        return ("cbnz" if nonzero else "cbz"), f"{reg}, 0x{target:X}", target, False, False

    if (word & 0x7E000000) == 0x36000000:
        nonzero = (word >> 24) & 1
        bit = (((word >> 31) & 1) << 5) | ((word >> 19) & 0x1F)
        displacement = _sign_extend((word >> 5) & 0x3FFF, 14) << 2
        target = (address + displacement) & 0xFFFFFFFFFFFFFFFF
        reg = _reg(word & 31, 1 if bit >= 32 else 0)
        return ("tbnz" if nonzero else "tbz"), f"{reg}, #{bit}, 0x{target:X}", target, False, False

    if (word & 0x1F000000) == 0x10000000:
        page = bool((word >> 31) & 1)
        immlo = (word >> 29) & 0x3
        immhi = (word >> 5) & 0x7FFFF
        immediate = _sign_extend((immhi << 2) | immlo, 21)
        rd = word & 31
        if page:
            target = ((address & ~0xFFF) + (immediate << 12)) & 0xFFFFFFFFFFFFFFFF
            return "adrp", f"{_xreg(rd)}, 0x{target:X}", target, False, False
        target = (address + immediate) & 0xFFFFFFFFFFFFFFFF
        return "adr", f"{_xreg(rd)}, 0x{target:X}", target, False, False

    if (word & 0x1F000000) == 0x11000000:
        sf = (word >> 31) & 1
        subtract = (word >> 30) & 1
        set_flags = (word >> 29) & 1
        shift = 12 if ((word >> 22) & 1) else 0
        immediate = ((word >> 10) & 0xFFF) << shift
        rn = (word >> 5) & 31
        rd = word & 31
        if set_flags and rd == 31:
            mnemonic = "cmp" if subtract else "cmn"
            return mnemonic, f"{_reg(rn, sf, sp=True)}, #{_fmt_imm(immediate)}", None, False, False
        mnemonic = ("sub" if subtract else "add") + ("s" if set_flags else "")
        return mnemonic, f"{_reg(rd, sf, sp=True)}, {_reg(rn, sf, sp=True)}, #{_fmt_imm(immediate)}", None, False, False

    if (word & 0x1F200000) == 0x0A000000:
        sf = (word >> 31) & 1
        opc = (word >> 29) & 0x3
        invert = (word >> 21) & 1
        shift_type = (word >> 22) & 0x3
        rm = (word >> 16) & 31
        amount = (word >> 10) & 0x3F
        rn = (word >> 5) & 31
        rd = word & 31
        names = {0: "and", 1: "orr", 2: "eor", 3: "ands"}
        mnemonic = names[opc]
        if invert:
            mnemonic = {0: "bic", 1: "orn", 2: "eon", 3: "bics"}[opc]
        if mnemonic == "orr" and rn == 31 and shift_type == 0 and amount == 0:
            return "mov", f"{_reg(rd, sf)}, {_reg(rm, sf)}", None, False, False
        shifts = ("lsl", "lsr", "asr", "ror")
        operands = f"{_reg(rd, sf)}, {_reg(rn, sf)}, {_reg(rm, sf)}"
        if amount or shift_type:
            operands += f", {shifts[shift_type]} #{amount}"
        return mnemonic, operands, None, False, False

    if (word & 0x1F200000) == 0x0B000000:
        sf = (word >> 31) & 1
        subtract = (word >> 30) & 1
        set_flags = (word >> 29) & 1
        shift_type = (word >> 22) & 0x3
        rm = (word >> 16) & 31
        amount = (word >> 10) & 0x3F
        rn = (word >> 5) & 31
        rd = word & 31
        if set_flags and rd == 31:
            mnemonic = "cmp" if subtract else "cmn"
            operands = f"{_reg(rn, sf)}, {_reg(rm, sf)}"
        else:
            mnemonic = ("sub" if subtract else "add") + ("s" if set_flags else "")
            operands = f"{_reg(rd, sf)}, {_reg(rn, sf)}, {_reg(rm, sf)}"
        if amount or shift_type:
            operands += f", {('lsl', 'lsr', 'asr', 'reserved')[shift_type]} #{amount}"
        return mnemonic, operands, None, False, False

    if (word & 0x1F800000) == 0x12000000:
        sf = (word >> 31) & 1
        opc = (word >> 29) & 0x3
        immediate = _decode_logical_immediate(word, 64 if sf else 32)
        if immediate is not None:
            rn = (word >> 5) & 31
            rd = word & 31
            mnemonic = ("and", "orr", "eor", "ands")[opc]
            if mnemonic == "orr" and rn == 31:
                return "mov", f"{_reg(rd, sf)}, #0x{immediate:X}", None, False, False
            if mnemonic == "ands" and rd == 31:
                return "tst", f"{_reg(rn, sf)}, #0x{immediate:X}", None, False, False
            return mnemonic, f"{_reg(rd, sf)}, {_reg(rn, sf)}, #0x{immediate:X}", None, False, False

    if (word & 0x1F800000) == 0x12800000:
        sf = (word >> 31) & 1
        opc = (word >> 29) & 0x3
        hw = (word >> 21) & 0x3
        imm16 = (word >> 5) & 0xFFFF
        rd = word & 31
        names = {0: "movn", 2: "movz", 3: "movk"}
        mnemonic = names.get(opc)
        if mnemonic is not None and (sf or hw < 2):
            operands = f"{_reg(rd, sf)}, #0x{imm16:X}"
            if hw:
                operands += f", lsl #{hw * 16}"
            return mnemonic, operands, None, False, False

    if (word & 0x3B000000) == 0x18000000:
        opc = (word >> 30) & 0x3
        vector = (word >> 26) & 1
        displacement = _sign_extend((word >> 5) & 0x7FFFF, 19) << 2
        target = (address + displacement) & 0xFFFFFFFFFFFFFFFF
        rt = word & 31
        if vector:
            suffix = ("s", "d", "q", "?")[opc]
            return "ldr", f"{suffix}{rt}, 0x{target:X}", target, False, False
        if opc == 0:
            reg = _wreg(rt)
            mnemonic = "ldr"
        elif opc == 1:
            reg = _xreg(rt)
            mnemonic = "ldr"
        elif opc == 2:
            reg = _xreg(rt)
            mnemonic = "ldrsw"
        else:
            return "prfm", f"#{rt}, 0x{target:X}", target, False, False
        return mnemonic, f"{reg}, 0x{target:X}", target, False, False

    pair = _decode_load_store_pair(word)
    if pair is not None:
        return pair

    unsigned = _decode_load_store_unsigned(word)
    if unsigned is not None:
        return unsigned

    return ".word", f"0x{word:08X}", None, False, False


def _decode_load_store_pair(word: int):
    if (word & 0x3A000000) != 0x28000000:
        return None
    vector = (word >> 26) & 1
    if vector:
        return None
    opc = (word >> 30) & 0x3
    if opc not in (0, 2):
        return None
    load = (word >> 22) & 1
    mode = (word >> 23) & 0x3
    imm7 = _sign_extend((word >> 15) & 0x7F, 7)
    rt2 = (word >> 10) & 31
    rn = (word >> 5) & 31
    rt = word & 31
    sf = 1 if opc == 2 else 0
    scale = 8 if sf else 4
    immediate = imm7 * scale
    base = _xreg(rn, sp=True)
    address = f"[{base}"
    if mode == 1:  # post-index
        address += f"], #{_fmt_signed_imm(immediate)}"
    elif mode == 3:  # pre-index
        address += f", #{_fmt_signed_imm(immediate)}]!"
    else:  # signed offset / non-temporal
        if immediate:
            address += f", #{_fmt_signed_imm(immediate)}"
        address += "]"
    return ("ldp" if load else "stp"), f"{_reg(rt, sf)}, {_reg(rt2, sf)}, {address}", None, False, False


def _decode_load_store_unsigned(word: int):
    if (word & 0x3B000000) != 0x39000000:
        return None
    vector = (word >> 26) & 1
    if vector:
        return None
    size = (word >> 30) & 0x3
    opc = (word >> 22) & 0x3
    imm12 = (word >> 10) & 0xFFF
    rn = (word >> 5) & 31
    rt = word & 31
    scale = 1 << size
    immediate = imm12 * scale
    base = _xreg(rn, sp=True)
    address = f"[{base}]" if immediate == 0 else f"[{base}, #0x{immediate:X}]"
    if opc == 0:
        names = ("strb", "strh", "str", "str")
        reg = _xreg(rt) if size == 3 else _wreg(rt)
        return names[size], f"{reg}, {address}", None, False, False
    if opc == 1:
        names = ("ldrb", "ldrh", "ldr", "ldr")
        reg = _xreg(rt) if size == 3 else _wreg(rt)
        return names[size], f"{reg}, {address}", None, False, False
    if opc == 2 and size in (2, 3):
        return "ldrsw", f"{_xreg(rt)}, {address}", None, False, False
    return None


def _decode_logical_immediate(word: int, width: int) -> Optional[int]:
    n = (word >> 22) & 1
    immr = (word >> 16) & 0x3F
    imms = (word >> 10) & 0x3F
    marker = (n << 6) | ((~imms) & 0x3F)
    if marker == 0:
        return None
    length = marker.bit_length() - 1
    element_size = 1 << length
    if element_size > width:
        return None
    levels = element_size - 1
    s = imms & levels
    r = immr & levels
    if s == levels:
        return None
    element = (1 << (s + 1)) - 1
    element = _rotate_right(element, r, element_size)
    value = 0
    for shift in range(0, width, element_size):
        value |= element << shift
    return value


def _rotate_right(value: int, amount: int, width: int) -> int:
    amount %= width
    mask = (1 << width) - 1
    return ((value >> amount) | (value << (width - amount))) & mask


def _reg(index: int, sf: int, sp: bool = False) -> str:
    return _xreg(index, sp=sp) if sf else _wreg(index, sp=sp)


def _xreg(index: int, sp: bool = False) -> str:
    if index == 31:
        return "sp" if sp else "xzr"
    return f"x{index}"


def _wreg(index: int, sp: bool = False) -> str:
    if index == 31:
        return "wsp" if sp else "wzr"
    return f"w{index}"


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)


def _fmt_imm(value: int) -> str:
    return str(value) if value < 10 else f"0x{value:X}"


def _fmt_signed_imm(value: int) -> str:
    if value < 0:
        return f"-0x{-value:X}"
    return f"0x{value:X}" if value >= 10 else str(value)
