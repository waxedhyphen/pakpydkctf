import math
import struct
import unittest
from types import SimpleNamespace

import ui_browser_filter_patch as patch

try:
    from PIL import Image
except Exception:
    Image = None


def _fixed(value):
    return struct.pack("<i", int(round(float(value) * 65536.0)))


def _fixed8(value):
    return struct.pack("<H", int(round(float(value) * 256.0)))


def _record(filter_id, name, payload):
    return SimpleNamespace(filter_id=filter_id, name=name, raw=bytes([filter_id]) + payload)


class UIBrowserFilterPatchTests(unittest.TestCase):
    def test_glow_record(self):
        record = _record(
            2, "Glow",
            bytes((255, 64, 0, 200))
            + _fixed(6.0) + _fixed(4.0) + _fixed8(1.5)
            + bytes([0x20 | 3]),
        )
        item = patch.parse_filter_record(record)
        self.assertEqual(item.color, (255, 64, 0, 200))
        self.assertEqual((item.blur_x, item.blur_y), (6.0, 4.0))
        self.assertAlmostEqual(item.strength, 1.5)
        self.assertTrue(item.composite_source)
        self.assertEqual(item.passes, 3)

    def test_drop_shadow_record(self):
        record = _record(
            0, "DropShadow",
            bytes((0, 0, 0, 180))
            + _fixed(4.0) + _fixed(4.0)
            + _fixed(math.pi / 4.0) + _fixed(3.0)
            + _fixed8(1.0) + bytes([0x21]),
        )
        item = patch.parse_filter_record(record)
        self.assertAlmostEqual(item.angle, math.pi / 4.0, places=4)
        self.assertAlmostEqual(item.distance, 3.0)
        self.assertEqual(item.passes, 1)

    def test_blur_pass_bits(self):
        record = _record(1, "Blur", _fixed(8.0) + _fixed(2.0) + bytes([4 << 3]))
        item = patch.parse_filter_record(record)
        self.assertEqual(item.passes, 4)
        self.assertFalse(item.composite_source)

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_glow_expands_alpha_and_keeps_source(self):
        image = Image.new("RGBA", (31, 31), (0, 0, 0, 0))
        image.putpixel((15, 15), (255, 255, 255, 255))
        record = _record(
            2, "Glow",
            bytes((255, 0, 0, 255))
            + _fixed(4.0) + _fixed(4.0) + _fixed8(1.0)
            + bytes([0x21]),
        )
        result = patch.apply_filter_chain(image, [record])
        self.assertEqual(result.getpixel((15, 15)), (255, 255, 255, 255))
        self.assertGreater(result.getpixel((14, 15))[3], 0)

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_drop_shadow_uses_angle_and_distance(self):
        image = Image.new("RGBA", (15, 15), (0, 0, 0, 0))
        image.putpixel((5, 5), (255, 255, 255, 255))
        record = _record(
            0, "DropShadow",
            bytes((0, 0, 0, 255))
            + _fixed(0.0) + _fixed(0.0)
            + _fixed(0.0) + _fixed(3.0)
            + _fixed8(1.0) + bytes([0x21]),
        )
        result = patch.apply_filter_chain(image, [record])
        self.assertEqual(result.getpixel((5, 5)), (255, 255, 255, 255))
        self.assertEqual(result.getpixel((8, 5)), (0, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
