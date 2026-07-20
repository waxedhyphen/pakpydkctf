"""Preserve exact SKEL bind matrices in generated GLB/BLEND rigs.

The older connected-rig export rebuilt bone rotations from head/tail directions and
then moved every Blender child head onto its parent's tail. That changes the rest
matrices. This patch keeps the serialized SKEL global matrices and inverse bind
matrices (apart from float32 storage in glTF) and imports the GLB into Blender
without editing the armature.
"""
from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Sequence

import skeletal_tail_patch


class ExactSkeletalRigError(ValueError):
    pass


def _matrix4(values: Sequence[float], label: str) -> list[list[float]]:
    if not isinstance(values, (list, tuple)) or len(values) != 16:
        raise ExactSkeletalRigError(f"{label} must contain 16 values")
    out = [[float(values[row * 4 + column]) for column in range(4)] for row in range(4)]
    if not all(math.isfinite(value) for row in out for value in row):
        raise ExactSkeletalRigError(f"{label} contains non-finite values")
    if any(abs(out[3][column]) > 1e-5 for column in range(3)) or abs(out[3][3] - 1.0) > 1e-5:
        raise ExactSkeletalRigError(f"{label} is not an affine row-major matrix")
    return out


def _flatten_column_major(matrix: Sequence[Sequence[float]]) -> list[float]:
    # glTF MAT4 accessor and node.matrix values are column-major arrays.
    return [float(matrix[row][column]) for column in range(4) for row in range(4)]


