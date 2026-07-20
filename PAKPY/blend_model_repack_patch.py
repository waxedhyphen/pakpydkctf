"""Rebuild model geometry from the edited Blender file in an exported package.

The original MESH partition count, material assignments, SKEL resource and bone
order stay fixed. Vertex and triangle counts inside each source MESH part may
change freely.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import model_package
import pak_core
import rigged_gltf
import skeletal_tail_patch
from blend_geometry_export import (
    _blender_export_script,
    _read_glb,
    _run_blender_export,
    _snapshot_blend_script,
)
from blend_geometry_extract import _expected_bones, _extract_parts_from_glb
from model_geometry_rebuild import (
    _build_model_asset,
    _encode_vertex_buffer,
    _relaxed_model_meta,
    _serialize_ibufs,
    _serialize_meshes,
    _serialize_vbufs,
)

MODEL_TYPES = {"CMDL", "SMDL", "WMDL"}

def _manifest_entry(parsed: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    uuid_hex = str(manifest.get("entry_uuid_hex") or "")
    entry = (parsed.get("uuid_to_entry") or {}).get(uuid_hex)
    if entry is None:
        index = manifest.get("entry_index")
        if isinstance(index, int) and 0 <= index < len(parsed.get("entries") or []):
            candidate = parsed["entries"][index]
            if candidate.get("uuid_hex") == uuid_hex:
                entry = candidate
    if entry is None or entry.get("type") not in MODEL_TYPES:
        raise pak_core.PakError(f"Modell {uuid_hex or 'unbekannt'} ist im geladenen PAK nicht vorhanden")
    return entry


def _add_replacement(replacements: dict[int, dict[str, bytes]], entry_index: int, asset: bytes, label: str) -> None:
    previous = replacements.get(entry_index)
    if previous is not None and previous.get("asset_bytes") != asset:
        raise pak_core.PakError(f"Widersprüchliche Änderungen für denselben PAK-Eintrag: {label}")
    replacements[entry_index] = {"asset_bytes": asset}


def _collect_texture_replacements(
    parsed: dict[str, Any], folder: Path, manifest: dict[str, Any], replacements: dict[int, dict[str, bytes]], changed: list[str]
) -> int:
    count = 0
    for item in manifest.get("textures") or []:
        uuid_hex = str(item.get("txtr_uuid_hex") or "")
        txtr_entry = (parsed.get("uuid_to_entry") or {}).get(uuid_hex)
        if txtr_entry is None or txtr_entry.get("type") != "TXTR":
            continue
        raw_name = str(item.get("raw_name") or "")
        raw_sha1 = str(item.get("raw_sha1") or "")
        if raw_name:
            raw_path = folder / raw_name
            if raw_path.is_file() and raw_sha1 and pak_core.sha1_bytes(raw_path.read_bytes()) != raw_sha1:
                asset = raw_path.read_bytes()
                _add_replacement(replacements, txtr_entry["index"], asset, raw_name)
                changed.append(str(raw_path))
                count += 1
                continue
        png_name = str(item.get("png_name") or "")
        png_sha1 = str(item.get("png_sha1") or "")
        if png_name:
            png_path = folder / png_name
            if png_path.is_file() and png_sha1 and pak_core.sha1_bytes(png_path.read_bytes()) != png_sha1:
                original_asset = pak_core.get_entry_asset(parsed, txtr_entry)
                asset = model_package.png_to_txtr_asset(original_asset, png_path)
                _add_replacement(replacements, txtr_entry["index"], asset, png_name)
                changed.append(str(png_path))
                count += 1
    return count


def _collect_geometry_replacement(
    parsed: dict[str, Any], folder: Path, manifest: dict[str, Any], replacements: dict[int, dict[str, bytes]], changed: list[str]
) -> tuple[int, dict[str, Any] | None]:
    blend_rel = str(manifest.get("experimental_skeletal_blend") or "")
    blend_sha1 = str(manifest.get("experimental_skeletal_blend_sha1") or "")
    if not blend_rel:
        return 0, None
    blend_path = folder / blend_rel
    if not blend_path.is_file():
        return 0, None
    current_sha1 = pak_core.sha1_bytes(blend_path.read_bytes())
    if blend_sha1 and current_sha1 == blend_sha1:
        return 0, None
    entry = _manifest_entry(parsed, manifest)
    original_asset = pak_core.get_entry_asset(parsed, entry)
    original_model = rigged_gltf.load_model_with_skin(original_asset)
    debug_dir = folder / "debug"
    glb_path = _run_blender_export(blend_path, debug_dir)
    gltf, binary = _read_glb(glb_path)
    bones = _expected_bones(parsed, folder, manifest, original_model)
    if int(original_model.get("bone_count") or 0) > 0 and not bones:
        raise pak_core.PakError("Skin-Bone-Reihenfolge konnte nicht aus dem Paket oder geladenen PAK aufgelöst werden")
    parts = _extract_parts_from_glb(gltf, binary, manifest, bones, len(original_model.get("meshes") or []))
    new_asset, summary = _build_model_asset(original_asset, parts)
    _add_replacement(replacements, entry["index"], new_asset, blend_rel)
    changed.append(str(blend_path))
    summary.update({"entry_index": entry["index"], "entry_uuid_hex": entry["uuid_hex"], "entry_type": entry["type"], "blend": str(blend_path)})
    (debug_dir / "repack_geometry_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    return 1, summary


def _model_package_dirs(folder: Path) -> list[Path]:
    if (folder / "repack_manifest.json").is_file():
        return [folder]
    char_manifest_path = folder / "manifest.json"
    if char_manifest_path.is_file():
        try:
            char_manifest = json.loads(char_manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise pak_core.PakError(f"CHAR manifest.json konnte nicht gelesen werden: {exc}") from exc
        result = []
        seen = set()
        for item in char_manifest.get("models") or []:
            rel = str(item.get("model_package_dir") or "")
            package_dir = folder / rel if rel else None
            key = str(package_dir.resolve()) if package_dir is not None else ""
            if package_dir is not None and key not in seen and (package_dir / "repack_manifest.json").is_file():
                seen.add(key)
                result.append(package_dir)
        if result:
            return result
    result = sorted({path.parent for path in folder.rglob("repack_manifest.json")})
    if result:
        return result
    raise pak_core.PakError("Weder Modellpaket noch CHAR-Paket mit repack_manifest.json gefunden")


def rebuild_from_blend_package(parsed: dict[str, Any], folder: str | Path, out_path: str | Path) -> dict[str, Any]:
    folder = Path(folder)
    package_dirs = _model_package_dirs(folder)
    replacements: dict[int, dict[str, bytes]] = {}
    changed: list[str] = []
    texture_count = 0
    geometry_count = 0
    geometry_summaries = []
    for package_dir in package_dirs:
        manifest = json.loads((package_dir / "repack_manifest.json").read_text(encoding="utf-8"))
        texture_count += _collect_texture_replacements(parsed, package_dir, manifest, replacements, changed)
        count, summary = _collect_geometry_replacement(parsed, package_dir, manifest, replacements, changed)
        geometry_count += count
        if summary:
            geometry_summaries.append(summary)
    if not replacements:
        raise pak_core.PakError("Keine geänderten Texturen oder BLEND-Geometrien gefunden")
    built = pak_core.rebuild_pak(parsed, replacements, out_path)
    return {
        "out_path": built,
        "changed_count": len(changed),
        "changed_files": changed,
        "texture_changed_count": texture_count,
        "geometry_changed_count": geometry_count,
        "model_package_count": len(package_dirs),
        "geometry_summaries": geometry_summaries,
    }


def _wrap_export_model_package(original):
    def export_model_package(parsed, entry, out_dir, require_store=None, animation_refs=None, skeleton_refs=None):
        result = original(parsed, entry, out_dir, require_store=require_store, animation_refs=animation_refs, skeleton_refs=skeleton_refs)
        package_dir = Path(result.get("package_dir") or "")
        manifest_path = package_dir / "repack_manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["geometry_repack_version"] = 1
            manifest["geometry_repack_source"] = "experimental_skeletal_blend"
            manifest["geometry_repack_armature_policy"] = "same skin bones, indices, hierarchy and rest pose"
            manifest["geometry_repack_topology_policy"] = "arbitrary vertices and triangles per existing source MESH part"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        return result

    export_model_package._pakpy_blend_geometry_repack_manifest = True
    return export_model_package


def _install_gui(App) -> None:
    import tkinter.messagebox as messagebox

    def rebuild_model_package_dialog(self):
        if self.parsed is None:
            messagebox.showerror("Fehler", "Noch keine PAK-Datei eingelesen")
            return
        folder = self.ask_directory("model_package_rebuild_dir", title="Modellpaket- oder CHAR-Paket-Ordner auswählen")
        if not folder:
            return
        try:
            out_path = self.ask_save_file(
                "model_package_rebuild_save",
                title="Neues PAK speichern",
                defaultextension=".pak",
                initialfile=Path(self.parsed["path"]).stem + "_model_repacked.pak",
                filetypes=[("PAK-Dateien", "*.pak"), ("Alle Dateien", "*.*")],
            )
            if not out_path:
                return
            result = rebuild_from_blend_package(self.parsed, folder, out_path)
            self.pak_var.set(result["out_path"])
            self.load_pak()
            lines = [
                "Neue Datei:",
                result["out_path"],
                "",
                f"Modellpakete geprüft: {result['model_package_count']}",
                f"Geänderte Modellressourcen: {result['geometry_changed_count']}",
                f"Geänderte Texturen: {result['texture_changed_count']}",
            ]
            if result["changed_files"]:
                lines.extend(["", "Verarbeitete Änderungen:"])
                lines.extend(result["changed_files"][:80])
                if len(result["changed_files"]) > 80:
                    lines.append(f"... {len(result['changed_files']) - 80} weitere")
            self.output.delete("1.0", "end")
            self.output.insert("1.0", "\n".join(lines))
            messagebox.showinfo("Fertig", result["out_path"])
        except Exception as exc:
            self.output.delete("1.0", "end")
            self.output.insert("1.0", f"Fehler: {exc}")
            messagebox.showerror("Fehler", str(exc))

    App.rebuild_model_package_dialog = rebuild_model_package_dialog


def install(App=None) -> None:
    if not getattr(skeletal_tail_patch._connected_blend_script, "_pakpy_geometry_bind_snapshot", False):
        skeletal_tail_patch._connected_blend_script = _snapshot_blend_script(skeletal_tail_patch._connected_blend_script)
    if not getattr(pak_core.build_model_meta_blob, "_pakpy_allow_zlib_model_segments", False):
        pak_core.build_model_meta_blob = _relaxed_model_meta(pak_core.build_model_meta_blob)
    if not getattr(model_package.export_model_package, "_pakpy_blend_geometry_repack_manifest", False):
        patched_export = _wrap_export_model_package(model_package.export_model_package)
        model_package.export_model_package = patched_export
        try:
            import gui

            gui.export_model_package = patched_export
            gui.rebuild_model_package_from_folder = rebuild_from_blend_package
        except Exception:
            pass
        try:
            import char_skeletal_package_patch

            char_skeletal_package_patch.export_model_package = patched_export
        except Exception:
            pass
    model_package.rebuild_model_package_from_folder = rebuild_from_blend_package
    if App is not None:
        _install_gui(App)
