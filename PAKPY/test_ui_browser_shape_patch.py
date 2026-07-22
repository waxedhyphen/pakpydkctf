import unittest

import ui_browser
from ui_browser_shape_patch import (
    VectorShapeDef,
    _rasterize_shape,
    install,
    parse_vector_shape,
)

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


def _straight_edge(dx, dy):
    nbits = max(2, max(abs(dx), abs(dy)).bit_length() + 1)
    values = [(1, 1), (1, 1), (nbits - 2, 4)]
    if dx and dy:
        values += [(1, 1), (_signed(dx, nbits), nbits), (_signed(dy, nbits), nbits)]
    elif dy:
        values += [(0, 1), (1, 1), (_signed(dy, nbits), nbits)]
    else:
        values += [(0, 1), (0, 1), (_signed(dx, nbits), nbits)]
    return values


def _solid_square_shape3():
    payload = (7).to_bytes(2, "little")
    payload += _rect(0, 2000, 0, 2000)
    payload += bytes([1, 0x00, 255, 0, 0, 255])
    payload += bytes([0])
    records = [
        (1, 4), (0, 4),
        (0, 1), (0b00101, 5),
        (1, 5), (0, 1), (0, 1), (1, 1),
    ]
    records += _straight_edge(2000, 0)
    records += _straight_edge(0, 2000)
    records += _straight_edge(-2000, 0)
    records += _straight_edge(0, -2000)
    records += [(0, 1), (0, 5)]
    payload += _bits(records)
    return payload


class UIBrowserShapePatchTests(unittest.TestCase):
    def test_define_shape3_solid_square_decodes(self):
        shape = parse_vector_shape(_solid_square_shape3(), 3)
        self.assertIsInstance(shape, VectorShapeDef)
        self.assertEqual(shape.character_id, 7)
        self.assertEqual(shape.fills[1].kind, "solid")
        self.assertEqual(shape.fills[1].color, (255, 0, 0, 255))
        self.assertEqual(len(shape.fill_edges[1]), 4)
        self.assertEqual(shape.unsupported_fill_types, ())

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_solid_shape_rasterizes_with_transparent_outside(self):
        shape = parse_vector_shape(_solid_square_shape3(), 3)
        image, origin = _rasterize_shape(shape, supersample=2)
        center = (int(50 - origin[0]), int(50 - origin[1]))
        self.assertGreater(image.getpixel(center)[3], 240)
        self.assertGreater(image.getpixel(center)[0], 240)
        self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_patch_replaces_shape_definition_in_parsed_movie(self):
        install()
        shape_payload = _solid_square_shape3()
        tag = ((ui_browser.TAG_DEFINE_SHAPE3 << 6) | 63).to_bytes(2, "little")
        tag += len(shape_payload).to_bytes(4, "little") + shape_payload
        tag += (0).to_bytes(2, "little")
        body = _rect(0, 2560, 0, 1440)
        body += (60 * 256).to_bytes(2, "little") + (1).to_bytes(2, "little") + tag
        raw = b"FWS" + bytes([25]) + (8 + len(body)).to_bytes(4, "little") + body
        movie = ui_browser.parse_swf_movie(raw)
        self.assertIsInstance(movie.definitions[7], VectorShapeDef)
        self.assertEqual(movie.vector_shape_count, 1)
        self.assertEqual(movie.vector_shape_errors, ())


if __name__ == "__main__":
    unittest.main()
