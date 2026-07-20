"""Make Blender mesh-part mapping deterministic and failures actionable."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

import blend_geometry_export
import blend_geometry_extract
import blend_model_repack_patch
import pak_core

_INDEX_KEYS = ("pakpy_source_mesh_index", "source_mesh_index")
_STABLE_MARKER = "# PAKPY stable mesh-part export names"


def _coerce_index(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _prepare_gltf(gltf: dict[str, Any]) -> dict[str, Any]:
    """Copy mesh-level index extras to their node when Blender places them there."""
    prepared = dict(gltf)
    meshes = list(gltf.get("meshes") or [])
    nodes = []
    for source_node in gltf.get("nodes") or []:
        node = dict(source_node)
        extras = dict(node.get("extras") or {})
        mesh_index = node.get("mesh")
        if mesh_index is not None and 0 <= int(mesh_index) < len(meshes):
            mesh_extras = dict((meshes[int(mesh_index)] or {}).get("extras") or {})
            for key in _INDEX_KEYS:
                if key not in extras and key in mesh_extras:
                    extras[key] = mesh_extras[key]
        if extras:
            node["extras"] = extras
        nodes.append(node)
    prepared["nodes"] = nodes
    return prepared


def _mesh_node_records(gltf: dict[str, Any], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    prepared = _prepare_gltf(gltf)
    nodes = list(prepared.get("nodes") or [])
    meshes = list(prepared.get("meshes") or [])
    manifest_parts = list(manifest.get("source_mesh_objects") or [])
    records: list[dict[str, Any]] = []
    for node_index, node in enumerate(nodes):
        mesh_index = node.get("mesh")
        if mesh_index is None or not 0 <= int(mesh_index) < len(meshes):
            continue
        node_extras = dict(node.get("extras") or {})
        mesh_extras = dict((meshes[int(mesh_index)] or {}).get("extras") or {})
        records.append(
            {
                "node_index": node_index,
                "mesh_index": int(mesh_index),
                "name": str(node.get("name") or f"node_{node_index}"),
                "source_index": blend_geometry_extract._source_index_from_node(node, manifest_parts),
                "object_property": next((node_extras[key] for key in _INDEX_KEYS if key in node_extras), None),
                "mesh_property": next((mesh_extras[key] for key in _INDEX_KEYS if key in mesh_extras), None),
            }
        )
    return records


def _expected_part_names(manifest: dict[str, Any]) -> dict[int, str]:
    names: dict[int, str] = {}
    for item in manifest.get("source_mesh_objects") or []:
        index = _coerce_index(item.get("pakpy_source_mesh_index"))
        if index is not None:
            names[index] = str(item.get("name") or "")
    return names


def _format_assignment(record: dict[str, Any]) -> str:
    source_index = record.get("source_index")
    assigned = "NICHT ZUGEORDNET" if source_index is None else str(source_index)
    return (
        f'- Objekt "{record["name"]}" | GLB-Node {record["node_index"]} | '
        f'Objekt-Property={record.get("object_property")!r} | '
        f'Mesh-Property={record.get("mesh_property")!r} | ausgewerteter Quellindex={assigned}'
    )


def _mapping_error_message(
    gltf: dict[str, Any], manifest: dict[str, Any], source_mesh_count: int
) -> str:
    records = _mesh_node_records(gltf, manifest)
    expected = list(range(source_mesh_count))
    found = sorted({int(record["source_index"]) for record in records if record.get("source_index") is not None})
    missing = [index for index in expected if index not in found]
    extra = [index for index in found if index not in expected]
    names = _expected_part_names(manifest)

    lines = [
        "BLEND-MESH-Part-Zuordnung fehlgeschlagen.",
        f"Das Originalmodell enthält {source_mesh_count} MESH-Part(s) mit den Quellindizes {expected}.",
        f"Aus der Blender-GLB wurden {len(found)} eindeutige Quellindizes erkannt: {found}.",
        f"Fehlende Quellindizes ({len(missing)}): {missing or 'keine'}.",
        f"Zusätzliche/ungültige Quellindizes ({len(extra)}): {extra or 'keine'}.",
    ]
    if missing:
        lines.append("")
        lines.append("Fehlende Original-Parts:")
        for index in missing:
            label = names.get(index) or f"ursprünglicher MESH-Part {index}"
            lines.append(
                f'- Quellindex {index}: "{label}". Kein exportiertes Mesh-Objekt wurde diesem einen Part zugeordnet.'
            )
    lines.extend(["", "Exportierte Mesh-Objekte und erkannte Zuordnung:"])
    if records:
        lines.extend(_format_assignment(record) for record in records[:80])
        if len(records) > 80:
            lines.append(f"... {len(records) - 80} weitere Mesh-Objekte")
    else:
        lines.append("- Keine Mesh-Nodes in der temporären Blender-GLB gefunden.")
    lines.extend(
        [
            "",
            "Erforderlich ist direkt am Blender-OBJEKT eine Integer-Custom-Property:",
            "pakpy_source_mesh_index = <Quellindex>",
            "Beispiel: Index 1 bezeichnet genau den ursprünglichen MESH-Part 1; nicht 'einen Fehler pro Objekt'.",
            "Der Objektname und die Collection sind nur organisatorisch und ersetzen diese Zuordnung nicht.",
        ]
    )
    return "\n".join(lines)


def _wrap_export_script(original: Callable[..., str]):
    def wrapped(output_glb):
        script = original(output_glb)
        if _STABLE_MARKER in script:
            return script
        injection = "\n".join(
            [
                _STABLE_MARKER,
                "for obj in mesh_parts:",
                "    source_index=int(obj.get('pakpy_source_mesh_index'))",
                "    original_name=str(obj.name)",
                "    stable_name='__PAKPY_REPACK__mesh_%03d__%s' % (source_index, original_name)",
                "    obj['pakpy_source_mesh_index']=source_index",
                "    obj['pakpy_source_mesh_partition']=True",
                "    if obj.data is not None:",
                "        obj.data['pakpy_source_mesh_index']=source_index",
                "        obj.data['pakpy_source_mesh_partition']=True",
                "        obj.data.name=stable_name+'__Mesh'",
                "    obj.name=stable_name",
                "    print('PAKPY_REPACK_PART index=%d object=%s' % (source_index, original_name))",
            ]
        )
        marker = "armature.data.pose_position='REST'"
        if marker in script:
            return script.replace(marker, injection + "\n" + marker, 1)
        return script + "\n" + injection + "\n"

    wrapped._pakpy_stable_mesh_part_names = True
    return wrapped


def _wrap_extract(original):
    def wrapped(gltf, binary, manifest, expected_bones, source_mesh_count):
        prepared = _prepare_gltf(gltf)
        records = _mesh_node_records(prepared, manifest)
        by_index: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            index = record.get("source_index")
            if index is not None:
                by_index[int(index)].append(record)
        duplicates = {index: items for index, items in by_index.items() if len(items) > 1}
        if duplicates:
            lines = ["BLEND/GLB enthält doppelte pakpy_source_mesh_index-Zuordnungen:"]
            for index, items in sorted(duplicates.items()):
                names = ", ".join(f'"{item["name"]}"' for item in items)
                lines.append(f"- Quellindex {index} ist {len(items)}-mal vergeben: {names}")
            lines.append("Jeder ursprüngliche MESH-Part darf genau einem Blender-Mesh-Objekt zugeordnet sein.")
            raise pak_core.PakError("\n".join(lines))
        try:
            return original(prepared, binary, manifest, expected_bones, source_mesh_count)
        except pak_core.PakError as exc:
            if "BLEND-MESH-Parts passen nicht zum Modell" not in str(exc):
                raise
            raise pak_core.PakError(
                _mapping_error_message(prepared, manifest, source_mesh_count)
            ) from exc

    wrapped._pakpy_detailed_mesh_part_diagnostics = True
    return wrapped


def install() -> None:
    if not getattr(blend_geometry_export._blender_export_script, "_pakpy_stable_mesh_part_names", False):
        export_script = _wrap_export_script(blend_geometry_export._blender_export_script)
        blend_geometry_export._blender_export_script = export_script
        blend_model_repack_patch._blender_export_script = export_script
    if not getattr(blend_geometry_extract._extract_parts_from_glb, "_pakpy_detailed_mesh_part_diagnostics", False):
        extractor = _wrap_extract(blend_geometry_extract._extract_parts_from_glb)
        blend_geometry_extract._extract_parts_from_glb = extractor
        blend_model_repack_patch._extract_parts_from_glb = extractor
