#!/usr/bin/env python3
"""Detect source-sample timing in consecutive RenderDoc skeletal poses.

The input is the NPZ produced by ``renderdoc_anim_reference.py``. The tool
compares each interior capture with the midpoint between its neighbours. A
strong alternating midpoint pattern identifies render-frame interpolation and
which capture parity is closest to source animation samples.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


def _rotation_matrix_to_quaternion_wxyz(matrix: np.ndarray) -> np.ndarray:
    """Convert a proper 3x3 rotation matrix to a unit WXYZ quaternion."""
    m = matrix
    trace = float(np.trace(m))
    if trace > 0.0:
        s = math.sqrt(max(trace + 1.0, 0.0)) * 2.0
        quat = np.array(
            [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s],
            dtype=np.float64,
        )
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(max(1.0 + m[0, 0] - m[1, 1] - m[2, 2], 0.0)) * 2.0
        quat = np.array(
            [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s],
            dtype=np.float64,
        )
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(max(1.0 + m[1, 1] - m[0, 0] - m[2, 2], 0.0)) * 2.0
        quat = np.array(
            [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s],
            dtype=np.float64,
        )
    else:
        s = math.sqrt(max(1.0 + m[2, 2] - m[0, 0] - m[1, 1], 0.0)) * 2.0
        quat = np.array(
            [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s],
            dtype=np.float64,
        )
    norm = float(np.linalg.norm(quat))
    return quat / norm if norm > 1e-15 else np.array([1.0, 0.0, 0.0, 0.0])


def _quaternion_to_rotation_matrix(quat: np.ndarray) -> np.ndarray:
    w, x, y, z = quat
    return np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def _slerp_midpoint(q0: np.ndarray, q1: np.ndarray) -> np.ndarray:
    """Unit-quaternion midpoint; normalized sum equals SLERP at t=0.5."""
    if float(np.dot(q0, q1)) < 0.0:
        q1 = -q1
    value = q0 + q1
    norm = float(np.linalg.norm(value))
    if norm < 1e-12:
        return q0.copy()
    return value / norm


def _polar_decompose(basis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return proper rotation and symmetric stretch, basis = rotation @ stretch."""
    u, singular, vt = np.linalg.svd(basis)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0.0:
        u[:, -1] *= -1.0
        singular[-1] *= -1.0
        rotation = u @ vt
    stretch = vt.T @ np.diag(singular) @ vt
    return rotation, stretch


def _trs_midpoint(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ra, sa = _polar_decompose(a[:3, :3])
    rb, sb = _polar_decompose(b[:3, :3])
    qa = _rotation_matrix_to_quaternion_wxyz(ra)
    qb = _rotation_matrix_to_quaternion_wxyz(rb)

    result = np.eye(4, dtype=np.float64)
    result[:3, :3] = _quaternion_to_rotation_matrix(_slerp_midpoint(qa, qb)) @ ((sa + sb) * 0.5)
    result[:3, 3] = (a[:3, 3] + b[:3, 3]) * 0.5
    return result


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "median": float(np.median(array)),
        "maximum": float(np.max(array)),
    }


