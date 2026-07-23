import unittest
import zlib

import ui_browser_avm2_repack as patcher


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


def _abc_with_method(code=b"\x26\x47"):
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
    result += _u30(1) + _u30(1) + _u30(0) + _u30(1)
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


def _swf(code=b"\x26\x47", compressed=False):
    doabc = (0).to_bytes(4, "little") + b"test\x00" + _abc_with_method(code)
    # Minimal RECT (nbits=1), frame rate and frame count.
    body = b"\x08\x00" + (24 * 256).to_bytes(2, "little") + (1).to_bytes(2, "little")
    body += _tag(82, doabc) + _tag(0, b"")
    raw = bytearray(b"FWS\x0A" + b"\x00\x00\x00\x00" + body)
    raw[4:8] = len(raw).to_bytes(4, "little")
    if compressed:
        return b"CWS" + bytes(raw[3:8]) + zlib.compress(bytes(raw[8:]))
    return bytes(raw)


def _gfx_asset(movie):
    payload = bytearray(b"\x00" * 32)
    payload += (1).to_bytes(4, "big")
    record = bytearray(64)
    movie_offset = 36 + 64
    record[0:8] = (movie_offset - 32).to_bytes(8, "big")
    record[8:16] = len(movie).to_bytes(8, "big")
    record[16:27] = b"Options.swf"
    payload += record + movie
    chunk = bytearray(b"GFX " + len(payload).to_bytes(8, "big") + b"\x00" * 12 + payload)
    return bytes(b"RFRM" + len(chunk).to_bytes(8, "big") + b"\x00" * 8 + b"GFX " + b"\x00" * 8 + chunk)


class AVM2RepackTests(unittest.TestCase):
    def test_locates_and_patches_method_body(self):
        movie = _swf()
        modules = patcher.locate_doabc_modules(movie)
        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].methods[0].code_size, 2)
        patch = patcher.BytePatch("test", "root", 0, 0, b"\x26", b"\x27")
        result = patcher.apply_movie_patches(movie, (patch,))
        data, _signature = patcher._inflate_swf(result.movie_data)
        module = patcher.locate_doabc_modules(result.movie_data)[0]
        method = module.methods[0]
        self.assertEqual(data[module.abc_offset + method.code_offset], 0x27)

    def test_preserves_cws_and_rebuilds_variable_size_gfx_movie(self):
        movie = _swf(compressed=True)
        patch = patcher.BytePatch("test", "root", 0, 0, b"\x26", b"\x27")
        result = patcher.apply_movie_patches(movie, (patch,))
        self.assertEqual(result.signature, "CWS")
        rebuilt = patcher.rebuild_gfx_asset(_gfx_asset(movie), 0, result.movie_data)
        self.assertEqual(rebuilt[:4], b"RFRM")
        self.assertEqual(int.from_bytes(rebuilt[4:12], "big"), len(rebuilt) - 32)
        self.assertEqual(int.from_bytes(rebuilt[36:44], "big"), len(rebuilt) - 56)

    def test_rejects_mismatched_original_bytes(self):
        patch = patcher.BytePatch("test", "root", 0, 0, b"\x27", b"\x26")
        with self.assertRaisesRegex(patcher.AVM2PatchError, "Originalbytes passen nicht"):
            patcher.apply_movie_patches(_swf(), (patch,))

    def test_rejects_overlapping_patches(self):
        patches = (
            patcher.BytePatch("test", "root", 0, 0, b"\x26", b"\x27"),
            patcher.BytePatch("test", "root", 0, 0, b"\x26", b"\x02"),
        )
        with self.assertRaisesRegex(patcher.AVM2PatchError, "überlappen"):
            patcher.apply_movie_patches(_swf(), patches)

    def test_manifest_round_trip(self):
        patches = (
            patcher.BytePatch(
                "root", "root", 419, 0x165,
                b"\x12\x18\x00\x00", b"\x29\x02\x02\x02", "branch",
            ),
        )
        self.assertEqual(
            patcher.load_patch_manifest(patcher.dump_patch_manifest(patches)), patches,
        )


if __name__ == "__main__":
    unittest.main()
