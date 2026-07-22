import struct
import unittest

import ui_browser
import ui_browser_text_patch as patch

try:
    from PIL import Image
except Exception:
    Image = None


def _bits(values):
    text = "".join(format(value, f"0{count}b") for value, count in values)
    text += "0" * ((8 - len(text) % 8) % 8)
    return bytes(int(text[index:index + 8], 2) for index in range(0, len(text), 8))


def _signed(value, count):
    return value if value >= 0 else (1 << count) + value


def _rect(xmin, xmax, ymin, ymax):
    nbits = max(1, max(abs(xmin), abs(xmax), abs(ymin), abs(ymax)).bit_length() + 1)
    return _bits([
        (nbits, 5),
        (_signed(xmin, nbits), nbits),
        (_signed(xmax, nbits), nbits),
        (_signed(ymin, nbits), nbits),
        (_signed(ymax, nbits), nbits),
    ])


class UIBrowserTextPatchTests(unittest.TestCase):
    def test_font_class_edit_text_consumes_font_height(self):
        flags1 = 0x80 | 0x04 | 0x08
        flags2 = 0x80 | 0x20 | 0x02 | 0x01
        payload = struct.pack("<H", 7) + _rect(0, 4000, 0, 1000)
        payload += bytes([flags1, flags2])
        payload += b"$NormalFont\x00" + struct.pack("<H", 24 * 20)
        payload += bytes((0x60, 0x3B, 0x14, 0xFF))
        payload += bytes([2]) + struct.pack("<HHHh", 20, 40, 60, -20)
        payload += b"scoreText\x00"
        payload += b'<p align="center"><font size="24" color="#ffffff">100</font></p>\x00'
        item = patch.parse_edit_text(payload)
        self.assertEqual(item.font_class, "$NormalFont")
        self.assertEqual(item.font_height, 24.0)
        self.assertEqual(item.variable_name, "scoreText")
        self.assertEqual(item.align, 2)
        self.assertEqual(item.left_margin, 1.0)
        self.assertEqual(item.leading, -1.0)

    def test_define_font3_empty_metadata(self):
        name = b"Test Font\x00"
        payload = struct.pack("<HBBB", 3, 0x8C, 0, len(name)) + name
        payload += struct.pack("<H", 0)
        payload += struct.pack("<I", 4)
        payload += struct.pack("<hhh", 20480, 4096, 20)
        font = patch.parse_define_font3(payload)
        self.assertEqual(font.font_id, 3)
        self.assertEqual(font.name, "Test Font")
        self.assertEqual(font.ascent, 20480)
        self.assertEqual(font.codes, ())

    def test_html_paragraph_style(self):
        item = patch.RichEditTextDef(
            1, (0, 0, 200, 80), "title", "",
            (255, 255, 255, 255), 24.0, False,
            font_class="$TitleFont", align=0, html=True,
        )
        item.initial_text = (
            '<p align="center"><font size="32" color="#663300" '
            'letterSpacing="1.5" kerning="1">MENU</font></p>'
        )
        paragraphs, placeholder = patch.parse_text_paragraphs(item)
        self.assertFalse(placeholder)
        self.assertEqual(paragraphs[0].align, "center")
        self.assertEqual(paragraphs[0].runs[0].size, 32.0)
        self.assertEqual(paragraphs[0].runs[0].color, (0x66, 0x33, 0x00, 0xFF))
        self.assertEqual(paragraphs[0].runs[0].letter_spacing, 1.5)

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_embedded_outline_glyph_renders(self):
        contour = (
            patch.FontEdge((0, -16000), (10000, -16000)),
            patch.FontEdge((10000, -16000), (10000, 0)),
            patch.FontEdge((10000, 0), (0, 0)),
            patch.FontEdge((0, 0), (0, -16000)),
        )
        font = patch.EmbeddedFont(
            font_id=1,
            name="Test",
            bold=False,
            italic=False,
            ascent=18000,
            descent=2000,
            leading=0,
            codes=(32, 65),
            advances=(6000, 12000),
            glyph_data=(b"", b""),
            class_name="$NormalFont",
        )
        font.glyph_cache[1] = patch.FontGlyph((contour,), (0, -16000, 10000, 0))
        item = patch.RichEditTextDef(
            1, (0, 0, 120, 50), "label", "A",
            (255, 255, 255, 255), 32.0, False,
            font_class="$NormalFont",
        )
        image = patch.render_edit_text_layer(item, font)
        self.assertIsNotNone(image.getbbox())
        self.assertGreater(image.getchannel("A").getextrema()[1], 0)

    def test_empty_dynamic_field_keeps_state_placeholder(self):
        item = patch.RichEditTextDef(
            1, (0, 0, 120, 40), "livesText", "",
            (255, 255, 255, 255), 24.0, False,
        )
        paragraphs, placeholder = patch.parse_text_paragraphs(item)
        self.assertTrue(placeholder)
        self.assertEqual(paragraphs[0].runs[0].text, "[livesText]")


if __name__ == "__main__":
    unittest.main()
