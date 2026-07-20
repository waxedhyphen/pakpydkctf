"""Embed decoded ``normal_clip`` Actions into generated BLEND files automatically.

The skeletal BLEND is created before the animation probe/bind pipeline finishes.
This final export wrapper reopens that BLEND after ``normal_clip_bind`` JSON files
exist, runs the generated Blender Action importer headlessly, and saves the same
file with persistent Actions.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import blender_normal_clip_action_script_patch as action_script_patch
import model_package
import skeletal_tail_patch


REPORT_NAME = "blender_normal_clip_action_report.json"
DEFAULT_FPS = 30.0
DEFAULT_TIMEOUT_SECONDS = 900


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


def _package_path(package_dir: Path, value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else package_dir / path


def _find_blend_path(package_dir: Path, result: dict[str, Any]) -> Path | None:
    candidates: list[Path] = []
    direct = _package_path(package_dir, result.get("experimental_skeletal_blend"))
    if direct is not None:
        candidates.append(direct)

    manifest = _read_json(package_dir / "repack_manifest.json") or {}
    manifest_path = _package_path(package_dir, manifest.get("experimental_skeletal_blend"))
    if manifest_path is not None:
        candidates.append(manifest_path)

    candidates.extend(sorted((package_dir / "model").glob("*.experimental_skeletal.blend")))
    seen: set[str] = set()
    for path in candidates:
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        if path.is_file():
            return path.resolve()
    return None


def _bind_files(package_dir: Path) -> list[Path]:
    return sorted((package_dir / "debug" / "anim_normal_clip_bind").glob("*.normal_clip_bind.json"))


def _ensure_action_script(package_dir: Path) -> Path:
    path = package_dir / "blender_import_normal_clip_actions.py"
    content = action_script_patch.NORMAL_CLIP_ACTION_SCRIPT.strip() + "\n"
    if not path.is_file() or path.read_text(encoding="utf-8", errors="replace") != content:
        path.write_text(content, encoding="utf-8", newline="\n")
    return path


def _timeout_seconds() -> int:
    try:
        value = int(os.environ.get("PAKPY_BLENDER_ACTION_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))
    except Exception:
        value = DEFAULT_TIMEOUT_SECONDS
    return max(30, value)


def _fps() -> float:
    try:
        value = float(os.environ.get("PAKPY_ANIM_FPS", DEFAULT_FPS))
    except Exception:
        value = DEFAULT_FPS
    return value if value > 0.0 else DEFAULT_FPS


def embed_normal_clip_actions(package_dir: str | Path, result: dict[str, Any]) -> dict[str, Any]:
    root = Path(package_dir).resolve()
    binds = _bind_files(root)
    if not binds:
        return {
            "status": "skipped:no_normal_clip_bind_files",
            "blend_path": "",
            "created_action_count": 0,
            "error_count": 0,
            "error": "",
        }

    blend_path = _find_blend_path(root, result)
    if blend_path is None:
        return {
            "status": "skipped:no_blend_file",
            "blend_path": "",
            "created_action_count": 0,
            "error_count": 0,
            "error": "",
        }

    blender = skeletal_tail_patch._find_blender_exe()
    if not blender:
        return {
            "status": "error:blender_not_found",
            "blend_path": str(blend_path),
            "created_action_count": 0,
            "error_count": 1,
            "error": "Blender nicht gefunden; setze PAKPY_BLENDER_EXE auf blender.exe.",
        }

    script_path = _ensure_action_script(root)
    report_path = root / REPORT_NAME
    try:
        report_path.unlink()
    except FileNotFoundError:
        pass

    command = [
        blender,
        "--background",
        str(blend_path),
        "--python",
        str(script_path),
        "--",
        "--package",
        str(root),
        "--fps",
        str(_fps()),
        "--save",
        str(blend_path),
    ]
    creationflags = 0x08000000 if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=_timeout_seconds(),
            creationflags=creationflags,
        )
    except Exception as exc:
        return {
            "status": "error:blender_process",
            "blend_path": str(blend_path),
            "created_action_count": 0,
            "error_count": 1,
            "error": str(exc),
            "command": command,
        }

    report = _read_json(report_path) or {}
    actions = report.get("actions") if isinstance(report.get("actions"), list) else []
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    if completed.returncode != 0 or not blend_path.is_file():
        return {
            "status": "error:blender_failed",
            "blend_path": str(blend_path),
            "created_action_count": len(actions),
            "error_count": max(1, len(errors)),
            "error": output[-4000:] or f"Blender returned {completed.returncode}",
            "command": command,
        }

    created = int(report.get("created_action_count") or len(actions))
    status = "ok" if created > 0 and not errors else "partial" if created > 0 else "error:no_actions"
    error_text = "\n".join(str(item.get("error") or item) for item in errors if item)
    return {
        "status": status,
        "blend_path": str(blend_path),
        "created_action_count": created,
        "error_count": len(errors),
        "error": error_text,
        "report_path": str(report_path) if report_path.is_file() else "",
        "normal_clip_bind_count": len(binds),
    }


def _update_manifest(package_dir: Path, embed: dict[str, Any]) -> None:
    manifest_path = package_dir / "repack_manifest.json"
    manifest = _read_json(manifest_path)
    if manifest is None:
        return
    report_path = _package_path(package_dir, embed.get("report_path"))
    manifest["experimental_skeletal_blend_actions_status"] = embed.get("status", "")
    manifest["experimental_skeletal_blend_action_count"] = int(embed.get("created_action_count") or 0)
    manifest["experimental_skeletal_blend_action_error_count"] = int(embed.get("error_count") or 0)
    manifest["experimental_skeletal_blend_action_error"] = str(embed.get("error") or "")
    manifest["experimental_skeletal_blend_action_report"] = (
        str(report_path.relative_to(package_dir)).replace("\\", "/")
        if report_path is not None and report_path.is_file()
        else ""
    )
    blend_path = _package_path(package_dir, embed.get("blend_path"))
    if blend_path is not None and blend_path.is_file():
        manifest["experimental_skeletal_blend_sha1"] = model_package.sha1_bytes(blend_path.read_bytes())
    _write_json(manifest_path, manifest)
    try:
        model_package._write_report(package_dir, manifest)
    except Exception:
        pass


def _wrap_export(original):
    def export_model_package(
        parsed,
        entry,
        out_dir,
        require_store=None,
        animation_refs=None,
        skeleton_refs=None,
    ):
        result = original(
            parsed,
            entry,
            out_dir,
            require_store=require_store,
            animation_refs=animation_refs,
            skeleton_refs=skeleton_refs,
        )
        package_dir = Path(result["package_dir"])
        try:
            embed = embed_normal_clip_actions(package_dir, result)
        except Exception as exc:
            embed = {
                "status": "error:unexpected",
                "blend_path": str(result.get("experimental_skeletal_blend") or ""),
                "created_action_count": 0,
                "error_count": 1,
                "error": str(exc),
            }
        result["experimental_skeletal_blend_actions_status"] = embed.get("status", "")
        result["experimental_skeletal_blend_action_count"] = int(embed.get("created_action_count") or 0)
        result["experimental_skeletal_blend_action_error"] = str(embed.get("error") or "")
        _update_manifest(package_dir, embed)
        return result

    export_model_package._pakpy_embed_normal_clip_actions = True
    return export_model_package


def install() -> None:
    if getattr(model_package.export_model_package, "_pakpy_embed_normal_clip_actions", False):
        return
    patched = _wrap_export(model_package.export_model_package)
    model_package.export_model_package = patched
    try:
        import gui

        gui.export_model_package = patched
    except Exception:
        pass
    try:
        import char_skeletal_package_patch

        char_skeletal_package_patch.export_model_package = patched
    except Exception:
        pass
