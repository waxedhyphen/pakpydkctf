import io
import struct
import unittest
import wave

import ui_audio_codec as codec


def chunk(tag, payload):
    head = bytearray(24)
    head[:4] = tag.encode('ascii')
    head[4:12] = len(payload).to_bytes(8, 'big')
    return bytes(head) + payload


def channel(sample=1, sample_count=14, rate=32000):
    head = bytearray(0x60)
    head[0:4] = sample_count.to_bytes(4, 'little')
    head[4:8] = (16).to_bytes(4, 'little')
    head[8:12] = rate.to_bytes(4, 'little')
    # predictor 0, exponent 0, fourteen identical signed nibbles
    nibble = sample & 0xF
    frame = bytes([0]) + bytes([(nibble << 4) | nibble] * 7)
    return bytes(head) + frame


def asset(channels=1):
    fmta = bytes([channels]) + (4 if channels == 1 else 3).to_bytes(4, 'big')
    data = b''.join(channel(index + 1) for index in range(channels))
    body = chunk('FMTA', fmta) + chunk('DATA', data)
    root = bytearray(32)
    root[:4] = b'RFRM'
    root[4:12] = len(body).to_bytes(8, 'big')
    root[20:24] = b'CSMP'
    return bytes(root) + body


class UiAudioCodecTests(unittest.TestCase):
    def test_decodes_mono_dsp_frame(self):
        channels, info = codec.decode_csmp_pcm(asset(1))
        self.assertEqual(info.source_channels, 1)
        self.assertEqual(info.sample_rate, 32000)
        self.assertEqual(info.sample_count, 14)
        self.assertEqual(channels[0], [1] * 14)

    def test_decodes_and_interleaves_stereo_wav(self):
        wav_bytes, info = codec.decode_csmp_to_wav(asset(2))
        self.assertEqual(info.output_channels, 2)
        with wave.open(io.BytesIO(wav_bytes), 'rb') as handle:
            self.assertEqual(handle.getnchannels(), 2)
            self.assertEqual(handle.getframerate(), 32000)
            self.assertEqual(handle.getnframes(), 14)
            left, right = struct.unpack_from('<hh', handle.readframes(1))
        self.assertEqual((left, right), (1, 2))

    def test_volume_is_bounded(self):
        wav_bytes, _info = codec.decode_csmp_to_wav(asset(1), volume=0.5)
        with wave.open(io.BytesIO(wav_bytes), 'rb') as handle:
            value = struct.unpack('<h', handle.readframes(1))[0]
        self.assertEqual(value, 0)

    def test_rejects_truncated_channel(self):
        broken = asset(1)[:-4]
        with self.assertRaises(codec.UiAudioDecodeError):
            codec.decode_csmp_pcm(broken)


if __name__ == '__main__':
    unittest.main()
