import unittest
import zlib

import ui_browser_timeline_repack as timeline


def _tag(code, payload):
    return timeline._tag(code, payload)


def _place(depth, character_id, name, matrix=b"\x00"):
    payload = (
        b"\x26"
        + int(depth).to_bytes(2, "little")
        + int(character_id).to_bytes(2, "little")
        + matrix
        + name.encode("utf-8")
        + b"\x00"
    )
    return _tag(26, payload)


def _sprite(sprite_id, children):
    payload = (
        int(sprite_id).to_bytes(2, "little")
        + b"\x01\x00"
        + b"".join(children)
        + _tag(1, b"")
        + _tag(0, b"")
    )
    return _tag(39, payload)


def _movie(compressed=False):
    body = b"\x08\x00" + (24 * 256).to_bytes(2, "little") + b"\x01\x00"
    body += _sprite(12, (
        _place(1, 9, "source_a"),
        _place(3, 10, "source_b"),
        _place(5, 11, "source_icon"),
    ))
    body += _sprite(15, (
        _place(1, 13, "target_a", b"\x10\xA0\x00"),
        _place(3, 14, "position_anchor"),
    ))
    body += _tag(0, b"")
    raw = bytearray(b"FWS\x0A" + b"\x00" * 4 + body)
    raw[4:8] = len(raw).to_bytes(4, "little")
    if compressed:
        return b"CWS" + bytes(raw[3:8]) + zlib.compress(bytes(raw[8:]))
    return bytes(raw)


class TimelineRepackTests(unittest.TestCase):
    def test_copies_arbitrary_named_instance_to_free_source_depth(self):
        spec = timeline.TimelineCopySpec(
            12, "source_icon", 15, "copied_icon", "position_anchor",
        )
        result = timeline.copy_instance(_movie(), spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        self.assertEqual(
            [item["name"] for item in target],
            ["target_a", "position_anchor", "copied_icon"],
        )
        self.assertEqual(result.report["target_depth"], 5)
        self.assertEqual(result.report["structural_validation"], "passed")

    def test_preserves_cws_signature(self):
        spec = timeline.TimelineCopySpec(
            12, "source_b", 15, "new_instance", "target_a",
        )
        result = timeline.copy_instance(_movie(compressed=True), spec)
        self.assertTrue(result.movie_data.startswith(b"CWS"))

    def test_rejects_duplicate_target_name(self):
        spec = timeline.TimelineCopySpec(
            12, "source_icon", 15, "copied_icon", "position_anchor",
        )
        result = timeline.copy_instance(_movie(), spec)
        with self.assertRaises(timeline.TimelinePatchError):
            timeline.copy_instance(result.movie_data, spec)

    def test_can_replace_existing_target_name(self):
        spec = timeline.TimelineCopySpec(
            12,
            "source_icon",
            15,
            "copied_icon",
            "position_anchor",
            replace_existing=True,
        )
        result = timeline.copy_instance(_movie(), spec)
        result = timeline.copy_instance(result.movie_data, spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        self.assertEqual(
            sum(item["name"] == "copied_icon" for item in target),
            1,
        )

    def test_supports_manual_target_depth_without_named_anchor(self):
        spec = timeline.TimelineCopySpec(
            12,
            "source_a",
            15,
            "manual_depth_instance",
            depth=8,
        )
        result = timeline.copy_instance(_movie(), spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        inserted = next(
            item for item in target if item["name"] == "manual_depth_instance"
        )
        self.assertEqual(inserted["depth"], 8)
        self.assertEqual(result.report["depth_reason"], "manuell")


if __name__ == "__main__":
    unittest.main()
