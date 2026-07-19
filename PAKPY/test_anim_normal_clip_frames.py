from types import SimpleNamespace
import unittest

from anim_normal_clip_frames import (
    _WordDurationReader,
    compact_vector_record_size,
    extended_vector_record_size,
    parse_frame_schedule_from_setup,
    rotation_record_size,
)


class ChannelSet:
    def __init__(self, nodes):
        self.animated_nodes = list(nodes)


class FrameScheduleTests(unittest.TestCase):
    def test_duration_prefix_codec(self):
        # Width 3. Values [1, 3, 1, 8] encode as:
        # 0 | 1,010 | 0 | 1,111, consumed LSB-first in a BE u16 word.
        bits = [0, 1, 0, 1, 0, 0, 1, 1, 1, 1]
        word = sum(bit << index for index, bit in enumerate(bits))
        reader = _WordDurationReader(word.to_bytes(2, "big"), 0)
        self.assertEqual([reader.decode(3) for _ in range(4)], [1, 3, 1, 8])
        self.assertEqual(reader.bit_position, 10)
        self.assertEqual(reader.end_offset, 2)

    def test_record_size_flags(self):
        self.assertEqual(rotation_record_size(bytes.fromhex("0000000000000000"), 0), 8)
        self.assertEqual(rotation_record_size(bytes.fromhex("800000000000000000000000"), 0), 12)
        self.assertEqual(compact_vector_record_size(bytes.fromhex("00000000"), 0), 4)
        self.assertEqual(compact_vector_record_size(bytes.fromhex("8000000000000000"), 0), 8)
        self.assertEqual(extended_vector_record_size(bytes.fromhex("0000000000000000"), 0), 4)
        self.assertEqual(extended_vector_record_size(bytes.fromhex("8000000000000000"), 0), 8)
        self.assertEqual(extended_vector_record_size(bytes.fromhex("8000000080000000"), 0), 12)

    def test_three_frame_implicit_schedule(self):
        # One rotation + one translation + one scale record per value block.
        value_block = bytes(8 + 4 + 4)
        raw = bytearray()
        raw += value_block
        raw += bytes([0x1C])       # all three types get implicit duration 1
        raw += bytes(3)            # value block 4-byte alignment
        raw += value_block         # keys at frame 1
        raw += bytes([0x1C])
        raw += bytes(3)
        raw += value_block         # keys at frame 2
        raw += bytes(8)            # RFRM trailing zero words

        indices = SimpleNamespace(
            flags=0,
            frame_count_field=3,
            rotation=ChannelSet([4]),
            translation=ChannelSet([5]),
            scale=ChannelSet([6]),
        )
        setup = SimpleNamespace(indices=indices, frame_data_file_offset=0)
        result = parse_frame_schedule_from_setup(bytes(raw), setup, strict=True)

        self.assertEqual(result.rotation_key_frames, [[0, 1, 2]])
        self.assertEqual(result.translation_key_frames, [[0, 1, 2]])
        self.assertEqual(result.scale_key_frames, [[0, 1, 2]])
        self.assertEqual(len(result.blocks), 2)
        self.assertEqual(result.stream_end_file_offset, len(raw) - 8)
        self.assertEqual(result.trailing_hex, "00" * 8)


if __name__ == "__main__":
    unittest.main()
