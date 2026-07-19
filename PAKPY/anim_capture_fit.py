#!/usr/bin/env python3
"""Fit chronological RenderDoc matrix-palette CSV captures to normal_clip exports.

The matcher deliberately treats capture numbers as chronological render samples,
not ANIM frame indices. It searches cyclic clip time, including subframes, and
reports both absolute palette error and temporal-motion error. The latter is
robust against nearly constant per-bone live-pose offsets.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np


class CaptureFitError(ValueError):
    pass


@dataclass(frozen=True)
class FitResult:
    clip_name: str
    source_file: str
    frame_count: int
    loop_length: float
    capture_count: int
    offset: float
    step: float
    absolute_rmse: float
    motion_rmse: float
    centered_rmse: float
    score: float


def _parse_float4(value: str) -> tuple[float, float, float, float]:
    text = str(value).strip().strip('"')
    parts = [part.strip() for part in text.split(',')]
    if len(parts) != 4:
        raise CaptureFitError(f"expected float4, got {value!r}")
    out = tuple(float(part) for part in parts)
    if not all(math.isfinite(v) for v in out):
        raise CaptureFitError(f"non-finite float4 {value!r}")
    return out  # type: ignore[return-value]


def read_capture_csv(path: str | Path, bone_count: int = 60) -> np.ndarray:
    rows: list[tuple[float, float, float, float]] = []
    with Path(path).open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        for item in reader:
            name = str(item.get('Name') or '')
            if not name.startswith('_child0['):
                continue
            rows.append(_parse_float4(str(item.get('Value') or '')))
            if len(rows) == bone_count * 3:
                break
    if len(rows) != bone_count * 3:
        raise CaptureFitError(
            f"{path}: expected {bone_count * 3} palette rows, got {len(rows)}"
        )
    return np.asarray(rows, dtype=np.float64).reshape(bone_count, 3, 4)


def read_capture_sequence(folder: str | Path, bone_count: int = 60) -> np.ndarray:
    root = Path(folder)
    paths = sorted(
        root.glob('*.csv'),
        key=lambda path: int(path.stem) if path.stem.isdigit() else 10**9,
    )
    if not paths:
        raise CaptureFitError(f"no capture CSVs found in {root}")
    return np.stack([read_capture_csv(path, bone_count) for path in paths], axis=0)


def load_bind_document(path: str | Path) -> tuple[str, np.ndarray]:
    source = Path(path)
    document = json.loads(source.read_text(encoding='utf-8'))
    frames = document.get('frames') or []
    matrices = [frame.get('render_matrices_3x4') or [] for frame in frames]
    if not matrices:
        raise CaptureFitError(f"{source}: no render matrices")
    array = np.asarray(matrices, dtype=np.float64)
    if array.ndim != 4 or array.shape[2:] != (3, 4):
        raise CaptureFitError(f"{source}: unexpected matrix shape {array.shape}")
    if not np.isfinite(array).all():
        raise CaptureFitError(f"{source}: non-finite matrices")
    name = source.name.replace('.normal_clip_bind.json', '')
    if '__' in name:
        name = name.rsplit('__', 1)[0]
    return name, array


def discover_bind_files(root: str | Path) -> list[Path]:
    base = Path(root)
    paths = list(base.glob('debug/anim_normal_clip_bind/*.normal_clip_bind.json'))
    paths += list(base.glob('models/*/debug/anim_normal_clip_bind/*.normal_clip_bind.json'))
    unique: dict[str, Path] = {}
    for path in paths:
        key = path.name
        if key not in unique or '/models/' in str(path).replace('\\', '/'):
            unique[key] = path
    return [unique[key] for key in sorted(unique)]


def infer_loop_length(frames: np.ndarray, duplicate_threshold: float = 2e-3) -> float:
    if len(frames) < 2:
        return float(len(frames))
    endpoint_rmse = float(np.sqrt(np.mean((frames[0] - frames[-1]) ** 2)))
    return float(len(frames) - 1 if endpoint_rmse <= duplicate_threshold else len(frames))


def sample_frames(frames: np.ndarray, times: np.ndarray, loop_length: float) -> np.ndarray:
    if loop_length <= 0:
        raise CaptureFitError(f"invalid loop length {loop_length}")
    wrapped = np.mod(times, loop_length)
    left = np.floor(wrapped).astype(np.int64)
    frac = wrapped - left
    right = (left + 1) % max(1, int(round(loop_length)))
    left = np.clip(left, 0, len(frames) - 1)
    right = np.clip(right, 0, len(frames) - 1)
    weight = frac.reshape((-1, 1, 1, 1))
    return frames[left] * (1.0 - weight) + frames[right] * weight


def _rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values))))


def score_fit(captures: np.ndarray, predicted: np.ndarray) -> tuple[float, float, float, float]:
    absolute = _rmse(captures - predicted)
    motion = _rmse(np.diff(captures, axis=0) - np.diff(predicted, axis=0))
    residual = captures - predicted
    centered = _rmse(residual - residual.mean(axis=0, keepdims=True))
    combined = motion + 0.10 * centered + 0.02 * absolute
    return absolute, motion, centered, combined


def _grid(start: float, stop: float, step: float) -> np.ndarray:
    count = max(1, int(math.floor((stop - start) / step + 0.5)) + 1)
    return start + np.arange(count, dtype=np.float64) * step


def fit_clip(
    captures: np.ndarray,
    clip_name: str,
    source_file: str,
    frames: np.ndarray,
    *,
    step_min: float = 0.25,
    step_max: float = 1.25,
    coarse_step: float = 0.10,
    fine_step: float = 0.01,
) -> FitResult:
    if captures.shape[1:] != frames.shape[1:]:
        raise CaptureFitError(
            f"palette mismatch: captures {captures.shape[1:]}, clip {frames.shape[1:]}"
        )
    loop_length = infer_loop_length(frames)
    best: tuple[float, float, float, float, float, float] | None = None
    indices = np.arange(len(captures), dtype=np.float64)

    coarse_capture = captures[:, : min(20, captures.shape[1]), :, :]
    coarse_indices = indices
    coarse_frames = frames[:, : coarse_capture.shape[1], :, :]
    coarse_best: tuple[float, float, float] | None = None
    coarse_steps = sorted({
        *[float(value) for value in _grid(step_min, step_max, coarse_step)],
        *[value for value in (0.25, 0.5, 1.0) if step_min <= value <= step_max],
    })
    for step in coarse_steps:
        for offset in _grid(0.0, loop_length - coarse_step, coarse_step):
            predicted = sample_frames(coarse_frames, offset + coarse_indices * step, loop_length)
            _absolute, _motion, _centered, combined = score_fit(coarse_capture, predicted)
            candidate = (combined, float(offset), float(step))
            if coarse_best is None or candidate < coarse_best:
                coarse_best = candidate

    assert coarse_best is not None
    _, offset0, step0 = coarse_best
    for step in _grid(max(step_min, step0 - coarse_step), min(step_max, step0 + coarse_step), fine_step):
        for offset in _grid(offset0 - coarse_step, offset0 + coarse_step, fine_step):
            predicted = sample_frames(frames, offset + indices * step, loop_length)
            absolute, motion, centered, combined = score_fit(captures, predicted)
            candidate = (combined, absolute, motion, centered, float(offset), float(step))
            if best is None or candidate < best:
                best = candidate
    assert best is not None
    combined, absolute, motion, centered, offset, step = best
    offset %= loop_length
    return FitResult(
        clip_name=clip_name,
        source_file=source_file,
        frame_count=len(frames),
        loop_length=loop_length,
        capture_count=len(captures),
        offset=offset,
        step=step,
        absolute_rmse=absolute,
        motion_rmse=motion,
        centered_rmse=centered,
        score=combined,
    )


def fit_package(captures: np.ndarray, package: str | Path) -> list[FitResult]:
    results: list[FitResult] = []
    for path in discover_bind_files(package):
        name, frames = load_bind_document(path)
        results.append(fit_clip(captures, name, str(path), frames))
    if not results:
        raise CaptureFitError(f"no normal_clip bind files found under {package}")
    return sorted(results, key=lambda item: item.score)


def write_results(results: Sequence[FitResult], json_path: str | Path, csv_path: str | Path) -> None:
    payload = {
        'type': 'ANIM_CAPTURE_CLIP_FIT',
        'ranking': [asdict(item) for item in results],
        'notes': [
            'Capture numbers are chronological render samples, not ANIM frame indices.',
            'Subframe matrices are linearly interpolated for diagnostic fitting.',
            'motion_rmse is robust against constant live-pose offsets.',
        ],
    }
    Path(json_path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    fields = list(asdict(results[0]).keys()) if results else []
    with Path(csv_path).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(asdict(item) for item in results)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--captures', required=True, help='folder containing 1.csv, 2.csv, ...')
    parser.add_argument('--package', required=True, help='exported Character/Model package')
    parser.add_argument('--json', default='anim_capture_fit.json')
    parser.add_argument('--csv', default='anim_capture_fit.csv')
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    captures = read_capture_sequence(args.captures)
    results = fit_package(captures, args.package)
    write_results(results, args.json, args.csv)
    print(json.dumps(asdict(results[0]), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
