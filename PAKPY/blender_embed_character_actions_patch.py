"""Run a final normal_clip Action embed pass after character export completes.

Model packages are created before the character-level animation pipeline writes
its final bind documents. This wrapper runs after that pipeline, reopens every
model BLEND with the character package as the importer root, and saves persistent
Actions into each BLEND.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import blender_embed_normal_clip_actions_patch as model_embed
import character_animation_batch


REPORT_NAME = "blender_normal_clip_character_embed_report.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def _relative(root: Path, value: str | Path) -> str:
    path = Path(value)
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _bind_files(root: Path) -> list[Path]:
    return sorted((root / "debug" / "anim_normal_clip_bind").glob("*.normal_clip_bind.json"))


def _blend_targets(root: Path) -> list[tuple[Path, Path]]:
    targets: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for blend in sorted(root.glob("models/*/model/*.experimental_skeletal.blend")):
        key = str(blend.resolve()).lower()
        if key in seen or not blend.is_file():
            continue
        seen.add(key)
        targets.append((blend.parent.parent.resolve(), blend.resolve()))
    return targets


def _copy_model_report(root_report: Path, model_root: Path) -> Path | None:
    if not root_report.is_file():
        return None
    target = model_root / "debug" / model_embed.REPORT_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root_report, target)
    return target


def _aggregate_status(models: list[dict[str, Any]]) -> str:
    if not models:
        return "skipped:no_model_blend_files"
    statuses = [str(item.get("status") or "") for item in models]
    if all(status == "ok" for status in statuses):
        return "ok"
    if any(int(item.get("created_action_count") or 0) > 0 for item in models):
        return "partial"
    if any(status.startswith("error") for status in statuses):
        return "error"
    return "skipped"


def _update_character_manifest(root: Path, aggregate: dict[str, Any]) -> None:
    path = root / "manifest.json"
    manifest = _read_json(path)
    if manifest is None:
        return
    model_results = aggregate.get("models") if isinstance(aggregate.get("models"), list) else []
    by_package = {str(item.get("model_package_dir") or ""): item for item in model_results}
    for model in manifest.get("models") or []:
        if not isinstance(model, dict):
            continue
        item = by_package.get(str(model.get("model_package_dir") or ""))
        if item is None:
            continue
        model["experimental_skeletal_blend_actions_status"] = item.get("status", "")
        model["experimental_skeletal_blend_action_count"] = int(item.get("created_action_count") or 0)
        model["experimental_skeletal_blend_action_error_count"] = int(item.get("error_count") or 0)
        model["experimental_skeletal_blend_action_error"] = str(item.get("error") or "")
    manifest["experimental_skeletal_blend_actions_status"] = aggregate.get("status", "")
    manifest["experimental_skeletal_blend_action_count"] = int(aggregate.get("created_action_count") or 0)
    manifest["experimental_skeletal_blend_action_error_count"] = int(aggregate.get("error_count") or 0)
    manifest["experimental_skeletal_blend_action_models"] = model_results
    manifest["experimental_skeletal_blend_action_report"] = aggregate.get("report_path", "")
    _write_json(path, manifest)


def embed_character_package_actions(package_dir: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    root = Path(package_dir).resolve()
    if result.get("animation_source_mode") == "character_root_raw":
        return character_animation_batch.run_character_animation_batch(root, result)
    binds = _bind_files(root)
    targets = _blend_targets(root)
    models: list[dict[str, Any]] = []

    if binds:
        for model_root, blend in targets:
            try:
                item = model_embed.embed_normal_clip_actions(
                    root,
                    {"experimental_skeletal_blend": str(blend)},
                )
            except Exception as exc:
                item = {
                    "status": "error:unexpected",
                    "blend_path": str(blend),
                    "created_action_count": 0,
                    "error_count": 1,
                    "error": str(exc),
                }
            item = dict(item)
            root_report = root / model_embed.REPORT_NAME
            model_report = _copy_model_report(root_report, model_root)
            manifest_item = dict(item)
            manifest_item["blend_path"] = str(blend)
            if model_report is not None:
                manifest_item["report_path"] = str(model_report)
            model_embed._update_manifest(model_root, manifest_item)

            item["model_package_dir"] = _relative(root, model_root)
            item["blend_path"] = _relative(root, item.get("blend_path") or blend)
            item["report_path"] = _relative(root, model_report) if model_report else ""
            models.append(item)

    if not binds:
        status = "skipped:no_character_bind_files"
    else:
        status = _aggregate_status(models)
    aggregate = {
        "type": "PAKPY_CHARACTER_BLEND_ACTION_EMBED",
        "status": status,
        "package": str(root),
        "normal_clip_bind_count": len(binds),
        "model_blend_count": len(targets),
        "created_action_count": sum(int(item.get("created_action_count") or 0) for item in models),
        "error_count": sum(int(item.get("error_count") or 0) for item in models),
        "models": models,
        "report_path": REPORT_NAME,
    }
    report_path = root / REPORT_NAME
    _write_json(report_path, aggregate)
    _update_character_manifest(root, aggregate)
    result["experimental_skeletal_blend_actions_status"] = status
    result["experimental_skeletal_blend_action_count"] = aggregate["created_action_count"]
    result["experimental_skeletal_blend_action_error_count"] = aggregate["error_count"]
    result["experimental_skeletal_blend_action_report"] = str(report_path)
    return aggregate


def _wrap_character_export(original):
    def export_clean_char_package(parsed, entry, out_dir, require_store=None):
        result = original(parsed, entry, out_dir, require_store=require_store)
        try:
            embed_character_package_actions(result["package_dir"], result)
        except Exception as exc:
            result["experimental_skeletal_blend_actions_status"] = "error:unexpected"
            result["experimental_skeletal_blend_action_count"] = 0
            result["experimental_skeletal_blend_action_error_count"] = 1
            result["experimental_skeletal_blend_action_error"] = str(exc)
        return result

    export_clean_char_package._pakpy_character_action_embed = True
    return export_clean_char_package


def install() -> None:
    try:
        import char_gui_patch
        import char_skeletal_package_patch
    except Exception:
        return
    original = char_skeletal_package_patch.export_clean_char_package
    if getattr(original, "_pakpy_character_action_embed", False):
        return
    patched = _wrap_character_export(original)
    char_skeletal_package_patch.export_clean_char_package = patched

    def export_char_package(parsed, entry, out_dir, require_store=None):
        return patched(parsed, entry, out_dir, require_store=require_store)

    char_gui_patch.export_char_package = export_char_package
