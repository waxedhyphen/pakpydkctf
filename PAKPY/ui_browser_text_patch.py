"""Render Tropical Freeze Scaleform EditText fields with embedded DefineFont3 outlines.

The game's static UI movies use DefineEditText with FontClass references into
``gfxfontlib.swf``.  This patch fixes the FontClass/FontHeight layout used by those
records, lazily decodes the four embedded DefineFont3 outline fonts, parses the small
HTML subset present in the UI corpus, and renders glyph contours into the normal
preview pipeline.  Dynamic fields without initial text remain identifiable by their
variable/instance placeholder until ActionScript/state overrides are available.

All changes are preview-only. GFX/SWF/TXTR/MSBT bytes and repacking are untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import html
import math
import re
import struct

import ui_browser
import ui_browser_shape_patch

try:
    from PIL import Image as PILImage, ImageChops, ImageDraw, ImageFont
except Exception:
    PILImage = None
    ImageChops = None
    ImageDraw = None
    ImageFont = None


TAG_DEFINE_FONT3 = 75
TAG_DEFINE_FONT_NAME = 88
_INSTALLED = False
_FONT_SOURCE_CACHE = {}


@dataclass
class RichEditTextDef:
    character_id: int
    bounds: tuple
    variable_name: str
    initial_text: str
    color: tuple
    font_height: float
    border: bool
    font_class: str = ""
    align: int = 0
    left_margin: float = 0.0
    right_margin: float = 0.0
    indent: float = 0.0
    leading: float = 0.0
    word_wrap: bool = False
    multiline: bool = False
    html: bool = False
    use_outlines: bool = False
    auto_size: bool = False
    no_select: bool = False
    read_only: bool = False
    max_length: int = 0


@dataclass(frozen=True)
class FontEdge:
    start: tuple[int, int]
    end: tuple[int, int]
    control: tuple[int, int] | None = None

    def reversed(self):
        return FontEdge(self.end, self.start, self.control)


@dataclass(frozen=True)
class FontGlyph:
    contours: tuple[tuple[FontEdge, ...], ...]
    bounds: tuple[int, int, int, int]


@dataclass
class EmbeddedFont:
    font_id: int
    name: str
    bold: bool
    italic: bool
    ascent: int
    descent: int
    leading: int
    codes: tuple[int, ...]
    advances: tuple[int, ...]
    glyph_data: tuple[bytes, ...]
    class_name: str = ""
    code_to_index: dict = field(default_factory=dict)
    glyph_cache: dict = field(default_factory=dict)
    mask_cache: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.code_to_index:
            self.code_to_index = {code: index for index, code in enumerate(self.codes)}

    def glyph_index(self, codepoint: int):
        index = self.code_to_index.get(codepoint)
        if index is None:
            index = self.code_to_index.get(0xFFFD)
        if index is None:
            index = self.code_to_index.get(ord("?"))
        return index

    def glyph(self, codepoint: int):
        index = self.glyph_index(codepoint)
        if index is None:
            return None, None
        glyph = self.glyph_cache.get(index)
        if glyph is None:
            glyph = parse_font_glyph(self.glyph_data[index])
            self.glyph_cache[index] = glyph
        return glyph, index

    def advance(self, codepoint: int, size: float):
        index = self.glyph_index(codepoint)
        if index is None or index >= len(self.advances):
            return max(1.0, float(size) * 0.55)
        return self.advances[index] * float(size) / 20480.0


@dataclass(frozen=True)
class TextRun:
    text: str
    size: float
    color: tuple[int, int, int, int]
    letter_spacing: float = 0.0
    kerning: bool = True


@dataclass(frozen=True)
class TextParagraph:
    runs: tuple[TextRun, ...]
    align: str = "left"


def _need(data: bytes, off: int, size: int, label: str):
    if off < 0 or off + size > len(data):
        raise ui_browser.PakError(f"{label} ist abgeschnitten")


def parse_edit_text(payload: bytes) -> RichEditTextDef:
    if len(payload) < 4:
        raise ui_browser.PakError("DefineEditText ist abgeschnitten")
    character_id = ui_browser._le16(payload, 0)
    bounds, p = ui_browser._read_rect(payload, 2)
    _need(payload, p, 2, "DefineEditText-Flags")
    flags1, flags2 = payload[p], payload[p + 1]
    p += 2
    has_text = bool(flags1 & 0x80)
    has_text_color = bool(flags1 & 0x04)
    has_max_length = bool(flags1 & 0x02)
    has_font = bool(flags1 & 0x01)
    has_font_class = bool(flags2 & 0x80)
    has_layout = bool(flags2 & 0x20)

    if has_font:
        _need(payload, p, 2, "DefineEditText-FontID")
        p += 2
    font_class = ""
    if has_font_class:
        font_class, p = ui_browser._read_c_string(payload, p)

    # Scaleform writes FontHeight for both FontID and FontClass text fields.  The
    # base parser only consumed it for FontID, shifting every later field by two
    # bytes in this corpus.
    font_height = 18.0
    if has_font or has_font_class:
        _need(payload, p, 2, "DefineEditText-FontHeight")
        font_height = ui_browser._le16(payload, p) / 20.0
        p += 2

    color = (255, 255, 255, 255)
    if has_text_color:
        _need(payload, p, 4, "DefineEditText-TextColor")
        color = tuple(payload[p:p + 4])
        p += 4

    max_length = 0
    if has_max_length:
        _need(payload, p, 2, "DefineEditText-MaxLength")
        max_length = ui_browser._le16(payload, p)
        p += 2

    align = 0
    left_margin = right_margin = indent = leading = 0.0
    if has_layout:
        _need(payload, p, 9, "DefineEditText-Layout")
        align = payload[p]
        left_margin = ui_browser._le16(payload, p + 1) / 20.0
        right_margin = ui_browser._le16(payload, p + 3) / 20.0
        indent = ui_browser._le16(payload, p + 5) / 20.0
        leading = struct.unpack_from("<h", payload, p + 7)[0] / 20.0
        p += 9

    variable_name, p = ui_browser._read_c_string(payload, p)
    initial_text = ""
    if has_text and p < len(payload):
        initial_text, p = ui_browser._read_c_string(payload, p)

    return RichEditTextDef(
        character_id=character_id,
        bounds=bounds,
        variable_name=variable_name,
        initial_text=initial_text,
        color=color,
        font_height=font_height,
        border=bool(flags2 & 0x08),
        font_class=font_class,
        align=align,
        left_margin=left_margin,
        right_margin=right_margin,
        indent=indent,
        leading=leading,
        word_wrap=bool(flags1 & 0x40),
        multiline=bool(flags1 & 0x20),
        html=bool(flags2 & 0x02),
        use_outlines=bool(flags2 & 0x01),
        auto_size=bool(flags2 & 0x40),
        no_select=bool(flags2 & 0x10),
        read_only=bool(flags1 & 0x08),
        max_length=max_length,
    )


def _join_edges(edges):
    remaining = list(edges)
    by_start = {}
    for index, edge in enumerate(remaining):
        by_start.setdefault(edge.start, []).append(index)
    used = set()
    contours = []
    for start_index, first in enumerate(remaining):
        if start_index in used:
            continue
        used.add(start_index)
        chain = [first]
        end = first.end
        while True:
            candidate = next((i for i in by_start.get(end, ()) if i not in used), None)
            if candidate is None:
                break
            used.add(candidate)
            edge = remaining[candidate]
            chain.append(edge)
            end = edge.end
            if end == chain[0].start:
                break
        contours.append(tuple(chain))
    return tuple(contours)


def parse_font_glyph(data: bytes) -> FontGlyph:
    if not data:
        return FontGlyph((), (0, 0, 0, 0))
    reader = ui_browser._BitReader(data, 0)
    num_fill_bits = reader.read_u(4)
    num_line_bits = reader.read_u(4)
    x = y = 0
    fill0 = fill1 = line = 0
    edges = []
    min_x = max_x = min_y = max_y = 0
    while True:
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
                control_dx, control_dy = reader.read_s(nbits), reader.read_s(nbits)
                anchor_dx, anchor_dy = reader.read_s(nbits), reader.read_s(nbits)
                control = (x + control_dx, y + control_dy)
                x, y = control[0] + anchor_dx, control[1] + anchor_dy
            edge = FontEdge(start, (x, y), control)
            if fill0:
                edges.append(edge)
            if fill1:
                edges.append(edge.reversed())
            for px, py in (start, (x, y), control or start):
                min_x, max_x = min(min_x, px), max(max_x, px)
                min_y, max_y = min(min_y, py), max(max_y, py)
            continue

        flags = reader.read_u(5)
        if flags == 0:
            break
        if flags & 0x01:
            move_bits = reader.read_u(5)
            x = reader.read_s(move_bits) if move_bits else 0
            y = reader.read_s(move_bits) if move_bits else 0
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
        if flags & 0x02:
            fill0 = reader.read_u(num_fill_bits) if num_fill_bits else 0
        if flags & 0x04:
            fill1 = reader.read_u(num_fill_bits) if num_fill_bits else 0
        if flags & 0x08:
            line = reader.read_u(num_line_bits) if num_line_bits else 0
        if flags & 0x10:
            # Glyph SHAPE records have no style arrays.  Preserve decoding of the
            # bit widths for malformed/generic files without reading nonexistent data.
            reader.align()
            num_fill_bits = reader.read_u(4)
            num_line_bits = reader.read_u(4)
    return FontGlyph(_join_edges(edges), (min_x, min_y, max_x, max_y))


def parse_define_font3(payload: bytes) -> EmbeddedFont:
    _need(payload, 0, 7, "DefineFont3")
    font_id = ui_browser._le16(payload, 0)
    flags = payload[2]
    name_len = payload[4]
    _need(payload, 5, name_len + 2, "DefineFont3-Name")
    name = payload[5:5 + name_len].decode("utf-8", "replace").rstrip("\x00")
    p = 5 + name_len
    num_glyphs = ui_browser._le16(payload, p)
    p += 2
    wide_offsets = bool(flags & 0x08)
    wide_codes = bool(flags & 0x04)
    has_layout = bool(flags & 0x80)
    offset_size = 4 if wide_offsets else 2
    table_start = p
    _need(payload, p, num_glyphs * offset_size + offset_size, "DefineFont3-OffsetTable")
    offsets = []
    for index in range(num_glyphs):
        offsets.append(int.from_bytes(payload[p:p + offset_size], "little"))
        p += offset_size
    code_table_offset = int.from_bytes(payload[p:p + offset_size], "little")
    code_pos = table_start + code_table_offset
    if code_pos > len(payload):
        raise ui_browser.PakError("DefineFont3-CodeTableOffset ist ungültig")

    glyph_data = []
    for index, relative in enumerate(offsets):
        start = table_start + relative
        end = table_start + (offsets[index + 1] if index + 1 < num_glyphs else code_table_offset)
        if start < table_start or end < start or end > len(payload):
            raise ui_browser.PakError(f"DefineFont3-Glyph {index} hat ungültige Grenzen")
        glyph_data.append(payload[start:end])

    code_size = 2 if wide_codes else 1
    _need(payload, code_pos, num_glyphs * code_size, "DefineFont3-CodeTable")
    codes = tuple(
        int.from_bytes(payload[code_pos + i * code_size:code_pos + (i + 1) * code_size], "little")
        for i in range(num_glyphs)
    )
    p = code_pos + num_glyphs * code_size
    ascent = 20480
    descent = 0
    leading = 0
    advances = tuple(10240 for _ in range(num_glyphs))
    if has_layout:
        _need(payload, p, 6 + num_glyphs * 2, "DefineFont3-Layout")
        ascent, descent, leading = struct.unpack_from("<hhh", payload, p)
        p += 6
        advances = struct.unpack_from("<" + "h" * num_glyphs, payload, p)
    return EmbeddedFont(
        font_id=font_id,
        name=name,
        bold=bool(flags & 0x01),
        italic=bool(flags & 0x02),
        ascent=ascent,
        descent=descent,
        leading=leading,
        codes=codes,
        advances=tuple(advances),
        glyph_data=tuple(glyph_data),
    )


def parse_font_movie(raw: bytes):
    data = ui_browser._decompress_swf(raw)
    _, p = ui_browser._read_rect(data, 8)
    tags = ui_browser._iter_tags(data, p + 4)
    fonts = {}
    symbol_classes = {}
    font_names = {}
    errors = []
    for code, payload in tags:
        try:
            if code == TAG_DEFINE_FONT3:
                font = parse_define_font3(payload)
                fonts[font.font_id] = font
            elif code == ui_browser.TAG_SYMBOL_CLASS:
                symbol_classes.update(ui_browser._parse_symbol_class(payload))
            elif code == TAG_DEFINE_FONT_NAME and len(payload) >= 2:
                font_id = ui_browser._le16(payload, 0)
                name, _ = ui_browser._read_c_string(payload, 2)
                font_names[font_id] = name
        except Exception as exc:
            errors.append(str(exc))
    registry = {}
    for font_id, font in fonts.items():
        if font_id in font_names:
            font.name = font_names[font_id].rstrip("\x00")
        class_name = symbol_classes.get(font_id, "")
        font.class_name = class_name
        if class_name:
            registry[class_name] = font
        registry.setdefault(font.name, font)
    return registry, tuple(fonts.values()), tuple(errors)


def _source_key(parsed, entry):
    return (
        str(parsed.get("path", "")),
        str(entry.get("uuid_hex", "")),
        str(entry.get("index", "")),
    )


def collect_embedded_fonts(parsed, require_store=None):
    registry = {}
    fonts = []
    errors = []
    sources = [parsed]
    if require_store is not None:
        for item in getattr(require_store, "required_paks", []):
            source = item.get("parsed")
            if source is not None:
                sources.append(source)
    for source in sources:
        entries = source.get("entries", [])
        candidates = [
            entry for entry in entries
            if ui_browser._normal_type(entry) == ui_browser.GFX_TYPE
            and "font" in ui_browser._entry_name(entry).lower()
        ]
        for entry in candidates:
            key = _source_key(source, entry)
            cached = _FONT_SOURCE_CACHE.get(key)
            if cached is None:
                try:
                    container = ui_browser.parse_gfx_asset(ui_browser.get_entry_asset(source, entry))
                    local_registry = {}
                    local_fonts = []
                    local_errors = []
                    for movie in container.movies:
                        movie_registry, movie_fonts, movie_errors = parse_font_movie(movie.data)
                        local_registry.update(movie_registry)
                        local_fonts.extend(movie_fonts)
                        local_errors.extend(movie_errors)
                    cached = (local_registry, tuple(local_fonts), tuple(local_errors))
                except Exception as exc:
                    cached = ({}, (), (f"{ui_browser._entry_name(entry)}: {exc}",))
                _FONT_SOURCE_CACHE[key] = cached
            local_registry, local_fonts, local_errors = cached
            for name, font in local_registry.items():
                registry.setdefault(name, font)
            fonts.extend(font for font in local_fonts if font not in fonts)
            errors.extend(local_errors)
    return registry, tuple(fonts), tuple(errors)


class _EditHTMLParser(HTMLParser):
    def __init__(self, default_size, default_color, default_align="left"):
        super().__init__(convert_charrefs=True)
        self.default_size = float(default_size)
        self.default_color = tuple(default_color)
        self.default_align = default_align
        self.paragraphs = []
        self.current_runs = []
        self.current_align = default_align
        self.style_stack = [(self.default_size, self.default_color, 0.0, True)]
        self.in_paragraph = False

    def _finish(self):
        if self.in_paragraph or self.current_runs:
            self.paragraphs.append(TextParagraph(tuple(self.current_runs), self.current_align))
        self.current_runs = []
        self.current_align = self.default_align
        self.in_paragraph = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "p":
            if self.in_paragraph or self.current_runs:
                self._finish()
            self.in_paragraph = True
            self.current_align = str(attrs.get("align", self.default_align)).lower()
        elif tag == "font":
            size, color, spacing, kerning = self.style_stack[-1]
            try:
                size = float(attrs.get("size", size))
            except Exception:
                pass
            raw_color = attrs.get("color")
            if raw_color:
                match = re.fullmatch(r"#?([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", raw_color.strip())
                if match:
                    value = match.group(1)
                    alpha = int(match.group(2), 16) if match.group(2) else color[3]
                    color = (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)
            try:
                spacing = float(attrs.get("letterspacing", attrs.get("letterSpacing", spacing)))
            except Exception:
                pass
            if "kerning" in attrs:
                kerning = str(attrs["kerning"]).strip() not in ("0", "false", "False")
            self.style_stack.append((size, color, spacing, kerning))
        elif tag == "br":
            self._finish()
            self.in_paragraph = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "font" and len(self.style_stack) > 1:
            self.style_stack.pop()
        elif tag == "p":
            self._finish()

    def handle_data(self, data):
        if not data:
            return
        size, color, spacing, kerning = self.style_stack[-1]
        self.current_runs.append(TextRun(data, size, color, spacing, kerning))

    def close(self):
        super().close()
        if self.in_paragraph or self.current_runs:
            self._finish()


def _align_name(value):
    if isinstance(value, str):
        return value.lower()
    return {0: "left", 1: "right", 2: "center", 3: "justify"}.get(int(value or 0), "left")


def parse_text_paragraphs(definition: RichEditTextDef, placeholder=True):
    text = definition.initial_text
    placeholder_used = False
    if not text and placeholder:
        label = definition.variable_name.strip() if definition.variable_name else "Text"
        text = f"[{label}]"
        placeholder_used = True
    default_align = _align_name(definition.align)
    if definition.html and "<" in text:
        parser = _EditHTMLParser(definition.font_height, definition.color, default_align)
        try:
            parser.feed(text)
            parser.close()
            paragraphs = parser.paragraphs
        except Exception:
            paragraphs = []
        if paragraphs:
            return tuple(paragraphs), placeholder_used
    plain = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = plain.splitlines() or [plain]
    return tuple(
        TextParagraph((TextRun(line, definition.font_height, definition.color),), default_align)
        for line in lines
    ), placeholder_used


def _edge_points(edge: FontEdge, scale: float, supersample: int):
    x0, y0 = edge.start
    x1, y1 = edge.end
    if edge.control is None:
        return [(x0 * scale, y0 * scale), (x1 * scale, y1 * scale)]
    cx, cy = edge.control
    estimate = (math.hypot(cx - x0, cy - y0) + math.hypot(x1 - cx, y1 - cy)) * scale
    steps = max(3, min(40, int(math.ceil(estimate * supersample / 3.0))))
    result = []
    for index in range(steps + 1):
        t = index / float(steps)
        inv = 1.0 - t
        result.append((
            (inv * inv * x0 + 2.0 * inv * t * cx + t * t * x1) * scale,
            (inv * inv * y0 + 2.0 * inv * t * cy + t * t * y1) * scale,
        ))
    return result


def rasterize_glyph(font: EmbeddedFont, codepoint: int, size: float, supersample=2):
    key = (int(codepoint), int(round(float(size) * 64.0)), int(supersample))
    cached = font.mask_cache.get(key)
    if cached is not None:
        return cached
    glyph, index = font.glyph(codepoint)
    if glyph is None or not glyph.contours:
        result = (None, (0.0, 0.0), index)
        font.mask_cache[key] = result
        return result
    scale = float(size) / 20480.0
    min_x, min_y, max_x, max_y = glyph.bounds
    pad = 2.0
    origin_x = math.floor(min_x * scale - pad)
    origin_y = math.floor(min_y * scale - pad)
    width = max(1, int(math.ceil(max_x * scale + pad - origin_x)))
    height = max(1, int(math.ceil(max_y * scale + pad - origin_y)))
    high_size = (width * supersample, height * supersample)
    if PILImage is None or ImageDraw is None:
        return None, (origin_x, origin_y), index
    mask = PILImage.new("1", high_size, 0)
    for contour in glyph.contours:
        points = []
        for edge_index, edge in enumerate(contour):
            sampled = _edge_points(edge, scale, supersample)
            if edge_index:
                sampled = sampled[1:]
            points.extend(sampled)
        if len(points) < 3:
            continue
        polygon = [
            ((x - origin_x) * supersample, (y - origin_y) * supersample)
            for x, y in points
        ]
        contour_mask = PILImage.new("1", high_size, 0)
        ImageDraw.Draw(contour_mask).polygon(polygon, fill=1)
        if ImageChops is not None:
            mask = ImageChops.logical_xor(mask, contour_mask)
        else:
            ImageDraw.Draw(mask).polygon(polygon, fill=1)
    mask = mask.convert("L")
    if supersample > 1:
        resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS")
        mask = mask.resize((width, height), resampling)
    result = (mask, (float(origin_x), float(origin_y)), index)
    font.mask_cache[key] = result
    return result


def _measure_run(font, run: TextRun):
    if font is None:
        return sum(max(1.0, run.size * 0.55) + run.letter_spacing for _ in run.text)
    total = 0.0
    for index, char in enumerate(run.text):
        total += font.advance(ord(char), run.size)
        if index + 1 < len(run.text):
            total += run.letter_spacing
    return total


def _line_metrics(font, runs, default_size, extra_leading):
    sizes = [run.size for run in runs] or [default_size]
    size = max(sizes)
    if font is None:
        ascent = size * 0.82
        descent = size * 0.22
        leading = max(0.0, extra_leading)
    else:
        scale = size / 20480.0
        ascent = max(1.0, font.ascent * scale)
        descent = max(0.0, font.descent * scale)
        leading = max(0.0, font.leading * scale + extra_leading)
    return ascent, descent, leading


def _fallback_font(size):
    if ImageFont is None:
        return None
    try:
        return ImageFont.truetype("DejaVuSans.ttf", max(1, int(round(size))))
    except Exception:
        return ImageFont.load_default()


def _draw_fallback_run(layer, run, x, baseline, stats):
    font = _fallback_font(run.size)
    if font is None:
        return x
    draw = ImageDraw.Draw(layer, "RGBA")
    try:
        bbox = font.getbbox(run.text)
        y = baseline - (bbox[3] - bbox[1])
    except Exception:
        y = baseline - run.size
    draw.text((x, y), run.text, font=font, fill=run.color)
    try:
        width = draw.textlength(run.text, font=font)
    except Exception:
        width = len(run.text) * run.size * 0.55
    if stats is not None:
        stats.fallback_text_runs = getattr(stats, "fallback_text_runs", 0) + 1
    return x + width


def render_edit_text_layer(definition, font, stats=None, show_placeholder=True):
    xmin, ymin, xmax, ymax = definition.bounds
    width = max(1, int(math.ceil(xmax - xmin)))
    height = max(1, int(math.ceil(ymax - ymin)))
    layer = PILImage.new("RGBA", (width, height), (0, 0, 0, 0))
    paragraphs, placeholder_used = parse_text_paragraphs(definition, show_placeholder)
    if placeholder_used and stats is not None:
        stats.dynamic_text_placeholders = getattr(stats, "dynamic_text_placeholders", 0) + 1
    y = 0.0
    available_width = max(1.0, width - definition.left_margin - definition.right_margin)
    for line_index, paragraph in enumerate(paragraphs):
        runs = paragraph.runs
        ascent, descent, leading = _line_metrics(font, runs, definition.font_height, definition.leading)
        baseline = y + ascent
        line_width = sum(_measure_run(font, run) for run in runs)
        align = paragraph.align
        indent = definition.indent if line_index == 0 else 0.0
        if align == "center":
            x = definition.left_margin + max(0.0, (available_width - line_width) * 0.5)
        elif align == "right":
            x = definition.left_margin + max(0.0, available_width - line_width)
        else:
            x = definition.left_margin + indent
        for run in runs:
            if font is None:
                x = _draw_fallback_run(layer, run, x, baseline, stats)
                continue
            for char_index, char in enumerate(run.text):
                mask, offset, glyph_index = rasterize_glyph(font, ord(char), run.size)
                if mask is not None:
                    glyph_layer = PILImage.new("RGBA", mask.size, run.color)
                    if run.color[3] != 255:
                        mask = mask.point(lambda value, alpha=run.color[3]: (value * alpha + 127) // 255)
                    glyph_layer.putalpha(mask)
                    layer.alpha_composite(glyph_layer, (int(round(x + offset[0])), int(round(baseline + offset[1]))))
                    if stats is not None:
                        stats.font_glyphs_drawn = getattr(stats, "font_glyphs_drawn", 0) + 1
                elif not char.isspace() and stats is not None:
                    stats.missing_font_glyphs = getattr(stats, "missing_font_glyphs", 0) + 1
                x += font.advance(ord(char), run.size)
                if char_index + 1 < len(run.text):
                    x += run.letter_spacing
        y += ascent + descent + leading
        if y > height + max(4.0, definition.font_height):
            break
    if definition.border:
        ImageDraw.Draw(layer, "RGBA").rectangle((0, 0, width - 1, height - 1), outline=(150, 210, 255, 130), width=1)
    return layer


def _font_for(renderer, definition):
    registry = getattr(renderer.resolver, "fonts_by_class", {})
    font = registry.get(definition.font_class)
    if font is None and definition.font_class:
        short = definition.font_class.rsplit("::", 1)[-1]
        font = registry.get(short)
    return font


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    ui_browser.EditTextDef = RichEditTextDef
    ui_browser._parse_edit_text = parse_edit_text

    original_resolver_init = ui_browser.TextureResolver.__init__

    def resolver_init(self, *args, **kwargs):
        original_resolver_init(self, *args, **kwargs)
        parsed = args[0] if args else kwargs.get("parsed")
        require_store = args[1] if len(args) > 1 else kwargs.get("require_store")
        try:
            registry, fonts, errors = collect_embedded_fonts(parsed, require_store)
        except Exception as exc:
            registry, fonts, errors = {}, (), (str(exc),)
        self.fonts_by_class = registry
        self.embedded_fonts = fonts
        self.font_parse_errors = errors

    ui_browser.TextureResolver.__init__ = resolver_init

    def draw_edit_text(self, canvas, definition, matrix, color):
        self.stats.text_fields_drawn += 1
        font = _font_for(self, definition)
        layer = render_edit_text_layer(definition, font, self.stats, show_placeholder=True)
        if getattr(self.movie, "preview_rotate_180", False):
            transpose = getattr(PILImage, "Transpose", PILImage)
            layer = layer.transpose(getattr(transpose, "FLIP_TOP_BOTTOM"))
        layer = self._apply_color(layer, color)
        xmin, ymin, xmax, ymax = definition.bounds
        local = ui_browser.Affine(1, 0, 0, 1, xmin, ymin)
        ui_browser_shape_patch._draw_transformed_image(self, canvas, layer, matrix.then(local))
        if font is not None:
            self.stats.embedded_text_fields = getattr(self.stats, "embedded_text_fields", 0) + 1
            used = getattr(self.stats, "font_classes", None)
            if used is None:
                self.stats.font_classes = {}
                used = self.stats.font_classes
            name = definition.font_class or font.name
            used[name] = used.get(name, 0) + 1
        else:
            self.stats.missing_font_fields = getattr(self.stats, "missing_font_fields", 0) + 1
        if self.show_bounds:
            self._draw_transformed_box(canvas, definition.bounds, matrix, definition.variable_name or definition.font_class)

    ui_browser.UIRenderer._draw_edit_text = draw_edit_text

    original_format_info = ui_browser.UIBrowser._format_info

    def format_info(self, stats):
        text = original_format_info(self, stats)
        embedded = getattr(stats, "embedded_text_fields", 0)
        missing_fields = getattr(stats, "missing_font_fields", 0)
        glyphs = getattr(stats, "font_glyphs_drawn", 0)
        missing_glyphs = getattr(stats, "missing_font_glyphs", 0)
        placeholders = getattr(stats, "dynamic_text_placeholders", 0)
        classes = getattr(stats, "font_classes", {})
        resolver = getattr(self, "_current_resolver", None)
        fonts = tuple(getattr(resolver, "embedded_fonts", ()) or ()) if resolver is not None else ()
        errors = tuple(getattr(resolver, "font_parse_errors", ()) or ()) if resolver is not None else ()
        if not any((embedded, missing_fields, glyphs, missing_glyphs, placeholders, classes, fonts, errors)):
            return text
        lines = ["", "Fonts und Text:"]
        lines.append(f"- Eingebettete Fonts geladen: {len(fonts)}")
        lines.append(f"- EditText mit Outline-Font: {embedded}")
        lines.append(f"- Glyphen gezeichnet: {glyphs}")
        if placeholders:
            lines.append(f"- Dynamische Platzhalter: {placeholders}")
        if missing_fields:
            lines.append(f"- Textfelder ohne Fontauflösung: {missing_fields}")
        if missing_glyphs:
            lines.append(f"- Fehlende Glyphen: {missing_glyphs}")
        if classes:
            lines.append("- Verwendete Fontklassen:")
            for name, count in sorted(classes.items()):
                lines.append(f"  - {name}: {count}")
        if fonts:
            lines.append("- Fontbibliothek:")
            for font in fonts:
                label = font.class_name or font.name
                lines.append(f"  - {label}: {len(font.codes)} Glyphen")
        if errors:
            lines.append("- Font-Parserfehler:")
            lines.extend(f"  - {error}" for error in errors[:20])
        return text + "\n" + "\n".join(lines)

    ui_browser.UIBrowser._format_info = format_info
    ui_browser.RichEditTextDef = RichEditTextDef
    ui_browser.EmbeddedFont = EmbeddedFont
    ui_browser.parse_define_font3 = parse_define_font3
    ui_browser.parse_text_paragraphs = parse_text_paragraphs
