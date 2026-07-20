"""Host-side orchestration for the lean CHAR -> Blender Action pipeline."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import skeletal_tail_patch


BATCH_MANIFEST_NAME = "animation_batch_manifest.json"
BATCH_REPORT_NAME = "blender_character_animation_batch_report.json"
DEFAULT_TIMEOUT_SECONDS = 900


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def _relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")


def skeleton_signature(document: dict[str, Any]) -> str:
    """Hash only animation-relevant rest-pose and hierarchy data."""
    nodes = []
    for node in document.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        nodes.append({
            "name": str(node.get("name") or ""),
            "parent_index": int(node.get("parent_index", -1)),
            "matrix": node.get("matrix") or [],
        })
    bones = []
    for bone in document.get("bones") or []:
        if not isinstance(bone, dict):
            continue
        bones.append({
            "name": str(bone.get("name") or ""),
            "node_index": int(bone.get("node_index", -1)),
            "parent_index": int(bone.get("parent_index", -1)),
            "matrix": bone.get("matrix") or [],
        })
    payload = {
        "node_count": int(document.get("node_count") or len(nodes)),
        "skin_bone_count": int(document.get("skin_bone_count") or len(bones)),
        "skin_node_indices": document.get("skin_node_indices") or [],
        "nodes": nodes,
        "bones": bones,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def collect_skeleton_groups(package_dir: str | Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    root = Path(package_dir).resolve()
    groups: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, str]] = []
    for model in manifest.get("models") or []:
        if not isinstance(model, dict) or not model.get("resolved"):
            continue
        model_rel = str(model.get("model_package_dir") or "")
        model_root = root / model_rel
        model_manifest = _read_json(model_root / "repack_manifest.json") or {}
        blend_rel = str(model_manifest.get("experimental_skeletal_blend") or "")
        skeleton_rel = str(model_manifest.get("skeleton_debug_json") or "debug/skeleton_debug.json")
        blend_path = model_root / blend_rel
        skeleton_path = model_root / skeleton_rel
        if not blend_rel or not blend_path.is_file():
            errors.append({"model_package_dir": model_rel, "error": "Skeletal BLEND fehlt"})
            continue
        skeleton = _read_json(skeleton_path)
        if skeleton is None or not skeleton.get("nodes"):
            errors.append({"model_package_dir": model_rel, "error": "Skeleton-Dokument fehlt oder ist leer"})
            continue
        signature = skeleton_signature(skeleton)
        group = groups.setdefault(signature, {
            "skeleton_signature": signature,
            "skeleton_file": _relative(root, skeleton_path),
            "models": [],
        })
        group["models"].append({
            "model_package_dir": model_rel,
            "blend_path": _relative(root, blend_path),
        })
    return list(groups.values()), errors


def _resolved_animations(manifest: dict[str, Any]) -> list[dict[str, str]]:
    result = []
    for item in manifest.get("animations") or []:
        if not isinstance(item, dict) or not item.get("resolved") or not item.get("source_file"):
            continue
        result.append({
            "name": str(item.get("name") or item.get("entry_name") or item.get("uuid_hex") or "animation"),
            "uuid_hex": str(item.get("uuid_hex") or ""),
            "source_file": str(item["source_file"]).replace("\\", "/"),
        })
    return result


def _timeout_seconds() -> int:
    try:
        value = int(os.environ.get("PAKPY_BLENDER_ACTION_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    except Exception:
        value = DEFAULT_TIMEOUT_SECONDS
    return max(30, value)


def _update_manifests(root: Path, char_manifest: dict[str, Any], report: dict[str, Any], collection_errors: list[dict[str, str]]) -> None:
    by_model = {
        str(model.get("model_package_dir") or ""): (group, model)
        for group in report.get("groups") or []
        for model in group.get("models") or []
    }
    collection_by_model = {item["model_package_dir"]: item["error"] for item in collection_errors}
    for model in char_manifest.get("models") or []:
        if not isinstance(model, dict):
            continue
        model_rel = str(model.get("model_package_dir") or "")
        pair = by_model.get(model_rel)
        if pair is not None:
            group, batch_model = pair
            model["animation_skeleton_signature"] = group.get("skeleton_signature", "")
            model["experimental_skeletal_blend_actions_status"] = batch_model.get("status", "")
            model["experimental_skeletal_blend_action_count"] = int(batch_model.get("action_count") or 0)
            model["experimental_skeletal_blend_action_error"] = str(batch_model.get("error") or "")
        elif model_rel in collection_by_model:
            model["experimental_skeletal_blend_actions_status"] = "error"
            model["experimental_skeletal_blend_action_count"] = 0
            model["experimental_skeletal_blend_action_error"] = collection_by_model[model_rel]

        model_manifest_path = root / model_rel / "repack_manifest.json"
        model_manifest = _read_json(model_manifest_path)
        if model_manifest is not None:
            model_manifest["char_animation_source"] = "../../source/anim"
            model_manifest["char_animation_batch_report"] = "../../" + BATCH_REPORT_NAME
            model_manifest["char_animation_count"] = int(model.get("experimental_skeletal_blend_action_count") or 0)
            model_manifest["experimental_skeletal_blend_actions_status"] = model.get("experimental_skeletal_blend_actions_status", "")
            model_manifest["experimental_skeletal_blend_action_count"] = int(model.get("experimental_skeletal_blend_action_count") or 0)
            model_manifest["experimental_skeletal_blend_action_error"] = model.get("experimental_skeletal_blend_action_error", "")
            model_manifest["animation_skeleton_signature"] = model.get("animation_skeleton_signature", "")
            _write_json(model_manifest_path, model_manifest)

    char_manifest["animation_export_mode"] = "raw_direct_blender_batch"
    char_manifest["animation_batch_report"] = BATCH_REPORT_NAME
    char_manifest["animation_skeleton_group_count"] = int(report.get("skeleton_group_count") or 0)
    char_manifest["experimental_skeletal_blend_actions_status"] = report.get("status", "")
    char_manifest["experimental_skeletal_blend_action_count"] = sum(
        int(group.get("decoded_animation_count") or 0) for group in report.get("groups") or []
    )
    _write_json(root / "manifest.json", char_manifest)


def _update_result(result: dict[str, Any], root: Path, report: dict[str, Any]) -> None:
    result["experimental_skeletal_blend_actions_status"] = report.get("status", "")
    result["experimental_skeletal_blend_action_count"] = sum(
        int(group.get("decoded_animation_count") or 0) for group in report.get("groups") or []
    )
    result["experimental_skeletal_blend_action_error_count"] = sum(
        int(group.get("animation_error_count") or 0) for group in report.get("groups") or []
    ) + len(report.get("collection_errors") or [])
    result["experimental_skeletal_blend_action_report"] = str(root / BATCH_REPORT_NAME)


def run_character_animation_batch(package_dir: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    root = Path(package_dir).resolve()
    char_manifest = _read_json(root / "manifest.json") or {}
    animations = _resolved_animations(char_manifest)
    groups, collection_errors = collect_skeleton_groups(root, char_manifest)
    batch_manifest = {
        "version": 1,
        "package_dir": str(root),
        "code_root": str(Path(__file__).resolve().parent),
        "fps": float(os.environ.get("PAKPY_ANIM_FPS", "30.0")),
        "report_file": BATCH_REPORT_NAME,
        "animations": animations,
        "groups": groups,
    }
    _write_json(root / BATCH_MANIFEST_NAME, batch_manifest)

    if not animations or not groups:
        report = {
            "type": "PAKPY_CHARACTER_ANIMATION_BATCH",
            "status": "skipped:no_animations" if not animations else "error:no_compatible_models",
            "animation_count": len(animations),
            "skeleton_group_count": len(groups),
            "groups": [],
            "collection_errors": collection_errors,
            "fatal_error": "",
        }
        _write_json(root / BATCH_REPORT_NAME, report)
        _update_manifests(root, char_manifest, report, collection_errors)
        _update_result(result, root, report)
        return report

    blender = skeletal_tail_patch._find_blender_exe()
    if not blender:
        report = {
            "type": "PAKPY_CHARACTER_ANIMATION_BATCH",
            "status": "error:blender_not_found",
            "animation_count": len(animations),
            "skeleton_group_count": len(groups),
            "groups": [],
            "collection_errors": collection_errors,
            "fatal_error": "Blender nicht gefunden",
        }
        _write_json(root / BATCH_REPORT_NAME, report)
        _update_manifests(root, char_manifest, report, collection_errors)
        _update_result(result, root, report)
        return report

    script = Path(__file__).resolve().with_name("blender_character_animation_batch.py")
    command = [blender, "--background", "--python", str(script), "--", "--manifest", str(root / BATCH_MANIFEST_NAME)]
    creationflags = 0x08000000 if os.name == "nt" else 0
    process_error = ""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_timeout_seconds(),
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            process_error = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()[-4000:]
    except Exception as exc:
        process_error = str(exc)

    report = _read_json(root / BATCH_REPORT_NAME) or {
        "type": "PAKPY_CHARACTER_ANIMATION_BATCH",
        "status": "error:blender_process",
        "animation_count": len(animations),
        "skeleton_group_count": len(groups),
        "groups": [],
        "fatal_error": process_error or "Blender hat keinen Report erzeugt",
    }
    if process_error and not report.get("fatal_error"):
        report["process_error"] = process_error
    report["collection_errors"] = collection_errors
    _write_json(root / BATCH_REPORT_NAME, report)
    _update_manifests(root, char_manifest, report, collection_errors)
    _update_result(result, root, report)
    return report
