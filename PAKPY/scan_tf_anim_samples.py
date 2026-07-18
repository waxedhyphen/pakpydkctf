"""Scan exported character packages with the verified TF ANIM decoder."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any

import anim_tf_codec as codec


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def find_skeleton(package: Path) -> tuple[dict[str, Any] | None, Path | None]:
    candidates = list(package.glob("source/skel/*.json"))
    candidates.extend(package.glob("models/*/debug/skeleton_debug.json"))
    candidates.extend(package.glob("**/source/skel/*.json"))
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        value = read_json(path)
        if value and value.get("nodes"):
            return value, path
    return None, None


def package_roots(root: Path) -> list[Path]:
    roots = [path for path in root.rglob("*_character_package") if path.is_dir()]
    if root.is_dir() and root.name.endswith("_character_package"):
        roots.insert(0, root)
    unique: list[Path] = []
    seen: set[Path] = set()
    for item in roots:
        resolved = item.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(item)
    return sorted(unique)


def scan_package(package: Path) -> dict[str, Any]:
    skeleton, skeleton_path = find_skeleton(package)
    records: list[dict[str, Any]] = []
    for anim_path in sorted(package.rglob("*.anim")):
        rel = anim_path.relative_to(package).as_posix()
        try:
            asset = anim_path.read_bytes()
            envelope = codec.parse_envelope(asset)
            record: dict[str, Any] = {
                "file": rel,
                "family": envelope.family,
                "frame_count_hint": envelope.frame_count_hint,
                "body_size": len(envelope.body),
            }
            if skeleton is None:
                record["status"] = "no_skeleton"
            else:
                result = codec.decode_asset(asset, skeleton)
                record.update({
                    "status": result.get("status", ""),
                    "active_node_indices": result.get("active_node_indices", []),
                    "active_node_names": result.get("active_node_names", []),
                })
        except Exception as exc:
            record = {"file": rel, "status": "error", "error": str(exc)}
        records.append(record)
    family_counts = Counter(record.get("family", "unknown") for record in records)
    status_counts = Counter(record.get("status", "unknown") for record in records)
    return {
        "package": str(package),
        "skeleton": str(skeleton_path.relative_to(package)) if skeleton_path else "",
        "node_count": len((skeleton or {}).get("nodes") or []),
        "animation_count": len(records),
        "family_counts": dict(sorted(family_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "animations": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Folder containing exported character packages")
    parser.add_argument("--output", type=Path, default=Path("tf_anim_scan_report.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    packages = package_roots(root)
    report = {
        "version": 1,
        "root": str(root),
        "package_count": len(packages),
        "packages": [scan_package(package) for package in packages],
    }
    overall_families: Counter[str] = Counter()
    overall_statuses: Counter[str] = Counter()
    total = 0
    for package in report["packages"]:
        total += int(package["animation_count"])
        overall_families.update(package["family_counts"])
        overall_statuses.update(package["status_counts"])
    report["animation_count"] = total
    report["family_counts"] = dict(sorted(overall_families.items()))
    report["status_counts"] = dict(sorted(overall_statuses.items()))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps({
        "packages": len(packages),
        "animations": total,
        "families": report["family_counts"],
        "statuses": report["status_counts"],
        "output": str(args.output.resolve()),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
