"""Blender script: import a RenderDoc animation-reference JSON as an Action.

Run in Blender's Scripting workspace after importing/selecting the armature.
Set REFERENCE_JSON below or pass it after `--` when running Blender in batch.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

REFERENCE_JSON = "renderdoc_b_idle_reference.json"
ACTION_NAME = "RenderDoc_b_idle_reference"
FRAME_START = 1


def argument_path() -> Path:
    if "--" in sys.argv:
        args = sys.argv[sys.argv.index("--") + 1 :]
        if args:
            return Path(args[0]).expanduser().resolve()
    return Path(REFERENCE_JSON).expanduser().resolve()


def active_armature():
    active = bpy.context.view_layer.objects.active
    if active and active.type == "ARMATURE":
        return active
    selected = [obj for obj in bpy.context.selected_objects if obj.type == "ARMATURE"]
    if selected:
        return selected[0]
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            return obj
    raise RuntimeError("No armature object found")


def normalized(name: str) -> str:
    return "".join(character for character in name.lower() if character.isalnum())


def bone_lookup(armature):
    result = {}
    for bone in armature.pose.bones:
        result[bone.name] = bone
        result[normalized(bone.name)] = bone
    return result


def find_bone(lookup, name):
    return lookup.get(name) or lookup.get(normalized(name))


def main():
    source = argument_path()
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("type") != "RENDERDOC_SKIN_MATRIX_ANIMATION_REFERENCE":
        raise ValueError("not a RenderDoc animation-reference JSON")

    armature = active_armature()
    armature.animation_data_create()
    old = bpy.data.actions.get(ACTION_NAME)
    if old:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(ACTION_NAME)
    action.use_fake_user = True
    armature.animation_data.action = action
    lookup = bone_lookup(armature)

    missing = set()
    keyed = set()
    for frame_offset, frame in enumerate(data["frames"]):
        frame_number = FRAME_START + frame_offset
        bpy.context.scene.frame_set(frame_number)
        for name, transform in frame["joints"].items():
            bone = find_bone(lookup, name)
            if bone is None:
                missing.add(name)
                continue
            bone.rotation_mode = "QUATERNION"
            global_matrix = transform.get("global_matrix_row_major")
            if global_matrix and len(global_matrix) == 16:
                bone.matrix = Matrix([global_matrix[row * 4 : row * 4 + 4] for row in range(4)])
            else:
                bone.location = Vector(transform["translation"])
                bone.rotation_quaternion = Quaternion(transform["rotation_wxyz"])
                bone.scale = Vector(transform["scale"])
            bone.keyframe_insert(data_path="location", frame=frame_number, group=bone.name)
            bone.keyframe_insert(data_path="rotation_quaternion", frame=frame_number, group=bone.name)
            bone.keyframe_insert(data_path="scale", frame=frame_number, group=bone.name)
            keyed.add(bone.name)

    bpy.context.scene.frame_start = FRAME_START
    bpy.context.scene.frame_end = FRAME_START + len(data["frames"]) - 1
    bpy.context.scene.render.fps = int(round(float(data.get("fps_assumption") or 30.0)))
    armature["renderdoc_reference_source"] = str(source)
    print(f"Created action {ACTION_NAME!r}; keyed {len(keyed)} bones; missing {sorted(missing)}")


if __name__ == "__main__":
    main()
