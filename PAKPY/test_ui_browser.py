import struct
import unittest

from ui_browser import (
    build_display_list,
    find_preview_frame,
    parse_gfx_asset,
    parse_gfxl_asset,
    parse_swf_movie,
)


def _rfrm_asset(tag, payload):
    chunk_tag = tag.encode("ascii").ljust(4, b" ")
    chunk = chunk_tag + len(payload).to_bytes(8, "big") + b"\x00" * 12 + payload
    return b"RFRM" + len(chunk).to_bytes(8, "big") + b"\x00" * 8 + chunk_tag + b"\x00" * 8 + chunk


def _bits(values):
    text = "".join(format(value, f"0{count}b") for value, count in values)
    text += "0" * ((8 - len(text) % 8) % 8)
    return bytes(int(text[index:index + 8], 2) for index in range(0, len(text), 8))


def _signed(value, count):
    return value if value >= 0 else (1 << count) + value


def _rect(xmin, xmax, ymin, ymax):
    nbits = max(1, max(abs(xmin), abs(xmax), abs(ymin), abs(ymax)).bit_length() + 1)
    return _bits([
        (nbits, 5),
        (_signed(xmin, nbits), nbits),
        (_signed(xmax, nbits), nbits),
        (_signed(ymin, nbits), nbits),
        (_signed(ymax, nbits), nbits),
    ])


def _tag(code, payload=b""):
    if len(payload) < 63:
        return struct.pack("<H", (code << 6) | len(payload)) + payload
    return struct.pack("<H", (code << 6) | 63) + struct.pack("<I", len(payload)) + payload


def _minimal_swf(width=1280, height=720, frames=1, tags=b""):
    body = _rect(0, width * 20, 0, height * 20)
    body += struct.pack("<H", 60 * 256)
    body += struct.pack("<H", frames)
    body += tags + _tag(0)
    return b"FWS" + bytes([25]) + struct.pack("<I", 8 + len(body)) + body


class UIBrowserParserTests(unittest.TestCase):
    def test_gfx_container_relative_offsets(self):
        movie = _minimal_swf()
        relative_offset = 4 + 64
        record = relative_offset.to_bytes(8, "big") + len(movie).to_bytes(8, "big")
        record += b"Source\x00".ljust(48, b"\x00")
        payload = b"\x11" * 16 + b"\x00" * 16 + (1).to_bytes(4, "big") + record + movie
        container = parse_gfx_asset(_rfrm_asset("GFX", payload))
        self.assertEqual(container.library_uuid, "11" * 16)
        self.assertEqual(container.movies[0].name, "Source")
        self.assertEqual(container.movies[0].data, movie)

    def test_gfxl_mapping(self):
        payload = (1).to_bytes(4, "big")
        payload += b"\x22" * 16 + (6).to_bytes(4, "big") + b"button"
        payload += (7).to_bytes(4, "big") + b"Lib.swf" + b"GFX-data"
        library = parse_gfxl_asset(_rfrm_asset("GFXL", payload))
        self.assertEqual(library.name, "Lib.swf")
        self.assertEqual(library.mappings["button"], "22" * 16)

    def test_swf_stage_ratio(self):
        movie = parse_swf_movie(_minimal_swf(1280, 720))
        self.assertEqual((movie.width, movie.height), (1280, 720))
        self.assertAlmostEqual(movie.width / movie.height, 16 / 9)
        self.assertEqual(movie.frame_rate, 60)

    def test_preview_frame_prefers_populated_frame(self):
        place = bytes([0x06]) + struct.pack("<H", 1) + struct.pack("<H", 7) + bytes([0])
        tags = _tag(1) + _tag(26, place) + _tag(1)
        movie = parse_swf_movie(_minimal_swf(frames=2, tags=tags))
        self.assertEqual(find_preview_frame(movie), 2)
        self.assertIn(1, build_display_list(movie.root_tags, 2))


if __name__ == "__main__":
    unittest.main()
