#!/usr/bin/env python3
"""Build CHAR Actions once per skeleton and copy them into matching BLENDs.

This file is executed by Blender, not by the PAKPY host interpreter.  It reads
raw ANIM assets and the small skeleton summaries directly; no per-frame JSON
transport is created.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix


def _load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path, value):
    Path(path).write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )


def _matrix4(rows):
    values = list(rows)
    if len(values) >= 4:
        return Matrix(tuple(tuple(row) for row in values[:4]))
    return Matrix((tuple(values[0]), tuple(values[1]), tuple(values[2]), (0.0, 0.0, 0.0, 1.0)))


def _norm_name(name):
    value = str(name).lower().replace(" ", "").replace("_", "").replace("-", "").replace(".", "")
    for suffix in ("jntskin", "skin", "joint", "jnt"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value


def _pose_lookup(armature):
    result = {}
    for bone in armature.pose.bones:
        result[bone.name] = bone
        result[_norm_name(bone.name)] = bone
    return result


def _find_armature():
    active = bpy.context.view_layer.objects.active
    if active is not None and active.type == "ARMATURE":
        return active
    for obj in bpy.context.scene.objects:
        if obj.type == "ARMATURE":
            return obj
    raise RuntimeError("Keine Armature im Modell-BLEND gefunden")


def _bone_depth(pose_bone):
    depth = 0
    current = pose_bone.parent
    while current is not None:
        depth += 1
        current = current.parent
    return depth


def _estimate_similarity(source_points, target_points):
    src = np.asarray(source_points, dtype=np.float64)
    dst = np.asarray(target_points, dtype=np.float64)
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    xs = src - src_mean
    yd = dst - dst_mean
    covariance = xs.T @ yd
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


def _curve_collection(action, armature):
    """Return an FCurve collection for legacy and Blender 4.4+ Actions."""
    legacy = getattr(action, "fcurves", None)
    if legacy is not None:
        return legacy
    slot = action.slots.new("OBJECT", armature.name)
    layer = action.layers.new("PAKPY Actions")
    strip = layer.strips.new(type="KEYFRAME")
    return strip.channelbag(slot, ensure=True).fcurves


def _new_curve(curves, data_path, index, group):
    try:
        return curves.new(data_path, index=index, action_group=group)
    except TypeError:
        return curves.new(data_path, index=index)


def _write_curve(curves, data_path, component, group, frames, values):
    curve = _new_curve(curves, data_path, component, group)
    count = len(frames)
    curve.keyframe_points.add(count)
    coordinates = [0.0] * (count * 2)
    coordinates[0::2] = frames
    coordinates[1::2] = values
    curve.keyframe_points.foreach_set("co", coordinates)
    # Enum value 1 is LINEAR in Blender's Beztriple interpolation enum.
    curve.keyframe_points.foreach_set("interpolation", [1] * count)
    curve.update()


def _safe_action_name(name):
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in str(name))


def _remove_action(name):
    old = bpy.data.actions.get(name)
    if old is not None:
        try:
            bpy.data.actions.remove(old, do_unlink=True)
        except TypeError:
            bpy.data.actions.remove(old)


def _create_action(armature, animation, hierarchy, skeleton, fps):
    node_names = [str(item.get("name", "")) for item in skeleton.get("nodes") or []]
    skin_nodes = list(hierarchy.skin_node_indices)
    names = [node_names[index] if 0 <= index < len(node_names) else f"node_{index:03d}" for index in skin_nodes]
    base_rows = hierarchy.base_absolute_matrices
    frames = hierarchy.frames
    lookup = _pose_lookup(armature)
    entries = []
    source_points = []
    target_points = []
    for palette_index, (name, node_index) in enumerate(zip(names, skin_nodes)):
        pose_bone = lookup.get(name) or lookup.get(_norm_name(name))
        if pose_bone is None or not (0 <= node_index < len(base_rows)):
            continue
        game_rest = _matrix4(base_rows[node_index])
        blender_rest = pose_bone.bone.matrix_local.copy()
        entries.append((palette_index, node_index, name, pose_bone, game_rest, blender_rest))
        source_points.append(tuple(game_rest.translation))
        target_points.append(tuple(blender_rest.translation))
    if len(entries) < 3:
        raise RuntimeError("Zu wenige passende Armature-Bones")

    conversion, scale, residual_median, residual_max = _estimate_similarity(source_points, target_points)
    corrections = {
        pose_bone.name: (conversion @ game_rest).inverted_safe() @ blender_rest
        for _palette, _node, _name, pose_bone, game_rest, blender_rest in entries
    }
    ordered = sorted(entries, key=lambda item: _bone_depth(item[3]))
    frame_numbers = []
    samples = {
        pose_bone.name: {"bone": pose_bone, "location": [[], [], []], "rotation": [[], [], [], []], "scale": [[], [], []]}
        for _palette, _node, _name, pose_bone, _game, _blend in ordered
    }
    previous_quaternions = {}

    for frame_record in frames:
        blender_frame = int(frame_record.frame) + 1
        frame_numbers.append(float(blender_frame))
        absolute = frame_record.absolute_node_matrices
        for _palette, node_index, _name, pose_bone, _game_rest, _blender_rest in ordered:
            if 0 <= node_index < len(absolute):
                pose_bone.rotation_mode = "QUATERNION"
                pose_bone.matrix = conversion @ _matrix4(absolute[node_index]) @ corrections[pose_bone.name]
                # This update is required after every parent-first assignment.
                # Blender decomposes/shear-corrects the parent's pose matrix;
                # descendants must see that evaluated result.  Deferring the
                # update corrupts local child-bone F-Curves.
                bpy.context.view_layer.update()
        for _palette, node_index, _name, pose_bone, _game_rest, _blender_rest in ordered:
            if not (0 <= node_index < len(absolute)):
                continue
            quaternion = pose_bone.rotation_quaternion.copy()
            previous = previous_quaternions.get(pose_bone.name)
            if previous is not None and previous.dot(quaternion) < 0.0:
                quaternion.negate()
            previous_quaternions[pose_bone.name] = quaternion.copy()
            item = samples[pose_bone.name]
            for index in range(3):
                item["location"][index].append(float(pose_bone.location[index]))
                item["scale"][index].append(float(pose_bone.scale[index]))
            for index in range(4):
                item["rotation"][index].append(float(quaternion[index]))

    name = _safe_action_name(animation.get("name") or animation.get("uuid_hex") or "animation")
    _remove_action(name)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    curves = _curve_collection(action, armature)
    for bone_name, item in samples.items():
        pose_bone = item["bone"]
        for index in range(3):
            _write_curve(curves, pose_bone.path_from_id("location"), index, bone_name, frame_numbers, item["location"][index])
        for index in range(4):
            _write_curve(curves, pose_bone.path_from_id("rotation_quaternion"), index, bone_name, frame_numbers, item["rotation"][index])
        for index in range(3):
            _write_curve(curves, pose_bone.path_from_id("scale"), index, bone_name, frame_numbers, item["scale"][index])
    action["pak_normal_clip_frame_count"] = len(frames)
    action["pak_normal_clip_fps"] = float(fps)
    action["pak_normal_clip_source"] = str(animation.get("source_file") or "")
    return {
        "action": name,
        "uuid_hex": animation.get("uuid_hex", ""),
        "frame_count": len(frames),
        "matched_bone_count": len(entries),
        "missing_bone_count": len(names) - len(entries),
        "inserted_key_channels": len(frame_numbers) * len(entries) * 10,
        "basis_scale": scale,
        "rest_position_residual_median": residual_median,
        "rest_position_residual_max": residual_max,
    }


def _assign_first_action(armature, names):
    armature.animation_data_create()
    for name in names:
        action = bpy.data.actions.get(name)
        if action is not None:
            armature.animation_data.action = action
            return


def _append_actions(reference_blend, target_blend, action_names):
    bpy.ops.wm.open_mainfile(filepath=str(target_blend))
    for name in action_names:
        _remove_action(name)
    with bpy.data.libraries.load(str(reference_blend), link=False) as (source, target):
        available = set(source.actions)
        target.actions = [name for name in action_names if name in available]
    loaded = [action for action in target.actions if action is not None]
    for action in loaded:
        action.use_fake_user = True
    armature = _find_armature()
    _assign_first_action(armature, [action.name for action in loaded])
    bpy.ops.wm.save_as_mainfile(filepath=str(target_blend), compress=True)
    return len(loaded)


def _process_group(root, group, animations, fps, compose):
    models = list(group.get("models") or [])
    if not models:
        raise RuntimeError("Skeleton-Gruppe enthält keine Modelle")
    skeleton_path = root / group["skeleton_file"]
    skeleton = _load_json(skeleton_path)
    reference_blend = root / models[0]["blend_path"]
    bpy.ops.wm.open_mainfile(filepath=str(reference_blend))
    armature = _find_armature()
    armature.animation_data_create()
    armature.animation_data.action = None
    reports = []
    errors = []
    for animation in animations:
        try:
            raw = (root / animation["source_file"]).read_bytes()
            hierarchy = compose(raw, skeleton, apply_skeleton_remap=False, strict=False)
            reports.append(_create_action(armature, animation, hierarchy, skeleton, fps))
        except Exception as exc:
            errors.append({
                "name": animation.get("name", ""),
                "uuid_hex": animation.get("uuid_hex", ""),
                "error": str(exc),
            })
    action_names = [item["action"] for item in reports]
    _assign_first_action(armature, action_names)
    bpy.context.scene.render.fps = max(1, int(round(fps)))
    bpy.context.scene.render.fps_base = max(1e-8, float(round(fps)) / float(fps))
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = max([item["frame_count"] for item in reports] or [1])
    bpy.ops.wm.save_as_mainfile(filepath=str(reference_blend), compress=True)
    model_results = [{
        "model_package_dir": models[0]["model_package_dir"],
        "blend_path": models[0]["blend_path"],
        "action_count": len(action_names),
        "status": "ok" if action_names and not errors else "partial" if action_names else "error",
    }]
    for model in models[1:]:
        target_blend = root / model["blend_path"]
        try:
            copied = _append_actions(reference_blend, target_blend, action_names)
            model_results.append({
                "model_package_dir": model["model_package_dir"],
                "blend_path": model["blend_path"],
                "action_count": copied,
                "status": "ok" if copied == len(action_names) else "partial",
            })
        except Exception as exc:
            model_results.append({
                "model_package_dir": model["model_package_dir"],
                "blend_path": model["blend_path"],
                "action_count": 0,
                "status": "error",
                "error": str(exc),
            })
    return {
        "skeleton_signature": group.get("skeleton_signature", ""),
        "skeleton_file": group["skeleton_file"],
        "decoded_animation_count": len(reports),
        "animation_error_count": len(errors),
        "actions": reports,
        "errors": errors,
        "models": model_results,
    }


def main():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    manifest_path = Path(args.manifest).resolve()
    manifest = _load_json(manifest_path)
    root = Path(manifest["package_dir"]).resolve()
    code_root = str(Path(manifest["code_root"]).resolve())
    if code_root not in sys.path:
        sys.path.insert(0, code_root)
    from anim_normal_clip_bind import compose_normal_clip_bind_hierarchy

    report = {
        "type": "PAKPY_CHARACTER_ANIMATION_BATCH",
        "status": "error",
        "animation_count": len(manifest.get("animations") or []),
        "skeleton_group_count": len(manifest.get("groups") or []),
        "groups": [],
        "fatal_error": "",
    }
    try:
        for group in manifest.get("groups") or []:
            report["groups"].append(
                _process_group(
                    root,
                    group,
                    list(manifest.get("animations") or []),
                    float(manifest.get("fps") or 30.0),
                    compose_normal_clip_bind_hierarchy,
                )
            )
        model_statuses = [model.get("status") for group in report["groups"] for model in group.get("models") or []]
        error_count = sum(int(group.get("animation_error_count") or 0) for group in report["groups"])
        if model_statuses and all(status == "ok" for status in model_statuses) and error_count == 0:
            report["status"] = "ok"
        elif any(status in ("ok", "partial") for status in model_statuses):
            report["status"] = "partial"
    except Exception as exc:
        report["fatal_error"] = str(exc)
        report["traceback"] = traceback.format_exc()
    _write_json(root / manifest["report_file"], report)
    if report["status"] == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
