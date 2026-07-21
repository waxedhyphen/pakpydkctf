import unittest

from preview_orientation_patch import (
    is_zlib_swf,
    needs_txtr_preview_rotation,
    rotate_preview_image,
)

try:
    from PIL import Image
except Exception:
    Image = None


class PreviewOrientationPatchTests(unittest.TestCase):
    def test_only_zlib_txtr_previews_rotate(self):
        self.assertTrue(needs_txtr_preview_rotation({"gpu_codec": "zlib"}))
        self.assertTrue(needs_txtr_preview_rotation({"gpu_codec": " ZLIB "}))
        self.assertFalse(needs_txtr_preview_rotation({"gpu_codec": "none"}))
        self.assertFalse(needs_txtr_preview_rotation({}))

    def test_only_cws_movies_use_zlib_frame_rotation(self):
        self.assertTrue(is_zlib_swf(b"CWS\x19\x00\x00\x00\x00"))
        self.assertFalse(is_zlib_swf(b"FWS\x19\x00\x00\x00\x00"))
        self.assertFalse(is_zlib_swf(b"GFX\x19\x00\x00\x00\x00"))

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_rotation_is_exact_180_degrees(self):
        image = Image.new("RGBA", (2, 2))
        image.putdata([
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
            (255, 255, 0, 255),
        ])
        rotated = rotate_preview_image(image)
        self.assertEqual(list(rotated.getdata()), [
            (255, 255, 0, 255),
            (0, 0, 255, 255),
            (0, 255, 0, 255),
            (255, 0, 0, 255),
        ])
        self.assertEqual(rotated.size, image.size)


if __name__ == "__main__":
    unittest.main()
