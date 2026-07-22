"""Apply AVM2-style numeric fallback for incomparable runtime values."""
from __future__ import annotations

import math

import ui_browser_avm2_runtime_patch as runtime


_INSTALLED = False
_BASE_BINARY = None


def binary(name, left, right):
    try:
        return _BASE_BINARY(name, left, right)
    except Exception:
        if name not in ("lessthan", "lessequals", "greaterthan", "greaterequals"):
            return runtime._UNDEFINED
        left_number = runtime._number(left)
        right_number = runtime._number(right)
        if math.isnan(left_number) or math.isnan(right_number):
            return False
        return {
            "lessthan": left_number < right_number,
            "lessequals": left_number <= right_number,
            "greaterthan": left_number > right_number,
            "greaterequals": left_number >= right_number,
        }[name]


def install():
    global _INSTALLED, _BASE_BINARY
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_BINARY = runtime._binary
    runtime._binary = binary
