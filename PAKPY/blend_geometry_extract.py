"""Transform and extract source MESH parts from Blender's temporary GLB."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

import pak_core
from blend_geometry_export import _read_accessor

def _identity4() -> list[list[float]]:
    return [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]


def _mul4(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [[sum(a[row][k] * b[k][column] for k in range(4)) for column in range(4)] for row in range(4)]


def _node_local_matrix(node: dict[str, Any]) -> list[list[float]]:
    matrix = node.get("matrix")
    if isinstance(matrix, list) and len(matrix) == 16:
        return [[float(matrix[column * 4 + row]) for column in range(4)] for row in range(4)]
    translation = node.get("translation") or [0.0, 0.0, 0.0]
    scale = node.get("scale") or [1.0, 1.0, 1.0]
    quaternion = node.get("rotation") or [0.0, 0.0, 0.0, 1.0]
    x, y, z, w = [float(value) for value in quaternion[:4]]
    length = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / length, y / length, z / length, w / length
    rotation = [
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ]
    out = _identity4()
    for row in range(3):
        for column in range(3):
            out[row][column] = rotation[row][column] * float(scale[column])
        out[row][3] = float(translation[row])
    return out


def _node_global_matrices(gltf: dict[str, Any]) -> list[list[list[float]]]:
    nodes = gltf.get("nodes") or []
    parents = [-1] * len(nodes)
    for parent_index, node in enumerate(nodes):
        for child in node.get("children") or []:
            if 0 <= int(child) < len(nodes):
                parents[int(child)] = parent_index
    memo: dict[int, list[list[float]]] = {}
    visiting: set[int] = set()

    def resolve(index: int) -> list[list[float]]:
        if index in memo:
            return memo[index]
        if index in visiting:
            return _node_local_matrix(nodes[index])
        visiting.add(index)
        local = _node_local_matrix(nodes[index])
        parent = parents[index]
        result = _mul4(resolve(parent), local) if parent >= 0 else local
        visiting.discard(index)
        memo[index] = result
        return result

    return [resolve(index) for index in range(len(nodes))]


def _transform_point(matrix: list[list[float]], value: Iterable[float]) -> list[float]:
    x, y, z = [float(item) for item in list(value)[:3]]
    return [
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z + matrix[0][3],
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z + matrix[1][3],
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z + matrix[2][3],
    ]


def _inverse3(matrix: list[list[float]]) -> list[list[float]]:
    a, b, c = matrix[0][0], matrix[0][1], matrix[0][2]
    d, e, f = matrix[1][0], matrix[1][1], matrix[1][2]
    g, h, i = matrix[2][0], matrix[2][1], matrix[2][2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) <= 1e-12:
        raise pak_core.PakError("Mesh-Objekttransform ist singulär")
    q = 1.0 / det
    return [
        [(e * i - f * h) * q, (c * h - b * i) * q, (b * f - c * e) * q],
        [(f * g - d * i) * q, (a * i - c * g) * q, (c * d - a * f) * q],
        [(d * h - e * g) * q, (b * g - a * h) * q, (a * e - b * d) * q],
    ]


def _normal_matrix(matrix: list[list[float]]) -> list[list[float]]:
    inverse = _inverse3(matrix)
    return [[inverse[column][row] for column in range(3)] for row in range(3)]


def _normalise3(value: Iterable[float], fallback=(0.0, 0.0, 1.0)) -> list[float]:
    values = [float(item) for item in list(value)[:3]]
    length = math.sqrt(sum(item * item for item in values))
    if length <= 1e-12:
        return list(fallback)
    return [item / length for item in values]


def _transform_vector(matrix3: list[list[float]], value: Iterable[float]) -> list[float]:
    x, y, z = [float(item) for item in list(value)[:3]]
    return _normalise3(
        [
            matrix3[0][0] * x + matrix3[0][1] * y + matrix3[0][2] * z,
            matrix3[1][0] * x + matrix3[1][1] * y + matrix3[1][2] * z,
            matrix3[2][0] * x + matrix3[2][1] * y + matrix3[2][2] * z,
        ]
    )


def _source_index_from_node(node: dict[str, Any], manifest_parts: list[dict[str, Any]]) -> int | None:
    extras = node.get("extras") or {}
    for key in ("pakpy_source_mesh_index", "source_mesh_index"):
        if extras.get(key) is not None:
            try:
                return int(extras[key])
            except Exception:
                pass
    name = str(node.get("name") or "")
    match = re.search(r"(?:^|__)mesh_(\d+)(?:__|$)", name, re.IGNORECASE)
    if match:
        return int(match.group(1))
    for item in manifest_parts:
        if str(item.get("name") or "") == name:
            try:
                return int(item.get("pakpy_source_mesh_index"))
            except Exception:
                return None
    return None


def _expected_bones(parsed: dict[str, Any], folder: Path, manifest: dict[str, Any], model: dict[str, Any]) -> list[dict[str, Any]]:
    debug_rel = str(manifest.get("skeleton_debug_json") or "")
    if debug_rel:
        path = folder / debug_rel
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                bones = data.get("bones") or (data.get("summary") or {}).get("bones") or []
                if bones:
                    return list(bones)[: int(model.get("bone_count") or len(bones))]
            except Exception:
                pass
    uuid_hex = str(manifest.get("skeleton_uuid_hex") or "")
    entry = (parsed.get("uuid_to_entry") or {}).get(uuid_hex)
    if entry is not None and entry.get("type") == "SKEL":
        try:
            from skeletal_codec import parse_skel_asset

            bones = parse_skel_asset(pak_core.get_entry_asset(parsed, entry)).get("bones") or []
            if bones:
                return list(bones)[: int(model.get("bone_count") or len(bones))]
        except Exception:
            pass
    return []


def _extract_parts_from_glb(
    gltf: dict[str, Any],
    binary: bytes,
    manifest: dict[str, Any],
    expected_bones: list[dict[str, Any]],
    source_mesh_count: int,
) -> list[dict[str, Any]]:
    nodes = gltf.get("nodes") or []
    meshes = gltf.get("meshes") or []
    skins = gltf.get("skins") or []
    globals_ = _node_global_matrices(gltf)
    manifest_parts = list(manifest.get("source_mesh_objects") or [])
    bone_name_to_index = {str(bone.get("name") or ""): index for index, bone in enumerate(expected_bones)}
    parts: dict[int, dict[str, Any]] = {}
    for node_index, node in enumerate(nodes):
        mesh_index = node.get("mesh")
        if mesh_index is None or not 0 <= int(mesh_index) < len(meshes):
            continue
        source_index = _source_index_from_node(node, manifest_parts)
        if source_index is None:
            continue
        if source_index in parts:
            raise pak_core.PakError(f"BLEND/GLB enthält MESH-Part {source_index} mehrfach")
        skin_index = node.get("skin")
        joint_map: dict[int, int] = {}
        if skin_index is not None and 0 <= int(skin_index) < len(skins):
            joint_nodes = list((skins[int(skin_index)] or {}).get("joints") or [])
            for local_index, joint_node_index in enumerate(joint_nodes):
                if not 0 <= int(joint_node_index) < len(nodes):
                    continue
                name = str(nodes[int(joint_node_index)].get("name") or "")
                if name in bone_name_to_index:
                    joint_map[local_index] = bone_name_to_index[name]
        transform = globals_[node_index]
        normal_transform = _normal_matrix(transform)
        linear_transform = [[transform[row][column] for column in range(3)] for row in range(3)]
        out_positions: list[list[float]] = []
        out_normals: list[list[float]] = []
        out_tangents: list[list[float]] = []
        out_uvs: list[list[float]] = []
        out_joints: list[list[int]] = []
        out_weights: list[list[float]] = []
        out_indices: list[int] = []
        for primitive in meshes[int(mesh_index)].get("primitives") or []:
            attributes = primitive.get("attributes") or {}
            if "POSITION" not in attributes:
                continue
            positions = _read_accessor(gltf, binary, int(attributes["POSITION"]))
            normals = _read_accessor(gltf, binary, int(attributes["NORMAL"])) if "NORMAL" in attributes else [[0.0, 0.0, 1.0] for _ in positions]
            tangents = _read_accessor(gltf, binary, int(attributes["TANGENT"])) if "TANGENT" in attributes else [[1.0, 0.0, 0.0, 1.0] for _ in positions]
            uvs = _read_accessor(gltf, binary, int(attributes["TEXCOORD_0"])) if "TEXCOORD_0" in attributes else [[0.0, 0.0] for _ in positions]
            joints = _read_accessor(gltf, binary, int(attributes["JOINTS_0"])) if "JOINTS_0" in attributes else [[0, 0, 0, 0] for _ in positions]
            weights = _read_accessor(gltf, binary, int(attributes["WEIGHTS_0"])) if "WEIGHTS_0" in attributes else [[1.0, 0.0, 0.0, 0.0] for _ in positions]
            base = len(out_positions)
            for vertex_index, position in enumerate(positions):
                out_positions.append(_transform_point(transform, position))
                out_normals.append(_transform_vector(normal_transform, normals[vertex_index] if vertex_index < len(normals) else [0.0, 0.0, 1.0]))
                tangent = tangents[vertex_index] if vertex_index < len(tangents) else [1.0, 0.0, 0.0, 1.0]
                tangent_xyz = _transform_vector(linear_transform, tangent[:3])
                out_tangents.append(tangent_xyz + [float(tangent[3]) if len(tangent) > 3 else 1.0])
                uv = uvs[vertex_index] if vertex_index < len(uvs) else [0.0, 0.0]
                out_uvs.append([float(uv[0]), float(uv[1])])
                raw_joints = joints[vertex_index] if vertex_index < len(joints) else [0, 0, 0, 0]
                raw_weights = weights[vertex_index] if vertex_index < len(weights) else [1.0, 0.0, 0.0, 0.0]
                pairs = []
                for raw_joint, raw_weight in zip(list(raw_joints)[:4], list(raw_weights)[:4]):
                    weight = max(0.0, float(raw_weight))
                    if weight <= 1e-8:
                        continue
                    mapped = joint_map.get(int(raw_joint), int(raw_joint) if not expected_bones else None)
                    if mapped is None or mapped < 0 or (expected_bones and mapped >= len(expected_bones)):
                        raise pak_core.PakError(f"Unbekannter Bone-Einfluss in MESH-Part {source_index}: Joint {raw_joint}")
                    pairs.append((weight, int(mapped)))
                pairs.sort(reverse=True)
                pairs = pairs[:4]
                total = sum(weight for weight, _joint in pairs)
                if total <= 1e-8:
                    pairs = [(1.0, 0)]
                    total = 1.0
                joint_set = [joint for _weight, joint in pairs]
                weight_set = [weight / total for weight, _joint in pairs]
                while len(joint_set) < 4:
                    joint_set.append(0)
                    weight_set.append(0.0)
                out_joints.append(joint_set[:4])
                out_weights.append(weight_set[:4])
            if primitive.get("indices") is not None:
                primitive_indices = [int(value) for value in _read_accessor(gltf, binary, int(primitive["indices"]))]
            else:
                primitive_indices = list(range(len(positions)))
            mode = int(primitive.get("mode", 4))
            if mode != 4:
                raise pak_core.PakError(f"Blender-GLB-Primitive Mode {mode} wird nicht unterstützt; Dreiecke erwartet")
            if len(primitive_indices) % 3:
                raise pak_core.PakError(f"MESH-Part {source_index} hat keine vollständige Dreiecksindexliste")
            out_indices.extend(base + value for value in primitive_indices)
        if not out_positions or not out_indices:
            raise pak_core.PakError(f"MESH-Part {source_index} enthält keine exportierbare Geometrie")
        if any(index < 0 or index >= len(out_positions) for index in out_indices):
            raise pak_core.PakError(f"MESH-Part {source_index} enthält ungültige Indizes")
        parts[source_index] = {
            "mesh_index": source_index,
            "positions": out_positions,
            "normals": out_normals,
            "tangents": out_tangents,
            "uvs": out_uvs,
            "joints": out_joints,
            "weights": out_weights,
            "indices": out_indices,
        }
    expected_indices = set(range(source_mesh_count))
    if set(parts) != expected_indices:
        missing = sorted(expected_indices - set(parts))
        extra = sorted(set(parts) - expected_indices)
        raise pak_core.PakError(f"BLEND-MESH-Parts passen nicht zum Modell | fehlen={missing} | zusätzlich={extra}")
    return [parts[index] for index in range(source_mesh_count)]
