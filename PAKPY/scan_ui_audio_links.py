"""Scan Scaleform UI sound calls and resolve them to CAUD/CSMP assets.

Usage:
    python scan_ui_audio_links.py UIPak.pak \
        --require PreLoadPak.pak --require MiscData.pak \
        --decode --json ui_audio_links.json

The scanner does not execute AVM2 and never plays audio.  Optional decoding validates the
first CSMP variant of every statically named sound and reports PCM metadata only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from types import SimpleNamespace

from pak_core import get_entry_asset, parse_pak
from scan_ui_native_callbacks import scan_file as scan_native_callbacks
from ui_audio_codec import decode_csmp_pcm
import ui_browser_audio_preview as audio
import ui_browser_native_callback_patch as native
from ui_browser_native_callback_catalog import compact_name


def _owner(primary, required):
    store = SimpleNamespace(required_paks=[
        {"path": item.get("path", "Require"), "parsed": item}
        for item in required
    ])
    return SimpleNamespace(parsed=primary, require_store=store)


def _explicit_sound_names(native_report):
    values = set()
    call_sites = 0
    for item in native_report.get("callbacks", ()):
        if compact_name(item.get("name")) not in ("playsound", "debugsoundplay"):
            continue
        call_sites += int(item.get("count", 0))
        for sample in item.get("argument_samples", ()):
            for value in sample:
                if isinstance(value, str) and value != native._DYNAMIC_ARGUMENT:
                    values.add(value)
    return values, call_sites


def _record_json(record):
    return {
        "name": record.name,
        "source": record.source_label,
        "caud_uuid": record.caud_uuid,
        "csmp_refs": list(record.csmp_refs),
        "loop": record.loop,
        "volume": record.caud_info.get("volume"),
        "gain": record.caud_info.get("gain"),
        "parser_error": record.parser_error,
    }


def _find_csmp(owner, record, ref):
    for parsed, _label in audio.source_items(owner):
        entry = (parsed.get("uuid_to_entry", {}) or {}).get(ref)
        if entry is not None:
            return parsed, entry
    return None, None


def scan_audio_links(primary_path, require_paths=(), decode=False):
    primary = parse_pak(primary_path)
    required = [parse_pak(path) for path in require_paths]
    owner = _owner(primary, required)
    catalog = audio.build_audio_catalog(owner)
    by_name = {}
    for record in catalog:
        by_name.setdefault(record.normalized_name, record)

    native_report = scan_native_callbacks(primary_path)
    explicit, audio_call_sites = _explicit_sound_names(native_report)
    normalized = {}
    for value in sorted(explicit):
        normalized.setdefault(compact_name(value), value)

    links = []
    unresolved = []
    decode_errors = []
    decoded = []
    for key, source_name in sorted(normalized.items()):
        record = by_name.get(key)
        # Shipped ActionScript contains one legacy MP3 library path.  Resolve by stem only
        # when an actual CAUD with that exact normalized stem exists; never guess otherwise.
        if record is None and source_name.lower().endswith(".mp3"):
            record = by_name.get(compact_name(Path(source_name).stem))
        if record is None:
            unresolved.append(source_name)
            links.append({"actionscript": source_name, "resolved": False})
            continue
        item = {"actionscript": source_name, "resolved": True, **_record_json(record)}
        links.append(item)
        if not decode:
            continue
        if not record.csmp_refs:
            decode_errors.append({"sound": record.name, "error": "CAUD besitzt keine CSMP-Referenz"})
            continue
        ref = record.csmp_refs[0]
        parsed, entry = _find_csmp(owner, record, ref)
        if entry is None:
            decode_errors.append({"sound": record.name, "csmp": ref, "error": "CSMP nicht gefunden"})
            continue
        try:
            _channels, info = decode_csmp_pcm(get_entry_asset(parsed, entry))
            metadata = {
                "sound": record.name,
                "csmp": ref,
                "sample_rate": info.sample_rate,
                "source_channels": info.source_channels,
                "output_channels": info.output_channels,
                "sample_count": info.sample_count,
                "duration_seconds": info.duration_seconds,
                "loop": info.loop,
            }
            decoded.append(metadata)
            item["decoded"] = metadata
        except Exception as exc:
            error = {"sound": record.name, "csmp": ref, "error": str(exc)}
            decode_errors.append(error)
            item["decode_error"] = str(exc)

    pak_counts = {}
    for parsed in (primary, *required):
        label = Path(parsed.get("path", "PAK")).name
        pak_counts[label] = {
            "CAUD": sum(str(entry.get("type", "")).strip().upper() == "CAUD" for entry in parsed.get("entries", ())),
            "CSMP": sum(str(entry.get("type", "")).strip().upper() == "CSMP" for entry in parsed.get("entries", ())),
        }
    return {
        "schema": 1,
        "primary": str(Path(primary_path)),
        "requires": [str(Path(path)) for path in require_paths],
        "pak_counts": pak_counts,
        "catalog": {
            "records": len(catalog),
            "normalized_names": len(by_name),
            "caud_parser_fallbacks": sum(bool(item.parser_error) for item in catalog),
        },
        "callbacks": {
            "audio_call_sites": audio_call_sites,
            "explicit_strings": len(explicit),
            "normalized_names": len(normalized),
            "resolved": len(normalized) - len(unresolved),
            "unresolved": unresolved,
        },
        "decode": {
            "enabled": bool(decode),
            "success": len(decoded),
            "errors": decode_errors,
            "sample_rates": dict(sorted(Counter(item["sample_rate"] for item in decoded).items())),
            "source_channels": dict(sorted(Counter(item["source_channels"] for item in decoded).items())),
            "duration_min": min((item["duration_seconds"] for item in decoded), default=0.0),
            "duration_max": max((item["duration_seconds"] for item in decoded), default=0.0),
            "duration_total": sum(item["duration_seconds"] for item in decoded),
        },
        "links": links,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="primary UI PAK, normally UIPak.pak")
    parser.add_argument("--require", action="append", default=[], help="required PAK; may be repeated")
    parser.add_argument("--decode", action="store_true", help="decode the first CSMP variant for every resolved static sound")
    parser.add_argument("--json", dest="json_path", help="write complete report as JSON")
    args = parser.parse_args(argv)
    result = scan_audio_links(args.input, args.require, args.decode)
    callback = result["callbacks"]
    decode = result["decode"]
    print(f"CAUD catalog: {result['catalog']['records']} records / {result['catalog']['normalized_names']} names")
    print(f"Audio call sites: {callback['audio_call_sites']}")
    print(f"Static names: {callback['resolved']} resolved / {callback['normalized_names']} normalized")
    if callback["unresolved"]:
        print("Unresolved:")
        for value in callback["unresolved"]:
            print(f"  {value}")
    if decode["enabled"]:
        print(f"Decoded: {decode['success']} / {callback['resolved']}; errors: {len(decode['errors'])}")
    if args.json_path:
        output = Path(args.json_path)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {output}")
    return 0 if not decode["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
