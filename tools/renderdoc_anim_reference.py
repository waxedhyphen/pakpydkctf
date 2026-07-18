#!/usr/bin/env python3
"""Convert RenderDoc float4 buffer CSVs into animation reference transforms.

The supplied capture contains 128 affine 3x4 matrices. The first N matrices,
where N is the DAE controller joint count, are treated as skin matrices in the
same order as the controller's JOINT array. Animated global and local matrices
are reconstructed with the DAE inverse-bind matrices.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import numpy as np

COLLADA_NS = "{http://www.collada.org/2005/11/COLLADASchema}"


def natural_key(path: Path) -> list[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.stem)]


def parse_float4_csv(path: Path) -> np.ndarray:
    rows: list[list[float]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "Value" not in reader.fieldnames:
            raise ValueError(f"{path}: CSV has no Value column")
        for row in reader:
            name = row.get("Name", "")
            value = row.get("Value", "")
            if "[" not in name or not value:
                continue
            parts = [float(item.strip()) for item in value.split(",")]
            if len(parts) != 4:
                raise ValueError(f"{path}: expected float4, got {value!r}")
            rows.append(parts)
    if not rows:
        raise ValueError(f"{path}: no float4 rows found")
    return np.asarray(rows, dtype=np.float64)


def source_float_array(source: ET.Element) -> np.ndarray:
    array = source.find(f"{COLLADA_NS}float_array")
    if array is None or not array.text:
        raise ValueError("COLLADA source has no float_array")
    return np.asarray([float(value) for value in array.text.split()], dtype=np.float64)


def parse_dae(path: Path) -> tuple[list[str], np.ndarray, dict[str, str | None]]:
    tree = ET.parse(path)
    root = tree.getroot()
    controller = root.find(f".//{COLLADA_NS}controller")
    if controller is None:
        raise ValueError("DAE has no controller")
    skin = controller.find(f"{COLLADA_NS}skin")
    if skin is None:
        raise ValueError("DAE controller has no skin")

    joints = skin.find(f"{COLLADA_NS}joints")
    if joints is None:
        raise ValueError("DAE skin has no joints")
    joint_source_id = None
    bind_source_id = None
    for item in joints.findall(f"{COLLADA_NS}input"):
        semantic = item.get("semantic")
        source_id = (item.get("source") or "").lstrip("#")
        if semantic == "JOINT":
            joint_source_id = source_id
        elif semantic == "INV_BIND_MATRIX":
            bind_source_id = source_id
    if not joint_source_id or not bind_source_id:
        raise ValueError("DAE joints block lacks JOINT or INV_BIND_MATRIX source")

    source_by_id = {element.get("id"): element for element in skin.findall(f"{COLLADA_NS}source")}
    joint_source = source_by_id[joint_source_id]
    name_array = joint_source.find(f"{COLLADA_NS}Name_array")
    if name_array is None:
        name_array = joint_source.find(f"{COLLADA_NS}IDREF_array")
    if name_array is None or not name_array.text:
        raise ValueError("DAE JOINT source has no names")
    joint_names = name_array.text.split()

    bind_values = source_float_array(source_by_id[bind_source_id])
    if bind_values.size != len(joint_names) * 16:
        raise ValueError("inverse-bind matrix count does not match joint count")
    inverse_bind = bind_values.reshape(len(joint_names), 4, 4)

    parent: dict[str, str | None] = {}
    visual_scene = root.find(f".//{COLLADA_NS}visual_scene")
    if visual_scene is None:
        raise ValueError("DAE has no visual_scene")

    def visit(node: ET.Element, parent_name: str | None) -> None:
        name = node.get("sid") or node.get("name") or node.get("id")
        next_parent = parent_name
        if name:
            parent[name] = parent_name
            next_parent = name
        for child in node.findall(f"{COLLADA_NS}node"):
            visit(child, next_parent)

    for node in visual_scene.findall(f"{COLLADA_NS}node"):
        visit(node, None)
    return joint_names, inverse_bind, parent


def affine_from_rows(rows: np.ndarray) -> np.ndarray:
    if rows.shape != (3, 4):
        raise ValueError(f"expected 3x4 matrix rows, got {rows.shape}")
    result = np.eye(4, dtype=np.float64)
    result[:3, :] = rows
    return result


def rotation_matrix_to_quaternion_wxyz(matrix: np.ndarray) -> list[float]:
    m = matrix
    trace = float(np.trace(m))
    if trace > 0.0:
        s = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(max(0.0, 1.0 + m[0, 0] - m[1, 1] - m[2, 2])) * 2.0
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(max(0.0, 1.0 + m[1, 1] - m[0, 0] - m[2, 2])) * 2.0
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(max(0.0, 1.0 + m[2, 2] - m[0, 0] - m[1, 1])) * 2.0
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    quaternion = np.asarray([w, x, y, z], dtype=np.float64)
    norm = float(np.linalg.norm(quaternion))
    if norm > 1e-12:
        quaternion /= norm
    return [float(value) for value in quaternion]


def decompose_affine(matrix: np.ndarray) -> dict[str, list[float]]:
    translation = matrix[:3, 3].copy()
    basis = matrix[:3, :3].copy()
    scale = np.linalg.norm(basis, axis=0)
    safe_scale = np.where(scale < 1e-12, 1.0, scale)
    rotation = basis / safe_scale
    u, _, vt = np.linalg.svd(rotation)
    rotation = u @ vt
    if np.linalg.det(rotation) < 0.0:
        u[:, -1] *= -1.0
        rotation = u @ vt
        scale[-1] *= -1.0
    return {
        "translation": [float(value) for value in translation],
        "rotation_wxyz": rotation_matrix_to_quaternion_wxyz(rotation),
        "scale": [float(value) for value in scale],
    }


def round_nested(value: Any, digits: int) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [round_nested(item, digits) for item in value]
    if isinstance(value, dict):
        return {key: round_nested(item, digits) for key, item in value.items()}
    return value


def build_reference(csv_dir: Path, dae: Path, fps: float, digits: int) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    joint_names, inverse_bind, parent = parse_dae(dae)
    joint_count = len(joint_names)
    csv_paths = sorted(csv_dir.glob("*.csv"), key=natural_key)
    if not csv_paths:
        raise ValueError(f"no CSV files in {csv_dir}")

    all_rows = [parse_float4_csv(path) for path in csv_paths]
    minimum_rows = joint_count * 3
    for path, rows in zip(csv_paths, all_rows):
        if rows.shape[0] < minimum_rows:
            raise ValueError(f"{path}: {rows.shape[0]} float4 rows, need at least {minimum_rows}")

    skin_matrices = np.empty((len(csv_paths), joint_count, 4, 4), dtype=np.float64)
    global_matrices = np.empty_like(skin_matrices)
    local_matrices = np.empty_like(skin_matrices)
    bind_global = np.linalg.inv(inverse_bind)
    joint_index = {name: index for index, name in enumerate(joint_names)}

    for frame_index, rows in enumerate(all_rows):
        for joint_index_value in range(joint_count):
            start = joint_index_value * 3
            skin_matrices[frame_index, joint_index_value] = affine_from_rows(rows[start : start + 3])
            global_matrices[frame_index, joint_index_value] = skin_matrices[frame_index, joint_index_value] @ bind_global[joint_index_value]
        for joint_index_value, name in enumerate(joint_names):
            parent_name = parent.get(name)
            if parent_name in joint_index:
                parent_matrix = global_matrices[frame_index, joint_index[parent_name]]
                local_matrices[frame_index, joint_index_value] = np.linalg.inv(parent_matrix) @ global_matrices[frame_index, joint_index_value]
            else:
                local_matrices[frame_index, joint_index_value] = global_matrices[frame_index, joint_index_value]

    transforms: list[list[dict[str, list[float]]]] = []
    previous_quaternion: list[np.ndarray | None] = [None] * joint_count
    for frame_index in range(len(csv_paths)):
        frame_transforms: list[dict[str, list[float]]] = []
        for joint_index_value in range(joint_count):
            item = decompose_affine(local_matrices[frame_index, joint_index_value])
            quaternion = np.asarray(item["rotation_wxyz"], dtype=np.float64)
            previous = previous_quaternion[joint_index_value]
            if previous is not None and float(np.dot(previous, quaternion)) < 0.0:
                quaternion *= -1.0
                item["rotation_wxyz"] = [float(value) for value in quaternion]
            previous_quaternion[joint_index_value] = quaternion
            frame_transforms.append(item)
        transforms.append(frame_transforms)

    frame_records = []
    for frame_index, (path, frame_transforms) in enumerate(zip(csv_paths, transforms)):
        joint_records = {}
        for index, name in enumerate(joint_names):
            item = dict(frame_transforms[index])
            item["global_matrix_row_major"] = [float(value) for value in global_matrices[frame_index, index].reshape(-1)]
            item["parent_joint"] = parent.get(name) if parent.get(name) in joint_index else None
            item["local_space"] = "parent_joint" if parent.get(name) in joint_index else "model_space_root"
            joint_records[name] = item
        frame_records.append(
            {
                "capture_index": frame_index,
                "source_csv": path.name,
                "time_seconds_assuming_fps": frame_index / fps if fps > 0 else None,
                "joints": joint_records,
            }
        )

    inactive_tail_rows = [int(np.count_nonzero(np.abs(rows[minimum_rows:]) > 1e-12)) for rows in all_rows]
    report = {
        "type": "RENDERDOC_SKIN_MATRIX_ANIMATION_REFERENCE",
        "status": "ground_truth_gpu_capture_not_raw_anim_decode",
        "source_csv_directory": str(csv_dir),
        "source_dae": str(dae),
        "capture_count": len(csv_paths),
        "fps_assumption": fps,
        "joint_count": joint_count,
        "matrix_layout": "three float4 rows per affine 3x4 matrix; first controller_joint_count matrices used",
        "reconstruction": "global_anim = skin_matrix @ inverse(inverse_bind); local_anim = inverse(parent_global) @ global_anim",
        "joint_order": joint_names,
        "joint_parent_in_controller": {name: (parent.get(name) if parent.get(name) in joint_index else None) for name in joint_names},
        "validation": {
            "float4_rows_per_capture": [int(rows.shape[0]) for rows in all_rows],
            "active_joint_float4_rows": minimum_rows,
            "nonzero_scalar_count_after_joint_rows": inactive_tail_rows,
            "root_or_external_parent_joint_count": sum(1 for name in joint_names if parent.get(name) not in joint_index),
            "warning": "The CSV sequence can contain interpolated render poses; capture index is not proven to equal source ANIM key index.",
        },
        "frames": frame_records,
    }
    arrays = {
        "skin_matrices": skin_matrices,
        "global_matrices": global_matrices,
        "local_matrices": local_matrices,
        "inverse_bind_matrices": inverse_bind,
        "joint_names": np.asarray(joint_names, dtype=str),
        "source_csv_names": np.asarray([path.name for path in csv_paths], dtype=str),
    }
    return round_nested(report, digits), arrays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-dir", type=Path, required=True)
    parser.add_argument("--dae", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-npz", type=Path, default=None)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--digits", type=int, default=7)
    args = parser.parse_args()

    report, arrays = build_reference(args.csv_dir, args.dae, args.fps, args.digits)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.output_npz:
        args.output_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(args.output_npz, **arrays)
    print(f"wrote {report['capture_count']} captures x {report['joint_count']} joints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
