import unittest

import ui_browser_timeline_repack as timeline
import ui_browser_timeline_transform_patch as transform
from test_ui_browser_timeline_repack import _movie


transform.install()


class TimelineTransformPatchTests(unittest.TestCase):
    def test_translates_matrix_without_changing_scale_or_rotation(self):
        original = transform.encode_matrix({
            "scale": (0x10000, 0x10000),
            "rotate": (0x100, -0x100),
            "translate_x_twips": 63,
            "translate_y_twips": 1385,
        })
        moved = transform.translate_matrix(original, 40, 1320)
        decoded = transform.decode_matrix(moved)
        self.assertEqual(decoded["scale"], (0x10000, 0x10000))
        self.assertEqual(decoded["rotate"], (0x100, -0x100))
        self.assertEqual(decoded["translate_x_twips"], 103)
        self.assertEqual(decoded["translate_y_twips"], 2705)

    def test_copies_unnamed_visual_instance_at_manual_depth(self):
        spec = timeline.TimelineCopySpec(
            source_sprite_id=12,
            source_name="source_icon",
            target_sprite_id=15,
            target_name="",
            depth=8,
            translate_y_twips=400,
            allow_unnamed=True,
        )
        result = timeline.copy_instance(_movie(), spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        inserted = next(item for item in target if item["depth"] == 8)
        self.assertEqual(inserted["name"], "")
        self.assertEqual(inserted["character_id"], 11)
        matrix = transform.decode_matrix(bytes.fromhex(inserted["matrix_hex"]))
        self.assertEqual(matrix["translate_y_twips"], 400)
        self.assertEqual(result.report["structural_validation"], "passed")

    def test_existing_named_copy_path_remains_compatible(self):
        spec = timeline.TimelineCopySpec(
            12, "source_icon", 15, "named_copy", "position_anchor"
        )
        result = timeline.copy_instance(_movie(), spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        self.assertEqual(sum(item["name"] == "named_copy" for item in target), 1)

    def test_unnamed_copy_requires_explicit_opt_in(self):
        spec = timeline.TimelineCopySpec(
            source_sprite_id=12,
            source_name="source_icon",
            target_sprite_id=15,
            target_name="",
            depth=8,
        )
        with self.assertRaises(timeline.TimelinePatchError):
            timeline.plan_copy_instance(_movie(), spec)


if __name__ == "__main__":
    unittest.main()
