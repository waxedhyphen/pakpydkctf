"""Blender background export and glTF extraction for model geometry repacking."""
from __future__ import annotations

import json
import math
import os
import re
import struct
import subprocess
from pathlib import Path
from typing import Any, Iterable

import pak_core
import skeletal_tail_patch

EPSILON = 2.0e-4

def _snapshot_blend_script(original):
    def wrapped(glb_path, blend_path, obj_path=None):
        base = original(glb_path, blend_path, obj_path)
        snapshot = [
            "# PAKPY bind snapshot for geometry repacking",
            "import json",
            "armatures=[obj for obj in bpy.context.scene.objects if obj.type=='ARMATURE']",
            "armature_obj=max(armatures,key=lambda item:len(item.data.bones)) if armatures else None",
            "if armature_obj is not None:",
            "    armature_obj['pakpy_bind_snapshot_version']=1",
            "    armature_obj['pakpy_bind_object_matrix_json']=json.dumps([float(armature_obj.matrix_world[r][c]) for r in range(4) for c in range(4)],separators=(',',':'))",
            "    snap_count=0",
            "    for bone in armature_obj.data.bones:",
            "        if bone.get('pakpy_skin_bone') or bone.get('pakpy_skin_bone_index') is not None:",
            "            bone['pakpy_bind_name']=bone.name",
            "            bone['pakpy_bind_parent_name']=bone.parent.name if bone.parent else ''",
            "            bone['pakpy_bind_matrix_local_json']=json.dumps([float(bone.matrix_local[r][c]) for r in range(4) for c in range(4)],separators=(',',':'))",
            "            snap_count+=1",
            "    armature_obj['pakpy_bind_snapshot_bone_count']=snap_count",
            "Path(BLEND_PATH).parent.mkdir(parents=True,exist_ok=True)",
            "bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)",
            "print('PAKPY_BIND_SNAPSHOT_BONES=%d' % (snap_count if armature_obj is not None else 0))",
            "",
        ]
        return base + "\n" + "\n".join(snapshot)
    wrapped._pakpy_geometry_bind_snapshot = True
    return wrapped


