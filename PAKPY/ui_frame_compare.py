"""Deterministic pixel comparison helpers for UI reference frames."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import math

try:
    from PIL import Image, ImageChops
except Exception:
    Image = None
    ImageChops = None


@dataclass(frozen=True)
class FrameComparison:
    width: int
    height: int
    channels: int
    pixels: int
    differing_pixels: int
    threshold_pixels: int
    exact_percent: float
    within_threshold_percent: float
    mean_absolute_error: tuple[float, ...]
    root_mean_square_error: float
    peak_signal_to_noise_ratio: float | None
    max_channel_delta: int
    difference_bounds: tuple[int, int, int, int] | None
    reference_sha256: str
    actual_sha256: str
    threshold: int
    ignore_alpha: bool

    def to_dict(self):
        value = asdict(self)
        value["mean_absolute_error"] = list(self.mean_absolute_error)
        value["difference_bounds"] = (
            list(self.difference_bounds) if self.difference_bounds is not None else None
        )
        return {"schema": 1, **value}


def _require_pillow():
    if Image is None:
        raise RuntimeError("Pillow is required for frame comparison")


def _rgba(image):
    _require_pillow()
    return image.convert("RGBA")


def _digest(image):
    payload = (
        f"{image.mode}:{image.width}x{image.height}:".encode("ascii")
        + image.tobytes()
    )
    return hashlib.sha256(payload).hexdigest()


def compare_images(reference, actual, threshold=0, ignore_alpha=False):
    """Compare two equally sized images and return stable numerical metrics."""
    reference = _rgba(reference)
    actual = _rgba(actual)
    if reference.size != actual.size:
        raise ValueError(
            f"image sizes differ: reference={reference.size}, actual={actual.size}"
        )
    threshold = max(0, min(255, int(threshold or 0)))
    channels = 3 if ignore_alpha else 4
    ref = reference.tobytes()
    got = actual.tobytes()
    pixel_count = reference.width * reference.height
    channel_sums = [0] * channels
    squared_sum = 0
    differing = 0
    threshold_pixels = 0
    max_delta = 0
    min_x = reference.width
    min_y = reference.height
    max_x = max_y = -1

    for pixel in range(pixel_count):
        base = pixel * 4
        deltas = [abs(ref[base + i] - got[base + i]) for i in range(channels)]
        peak = max(deltas) if deltas else 0
        if peak:
            differing += 1
            x = pixel % reference.width
            y = pixel // reference.width
            min_x, min_y = min(min_x, x), min(min_y, y)
            max_x, max_y = max(max_x, x), max(max_y, y)
        if peak > threshold:
            threshold_pixels += 1
        max_delta = max(max_delta, peak)
        for index, delta in enumerate(deltas):
            channel_sums[index] += delta
            squared_sum += delta * delta

    sample_count = max(1, pixel_count * channels)
    mae = tuple(value / float(max(1, pixel_count)) for value in channel_sums)
    rmse = math.sqrt(squared_sum / float(sample_count))
    psnr = None if rmse <= 0.0 else 20.0 * math.log10(255.0 / rmse)
    bounds = None if max_x < 0 else (min_x, min_y, max_x + 1, max_y + 1)
    return FrameComparison(
        width=reference.width,
        height=reference.height,
        channels=channels,
        pixels=pixel_count,
        differing_pixels=differing,
        threshold_pixels=threshold_pixels,
        exact_percent=(pixel_count - differing) * 100.0 / max(1, pixel_count),
        within_threshold_percent=(pixel_count - threshold_pixels) * 100.0 / max(1, pixel_count),
        mean_absolute_error=mae,
        root_mean_square_error=rmse,
        peak_signal_to_noise_ratio=psnr,
        max_channel_delta=max_delta,
        difference_bounds=bounds,
        reference_sha256=_digest(reference),
        actual_sha256=_digest(actual),
        threshold=threshold,
        ignore_alpha=bool(ignore_alpha),
    )


def difference_image(reference, actual, ignore_alpha=False):
    """Return an RGBA heatmap. Exact pixels remain transparent."""
    reference = _rgba(reference)
    actual = _rgba(actual)
    if reference.size != actual.size:
        raise ValueError(
            f"image sizes differ: reference={reference.size}, actual={actual.size}"
        )
    channels = 3 if ignore_alpha else 4
    ref = reference.tobytes()
    got = actual.tobytes()
    out = bytearray(reference.width * reference.height * 4)
    for pixel in range(reference.width * reference.height):
        base = pixel * 4
        peak = max(abs(ref[base + i] - got[base + i]) for i in range(channels))
        if not peak:
            continue
        red = min(255, peak * 4)
        green = max(0, min(255, (peak - 48) * 3))
        blue = max(0, min(255, (peak - 160) * 3))
        out[base:base + 4] = bytes((red, green, blue, 255))
    return Image.frombytes("RGBA", reference.size, bytes(out))


def overlay_difference(reference, actual, opacity=0.65, ignore_alpha=False):
    """Return the reference frame with the heatmap composited on top."""
    reference = _rgba(reference)
    heatmap = difference_image(reference, actual, ignore_alpha)
    opacity = max(0.0, min(1.0, float(opacity)))
    if opacity < 1.0:
        alpha = heatmap.getchannel("A").point(
            lambda value, factor=opacity: int(round(value * factor))
        )
        heatmap.putalpha(alpha)
    return Image.alpha_composite(reference, heatmap)
