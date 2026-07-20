"""Preserve source model partitions and SKEL helpers in generated GLB/BLEND files.

The base exporters decode every source MESH record, but historically merge all
records into one glTF mesh/node. Blender consequently imports one mesh object and
loses the source partition identity needed for editing and future repacking.

This patch keeps one compact glTF mesh and one scene node per source MESH record,
adds deterministic names and source metadata, preserves original vertex indices
as a custom vertex attribute, and exposes non-skin SKEL nodes as named helpers.
"""
from __future__ import annotations

import json
import mimetypes
import os
import struct
from pathlib import Path
from typing import Any, Iterable

import model_package
import rigged_gltf
import skeletal_tail_patch


def _safe(value: Any, fallback: str) -> str:
    text = rigged_gltf.safe_name(str(value or fallback)).strip("_")
    return text or fallback


def _normalise_weight_set(values: Iterable[float]) -> list[float]:
    weights = [max(0.0, float(value)) for value in values]
    while len(weights) < 4:
        weights.append(0.0)
    weights = weights[:4]
    total = sum(weights)
    return [1.0, 0.0, 0.0, 0.0] if total <= 0.000001 else [value / total for value in weights]


def _normalise_joint_set(values: Iterable[int], bone_count: int) -> list[int]:
    joints = [int(value) for value in values]
    while len(joints) < 4:
        joints.append(0)
    limit = max(0, int(bone_count) - 1)
    return [min(max(0, value), limit) for value in joints[:4]]


def _material_name(model: dict[str, Any], material_index: int) -> str:
    materials = model.get("materials") or []
    if 0 <= int(material_index) < len(materials):
        return str(materials[int(material_index)] or f"material_{material_index}")
    return f"material_{material_index}"


def _part_name(entry_name: str, mesh_index: int, material_name: str, dominant_joint_name: str, dominant_joint_ratio: float) -> str:
    parts = [_safe(entry_name, "model"), f"mesh_{int(mesh_index):03d}", _safe(material_name, f"material_{mesh_index}")]
    joint_token = _safe(dominant_joint_name, "") if dominant_joint_name else ""
    joined = "__".join(parts).lower()
    generic_joints = {"root", "root_skin", "hips", "hips_skin", "pelvis", "pelvis_skin", "center", "body_root", "body_root_skin"}
    if dominant_joint_ratio >= 0.55 and joint_token and joint_token.lower() not in generic_joints and joint_token.lower() not in joined:
        parts.append(joint_token)
    return "__".join(parts)[:240]


