import struct
import unittest

import ui_browser
from ui_browser_library_patch import (
    build_library_symbol_index,
    parse_external_image_tag,
    resize_external_image,
)

try:
    from PIL import Image
except Exception:
    Image = None


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


def _minimal_swf(tags=b""):
    body = _rect(0, 1280 * 20, 0, 720 * 20)
    body += struct.pack("<H", 60 * 256)
    body += struct.pack("<H", 1)
    body += tags + _tag(0)
    return b"GFX" + bytes([25]) + struct.pack("<I", 8 + len(body)) + body


def _external_payload(character_id=7, width=256, height=128, name="button", filename="button.tga"):
    name_raw = name.encode("utf-8")
    filename_raw = filename.encode("utf-8")
    return (
        struct.pack("<IHHH", character_id, 13, width, height)
        + bytes([len(name_raw)]) + name_raw
        + bytes([len(filename_raw)]) + filename_raw
    )


def _symbol_class(character_id=7, name="button"):
    return struct.pack("<H", 1) + struct.pack("<H", character_id) + name.encode("utf-8") + b"\x00"


class UIBrowserLibraryPatchTests(unittest.TestCase):
    def test_external_image_tag(self):
        item = parse_external_image_tag(_external_payload())
        self.assertEqual(item.character_id, 7)
        self.assertEqual(item.format_id, 13)
        self.assertEqual((item.width, item.height), (256, 128))
        self.assertEqual(item.name, "button")
        self.assertEqual(item.filename, "button.tga")

    def test_library_index_links_symbol_class_and_uuid(self):
        movie_data = _minimal_swf(
            _tag(1009, _external_payload())
            + _tag(76, _symbol_class())
        )
        library = ui_browser.GfxLibrary(
            name="TestLib.swf",
            mappings={"button": "22" * 16},
            movie_data=movie_data,
            source="Test.pak",
            entry_uuid="11" * 16,
        )
        symbols, index, errors = build_library_symbol_index([library])
        self.assertEqual(errors, ())
        self.assertEqual(len(symbols), 1)
        symbol = symbols[0]
        self.assertEqual(symbol.class_name, "button")
        self.assertEqual(symbol.uuid_hex, "22" * 16)
        self.assertEqual(index["button"][0], symbol)
        self.assertEqual(index["button.tga"][0], symbol)

    @unittest.skipIf(Image is None, "Pillow fehlt")
    def test_external_dimensions_are_used_for_preview(self):
        image = Image.new("RGBA", (32, 16), (255, 0, 0, 255))
        resized = resize_external_image(image, 256, 128)
        self.assertEqual(resized.size, (256, 128))


if __name__ == "__main__":
    unittest.main()
