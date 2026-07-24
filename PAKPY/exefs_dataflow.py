"""Small local register/constant tracer for ARM64 functions.

This is intentionally not a decompiler. It follows simple values through MOV,
ADR/ADRP, ADD/SUB, MOVZ/MOVK and immediate memory accesses, and annotates CMP
plus the following conditional branch. The primary goal is to expose facts such
as ``load32(arg0 + 0x840) == 2`` without inventing source-level names.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from exefs_functions import FunctionSummary, MemoryAccess, _decode_memory_access


@dataclass(frozen=True)
class ValueExpr:
    text: str
    constant: Optional[int] = None


@dataclass(frozen=True)
class ConditionTrace:
    compare_address: int
    branch_address: Optional[int]
    relation: str
    left: str
    right: str
    branch_target: Optional[int]

    def format_line(self) -> str:
        location = f"0x{self.compare_address:X}"
        if self.branch_address is not None:
            location += f" / branch 0x{self.branch_address:X}"
        target = "" if self.branch_target is None else f" -> 0x{self.branch_target:X}"
        return f"{location}: {self.left} {self.relation} {self.right}{target}"


@dataclass(frozen=True)
class DataflowResult:
    function_start: int
    conditions: tuple[ConditionTrace, ...]
    memory_accesses: tuple[tuple[MemoryAccess, str], ...]

    def format_lines(self) -> list[str]:
        lines = [f"Lokaler Datenfluss ab 0x{self.function_start:X}", "", "Bedingungen:"]
        lines.extend(f"  {item.format_line()}" for item in self.conditions)
        if not self.conditions:
            lines.append("  —")
        lines.extend(["", "Speicherzugriffe:"])
        for access, expression in self.memory_accesses:
            lines.append(f"  0x{access.memory_offset:X}: {access.mnemonic} {expression}")
        if not self.memory_accesses:
            lines.append("  —")
        return lines


def trace_function(summary: FunctionSummary) -> DataflowResult:
    registers: dict[int, ValueExpr] = {
        index: ValueExpr(f"arg{index}") for index in range(8)
    }
    conditions = []
    memory_accesses = []
    last_compare: Optional[tuple[int, str, str]] = None

    for instruction in summary.instructions:
        word = instruction.word
        address = instruction.memory_offset

        branch_relation = _branch_relation(instruction.mnemonic)
        if branch_relation is not None and last_compare is not None:
            compare_address, left, right = last_compare
            conditions.append(
                ConditionTrace(
                    compare_address=compare_address,
                    branch_address=address,
                    relation=branch_relation,
                    left=left,
                    right=right,
                    branch_target=instruction.branch_target,
                )
            )
            last_compare = None

        mov = _decode_mov_register(word)
        if mov is not None:
            rd, rn = mov
            registers[rd] = registers.get(rn, ValueExpr(f"reg{rn}"))
            continue

        adr = _decode_adr(word, address)
        if adr is not None:
            rd, target = adr
            registers[rd] = ValueExpr(f"0x{target:X}", target)
            continue

        add = _decode_add_sub_immediate(word)
        if add is not None:
            rd, rn, immediate, subtract, set_flags = add
            source = registers.get(rn, ValueExpr(f"reg{rn}"))
            value = -immediate if subtract else immediate
            text = _offset_expr(source.text, value)
            constant = None if source.constant is None else source.constant + value
            if set_flags and rd == 31:
                last_compare = (address, source.text, f"{immediate}")
            else:
                registers[rd] = ValueExpr(text, constant)
            continue

        wide = _decode_move_wide(word)
        if wide is not None:
            rd, value, keep = wide
            if keep:
                previous = registers.get(rd)
                if previous is not None and previous.constant is not None:
                    mask, shifted = value
                    constant = (previous.constant & ~mask) | shifted
                    registers[rd] = ValueExpr(f"0x{constant:X}", constant)
                else:
                    registers[rd] = ValueExpr("unknown")
            else:
                registers[rd] = ValueExpr(f"0x{value:X}", value)
            continue

        compare = _decode_compare_register(word)
        if compare is not None:
            rn, rm = compare
            left = registers.get(rn, ValueExpr(f"reg{rn}")).text
            right = registers.get(rm, ValueExpr(f"reg{rm}")).text
            last_compare = (address, left, right)
            continue

        access = _decode_memory_access(word, address)
        if access is not None:
            base = registers.get(access.base_register, ValueExpr(f"reg{access.base_register}"))
            location = _offset_expr(base.text, access.displacement)
            bits = access.width * 8
            if access.is_load:
                expression = f"load{bits}({location})"
                registers[access.register] = ValueExpr(expression)
            else:
                value = registers.get(access.register, ValueExpr(f"reg{access.register}")).text
                expression = f"store{bits}({location}, {value})"
            memory_accesses.append((access, expression))
            continue

        if instruction.is_call:
            for index in range(19):
                registers.pop(index, None)
            registers[0] = ValueExpr(
                "return(indirect)" if instruction.branch_target is None
                else f"return(0x{instruction.branch_target:X})"
            )

    return DataflowResult(
        function_start=summary.start,
        conditions=tuple(conditions),
        memory_accesses=tuple(memory_accesses),
    )


def _decode_mov_register(word: int):
    if (word & 0x1F200000) != 0x0A000000:
        return None
    opc = (word >> 29) & 3
    invert = (word >> 21) & 1
    shift_type = (word >> 22) & 3
    amount = (word >> 10) & 0x3F
    rn = (word >> 5) & 31
    if opc != 1 or invert or rn != 31 or shift_type or amount:
        return None
    return word & 31, (word >> 16) & 31


def _decode_adr(word: int, address: int):
    if (word & 0x1F000000) != 0x10000000:
        return None
    page = bool((word >> 31) & 1)
    immlo = (word >> 29) & 3
    immhi = (word >> 5) & 0x7FFFF
    immediate = _sign_extend((immhi << 2) | immlo, 21)
    rd = word & 31
    if page:
        target = ((address & ~0xFFF) + (immediate << 12)) & 0xFFFFFFFFFFFFFFFF
    else:
        target = (address + immediate) & 0xFFFFFFFFFFFFFFFF
    return rd, target


def _decode_add_sub_immediate(word: int):
    if (word & 0x1F000000) != 0x11000000:
        return None
    subtract = bool((word >> 30) & 1)
    set_flags = bool((word >> 29) & 1)
    shift = 12 if ((word >> 22) & 1) else 0
    immediate = ((word >> 10) & 0xFFF) << shift
    rn = (word >> 5) & 31
    rd = word & 31
    return rd, rn, immediate, subtract, set_flags


def _decode_move_wide(word: int):
    if (word & 0x1F800000) != 0x12800000:
        return None
    sf = (word >> 31) & 1
    opc = (word >> 29) & 3
    hw = (word >> 21) & 3
    if not sf and hw >= 2:
        return None
    immediate = (word >> 5) & 0xFFFF
    shift = hw * 16
    rd = word & 31
    if opc == 2:
        return rd, immediate << shift, False
    if opc == 0:
        width_mask = (1 << (64 if sf else 32)) - 1
        return rd, (~(immediate << shift)) & width_mask, False
    if opc == 3:
        mask = 0xFFFF << shift
        return rd, (mask, immediate << shift), True
    return None


def _decode_compare_register(word: int):
    if (word & 0x1F200000) != 0x0B000000:
        return None
    subtract = (word >> 30) & 1
    set_flags = (word >> 29) & 1
    rd = word & 31
    if not subtract or not set_flags or rd != 31:
        return None
    rn = (word >> 5) & 31
    rm = (word >> 16) & 31
    return rn, rm


def _branch_relation(mnemonic: str):
    relations = {
        "b.eq": "==", "b.ne": "!=", "b.lt": "<", "b.le": "<=",
        "b.gt": ">", "b.ge": ">=", "b.lo": "unsigned <",
        "b.ls": "unsigned <=", "b.hi": "unsigned >", "b.hs": "unsigned >=",
    }
    return relations.get(mnemonic)


def _offset_expr(base: str, displacement: int) -> str:
    if displacement == 0:
        return base
    if displacement < 0:
        return f"{base}-0x{-displacement:X}"
    return f"{base}+0x{displacement:X}"


def _sign_extend(value: int, bits: int) -> int:
    sign = 1 << (bits - 1)
    return (value & (sign - 1)) - (value & sign)
