#!/usr/bin/env python3
"""Create real Blender Actions from PAKPY normal_clip bind/hierarchy JSON.

Run inside Blender, for example from the Scripting workspace, or:
  blender character.blend --python blender_import_normal_clip_actions.py -- --package /path/to/package

The importer calibrates game-space to the imported armature from matching rest
joint positions. Bone roll is handled by a per-bone rest correction, so no fixed
axis-swizzle or hand-authored roll table is required.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

DEFAULT_FPS = 30.0
REPORT_NAME = "blender_normal_clip_action_report.json"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def matrix4(rows3):
    return Matrix((tuple(rows3[0]), tuple(rows3[1]), tuple(rows3[2]), (0.0, 0.0, 0.0, 1.0)))


def norm_name(name):
    value = str(name).lower().replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
    for suffix in ("jntskin", "skin", "joint", "jnt"):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    return value


def package_candidates(start):
    path = Path(start).resolve()
    yield path if path.is_dir() else path.parent
    yield from (path if path.is_dir() else path.parent).parents


def find_package(explicit=""):
    if explicit:
        root = Path(explicit).resolve()
        if root.is_dir():
            return root
        raise RuntimeError("Package-Ordner existiert nicht: " + str(root))
    starts = [Path.cwd()]
    if bpy.data.filepath:
        starts.insert(0, Path(bpy.data.filepath))
    try:
        starts.insert(0, Path(__file__))
    except Exception:
        pass
    seen = set()
    for start in starts:
        for root in package_candidates(start):
            key = str(root).lower()
            if key in seen:
                continue
            seen.add(key)
            if (root / "debug" / "anim_normal_clip_bind").is_dir() or list(root.glob("models/*/debug/anim_normal_clip_bind")):
                return root
    raise RuntimeError("Kein Character-/Model-Package mit debug/anim_normal_clip_bind gefunden")


def bind_files(root):
    paths = list(root.glob("debug/anim_normal_clip_bind/*.normal_clip_bind.json"))
    paths += list(root.glob("models/*/debug/anim_normal_clip_bind/*.normal_clip_bind.json"))
    unique = {}
    for path in paths:
        name = path.name
        prefer_model = "/models/" in str(path).replace("\\", "/")
        if name not in unique or prefer_model:
            unique[name] = path
    return [unique[key] for key in sorted(unique)]


def find_armature(name=""):
    if name:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == "ARMATURE":
            return obj
        raise RuntimeError("Armature nicht gefunden: " + name)
    active = bpy.context.view_layer.objects.active
    if active and active.type == "ARMATURE":
        return active
    for obj in bpy.context.selected_objects:
        if obj.type == "ARMATURE":
            return obj
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            return obj
    raise RuntimeError("Keine Armature in der Szene gefunden")


def pose_lookup(armature):
    out = {}
    for bone in armature.pose.bones:
        out[bone.name] = bone
        out[norm_name(bone.name)] = bone
    return out


def match_bone(lookup, name):
    return lookup.get(name) or lookup.get(norm_name(name))


def estimate_similarity(source_points, target_points):
    """Umeyama similarity mapping source points to target points."""
    src = np.asarray(source_points, dtype=np.float64)
    dst = np.asarray(target_points, dtype=np.float64)
    if src.shape != dst.shape or src.ndim != 2 or src.shape[1] != 3 or len(src) < 3:
        raise RuntimeError("Mindestens drei passende Rest-Joints werden für die Basis-Kalibrierung benötigt")
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    xs = src - src_mean
    ys = dst - dst_mean
    covariance = xs.T @ ys
    u, singular, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0.0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    denominator = float(np.sum(xs * xs))
    if denominator <= 1e-20:
        raise RuntimeError("Degenerierte Rest-Joint-Punktmenge")
    scale = float(np.sum(singular) / denominator)
    translation = dst_mean - scale * (rotation @ src_mean)
    result = Matrix.Identity(4)
    for row in range(3):
        for column in range(3):
            result[row][column] = scale * float(rotation[row, column])
        result[row][3] = float(translation[row])
    residual = np.linalg.norm((scale * (rotation @ src.T)).T + translation - dst, axis=1)
    return result, scale, float(np.median(residual)), float(np.max(residual))


def action_name(path):
    stem = path.name.replace(".normal_clip_bind.json", "")
    if "__" in stem:
        stem = stem.rsplit("__", 1)[0]
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in stem)


def bone_depth(pose_bone):
    depth = 0
    current = pose_bone.parent
    while current is not None:
        depth += 1
        current = current.parent
    return depth


def create_action(armature, path, document, fps):
    names = list(document.get("skin_node_names") or [])
    skin_nodes = [int(value) for value in document.get("skin_node_indices") or []]
    base_rows = document.get("base_absolute_matrices_3x4") or []
    frames = document.get("frames") or []
    if len(names) != len(skin_nodes) or not base_rows or not frames:
        raise RuntimeError("Unvollständiges normal_clip_bind-Dokument: " + str(path))

    lookup = pose_lookup(armature)
    entries = []
    source_points = []
    target_points = []
    for palette_index, (name, node_index) in enumerate(zip(names, skin_nodes)):
        pose_bone = match_bone(lookup, name)
        if pose_bone is None or not (0 <= node_index < len(base_rows)):
            continue
        game_rest = matrix4(base_rows[node_index])
        blender_rest = pose_bone.bone.matrix_local.copy()
        entries.append((palette_index, node_index, name, pose_bone, game_rest, blender_rest))
        source_points.append(tuple(game_rest.translation))
        target_points.append(tuple(blender_rest.translation))
    if len(entries) < 3:
        raise RuntimeError("Zu wenige passende Armature-Bones für " + str(path))

    conversion, scale, residual_median, residual_max = estimate_similarity(source_points, target_points)
    corrections = {}
    for _palette, node_index, _name, pose_bone, game_rest, blender_rest in entries:
        corrections[pose_bone.name] = (conversion @ game_rest).inverted_safe() @ blender_rest

    name_out = action_name(path)
    old = bpy.data.actions.get(name_out)
    if old:
        try:
            bpy.data.actions.remove(old, do_unlink=True)
        except TypeError:
            bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name_out)
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action
    armature["pak_normal_clip_source"] = str(path)
    armature["pak_normal_clip_rest_calibrated"] = True
    armature["pak_normal_clip_basis_scale"] = scale

    scene = bpy.context.scene
    scene.render.fps = max(1, int(round(fps)))
    scene.render.fps_base = max(1e-8, float(round(fps)) / float(fps))
    ordered = sorted(entries, key=lambda item: bone_depth(item[3]))
    previous_quaternions = {}
    keyed = 0

    for frame_record in frames:
        source_frame = int(frame_record.get("frame", 0))
        blender_frame = source_frame + 1
        absolute = frame_record.get("absolute_node_matrices_3x4") or []
        scene.frame_set(blender_frame)
        for _palette, node_index, _name, pose_bone, _game_rest, _blender_rest in ordered:
            if not (0 <= node_index < len(absolute)):
                continue
            target = conversion @ matrix4(absolute[node_index]) @ corrections[pose_bone.name]
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix = target
            bpy.context.view_layer.update()
        for _palette, node_index, _name, pose_bone, _game_rest, _blender_rest in ordered:
            if not (0 <= node_index < len(absolute)):
                continue
            quaternion = pose_bone.rotation_quaternion.copy()
            previous = previous_quaternions.get(pose_bone.name)
            if previous is not None and previous.dot(quaternion) < 0.0:
                quaternion.negate()
                pose_bone.rotation_quaternion = quaternion
            previous_quaternions[pose_bone.name] = quaternion.copy()
            pose_bone.keyframe_insert(data_path="location", frame=blender_frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=blender_frame, group=pose_bone.name)
            pose_bone.keyframe_insert(data_path="scale", frame=blender_frame, group=pose_bone.name)
            keyed += 10

    seen_curves = set()
    curves = []
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        curves.extend(list(legacy))
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                curves.extend(list(getattr(channelbag, "fcurves", [])))
    for curve in curves:
        pointer = curve.as_pointer() if hasattr(curve, "as_pointer") else id(curve)
        if pointer in seen_curves:
            continue
        seen_curves.add(pointer)
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    action["pak_normal_clip_frame_count"] = len(frames)
    action["pak_normal_clip_fps"] = float(fps)
    scene.frame_start = 1
    scene.frame_end = max(scene.frame_end, len(frames))
    return {
        "action": name_out,
        "source": str(path),
        "frame_count": len(frames),
        "matched_bone_count": len(entries),
        "missing_bone_count": len(names) - len(entries),
        "inserted_key_channels": keyed,
        "basis_scale": scale,
        "rest_position_residual_median": residual_median,
        "rest_position_residual_max": residual_max,
    }


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1 :] if "--" in argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="")
    parser.add_argument("--armature", default="")
    parser.add_argument("--filter", default="")
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--save", default="")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    root = find_package(args.package)
    armature = find_armature(args.armature)
    paths = bind_files(root)
    if args.filter:
        paths = [path for path in paths if args.filter.lower() in path.name.lower()]
    if not paths:
        raise RuntimeError("Keine normal_clip_bind-Dateien gefunden. Character-Paket mit aktuellem PAKPY erneut exportieren.")
    reports = []
    errors = []
    first_action = None
    for path in paths:
        try:
            result = create_action(armature, path, load_json(path), args.fps)
            reports.append(result)
            if first_action is None:
                first_action = bpy.data.actions.get(result["action"])
        except Exception as exc:
            errors.append({"source": str(path), "error": str(exc)})
    if first_action is not None:
        armature.animation_data.action = first_action
        bpy.context.scene.frame_set(1)
    report = {
        "type": "PAKPY_NORMAL_CLIP_BLENDER_ACTION_IMPORT",
        "package": str(root),
        "armature": armature.name,
        "fps": args.fps,
        "created_action_count": len(reports),
        "errors": errors,
        "actions": reports,
        "note": "Actions reproduce isolated normal_clip output. Live game captures may include additional posegraph/procedural layers.",
    }
    (root / REPORT_NAME).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    if args.save:
        save_path = Path(args.save)
        if not save_path.is_absolute():
            save_path = root / save_path
        bpy.ops.wm.save_as_mainfile(filepath=str(save_path.resolve()))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()