def _source_mesh_parts(model: dict[str, Any], bones: list[dict[str, Any]], entry_name: str) -> tuple[list[dict[str, Any]], int, int]:
    bone_count = max(1, len(bones))
    bone_names = [str(bone.get("name") or f"bone_{index:03d}") for index, bone in enumerate(bones)]
    parts: list[dict[str, Any]] = []
    face_count = 0
    source_vertex_count = sum(len(item.get("positions") or []) for item in model.get("vertex_sets", {}).values())
    for mesh in model.get("meshes") or []:
        vbuf_index = int(mesh.get("vertex_buffer_index", -1))
        ibuf_index = int(mesh.get("index_buffer_index", -1))
        vertex_set = (model.get("vertex_sets") or {}).get(vbuf_index)
        index_values = (model.get("index_sets") or {}).get(ibuf_index)
        if not vertex_set or index_values is None:
            continue
        positions_source = vertex_set.get("positions") or []
        start = int(mesh.get("index_buffer_offset", 0))
        count = int(mesh.get("index_count", 0))
        faces = rigged_gltf.build_faces(int(mesh.get("primitive_mode", 3)), index_values[start:start + count], vertex_limit=len(positions_source))
        if not faces:
            continue
        remap: dict[int, int] = {}
        source_indices: list[int] = []
        compact_indices: list[int] = []
        for face in faces:
            for source_index in face:
                source_index = int(source_index)
                if source_index not in remap:
                    remap[source_index] = len(source_indices)
                    source_indices.append(source_index)
                compact_indices.append(remap[source_index])
        normals_source = vertex_set.get("normals") or []
        uvs_source = vertex_set.get("uvs") or []
        joints_source = vertex_set.get("joints") or []
        weights_source = vertex_set.get("weights") or []
        positions: list[list[float]] = []
        normals: list[list[float]] = []
        uvs: list[list[float]] = []
        joints: list[list[int]] = []
        weights: list[list[float]] = []
        joint_totals: dict[int, float] = {}
        for source_index in source_indices:
            position = positions_source[source_index] if source_index < len(positions_source) else [0.0, 0.0, 0.0]
            normal = normals_source[source_index] if source_index < len(normals_source) else [0.0, 0.0, 1.0]
            uv = uvs_source[source_index] if source_index < len(uvs_source) else [0.0, 0.0]
            joint_set = _normalise_joint_set(joints_source[source_index] if source_index < len(joints_source) else [0, 0, 0, 0], bone_count)
            weight_set = _normalise_weight_set(weights_source[source_index] if source_index < len(weights_source) else [1.0, 0.0, 0.0, 0.0])
            positions.append([float(value) for value in position[:3]])
            normals.append([float(value) for value in normal[:3]])
            uvs.append([float(value) for value in uv[:2]])
            joints.append(joint_set)
            weights.append(weight_set)
            for joint_index, weight in zip(joint_set, weight_set):
                if weight > 0.000001:
                    joint_totals[joint_index] = joint_totals.get(joint_index, 0.0) + weight
        used_joint_indices = sorted(joint_totals)
        total_joint_weight = sum(joint_totals.values())
        dominant_joint_index = max(joint_totals, key=joint_totals.get) if joint_totals else 0
        dominant_joint_ratio = joint_totals.get(dominant_joint_index, 0.0) / total_joint_weight if total_joint_weight else 0.0
        dominant_joint_name = bone_names[dominant_joint_index] if dominant_joint_index < len(bone_names) else f"bone_{dominant_joint_index:03d}"
        material_index = int(mesh.get("material_index", 0))
        material_name = _material_name(model, material_index)
        mesh_index = int(mesh.get("mesh_index", len(parts)))
        name = _part_name(entry_name, mesh_index, material_name, dominant_joint_name, dominant_joint_ratio)
        extras = {
            "pakpy_source_mesh_partition": True,
            "pakpy_source_mesh_index": mesh_index,
            "pakpy_material_index": material_index,
            "pakpy_material_name": material_name,
            "pakpy_vertex_buffer_index": vbuf_index,
            "pakpy_index_buffer_index": ibuf_index,
            "pakpy_index_buffer_offset": start,
            "pakpy_index_count": count,
            "pakpy_primitive_mode": int(mesh.get("primitive_mode", 3)),
            "pakpy_mesh_field_10": int(mesh.get("field_10", 0)),
            "pakpy_mesh_field_12": int(mesh.get("field_12", 0)),
            "pakpy_mesh_field_13": int(mesh.get("field_13", 0)),
            "pakpy_mesh_flags": int(mesh.get("flags", 0)),
            "pakpy_source_vertex_count": len(source_indices),
            "pakpy_face_count": len(faces),
            "pakpy_used_joint_indices": used_joint_indices,
            "pakpy_used_joint_names": [bone_names[index] if index < len(bone_names) else f"bone_{index:03d}" for index in used_joint_indices],
            "pakpy_dominant_joint_index": dominant_joint_index,
            "pakpy_dominant_joint_name": dominant_joint_name,
            "pakpy_dominant_joint_ratio": round(dominant_joint_ratio, 8),
        }
        parts.append({"name": name, "positions": positions, "normals": normals, "uvs": uvs, "joints": joints, "weights": weights, "source_vertex_indices": source_indices, "indices": compact_indices, "material_index": material_index, "extras": extras})
        face_count += len(faces)
    if face_count <= 0:
        raise rigged_gltf.PakError("GLB-Export erzeugte 0 Faces")
    return parts, face_count, source_vertex_count


