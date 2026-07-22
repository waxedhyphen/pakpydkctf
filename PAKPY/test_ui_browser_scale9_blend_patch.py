import struct
import unittest

import ui_browser
import ui_browser_shape_patch
import ui_browser_scale9_blend_patch as patch

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
        (nbits, 5), (_signed(xmin, nbits), nbits), (_signed(xmax, nbits), nbits),
        (_signed(ymin, nbits), nbits), (_signed(ymax, nbits), nbits),
    ])


def _matrix(scale_x=1.0, scale_y=1.0, tx=0, ty=0):
    values = []
    has_scale = abs(scale_x - 1.0) > 1e-8 or abs(scale_y - 1.0) > 1e-8
    values.append((1 if has_scale else 0, 1))
    if has_scale:
        sx = int(round(scale_x * 65536))
        sy = int(round(scale_y * 65536))
        n = max(abs(sx), abs(sy)).bit_length() + 1
        values.extend([(n, 5), (_signed(sx, n), n), (_signed(sy, n), n)])
    values.append((0, 1))
    twx, twy = int(tx * 20), int(ty * 20)
    n = max(abs(twx), abs(twy)).bit_length() + 1 if (twx or twy) else 0
    values.append((n, 5))
    if n:
        values.extend([(_signed(twx, n), n), (_signed(twy, n), n)])
    return _bits(values)


class Scale9BlendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ui_browser_shape_patch.install()
        patch.install()

    def test_scaling_grid_parser(self):
        item = patch.parse_scaling_grid(struct.pack("<H", 7) + _rect(20, 80, 30, 90))
        self.assertEqual(item.character_id, 7)
        self.assertEqual(item.rect, (1.0, 1.5, 4.0, 4.5))

    def test_place_object3_reads_filter_blend_and_visibility(self):
        payload = bytes([0x06, 0x23]) + struct.pack("<H", 3) + struct.pack("<H", 9)
        payload += _matrix()
        payload += bytes([1, 1]) + b"\x00" * 9
        payload += bytes([3, 0])
        command = patch.parse_place_object3(payload)
        self.assertEqual(command.character_id, 9)
        self.assertEqual(command.blend_mode, 3)
        self.assertFalse(command.visible)
        self.assertEqual(command.filters[0].name, "Blur")
        self.assertEqual(command.place_object3_end, len(payload))

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_scale9_keeps_corner_size(self):
        image = Image.new("RGBA", (9, 9), (0, 255, 0, 255))
        for y in range(3):
            for x in range(3):
                image.putpixel((x, y), (255, 0, 0, 255))
        result = patch.scale9_resize(image, (0, 0, 9, 9), (3, 3, 6, 6), 2.0, 2.0)
        self.assertEqual(result.size, (18, 18))
        self.assertEqual(result.getpixel((2, 2)), (255, 0, 0, 255))
        self.assertEqual(result.getpixel((4, 2)), (0, 255, 0, 255))

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_multiply_blend(self):
        destination = Image.new("RGBA", (1, 1), (200, 100, 50, 255))
        source = Image.new("RGBA", (1, 1), (128, 128, 128, 255))
        patch.blend_rgba(destination, source, 3)
        self.assertEqual(destination.getpixel((0, 0)), (100, 50, 25, 255))

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_alpha_blend_masks_destination(self):
        destination = Image.new("RGBA", (1, 1), (10, 20, 30, 200))
        source = Image.new("RGBA", (1, 1), (255, 0, 0, 128))
        patch.blend_rgba(destination, source, 11)
        self.assertEqual(destination.getpixel((0, 0)), (10, 20, 30, 100))


if __name__ == "__main__":
    unittest.main()
