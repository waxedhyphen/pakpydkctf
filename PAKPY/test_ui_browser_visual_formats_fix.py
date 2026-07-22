import io
import zlib
import unittest

from PIL import Image

import ui_browser_visual_formats as visual
import ui_browser_visual_formats_fix_patch as fix


class VisualFormatFixTests(unittest.TestCase):
    def setUp(self):
        fix.install()

    def test_jpeg4_alpha_offset_starts_after_deblock_parameter(self):
        image = Image.new("RGB", (2, 1), (20, 40, 60))
        stream = io.BytesIO()
        image.save(stream, format="JPEG")
        jpeg = stream.getvalue()
        alpha = bytes((17, 231))
        payload = (
            (9).to_bytes(2, "little")
            + len(jpeg).to_bytes(4, "little")
            + (0).to_bytes(2, "little")
            + jpeg
            + zlib.compress(alpha)
        )
        value = visual.decode_jpeg_bitmap(
            payload, visual.TAG_DEFINE_BITS_JPEG4,
        )
        self.assertEqual(value.character_id, 9)
        self.assertEqual(value.image.size, (2, 1))
        self.assertEqual(value.image.getchannel("A").tobytes(), alpha)

    def test_morph_start_records_cannot_cross_end_edges_offset(self):
        # One byte can hold NumFillBits/NumLineBits and an EndShapeRecord. A zero
        # boundary must reject it before the reader consumes EndEdges bytes.
        with self.assertRaises(Exception):
            fix.read_shape_records(b"\x00", 0, 0)


if __name__ == "__main__":
    unittest.main()
