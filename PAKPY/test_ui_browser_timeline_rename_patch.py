import unittest
import zlib

import ui_browser_timeline_rename_patch as rename
import ui_browser_timeline_repack as timeline


def _tag(code, payload):
    return timeline._tag(code, payload)


def _place(depth, character_id, name="", matrix=b"\x00"):
    name_bytes = name.encode("utf-8")
    flags = b"\x26" if name_bytes else b"\x06"
    payload = (
        flags
        + int(depth).to_bytes(2, "little")
        + int(character_id).to_bytes(2, "little")
        + matrix
        + (name_bytes + b"\x00" if name_bytes else b"")
    )
    return _tag(timeline.PLACE_OBJECT2, payload)


def _sprite(sprite_id, children):
    payload = (
        int(sprite_id).to_bytes(2, "little")
        + b"\x01\x00"
        + b"".join(children)
        + _tag(timeline.SHOW_FRAME, b"")
        + _tag(timeline.END, b"")
    )
    return _tag(timeline.DEFINE_SPRITE, payload)


def _movie(compressed=False, second_name=""):
    body = b"\x08\x00" + (24 * 256).to_bytes(2, "little") + b"\x01\x00"
    body += _sprite(80, (
        _place(1, 60, "playHM"),
        _place(21, 72, "chooseKong", b"\x1A\x07\xFA\xD2"),
        _place(22, 72, second_name, b"\x1A\x03\xF5\x48\x80"),
        _place(32, 60, "rules"),
    ))
    body += _tag(timeline.END, b"")
    raw = bytearray(b"FWS\x0A" + b"\x00" * 4 + body)
    raw[4:8] = len(raw).to_bytes(4, "little")
    if compressed:
        return b"CWS" + bytes(raw[3:8]) + zlib.compress(bytes(raw[8:]))
    return bytes(raw)


class TimelineRenameTests(unittest.TestCase):
    def test_renames_unnamed_instance_without_changing_visual_data(self):
        before = timeline.inspect_sprites(_movie())[80]
        original = next(item for item in before if item["depth"] == 22)
        spec = rename.TimelineRenameSpec(80, 22, "chooseKongP2")
        result = rename.rename_instance(_movie(), spec)
        after = timeline.inspect_sprites(result.movie_data)[80]
        renamed = next(item for item in after if item["depth"] == 22)

        self.assertEqual(renamed["name"], "chooseKongP2")
        self.assertEqual(renamed["character_id"], original["character_id"])
        self.assertEqual(renamed["matrix_hex"], original["matrix_hex"])
        self.assertEqual(result.report["structural_validation"], "passed")

    def test_preserves_cws_signature(self):
        result = rename.rename_instance(
            _movie(compressed=True),
            rename.TimelineRenameSpec(80, 22, "chooseKongP2"),
        )
        self.assertTrue(result.movie_data.startswith(b"CWS"))

    def test_rejects_already_named_target_in_safe_mode(self):
        with self.assertRaises(timeline.TimelinePatchError):
            rename.rename_instance(
                _movie(second_name="alreadyNamed"),
                rename.TimelineRenameSpec(80, 22, "chooseKongP2"),
            )

    def test_rejects_duplicate_target_name(self):
        with self.assertRaises(timeline.TimelinePatchError):
            rename.rename_instance(
                _movie(),
                rename.TimelineRenameSpec(80, 22, "chooseKong"),
            )


if __name__ == "__main__":
    unittest.main()
