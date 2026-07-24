"""Function, control-flow and callgraph analysis for the PAKPY ExeFS Lab."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from exefs_arm64 import Arm64Instruction, decode_word
from exefs_nso import DEFAULT_RUNTIME_BASE, NsoError, NsoImage


@dataclass(frozen=True)
class CallSite:
    memory_offset: int
    target: int


@dataclass(frozen=True)
class MemoryAccess:
    memory_offset: int
    mnemonic: str
    register: int
    base_register: int
    displacement: int
    width: int
    is_load: bool

    def format_line(self) -> str:
        data_reg = ("x" if self.width == 8 else "w") + str(self.register)
        base = "sp" if self.base_register == 31 else f"x{self.base_register}"
        sign = "-" if self.displacement < 0 else ""
        amount = abs(self.displacement)
        address = f"[{base}]" if amount == 0 else f"[{base}, #{sign}0x{amount:X}]"
        return f"0x{self.memory_offset:X}: {self.mnemonic} {data_reg}, {address}"


@dataclass(frozen=True)
class FunctionSummary:
    start: int
    end: int
    instructions: tuple[Arm64Instruction, ...]
    basic_block_starts: tuple[int, ...]
    calls: tuple[CallSite, ...]
    called_by: tuple[CallSite, ...]
    branch_targets: tuple[int, ...]
    returns: tuple[int, ...]
    truncated: bool = False

    @property
    def size(self) -> int:
        return self.end - self.start

    def format_lines(self) -> list[str]:
        lines = [
            f"Funktion: 0x{self.start:X}–0x{self.end:X}",
            f"Größe: 0x{self.size:X} ({self.size} Bytes)",
            f"Instruktionen: {len(self.instructions)}",
            f"Basic Blocks: {len(self.basic_block_starts)}",
            f"Direkte Calls: {len(self.calls)}",
            f"Direkte Aufrufer: {len(self.called_by)}",
            f"Returns: {len(self.returns)}",
            f"Abgeschnitten: {'ja' if self.truncated else 'nein'}",
            "",
            "Calls:",
        ]
        lines.extend(
            f"  0x{item.memory_offset:X} -> 0x{item.target:X}" for item in self.calls
        )
        if not self.calls:
            lines.append("  —")
        lines.extend(["", "Called by:"])
        lines.extend(
            f"  0x{item.memory_offset:X} -> 0x{item.target:X}" for item in self.called_by
        )
        if not self.called_by:
            lines.append("  —")
        lines.extend(["", "Basic-Block-Starts:"])
        lines.append("  " + ", ".join(f"0x{x:X}" for x in self.basic_block_starts))
        return lines


def scan_direct_calls(image: NsoImage) -> tuple[CallSite, ...]:
    text_segment = image.segment("text")
    text = image.read_segment("text")
    result = []
    for offset in range(0, len(text) - 3, 4):
        word = int.from_bytes(text[offset:offset + 4], "little")
        if ((word >> 26) & 0x3F) != 0b100101:
            continue
        address = text_segment.memory_offset + offset
        displacement = _sign_extend(word & 0x03FFFFFF, 26) << 2
        target = (address + displacement) & 0xFFFFFFFFFFFFFFFF
        result.append(CallSite(address, target))
    return tuple(result)


def direct_callers(image: NsoImage, target: int) -> tuple[CallSite, ...]:
    value = int(target)
    return tuple(item for item in scan_direct_calls(image) if item.target == value)


def analyze_function(
    image: NsoImage,
    start: int,
    max_instructions: int = 4096,
    runtime_base: int = DEFAULT_RUNTIME_BASE,
    calls_index: Optional[tuple[CallSite, ...]] = None,
) -> FunctionSummary:
    text_segment = image.segment("text")
    text = image.read_segment("text")
    entry = int(start)
    if entry % 4:
        raise NsoError(f"Funktionsstart muss 4-Byte-ausgerichtet sein: 0x{entry:X}")
    if not text_segment.contains_memory_offset(entry):
        raise NsoError(f"Funktionsstart 0x{entry:X} liegt nicht im text-Segment")
    if max_instructions <= 0:
        raise NsoError("Maximale Instruktionsanzahl muss größer als null sein")

    pending = [entry]
    block_starts = {entry}
    decoded: dict[int, Arm64Instruction] = {}
    calls: list[CallSite] = []
    branch_targets = set()
    returns = set()
    truncated = False

    while pending:
        block = pending.pop()
        address = block
        while text_segment.contains_memory_offset(address):
            if address in decoded:
                break
            if len(decoded) >= max_instructions:
                truncated = True
                pending.clear()
                break
            local = address - text_segment.memory_offset
            raw = text[local:local + 4]
            if len(raw) != 4:
                break
            word = int.from_bytes(raw, "little")
            mnemonic, operands, target, is_call, is_return = decode_word(word, address)
            instruction = Arm64Instruction(
                memory_offset=address,
                runtime_address=runtime_base + address,
                segment_offset=local,
                raw=raw,
                word=word,
                mnemonic=mnemonic,
                operands=operands,
                branch_target=target,
                is_call=is_call,
                is_return=is_return,
                backend="builtin",
            )
            decoded[address] = instruction

            if is_call and target is not None:
                calls.append(CallSite(address, target))
                address += 4
                continue
            if is_return:
                returns.add(address)
                break
            if mnemonic in ("br", "blr"):
                break
            if target is not None and _is_branch_mnemonic(mnemonic):
                branch_targets.add(target)
                if text_segment.contains_memory_offset(target):
                    block_starts.add(target)
                    if target not in decoded:
                        pending.append(target)
                if mnemonic == "b":
                    break
                fallthrough = address + 4
                if text_segment.contains_memory_offset(fallthrough):
                    block_starts.add(fallthrough)
                    if fallthrough not in decoded:
                        pending.append(fallthrough)
                break
            address += 4

    instructions = tuple(decoded[address] for address in sorted(decoded))
    end = max(decoded) + 4 if decoded else entry
    all_calls = calls_index if calls_index is not None else scan_direct_calls(image)
    called_by = tuple(item for item in all_calls if item.target == entry)
    unique_calls = tuple(sorted(set(calls), key=lambda item: (item.memory_offset, item.target)))
    return FunctionSummary(
        start=entry,
        end=end,
        instructions=instructions,
        basic_block_starts=tuple(sorted(block_starts & set(decoded))),
        calls=unique_calls,
        called_by=called_by,
        branch_targets=tuple(sorted(branch_targets)),
        returns=tuple(sorted(returns)),
        truncated=truncated,
    )


def scan_memory_accesses(
    image: NsoImage,
    displacement: Optional[int] = None,
) -> tuple[MemoryAccess, ...]:
    text_segment = image.segment("text")
    text = image.read_segment("text")
    result = []
    for offset in range(0, len(text) - 3, 4):
        word = int.from_bytes(text[offset:offset + 4], "little")
        address = text_segment.memory_offset + offset
        decoded = _decode_memory_access(word, address)
        if decoded is None:
            continue
        if displacement is not None and decoded.displacement != displacement:
            continue
        result.append(decoded)
    return tuple(result)


def _decode_memory_access(word: int, address: int) -> Optional[MemoryAccess]:
    if (word & 0x3B000000) == 0x39000000 and not ((word >> 26) & 1):
        size = (word >> 30) & 3
        opc = (word >> 22) & 3
        imm = ((word >> 10) & 0xFFF) * (1 << size)
        rn = (word >> 5) & 31
        rt = word & 31
        width = 1 << size
        if opc == 0:
            mnemonic = ("strb", "strh", "str", "str")[size]
            load = False
        elif opc == 1:
            mnemonic = ("ldrb", "ldrh", "ldr", "ldr")[size]
            load = True
        elif opc == 2 and size in (2, 3):
            mnemonic = "ldrsw"
            load = True
            width = 4
        else:
            return None
        return MemoryAccess(address, mnemonic, rt, rn, imm, width, load)

    if (word & 0x3B200000) == 0x38000000 and not ((word >> 26) & 1):
        size = (word >> 30) & 3
        opc = (word >> 22) & 3
        imm = _sign_extend((word >> 12) & 0x1FF, 9)
        rn = (word >> 5) & 31
        rt = word & 31
        width = 1 << size
        if opc == 0:
            mnemonic = ("sturb", "sturh", "stur", "stur")[size]
            load = False
        elif opc == 1:
            mnemonic = ("ldurb", "ldurh", "ldur", "ldur")[size]
            load = True
        else:
            return None
        return MemoryAccess(address, mnemonic, rt, rn, imm, width, load)
    return None


def _is_branch_mnemonic(mnemonic: str) -> bool:
    return (
        mnemonic == "b"
        or mnemonic.startswith("b.")
        or mnemonic in ("cbz", "cbnz", "tbz", "tbnz")
    )


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)
