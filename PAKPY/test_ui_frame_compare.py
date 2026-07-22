import unittest

from PIL import Image

from ui_frame_compare import compare_images, difference_image


class FrameCompareTests(unittest.TestCase):
    def test_exact_images(self):
        image = Image.new("RGBA", (2, 2), (10, 20, 30, 255))
        report = compare_images(image, image)
        self.assertEqual(report.differing_pixels, 0)
        self.assertEqual(report.threshold_pixels, 0)
        self.assertEqual(report.exact_percent, 100.0)
        self.assertIsNone(report.peak_signal_to_noise_ratio)
        self.assertIsNone(report.difference_bounds)

    def test_reports_threshold_and_bounds(self):
        reference = Image.new("RGBA", (3, 2), (0, 0, 0, 255))
        actual = reference.copy()
        actual.putpixel((1, 1), (10, 20, 30, 255))
        report = compare_images(reference, actual, threshold=20)
        self.assertEqual(report.differing_pixels, 1)
        self.assertEqual(report.threshold_pixels, 1)
        self.assertEqual(report.max_channel_delta, 30)
        self.assertEqual(report.difference_bounds, (1, 1, 2, 2))
        self.assertGreater(report.root_mean_square_error, 0.0)

    def test_ignore_alpha(self):
        reference = Image.new("RGBA", (1, 1), (1, 2, 3, 0))
        actual = Image.new("RGBA", (1, 1), (1, 2, 3, 255))
        self.assertEqual(
            compare_images(reference, actual, ignore_alpha=True).differing_pixels,
            0,
        )
        self.assertEqual(compare_images(reference, actual).differing_pixels, 1)

    def test_heatmap_is_transparent_for_exact_pixels(self):
        reference = Image.new("RGBA", (2, 1), (0, 0, 0, 255))
        actual = reference.copy()
        actual.putpixel((1, 0), (255, 0, 0, 255))
        heatmap = difference_image(reference, actual)
        self.assertEqual(heatmap.getpixel((0, 0))[3], 0)
        self.assertEqual(heatmap.getpixel((1, 0))[3], 255)

    def test_size_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            compare_images(
                Image.new("RGBA", (1, 1)),
                Image.new("RGBA", (2, 1)),
            )


if __name__ == "__main__":
    unittest.main()
