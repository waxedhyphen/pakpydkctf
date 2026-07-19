#!/usr/bin/env python3
"""Local-pose evaluation for DKCTF ANIM ``normal_clip``.

This module ports the interpolation/output stage implemented by the game around
``0x1973BC``.  It consumes the sparse values from ``anim_normal_clip_values``
and evaluates complete local animation-delta TRS poses.

Verified behavior:

* missing rotation channels inherit the input/base pose (identity by default);
* missing translation channels inherit zero by default;
* missing scale channels inherit one by default;
* constant channels overwrite the corresponding component for every frame;
* animated rotation uses shortest-path normalized linear interpolation;
* animated translation and scale use component-wise linear interpolation;
* the sign/correction metadata stored on the right rotation key controls the
  interval ending at that key;
* optional SKEL sign/permutation maps are exact ports of ``0x12D57C`` and
  ``0x12D610``.  They are opt-in because the caller's remap flag is external to
  the serialized ANIM stream.

Bind-pose multiplication, hierarchy evaluation, root/model transforms and
Blender axis conversion deliberately belong to the next layer.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from anim_normal_clip_values import NormalClipValueResult, parse_normal_clip_values


class NormalClipPoseError(ValueError):
    pass


IDENTITY_ROTATION = (1.0, 0.0, 0.0, 0.0)
IDENTITY_SCALE = (1.0, 1.0, 1.0)
ZERO_TRANSLATION = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class LocalTRS:
    rotation_wxyz: tuple[float, float, float, float]
    scale_xyz: tuple[float, float, float]
    translation_xyz: tuple[float, float, float]


@dataclass
class LocalPoseFrame:
    frame: int
    nodes: list[LocalTRS]


@dataclass
class NormalClipLocalPose:
    type: str
    frame_count: int
    node_count: int
    frames: list[LocalPoseFrame]
    skeleton_remap_applied: bool
    notes: list[str]

    def to_dict(self, node_names: Sequence[str] | None = None) -> dict[str, Any]:
        out = asdict(self)
        if node_names is not None:
            out["node_names"] = [
                str(node_names[index]) if index < len(node_names) else f"<node_{index}>"
                for index in range(self.node_count)
            ]
        return out


def _normalize_quaternion(values: Sequence[float]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise NormalClipPoseError(f"quaternion must have four components, got {len(values)}")
    norm_sq = sum(float(value) * float(value) for value in values)
    if not math.isfinite(norm_sq) or norm_sq <= 0.0:
        raise NormalClipPoseError(f"invalid quaternion norm squared {norm_sq!r}")
    inv = 1.0 / math.sqrt(norm_sq)
    return tuple(float(value) * inv for value in values)  # type: ignore[return-value]


def normalized_lerp_wxyz(
    left: Sequence[float],
    right: Sequence[float],
    factor: float,
    *,
    negate_right: bool = False,
) -> tuple[float, float, float, float]:
    """Port the quaternion path in ``0x1973BC``.

    The binary multiplies both linear weights by the same correction factor
    ``1 + c*t*(1-t)`` and normalizes the result.  The common factor cancels from
    the quaternion direction, leaving shortest-path normalized lerp.  Bit zero
    in the stored interpolation float selects the sign of the right quaternion.
    """
    t = min(1.0, max(0.0, float(factor)))
    sign = -1.0 if negate_right else 1.0
    mixed = tuple(
        (1.0 - t) * float(left[index]) + t * sign * float(right[index])
        for index in range(4)
    )
    return _normalize_quaternion(mixed)


def linear_lerp_xyz(
    left: Sequence[float],
    right: Sequence[float],
    factor: float,
) -> tuple[float, float, float]:
    if len(left) != 3 or len(right) != 3:
        raise NormalClipPoseError("vector interpolation requires three components")
    t = min(1.0, max(0.0, float(factor)))
    return tuple(
        (1.0 - t) * float(left[index]) + t * float(right[index])
        for index in range(3)
    )  # type: ignore[return-value]


def _field(item: Any, name: str) -> Any:
    return item[name] if isinstance(item, dict) else getattr(item, name)


def _track_keys(track: Any) -> Sequence[Any]:
    return _field(track, "keys")


def _segment(keys: Sequence[Any], frame: float) -> tuple[Any, Any, float]:
    if not keys:
        raise NormalClipPoseError("cannot evaluate an empty key track")
    if frame <= float(_field(keys[0], "frame")):
        return keys[0], keys[0], 0.0
    if frame >= float(_field(keys[-1], "frame")):
        return keys[-1], keys[-1], 0.0
    positions = [int(_field(key, "frame")) for key in keys]
    right_index = bisect.bisect_right(positions, frame)
    left = keys[right_index - 1]
    right = keys[right_index]
    span = float(_field(right, "frame") - _field(left, "frame"))
    if span <= 0.0:
        raise NormalClipPoseError(
            f"non-increasing key frames {_field(left, 'frame')} and {_field(right, 'frame')}"
        )
    return left, right, (float(frame) - float(_field(left, "frame"))) / span


def evaluate_rotation_track(track: Any, frame: float) -> tuple[float, float, float, float]:
    left, right, factor = _segment(_track_keys(track), frame)
    if left is right:
        return _normalize_quaternion(_field(left, "quaternion_wxyz"))
    # Metadata is written while decoding the new/right key and therefore applies
    # to the interval from the previous key to this right key.
    return normalized_lerp_wxyz(
        _field(left, "quaternion_wxyz"),
        _field(right, "quaternion_wxyz"),
        factor,
        negate_right=bool(_field(right, "interpolation_sign_bit")),
    )


def evaluate_vector_track(track: Any, frame: float) -> tuple[float, float, float]:
    left, right, factor = _segment(_track_keys(track), frame)
    if left is right:
        return tuple(float(value) for value in _field(left, "value_xyz"))  # type: ignore[return-value]
    return linear_lerp_xyz(_field(left, "value_xyz"), _field(right, "value_xyz"), factor)


def _base_component(
    base_pose: Sequence[LocalTRS] | None,
    node_index: int,
    attribute: str,
    fallback: tuple[float, ...],
) -> tuple[float, ...]:
    if base_pose is None:
        return fallback
    if node_index >= len(base_pose):
        raise NormalClipPoseError(
            f"base pose has {len(base_pose)} nodes, need node {node_index}"
        )
    return tuple(getattr(base_pose[node_index], attribute))


def evaluate_local_pose_frame(
    values: NormalClipValueResult,
    node_count: int,
    frame: float,
    *,
    base_pose: Sequence[LocalTRS] | None = None,
) -> list[LocalTRS]:
    if node_count <= 0:
        raise NormalClipPoseError(f"invalid node count {node_count}")

    rotations = [
        _base_component(base_pose, index, "rotation_wxyz", IDENTITY_ROTATION)
        for index in range(node_count)
    ]
    translations = [
        _base_component(base_pose, index, "translation_xyz", ZERO_TRANSLATION)
        for index in range(node_count)
    ]
    scales = [
        _base_component(base_pose, index, "scale_xyz", IDENTITY_SCALE)
        for index in range(node_count)
    ]

    for item in values.constant_rotations:
        rotations[int(item["node_index"])] = _normalize_quaternion(
            item["quaternion_wxyz"]
        )
    for item in values.constant_translations:
        translations[int(item["node_index"])] = tuple(
            float(value) for value in item["value_xyz"]
        )

    for track in values.rotation_tracks:
        rotations[int(_field(track, "node_index"))] = evaluate_rotation_track(track, frame)
    for track in values.translation_tracks:
        translations[int(_field(track, "node_index"))] = evaluate_vector_track(track, frame)
    for track in values.scale_tracks:
        scales[int(_field(track, "node_index"))] = evaluate_vector_track(track, frame)

    return [
        LocalTRS(
            rotation_wxyz=_normalize_quaternion(rotations[index]),
            scale_xyz=tuple(float(value) for value in scales[index]),
            translation_xyz=tuple(float(value) for value in translations[index]),
        )
        for index in range(node_count)
    ]


def _decode_map_entry(value: int) -> tuple[int, int]:
    if not 0 <= int(value) <= 0xFFFF:
        raise NormalClipPoseError(f"invalid SKEL map entry {value!r}")
    return (int(value) >> 8) & 0xFF, int(value) & 0xFF


def remap_quaternion_wxyz(
    quaternion: Sequence[float],
    map_entry: int,
) -> tuple[float, float, float, float]:
    """Exact sign/permutation operation from ``0x12D57C``."""
    sign_bits, permutation = _decode_map_entry(map_entry)
    if sign_bits == 0xFF:
        return _normalize_quaternion(quaternion)
    output = [0.0, 0.0, 0.0, 0.0]
    seen: set[int] = set()
    for source_index in range(4):
        destination = (permutation >> (source_index * 2)) & 0x03
        seen.add(destination)
        sign = -1.0 if ((sign_bits >> (source_index * 2)) & 1) else 1.0
        output[destination] = sign * float(quaternion[source_index])
    if seen != {0, 1, 2, 3}:
        raise NormalClipPoseError(
            f"invalid quaternion permutation 0x{permutation:02X}"
        )
    return _normalize_quaternion(output)


def remap_translation_xyz(
    translation: Sequence[float],
    map_entry: int,
) -> tuple[float, float, float]:
    """Exact sign/permutation operation from ``0x12D610``."""
    if len(translation) != 3:
        raise NormalClipPoseError("translation must have three components")
    sign_bits, permutation = _decode_map_entry(map_entry)
    if sign_bits == 0xFF:
        return tuple(float(value) for value in translation)  # type: ignore[return-value]
    output = [0.0, 0.0, 0.0]
    seen: set[int] = set()
    for source_index in range(3):
        destination = (permutation >> (source_index * 2)) & 0x03
        if destination >= 3:
            raise NormalClipPoseError(
                f"invalid translation destination {destination} in 0x{permutation:02X}"
            )
        seen.add(destination)
        sign = -1.0 if ((sign_bits >> (source_index * 2)) & 1) else 1.0
        output[destination] = sign * float(translation[source_index])
    if seen != {0, 1, 2}:
        raise NormalClipPoseError(
            f"invalid translation permutation 0x{permutation:02X}"
        )
    return tuple(output)  # type: ignore[return-value]


def apply_skeleton_maps(
    nodes: Sequence[LocalTRS],
    rotation_map: Sequence[int],
    translation_map: Sequence[int],
) -> list[LocalTRS]:
    if len(rotation_map) < len(nodes) or len(translation_map) < len(nodes):
        raise NormalClipPoseError(
            "SKEL rotation/translation maps must cover every evaluated node"
        )
    return [
        LocalTRS(
            rotation_wxyz=remap_quaternion_wxyz(
                node.rotation_wxyz, rotation_map[index]
            ),
            scale_xyz=node.scale_xyz,
            translation_xyz=remap_translation_xyz(
                node.translation_xyz, translation_map[index]
            ),
        )
        for index, node in enumerate(nodes)
    ]


def split_skeleton_map_entries(
    entries: Sequence[int], node_count: int
) -> tuple[list[int], list[int]]:
    if len(entries) < node_count * 2:
        raise NormalClipPoseError(
            f"SKEL map has {len(entries)} entries, expected at least {node_count * 2}"
        )
    return list(entries[:node_count]), list(entries[node_count : node_count * 2])


def evaluate_normal_clip_local_pose(
    raw: bytes,
    node_count: int,
    *,
    base_pose: Sequence[LocalTRS] | None = None,
    skeleton_map_entries: Sequence[int] | None = None,
    apply_skeleton_remap: bool = False,
    strict: bool = True,
) -> NormalClipLocalPose:
    values = parse_normal_clip_values(raw, node_count, strict=strict)
    maps: tuple[list[int], list[int]] | None = None
    if apply_skeleton_remap:
        if skeleton_map_entries is None:
            raise NormalClipPoseError(
                "apply_skeleton_remap requires the two SKEL map tables"
            )
        maps = split_skeleton_map_entries(skeleton_map_entries, node_count)

    frames: list[LocalPoseFrame] = []
    for frame in range(values.frame_count):
        nodes = evaluate_local_pose_frame(
            values,
            node_count,
            float(frame),
            base_pose=base_pose,
        )
        if maps is not None:
            nodes = apply_skeleton_maps(nodes, maps[0], maps[1])
        frames.append(LocalPoseFrame(frame=frame, nodes=nodes))

    if strict:
        for pose_frame in frames:
            for node_index, node in enumerate(pose_frame.nodes):
                norm = math.sqrt(sum(value * value for value in node.rotation_wxyz))
                if abs(norm - 1.0) > 1e-5:
                    raise NormalClipPoseError(
                        f"frame {pose_frame.frame} node {node_index} quaternion norm {norm}"
                    )
                values_to_check: Iterable[float] = (
                    *node.rotation_wxyz,
                    *node.scale_xyz,
                    *node.translation_xyz,
                )
                if not all(math.isfinite(value) for value in values_to_check):
                    raise NormalClipPoseError(
                        f"frame {pose_frame.frame} node {node_index} has non-finite TRS"
                    )

    return NormalClipLocalPose(
        type="ANIM_NORMAL_CLIP_LOCAL_POSE",
        frame_count=values.frame_count,
        node_count=node_count,
        frames=frames,
        skeleton_remap_applied=bool(apply_skeleton_remap),
        notes=[
            "Quaternion interpolation is shortest-path normalized lerp from 0x1973BC.",
            "Translation and scale interpolation are component-wise linear.",
            "Missing channels inherit the supplied base pose; default base pose is identity TRS.",
            "SKEL sign/permutation maps are opt-in because their caller flag is not serialized in ANIM.",
            "Bind/hierarchy/root/Blender composition remains a separate stage.",
        ],
    )
