import zlib
import unittest

import ui_browser_shape_patch as shape_patch
import ui_browser_visual_formats as visual


class VisualFormatTests(unittest.TestCase):
    def test_decodes_argb_lossless_bitmap(self):
        raw = bytes((255, 10, 20, 30, 128, 40, 50, 60))
        payload = (
            (7).to_bytes(2, "little")
            + bytes((5,))
            + (2).to_bytes(2, "little")
            + (1).to_bytes(2, "little")
            + zlib.compress(raw)
        )
        value = visual.decode_lossless_bitmap(
            payload, True, visual.TAG_DEFINE_BITS_LOSSLESS2,
        )
        self.assertEqual(value.character_id, 7)
        self.assertEqual(value.image.size, (2, 1))
        self.assertEqual(value.image.getpixel((0, 0)), (10, 20, 30, 255))
        self.assertEqual(value.image.getpixel((1, 0)), (40, 50, 60, 128))

    def test_gradient_parameters(self):
        self.assertAlmostEqual(
            visual.gradient_parameter("linear_gradient", -1.0, 0.0), 0.0,
        )
        self.assertAlmostEqual(
            visual.gradient_parameter("linear_gradient", 1.0, 0.0), 1.0,
        )
        self.assertAlmostEqual(
            visual.gradient_parameter("radial_gradient", 0.0, 0.0), 0.0,
        )
        self.assertAlmostEqual(
            visual.gradient_parameter("radial_gradient", 1.0, 0.0), 1.0,
        )
        self.assertAlmostEqual(
            visual.gradient_parameter("focal_gradient", 0.5, 0.0, 0.5), 0.0,
        )

    def test_gradient_spread_modes(self):
        self.assertEqual(visual.spread_unit(-1.0, 0), 0.0)
        self.assertEqual(visual.spread_unit(2.0, 0), 1.0)
        self.assertAlmostEqual(visual.spread_unit(1.25, 1), 0.75)
        self.assertAlmostEqual(visual.spread_unit(1.25, 2), 0.25)

    def test_scale9_inverse_coordinate(self):
        self.assertAlmostEqual(
            visual.scale9_inverse_coordinate(10, 100, 20, 20, 200), 10,
        )
        self.assertAlmostEqual(
            visual.scale9_inverse_coordinate(20, 100, 20, 20, 200), 20,
        )
        self.assertAlmostEqual(
            visual.scale9_inverse_coordinate(180, 100, 20, 20, 200), 80,
        )
        self.assertAlmostEqual(
            visual.scale9_inverse_coordinate(190, 100, 20, 20, 200), 90,
        )
        self.assertAlmostEqual(
            visual.scale9_inverse_coordinate(10, 100, 20, 20, 200, True), 90,
        )

    def test_interpolates_morph_edges_and_color(self):
        start_fill = visual.EnhancedVectorFillStyle(
            kind="solid", color=(0, 0, 0, 255),
        )
        end_fill = visual.EnhancedVectorFillStyle(
            kind="solid", color=(255, 128, 64, 255),
        )
        start_edge = shape_patch.VectorEdge((0, 0), (100, 0), None)
        end_edge = shape_patch.VectorEdge((0, 0), (200, 100), (100, 0))
        definition = visual.MorphShapeDef(
            character_id=12,
            version=1,
            start_bounds=(0.0, 0.0, 5.0, 5.0),
            end_bounds=(0.0, 0.0, 10.0, 10.0),
            start_edge_bounds=(0.0, 0.0, 5.0, 5.0),
            end_edge_bounds=(0.0, 0.0, 10.0, 10.0),
            fills=(None, visual.MorphFillPair(start_fill, end_fill)),
            lines=(None,),
            start_records=(visual.MorphStyledEdge(1, 0, 0, start_edge),),
            end_records=(visual.MorphStyledEdge(1, 0, 0, end_edge),),
        )
        value = visual.interpolate_morph(definition, 32768)
        self.assertEqual(value.character_id, 12)
        self.assertEqual(value.record_count, 1)
        edge = value.fill_edges[1][0]
        self.assertEqual(edge.end, (150, 50))
        self.assertIsNotNone(edge.control)
        self.assertEqual(value.fills[1].color, (128, 64, 32, 255))
        self.assertAlmostEqual(value.bounds[2], 7.500038, places=5)

    def test_rejects_invalid_morph_offset(self):
        payload = (
            (1).to_bytes(2, "little")
            + b"\x00\x00"
            + (0xFFFFFFFF).to_bytes(4, "little")
        )
        with self.assertRaises(Exception):
            visual.parse_morph_shape(payload, 1)


if __name__ == "__main__":
    unittest.main()