def _write_partitioned_glb(path, model, bones, entry_name, texture_map=None, texture_root=None, include_skin=True):
    bones = rigged_gltf._normalise_bone_nodes(bones)
    parts, face_count, source_vertex_count = _source_mesh_parts(model, bones, entry_name)
    texture_map = texture_map or {}
    texture_root = Path(texture_root) if texture_root else None
    bin_blob = bytearray()
    buffer_views: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    textures: list[dict[str, Any]] = []
    def add_view(data: bytes, target=None):
        while len(bin_blob) % 4:
            bin_blob.append(0)
        offset = len(bin_blob)
        bin_blob.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        return len(buffer_views) - 1
    def add_accessor(data: bytes, component_type: int, count: int, typ: str, target=None, min_value=None, max_value=None):
        accessor = {"bufferView": add_view(data, target=target), "byteOffset": 0, "componentType": component_type, "count": count, "type": typ}
        if min_value is not None:
            accessor["min"] = min_value
        if max_value is not None:
            accessor["max"] = max_value
        accessors.append(accessor)
        return len(accessors) - 1
    def add_image(path_text):
        if not texture_root or not path_text:
            return None
        image_path = texture_root / path_text
        if not image_path.is_file():
            return None
        mime = mimetypes.guess_type(str(image_path))[0] or "image/png"
        try:
            uri = os.path.relpath(str(image_path), str(Path(path).parent)).replace("\\", "/")
        except Exception:
            uri = str(image_path).replace("\\", "/")
        images.append({"uri": uri, "mimeType": mime, "name": image_path.stem})
        textures.append({"source": len(images) - 1})
        return len(textures) - 1
    materials = []
    for index, name in enumerate(model.get("materials") or ["material_0"]):
        info = texture_map.get(index) or texture_map.get(str(name)) or {}
        if isinstance(info, str):
            info = {"map_Kd": info}
        elif not isinstance(info, dict):
            info = {}
        base_tex_index = add_image(info.get("map_Kd") or info.get("baseColorTexture") or "")
        normal_tex_index = add_image(info.get("map_Bump") or info.get("normalTexture") or "")
        emissive_tex_index = add_image(info.get("map_Ke") or info.get("emissiveTexture") or "")
        material = {"name": str(name), "pbrMetallicRoughness": {"baseColorFactor": [1.0, 1.0, 1.0, 1.0], "metallicFactor": 0.0, "roughnessFactor": 1.0}}
        if base_tex_index is not None:
            material["pbrMetallicRoughness"]["baseColorTexture"] = {"index": base_tex_index}
        if normal_tex_index is not None:
            material["normalTexture"] = {"index": normal_tex_index}
        if emissive_tex_index is not None:
            material["emissiveTexture"] = {"index": emissive_tex_index}
            material["emissiveFactor"] = [1.0, 1.0, 1.0]
        materials.append(material)
    nodes: list[dict[str, Any]] = []
    roots: list[int] = []
    skins: list[dict[str, Any]] = []
    if include_skin:
        inverse_bind_values: list[float] = []
        for position in rigged_gltf._global_bind_positions(bones):
            inverse_bind_values.extend(rigged_gltf._inverse_translation_matrix(position))
        inverse_bind_accessor = add_accessor(rigged_gltf._pack_floats(inverse_bind_values), 5126, len(bones), "MAT4")
        for bone_index, bone in enumerate(bones):
            nodes.append({"name": bone["name"], "translation": bone["head"], "extras": {"pakpy_skin_bone": True, "pakpy_skin_bone_index": bone_index, "pakpy_skel_node_index": int(bone.get("node_index", bone_index))}})
        for bone_index, bone in enumerate(bones):
            parent_index = int(bone.get("parent_index", -1))
            if 0 <= parent_index < len(nodes) and parent_index != bone_index:
                nodes[parent_index].setdefault("children", []).append(bone_index)
            else:
                roots.append(bone_index)
        skin = {"name": entry_name + "_skin", "joints": list(range(len(bones))), "inverseBindMatrices": inverse_bind_accessor, "extras": {"pakpy_skin_bone_count": len(bones)}}
        if roots:
            skin["skeleton"] = roots[0]
        skins.append(skin)
    gltf_meshes: list[dict[str, Any]] = []
    mesh_node_indices: list[int] = []
    exported_vertex_count = 0
    for part in parts:
        positions = part["positions"]
        pos_accessor = add_accessor(rigged_gltf._pack_floats([value for item in positions for value in item]), 5126, len(positions), "VEC3", target=34962, min_value=[min(position[axis] for position in positions) for axis in range(3)], max_value=[max(position[axis] for position in positions) for axis in range(3)])
        normal_accessor = add_accessor(rigged_gltf._pack_floats([value for item in part["normals"] for value in item]), 5126, len(part["normals"]), "VEC3", target=34962)
        uv_accessor = add_accessor(rigged_gltf._pack_gltf_uvs(part["uvs"]), 5126, len(part["uvs"]), "VEC2", target=34962)
        source_index_accessor = add_accessor(rigged_gltf._pack_u32(part["source_vertex_indices"]), 5125, len(part["source_vertex_indices"]), "SCALAR", target=34962)
        attributes = {"POSITION": pos_accessor, "NORMAL": normal_accessor, "TEXCOORD_0": uv_accessor, "_PAKPY_SOURCE_VERTEX_INDEX": source_index_accessor}
        if include_skin:
            attributes["JOINTS_0"] = add_accessor(rigged_gltf._pack_u16([value for item in part["joints"] for value in item]), 5123, len(part["joints"]), "VEC4", target=34962)
            attributes["WEIGHTS_0"] = add_accessor(rigged_gltf._pack_floats([value for item in part["weights"] for value in item]), 5126, len(part["weights"]), "VEC4", target=34962)
        index_accessor = add_accessor(rigged_gltf._pack_u32(part["indices"]), 5125, len(part["indices"]), "SCALAR", target=34963)
        material_index = part["material_index"] if part["material_index"] < max(1, len(materials)) else 0
        gltf_meshes.append({"name": part["name"], "primitives": [{"attributes": attributes, "indices": index_accessor, "material": material_index}], "extras": dict(part["extras"])})
        node = {"name": part["name"], "mesh": len(gltf_meshes) - 1, "extras": dict(part["extras"])}
        if include_skin:
            node["skin"] = 0
        nodes.append(node)
        mesh_node_indices.append(len(nodes) - 1)
        exported_vertex_count += len(positions)
    gltf = {"asset": {"version": "2.0", "generator": "PAKPY", "extras": {"pakpy_source_mesh_partitioning": True, "pakpy_entry_name": entry_name, "pakpy_source_mesh_count": len(parts)}}, "scene": 0, "scenes": [{"nodes": mesh_node_indices + roots if include_skin else mesh_node_indices}], "nodes": nodes, "meshes": gltf_meshes, "materials": materials, "buffers": [{"byteLength": len(bin_blob)}], "bufferViews": buffer_views, "accessors": accessors}
    if include_skin:
        gltf["skins"] = skins
    if images:
        gltf["images"] = images
        gltf["textures"] = textures
    json_blob = rigged_gltf._align4(json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), b" ")
    bin_data = rigged_gltf._align4(bytes(bin_blob), b"\x00")
    total_length = 12 + 8 + len(json_blob) + 8 + len(bin_data)
    output = bytearray(struct.pack("<III", 0x46546C67, 2, total_length))
    output.extend(struct.pack("<I4s", len(json_blob), b"JSON")); output.extend(json_blob)
    output.extend(struct.pack("<I4s", len(bin_data), b"BIN\x00")); output.extend(bin_data)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(output)
    return {"glb_path": str(path), "vertex_count": source_vertex_count, "exported_vertex_count": exported_vertex_count, "face_count": face_count, "bone_count": len(bones) if include_skin else 0, "mesh_count": len(parts), "mesh_parts": [{"name": part["name"], **part["extras"]} for part in parts]}


