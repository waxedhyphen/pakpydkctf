"""Inventory remaining SWF visual formats without executing AVM1 or AVM2.

Usage:
    python scan_ui_visual_formats.py UIPak.pak \
        --require PreLoadPak.pak --require MiscData.pak \
        --decode-bitmaps --json ui_visual_formats.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import ui_browser
import ui_browser_shape_patch as shape_patch
import ui_browser_visual_formats as visual
from scan_ui_native_callbacks import _decode_swf, _iter_tags


TAG_DEFINE_SPRITE = 39
TAG_PLACE_OBJECT2 = 26
TAG_PLACE_OBJECT3 = 70
_MAX_RECURSION = 64
_MAX_EXAMPLES = 300


def _record_shape(payload, version, source, path, result):
    definition = shape_patch.parse_vector_shape(payload, version)
    result["counts"]["vector_shapes"] += 1
    result["counts"][f"define_shape_{version}"] += 1
    kinds = Counter()
    for style in definition.fills[1:]:
        if style is None:
            continue
        kinds[style.kind] += 1
        result["counts"][f"fill_{style.kind}"] += 1
        result["counts"][f"fill_type_0x{style.fill_type:02X}"] += 1
        if style.kind == "focal_gradient" and abs(float(getattr(style, "focal_point", 0.0))) > 1e-9:
            result["counts"]["nonzero_focal_gradients"] += 1
    if len(result["examples"]) < _MAX_EXAMPLES:
        result["examples"].append({
            "source": source,
            "path": path,
            "kind": f"DefineShape{version}",
            "character_id": int(definition.character_id),
            "fills": dict(sorted(kinds.items())),
            "records": int(definition.record_count),
            "unsupported": list(definition.unsupported_fill_types),
        })


def _record_morph(payload, version, source, path, result):
    definition = visual.parse_morph_shape(payload, version)
    result["counts"]["morph_shapes"] += 1
    result["counts"][f"define_morph_shape_{version}"] += 1
    result["counts"]["morph_start_edges"] += len(definition.start_records)
    result["counts"]["morph_end_edges"] += len(definition.end_records)
    result["counts"]["morph_edge_mismatches"] += int(
        len(definition.start_records) != len(definition.end_records)
    )
    for pair in definition.fills[1:]:
        if pair is None:
            continue
        result["counts"][f"morph_fill_{pair.start.kind}"] += 1
    if len(result["examples"]) < _MAX_EXAMPLES:
        result["examples"].append({
            "source": source,
            "path": path,
            "kind": f"DefineMorphShape{version if version > 1 else ''}",
            "character_id": int(definition.character_id),
            "start_edges": len(definition.start_records),
            "end_edges": len(definition.end_records),
            "warnings": list(definition.parse_warnings),
        })


def _scan_tags(tags, source, result, path="root", depth=0):
    if depth > _MAX_RECURSION:
        result["errors"].append({
            "source": source, "path": path, "error": "sprite recursion limit",
        })
        return
    for index, (code, payload) in enumerate(tags):
        tag_path = f"{path}/tag{index}:{code}"
        try:
            version = {2: 1, 22: 2, 32: 3, 83: 4}.get(code)
            if version:
                _record_shape(payload, version, source, tag_path, result)
            elif code in (visual.TAG_DEFINE_MORPH_SHAPE, visual.TAG_DEFINE_MORPH_SHAPE2):
                _record_morph(
                    payload, 1 if code == visual.TAG_DEFINE_MORPH_SHAPE else 2,
                    source, tag_path, result,
                )
            elif code in (
                visual.TAG_DEFINE_BITS, visual.TAG_DEFINE_BITS_JPEG2,
                visual.TAG_DEFINE_BITS_JPEG3, visual.TAG_DEFINE_BITS_JPEG4,
                visual.TAG_DEFINE_BITS_LOSSLESS, visual.TAG_DEFINE_BITS_LOSSLESS2,
            ):
                result["counts"]["embedded_bitmap_tags"] += 1
                result["counts"][f"bitmap_tag_{code}"] += 1
            elif code == TAG_PLACE_OBJECT2:
                result["counts"]["place_object2"] += 1
                if payload and payload[0] & 0x10:
                    result["counts"]["ratio_placements"] += 1
            elif code == TAG_PLACE_OBJECT3:
                result["counts"]["place_object3"] += 1
                if payload and payload[0] & 0x10:
                    result["counts"]["ratio_placements"] += 1
            elif code == TAG_DEFINE_SPRITE:
                if len(payload) < 4:
                    raise ValueError("DefineSprite truncated")
                character_id = int.from_bytes(payload[:2], "little")
                child_tags = ui_browser._iter_tags(payload, 4)
                _scan_tags(
                    child_tags, source, result,
                    f"{path}/sprite:{character_id}", depth + 1,
                )
        except Exception as exc:
            result["errors"].append({
                "source": source, "path": tag_path, "tag": int(code),
                "error": str(exc),
            })


def scan_path(path, decode_bitmaps=False):
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
        "examples": [],
        "errors": [],
    }
    for offset in sorted(offsets):
        try:
            swf = _decode_swf(raw, offset)
            if swf is None:
                continue
            tags = _iter_tags(swf)
            source = f"{Path(path).name}@0x{offset:X}"
            result["movies"] += 1
            _scan_tags(tags, source, result)
            if decode_bitmaps:
                definitions, errors = visual.parse_embedded_bitmaps(tags)
                result["counts"]["decoded_bitmaps"] += len(definitions)
                result["counts"]["bitmap_decode_errors"] += len(errors)
                for error in errors:
                    result["errors"].append({"source": source, **error})
        except Exception as exc:
            result["errors"].append({
                "source": str(Path(path)), "offset": offset, "error": str(exc),
            })
    result["counts"] = dict(sorted(result["counts"].items()))
    return result


def scan_all(primary, requires=(), decode_bitmaps=False):
    files = [scan_path(primary, decode_bitmaps)] + [
        scan_path(path, decode_bitmaps) for path in requires
    ]
    totals = Counter()
    for item in files:
        totals.update(item["counts"])
    return {
        "schema": 1,
        "primary": str(Path(primary)),
        "requires": [str(Path(path)) for path in requires],
        "decode_bitmaps": bool(decode_bitmaps),
        "movies": sum(item["movies"] for item in files),
        "errors": sum(len(item["errors"]) for item in files),
        "totals": dict(sorted(totals.items())),
        "files": files,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="primary UI PAK or standalone SWF/GFX")
    parser.add_argument("--require", action="append", default=[], help="required PAK; may repeat")
    parser.add_argument("--decode-bitmaps", action="store_true", help="validate embedded bitmap payloads")
    parser.add_argument("--json", dest="json_path", help="write complete JSON report")
    args = parser.parse_args(argv)

    shape_patch._read_fill_style = visual.read_vector_fill_style
    result = scan_all(args.input, args.require, args.decode_bitmaps)
    totals = result["totals"]
    print(f"Embedded movies: {result['movies']}")
    print(f"Vector shapes: {totals.get('vector_shapes', 0)}")
    print(f"Morph shapes: {totals.get('morph_shapes', 0)}")
    print(f"Bitmap fill styles: {totals.get('fill_bitmap', 0)}")
    print(f"Radial/focal gradients: {totals.get('fill_radial_gradient', 0)} / {totals.get('fill_focal_gradient', 0)}")
    print(f"Embedded bitmap tags: {totals.get('embedded_bitmap_tags', 0)}")
    print(f"Ratio placements: {totals.get('ratio_placements', 0)}")
    print(f"Parser errors: {result['errors']}")
    if args.json_path:
        output = Path(args.json_path)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {output}")
    return 0 if not result["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
