"""Export verified normal_clip frame timing and record boundaries.

Installed after the setup-stage patch.  This layer resolves key times and
record offsets but deliberately does not claim that payload values are decoded.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import anim_raw_probe_patch as raw_patch
import anim_normal_clip_setup_patch as setup_patch
import model_animation_refs_patch as anim_patch
from anim_normal_clip_frames import parse_normal_clip_frames

NORMAL_CLIP_CLASS = 0x81
TRACK_DECODE_VERSION = 5


def _pending_value_decode(probe: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": TRACK_DECODE_VERSION,
        "status": "pending:normal_clip_value_decode",
        "frame_count_guess": int(probe.get("frame_count_guess") or 0),
        "group_count": 0,
        "groups": [],
        "primary_group_index": None,
        "primary_timeline_frame_count": 0,
        "note": (
            "LoadIdxData, setup data, frame traversal, key timing and record boundaries "
            "are decoded. Rotation/vector payload values still need exact decoding."
        ),
    }


def _enrich_probe_set(
    result: dict[str, Any],
    parsed: dict[str, Any],
    package_dir: str | Path,
    require_store: Any,
) -> dict[str, Any]:
    root = Path(package_dir)
    node_names, skeleton_file = setup_patch._find_skeleton(root)
    integration = {
        "version": 1,
        "status": "no_skeleton" if not node_names else "ok",
        "skeleton_file": skeleton_file,
        "node_count": len(node_names),
        "normal_clip_count": 0,
        "parsed_count": 0,
        "errors": [],
        "documentation": "ANIM_UPDATE.md",
    }

    if node_names:
        for item in result.get("animations") or []:
            if not isinstance(item, dict) or not item.get("resolved"):
                continue
            uuid_hex = str(item.get("uuid_hex") or "")
            probe_rel = str(item.get("probe21_file") or "")
            if not uuid_hex or not probe_rel:
                continue
            asset, _entry, _source, _source_path = anim_patch._resolve_anim_asset(
                parsed, uuid_hex, require_store
            )
            if asset is None or setup_patch._control_class(asset) != NORMAL_CLIP_CLASS:
                continue

            integration["normal_clip_count"] += 1
            probe_path = root / probe_rel
            probe = setup_patch._read_json(probe_path)
            if probe is None:
                integration["errors"].append(
                    {"uuid_hex": uuid_hex, "error": f"probe JSON unreadable: {probe_rel}"}
                )
                continue

            try:
                frames = parse_normal_clip_frames(asset, len(node_names), strict=True)
                probe["normal_clip_frames"] = frames.to_dict(node_names)
                probe["normal_clip_frames_status"] = "ok"
                probe["normal_clip_frames_skeleton_file"] = skeleton_file
                probe["track_decode"] = _pending_value_decode(probe)
                item["normal_clip_frames_status"] = "ok"
                item["normal_clip_frame_block_count"] = len(frames.blocks)
                item["normal_clip_stream_end_file_offset"] = frames.stream_end_file_offset
                integration["parsed_count"] += 1
            except (ValueError, IndexError, OverflowError) as exc:
                message = str(exc)
                probe["normal_clip_frames_status"] = "error"
                probe["normal_clip_frames_error"] = message
                item["normal_clip_frames_status"] = "error"
                item["normal_clip_frames_error"] = message
                integration["errors"].append({"uuid_hex": uuid_hex, "error": message})
            setup_patch._write_json(probe_path, probe)

    if integration["errors"]:
        integration["status"] = "partial" if integration["parsed_count"] else "error"

    summary = result.get("summary")
    if not isinstance(summary, dict):
        summary = {}
        result["summary"] = summary
    summary["normal_clip_frames"] = integration
    result["normal_clip_frames"] = integration

    summary_rel = str(result.get("summary_file") or "")
    if summary_rel:
        setup_patch._write_json(root / summary_rel, summary)
    return result


def install(App) -> None:
    previous_track_decode = raw_patch._build_track_decode

    def build_track_decode(probe: dict[str, Any], body: bytes | None = None):
        if probe.get("raw_family") == "normal_clip":
            return _pending_value_decode(probe)
        return previous_track_decode(probe, body)

    raw_patch._build_track_decode = build_track_decode

    original_write_probe_set = anim_patch._write_animation_probe_set

    def write_animation_probe_set(
        parsed,
        entry,
        package_dir,
        refs,
        require_store=None,
        root_name="char",
    ):
        result = original_write_probe_set(
            parsed,
            entry,
            package_dir,
            refs,
            require_store=require_store,
            root_name=root_name,
        )
        try:
            return _enrich_probe_set(result, parsed, package_dir, require_store)
        except Exception as exc:
            result["normal_clip_frames_error"] = str(exc)
            return result

    anim_patch._write_animation_probe_set = write_animation_probe_set
