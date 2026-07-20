"""Decode-once cache for TXTR -> PNG conversion.

Characters reference several model slots (body, head variants, ...) that very
often share the *same* textures. The export pipeline decoded (ASTC / Tegra
swizzle) and re-encoded each texture to PNG once per model, so a normal map
shared by five slots was decoded five times. In the sample outputs 285 raw
textures collapsed to only 172 unique ones, i.e. ~40% of the decode work was
redundant.

This patch memoizes the *pure* ``convert_txtr_to_png_bytes(raw) -> png_bytes``
call by the SHA-1 of the raw asset. It changes nothing about the output, only
how many times the expensive decode runs. The cache lives for the duration of
the process and is bounded so long batch runs cannot grow it without limit.
"""
from __future__ import annotations

import hashlib

import pak_extract

# Bytes of decoded PNGs we are willing to keep resident. A single Fugu normal
# map PNG is a few MB, so ~256 MB comfortably covers one character's texture set
# while protecting against unbounded growth over a whole-PAK batch export.
_MAX_CACHE_BYTES = 256 * 1024 * 1024

_cache: "dict[bytes, bytes]" = {}
_cache_bytes = 0


def _reset_cache() -> None:
    global _cache_bytes
    _cache.clear()
    _cache_bytes = 0


def install(App=None) -> None:
    original = pak_extract.convert_txtr_to_png_bytes
    if getattr(original, "_pakpy_decode_cache", False):
        return

    def cached_convert(raw):
        global _cache_bytes
        if not raw:
            return original(raw)
        try:
            key = hashlib.sha1(raw).digest()
        except Exception:
            return original(raw)
        hit = _cache.get(key)
        if hit is not None:
            return hit
        png = original(raw)
        if png:
            size = len(png)
            if size <= _MAX_CACHE_BYTES:
                if _cache_bytes + size > _MAX_CACHE_BYTES:
                    _reset_cache()
                _cache[key] = png
                _cache_bytes += size
        return png

    cached_convert._pakpy_decode_cache = True
    pak_extract.convert_txtr_to_png_bytes = cached_convert