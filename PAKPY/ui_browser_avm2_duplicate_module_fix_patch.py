"""Disambiguate duplicate DoABC modules for the generic AVM2 patcher.

Scaleform movies can contain multiple unnamed DoABC tags in the same root timeline.
The base patcher identifies modules by name and source, which is insufficient in that
case. This patch narrows duplicate candidates using the selected method body, patch
range and expected original bytes. Existing JSON profiles remain unchanged.
"""
from __future__ import annotations

import ui_browser_avm2_repack as repack


_INSTALLED = False
_BASE_INFLATE_SWF = None
_BASE_FIND_MODULE = None
_LAST_INFLATED_DATA = b""


def _inflate_swf(raw):
    global _LAST_INFLATED_DATA
    data, signature = _BASE_INFLATE_SWF(raw)
    _LAST_INFLATED_DATA = bytes(data)
    return data, signature


def _method_for(location, method_index):
    return next(
        (item for item in location.methods if item.method_index == int(method_index)),
        None,
    )


def _method_candidates(candidates, patch):
    result = []
    patch_end = int(patch.code_offset) + len(patch.expected)
    for location in candidates:
        method = _method_for(location, patch.method_index)
        if method is None or patch_end > method.code_size:
            continue
        result.append((location, method))
    return result


def _expected_byte_candidates(candidates, patch):
    if not _LAST_INFLATED_DATA:
        return []
    result = []
    for location, method in candidates:
        absolute = location.abc_offset + method.code_offset + int(patch.code_offset)
        end = absolute + len(patch.expected)
        if absolute < 0 or end > len(_LAST_INFLATED_DATA):
            continue
        if _LAST_INFLATED_DATA[absolute:end] == patch.expected:
            result.append(location)
    return result


def _find_module(locations, patch):
    exact = [
        item for item in locations
        if item.name == patch.module_name and item.source == patch.source
    ]
    candidates = exact
    if not candidates:
        candidates = [item for item in locations if item.name == patch.module_name]
    if not candidates:
        raise repack.AVM2PatchError(
            f"DoABC-Modul nicht gefunden: {patch.module_name} [{patch.source}]"
        )
    if len(candidates) == 1:
        return candidates[0]

    method_candidates = _method_candidates(candidates, patch)
    if len(method_candidates) == 1:
        return method_candidates[0][0]

    byte_candidates = _expected_byte_candidates(method_candidates, patch)
    if len(byte_candidates) == 1:
        return byte_candidates[0]

    if not method_candidates:
        raise repack.AVM2PatchError(
            f"Keines von {len(candidates)} gleichnamigen DoABC-Modulen enthält "
            f"Methode {patch.method_index} mit Patchbereich +0x{patch.code_offset:X}"
        )

    detail = (
        f"{len(byte_candidates)} passende Originalbyte-Treffer"
        if byte_candidates
        else f"{len(method_candidates)} passende Methodenbodies"
    )
    raise repack.AVM2PatchError(
        f"DoABC-Modul bleibt mehrdeutig: {patch.module_name} [{patch.source}] · {detail}"
    )


def install():
    global _INSTALLED, _BASE_INFLATE_SWF, _BASE_FIND_MODULE
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_INFLATE_SWF = repack._inflate_swf
    _BASE_FIND_MODULE = repack._find_module
    repack._inflate_swf = _inflate_swf
    repack._find_module = _find_module
