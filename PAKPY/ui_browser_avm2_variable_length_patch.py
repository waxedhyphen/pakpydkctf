"""Variable-length AVM2 method-body patching.

This extension keeps the existing expected-byte validation, but allows a replacement
block to be longer or shorter than the original block. It rebuilds the method's U30
code-size field, the containing DoABC tag, nested DefineSprite tag sizes and the SWF
file length. Branch offsets, lookupswitch offsets and exception-table offsets are not
rewritten automatically; the UI therefore requires explicit confirmation for every
size-changing patch.
"""
from __future__ import annotations

from collections import defaultdict

import ui_browser_avm2_repack as repack


_INSTALLED = False
_BASE_BYTEPATCH_POST_INIT = None
_BASE_APPLY_MOVIE_PATCHES = None


def _encode_u30(value):
    value = int(value)
    if value < 0 or value > 0x3FFFFFFF:
        raise repack.AVM2PatchError(f"Ungültiger U30-Wert {value}")
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            result.append(byte | 0x80)
        else:
            result.append(byte)
            return bytes(result)


def _bytepatch_post_init(self):
    if self.method_index < 0 or self.code_offset < 0:
        raise repack.AVM2PatchError(
            "Methodenindex und Code-Offset dürfen nicht negativ sein"
        )
    if not self.expected:
        raise repack.AVM2PatchError(
            "Eine erwartete Bytefolge ist als Sicherheitsanker erforderlich"
        )
    if not self.replacement and len(self.expected) == 0:
        raise repack.AVM2PatchError("Leerer Patch ist nicht zulässig")


def patch_delta(patch):
    return len(patch.replacement) - len(patch.expected)


def patch_kind(patch):
    delta = patch_delta(patch)
    if delta > 0:
        return f"+{delta} Bytes"
    if delta < 0:
        return f"{delta} Bytes"
    return "gleich lang"


def _encode_tag(code, payload):
    payload = bytes(payload)
    if len(payload) < 63:
        return ((int(code) << 6) | len(payload)).to_bytes(2, "little") + payload
    return (
        ((int(code) << 6) | 63).to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
        + payload
    )


def _rewrite_tag_stream(data, start, end, replacements):
    """Rebuild only tags whose payload or nested payload changed."""
    result = bytearray()
    p = int(start)
    changed_any = False
    while p + 2 <= end:
        header_offset = p
        record = int.from_bytes(data[p:p + 2], "little")
        p += 2
        code = record >> 6
        size = record & 0x3F
        if size == 0x3F:
            if p + 4 > end:
                raise repack.AVM2PatchError("SWF-Langtag ist abgeschnitten")
            size = int.from_bytes(data[p:p + 4], "little")
            p += 4
        payload_offset = p
        payload_end = p + size
        if payload_end > end:
            raise repack.AVM2PatchError(f"SWF-Tag {code} läuft über das Dateiende")

        changed = False
        payload = bytes(data[payload_offset:payload_end])
        replacement = replacements.get(payload_offset)
        if code == 82 and replacement is not None:
            payload = bytes(replacement)
            changed = True
        elif code == 39 and size >= 4:
            nested, nested_changed = _rewrite_tag_stream(
                data, payload_offset + 4, payload_end, replacements
            )
            if nested_changed:
                payload = bytes(data[payload_offset:payload_offset + 4]) + nested
                changed = True

        if changed:
            result += _encode_tag(code, payload)
            changed_any = True
        else:
            result += data[header_offset:payload_end]

        p = payload_end
        if code == 0:
            if p < end:
                result += data[p:end]
            return bytes(result), changed_any

    if p < end:
        result += data[p:end]
    return bytes(result), changed_any


def _method_for(module, method_index):
    return next(
        (item for item in module.methods if item.method_index == int(method_index)),
        None,
    )


def _code_size_field(abc_data, method):
    encoded = _encode_u30(method.code_size)
    start = int(method.code_offset) - len(encoded)
    if start < 0 or bytes(abc_data[start:method.code_offset]) != encoded:
        raise repack.AVM2PatchError(
            f"Codegrößenfeld von Methode {method.method_index} konnte nicht "
            "eindeutig bestimmt werden"
        )
    return start, encoded


