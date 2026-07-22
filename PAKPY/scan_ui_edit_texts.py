"""Inventory DefineEditText input capabilities in embedded SWF/GFX movies.

Usage:
    python scan_ui_edit_texts.py UIPak.pak --require PreLoadPak.pak \
        --json ui_edit_texts.json

The scanner is read-only.  It does not execute AVM1/AVM2, access the clipboard or
modify PAK/SWF resources.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import ui_browser
import ui_browser_text_patch as text_patch
from scan_ui_native_callbacks import _decode_swf, _iter_tags


TAG_DEFINE_EDIT_TEXT = 37
TAG_DEFINE_SPRITE = 39
_MAX_RECURSION = 64
_MAX_EXAMPLES = 200


def _flags(payload):
    _bounds, position = ui_browser._read_rect(payload, 2)
    if position + 2 > len(payload):
        raise ValueError("DefineEditText flags are truncated")
    first, second = payload[position], payload[position + 1]
    return {
        "has_text": bool(first & 0x80),
        "word_wrap": bool(first & 0x40),
        "multiline": bool(first & 0x20),
        "password": bool(first & 0x10),
        "read_only": bool(first & 0x08),
        "auto_size": bool(second & 0x40),
        "no_select": bool(second & 0x10),
        "border": bool(second & 0x08),
        "html": bool(second & 0x02),
    }


def _scan_tags(tags, source, result, path="root", depth=0):
    if depth > _MAX_RECURSION:
        result["errors"].append({"source": source, "path": path, "error": "sprite recursion limit"})
        return
    for index, (code, payload) in enumerate(tags):
        tag_path = f"{path}/tag{index}:{code}"
        if code == TAG_DEFINE_EDIT_TEXT:
            try:
                definition = text_patch.parse_edit_text(payload)
                flags = _flags(payload)
                editable = not flags["read_only"] and not flags["no_select"]
                result["counts"]["define_edit_text"] += 1
                result["counts"]["editable"] += int(editable)
                result["counts"]["read_only"] += int(flags["read_only"])
                result["counts"]["no_select"] += int(flags["no_select"])
                result["counts"]["multiline"] += int(flags["multiline"])
                result["counts"]["word_wrap"] += int(flags["word_wrap"])
                result["counts"]["password"] += int(flags["password"])
                result["counts"]["html"] += int(flags["html"])
                result["counts"]["max_length"] += int(bool(getattr(definition, "max_length", 0)))
                if len(result["fields"]) < _MAX_EXAMPLES:
                    result["fields"].append({
                        "source": source,
                        "path": tag_path,
                        "character_id": int(definition.character_id),
                        "variable_name": str(definition.variable_name or ""),
                        "initial_text": str(definition.initial_text or "")[:500],
                        "editable": editable,
                        "max_length": int(getattr(definition, "max_length", 0) or 0),
                        **flags,
                    })
            except Exception as exc:
                result["errors"].append({"source": source, "path": tag_path, "error": str(exc)})
        elif code == TAG_DEFINE_SPRITE:
            if len(payload) < 4:
                result["errors"].append({"source": source, "path": tag_path, "error": "DefineSprite truncated"})
                continue
            character_id = int.from_bytes(payload[:2], "little")
            try:
                child_tags = ui_browser._iter_tags(payload, 4)
                _scan_tags(child_tags, source, result, f"{path}/sprite:{character_id}", depth + 1)
            except Exception as exc:
                result["errors"].append({"source": source, "path": tag_path, "error": str(exc)})


def scan_path(path):
    raw = Path(path).read_bytes()
    offsets = set()
    for signature in (b"FWS", b"CWS", b"GFX"):
        start = 0
        while True:
            offset = raw.find(signature, start)
            if offset < 0:
                break
            offsets.add(offset)
            start = offset + 1
    result = {
        "path": str(Path(path)),
        "movies": 0,
        "counts": Counter(),
        "fields": [],
        "errors": [],
    }
    for offset in sorted(offsets):
        try:
            swf = _decode_swf(raw, offset)
            if swf is None:
                continue
            tags = _iter_tags(swf)
            result["movies"] += 1
            _scan_tags(tags, f"{Path(path).name}@0x{offset:X}", result)
        except Exception as exc:
            result["errors"].append({"source": str(Path(path)), "offset": offset, "error": str(exc)})
    result["counts"] = dict(sorted(result["counts"].items()))
    return result


def scan_all(primary, requires=()):
    files = [scan_path(primary)] + [scan_path(path) for path in requires]
    totals = Counter()
    for item in files:
        totals.update(item["counts"])
    return {
        "schema": 1,
        "primary": str(Path(primary)),
        "requires": [str(Path(path)) for path in requires],
        "totals": dict(sorted(totals.items())),
        "movies": sum(item["movies"] for item in files),
        "errors": sum(len(item["errors"]) for item in files),
        "files": files,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="primary UI PAK or standalone SWF/GFX")
    parser.add_argument("--require", action="append", default=[], help="required PAK; may be repeated")
    parser.add_argument("--json", dest="json_path", help="write complete JSON report")
    args = parser.parse_args(argv)
    result = scan_all(args.input, args.require)
    totals = result["totals"]
    print(f"Embedded movies: {result['movies']}")
    print(f"DefineEditText: {totals.get('define_edit_text', 0)}")
    print(f"Editable fields: {totals.get('editable', 0)}")
    print(f"Multiline: {totals.get('multiline', 0)}")
    print(f"Password: {totals.get('password', 0)}")
    print(f"Parser errors: {result['errors']}")
    if args.json_path:
        output = Path(args.json_path)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {output}")
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