def _matrix_column_major(values: Any) -> list[float] | None:
    if not isinstance(values, (list, tuple)) or len(values) != 16:
        return None
    return [float(values[row * 4 + column]) for column in range(4) for row in range(4)]


def _patch_skel_helper_nodes(glb_path: str | Path, skeleton: dict[str, Any]) -> list[dict[str, Any]]:
    summary = skeleton.get("raw_skel_summary") or {}
    raw_nodes = summary.get("nodes") or []
    bones = skeleton.get("bones") or []
    if not raw_nodes or not bones:
        return []
    chunks = skeletal_tail_patch._read_glb(glb_path)
    if chunks is None:
        return []
    gltf = json.loads(bytes(chunks[0][1]).decode("utf-8"))
    nodes = gltf.get("nodes") or []
    skins = gltf.get("skins") or []
    if not skins:
        return []
    joints = list(skins[0].get("joints") or [])
    raw_to_gltf: dict[int, int] = {}
    for bone_index, bone in enumerate(bones[:len(joints)]):
        raw_index = int(bone.get("node_index", bone_index)); gltf_index = int(joints[bone_index])
        raw_to_gltf[raw_index] = gltf_index
        if 0 <= gltf_index < len(nodes):
            extras = nodes[gltf_index].setdefault("extras", {})
            extras.update({"pakpy_skel_node_index": raw_index, "pakpy_skin_bone_index": bone_index, "pakpy_skin_bone": True})
    helper_records: list[dict[str, Any]] = []
    helper_raw_indices = [int(item.get("index", index)) for index, item in enumerate(raw_nodes) if int(item.get("index", index)) not in raw_to_gltf]
    for raw_index in helper_raw_indices:
        raw = raw_nodes[raw_index] if 0 <= raw_index < len(raw_nodes) else {}
        name = str(raw.get("name") or f"skel_node_{raw_index:03d}")
        parent_index = int(raw.get("parent_index", 255))
        parent_name = str(raw_nodes[parent_index].get("name") or f"skel_node_{parent_index:03d}") if 0 <= parent_index < len(raw_nodes) else ""
        extras = {"pakpy_skel_helper": True, "pakpy_non_deform_helper": True, "pakpy_skel_node_index": raw_index, "pakpy_skel_name_index": int(raw.get("name_index", raw_index)), "pakpy_skel_parent_node_index": parent_index, "pakpy_skel_parent_name": parent_name, "pakpy_skel_flags": int(raw.get("flags", 0))}
        node: dict[str, Any] = {"name": name, "extras": extras}
        matrix = _matrix_column_major(raw.get("matrix"))
        if matrix is not None:
            node["matrix"] = matrix
        else:
            node["translation"] = [float(value) for value in (raw.get("translation") or [0.0, 0.0, 0.0])[:3]]
        nodes.append(node); raw_to_gltf[raw_index] = len(nodes) - 1
        helper_records.append({"name": name, **extras})
    scene_roots = gltf.get("scenes", [{}])[int(gltf.get("scene", 0))].setdefault("nodes", [])
    for raw_index in helper_raw_indices:
        raw = raw_nodes[raw_index] if 0 <= raw_index < len(raw_nodes) else {}
        child_gltf = raw_to_gltf[raw_index]; parent_gltf = raw_to_gltf.get(int(raw.get("parent_index", 255)))
        if parent_gltf is not None and parent_gltf != child_gltf:
            children = nodes[parent_gltf].setdefault("children", [])
            if child_gltf not in children:
                children.append(child_gltf)
        elif child_gltf not in scene_roots:
            scene_roots.append(child_gltf)
    gltf["nodes"] = nodes
    gltf.setdefault("asset", {}).setdefault("extras", {})["pakpy_skel_helper_count"] = len(helper_records)
    skeletal_tail_patch._write_glb(glb_path, chunks, gltf)
    return helper_records


