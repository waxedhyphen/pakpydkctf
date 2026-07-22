"""Pure parsers and geometry helpers for remaining SWF visual formats.

The module contains no Tk integration.  It decodes bounded embedded bitmap tags,
DefineMorphShape/DefineMorphShape2 records, interpolates morph definitions into the
existing VectorShapeDef representation and exposes Scale9 inverse-coordinate helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import math
import zlib

import ui_browser
import ui_browser_shape_patch as shape_patch

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


TAG_JPEG_TABLES = 8
TAG_DEFINE_BITS = 6
TAG_DEFINE_BITS_JPEG2 = 21
TAG_DEFINE_BITS_JPEG3 = 35
TAG_DEFINE_BITS_LOSSLESS = 20
TAG_DEFINE_BITS_LOSSLESS2 = 36
TAG_DEFINE_BITS_JPEG4 = 90
TAG_DEFINE_MORPH_SHAPE = 46
TAG_DEFINE_MORPH_SHAPE2 = 84

MAX_BITMAP_DIMENSION = 8192
MAX_BITMAP_PIXELS = 32_000_000
MAX_BITMAP_BYTES = 256 * 1024 * 1024
MAX_EMBEDDED_BITMAP_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MORPH_STYLES = 65_535
MAX_MORPH_RECORDS = 2_000_000


@dataclass(frozen=True)
class EnhancedVectorFillStyle(shape_patch.VectorFillStyle):
    focal_point: float = 0.0


@dataclass(frozen=True)
class EmbeddedBitmapDef:
    character_id: int
    image: object
    source_tag: int
    format_name: str


@dataclass(frozen=True)
class MorphFillPair:
    start: EnhancedVectorFillStyle
    end: EnhancedVectorFillStyle


@dataclass(frozen=True)
class MorphLinePair:
    start: shape_patch.VectorLineStyle
    end: shape_patch.VectorLineStyle


@dataclass(frozen=True)
class MorphStyledEdge:
    fill0: int
    fill1: int
    line: int
    edge: shape_patch.VectorEdge


@dataclass
class MorphShapeDef:
    character_id: int
    version: int
    start_bounds: tuple[float, float, float, float]
    end_bounds: tuple[float, float, float, float]
    start_edge_bounds: tuple[float, float, float, float]
    end_edge_bounds: tuple[float, float, float, float]
    fills: tuple[MorphFillPair | None, ...]
    lines: tuple[MorphLinePair | None, ...]
    start_records: tuple[MorphStyledEdge, ...]
    end_records: tuple[MorphStyledEdge, ...]
    uses_non_scaling_strokes: bool = False
    uses_scaling_strokes: bool = False
    parse_warnings: tuple[str, ...] = ()


def _need(data: bytes, off: int, size: int, label: str) -> None:
    if off < 0 or size < 0 or off + size > len(data):
        raise ui_browser.PakError(f"{label} ist abgeschnitten")


def _le16(data: bytes, off: int) -> int:
    _need(data, off, 2, "UI16")
    return int.from_bytes(data[off:off + 2], "little")


def _le32(data: bytes, off: int) -> int:
    _need(data, off, 4, "UI32")
    return int.from_bytes(data[off:off + 4], "little")


def _s16(data: bytes, off: int) -> int:
    _need(data, off, 2, "SI16")
    return int.from_bytes(data[off:off + 2], "little", signed=True)


def _rgba(data: bytes, off: int):
    _need(data, off, 4, "RGBA")
    return tuple(data[off:off + 4]), off + 4


def _bounded_zlib(data: bytes, expected: int | None = None) -> bytes:
    if expected is not None and expected > MAX_BITMAP_BYTES:
        raise ui_browser.PakError("Dekodiertes Bitmap überschreitet das Byte-Limit")
    decoder = zlib.decompressobj()
    limit = MAX_BITMAP_BYTES if expected is None else min(MAX_BITMAP_BYTES, max(0, expected))
    result = decoder.decompress(data, limit + 1)
    if len(result) > limit:
        raise ui_browser.PakError("Zlib-Bitmap überschreitet das Byte-Limit")
    if decoder.unconsumed_tail:
        raise ui_browser.PakError("Zlib-Bitmap überschreitet das Byte-Limit")
    result += decoder.flush(max(0, limit + 1 - len(result)))
    if len(result) > limit:
        raise ui_browser.PakError("Zlib-Bitmap überschreitet das Byte-Limit")
    if expected is not None and len(result) < expected:
        raise ui_browser.PakError("Zlib-Bitmap ist abgeschnitten")
    return result


def _validate_bitmap_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ui_browser.PakError("Bitmap hat ungültige Abmessungen")
    if width > MAX_BITMAP_DIMENSION or height > MAX_BITMAP_DIMENSION:
        raise ui_browser.PakError("Bitmap überschreitet das Abmessungslimit")
    if width * height > MAX_BITMAP_PIXELS:
        raise ui_browser.PakError("Bitmap überschreitet das Pixellimit")


def decode_lossless_bitmap(payload: bytes, with_alpha: bool, source_tag: int) -> EmbeddedBitmapDef:
    if PILImage is None:
        raise ui_browser.PakError("Pillow fehlt für eingebettete SWF-Bitmaps")
    _need(payload, 0, 7, "DefineBitsLossless")
    character_id = _le16(payload, 0)
    bitmap_format = payload[2]
    width = _le16(payload, 3)
    height = _le16(payload, 5)
    _validate_bitmap_size(width, height)
    p = 7

    if bitmap_format == 3:
        _need(payload, p, 1, "ColorTableSize")
        color_count = int(payload[p]) + 1
        p += 1
        palette_stride = 4 if with_alpha else 3
        row_stride = (width + 3) & ~3
        expected = color_count * palette_stride + row_stride * height
        raw = _bounded_zlib(payload[p:], expected)
        palette = []
        q = 0
        for _ in range(color_count):
            color = tuple(raw[q:q + palette_stride])
            q += palette_stride
            if not with_alpha:
                color += (255,)
            palette.append(color)
        pixels = bytearray(width * height * 4)
        out = 0
        for y in range(height):
            row = q + y * row_stride
            for x in range(width):
                index = raw[row + x]
                color = palette[index] if index < len(palette) else (255, 0, 255, 255)
                pixels[out:out + 4] = bytes(color)
                out += 4
        image = PILImage.frombytes("RGBA", (width, height), bytes(pixels))
        return EmbeddedBitmapDef(character_id, image, source_tag, "colormapped8")

    if bitmap_format == 4:
        row_stride = ((width * 2) + 3) & ~3
        expected = row_stride * height
        raw = _bounded_zlib(payload[p:], expected)
        pixels = bytearray(width * height * 4)
        out = 0
        for y in range(height):
            row = y * row_stride
            for x in range(width):
                value = int.from_bytes(raw[row + x * 2:row + x * 2 + 2], "little")
                r = ((value >> 10) & 0x1F) * 255 // 31
                g = ((value >> 5) & 0x1F) * 255 // 31
                b = (value & 0x1F) * 255 // 31
                pixels[out:out + 4] = bytes((r, g, b, 255))
                out += 4
        image = PILImage.frombytes("RGBA", (width, height), bytes(pixels))
        return EmbeddedBitmapDef(character_id, image, source_tag, "rgb15")

    if bitmap_format == 5:
        expected = width * height * 4
        raw = _bounded_zlib(payload[p:], expected)
        pixels = bytearray(expected)
        out = 0
        for q in range(0, expected, 4):
            a_or_x, r, g, b = raw[q:q + 4]
            a = a_or_x if with_alpha else 255
            pixels[out:out + 4] = bytes((r, g, b, a))
            out += 4
        image = PILImage.frombytes("RGBA", (width, height), bytes(pixels))
        return EmbeddedBitmapDef(character_id, image, source_tag, "argb32" if with_alpha else "rgb32")

    raise ui_browser.PakError(f"Nicht unterstütztes Lossless-Bitmapformat {bitmap_format}")


def _clean_jpeg(data: bytes) -> bytes:
    # Older SWF encoders may leave an EOI/SOI pair between JPEGTables and image data.
    return bytes(data).replace(b"\xFF\xD9\xFF\xD8", b"\xFF\xD8")


def _open_jpeg(data: bytes):
    if PILImage is None:
        raise ui_browser.PakError("Pillow fehlt für JPEG-Bitmaps")
    if len(data) > MAX_BITMAP_BYTES:
        raise ui_browser.PakError("JPEG überschreitet das Byte-Limit")
    image = PILImage.open(io.BytesIO(_clean_jpeg(data)))
    image.load()
    _validate_bitmap_size(image.width, image.height)
    return image.convert("RGBA")


def decode_jpeg_bitmap(payload: bytes, source_tag: int, jpeg_tables: bytes = b"") -> EmbeddedBitmapDef:
    _need(payload, 0, 3, "DefineBitsJPEG")
    character_id = _le16(payload, 0)
    if source_tag == TAG_DEFINE_BITS:
        image = _open_jpeg(jpeg_tables + payload[2:])
        return EmbeddedBitmapDef(character_id, image, source_tag, "jpeg-tables")
    if source_tag == TAG_DEFINE_BITS_JPEG2:
        image = _open_jpeg(payload[2:])
        return EmbeddedBitmapDef(character_id, image, source_tag, "jpeg2")

    _need(payload, 2, 4, "AlphaDataOffset")
    alpha_offset = _le32(payload, 2)
    jpeg_start = 6
    if source_tag == TAG_DEFINE_BITS_JPEG4:
        _need(payload, 6, 2, "DeblockParam")
        jpeg_start = 8
    alpha_start = 6 + alpha_offset
    if alpha_start < jpeg_start or alpha_start > len(payload):
        raise ui_browser.PakError("JPEG-AlphaDataOffset ist ungültig")
    image = _open_jpeg(payload[jpeg_start:alpha_start])
    expected = image.width * image.height
    alpha = _bounded_zlib(payload[alpha_start:], expected)[:expected]
    image.putalpha(PILImage.frombytes("L", image.size, alpha))
    return EmbeddedBitmapDef(
        character_id, image, source_tag,
        "jpeg4-alpha" if source_tag == TAG_DEFINE_BITS_JPEG4 else "jpeg3-alpha",
    )


def parse_embedded_bitmaps(tags):
    tables = b""
    for code, payload in tags:
        if code == TAG_JPEG_TABLES:
            tables = bytes(payload)
            break
    result = {}
    errors = []
    total_bytes = 0
    for code, payload in tags:
        try:
            if code == TAG_DEFINE_BITS_LOSSLESS:
                value = decode_lossless_bitmap(payload, False, code)
            elif code == TAG_DEFINE_BITS_LOSSLESS2:
                value = decode_lossless_bitmap(payload, True, code)
            elif code in (TAG_DEFINE_BITS, TAG_DEFINE_BITS_JPEG2, TAG_DEFINE_BITS_JPEG3, TAG_DEFINE_BITS_JPEG4):
                value = decode_jpeg_bitmap(payload, code, tables)
            else:
                continue
            image_bytes = int(value.image.width) * int(value.image.height) * 4
            if total_bytes + image_bytes > MAX_EMBEDDED_BITMAP_TOTAL_BYTES:
                raise ui_browser.PakError("Eingebettete Bitmaps überschreiten das Gesamtlimit")
            previous = result.get(value.character_id)
            if previous is not None:
                total_bytes -= int(previous.image.width) * int(previous.image.height) * 4
            result[value.character_id] = value
            total_bytes += image_bytes
        except Exception as exc:
            errors.append({"tag": int(code), "error": str(exc)})
    return result, tuple(errors)


def _read_style_count(data: bytes, off: int):
    _need(data, off, 1, "Style-Anzahl")
    count = data[off]
    off += 1
    if count == 0xFF:
        count = _le16(data, off)
        off += 2
    if count > MAX_MORPH_STYLES:
        raise ui_browser.PakError("Morph-Style-Anzahl überschreitet das Limit")
    return count, off


def _enhanced_fill(kind: str, *, color=(255, 255, 255, 255), matrix=None, stops=(),
                   spread_mode=0, interpolation_mode=0, bitmap_id=0, fill_type=0,
                   focal_point=0.0):
    return EnhancedVectorFillStyle(
        kind=kind, color=tuple(color), matrix=matrix, stops=tuple(stops),
        spread_mode=int(spread_mode), interpolation_mode=int(interpolation_mode),
        bitmap_id=int(bitmap_id), fill_type=int(fill_type), focal_point=float(focal_point),
    )


def read_vector_fill_style(data: bytes, off: int, version: int, unsupported=None):
    """Replacement for the base shape parser that preserves focal-gradient values."""
    unsupported = set() if unsupported is None else unsupported
    _need(data, off, 1, "FillStyle-Typ")
    fill_type = data[off]
    off += 1
    with_alpha = version >= 3
    if fill_type == 0x00:
        count = 4 if with_alpha else 3
        _need(data, off, count, "Shape-Farbe")
        color = tuple(data[off:off + count]) + (() if with_alpha else (255,))
        return _enhanced_fill("solid", color=color, fill_type=fill_type), off + count
    if fill_type in (0x10, 0x12, 0x13):
        matrix, off = ui_browser._read_matrix(data, off)
        _need(data, off, 1, "Gradient-Header")
        flags = data[off]
        off += 1
        spread_mode = (flags >> 6) & 0x03
        interpolation_mode = (flags >> 4) & 0x03
        count = flags & 0x0F
        stops = []
        for _ in range(count):
            _need(data, off, 1, "Gradient-Ratio")
            ratio = data[off]
            off += 1
            color_count = 4 if with_alpha else 3
            _need(data, off, color_count, "Gradient-Farbe")
            color = tuple(data[off:off + color_count]) + (() if with_alpha else (255,))
            off += color_count
            stops.append(shape_patch.GradientStop(ratio, color))
        focal = 0.0
        if fill_type == 0x13:
            focal = _s16(data, off) / 256.0
            off += 2
        kind = {0x10: "linear_gradient", 0x12: "radial_gradient", 0x13: "focal_gradient"}[fill_type]
        return _enhanced_fill(
            kind, matrix=matrix, stops=stops, spread_mode=spread_mode,
            interpolation_mode=interpolation_mode, fill_type=fill_type,
            focal_point=max(-0.99, min(0.99, focal)),
        ), off
    if fill_type in (0x40, 0x41, 0x42, 0x43):
        bitmap_id = _le16(data, off)
        matrix, off = ui_browser._read_matrix(data, off + 2)
        return _enhanced_fill(
            "bitmap", matrix=matrix, bitmap_id=bitmap_id, fill_type=fill_type,
        ), off
    unsupported.add(fill_type)
    raise ui_browser.PakError(f"Unbekannter FillStyle 0x{fill_type:02X}")


def _read_morph_fill(data: bytes, off: int, version: int):
    _need(data, off, 1, "MorphFillStyle-Typ")
    fill_type = data[off]
    off += 1
    if fill_type == 0x00:
        start_color, off = _rgba(data, off)
        end_color, off = _rgba(data, off)
        return MorphFillPair(
            _enhanced_fill("solid", color=start_color, fill_type=fill_type),
            _enhanced_fill("solid", color=end_color, fill_type=fill_type),
        ), off
    if fill_type in (0x10, 0x12, 0x13):
        start_matrix, off = ui_browser._read_matrix(data, off)
        end_matrix, off = ui_browser._read_matrix(data, off)
        _need(data, off, 1, "MorphGradient-Header")
        flags = data[off]
        off += 1
        spread_mode = (flags >> 6) & 0x03
        interpolation_mode = (flags >> 4) & 0x03
        count = flags & 0x0F
        start_stops = []
        end_stops = []
        for _ in range(count):
            _need(data, off, 1, "MorphGradient-StartRatio")
            start_ratio = data[off]
            off += 1
            start_color, off = _rgba(data, off)
            _need(data, off, 1, "MorphGradient-EndRatio")
            end_ratio = data[off]
            off += 1
            end_color, off = _rgba(data, off)
            start_stops.append(shape_patch.GradientStop(start_ratio, start_color))
            end_stops.append(shape_patch.GradientStop(end_ratio, end_color))
        start_focal = end_focal = 0.0
        if fill_type == 0x13:
            start_focal = _s16(data, off) / 256.0
            end_focal = _s16(data, off + 2) / 256.0
            off += 4
        kind = {0x10: "linear_gradient", 0x12: "radial_gradient", 0x13: "focal_gradient"}[fill_type]
        return MorphFillPair(
            _enhanced_fill(
                kind, matrix=start_matrix, stops=start_stops, spread_mode=spread_mode,
                interpolation_mode=interpolation_mode, fill_type=fill_type,
                focal_point=max(-0.99, min(0.99, start_focal)),
            ),
            _enhanced_fill(
                kind, matrix=end_matrix, stops=end_stops, spread_mode=spread_mode,
                interpolation_mode=interpolation_mode, fill_type=fill_type,
                focal_point=max(-0.99, min(0.99, end_focal)),
            ),
        ), off
    if fill_type in (0x40, 0x41, 0x42, 0x43):
        bitmap_id = _le16(data, off)
        start_matrix, off = ui_browser._read_matrix(data, off + 2)
        end_matrix, off = ui_browser._read_matrix(data, off)
        return MorphFillPair(
            _enhanced_fill("bitmap", matrix=start_matrix, bitmap_id=bitmap_id, fill_type=fill_type),
            _enhanced_fill("bitmap", matrix=end_matrix, bitmap_id=bitmap_id, fill_type=fill_type),
        ), off
    raise ui_browser.PakError(f"Unbekannter MorphFillStyle 0x{fill_type:02X}")


def _read_morph_fill_array(data: bytes, off: int, version: int):
    count, off = _read_style_count(data, off)
    values = [None]
    for _ in range(count):
        value, off = _read_morph_fill(data, off, version)
        values.append(value)
    return tuple(values), off


def _read_morph_line(data: bytes, off: int, version: int):
    start_width = _le16(data, off) / 20.0
    end_width = _le16(data, off + 2) / 20.0
    off += 4
    if version == 1:
        start_color, off = _rgba(data, off)
        end_color, off = _rgba(data, off)
        return MorphLinePair(
            shape_patch.VectorLineStyle(start_width, start_color),
            shape_patch.VectorLineStyle(end_width, end_color),
        ), off

    reader = ui_browser._BitReader(data, off)
    start_cap = reader.read_u(2)
    join_style = reader.read_u(2)
    has_fill = bool(reader.read_u(1))
    reader.read_u(1)
    reader.read_u(1)
    reader.read_u(1)
    reader.read_u(5)
    no_close = bool(reader.read_u(1))
    end_cap = reader.read_u(2)
    reader.align()
    off = reader.byte_pos
    if join_style == 2:
        _need(data, off, 2, "MorphLineStyle2-MiterLimit")
        off += 2
    if has_fill:
        fill, off = _read_morph_fill(data, off, version)
        start_fill, end_fill = fill.start, fill.end
        start_color = start_fill.color if start_fill.kind == "solid" else (
            start_fill.stops[0].color if start_fill.stops else (255, 255, 255, 255)
        )
        end_color = end_fill.color if end_fill.kind == "solid" else (
            end_fill.stops[0].color if end_fill.stops else (255, 255, 255, 255)
        )
    else:
        start_fill = end_fill = None
        start_color, off = _rgba(data, off)
        end_color, off = _rgba(data, off)
    return MorphLinePair(
        shape_patch.VectorLineStyle(
            start_width, start_color, start_fill, start_cap, end_cap, join_style, no_close,
        ),
        shape_patch.VectorLineStyle(
            end_width, end_color, end_fill, start_cap, end_cap, join_style, no_close,
        ),
    ), off


def _read_morph_line_array(data: bytes, off: int, version: int):
    count, off = _read_style_count(data, off)
    values = [None]
    for _ in range(count):
        value, off = _read_morph_line(data, off, version)
        values.append(value)
    return tuple(values), off


def _read_shape_records(data: bytes, off: int, limit_end: int | None = None):
    reader = ui_browser._BitReader(data, off)
    num_fill_bits = reader.read_u(4)
    num_line_bits = reader.read_u(4)
    x = y = 0
    fill0 = fill1 = line = 0
    result = []
    while True:
        if len(result) > MAX_MORPH_RECORDS:
            raise ui_browser.PakError("Morph-Kanten überschreiten das Limit")
        if limit_end is not None and reader.byte_pos > limit_end:
            raise ui_browser.PakError("Morph-Startkanten überschreiten Offset")
        if reader.read_u(1):
            straight = bool(reader.read_u(1))
            nbits = reader.read_u(4) + 2
            start = (x, y)
            control = None
            if straight:
                if reader.read_u(1):
                    dx, dy = reader.read_s(nbits), reader.read_s(nbits)
                elif reader.read_u(1):
                    dx, dy = 0, reader.read_s(nbits)
                else:
                    dx, dy = reader.read_s(nbits), 0
                x += dx
                y += dy
            else:
                cdx, cdy = reader.read_s(nbits), reader.read_s(nbits)
                adx, ady = reader.read_s(nbits), reader.read_s(nbits)
                control = (x + cdx, y + cdy)
                x, y = control[0] + adx, control[1] + ady
            result.append(MorphStyledEdge(fill0, fill1, line, shape_patch.VectorEdge(start, (x, y), control)))
            continue
        flags = reader.read_u(5)
        if flags == 0:
            break
        if flags & 0x01:
            bits = reader.read_u(5)
            x = reader.read_s(bits) if bits else 0
            y = reader.read_s(bits) if bits else 0
        if flags & 0x02:
            fill0 = reader.read_u(num_fill_bits) if num_fill_bits else 0
        if flags & 0x04:
            fill1 = reader.read_u(num_fill_bits) if num_fill_bits else 0
        if flags & 0x08:
            line = reader.read_u(num_line_bits) if num_line_bits else 0
        if flags & 0x10:
            raise ui_browser.PakError("Neue Styles in Morph-SHAPE werden nicht unterstützt")
    reader.align()
    return tuple(result), reader.byte_pos


def parse_morph_shape(payload: bytes, version: int) -> MorphShapeDef:
    if version not in (1, 2):
        raise ValueError("MorphShape-Version muss 1 oder 2 sein")
    _need(payload, 0, 3, "DefineMorphShape")
    character_id = _le16(payload, 0)
    start_bounds, off = ui_browser._read_rect(payload, 2)
    end_bounds, off = ui_browser._read_rect(payload, off)
    start_edge_bounds = start_bounds
    end_edge_bounds = end_bounds
    uses_non_scaling = uses_scaling = False
    if version == 2:
        start_edge_bounds, off = ui_browser._read_rect(payload, off)
        end_edge_bounds, off = ui_browser._read_rect(payload, off)
        _need(payload, off, 1, "DefineMorphShape2-Flags")
        flags = payload[off]
        off += 1
        uses_non_scaling = bool(flags & 0x02)
        uses_scaling = bool(flags & 0x01)
    offset = _le32(payload, off)
    offset_base = off + 4
    end_edges_pos = offset_base + offset
    if end_edges_pos < offset_base or end_edges_pos > len(payload):
        raise ui_browser.PakError("MorphShape-Offset ist ungültig")
    off = offset_base
    fills, off = _read_morph_fill_array(payload, off, version)
    lines, off = _read_morph_line_array(payload, off, version)
    if off > end_edges_pos:
        raise ui_browser.PakError("Morph-Styles überschreiten EndEdges-Offset")
    start_records, start_end = _read_shape_records(payload, off, end_edges_pos)
    warnings = []
    if start_end != end_edges_pos:
        if any(payload[start_end:end_edges_pos]):
            warnings.append(f"{end_edges_pos - start_end} nichtleere Bytes vor EndEdges")
    end_records, end_end = _read_shape_records(payload, end_edges_pos)
    if end_end > len(payload):
        raise ui_browser.PakError("Morph-Endkanten sind abgeschnitten")
    if len(start_records) != len(end_records):
        warnings.append(
            f"Kantenanzahl unterscheidet sich: {len(start_records)} / {len(end_records)}"
        )
    return MorphShapeDef(
        character_id=character_id, version=version,
        start_bounds=start_bounds, end_bounds=end_bounds,
        start_edge_bounds=start_edge_bounds, end_edge_bounds=end_edge_bounds,
        fills=fills, lines=lines, start_records=start_records, end_records=end_records,
        uses_non_scaling_strokes=uses_non_scaling,
        uses_scaling_strokes=uses_scaling,
        parse_warnings=tuple(warnings),
    )


def _lerp(left, right, t):
    return left + (right - left) * t


def _lerp_int(left, right, t):
    return int(round(_lerp(float(left), float(right), t)))


def _lerp_tuple(left, right, t):
    return tuple(_lerp(float(a), float(b), t) for a, b in zip(left, right))


def _lerp_color(left, right, t):
    return tuple(max(0, min(255, _lerp_int(a, b, t))) for a, b in zip(left, right))


def _lerp_matrix(left, right, t):
    if left is None:
        return right
    if right is None:
        return left
    return ui_browser.Affine(*(
        _lerp(a, b, t)
        for a, b in zip(
            (left.a, left.b, left.c, left.d, left.tx, left.ty),
            (right.a, right.b, right.c, right.d, right.tx, right.ty),
        )
    ))


def _interpolate_stops(start, end, t):
    if not start and not end:
        return ()
    count = max(len(start), len(end))
    values = []
    for index in range(count):
        left = start[min(index, len(start) - 1)] if start else end[min(index, len(end) - 1)]
        right = end[min(index, len(end) - 1)] if end else start[min(index, len(start) - 1)]
        values.append(shape_patch.GradientStop(
            max(0, min(255, _lerp_int(left.ratio, right.ratio, t))),
            _lerp_color(left.color, right.color, t),
        ))
    return tuple(values)


def interpolate_fill(pair: MorphFillPair, t: float):
    start, end = pair.start, pair.end
    kind = start.kind if start.kind == end.kind else start.kind
    return _enhanced_fill(
        kind,
        color=_lerp_color(start.color, end.color, t),
        matrix=_lerp_matrix(start.matrix, end.matrix, t),
        stops=_interpolate_stops(start.stops, end.stops, t),
        spread_mode=start.spread_mode,
        interpolation_mode=start.interpolation_mode,
        bitmap_id=start.bitmap_id or end.bitmap_id,
        fill_type=start.fill_type,
        focal_point=_lerp(
            float(getattr(start, "focal_point", 0.0)),
            float(getattr(end, "focal_point", 0.0)),
            t,
        ),
    )


def interpolate_line(pair: MorphLinePair, t: float):
    start, end = pair.start, pair.end
    fill = None
    if start.fill is not None and end.fill is not None:
        fill = interpolate_fill(MorphFillPair(start.fill, end.fill), t)
    return shape_patch.VectorLineStyle(
        width=max(0.0, _lerp(start.width, end.width, t)),
        color=_lerp_color(start.color, end.color, t),
        fill=fill,
        start_cap=start.start_cap,
        end_cap=start.end_cap,
        join_style=start.join_style,
        no_close=start.no_close,
    )


def _quadratic_control(edge):
    if edge.control is not None:
        return edge.control
    return (
        (edge.start[0] + edge.end[0]) / 2.0,
        (edge.start[1] + edge.end[1]) / 2.0,
    )


def interpolate_edge(start, end, t):
    start_point = tuple(_lerp_int(a, b, t) for a, b in zip(start.start, end.start))
    end_point = tuple(_lerp_int(a, b, t) for a, b in zip(start.end, end.end))
    if start.control is None and end.control is None:
        control = None
    else:
        left = _quadratic_control(start)
        right = _quadratic_control(end)
        control = tuple(_lerp_int(a, b, t) for a, b in zip(left, right))
    return shape_patch.VectorEdge(start_point, end_point, control)


def interpolate_morph(definition: MorphShapeDef, ratio: int):
    ratio = max(0, min(65535, int(ratio or 0)))
    t = ratio / 65535.0
    fills = [None]
    for value in definition.fills[1:]:
        fills.append(interpolate_fill(value, t) if value is not None else None)
    lines = [None]
    for value in definition.lines[1:]:
        lines.append(interpolate_line(value, t) if value is not None else None)

    fill_edges = {}
    line_edges = {}
    count = min(len(definition.start_records), len(definition.end_records))
    for index in range(count):
        start = definition.start_records[index]
        end = definition.end_records[index]
        edge = interpolate_edge(start.edge, end.edge, t)
        if start.fill0:
            fill_edges.setdefault(start.fill0, []).append(edge)
        if start.fill1:
            fill_edges.setdefault(start.fill1, []).append(edge.reversed())
        if start.line:
            line_edges.setdefault(start.line, []).append(edge)

    result = shape_patch.VectorShapeDef(
        character_id=definition.character_id,
        bounds=_lerp_tuple(definition.start_bounds, definition.end_bounds, t),
        edge_bounds=_lerp_tuple(definition.start_edge_bounds, definition.end_edge_bounds, t),
        fills=tuple(fills),
        lines=tuple(lines),
        fill_edges={key: tuple(value) for key, value in fill_edges.items()},
        line_edges={key: tuple(value) for key, value in line_edges.items()},
        uses_fill_winding_rule=False,
        unsupported_fill_types=(),
        record_count=count,
    )
    result.morph_ratio = ratio
    result.morph_source_character_id = definition.character_id
    result.morph_edge_mismatch = abs(
        len(definition.start_records) - len(definition.end_records)
    )
    return result


def spread_unit(value: float, mode: int) -> float:
    if mode == 1:
        value = value % 2.0
        return value if value <= 1.0 else 2.0 - value
    if mode == 2:
        return value % 1.0
    return max(0.0, min(1.0, value))


def gradient_parameter(kind: str, x: float, y: float, focal_point: float = 0.0) -> float:
    if kind == "linear_gradient":
        return (x + 1.0) * 0.5
    if kind == "radial_gradient":
        return math.hypot(x, y)
    if kind == "focal_gradient":
        focal = max(-0.99, min(0.99, float(focal_point)))
        dx = x - focal
        dy = y
        a = dx * dx + dy * dy
        if a <= 1e-15:
            return 0.0
        b = 2.0 * focal * dx
        c = focal * focal - 1.0
        discriminant = max(0.0, b * b - 4.0 * a * c)
        boundary = (-b + math.sqrt(discriminant)) / (2.0 * a)
        if boundary <= 1e-12:
            return 1.0
        return 1.0 / boundary
    return 0.5


def scale9_target_segments(total: int, first: int, last: int):
    total = max(1, int(total))
    first = max(0, int(first))
    last = max(0, int(last))
    fixed = first + last
    if fixed <= total:
        return first, total - fixed, last
    if fixed <= 0:
        return 0, total, 0
    left = max(0, min(total, int(round(total * first / fixed))))
    return left, 0, total - left


def scale9_inverse_coordinate(value: float, source_total: float, first: float, last: float,
                              target_total: float, flipped: bool = False) -> float:
    """Map one rendered Scale9 coordinate back to the natural sprite coordinate."""
    source_total = max(1e-9, float(source_total))
    target_total = max(1e-9, float(target_total))
    first = max(0.0, min(source_total, float(first)))
    last = max(0.0, min(source_total - first, float(last)))
    if flipped:
        value = target_total - float(value)
    value = max(0.0, min(target_total, float(value)))
    out_first, out_center, out_last = scale9_target_segments(
        int(round(target_total)), int(round(first)), int(round(last)),
    )
    src_center = max(0.0, source_total - first - last)
    if value <= out_first and out_first > 0:
        return value * first / out_first
    if value < out_first + out_center and out_center > 0:
        return first + (value - out_first) * src_center / out_center
    if out_last > 0:
        return source_total - last + (value - out_first - out_center) * last / out_last
    return first
