"""Blender-side integration fixture for the CHAR Action batch importer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import bpy

import blender_character_animation_batch as batch


def _matrix(x, y, z):
    return (
        (1.0, 0.0, 0.0, x),
        (0.0, 1.0, 0.0, y),
        (0.0, 0.0, 1.0, z),
        (0.0, 0.0, 0.0, 1.0),
    )


def _rotated_matrix(x, y, z):
    return (
        (0.0, -1.0, 0.0, x),
        (1.0, 0.0, 0.0, y),
        (0.0, 0.0, 1.0, z),
        (0.0, 0.0, 0.0, 1.0),
    )


def _new_armature():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    data = bpy.data.armatures.new("FixtureSkeleton")
    armature = bpy.data.objects.new("FixtureArmature", data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    created = {}
    for name, head in (("root", (0.0, 0.0, 0.0)), ("right", (1.0, 0.0, 0.0)), ("front", (0.0, 1.0, 0.0))):
        bone = data.edit_bones.new(name)
        bone.head = head
        bone.tail = (head[0], head[1], head[2] + 1.0)
        created[name] = bone
    created["right"].parent = created["root"]
    created["front"].parent = created["root"]
    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _hierarchy():
    base = [_matrix(0.0, 0.0, 0.0), _matrix(1.0, 0.0, 0.0), _matrix(0.0, 1.0, 0.0)]
    moved = [
        _rotated_matrix(0.25, 0.0, 0.0),
        _rotated_matrix(0.25, 1.0, 0.0),
        _rotated_matrix(-0.75, 0.0, 0.0),
    ]
    return SimpleNamespace(
        skin_node_indices=[0, 1, 2],
        base_absolute_matrices=base,
        frames=[
            SimpleNamespace(frame=0, absolute_node_matrices=base),
            SimpleNamespace(frame=1, absolute_node_matrices=moved),
        ],
    )


def _skeleton():
    return {"nodes": [{"name": "root"}, {"name": "right"}, {"name": "front"}]}


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--temp", required=True)
    args = parser.parse_args(argv)
    temp = Path(args.temp).resolve()
    reference = temp / "reference.blend"
    target = temp / "target.blend"

    _new_armature()
    bpy.ops.wm.save_as_mainfile(filepath=str(target))

    armature = _new_armature()
    report = batch._create_action(
        armature,
        {"name": "fixture_idle", "uuid_hex": "1" * 32, "source_file": "source/anim/fixture.anim"},
        _hierarchy(),
        _skeleton(),
        30.0,
    )
    batch._assign_first_action(armature, [report["action"]])
    bpy.ops.wm.save_as_mainfile(filepath=str(reference))
    copied = batch._append_actions(reference, target, [report["action"]])
    if copied != 1:
        raise RuntimeError(f"Expected one copied Action, got {copied}")

    bpy.ops.wm.open_mainfile(filepath=str(target))
    action = bpy.data.actions.get("fixture_idle")
    if action is None:
        raise RuntimeError("Copied Action missing from target BLEND")
    curves = []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        curves.extend(legacy)
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                curves.extend(channelbag.fcurves)
    if len(curves) != 30:
        raise RuntimeError(f"Expected 30 FCurves, got {len(curves)}")
    if any(len(curve.keyframe_points) != 2 for curve in curves):
        raise RuntimeError("Bulk-created FCurve has wrong key count")
    if any(point.interpolation != "LINEAR" for curve in curves for point in curve.keyframe_points):
        raise RuntimeError("Bulk-created keys are not linear")
    root_x = next(
        (
            curve
            for curve in curves
            if curve.data_path == 'pose.bones["root"].location' and curve.array_index == 0
        ),
        None,
    )
    if root_x is None or abs(float(root_x.keyframe_points[-1].co[1]) - 0.25) > 1e-5:
        raise RuntimeError("Copied Action does not preserve the expected frame transform")
    right_x = next(
        (
            curve
            for curve in curves
            if curve.data_path == 'pose.bones["right"].location' and curve.array_index == 0
        ),
        None,
    )
    if right_x is None or abs(float(right_x.keyframe_points[-1].co[1])) > 1e-5:
        raise RuntimeError(
            "Child-bone local transform is corrupted by parent/child evaluation: "
            + str(float(right_x.keyframe_points[-1].co[1]) if right_x else "missing")
        )
    armature = batch._find_armature()
    if armature.animation_data is None or armature.animation_data.action is None:
        raise RuntimeError("Target armature has no active copied Action")


if __name__ == "__main__":
    main()
