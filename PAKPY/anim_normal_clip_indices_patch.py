"""Install the verified normal_clip LoadIdxData parser into export probes.

This patch intentionally does not fabricate animation samples. It replaces the
old marker-based normal_clip track claim with a truthful pending status, then
adds exact animated/constant node lists once the package skeleton is available.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anim_raw_probe_patch as raw_patch
import model_animation_refs_patch as anim_patch
from anim_normal_clip_indices import LoadIdxDataError, parse_load_idx_data


NORMAL_CLIP_CLASS = 0x81
TRACK_DECODE_VERSION = 4


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )


def _find_skeleton(package_dir: Path) -> tuple[list[str], str]:
    root = Path(package_dir)
    candidates: list[Path] = []
    candidates.extend(root.glob("debug/skeleton_debug.json"))
    candidates.extend(root.glob("source/skel/*.json"))
    candidates.extend(root.glob("models/*/debug/skeleton_debug.json"))
    candidates.extend(root.glob("**/source/skel/*.json"))

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
            rel = str(path.relative_to(root)).replace("\\", "/")
        except Exception:
            rel = str(path)
        return names, rel
    return [], ""


def _pending_normal_clip_track_decode(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": TRACK_DECODE_VERSION,
        "status": "pending:normal_clip_frame_decode",
        "frame_count_guess": int(probe.get("frame_count_guess") or 0),
        "group_count": 0,
        "groups": [],
        "primary_group_index": None,
        "primary_timeline_frame_count": 0,
        "note": (
            "LoadIdxData/node-channel structure is decoded. LoadPairData, ranges, "
            "LoadSetupFrames and ProcessFrame are still required for real samples."
        ),
    }


def _control_class(asset: bytes) -> int:
    if len(asset) < 0x2C:
        return -1
    return (int.from_bytes(asset[0x28:0x2C], "big") >> 24) & 0xFF


def _enrich_probe_set(
    result: dict[str, Any],
    parsed: dict[str, Any],
    package_dir: str | Path,
    require_store: Any,
) -> dict[str, Any]:
    root = Path(package_dir)
    node_names, skeleton_file = _find_skeleton(root)
    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        result["summary"] = summary

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

            asset, _anim_entry, _source, _source_path = anim_patch._resolve_anim_asset(
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
                index_data = parse_load_idx_data(asset, len(node_names), strict=True)
                probe["normal_clip_indices"] = index_data.to_dict(node_names)
                probe["normal_clip_indices_status"] = "ok"
                probe["normal_clip_indices_skeleton_file"] = skeleton_file
                probe["track_decode"] = _pending_normal_clip_track_decode(probe)
                item["normal_clip_indices_status"] = "ok"
                item["normal_clip_load_pair_data_file_offset"] = (
                    index_data.load_pair_data_file_offset
                )
                integration["parsed_count"] += 1
            except (LoadIdxDataError, ValueError) as exc:
                message = str(exc)
                probe["normal_clip_indices_status"] = "error"
                probe["normal_clip_indices_error"] = message
                item["normal_clip_indices_status"] = "error"
                item["normal_clip_indices_error"] = message
                integration["errors"].append({"uuid_hex": uuid_hex, "error": message})
            _write_json(probe_path, probe)

    if integration["errors"]:
        integration["status"] = "partial" if integration["parsed_count"] else "error"
    summary["normal_clip_indices"] = integration
    result["normal_clip_indices"] = integration

    summary_rel = str(result.get("summary_file") or "")
    if summary_rel:
        _write_json(root / summary_rel, summary)
    return result


def install(App) -> None:
    old_track_decode = raw_patch._build_track_decode

    def build_track_decode(probe: dict[str, Any], body: bytes | None = None):
        if probe.get("raw_family") == "normal_clip":
            return _pending_normal_clip_track_decode(probe)
        return old_track_decode(probe, body)

    raw_patch._build_track_decode = build_track_decode

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
            result["normal_clip_indices_error"] = str(exc)
            return result

    anim_patch._write_animation_probe_set = write_animation_probe_set
