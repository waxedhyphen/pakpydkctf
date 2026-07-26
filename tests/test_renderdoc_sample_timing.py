from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).parents[1] / "tools" / "analyze_renderdoc_sample_timing.py"
SPEC = importlib.util.spec_from_file_location("analyze_renderdoc_sample_timing", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
analyze_timing = MODULE.analyze_timing


def make_translation_sequence() -> np.ndarray:
    # Source keys are captures 2, 4, 6, 8. Odd captures are exact half steps.
    key_values = np.array([0.0, 1.0, 4.0, 9.0], dtype=np.float64)
    values = np.array(
        [
            -0.5,
            key_values[0],
            (key_values[0] + key_values[1]) * 0.5,
            key_values[1],
            (key_values[1] + key_values[2]) * 0.5,
            key_values[2],
            (key_values[2] + key_values[3]) * 0.5,
            key_values[3],
            11.5,
        ],
        dtype=np.float64,
    )
    matrices = np.tile(np.eye(4, dtype=np.float64), (values.size, 2, 1, 1))
    matrices[:, :, 0, 3] = values[:, None]
    return matrices


def test_detects_even_capture_source_keys() -> None:
    report = analyze_timing(make_translation_sequence(), render_fps=60.0, anim_sample_count=61)
    inference = report["inference"]
    assert inference["interpolated_midpoint_capture_parity"] == "odd"
    assert inference["source_key_capture_parity"] == "even"
    assert inference["source_key_capture_numbers"] == [2, 4, 6, 8]
    assert inference["inferred_source_sample_fps"] == 30.0
    assert inference["inferred_duration_seconds"] == 2.0


def test_continuous_sequence_has_no_boundary_flag() -> None:
    report = analyze_timing(make_translation_sequence())
    assert report["sequence_continuity"]["abrupt_boundary_detected"] is False