def _wrap_rigged_export(original):
    def export_rigged_model_glb(parsed, entry, out_path, require_store=None, skeleton_refs=None, texture_map=None, texture_root=None):
        result = original(parsed, entry, out_path, require_store=require_store, skeleton_refs=skeleton_refs, texture_map=texture_map, texture_root=texture_root)
        helpers = _patch_skel_helper_nodes(result.get("glb_path") or out_path, result.get("skeleton") or {})
        result["skel_helper_count"] = len(helpers); result["skel_helpers"] = helpers
        return result
    export_rigged_model_glb._pakpy_source_mesh_partition = True
    return export_rigged_model_glb


def _blend_script(glb_path, blend_path, obj_path=None) -> str:
    return "\n".join([
        "import bpy, json, struct",
        "from pathlib import Path",
        "from mathutils import Vector",
        f"GLB_PATH={json.dumps(str(glb_path))}", f"BLEND_PATH={json.dumps(str(blend_path))}",
        "def _gltf_json(path):",
        "    data=Path(path).read_bytes()",
        "    if len(data)<20 or data[:4]!=b'glTF': return {}",
        "    size,kind=struct.unpack_from('<I4s',data,12)",
        "    return json.loads(data[20:20+size].decode('utf-8')) if kind==b'JSON' else {}",
        "gltf=_gltf_json(GLB_PATH)", "nodes=gltf.get('nodes') or []", "asset_extras=(gltf.get('asset') or {}).get('extras') or {}", "entry_name=str(asset_extras.get('pakpy_entry_name') or Path(GLB_PATH).stem)",
        "mesh_specs=[node for node in nodes if isinstance(node,dict) and 'mesh' in node and ((node.get('extras') or {}).get('pakpy_source_mesh_partition'))]",
        "helper_specs=[node for node in nodes if isinstance(node,dict) and ((node.get('extras') or {}).get('pakpy_skel_helper'))]",
        "joint_specs=[node for node in nodes if isinstance(node,dict) and ((node.get('extras') or {}).get('pakpy_skin_bone'))]",
        "try: bpy.ops.object.mode_set(mode='OBJECT')", "except Exception: pass", "bpy.ops.object.select_all(action='SELECT')", "bpy.ops.object.delete()",
        "try: bpy.ops.preferences.addon_enable(module='io_scene_gltf2')", "except Exception: pass", "bpy.ops.import_scene.gltf(filepath=GLB_PATH)",
        "def _set_props(target,values):",
        "    for key,value in (values or {}).items():",
        "        try: target[key]=json.dumps(value,ensure_ascii=False) if isinstance(value,dict) else value",
        "        except Exception: target[key]=str(value)",
        "mesh_objects=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']", "by_name={obj.name:obj for obj in mesh_objects}", "unused=list(mesh_objects)",
        "part_collection=bpy.data.collections.get(entry_name+'__MESH_PARTS') or bpy.data.collections.new(entry_name+'__MESH_PARTS')",
        "if part_collection.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(part_collection)",
        "for spec in sorted(mesh_specs,key=lambda item:int((item.get('extras') or {}).get('pakpy_source_mesh_index',0))):",
        "    name=str(spec.get('name') or 'mesh_part'); obj=by_name.get(name)",
        "    if obj is None: obj=next((item for item in unused if item.name.startswith(name)),None)",
        "    if obj is None and unused: obj=unused[0]",
        "    if obj is None: continue",
        "    if obj in unused: unused.remove(obj)",
        "    obj.name=name; obj.data.name=name+'__Mesh'; _set_props(obj,spec.get('extras') or {}); _set_props(obj.data,spec.get('extras') or {})",
        "    if obj.name not in part_collection.objects: part_collection.objects.link(obj)",
        "armatures=[obj for obj in bpy.context.scene.objects if obj.type=='ARMATURE']", "armature_obj=max(armatures,key=lambda item:len(item.data.bones)) if armatures else None",
        "if armature_obj is not None:",
        "    armature_obj.name=entry_name+'__Armature'; armature_obj.data.name=entry_name+'__Skeleton'; armature_obj['pakpy_exact_skel_rig']=True",
        "    for spec in joint_specs:",
        "        bone=armature_obj.data.bones.get(str(spec.get('name') or ''))",
        "        if bone: _set_props(bone,spec.get('extras') or {})",
        "helper_objects={obj.name:obj for obj in bpy.context.scene.objects if obj.type=='EMPTY'}",
        "helper_collection=bpy.data.collections.get(entry_name+'__SKEL_HELPERS') or bpy.data.collections.new(entry_name+'__SKEL_HELPERS')",
        "if helper_collection.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(helper_collection)",
        "for spec in helper_specs:",
        "    name=str(spec.get('name') or 'skel_helper'); obj=helper_objects.get(name) or next((item for item in helper_objects.values() if item.name.startswith(name)),None)",
        "    if obj: obj.name=name; _set_props(obj,spec.get('extras') or {}); helper_collection.objects.link(obj) if obj.name not in helper_collection.objects else None",
        "helper_bones=0",
        "if armature_obj is not None and helper_specs:",
        "    try:",
        "        bpy.ops.object.select_all(action='DESELECT'); armature_obj.select_set(True); bpy.context.view_layer.objects.active=armature_obj; bpy.ops.object.mode_set(mode='EDIT')",
        "        pending=list(helper_specs); created=set()",
        "        for _pass in range(len(pending)+1):",
        "            progress=False",
        "            for spec in list(pending):",
        "                name=str(spec.get('name') or 'skel_helper'); extras=spec.get('extras') or {}; parent_name=str(extras.get('pakpy_skel_parent_name') or '')",
        "                if parent_name and armature_obj.data.edit_bones.get(parent_name) is None and parent_name not in created: continue",
        "                obj=helper_objects.get(name)",
        "                if obj is None: pending.remove(spec); continue",
        "                matrix=armature_obj.matrix_world.inverted() @ obj.matrix_world; head=matrix.translation; axis=matrix.to_3x3() @ Vector((0.0,0.035,0.0))",
        "                if axis.length<0.000001: axis=Vector((0.0,0.035,0.0))",
        "                bone=armature_obj.data.edit_bones.get(name) or armature_obj.data.edit_bones.new(name); bone.head=head; bone.tail=head+axis.normalized()*0.035; bone.use_deform=False; bone.use_connect=False",
        "                parent=armature_obj.data.edit_bones.get(parent_name) if parent_name else None",
        "                if parent is not None and parent!=bone: bone.parent=parent",
        "                created.add(name); pending.remove(spec); progress=True; helper_bones+=1",
        "            if not progress: break",
        "        bpy.ops.object.mode_set(mode='OBJECT')",
        "        for spec in helper_specs:",
        "            bone=armature_obj.data.bones.get(str(spec.get('name') or ''))",
        "            if bone: bone.use_deform=False; _set_props(bone,spec.get('extras') or {})",
        "    except Exception as exc:",
        "        try: bpy.ops.object.mode_set(mode='OBJECT')", "        except Exception: pass", "        armature_obj['pakpy_helper_bone_error']=str(exc)",
        "Path(BLEND_PATH).parent.mkdir(parents=True,exist_ok=True)", "bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)",
        "print('PAKPY_MESH_PARTS=%d' % len(mesh_specs))", "print('PAKPY_SKEL_HELPERS=%d' % len(helper_specs))", "print('PAKPY_HELPER_BONES=%d' % helper_bones)", "",
    ])


