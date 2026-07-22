"""Reproducible scanner for native Scaleform callback call sites.

Usage:
    python scan_ui_native_callbacks.py UIPak.pak --json callbacks.json

The scanner does not execute AVM2. It finds embedded FWS/CWS/GFX films, deduplicates ABC
payloads by SHA-256 and applies the same callback-site extractor as the UI Browser.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zlib

import ui_browser_avm2_patch as avm2
import ui_browser_native_callback_patch as native


def _rect_end(data, offset=8):
    bit = int(offset) * 8

    def read(count):
        nonlocal bit
        value = 0
        for _ in range(count):
            if bit >= len(data) * 8:
                raise ValueError("SWF RECT is truncated")
            value = (value << 1) | ((data[bit >> 3] >> (7 - (bit & 7))) & 1)
            bit += 1
        return value

    width = read(5)
    for _ in range(4):
        read(width)
    return (bit + 7) // 8


def _iter_tags(data):
    position = _rect_end(data) + 4
    while position + 2 <= len(data):
        record = int.from_bytes(data[position:position + 2], "little")
        position += 2
        code = record >> 6
        length = record & 0x3F
        if length == 0x3F:
            if position + 4 > len(data):
                return
            length = int.from_bytes(data[position:position + 4], "little")
            position += 4
        end = position + length
        if end > len(data):
            return
        yield code, data[position:end]
        position = end
        if code == 0:
            return


def _decode_swf(raw, offset):
    if offset + 8 > len(raw):
        return None
    signature = raw[offset:offset + 3]
    version = raw[offset + 3]
    length = int.from_bytes(raw[offset + 4:offset + 8], "little")
    if not (8 <= length <= 20_000_000 and 5 <= version <= 50):
        return None
    if signature in (b"FWS", b"GFX"):
        if offset + length > len(raw):
            return None
        return b"FWS" + raw[offset + 3:offset + length]
    if signature == b"CWS":
        stream = zlib.decompressobj()
        body = stream.decompress(raw[offset + 8:]) + stream.flush()
        if not stream.eof:
            return None
        data = b"FWS" + raw[offset + 3:offset + 8] + body
        return data[:length] if len(data) >= length else None
    return None


def scan_file(path):
    raw = Path(path).read_bytes()
    offsets = set()
    for signature in (b"FWS", b"CWS", b"GFX"):
        start = 0
        while True:
            offset = raw.find(signature, start)
            if offset < 0:
                break
            start = offset + 1
            offsets.add(offset)

    modules = {}
    movie_count = 0
    parser_errors = []
    for offset in sorted(offsets):
        try:
            swf = _decode_swf(raw, offset)
            if swf is None:
                continue
            payloads = [payload for code, payload in _iter_tags(swf) if code == avm2.TAG_DO_ABC]
            if not payloads:
                continue
            movie_count += 1
            for payload in payloads:
                end = payload.find(b"\x00", 4)
                abc_raw = payload[end + 1:] if end >= 0 else payload
                digest = hashlib.sha256(abc_raw).hexdigest()
                if digest in modules:
                    continue
                module = avm2.parse_doabc(payload, f"offset 0x{offset:X}")
                modules[digest] = module
                if module.error:
                    parser_errors.append({"offset": offset, "module": module.name, "error": module.error})
        except Exception as exc:
            parser_errors.append({"offset": offset, "module": "<scan>", "error": str(exc)})

    sites = []
    for module in modules.values():
        sites.extend(native.extract_callback_sites(module))
    summaries = native.summarize_callback_sites(sites)
    category_counts = Counter(site.category for site in sites)
    return {
        "schema": 1,
        "input": str(Path(path)),
        "embedded_movies_with_doabc": movie_count,
        "unique_abc_modules": len(modules),
        "parser_errors": parser_errors,
        "callback_names": len(summaries),
        "call_sites": len(sites),
        "implemented_names": sum(1 for item in summaries if item.implemented),
        "categories": dict(sorted(category_counts.items())),
        "callbacks": [
            {
                "name": item.name,
                "category": item.category,
                "behavior": item.behavior,
                "return_policy": item.return_policy,
                "implemented": item.implemented,
                "count": item.count,
                "bridges": list(item.bridges),
                "argument_samples": native._json_safe(item.argument_samples),
                "sites": [
                    {
                        "module": site.module,
                        "source": site.source,
                        "class": site.class_name,
                        "method": site.method_name,
                        "method_index": site.method_index,
                        "offset": site.offset,
                        "bridge": site.bridge,
                        "arguments": native._json_safe(site.arguments),
                    }
                    for site in item.sites
                ],
            }
            for item in summaries
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="SWF/GFX or a container such as UIPak.pak")
    parser.add_argument("--json", dest="json_path", help="write the complete report to this JSON file")
    parser.add_argument("--top", type=int, default=25, help="number of callback counts to print")
    args = parser.parse_args(argv)
    result = scan_file(args.input)
    print(f"Movies with DoABC: {result['embedded_movies_with_doabc']}")
    print(f"Unique ABC modules: {result['unique_abc_modules']}")
    print(f"Parser errors: {len(result['parser_errors'])}")
    print(f"Callback names: {result['callback_names']}")
    print(f"Static call sites: {result['call_sites']}")
    print(f"Classified names: {result['implemented_names']}")
    print("\nTop callbacks:")
    for item in sorted(result["callbacks"], key=lambda value: (-value["count"], value["name"]))[:max(0, args.top)]:
        print(f"{item['count']:6}  {item['category']:<16}  {item['name']}")
    if args.json_path:
        output = Path(args.json_path)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
