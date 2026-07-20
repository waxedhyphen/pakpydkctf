#!/usr/bin/env python3
"""Compare the legacy JSON importer with the direct batch importer in Blender."""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

import bpy


def curves(action):
    result = []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        result.extend(legacy)
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                result.extend(channelbag.fcurves)
    return result


def snapshot(action):
    return {
        (curve.data_path, curve.array_index): [
            (float(point.co[0]), float(point.co[1])) for point in curve.keyframe_points
        ]
        for curve in curves(action)
    }


def armature():
    return next(obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE")


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-blend", required=True)
    parser.add_argument("--new-blend", default="")
    parser.add_argument("--bind", required=True)
    parser.add_argument("--raw", default="")
    parser.add_argument("--skeleton", default="")
    parser.add_argument("--code-root", required=True)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(args.code_root).resolve()))
    source_path = Path(args.code_root).resolve() / "blender_normal_clip_action_script_patch.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    normal_clip_script = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "NORMAL_CLIP_ACTION_SCRIPT"
            for target in node.targets
        ):
            normal_clip_script = ast.literal_eval(node.value)
            break
    if normal_clip_script is None:
        raise RuntimeError("Legacy Action-Script konnte nicht gelesen werden")

    bpy.ops.wm.open_mainfile(filepath=str(Path(args.base_blend).resolve()))
    namespace = {"__name__": "pakpy_legacy_compare"}
    exec(normal_clip_script, namespace)
    bind_path = Path(args.bind).resolve()
    document = json.loads(bind_path.read_text(encoding="utf-8"))
    report = namespace["create_action"](armature(), bind_path, document, 30.0)
    legacy = snapshot(bpy.data.actions[report["action"]])

    if args.raw and args.skeleton:
        from anim_normal_clip_bind import compose_normal_clip_bind_hierarchy
        import blender_character_animation_batch as direct_batch

        skeleton = json.loads(Path(args.skeleton).read_text(encoding="utf-8"))
        hierarchy = compose_normal_clip_bind_hierarchy(
            Path(args.raw).read_bytes(),
            skeleton,
            apply_skeleton_remap=False,
            strict=False,
        )
        direct_batch._create_action(
            armature(),
            {"name": report["action"], "source_file": args.raw},
            hierarchy,
            skeleton,
            30.0,
        )
    else:
        bpy.ops.wm.open_mainfile(filepath=str(Path(args.new_blend).resolve()))
    direct_action = bpy.data.actions.get(report["action"])
    if direct_action is None:
        raise RuntimeError("Direct Action fehlt: " + report["action"])
    direct = snapshot(direct_action)
    keys = set(legacy) | set(direct)
    missing = []
    shape = []
    max_error = 0.0
    max_key = None
    for key in keys:
        left = legacy.get(key)
        right = direct.get(key)
        if left is None or right is None:
            missing.append(key)
            continue
        if len(left) != len(right):
            shape.append((key, len(left), len(right)))
            continue
        for index, (a, b) in enumerate(zip(left, right)):
            error = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
            if error > max_error:
                max_error = error
                max_key = (key, index, a, b)
    print(json.dumps({
        "action": report["action"],
        "legacy_curve_count": len(legacy),
        "direct_curve_count": len(direct),
        "missing_curve_count": len(missing),
        "shape_mismatch_count": len(shape),
        "max_error": max_error,
        "max_error_key": max_key,
    }, indent=2))
    if missing or shape or max_error > 1e-5:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
