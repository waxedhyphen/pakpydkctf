"""Import a fully decoded DKCTF action JSON into Blender.

This file deliberately does not decode raw .anim payloads. It consumes only
DKCTF_DECODED_ACTIONS_V1, whose matrices are already in Blender armature space.
Unknown bones or malformed matrices are hard errors; no prefix matching or Euler
guessing is performed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix


FORMAT = "DKCTF_DECODED_ACTIONS_V1"


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("format") != FORMAT:
        raise ValueError(f"expected format {FORMAT!r}")
    return value


def find_armature(name: str | None) -> bpy.types.Object:
    if name:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "ARMATURE":
            raise ValueError(f"armature {name!r} was not found")
        return obj

    active = bpy.context.view_layer.objects.active
    if active is not None and active.type == "ARMATURE":
        return active

    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise ValueError(
            f"expected exactly one armature or --armature, found {len(armatures)}"
        )
    return armatures[0]


def matrix_from_row_major(values: list[float]) -> Matrix:
    if len(values) != 16:
        raise ValueError(f"matrix must contain 16 values, got {len(values)}")
    return Matrix((
        values[0:4],
        values[4:8],
        values[8:12],
        values[12:16],
    ))


def rest_local_matrix(pose_bone: bpy.types.PoseBone) -> Matrix:
    bone = pose_bone.bone
    if bone.parent is None:
        return bone.matrix_local.copy()
    return bone.parent.matrix_local.inverted_safe() @ bone.matrix_local


def import_action(
    armature: bpy.types.Object,
    action_data: dict,
    *,
    source_path: Path,
) -> bpy.types.Action:
    name = str(action_data["name"])
    existing = bpy.data.actions.get(name)
    if existing is not None:
        bpy.data.actions.remove(existing)

    action = bpy.data.actions.new(name=name)
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action

    channels = action_data.get("channels")
    if not isinstance(channels, list):
        raise ValueError(f"action {name!r}: channels must be a list")

    for channel in channels:
        bone_name = str(channel["bone"])
        pose_bone = armature.pose.bones.get(bone_name)
        if pose_bone is None:
            raise ValueError(f"action {name!r}: exact bone {bone_name!r} was not found")

        rest_local = rest_local_matrix(pose_bone)
        frames = channel.get("frames")
        if not isinstance(frames, list):
            raise ValueError(f"action {name!r}, bone {bone_name!r}: frames must be a list")

        pose_bone.rotation_mode = "QUATERNION"
        for item in frames:
            frame = int(item["frame"])
            local_matrix = matrix_from_row_major(item["local_matrix_row_major"])
            # The JSON stores the animated local transform in Blender armature
            # coordinates. matrix_basis is the delta from Blender's rest local matrix.
            pose_bone.matrix_basis = rest_local.inverted_safe() @ local_matrix
            pose_bone.keyframe_insert("location", frame=frame, group=bone_name)
            pose_bone.keyframe_insert("rotation_quaternion", frame=frame, group=bone_name)
            pose_bone.keyframe_insert("scale", frame=frame, group=bone_name)

    action["dkctf_source"] = str(source_path)
    action["dkctf_decoded_format"] = FORMAT
    return action


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("decoded_json", type=Path)
    parser.add_argument("--armature", default="")
    parser.add_argument("--save", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    data = load_json(args.decoded_json)
    armature = find_armature(args.armature or None)

    fps = int(data.get("fps", 30))
    bpy.context.scene.render.fps = fps

    actions_data = data.get("actions")
    if not isinstance(actions_data, list) or not actions_data:
        raise ValueError("decoded JSON contains no actions")

    actions = [
        import_action(armature, action_data, source_path=args.decoded_json)
        for action_data in actions_data
    ]

    armature.animation_data.action = actions[0]
    all_frames = [
        int(frame["frame"])
        for action in actions_data
        for channel in action.get("channels", [])
        for frame in channel.get("frames", [])
    ]
    if all_frames:
        bpy.context.scene.frame_start = min(all_frames)
        bpy.context.scene.frame_end = max(all_frames)
        bpy.context.scene.frame_set(min(all_frames))

    if args.save:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    return 0


if __name__ == "__main__":
    script_args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    raise SystemExit(main(script_args))
