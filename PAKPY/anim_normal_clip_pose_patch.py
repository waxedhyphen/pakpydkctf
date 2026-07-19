"""Export evaluated ``normal_clip`` local poses into standalone JSON files.

Installed after ``anim_normal_clip_values_patch``.  This layer evaluates the
verified interpolation stage but deliberately does not multiply by the SKEL bind
pose or claim Blender-ready matrices.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anim_normal_clip_setup_patch as setup_patch
import model_animation_refs_patch as anim_patch
from anim_normal_clip_pose import evaluate_normal_clip_local_pose

NORMAL_CLIP_CLASS = 0x81


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )


def _safe_name(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in str(value or "normal_clip")
    ).strip("._") or "normal_clip"


def _pose_summary(pose: Any) -> dict[str, Any]:
    return {
        "type": pose.type,
        "frame_count": pose.frame_count,
        "node_count": pose.node_count,
        "evaluated_node_frames": pose.frame_count * pose.node_count,
        "skeleton_remap_applied": pose.skeleton_remap_applied,
        "status": "ok",
    }


def _enrich_probe_set(
    result: dict[str, Any],
    parsed: dict[str, Any],
    package_dir: str | Path,
    require_store: Any,
) -> dict[str, Any]:
    root = Path(package_dir)
    node_names, skeleton_file = setup_patch._find_skeleton(root)
    output_dir = root / "debug" / "anim_normal_clip_pose"
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
            if asset is None or setup_patch._control_class(asset) != NORMAL_CLIP_CLASS:
                continue

            integration["normal_clip_count"] += 1
            probe_path = root / probe_rel
            probe = setup_patch._read_json(probe_path)
            if probe is None:
                integration["errors"].append(
                    {"uuid_hex": uuid_hex, "error": f"probe JSON unreadable: {probe_rel}"}
                )
                continue

            try:
                pose = evaluate_normal_clip_local_pose(
                    asset,
                    len(node_names),
                    strict=True,
                )
                base_name = _safe_name(
                    item.get("char_animation_name")
                    or item.get("name")
                    or item.get("entry_name")
                    or uuid_hex
                )
                pose_path = output_dir / f"{base_name}__{uuid_hex}.normal_clip_pose.json"
                _write_json(pose_path, pose.to_dict(node_names))
                relative = str(pose_path.relative_to(root)).replace("\\", "/")
                summary = _pose_summary(pose)
                probe["normal_clip_pose_file"] = relative
                probe["normal_clip_pose_summary"] = summary
                probe["normal_clip_pose_status"] = "ok"
                probe["track_decode"] = {
                    "version": 7,
                    "status": "pending:normal_clip_bind_composition",
                    "frame_count_guess": pose.frame_count,
                    "group_count": 0,
                    "groups": [],
                    "primary_group_index": None,
                    "primary_timeline_frame_count": 0,
                    "note": (
                        "Local identity-base TRS poses are evaluated exactly. "
                        "SKEL bind/hierarchy/root/Blender composition remains pending."
                    ),
                }
                item["normal_clip_pose_status"] = "ok"
                item["normal_clip_pose_file"] = relative
                item["normal_clip_pose_frame_count"] = pose.frame_count
                integration["parsed_count"] += 1
            except (ValueError, IndexError, OverflowError) as exc:
                message = str(exc)
                probe["normal_clip_pose_status"] = "error"
                probe["normal_clip_pose_error"] = message
                item["normal_clip_pose_status"] = "error"
                item["normal_clip_pose_error"] = message
                integration["errors"].append({"uuid_hex": uuid_hex, "error": message})
            setup_patch._write_json(probe_path, probe)

    if integration["errors"]:
        integration["status"] = "partial" if integration["parsed_count"] else "error"

    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        result["summary"] = summary
    summary["normal_clip_pose"] = integration
    result["normal_clip_pose"] = integration

    summary_rel = str(result.get("summary_file") or "")
    if summary_rel:
        setup_patch._write_json(root / summary_rel, summary)
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
            result["normal_clip_pose_error"] = str(exc)
            return result

    anim_patch._write_animation_probe_set = write_animation_probe_set
