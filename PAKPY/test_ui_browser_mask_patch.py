import unittest
from types import SimpleNamespace

import ui_browser
import ui_browser_shape_patch
import ui_browser_mask_patch

try:
    from PIL import Image
except Exception:
    Image = None


class _Resolver:
    def __init__(self):
        self.images = {
            "mask": Image.new("RGBA", (5, 10), (255, 255, 255, 255)) if Image is not None else None,
            "content": Image.new("RGBA", (10, 10), (0, 255, 0, 255)) if Image is not None else None,
            "after": Image.new("RGBA", (10, 10), (0, 0, 255, 255)) if Image is not None else None,
        }

    def get(self, name):
        return SimpleNamespace(image=self.images.get(name), uuid_hex=name, source="test", error="")


@unittest.skipIf(Image is None, "Pillow fehlt")
class UIBrowserMaskPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ui_browser_shape_patch.install()
        ui_browser_mask_patch.install()

    def test_clip_depth_masks_only_its_inclusive_range(self):
        movie = SimpleNamespace(definitions={})
        renderer = ui_browser.UIRenderer(movie, _Resolver(), show_bounds=False, show_placeholders=False)
        canvas = Image.new("RGBA", (10, 20), (0, 0, 0, 0))
        display = {
            1: ui_browser.DisplayObject(depth=1, class_name="mask", clip_depth=2),
            2: ui_browser.DisplayObject(depth=2, class_name="content"),
            3: ui_browser.DisplayObject(depth=3, class_name="after", matrix=ui_browser.Affine(tx=0, ty=10)),
        }
        renderer._draw_display(canvas, display, ui_browser.Affine(), ui_browser.IDENTITY_COLOR, set(), 0)

        self.assertEqual(canvas.getpixel((2, 5))[3], 255)
        self.assertEqual(canvas.getpixel((7, 5))[3], 0)
        self.assertEqual(canvas.getpixel((2, 15))[3], 255)
        self.assertEqual(canvas.getpixel((7, 15))[3], 255)
        self.assertEqual(renderer.stats.masks_defined, 1)
        self.assertEqual(renderer.stats.masked_placements, 1)

    def test_multiple_masks_intersect(self):
        layer = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        left = Image.new("L", (2, 2), 0)
        left.putpixel((0, 0), 255)
        left.putpixel((0, 1), 255)
        top = Image.new("L", (2, 2), 0)
        top.putpixel((0, 0), 255)
        top.putpixel((1, 0), 255)
        masks = [
            ui_browser_mask_patch.ActiveClipMask(1, 5, left),
            ui_browser_mask_patch.ActiveClipMask(2, 5, top),
        ]
        ui_browser_mask_patch.apply_clip_masks(layer, masks)
        self.assertEqual([layer.getpixel((x, y))[3] for y in range(2) for x in range(2)], [255, 0, 0, 0])


if __name__ == "__main__":
    unittest.main()
