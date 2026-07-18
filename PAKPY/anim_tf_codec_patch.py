"""Integrate the verified Tropical Freeze decoder with package enrichment."""
from __future__ import annotations

import json
from pathlib import Path

import anim_tf_codec as codec
import anim_track_skel_map_patch as timeline_patch
import blender_named_timeline_patch as blender_patch


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _find_anim(root: Path, uuid_hex: str) -> Path | None:
    if not uuid_hex:
        return None
    for pattern in (
        f"source/anim/*{uuid_hex}*.anim",
        f"models/*/source/anim/*{uuid_hex}*.anim",
        f"models/*/debug/*{uuid_hex}*.anim",
    ):
        match = next(root.glob(pattern), None)
        if match and match.is_file():
            return match
    return None


def _clear_generated_timelines(root: Path) -> int:
    removed = 0
    paths = list(root.glob("debug/anim_named_timeline/*.named_timeline.json"))
    paths.extend(root.glob("models/*/debug/anim_named_timeline/*.named_timeline.json"))
    for path in paths:
        try:
            path.unlink()
            removed += 1
        except FileNotFoundError:
            pass
    return removed


def _install_named_frame_channels() -> None:
    def named_frame_timeline(group, start_frame_index):
        tracks = group.get("tracks") or []
        frame_count = max([track.get("timeline_frame_count", 0) for track in tracks] + [0])
        frames = []
        for frame_index in range(frame_count):
            values = []
            by_name = {}
            for track in tracks:
                target = track.get("target_guess") or {}
                name = target.get("target_name") or track.get("target_name_hint") or f'lane_{track.get("lane_index", 0)}'
                stream = track.get("timeline_values") or []
                value = stream[frame_index] if frame_index < len(stream) else None
                values.append({
                    "lane_index": track.get("lane_index", 0),
                    "target_kind": target.get("target_kind", "node"),
                    "target_name": name,
                    "target_node_index": target.get("target_node_index", track.get("target_node_index", -1)),
                    "channel": track.get("channel", "raw"),
                    "value_kind": track.get("value_kind", ""),
                    "value": value,
                })
                by_name[name] = value
            frames.append({
                "frame_index": frame_index,
                "absolute_frame_index": start_frame_index + frame_index,
                "values": values,
                "by_name": by_name,
            })
        return frames

    timeline_patch._named_frame_timeline = named_frame_timeline


def _install_blender_quaternion_support() -> None:
    """Teach the generated Blender script to key typed quaternion channels."""
    script = blender_patch.BLENDER_SCRIPT
    old_set = """def set_value(pose_bone,value):
    if value is None:
        return False
    if MODE=='location':
        set_location(pose_bone,value)
    elif MODE=='rotation_euler':
        set_rotation_euler(pose_bone,value)
    else:
        set_raw_props(pose_bone,value)
    return True"""
    new_set = """def set_value(pose_bone,value,channel=''):
    if value is None:
        return False
    if channel=='rotation_quaternion':
        pose_bone.rotation_mode='QUATERNION'
        pose_bone.rotation_quaternion=tuple(float(item) for item in value)
    elif channel=='location':
        set_location(pose_bone,value)
    elif channel=='scale':
        pose_bone.scale=tuple(float(item) for item in value)
    elif MODE=='location':
        set_location(pose_bone,value)
    elif MODE=='rotation_euler':
        set_rotation_euler(pose_bone,value)
    else:
        set_raw_props(pose_bone,value)
    return True"""
    old_insert = """def insert_value_key(pose_bone,frame):
    if MODE=='location':
        pose_bone.keyframe_insert(data_path='location',frame=frame)
        return 3
    if MODE=='rotation_euler':
        pose_bone.keyframe_insert(data_path='rotation_euler',frame=frame)
        return 3
    pose_bone.keyframe_insert(data_path='[\"pak_anim_raw_x\"]',frame=frame)
    pose_bone.keyframe_insert(data_path='[\"pak_anim_raw_y\"]',frame=frame)
    pose_bone.keyframe_insert(data_path='[\"pak_anim_raw_z\"]',frame=frame)
    return 3"""
    new_insert = """def insert_value_key(pose_bone,frame,channel=''):
    if channel=='rotation_quaternion':
        pose_bone.keyframe_insert(data_path='rotation_quaternion',frame=frame)
        return 4
    if channel=='location' or MODE=='location':
        pose_bone.keyframe_insert(data_path='location',frame=frame)
        return 3
    if channel=='scale':
        pose_bone.keyframe_insert(data_path='scale',frame=frame)
        return 3
    if MODE=='rotation_euler':
        pose_bone.keyframe_insert(data_path='rotation_euler',frame=frame)
        return 3
    pose_bone.keyframe_insert(data_path='[\"pak_anim_raw_x\"]',frame=frame)
    pose_bone.keyframe_insert(data_path='[\"pak_anim_raw_y\"]',frame=frame)
    pose_bone.keyframe_insert(data_path='[\"pak_anim_raw_z\"]',frame=frame)
    return 3"""
    script = script.replace(old_set, new_set).replace(old_insert, new_insert)
    script = script.replace(
        "if set_value(bone,value):\n                    action_report['inserted_key_channels']+=insert_value_key(bone,frame_index)",
        "channel=item.get('channel','')\n                if set_value(bone,value,channel):\n                    action_report['inserted_key_channels']+=insert_value_key(bone,frame_index,channel)",
    )
    blender_patch.BLENDER_SCRIPT = script


def install_into() -> None:
    if getattr(timeline_patch, "_tf_codec_installed", False):
        return
    timeline_patch._tf_codec_installed = True
    _install_named_frame_channels()
    _install_blender_quaternion_support()
    original = timeline_patch._enrich_package

    def enrich_package(package_dir):
        root = Path(package_dir)
        skeleton, _ = timeline_patch._find_skeleton(root)
        decoded = []
        removed_timelines = _clear_generated_timelines(root)
        if isinstance(skeleton, dict):
            probe_paths = list(root.glob("debug/anim_probe21/*.probe21.json"))
            probe_paths.extend(root.glob("models/*/debug/anim_probe21/*.probe21.json"))
            seen = set()
            for probe_path in probe_paths:
                key = str(probe_path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                probe = _read_json(probe_path)
                if not isinstance(probe, dict):
                    continue
                anim_path = _find_anim(root, str(probe.get("uuid_hex") or ""))
                if anim_path is None:
                    continue
                try:
                    tf_result = codec.decode_asset(anim_path.read_bytes(), skeleton)
                    legacy = probe.get("track_decode")
                    if legacy and legacy != tf_result:
                        probe["legacy_track_decode"] = legacy
                    probe["tf_decode"] = tf_result
                    probe["track_decode"] = tf_result
                    probe_path.write_text(json.dumps(probe, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
                    decoded.append({"probe": str(probe_path), "status": tf_result.get("status", "")})
                except Exception as exc:
                    legacy = probe.get("track_decode")
                    if legacy:
                        probe["legacy_track_decode"] = legacy
                    failure = {"version": 1, "status": "error", "error": str(exc), "groups": []}
                    probe["tf_decode"] = failure
                    probe["track_decode"] = failure
                    probe_path.write_text(json.dumps(probe, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
        result = original(package_dir)
        if isinstance(result, dict):
            result["tf_codec"] = decoded
            result["tf_codec_removed_stale_timeline_count"] = removed_timelines
            result["tf_codec_ok_count"] = sum(1 for item in decoded if str(item.get("status", "")).startswith("ok:"))
        return result

    timeline_patch._enrich_package = enrich_package
