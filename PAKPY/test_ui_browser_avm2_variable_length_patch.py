import unittest
import zlib

import ui_browser_avm2_repack as repack
import ui_browser_avm2_variable_length_patch as variable


def _u30(value):
    result = bytearray()
    value = int(value)
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            result.append(byte | 0x80)
        else:
            result.append(byte)
            return bytes(result)


def _abc_with_method(code):
    result = bytearray()
    result += (16).to_bytes(2, "little") + (46).to_bytes(2, "little")
    result += _u30(1)  # int pool
    result += _u30(1)  # uint pool
    result += _u30(1)  # double pool
    result += _u30(1)  # string pool
    result += _u30(1)  # namespace pool
    result += _u30(1)  # namespace-set pool
    result += _u30(1)  # multiname pool
    result += _u30(1)  # method count
    result += _u30(0) + _u30(0) + _u30(0) + b"\x00"
    result += _u30(0)  # metadata count
    result += _u30(0)  # class count
    result += _u30(0)  # script count
    result += _u30(1)  # body count
    result += _u30(0)  # method index
    result += _u30(4) + _u30(1) + _u30(0) + _u30(1)
    result += _u30(len(code)) + code
    result += _u30(0)  # exceptions
    result += _u30(0)  # body traits
    return bytes(result)


def _tag(code, payload):
    if len(payload) < 63:
        return ((code << 6) | len(payload)).to_bytes(2, "little") + payload
    return (
        ((code << 6) | 63).to_bytes(2, "little")
        + len(payload).to_bytes(4, "little")
        + payload
    )


def _doabc(code, name=b"test"):
    return _tag(
        82,
        (0).to_bytes(4, "little") + name + b"\x00" + _abc_with_method(code),
    )


def _swf(code, compressed=False, nested=False):
    body = b"\x08\x00" + (24 * 256).to_bytes(2, "little") + (1).to_bytes(2, "little")
    if nested:
        sprite_payload = (
            (7).to_bytes(2, "little")
            + (1).to_bytes(2, "little")
            + _doabc(code)
            + _tag(0, b"")
        )
        body += _tag(39, sprite_payload)
    else:
        body += _doabc(code)
    body += _tag(0, b"")
    raw = bytearray(b"FWS\x0A" + b"\x00\x00\x00\x00" + body)
    raw[4:8] = len(raw).to_bytes(4, "little")
    if compressed:
        return b"CWS" + bytes(raw[3:8]) + zlib.compress(bytes(raw[8:]))
    return bytes(raw)


def _method_code(movie):
    data, _signature = repack._inflate_swf(movie)
    module = repack.locate_doabc_modules(movie)[0]
    method = module.methods[0]
    return bytes(
        data[
            module.abc_offset + method.code_offset:
            module.abc_offset + method.code_offset + method.code_size
        ]
    )


class VariableLengthAVM2PatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        variable.install()

    def test_keeps_same_length_patches_compatible(self):
        patch = repack.BytePatch("test", "root", 0, 0, b"\x26", b"\x27")
        result = repack.apply_movie_patches(_swf(b"\x26\x47"), (patch,))
        self.assertEqual(_method_code(result.movie_data), b"\x27\x47")

    def test_inserts_a_multibyte_block_and_updates_method_size(self):
        patch = repack.BytePatch(
            "test", "root", 0, 0,
            b"\x26", b"\x26\x02\x02\x02",
        )
        result = repack.apply_movie_patches(_swf(b"\x26\x47"), (patch,))
        self.assertEqual(_method_code(result.movie_data), b"\x26\x02\x02\x02\x47")
        self.assertEqual(result.applied[0]["byte_delta"], 3)
        self.assertEqual(result.applied[0]["old_method_code_size"], 2)
        self.assertEqual(result.applied[0]["new_method_code_size"], 5)

    def test_removes_bytes_and_updates_method_size(self):
        patch = repack.BytePatch(
            "test", "root", 0, 1,
            b"\x02\x02\x47", b"\x47",
        )
        result = repack.apply_movie_patches(
            _swf(b"\x26\x02\x02\x47"), (patch,)
        )
        self.assertEqual(_method_code(result.movie_data), b"\x26\x47")
        self.assertEqual(result.applied[0]["byte_delta"], -2)

    def test_applies_multiple_original_offsets_without_offset_drift(self):
        patches = (
            repack.BytePatch(
                "test", "root", 0, 1, b"\x11", b"\xAA\xBB"
            ),
            repack.BytePatch(
                "test", "root", 0, 3, b"\x13\x14", b"\xCC"
            ),
        )
        result = repack.apply_movie_patches(
            _swf(b"\x10\x11\x12\x13\x14"), patches
        )
        self.assertEqual(_method_code(result.movie_data), b"\x10\xAA\xBB\x12\xCC")

    def test_rebuilds_u30_when_code_size_crosses_127_bytes(self):
        code = b"\x02" * 127
        patch = repack.BytePatch(
            "test", "root", 0, 126,
            b"\x02", b"\x02\x02\x02\x02",
        )
        result = repack.apply_movie_patches(_swf(code), (patch,))
        self.assertEqual(len(_method_code(result.movie_data)), 130)

    def test_rebuilds_parent_definesprite_tag(self):
        patch = repack.BytePatch(
            "test", "sprite 7", 0, 0,
            b"\x26", b"\x26\x02\x02",
        )
        result = repack.apply_movie_patches(
            _swf(b"\x26\x47", nested=True), (patch,)
        )
        modules = repack.locate_doabc_modules(result.movie_data)
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].source, "sprite 7")
        self.assertEqual(_method_code(result.movie_data), b"\x26\x02\x02\x47")

    def test_preserves_cws_signature(self):
        patch = repack.BytePatch(
            "test", "root", 0, 0,
            b"\x26", b"\x26\x02",
        )
        result = repack.apply_movie_patches(
            _swf(b"\x26\x47", compressed=True), (patch,)
        )
        self.assertEqual(result.signature, "CWS")
        self.assertTrue(result.movie_data.startswith(b"CWS"))

    def test_still_rejects_overlapping_original_ranges(self):
        patches = (
            repack.BytePatch(
                "test", "root", 0, 0, b"\x26\x02", b"\x26"
            ),
            repack.BytePatch(
                "test", "root", 0, 1, b"\x02", b"\x02\x02"
            ),
        )
        with self.assertRaisesRegex(repack.AVM2PatchError, "überlappen"):
            repack.apply_movie_patches(_swf(b"\x26\x02\x47"), patches)


if __name__ == "__main__":
    unittest.main()
