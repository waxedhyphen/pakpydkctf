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
        _place(1, 9, "cranky"),
        _place(3, 10, "dixie"),
        _place(5, 11, "diddy"),
    ))
    body += _sprite(15, (
        _place(1, 13, "dk", b"\x10\xA0\x00"),
        _place(3, 14, "fk"),
    ))
    body += _tag(0, b"")
    raw = bytearray(b"FWS\x0A" + b"\x00" * 4 + body)
    raw[4:8] = len(raw).to_bytes(4, "little")
    if compressed:
        return b"CWS" + bytes(raw[3:8]) + zlib.compress(bytes(raw[8:]))
    return bytes(raw)


class TimelineRepackTests(unittest.TestCase):
    def test_copies_named_instance_to_free_source_depth(self):
        spec = timeline.TimelineCopySpec(12, "diddy", 15, "diddy", "fk")
        result = timeline.copy_instance(_movie(), spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        self.assertEqual([item["name"] for item in target], ["dk", "fk", "diddy"])
        self.assertEqual(result.report["target_depth"], 5)
        self.assertEqual(result.report["structural_validation"], "passed")

    def test_preserves_cws_signature(self):
        spec = timeline.TimelineCopySpec(12, "diddy", 15, "diddy", "fk")
        result = timeline.copy_instance(_movie(compressed=True), spec)
        self.assertTrue(result.movie_data.startswith(b"CWS"))

    def test_rejects_duplicate_target_name(self):
        spec = timeline.TimelineCopySpec(12, "diddy", 15, "diddy", "fk")
        result = timeline.copy_instance(_movie(), spec)
        with self.assertRaises(timeline.TimelinePatchError):
            timeline.copy_instance(result.movie_data, spec)

    def test_can_replace_existing_target_name(self):
        spec = timeline.TimelineCopySpec(
            12, "diddy", 15, "diddy", "fk", replace_existing=True,
        )
        result = timeline.copy_instance(_movie(), spec)
        result = timeline.copy_instance(result.movie_data, spec)
        target = timeline.inspect_sprites(result.movie_data)[15]
        self.assertEqual(sum(item["name"] == "diddy" for item in target), 1)


if __name__ == "__main__":
    unittest.main()
