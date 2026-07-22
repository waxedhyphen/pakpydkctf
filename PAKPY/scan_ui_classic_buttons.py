"""Scan embedded Scaleform movies for classic SWF buttons and input-mask features.

Usage:
    python scan_ui_classic_buttons.py UIPak.pak --json ui_buttons.json

The scanner is read-only. It never executes AVM1/AVM2 and reports classic button actions
as inventory only. Run it once per PAK when a corpus spans multiple containers.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import ui_browser_avm2_patch as avm2
import ui_browser_classic_button as classic
from scan_ui_native_callbacks import _decode_swf, _iter_tags

_RUNTIME_INPUT_NAMES = ("scrollRect", "hitArea", "mask", "mouseChildren")
TAG_PLACE_OBJECT2 = 26
TAG_DEFINE_SPRITE = 39
TAG_PLACE_OBJECT3 = 70


def _tag_stream(data: bytes, start=0):
    p = int(start)
    while p + 2 <= len(data):
        record = int.from_bytes(data[p:p + 2], "little")
        p += 2
        code = record >> 6
        size = record & 0x3F
        if size == 0x3F:
            if p + 4 > len(data):
                return
            size = int.from_bytes(data[p:p + 4], "little")
            p += 4
        end = p + size
        if end > len(data):
            return
        yield code, data[p:end]
        p = end
        if code == 0:
            return


def _skip_matrix(data: bytes, p: int):
    bit = p * 8

    def read(count):
        nonlocal bit
        value = 0
        for _ in range(count):
            if bit >= len(data) * 8:
                raise ValueError("MATRIX is truncated")
            value = (value << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
            bit += 1
        return value

    if read(1):
        n = read(5)
        read(n)
        read(n)
    if read(1):
        n = read(5)
        read(n)
        read(n)
    n = read(5)
    read(n)
    read(n)
    return (bit + 7) // 8


def _skip_cxform(data: bytes, p: int):
    bit = p * 8

    def read(count):
        nonlocal bit
        value = 0
        for _ in range(count):
            if bit >= len(data) * 8:
                raise ValueError("CXFORM is truncated")
            value = (value << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
            bit += 1
        return value

    has_add, has_mult, n = read(1), read(1), read(4)
    if has_mult:
        for _ in range(4):
            read(n)
    if has_add:
        for _ in range(4):
            read(n)
    return (bit + 7) // 8


def _skip_cstring(data: bytes, p: int):
    end = data.find(b"\x00", p)
    if end < 0:
        raise ValueError("string is not terminated")
    return end + 1


def _clip_depth(code: int, payload: bytes):
    if code == TAG_PLACE_OBJECT2:
        if len(payload) < 3:
            raise ValueError("PlaceObject2 is truncated")
        flags, p = payload[0], 3
        if flags & 0x02:
            p += 2
        if flags & 0x04:
            p = _skip_matrix(payload, p)
        if flags & 0x08:
            p = _skip_cxform(payload, p)
        if flags & 0x10:
            p += 2
        if flags & 0x20:
            p = _skip_cstring(payload, p)
        if flags & 0x40:
            if p + 2 > len(payload):
                raise ValueError("clipDepth is truncated")
            return int.from_bytes(payload[p:p + 2], "little")
        return None
    if code == TAG_PLACE_OBJECT3:
        if len(payload) < 4:
            raise ValueError("PlaceObject3 is truncated")
        flags1, flags2, p = payload[0], payload[1], 4
        has_character = bool(flags1 & 0x02)
        if flags2 & 0x08 or (flags2 & 0x10 and has_character):
            p = _skip_cstring(payload, p)
        if has_character:
            p += 2
        if flags1 & 0x04:
            p = _skip_matrix(payload, p)
        if flags1 & 0x08:
            p = _skip_cxform(payload, p)
        if flags1 & 0x10:
            p += 2
        if flags1 & 0x20:
            p = _skip_cstring(payload, p)
        if flags1 & 0x40:
            if p + 2 > len(payload):
                raise ValueError("clipDepth is truncated")
            return int.from_bytes(payload[p:p + 2], "little")
        return None
    return None


def _embedded_offsets(raw: bytes):
    result = set()
    for signature in (b"FWS", b"CWS", b"GFX"):
        start = 0
        while True:
            offset = raw.find(signature, start)
            if offset < 0:
                break
            result.add(offset)
            start = offset + 1
    return tuple(sorted(result))


def _walk_tags(tags, result, source="root"):
    for code, payload in tuple(tags or ()):
        if code in (classic.TAG_DEFINE_BUTTON, classic.TAG_DEFINE_BUTTON2):
            version = 1 if code == classic.TAG_DEFINE_BUTTON else 2
            key = "define_button" if version == 1 else "define_button2"
            result[key] += 1
            try:
                definition = classic.parse_classic_button(payload, version)
                result["records"] += len(definition.records)
                result["hit_records"] += len(definition.hit_records)
                result["action_bindings"] += len(definition.button_actions)
                for binding in definition.button_actions:
                    result["condition_counts"].update(binding.conditions)
                    if binding.key_code:
                        result["key_bindings"] += 1
                    for action in binding.actions:
                        result["actions"] += 1
                        result["action_names"][action.name] += 1
                        result["safe_actions" if action.safe else "blocked_actions"] += 1
            except Exception as exc:
                result["button_errors"].append({"source": source, "tag": code, "error": str(exc)})
        elif code in (TAG_PLACE_OBJECT2, TAG_PLACE_OBJECT3):
            try:
                if _clip_depth(code, payload) is not None:
                    result["clip_depth_masks"] += 1
            except Exception as exc:
                result["placement_errors"].append({"source": source, "tag": code, "error": str(exc)})
        elif code == TAG_DEFINE_SPRITE and len(payload) >= 4:
            character_id = int.from_bytes(payload[:2], "little")
            try:
                nested = tuple(_tag_stream(payload, 4))
                _walk_tags(nested, result, f"sprite:{character_id}")
            except Exception as exc:
                result["sprite_errors"].append({"source": source, "character_id": character_id, "error": str(exc)})


def scan_file(path):
    path = Path(path)
    raw = path.read_bytes()
    result = {
        "schema": 1, "input": str(path), "embedded_movies": 0,
        "define_button": 0, "define_button2": 0, "records": 0,
        "hit_records": 0, "action_bindings": 0, "actions": 0,
        "safe_actions": 0, "blocked_actions": 0, "key_bindings": 0,
        "clip_depth_masks": 0, "action_names": Counter(),
        "condition_counts": Counter(), "runtime_input_strings": Counter(),
        "unique_abc_modules": 0, "button_errors": [], "placement_errors": [],
        "sprite_errors": [], "abc_errors": [],
    }
    modules = {}
    for offset in _embedded_offsets(raw):
        try:
            swf = _decode_swf(raw, offset)
            if swf is None:
                continue
            tags = tuple(_iter_tags(swf))
            result["embedded_movies"] += 1
            _walk_tags(tags, result, f"offset:0x{offset:X}")
            for code, payload in tags:
                if code != avm2.TAG_DO_ABC:
                    continue
                end = payload.find(b"\x00", 4)
                abc_raw = payload[end + 1:] if end >= 0 else payload
                abc_digest = hashlib.sha256(abc_raw).hexdigest()
                if abc_digest in modules:
                    continue
                module = avm2.parse_doabc(payload, f"offset 0x{offset:X}")
                modules[abc_digest] = module
                if module.error:
                    result["abc_errors"].append({"offset": offset, "module": module.name, "error": module.error})
                abc = getattr(module, "abc", None)
                for value in tuple(getattr(abc, "strings", ()) or ()):
                    if value in _RUNTIME_INPUT_NAMES:
                        result["runtime_input_strings"][value] += 1
        except Exception as exc:
            result["sprite_errors"].append({"source": f"offset:0x{offset:X}", "error": str(exc)})
    result["unique_abc_modules"] = len(modules)
    result["action_names"] = dict(result["action_names"].most_common())
    result["condition_counts"] = dict(result["condition_counts"].most_common())
    result["runtime_input_strings"] = dict(sorted(result["runtime_input_strings"].items()))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="SWF/GFX or a containing PAK")
    parser.add_argument("--json", dest="json_path", help="write the complete report as JSON")
    args = parser.parse_args(argv)
    result = scan_file(args.input)
    print(f"Embedded movies: {result['embedded_movies']}")
    print(f"DefineButton: {result['define_button']}")
    print(f"DefineButton2: {result['define_button2']}")
    print(f"Button records / hit records: {result['records']} / {result['hit_records']}")
    print(f"Actions: {result['actions']} ({result['safe_actions']} safe, {result['blocked_actions']} inventory-only)")
    print(f"ClipDepth masks: {result['clip_depth_masks']}")
    print(f"ABC modules: {result['unique_abc_modules']}")
    if result["runtime_input_strings"]:
        print("Runtime input names:")
        for name, count in result["runtime_input_strings"].items():
            print(f"  {name}: {count}")
    errors = sum(len(result[key]) for key in ("button_errors", "placement_errors", "sprite_errors", "abc_errors"))
    print(f"Errors: {errors}")
    if args.json_path:
        output = Path(args.json_path)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {output}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
