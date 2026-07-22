"""Use dataclass-safe copies for corpus AVM2 instruction translations."""
from __future__ import annotations

import copy
from dataclasses import replace

import ui_browser_avm2_runtime_corpus_patch as corpus_patch


_INSTALLED = False


def instruction(item, name, operands=None):
    changes = {"name": name}
    if operands is not None:
        changes["operands"] = tuple(operands)
    try:
        return replace(item, **changes)
    except Exception:
        clone = copy.copy(item)
        for key, value in changes.items():
            setattr(clone, key, value)
        return clone


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    corpus_patch._instruction = instruction
