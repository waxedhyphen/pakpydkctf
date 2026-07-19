"""Export verified normal_clip setup data into ANIM probe JSON files.

Installed after anim_normal_clip_indices_patch. The patch decodes only the
constructor/setup stage and deliberately leaves animated frame samples pending.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import model_animation_refs_patch as anim_patch
from anim_normal_clip_setup import parse_normal_clip_setup

NORMAL_CLIP_CLASS = 0x81


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )


def _find_skeleton(package_dir: Path) -> tuple[list[str], str]:
    candidates: list[Path] = []
    candidates.extend(package_dir.glob("debug/skeleton_debug.json"))
    candidates.extend(package_dir.glob("source/skel/*.json"))
    candidates.extend(package_dir.glob("models/*/debug/skeleton_debug.json"))
    candidates.extend(package_dir.glob("**/source/skel/*.json"))

    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        data = _read_json(path)
        nodes = data.get("nodes") if data else None
        if not isinstance(nodes, list) or not nodes:
            continue
        names = [
            str(node.get("name", "")) if isinstance(node, dict) else ""
            for node in nodes
        ]
        try:
            relative = str(path.relative_to(package_dir)).replace("\\", "/")
        except Exception:
            relative = str(path)
        return names, relative
    return [], ""


def _control_class(asset: bytes) -> int:
    if len(asset) < 0x2C:
        return -1
    return (int.from_bytes(asset[0x28:0x2C], "big") >> 24) & 0xFF


def _setup_document(setup, node_names: list[str]) -> dict[str, Any]:
    document = setup.to_dict(node_names)
    document.pop("indices", None)
    return document


def _enrich_probe_set(
    result: dict[str, Any],
    parsed: dict[str, Any],
    package_dir: str | Path,
    require_store: Any,
) -> dict[str, Any]:
    root = Path(package_dir)
    node_names, skeleton_file = _find_skeleton(root)
    integration = {
        "version": 1,
        "status": "no_skeleton" if not node_names else "ok",
        "skeleton_file": skeleton_file,
        "node_count": len(node_names),
        "normal_clip_count": 0,
        "parsed_count": 0,
        "errors": [],
        "documentation": "ANIM_UPDATE.md",
    }

    if node_names:
        for item in result.get("animations") or []:
            if not isinstance(item, dict) or not item.get("resolved"):
                continue
            uuid_hex = str(item.get("uuid_hex") or "")
            probe_rel = str(item.get("probe21_file") or "")
            if not uuid_hex or not probe_rel:
                continue
            asset, _entry, _source, _source_path = anim_patch._resolve_anim_asset(
                parsed, uuid_hex, require_store
            )
            if asset is None or _control_class(asset) != NORMAL_CLIP_CLASS:
                continue

            integration["normal_clip_count"] += 1
            probe_path = root / probe_rel
            probe = _read_json(probe_path)
            if probe is None:
                integration["errors"].append(
                    {"uuid_hex": uuid_hex, "error": f"probe JSON unreadable: {probe_rel}"}
                )
                continue

            try:
                setup = parse_normal_clip_setup(asset, len(node_names), strict=True)
                probe["normal_clip_setup"] = _setup_document(setup, node_names)
                probe["normal_clip_setup_status"] = "ok"
                probe["normal_clip_setup_skeleton_file"] = skeleton_file
                item["normal_clip_setup_status"] = "ok"
                item["normal_clip_frame_data_file_offset"] = setup.frame_data_file_offset
                integration["parsed_count"] += 1
            except (ValueError, IndexError, OverflowError) as exc:
                message = str(exc)
                probe["normal_clip_setup_status"] = "error"
                probe["normal_clip_setup_error"] = message
                item["normal_clip_setup_status"] = "error"
                item["normal_clip_setup_error"] = message
                integration["errors"].append({"uuid_hex": uuid_hex, "error": message})
            _write_json(probe_path, probe)

    if integration["errors"]:
        integration["status"] = "partial" if integration["parsed_count"] else "error"

    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        result["summary"] = summary
    summary["normal_clip_setup"] = integration
    result["normal_clip_setup"] = integration

    summary_rel = str(result.get("summary_file") or "")
    if summary_rel:
        _write_json(root / summary_rel, summary)
    return result


def install(App) -> None:
    original_write_probe_set = anim_patch._write_animation_probe_set

    def write_animation_probe_set(
        parsed,
        entry,
        package_dir,
        refs,
        require_store=None,
        root_name="char",
    ):
        result = original_write_probe_set(
            parsed,
            entry,
            package_dir,
            refs,
            require_store=require_store,
            root_name=root_name,
        )
        try:
            return _enrich_probe_set(result, parsed, package_dir, require_store)
        except Exception as exc:
            result["normal_clip_setup_error"] = str(exc)
            return result

    anim_patch._write_animation_probe_set = write_animation_probe_set