def _blender_export_script(output_glb: Path) -> str:
    return "\n".join(
        [
            "import bpy, json, math, sys",
            "from pathlib import Path",
            f"OUTPUT_GLB={json.dumps(str(output_glb))}",
            f"EPS={EPSILON!r}",
            "def _flat(matrix): return [float(matrix[r][c]) for r in range(4) for c in range(4)]",
            "def _read_json_prop(owner,key):",
            "    value=owner.get(key)",
            "    if value is None: return None",
            "    try: return json.loads(str(value))",
            "    except Exception: return None",
            "def _near(a,b):",
            "    return isinstance(a,(list,tuple)) and isinstance(b,(list,tuple)) and len(a)==len(b) and max((abs(float(x)-float(y)) for x,y in zip(a,b)),default=0.0)<=EPS",
            "armatures=[obj for obj in bpy.context.scene.objects if obj.type=='ARMATURE']",
            "if not armatures: raise RuntimeError('Keine Armature in der BLEND-Datei gefunden')",
            "armature=max(armatures,key=lambda item:len(item.data.bones))",
            "if int(armature.get('pakpy_bind_snapshot_version',0))!=1: raise RuntimeError('Bind-Snapshot fehlt; CHAR/Modellpaket mit aktueller PAKPY-Version neu exportieren')",
            "expected_object=_read_json_prop(armature,'pakpy_bind_object_matrix_json')",
            "if expected_object is None or not _near(expected_object,_flat(armature.matrix_world)): raise RuntimeError('Armature-Objekttransform wurde verändert')",
            "skin_bones=[]",
            "for bone in armature.data.bones:",
            "    skin_index=bone.get('pakpy_skin_bone_index')",
            "    if skin_index is None: continue",
            "    expected_name=str(bone.get('pakpy_bind_name') or '')",
            "    expected_parent=str(bone.get('pakpy_bind_parent_name') or '')",
            "    current_parent=bone.parent.name if bone.parent else ''",
            "    if expected_name and bone.name!=expected_name: raise RuntimeError('Bone wurde umbenannt: '+expected_name+' -> '+bone.name)",
            "    if current_parent!=expected_parent: raise RuntimeError('Bone-Hierarchie wurde verändert: '+bone.name)",
            "    expected=_read_json_prop(bone,'pakpy_bind_matrix_local_json')",
            "    if expected is None: raise RuntimeError('Bind-Snapshot fehlt für Bone '+bone.name)",
            "    if not _near(expected,_flat(bone.matrix_local)): raise RuntimeError('Rest-Pose wurde verändert: '+bone.name)",
            "    skin_bones.append((int(skin_index),bone.name))",
            "skin_bones.sort()",
            "if len(skin_bones)!=int(armature.get('pakpy_bind_snapshot_bone_count',-1)): raise RuntimeError('Skin-Bone-Anzahl wurde verändert')",
            "if skin_bones and [i for i,_ in skin_bones]!=list(range(len(skin_bones))): raise RuntimeError('Skin-Bone-Indizes sind nicht mehr vollständig')",
            "mesh_parts=[obj for obj in bpy.context.scene.objects if obj.type=='MESH' and obj.get('pakpy_source_mesh_index') is not None]",
            "if not mesh_parts: raise RuntimeError('Keine PAKPY MESH_PARTS in der BLEND-Datei gefunden')",
            "indices=[int(obj.get('pakpy_source_mesh_index')) for obj in mesh_parts]",
            "if len(indices)!=len(set(indices)): raise RuntimeError('Doppelte pakpy_source_mesh_index Werte in der BLEND-Datei')",
            "armature.data.pose_position='REST'",
            "try: bpy.ops.object.mode_set(mode='OBJECT')",
            "except Exception: pass",
            "bpy.ops.object.select_all(action='DESELECT')",
            "armature.hide_set(False); armature.hide_viewport=False; armature.select_set(True)",
            "for obj in mesh_parts:",
            "    obj.hide_set(False); obj.hide_viewport=False; obj.select_set(True)",
            "bpy.context.view_layer.objects.active=armature",
            "try: bpy.ops.preferences.addon_enable(module='io_scene_gltf2')",
            "except Exception: pass",
            "props=set(bpy.ops.export_scene.gltf.get_rna_type().properties.keys())",
            "options={",
            " 'filepath':OUTPUT_GLB,'export_format':'GLB','use_selection':True,'export_extras':True,",
            " 'export_animations':False,'export_skins':True,'export_morph':False,'export_yup':True,",
            " 'export_apply':True,'export_normals':True,'export_tangents':True,'export_texcoords':True,",
            " 'export_rest_position_armature':True,'export_current_frame':False,",
            " 'export_all_influences':False,'export_def_bones':False,",
            "}",
            "options={key:value for key,value in options.items() if key in props}",
            "Path(OUTPUT_GLB).parent.mkdir(parents=True,exist_ok=True)",
            "result=bpy.ops.export_scene.gltf(**options)",
            "if not Path(OUTPUT_GLB).is_file(): raise RuntimeError('Blender hat keine temporäre GLB-Datei erzeugt: '+str(result))",
            "print('PAKPY_REPACK_MESH_PARTS=%d' % len(mesh_parts))",
            "print('PAKPY_REPACK_SKIN_BONES=%d' % len(skin_bones))",
            "",
        ]
    )


def _run_blender_export(blend_path: Path, debug_dir: Path) -> Path:
    blender = skeletal_tail_patch._find_blender_exe()
    if not blender:
        raise pak_core.PakError(
            "Blender wurde nicht gefunden. PAKPY_BLENDER_EXE oder BLENDER_EXE auf blender.exe setzen."
        )
    debug_dir.mkdir(parents=True, exist_ok=True)
    output_glb = debug_dir / "repack_from_blend.glb"
    script_path = debug_dir / "repack_from_blend_tmp.py"
    log_path = debug_dir / "repack_from_blend.log.txt"
    script_path.write_text(_blender_export_script(output_glb), encoding="utf-8", newline="\n")
    creationflags = 0x08000000 if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [blender, "--background", str(blend_path), "--python", str(script_path)],
            capture_output=True,
            text=True,
            timeout=600,
            creationflags=creationflags,
        )
    except Exception as exc:
        raise pak_core.PakError(f"Blender-Geometrieexport fehlgeschlagen: {exc}") from exc
    finally:
        try:
            script_path.unlink()
        except Exception:
            pass
    log_text = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    log_path.write_text(log_text, encoding="utf-8", newline="\n")
    if completed.returncode != 0 or not output_glb.is_file():
        raise pak_core.PakError(
            "Blender-Geometrieexport fehlgeschlagen:\n" + (log_text[-4000:] or f"Exitcode {completed.returncode}")
        )
    return output_glb


