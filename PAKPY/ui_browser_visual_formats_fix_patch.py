"""Correct JPEG4 alpha offsets and enforce the MorphShape EndEdges boundary."""
from __future__ import annotations

import io

import ui_browser
import ui_browser_visual_formats as visual

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


_INSTALLED = False


def decode_jpeg_bitmap(payload: bytes, source_tag: int, jpeg_tables: bytes = b""):
    visual._need(payload, 0, 3, "DefineBitsJPEG")
    character_id = visual._le16(payload, 0)
    if source_tag == visual.TAG_DEFINE_BITS:
        image = visual._open_jpeg(jpeg_tables + payload[2:])
        return visual.EmbeddedBitmapDef(character_id, image, source_tag, "jpeg-tables")
    if source_tag == visual.TAG_DEFINE_BITS_JPEG2:
        image = visual._open_jpeg(payload[2:])
        return visual.EmbeddedBitmapDef(character_id, image, source_tag, "jpeg2")

    visual._need(payload, 2, 4, "AlphaDataOffset")
    alpha_offset = visual._le32(payload, 2)
    jpeg_start = 6
    if source_tag == visual.TAG_DEFINE_BITS_JPEG4:
        visual._need(payload, 6, 2, "DeblockParam")
        jpeg_start = 8
    # AlphaDataOffset is the count of bytes in ImageData. JPEG4's ImageData
    # starts after its additional DeblockParam field.
    alpha_start = jpeg_start + alpha_offset
    if alpha_start < jpeg_start or alpha_start > len(payload):
        raise ui_browser.PakError("JPEG-AlphaDataOffset ist ungültig")
    image = visual._open_jpeg(payload[jpeg_start:alpha_start])
    expected = image.width * image.height
    alpha = visual._bounded_zlib(payload[alpha_start:], expected)[:expected]
    image.putalpha(PILImage.frombytes("L", image.size, alpha))
    return visual.EmbeddedBitmapDef(
        character_id, image, source_tag,
        "jpeg4-alpha" if source_tag == visual.TAG_DEFINE_BITS_JPEG4 else "jpeg3-alpha",
    )


def read_shape_records(data: bytes, off: int, limit_end: int | None = None):
    reader = ui_browser._BitReader(data, off)
    num_fill_bits = reader.read_u(4)
    num_line_bits = reader.read_u(4)
    x = y = 0
    fill0 = fill1 = line = 0
    result = []
    while True:
        if len(result) > visual.MAX_MORPH_RECORDS:
            raise ui_browser.PakError("Morph-Kanten überschreiten das Limit")
        if limit_end is not None and reader.byte_pos >= limit_end:
            raise ui_browser.PakError("Morph-Startkanten enden nicht vor EndEdges")
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
            result.append(visual.MorphStyledEdge(
                fill0, fill1, line,
                visual.shape_patch.VectorEdge(start, (x, y), control),
            ))
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
    end = reader.byte_pos
    if limit_end is not None and end > limit_end:
        raise ui_browser.PakError("Morph-Startkanten überschreiten EndEdges-Offset")
    return tuple(result), end


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    visual.decode_jpeg_bitmap = decode_jpeg_bitmap
    visual._read_shape_records = read_shape_records
