"""Export exact ``normal_clip`` bind/hierarchy and render matrices.

Installed after ``anim_normal_clip_pose_patch``. The exported matrices match the
CSkelPose composition path, but do not include the external model/world transform
or Blender basis conversion.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anim_normal_clip_setup_patch as setup_patch
import model_animation_refs_patch as anim_patch
from anim_normal_clip_bind import compose_normal_clip_bind_hierarchy

NORMAL_CLIP_CLASS = 0x81


def _safe_name(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in "._-" else "_"
        for char in str(value or "normal_clip")
    ).strip("._") or "normal_clip"


def _read_skeleton_document(root: Path) -> tuple[dict[str, Any] | None, str]:
    candidates: list[Path] = []
    candidates.extend(root.glob("source/skel/*.json"))
    candidates.extend(root.glob("debug/skeleton_debug.json"))
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
        data = setup_patch._read_json(path)
        if not isinstance(data, dict):
            continue
        nodes = data.get("nodes")
        skin = data.get("skin_node_indices")
        if not isinstance(nodes, list) or not nodes or not isinstance(skin, list):
            continue
        try:
            relative = str(path.relative_to(root)).replace("\\", "/")
        except Exception:
            relative = str(path)
        return data, relative
    return None, ""


def _matrix_3x4(matrix) -> list[list[float]]:
    return [[float(value) for value in row] for row in matrix[:3]]


def _compact_document(result, node_names: list[str]) -> dict[str, Any]:
    return {
        "type": result.type,
        "frame_count": result.frame_count,
        "node_count": result.node_count,
        "skin_bone_count": result.skin_bone_count,
        "layout": {
            "relative_start": result.layout.relative_start,
            "hierarchy_start": result.layout.hierarchy_start,
            "active_anchor": result.layout.active_anchor,
        },
        "skin_node_indices": result.skin_node_indices,
        "skin_node_names": [
            node_names[index] if 0 <= index < len(node_names) else f"<node_{index}>"
            for index in result.skin_node_indices
        ],
        "base_absolute_matrices_3x4": [
            _matrix_3x4(matrix) for matrix in result.base_absolute_matrices
        ],
        "base_absolute_inverse_matrices_3x4": [
            _matrix_3x4(matrix) for matrix in result.base_absolute_inverse_matrices
        ],
        "frames": [
            {
                "frame": frame.frame,
                "absolute_node_matrices_3x4": [
                    _matrix_3x4(matrix) for matrix in frame.absolute_node_matrices
                ],
                "render_matrices_3x4": [
                    _matrix_3x4(matrix) for matrix in frame.render_matrices
                ],
            }
            for frame in result.frames
        ],
        "skeleton_remap_applied": result.skeleton_remap_applied,
        "external_model_transform_applied": False,
        "blender_basis_applied": False,
        "notes": result.notes,
    }


def _summary(result) -> dict[str, Any]:
    return {
        "type": result.type,
        "frame_count": result.frame_count,
        "node_count": result.node_count,
        "skin_bone_count": result.skin_bone_count,
        "absolute_node_frames": result.frame_count * result.node_count,
        "render_bone_frames": result.frame_count * result.skin_bone_count,
        "relative_start": result.layout.relative_start,
        "hierarchy_start": result.layout.hierarchy_start,
        "active_anchor": result.layout.active_anchor,
        "skeleton_remap_applied": result.skeleton_remap_applied,
        "status": "ok",
    }


def _enrich_probe_set(
    result: dict[str, Any],
    parsed: dict[str, Any],
    package_dir: str | Path,
    require_store: Any,
) -> dict[str, Any]:
    root = Path(package_dir)
    skeleton, skeleton_file = _read_skeleton_document(root)
    node_names = [
        str(node.get("name", "")) if isinstance(node, dict) else ""
        for node in (skeleton.get("nodes") if skeleton else [])
    ]
    output_dir = root / "debug" / "anim_normal_clip_bind"
    integration = {
        "version": 1,
        "status": "no_skeleton" if skeleton is None else "ok",
        "skeleton_file": skeleton_file,
        "node_count": len(node_names),
        "normal_clip_count": 0,
        "parsed_count": 0,
        "errors": [],
        "documentation": "ANIM_UPDATE.md",
    }

    if skeleton is not None:
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
                hierarchy = compose_normal_clip_bind_hierarchy(
                    asset,
                    skeleton,
                    apply_skeleton_remap=False,
                    strict=True,
                )
                base_name = _safe_name(
                    item.get("char_animation_name")
                    or item.get("name")
                    or item.get("entry_name")
                    or uuid_hex
                )
                hierarchy_path = output_dir / f"{base_name}__{uuid_hex}.normal_clip_bind.json"
                hierarchy_path.parent.mkdir(parents=True, exist_ok=True)
                hierarchy_path.write_text(
                    json.dumps(_compact_document(hierarchy, node_names), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                    newline="\n",
                )
                relative = str(hierarchy_path.relative_to(root)).replace("\\", "/")
                summary = _summary(hierarchy)
                probe["normal_clip_bind_file"] = relative
                probe["normal_clip_bind_summary"] = summary
                probe["normal_clip_bind_status"] = "ok"
                probe["track_decode"] = {
                    "version": 8,
                    "status": "pending:normal_clip_external_root_and_blender_basis",
                    "frame_count_guess": hierarchy.frame_count,
                    "group_count": 0,
                    "groups": [],
                    "primary_group_index": None,
                    "primary_timeline_frame_count": 0,
                    "note": (
                        "ANIM values, interpolation, bind composition, 81-node hierarchy "
                        "and 60 render matrices are decoded. External model/root transform, "
                        "capture time alignment and Blender basis/F-curves remain pending."
                    ),
                }
                item["normal_clip_bind_status"] = "ok"
                item["normal_clip_bind_file"] = relative
                item["normal_clip_bind_frame_count"] = hierarchy.frame_count
                integration["parsed_count"] += 1
            except (ValueError, IndexError, OverflowError) as exc:
                message = str(exc)
                probe["normal_clip_bind_status"] = "error"
                probe["normal_clip_bind_error"] = message
                item["normal_clip_bind_status"] = "error"
                item["normal_clip_bind_error"] = message
                integration["errors"].append({"uuid_hex": uuid_hex, "error": message})
            setup_patch._write_json(probe_path, probe)

    if integration["errors"]:
        integration["status"] = "partial" if integration["parsed_count"] else "error"
    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        result["summary"] = summary
    summary["normal_clip_bind"] = integration
    result["normal_clip_bind"] = integration
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
            result["normal_clip_bind_error"] = str(exc)
            return result

    anim_patch._write_animation_probe_set = write_animation_probe_set