def _mul(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list[list[float]]:
    return [
        [sum(float(a[row][k]) * float(b[k][column]) for k in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _inverse_affine(matrix: Sequence[Sequence[float]]) -> list[list[float]]:
    m = matrix
    a, b, c = float(m[0][0]), float(m[0][1]), float(m[0][2])
    d, e, f = float(m[1][0]), float(m[1][1]), float(m[1][2])
    g, h, i = float(m[2][0]), float(m[2][1]), float(m[2][2])
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
        raise ExactSkeletalRigError("SKEL matrix has a singular 3x3 basis")
    inv_det = 1.0 / determinant
    inverse_basis = [
        [(e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det],
        [(f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det],
        [(d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det],
    ]
    translation = [float(m[0][3]), float(m[1][3]), float(m[2][3])]
    inverse_translation = [
        -sum(inverse_basis[row][column] * translation[column] for column in range(3))
        for row in range(3)
    ]
    return [
        [*inverse_basis[0], inverse_translation[0]],
        [*inverse_basis[1], inverse_translation[1]],
        [*inverse_basis[2], inverse_translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _bone_global_matrix(bone: dict, index: int) -> list[list[float]]:
    values = bone.get("global_matrix")
    if isinstance(values, (list, tuple)) and len(values) == 16:
        return _matrix4(values, f"bone[{index}].global_matrix")
    inverse_values = bone.get("inverse_bind_matrix")
    if isinstance(inverse_values, (list, tuple)) and len(inverse_values) == 16:
        return _inverse_affine(_matrix4(inverse_values, f"bone[{index}].inverse_bind_matrix"))
    raise ExactSkeletalRigError(f"bone[{index}] has no exact SKEL global/inverse-bind matrix")


def _bone_inverse_bind_matrix(
    bone: dict, index: int, global_matrix: Sequence[Sequence[float]]
) -> list[list[float]]:
    values = bone.get("inverse_bind_matrix")
    if isinstance(values, (list, tuple)) and len(values) == 16:
        return _matrix4(values, f"bone[{index}].inverse_bind_matrix")
    return _inverse_affine(global_matrix)


def _parent_index(bone: dict, index: int, count: int) -> int:
    try:
        parent = int(bone.get("parent_index", -1))
    except Exception:
        parent = -1
    if parent < 0 or parent >= count or parent == index:
        return -1
    return parent


def _find_binary_chunk(chunks):
    for item in chunks:
        if item[0] == b"BIN\x00":
            return item[1]
    raise ExactSkeletalRigError("GLB has no BIN chunk")


def patch_glb_bind_pose(path, bones) -> bool:
    """Replace glTF joint locals and inverse binds with exact SKEL matrices."""
    chunks = skeletal_tail_patch._read_glb(path)
    if chunks is None:
        raise ExactSkeletalRigError(f"not a readable GLB: {path}")
    gltf = json.loads(bytes(chunks[0][1]).decode("utf-8"))
    nodes = gltf.get("nodes") or []
    skins = gltf.get("skins") or []
    if not skins:
        raise ExactSkeletalRigError("GLB has no skin")
    skin = skins[0]
    joints = list(skin.get("joints") or [])
    if not joints:
        raise ExactSkeletalRigError("GLB skin has no joints")
    if len(bones) < len(joints):
        raise ExactSkeletalRigError(
            f"SKEL supplies {len(bones)} bones but GLB skin contains {len(joints)} joints"
        )
    count = len(joints)
    globals_ = [_bone_global_matrix(bones[index], index) for index in range(count)]
    inverse_binds = [
        _bone_inverse_bind_matrix(bones[index], index, globals_[index])
        for index in range(count)
    ]

    for index, node_index in enumerate(joints):
        if not 0 <= int(node_index) < len(nodes):
            raise ExactSkeletalRigError(f"joint node index {node_index} is outside GLB nodes")
        parent = _parent_index(bones[index], index, count)
        local = _mul(_inverse_affine(globals_[parent]), globals_[index]) if parent >= 0 else globals_[index]
        node = nodes[int(node_index)]
        node.pop("translation", None)
        node.pop("rotation", None)
        node.pop("scale", None)
        node["matrix"] = _flatten_column_major(local)
        node.setdefault("extras", {})["pakpy_exact_skel_matrix"] = True

    accessor_index = skin.get("inverseBindMatrices")
    if accessor_index is None:
        raise ExactSkeletalRigError("GLB skin has no inverseBindMatrices accessor")
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    if not 0 <= int(accessor_index) < len(accessors):
        raise ExactSkeletalRigError("inverseBindMatrices accessor is outside accessor table")
    accessor = accessors[int(accessor_index)]
    view_index = accessor.get("bufferView")
    if view_index is None or not 0 <= int(view_index) < len(views):
        raise ExactSkeletalRigError("inverseBindMatrices bufferView is invalid")
    if int(accessor.get("componentType", 5126)) != 5126 or accessor.get("type") != "MAT4":
        raise ExactSkeletalRigError("inverseBindMatrices accessor is not float32 MAT4")
    if int(accessor.get("count", 0)) < count:
        raise ExactSkeletalRigError("inverseBindMatrices accessor contains too few matrices")
    view = views[int(view_index)]
    byte_stride = int(view.get("byteStride", 64))
    if byte_stride != 64:
        raise ExactSkeletalRigError(f"unsupported inverse-bind byteStride {byte_stride}")
    binary = _find_binary_chunk(chunks)
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    end = start + count * 64
    if start < 0 or end > len(binary):
        raise ExactSkeletalRigError("inverse-bind matrix range is outside GLB BIN chunk")
    values = [value for matrix in inverse_binds for value in _flatten_column_major(matrix)]
    binary[start:end] = struct.pack("<" + "f" * len(values), *values)

    skin.setdefault("extras", {})["pakpy_exact_skel_bind"] = True
    gltf.setdefault("asset", {}).setdefault("extras", {})["pakpy_exact_skel_rig"] = True
    skeletal_tail_patch._write_glb(path, chunks, gltf)
    return True


def exact_blend_script(glb_path, blend_path, obj_path=None) -> str:
    """Import the exact GLB and save it without mutating Blender edit bones."""
    return "\n".join(
        [
            "import bpy",
            "from pathlib import Path",
            f"GLB_PATH={json.dumps(str(glb_path))}",
            f"BLEND_PATH={json.dumps(str(blend_path))}",
            "try:",
            "    bpy.ops.object.mode_set(mode='OBJECT')",
            "except Exception:",
            "    pass",
            "bpy.ops.object.select_all(action='SELECT')",
            "bpy.ops.object.delete()",
            "try:",
            "    bpy.ops.preferences.addon_enable(module='io_scene_gltf2')",
            "except Exception:",
            "    pass",
            "bpy.ops.import_scene.gltf(filepath=GLB_PATH)",
            "armatures=[obj for obj in bpy.context.scene.objects if obj.type=='ARMATURE']",
            "if not armatures:",
            "    raise RuntimeError('No armature imported from exact SKEL GLB')",
            "armature_obj=max(armatures,key=lambda item: len(item.data.bones))",
            "armature_obj['pakpy_exact_skel_rig']=True",
            "bpy.ops.object.select_all(action='DESELECT')",
            "armature_obj.select_set(True)",
            "bpy.context.view_layer.objects.active=armature_obj",
            "try:",
            "    bpy.ops.file.pack_all()",
            "except Exception:",
            "    pass",
            "Path(BLEND_PATH).parent.mkdir(parents=True,exist_ok=True)",
            "bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)",
            "print('PAKPY_EXACT_SKEL_BONES=%d' % len(armature_obj.data.bones))",
            "",
        ]
    )


def install() -> None:
    skeletal_tail_patch._patch_glb_bind_pose = patch_glb_bind_pose
    skeletal_tail_patch._connected_blend_script = exact_blend_script