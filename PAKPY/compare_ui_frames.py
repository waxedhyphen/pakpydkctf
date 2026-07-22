"""Compare two UI frame PNGs and optionally write heatmap and JSON diagnostics.

Usage:
    python compare_ui_frames.py reference.png actual.png \
        --threshold 8 --heatmap diff.png --overlay overlay.png --json report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from ui_frame_compare import compare_images, difference_image, overlay_difference


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", help="trusted reference PNG")
    parser.add_argument("actual", help="rendered PNG to evaluate")
    parser.add_argument("--threshold", type=int, default=0, help="per-channel tolerance, 0-255")
    parser.add_argument("--ignore-alpha", action="store_true", help="compare RGB only")
    parser.add_argument("--heatmap", help="write transparent difference heatmap")
    parser.add_argument("--overlay", help="write heatmap composited over the reference")
    parser.add_argument("--json", dest="json_path", help="write machine-readable report")
    parser.add_argument(
        "--fail-above", type=float, default=None,
        help="exit 2 when percent of pixels above threshold exceeds this value",
    )
    args = parser.parse_args(argv)

    reference = Image.open(args.reference)
    actual = Image.open(args.actual)
    report = compare_images(
        reference, actual, threshold=args.threshold, ignore_alpha=args.ignore_alpha,
    )
    payload = report.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.heatmap:
        output = Path(args.heatmap)
        output.parent.mkdir(parents=True, exist_ok=True)
        difference_image(reference, actual, args.ignore_alpha).save(output)
    if args.overlay:
        output = Path(args.overlay)
        output.parent.mkdir(parents=True, exist_ok=True)
        overlay_difference(reference, actual, ignore_alpha=args.ignore_alpha).save(output)
    if args.json_path:
        output = Path(args.json_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.fail_above is not None:
        percent = report.threshold_pixels * 100.0 / max(1, report.pixels)
        if percent > max(0.0, float(args.fail_above)):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
