#!/usr/bin/env python3
"""Exact SKEL bind/hierarchy composition for DKCTF ANIM ``normal_clip``.

This layer ports the runtime path around:

* ``CSkelLayout::BuildBaseAbsFromRel`` @ ``0x12C930``
* ``CCoords::x_y_ss`` @ ``0x11A490``
* ``CSkelPose::BuildRelative`` @ ``0x12E830``
* ``CSkelPose::Transform`` @ ``0x12E358``
* ``CAnimMath::BuildAbsoluteScalePropagation`` @ ``0x18AA40``
* ``CAnimMath::BuildAbsoluteNoScalePropagation`` @ ``0x18AB48``
* ``CSkelPose::GetRenderTransforms`` @ ``0x12E9A0``

It consumes decoded local animation-delta poses and an exported SKEL summary. The
result contains current absolute node matrices and render/skinning matrices in the
SKEL skin-node order. External model/world transforms and Blender basis conversion
are intentionally outside this module.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from anim_normal_clip_pose import (
    IDENTITY_ROTATION,
    IDENTITY_SCALE,
    ZERO_TRANSLATION,
    LocalTRS,
    evaluate_normal_clip_local_pose,
)

Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]


class NormalClipBindError(ValueError):
    pass


@dataclass(frozen=True)
class LayoutStartInfo:
    node_count: int
    relative_start: int
    hierarchy_start: int
    active_anchor: int


@dataclass
class HierarchyFrame:
    frame: int
    absolute_node_matrices: list[Matrix4]
    render_matrices: list[Matrix4]


@dataclass
class NormalClipBindResult:
    type: str
    frame_count: int
    node_count: int
    skin_bone_count: int
    layout: LayoutStartInfo
    skin_node_indices: list[int]
    base_absolute_matrices: list[Matrix4]
    base_absolute_inverse_matrices: list[Matrix4]
    frames: list[HierarchyFrame]
    skeleton_remap_applied: bool
    notes: list[str]

    def to_dict(self, node_names: Sequence[str] | None = None) -> dict[str, Any]:
        out = asdict(self)
        if node_names is not None:
            out["node_names"] = [
                str(node_names[index]) if index < len(node_names) else f"<node_{index}>"
                for index in range(self.node_count)
            ]
            out["skin_node_names"] = [
                str(node_names[index]) if index < len(node_names) else f"<node_{index}>"
                for index in self.skin_node_indices
            ]
        return out


def _zero_transform_matrix() -> Matrix4:
    return (
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def _normalize_quaternion(values: Sequence[float]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise NormalClipBindError("quaternion must contain four components")
    norm_sq = sum(float(value) * float(value) for value in values)
    if not math.isfinite(norm_sq) or norm_sq <= 0.0:
        raise NormalClipBindError(f"invalid quaternion norm squared {norm_sq!r}")
    inv = 1.0 / math.sqrt(norm_sq)
    return tuple(float(value) * inv for value in values)  # type: ignore[return-value]


def quaternion_multiply_wxyz(
    left: Sequence[float], right: Sequence[float]
) -> tuple[float, float, float, float]:
    """Hamilton product used by ``CCoords::x_y_ss``: ``left * right``."""
    lw, lx, ly, lz = (float(value) for value in left)
    rw, rx, ry, rz = (float(value) for value in right)
    return _normalize_quaternion(
        (
            lw * rw - lx * rx - ly * ry - lz * rz,
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
        )
    )


def compose_animation_with_bind(animation: LocalTRS, bind: LocalTRS) -> LocalTRS:
    """Port ``CCoords::x_y_ss(out, animation, bind)``."""
    return LocalTRS(
        rotation_wxyz=quaternion_multiply_wxyz(
            animation.rotation_wxyz, bind.rotation_wxyz
        ),
        scale_xyz=tuple(
            float(animation.scale_xyz[index]) * float(bind.scale_xyz[index])
            for index in range(3)
        ),
        translation_xyz=tuple(
            float(animation.translation_xyz[index])
            + float(bind.translation_xyz[index])
            for index in range(3)
        ),
    )


def coords_to_matrix(coords: LocalTRS, *, include_scale: bool = True) -> Matrix4:
    """Build the row-major 3x4 transform used by ``CCoords::BuildTransform``."""
    w, x, y, z = _normalize_quaternion(coords.rotation_wxyz)
    if include_scale:
        sx, sy, sz = (float(value) for value in coords.scale_xyz)
    else:
        sx = sy = sz = 1.0
    tx, ty, tz = (float(value) for value in coords.translation_xyz)
    return (
        (
            (1.0 - 2.0 * (y * y + z * z)) * sx,
            2.0 * (x * y - z * w) * sy,
            2.0 * (x * z + y * w) * sz,
            tx,
        ),
        (
            2.0 * (x * y + z * w) * sx,
            (1.0 - 2.0 * (x * x + z * z)) * sy,
            2.0 * (y * z - x * w) * sz,
            ty,
        ),
        (
            2.0 * (x * z - y * w) * sx,
            2.0 * (y * z + x * w) * sy,
            (1.0 - 2.0 * (x * x + y * y)) * sz,
            tz,
        ),
        (0.0, 0.0, 0.0, 1.0),
    )


def matrix_multiply(left: Matrix4, right: Matrix4) -> Matrix4:
    return tuple(
        tuple(
            sum(float(left[row][k]) * float(right[k][column]) for k in range(4))
            for column in range(4)
        )
        for row in range(4)
    )  # type: ignore[return-value]


def affine_inverse(matrix: Matrix4) -> Matrix4:
    a, b, c, tx = matrix[0]
    d, e, f, ty = matrix[1]
    g, h, i, tz = matrix[2]
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if not math.isfinite(determinant) or abs(determinant) <= 1e-12:
        raise NormalClipBindError(f"singular affine transform determinant {determinant!r}")
    inv_det = 1.0 / determinant
    r00 = (e * i - f * h) * inv_det
    r01 = (c * h - b * i) * inv_det
    r02 = (b * f - c * e) * inv_det
    r10 = (f * g - d * i) * inv_det
    r11 = (a * i - c * g) * inv_det
    r12 = (c * d - a * f) * inv_det
    r20 = (d * h - e * g) * inv_det
    r21 = (b * g - a * h) * inv_det
    r22 = (a * e - b * d) * inv_det
    return (
        (r00, r01, r02, -(r00 * tx + r01 * ty + r02 * tz)),
        (r10, r11, r12, -(r10 * tx + r11 * ty + r12 * tz)),
        (r20, r21, r22, -(r20 * tx + r21 * ty + r22 * tz)),
        (0.0, 0.0, 0.0, 1.0),
    )


def derive_layout_start_info(
    parent_indices: Sequence[int], node_flags: Sequence[int]
) -> LayoutStartInfo:
    node_count = len(parent_indices)
    if node_count == 0 or len(node_flags) < node_count:
        raise NormalClipBindError("parent and flag tables must cover every node")
    active_anchor = next(
        (index for index, flags in enumerate(node_flags[:node_count]) if (0x28 & ~int(flags)) == 0),
        node_count,
    )
    relative_start = next(
        (index for index in range(1, node_count) if not (int(node_flags[index]) & 0x10)),
        node_count,
    )
    hierarchy_start = relative_start
    while hierarchy_start < node_count and int(parent_indices[hierarchy_start]) == 0xFF:
        hierarchy_start += 1
    if active_anchor >= node_count:
        raise NormalClipBindError("SKEL has no active anchor containing flag mask 0x28")
    return LayoutStartInfo(node_count, relative_start, hierarchy_start, active_anchor)


def _node_to_trs(node: dict[str, Any]) -> LocalTRS:
    return LocalTRS(
        rotation_wxyz=tuple(float(value) for value in node.get("rotation", IDENTITY_ROTATION)),
        scale_xyz=tuple(float(value) for value in node.get("scale", IDENTITY_SCALE)),
        translation_xyz=tuple(float(value) for value in node.get("translation", ZERO_TRANSLATION)),
    )


def build_base_absolute(
    bind_coords: Sequence[LocalTRS],
    parent_indices: Sequence[int],
    layout: LayoutStartInfo,
) -> list[Matrix4]:
    output: list[Matrix4] = [_zero_transform_matrix() for _ in bind_coords]
    for index in range(layout.hierarchy_start):
        output[index] = coords_to_matrix(bind_coords[index], include_scale=True)
    for index in range(layout.hierarchy_start, layout.node_count):
        parent = int(parent_indices[index])
        if not 0 <= parent < index:
            raise NormalClipBindError(f"node {index} has invalid hierarchical parent {parent}")
        output[index] = matrix_multiply(
            output[parent], coords_to_matrix(bind_coords[index], include_scale=False)
        )
    return output


def build_absolute_scale_propagation(parent: Matrix4, child: LocalTRS) -> Matrix4:
    return matrix_multiply(parent, coords_to_matrix(child, include_scale=True))


def build_absolute_no_scale_propagation(
    parent_absolute: Matrix4,
    parent_relative: LocalTRS,
    child_relative: LocalTRS,
) -> Matrix4:
    reciprocal = []
    for component in parent_relative.scale_xyz:
        value = float(component)
        if not math.isfinite(value) or abs(value) <= 1e-12:
            raise NormalClipBindError(f"cannot suppress zero/non-finite parent scale {value!r}")
        reciprocal.append(1.0 / value)
    cancel_parent_scale: Matrix4 = (
        (reciprocal[0], 0.0, 0.0, 0.0),
        (0.0, reciprocal[1], 0.0, 0.0),
        (0.0, 0.0, reciprocal[2], 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    return matrix_multiply(
        matrix_multiply(parent_absolute, cancel_parent_scale),
        coords_to_matrix(child_relative, include_scale=True),
    )


def build_relative_coords(
    animation_nodes: Sequence[LocalTRS],
    bind_coords: Sequence[LocalTRS],
    layout: LayoutStartInfo,
) -> list[LocalTRS]:
    if len(animation_nodes) < layout.node_count or len(bind_coords) < layout.node_count:
        raise NormalClipBindError("animation and bind poses must cover every node")
    output = [
        LocalTRS(IDENTITY_ROTATION, IDENTITY_SCALE, ZERO_TRANSLATION)
        for _ in range(layout.node_count)
    ]
    for index in range(layout.relative_start, layout.node_count):
        output[index] = compose_animation_with_bind(animation_nodes[index], bind_coords[index])
    return output


def build_current_absolute(
    relative_coords: Sequence[LocalTRS],
    parent_indices: Sequence[int],
    node_flags: Sequence[int],
    layout: LayoutStartInfo,
) -> list[Matrix4]:
    output = [_zero_transform_matrix() for _ in range(layout.node_count)]
    output[0] = coords_to_matrix(relative_coords[layout.active_anchor])
    for index in range(layout.relative_start, layout.hierarchy_start):
        output[index] = coords_to_matrix(relative_coords[index])
    for index in range(layout.hierarchy_start, layout.node_count):
        parent = int(parent_indices[index])
        if not 0 <= parent < index:
            raise NormalClipBindError(f"node {index} has invalid runtime parent {parent}")
        if int(node_flags[index]) & 1:
            output[index] = build_absolute_no_scale_propagation(
                output[parent], relative_coords[parent], relative_coords[index]
            )
        else:
            output[index] = build_absolute_scale_propagation(output[parent], relative_coords[index])
    return output


def build_render_matrices(
    current_absolute: Sequence[Matrix4],
    base_absolute_inverse: Sequence[Matrix4],
    skin_node_indices: Sequence[int],
) -> list[Matrix4]:
    output: list[Matrix4] = []
    for node_index in skin_node_indices:
        index = int(node_index)
        if not 0 <= index < len(current_absolute):
            raise NormalClipBindError(f"invalid skin node index {index}")
        output.append(matrix_multiply(current_absolute[index], base_absolute_inverse[index]))
    return output


def compose_bind_hierarchy_from_pose(
    pose: Any,
    skeleton: dict[str, Any],
    *,
    strict: bool = True,
) -> NormalClipBindResult:
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise NormalClipBindError("SKEL summary has no nodes")
    node_count = len(nodes)
    parent_indices = [int(node.get("parent_index", 0xFF)) for node in nodes]
    node_flags = list(skeleton.get("node_flags") or [node.get("flags", 0) for node in nodes])
    skin_node_indices = [int(value) for value in skeleton.get("skin_node_indices") or []]
    layout = derive_layout_start_info(parent_indices, node_flags)
    bind_coords = [_node_to_trs(node) for node in nodes]
    base_absolute = build_base_absolute(bind_coords, parent_indices, layout)
    base_inverse = [affine_inverse(matrix) for matrix in base_absolute]
    frames: list[HierarchyFrame] = []
    for pose_frame in pose.frames:
        relative = build_relative_coords(pose_frame.nodes, bind_coords, layout)
        absolute = build_current_absolute(relative, parent_indices, node_flags, layout)
        render = build_render_matrices(absolute, base_inverse, skin_node_indices)
        frames.append(HierarchyFrame(int(pose_frame.frame), absolute, render))
    if strict:
        for frame in frames:
            for matrix in (*frame.absolute_node_matrices, *frame.render_matrices):
                if not all(math.isfinite(value) for row in matrix for value in row):
                    raise NormalClipBindError(
                        f"frame {frame.frame} contains a non-finite hierarchy matrix"
                    )
    return NormalClipBindResult(
        type="ANIM_NORMAL_CLIP_BIND_HIERARCHY",
        frame_count=int(pose.frame_count),
        node_count=node_count,
        skin_bone_count=len(skin_node_indices),
        layout=layout,
        skin_node_indices=skin_node_indices,
        base_absolute_matrices=base_absolute,
        base_absolute_inverse_matrices=base_inverse,
        frames=frames,
        skeleton_remap_applied=bool(getattr(pose, "skeleton_remap_applied", False)),
        notes=[
            "Relative CCoords are animation * bind: quaternion product, scale product, translation sum.",
            "The active anchor relative transform is copied to absolute node zero.",
            "Base hierarchical matrices omit local scale below the root/control zone.",
            "Node flag bit 0 selects no-scale propagation; clear selects scale propagation.",
            "Render matrices are currentAbsolute[node] * inverseBaseAbsolute[node].",
            "External model/world transforms and Blender basis conversion remain separate.",
        ],
    )


def compose_normal_clip_bind_hierarchy(
    raw: bytes,
    skeleton: dict[str, Any],
    *,
    apply_skeleton_remap: bool = False,
    strict: bool = True,
) -> NormalClipBindResult:
    nodes = skeleton.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise NormalClipBindError("SKEL summary has no nodes")
    map_entries = None
    if apply_skeleton_remap:
        map_entries = (skeleton.get("skeleton_map") or {}).get("u16_values")
        if not isinstance(map_entries, list):
            raise NormalClipBindError("SKEL summary has no skeleton_map.u16_values")
    pose = evaluate_normal_clip_local_pose(
        raw,
        len(nodes),
        skeleton_map_entries=map_entries,
        apply_skeleton_remap=apply_skeleton_remap,
        strict=strict,
    )
    return compose_bind_hierarchy_from_pose(pose, skeleton, strict=strict)