def _read_glb_summary(path: Path) -> dict[str, Any]:
    chunks = skeletal_tail_patch._read_glb(path)
    if chunks is None:
        return {}
    gltf = json.loads(bytes(chunks[0][1]).decode("utf-8")); parts = []; helpers = []
    for node in gltf.get("nodes") or []:
        extras = node.get("extras") or {}
        if extras.get("pakpy_source_mesh_partition"):
            parts.append({"name": node.get("name", ""), **extras})
        if extras.get("pakpy_skel_helper"):
            helpers.append({"name": node.get("name", ""), **extras})
    return {"parts": parts, "helpers": helpers}


def _wrap_model_package(original):
    def export_model_package(parsed, entry, out_dir, require_store=None, animation_refs=None, skeleton_refs=None):
        result = original(parsed, entry, out_dir, require_store=require_store, animation_refs=animation_refs, skeleton_refs=skeleton_refs)
        package_dir = Path(result.get("package_dir") or ""); manifest_path = package_dir / "repack_manifest.json"; glb_path = Path(result.get("experimental_skeletal_glb") or "")
        if manifest_path.is_file() and glb_path.is_file():
            summary = _read_glb_summary(glb_path); manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_mesh_object_count"] = len(summary.get("parts") or []); manifest["source_mesh_objects"] = summary.get("parts") or []
            manifest["skel_helper_count"] = len(summary.get("helpers") or []); manifest["skel_helpers"] = summary.get("helpers") or []
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
            result["source_mesh_object_count"] = manifest["source_mesh_object_count"]; result["skel_helper_count"] = manifest["skel_helper_count"]
        return result
    export_model_package._pakpy_source_mesh_manifest = True
    return export_model_package


def install() -> None:
    rigged_gltf._write_glb = _write_partitioned_glb
    if not getattr(rigged_gltf.export_rigged_model_glb, "_pakpy_source_mesh_partition", False):
        rigged_gltf.export_rigged_model_glb = _wrap_rigged_export(rigged_gltf.export_rigged_model_glb)
    skeletal_tail_patch._connected_blend_script = _blend_script
    if not getattr(model_package.export_model_package, "_pakpy_source_mesh_manifest", False):
        patched = _wrap_model_package(model_package.export_model_package); model_package.export_model_package = patched
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