def analyze_timing(
    matrices: np.ndarray,
    render_fps: float | None = 60.0,
    anim_sample_count: int | None = None,
) -> dict[str, Any]:
    if matrices.ndim != 4 or matrices.shape[-2:] != (4, 4):
        raise ValueError(f"expected (capture,joint,4,4), got {matrices.shape}")
    capture_count, joint_count = matrices.shape[:2]
    if capture_count < 5:
        raise ValueError("at least five consecutive captures are required")

    parity_records: dict[int, dict[str, Any]] = {}
    for zero_based_parity in (0, 1):
        matrix_errors: list[float] = []
        trs_errors: list[float] = []
        capture_numbers: list[int] = []
        for center in range(1, capture_count - 1):
            if center % 2 != zero_based_parity:
                continue
            linear_midpoint = (matrices[center - 1] + matrices[center + 1]) * 0.5
            matrix_errors.append(
                float(np.sqrt(np.mean((matrices[center, :, :3, :] - linear_midpoint[:, :3, :]) ** 2)))
            )

            predicted = np.empty((joint_count, 4, 4), dtype=np.float64)
            for joint in range(joint_count):
                predicted[joint] = _trs_midpoint(matrices[center - 1, joint], matrices[center + 1, joint])
            trs_errors.append(float(np.sqrt(np.mean((matrices[center, :, :3, :] - predicted[:, :3, :]) ** 2))))
            capture_numbers.append(center + 1)

        parity_records[zero_based_parity] = {
            "capture_number_parity": "odd" if zero_based_parity == 0 else "even",
            "center_capture_numbers": capture_numbers,
            "linear_matrix_midpoint_rms": _summary(matrix_errors),
            "trs_midpoint_rms": _summary(trs_errors),
        }

    midpoint_parity = min(
        parity_records,
        key=lambda parity: parity_records[parity]["trs_midpoint_rms"]["median"],
    )
    source_key_parity = 1 - midpoint_parity
    midpoint_median = parity_records[midpoint_parity]["trs_midpoint_rms"]["median"]
    other_median = parity_records[source_key_parity]["trs_midpoint_rms"]["median"]
    separation_ratio = float(other_median / midpoint_median) if midpoint_median > 0.0 else math.inf

    source_key_capture_numbers = [index + 1 for index in range(capture_count) if index % 2 == source_key_parity]
    adjacent_rms = np.sqrt(np.mean((matrices[1:, :, :3, :] - matrices[:-1, :, :3, :]) ** 2, axis=(1, 2, 3)))
    adjacent_median = float(np.median(adjacent_rms))
    adjacent_maximum = float(np.max(adjacent_rms))
    adjacent_ratio = adjacent_maximum / adjacent_median if adjacent_median > 0.0 else math.inf
    largest_step = int(np.argmax(adjacent_rms))

    source_fps = render_fps / 2.0 if render_fps and render_fps > 0.0 else None
    duration = None
    if source_fps and anim_sample_count is not None and anim_sample_count > 0:
        duration = (anim_sample_count - 1) / source_fps

    return {
        "type": "RENDERDOC_ANIMATION_SAMPLE_TIMING_ANALYSIS",
        "capture_count": int(capture_count),
        "joint_count": int(joint_count),
        "parity_analysis": [parity_records[0], parity_records[1]],
        "inference": {
            "interpolated_midpoint_capture_parity": parity_records[midpoint_parity]["capture_number_parity"],
            "source_key_capture_parity": "odd" if source_key_parity == 0 else "even",
            "source_key_capture_numbers": source_key_capture_numbers,
            "midpoint_median_separation_ratio": separation_ratio,
            "render_frames_per_source_sample_interval": 2,
            "render_fps": render_fps,
            "inferred_source_sample_fps": source_fps,
            "anim_sample_count": anim_sample_count,
            "inferred_duration_seconds": duration,
        },
        "sequence_continuity": {
            "adjacent_rms_median": adjacent_median,
            "adjacent_rms_maximum": adjacent_maximum,
            "maximum_to_median_ratio": adjacent_ratio,
            "largest_step_between_capture_numbers": [largest_step + 1, largest_step + 2],
            "abrupt_boundary_detected": bool(adjacent_ratio >= 3.0),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference_npz", type=Path, help="NPZ from renderdoc_anim_reference.py")
    parser.add_argument("--matrix-array", default="local_matrices")
    parser.add_argument("--render-fps", type=float, default=60.0)
    parser.add_argument("--anim-sample-count", type=int, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with np.load(args.reference_npz) as archive:
        if args.matrix_array not in archive:
            raise KeyError(f"{args.matrix_array!r} not present in {args.reference_npz}")
        matrices = np.asarray(archive[args.matrix_array], dtype=np.float64)

    report = analyze_timing(matrices, args.render_fps, args.anim_sample_count)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["inference"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