def _validated_method_replacement(abc_data, module, method, patches):
    original_code = bytes(
        abc_data[method.code_offset:method.code_offset + method.code_size]
    )
    ordered = sorted(
        patches,
        key=lambda item: (int(item.code_offset), len(item.expected)),
    )
    previous_end = 0
    for patch in ordered:
        start = int(patch.code_offset)
        end = start + len(patch.expected)
        if end > len(original_code):
            raise repack.AVM2PatchError(
                f"Patch überschreitet Methode {patch.method_index}: "
                f"0x{patch.code_offset:X}+{len(patch.expected)}"
            )
        if start < previous_end:
            raise repack.AVM2PatchError(
                "Mehrere Patches überlappen sich innerhalb derselben Methode"
            )
        actual = original_code[start:end]
        if actual != patch.expected:
            raise repack.AVM2PatchError(
                f"Originalbytes passen nicht bei {module.name} "
                f"Methode {patch.method_index} +0x{patch.code_offset:X}: "
                f"erwartet {patch.expected.hex(' ').upper()}, "
                f"gefunden {actual.hex(' ').upper()}"
            )
        previous_end = end

    rebuilt = bytearray()
    cursor = 0
    for patch in ordered:
        start = int(patch.code_offset)
        end = start + len(patch.expected)
        rebuilt += original_code[cursor:start]
        rebuilt += patch.replacement
        cursor = end
    rebuilt += original_code[cursor:]
    return bytes(rebuilt), ordered


def _rebuild_module_abc(data, module, method_patches, applied):
    abc = bytearray(data[module.abc_offset:module.abc_offset + module.abc_size])
    methods = []
    for method_index, patches in method_patches.items():
        method = _method_for(module, method_index)
        if method is None:
            raise repack.AVM2PatchError(
                f"Methode {method_index} hat in {module.name} "
                f"[{module.source}] keinen Body"
            )
        methods.append((method, patches))

    # Later method bodies first, so original offsets for earlier bodies stay valid.
    for method, patches in sorted(methods, key=lambda item: item[0].code_offset, reverse=True):
        new_code, ordered = _validated_method_replacement(
            abc, module, method, patches
        )
        size_start, _encoded = _code_size_field(abc, method)
        old_end = method.code_offset + method.code_size
        abc[size_start:old_end] = _encode_u30(len(new_code)) + new_code

        for patch in ordered:
            applied.append({
                **patch.to_json(),
                "absolute_uncompressed_swf_offset": (
                    module.abc_offset + method.code_offset + patch.code_offset
                ),
                "old_method_code_size": method.code_size,
                "new_method_code_size": len(new_code),
                "byte_delta": patch_delta(patch),
                "size_change_warning": (
                    "Sprung-, lookupswitch- und Exception-Offsets werden nicht "
                    "automatisch angepasst"
                    if patch_delta(patch)
                    else ""
                ),
            })
    return bytes(abc)


def apply_movie_patches(movie_data, patches):
    patches = tuple(patches or ())
    data, signature = repack._inflate_swf(movie_data)
    locations = repack.locate_doabc_modules(bytes(data))

    grouped = defaultdict(lambda: defaultdict(list))
    modules = {}
    for patch in patches:
        module = repack._find_module(locations, patch)
        method = _method_for(module, patch.method_index)
        if method is None:
            raise repack.AVM2PatchError(
                f"Methode {patch.method_index} hat in {module.name} "
                f"[{module.source}] keinen Body"
            )
        key = int(module.tag_payload_offset)
        modules[key] = module
        grouped[key][int(patch.method_index)].append(patch)

    replacements = {}
    applied = []
    for key, method_patches in grouped.items():
        module = modules[key]
        new_abc = _rebuild_module_abc(data, module, method_patches, applied)
        prefix_size = module.abc_offset - module.tag_payload_offset
        original_payload = bytes(
            data[module.tag_payload_offset:
                 module.tag_payload_offset + module.tag_payload_size]
        )
        replacements[key] = original_payload[:prefix_size] + new_abc

    if replacements:
        start = repack._swf_header_end(data)
        stream, changed = _rewrite_tag_stream(
            data, start, len(data), replacements
        )
        if not changed:
            raise repack.AVM2PatchError(
                "DoABC-Tag für den Größenpatch wurde nicht wiedergefunden"
            )
        rebuilt = bytearray(data[:start])
        rebuilt += stream
    else:
        rebuilt = bytearray(data)

    result = repack._deflate_swf(rebuilt, signature)
    # Reparse both ABC and SWF/GFX structure after rebuilding.
    repack.locate_doabc_modules(result)
    return repack.PatchResult(
        result,
        tuple(applied),
        signature.decode("ascii", "replace"),
    )


def install():
    global _INSTALLED, _BASE_BYTEPATCH_POST_INIT, _BASE_APPLY_MOVIE_PATCHES
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_BYTEPATCH_POST_INIT = repack.BytePatch.__post_init__
    _BASE_APPLY_MOVIE_PATCHES = repack.apply_movie_patches
    repack.BytePatch.__post_init__ = _bytepatch_post_init
    repack.apply_movie_patches = apply_movie_patches
