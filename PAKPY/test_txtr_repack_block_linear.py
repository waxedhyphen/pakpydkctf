import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

import txtr_repack


class BlockLinearRgba8RepackTests(unittest.TestCase):
    def test_format_12_tile_mode_0_uses_tegra_block_linear_swizzle(self):
        image = Image.new('RGBA', (76, 76), (1, 2, 3, 4))
        with mock.patch.object(txtr_repack, 'block_height_mip0', return_value=8) as block_height:
            with mock.patch.object(txtr_repack, 'swizzle_block_linear', return_value=b'tiled') as swizzle:
                result = txtr_repack._encode_mip_payload(
                    {'format': 12, 'tile_mode': 0, 'swizzle': 7},
                    image,
                )
        self.assertEqual(result, b'tiled')
        block_height.assert_called_once_with(76)
        swizzle.assert_called_once_with(
            76,
            76,
            1,
            image.tobytes('raw', 'RGBA'),
            8,
            4,
        )

    def test_block_linear_rgba8_is_reported_as_editable_when_swizzler_exists(self):
        info = {'format': 12, 'tile_mode': 0, 'swizzle': 7}
        with mock.patch.object(txtr_repack, 'parse_txtr_asset', return_value=info):
            with mock.patch.object(txtr_repack, 'swizzle_block_linear', object()):
                with mock.patch.object(txtr_repack, 'block_height_mip0', object()):
                    self.assertTrue(txtr_repack.can_repack_txtr_asset(b'asset'))

    def test_repack_preserves_head_sampler_fields(self):
        head_payload = b'HEAD-SAMPLER-DATA'
        gpu_payload = b'OLD-GPU'
        original_asset = b'\x00' * 32 + head_payload + gpu_payload
        chunks = [
            {
                'tag': 'HEAD',
                'payload_off': 32,
                'payload_end': 32 + len(head_payload),
            },
            {
                'tag': 'GPU ',
                'payload_off': 32 + len(head_payload),
                'payload_end': len(original_asset),
            },
        ]
        info = {'width': 1, 'height': 1}
        with tempfile.TemporaryDirectory() as td:
            png_path = Path(td) / 'edit.png'
            Image.new('RGBA', (1, 1), (10, 20, 30, 40)).save(png_path)
            with mock.patch.object(txtr_repack, 'parse_txtr_asset', return_value=info):
                with mock.patch.object(txtr_repack, '_encode_mip_chain', return_value=[b'NEW-GPU']):
                    with mock.patch.object(txtr_repack, 'parse_asset_chunks', return_value=chunks):
                        with mock.patch.object(txtr_repack, 'build_chunk_raw', side_effect=lambda chunk, payload: payload) as build:
                            txtr_repack.png_to_txtr_asset(original_asset, png_path)
        self.assertEqual(build.call_args_list[0].args[1], head_payload)
        self.assertEqual(build.call_args_list[1].args[1], b'\x00\x00\x00\x00NEW-GPU')


if __name__ == '__main__':
    unittest.main()
