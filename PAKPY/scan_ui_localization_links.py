"""Scan MSBT language bundles and exact UI runtime text links.

Usage:
    python scan_ui_localization_links.py UIPak.pak \
      --require MiscData.pak --json ui_localization_links.json

The scanner is read-only. It does not execute AVM2 and never guesses similar labels.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from pak_core import parse_pak
import ui_browser_avm2_patch as avm2
import ui_browser_localization as localization
import ui_browser_native_callback_patch as native
from scan_ui_native_callbacks import _decode_swf, _iter_tags


def _owner(primary, required):
    return SimpleNamespace(
        parsed=primary,
        require_store=SimpleNamespace(required_paks=[
            {"path": item.get("path", "Require"), "parsed": item}
            for item in required
        ]),
    )


def _modules(path):
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
    modules = {}
    errors = []
    movie_count = 0
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
                    errors.append({"offset": offset, "module": module.name, "error": module.error})
        except Exception as exc:
            errors.append({"offset": offset, "module": "<scan>", "error": str(exc)})
    return movie_count, tuple(modules.values()), errors


def _catalog_label(catalog, value):
    for candidate in localization.text_id_candidates(value):
        _bundle, label = localization._split_bundle_candidate(candidate, catalog)
        canonical = localization._canonical_label(catalog, label)
        if canonical:
            return canonical
    return ""


def scan_localization(primary_path, require_paths=()):
    primary = parse_pak(primary_path)
    required = [parse_pak(path) for path in require_paths]
    owner = _owner(primary, required)
    catalog = localization.build_localization_catalog(owner)
    movie_count, modules, parser_errors = _modules(primary_path)

    abc_counts = Counter()
    abc_sources = defaultdict(set)
    callback_counts = Counter()
    callback_sources = defaultdict(set)
    callback_sites = []
    for module in modules:
        abc = getattr(module, "abc", None)
        if abc is not None:
            for value in tuple(getattr(abc, "strings", ()) or ()):
                if not isinstance(value, str) or not value:
                    continue
                label = _catalog_label(catalog, value)
                if label:
                    abc_counts[label] += 1
                    if len(abc_sources[label]) < 32:
                        abc_sources[label].add(str(getattr(module, "name", "<unnamed>")))
        for site in native.extract_callback_sites(module):
            for value in tuple(site.arguments or ()):
                if not isinstance(value, str) or value == native._DYNAMIC_ARGUMENT:
                    continue
                label = _catalog_label(catalog, value)
                if not label:
                    continue
                callback_counts[label] += 1
                callback_sources[label].add(site.callback)
                callback_sites.append({
                    "text_id": label, "callback": site.callback,
                    "class": site.class_name, "method": site.method_name,
                    "offset": site.offset, "value": value,
                })

    language_counts = Counter(record.language for record in catalog["records"])
    labels_by_language = defaultdict(set)
    bundles_by_language = defaultdict(lambda: defaultdict(int))
    label_bundles = defaultdict(set)
    for record in catalog["records"]:
        labels_by_language[record.language].add(record.label)
        bundles_by_language[record.language][record.bundle] += 1
        label_bundles[record.label].add(record.bundle)
    all_labels = set().union(*labels_by_language.values()) if labels_by_language else set()
    missing = {
        language: sorted(all_labels - labels)
        for language, labels in labels_by_language.items() if all_labels - labels
    }
    duplicate_labels = {
        label: sorted(bundles)
        for label, bundles in label_bundles.items() if len(bundles) > 1
    }
    safe_abc_counts = {
        label: count for label, count in abc_counts.items()
        if localization.label_is_unambiguous(catalog, label)
    }
    safe_callback_counts = {
        label: count for label, count in callback_counts.items()
        if localization.label_is_unambiguous(catalog, label)
    }
    return {
        "schema": 1,
        "primary": str(Path(primary_path)),
        "requires": [str(Path(path)) for path in require_paths],
        "msbt": {
            "documents": len(catalog["documents"]),
            "records": len(catalog["records"]),
            "languages": dict(language_counts),
            "unique_labels": len(all_labels),
            "labels_per_language": {key: len(value) for key, value in sorted(labels_by_language.items())},
            "bundles_per_language": {
                key: dict(sorted(value.items())) for key, value in sorted(bundles_by_language.items())
            },
            "duplicate_labels_across_bundles": len(duplicate_labels),
            "duplicate_label_examples": dict(list(sorted(duplicate_labels.items()))[:100]),
            "missing_labels": missing,
            "parser_errors": list(catalog["errors"]),
            "documents_detail": list(catalog["documents"]),
        },
        "avm2": {
            "embedded_movies_with_doabc": movie_count,
            "unique_abc_modules": len(modules),
            "parser_errors": parser_errors,
            "linked_labels": len(abc_counts),
            "linked_string_occurrences": sum(abc_counts.values()),
            "runtime_safe_labels": len(safe_abc_counts),
            "runtime_safe_occurrences": sum(safe_abc_counts.values()),
            "links": [
                {"text_id": label, "count": count, "modules": sorted(abc_sources[label])}
                for label, count in abc_counts.most_common()
            ],
        },
        "callbacks": {
            "linked_labels": len(callback_counts),
            "linked_call_sites": sum(callback_counts.values()),
            "runtime_safe_labels": len(safe_callback_counts),
            "runtime_safe_call_sites": sum(safe_callback_counts.values()),
            "links": [
                {"text_id": label, "count": count, "callbacks": sorted(callback_sources[label])}
                for label, count in callback_counts.most_common()
            ],
            "sites": callback_sites,
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="primary UI PAK, normally UIPak.pak")
    parser.add_argument("--require", action="append", default=[], help="required PAK; may be repeated")
    parser.add_argument("--json", dest="json_path", help="write the complete report as JSON")
    args = parser.parse_args(argv)
    result = scan_localization(args.input, args.require)
    msbt = result["msbt"]
    avm2_result = result["avm2"]
    callbacks = result["callbacks"]
    print(f"MSBT documents: {msbt['documents']}")
    print(f"MSBT records: {msbt['records']}")
    print(f"Languages: {len(msbt['languages'])}")
    print(f"Unique labels: {msbt['unique_labels']}")
    print(f"MSBT parser errors: {len(msbt['parser_errors'])}")
    print(f"ABC modules: {avm2_result['unique_abc_modules']}")
    print(f"Exact ABC text links: {avm2_result['linked_labels']} labels / {avm2_result['linked_string_occurrences']} occurrences")
    print(f"Runtime-safe ABC links: {avm2_result['runtime_safe_labels']} labels / {avm2_result['runtime_safe_occurrences']} occurrences")
    print(f"Exact callback links: {callbacks['linked_labels']} labels / {callbacks['linked_call_sites']} call sites")
    if args.json_path:
        output = Path(args.json_path)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {output}")
    return 0 if not msbt["parser_errors"] and not avm2_result["parser_errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