def _read_glb(path: Path) -> tuple[dict[str, Any], bytes]:
    data = path.read_bytes()
    if len(data) < 20:
        raise pak_core.PakError("Temporäre Blender-GLB ist zu klein")
    magic, version, total = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67 or version != 2 or total != len(data):
        raise pak_core.PakError("Temporäre Blender-GLB hat einen ungültigen Header")
    offset = 12
    gltf = None
    binary = b""
    while offset + 8 <= len(data):
        size, kind = struct.unpack_from("<I4s", data, offset)
        offset += 8
        chunk = data[offset : offset + size]
        offset += size
        if kind == b"JSON":
            gltf = json.loads(chunk.decode("utf-8"))
        elif kind == b"BIN\x00":
            binary = chunk
    if not isinstance(gltf, dict):
        raise pak_core.PakError("Temporäre Blender-GLB enthält keinen JSON-Chunk")
    return gltf, binary


_COMPONENTS = {
    5120: ("b", 1, True),
    5121: ("B", 1, False),
    5122: ("h", 2, True),
    5123: ("H", 2, False),
    5125: ("I", 4, False),
    5126: ("f", 4, True),
}
_TYPE_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _normalise_integer(value: int, component_type: int) -> float:
    if component_type == 5120:
        return max(float(value) / 127.0, -1.0)
    if component_type == 5121:
        return float(value) / 255.0
    if component_type == 5122:
        return max(float(value) / 32767.0, -1.0)
    if component_type == 5123:
        return float(value) / 65535.0
    return float(value)


def _read_accessor(gltf: dict[str, Any], binary: bytes, accessor_index: int) -> list[Any]:
    accessors = gltf.get("accessors") or []
    views = gltf.get("bufferViews") or []
    if not 0 <= int(accessor_index) < len(accessors):
        raise pak_core.PakError(f"GLB-Accessor {accessor_index} liegt außerhalb der Tabelle")
    accessor = accessors[int(accessor_index)]
    if accessor.get("sparse"):
        raise pak_core.PakError("Sparse GLB-Accessors werden beim Rückbau nicht unterstützt")
    view_index = accessor.get("bufferView")
    if view_index is None or not 0 <= int(view_index) < len(views):
        raise pak_core.PakError("GLB-Accessor hat keinen gültigen bufferView")
    view = views[int(view_index)]
    component_type = int(accessor.get("componentType", 0))
    if component_type not in _COMPONENTS:
        raise pak_core.PakError(f"Nicht unterstützter GLB-Komponententyp {component_type}")
    fmt, component_size, _signed = _COMPONENTS[component_type]
    type_name = str(accessor.get("type", "SCALAR"))
    component_count = _TYPE_COUNTS.get(type_name)
    if component_count is None:
        raise pak_core.PakError(f"Nicht unterstützter GLB-Accessor-Typ {type_name}")
    count = int(accessor.get("count", 0))
    element_size = component_size * component_count
    stride = int(view.get("byteStride", element_size))
    start = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    normalized = bool(accessor.get("normalized", False))
    out: list[Any] = []
    unpack_fmt = "<" + fmt * component_count
    for index in range(count):
        offset = start + index * stride
        if offset < 0 or offset + element_size > len(binary):
            raise pak_core.PakError("GLB-Accessor läuft aus dem BIN-Chunk heraus")
        values = list(struct.unpack_from(unpack_fmt, binary, offset))
        if normalized and component_type != 5126:
            values = [_normalise_integer(int(value), component_type) for value in values]
        out.append(values[0] if component_count == 1 else values)
    return out
