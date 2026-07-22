"""Decode Tropical Freeze CSMP DSP-ADPCM samples into standard PCM WAV bytes.

The decoder is intentionally read-only.  It accepts the internal RFRM/CSMP wrapper used
inside PAK files (and the raw CSMP interchange form supported by ``csmp_codec``), validates
all channel headers and emits bounded 16-bit PCM suitable for preview/export.
"""
from __future__ import annotations

from dataclasses import dataclass
import io
import struct
import wave

import csmp_codec


class UiAudioDecodeError(Exception):
    pass


_MAX_CHANNELS = 4
_MAX_SAMPLES_PER_CHANNEL = 20_000_000
_MAX_PCM_BYTES = 256 * 1024 * 1024
_DSP_HEADER_SIZE = 0x60


@dataclass(frozen=True)
class DspChannelInfo:
    sample_count: int
    nibble_count: int
    sample_rate: int
    loop: bool
    loop_start: int
    loop_end: int
    current_address: int
    coefficients: tuple[int, ...]
    gain: int
    initial_predictor_scale: int
    initial_history_1: int
    initial_history_2: int


@dataclass(frozen=True)
class DecodedCsmpInfo:
    source_channels: int
    output_channels: int
    sample_rate: int
    sample_count: int
    duration_seconds: float
    loop: bool
    format_code: int
    label_count: int = 0


def _le16(data: bytes, offset: int, signed: bool = False) -> int:
    end = offset + 2
    if offset < 0 or end > len(data):
        raise UiAudioDecodeError("DSP-Header ist abgeschnitten")
    return int.from_bytes(data[offset:end], "little", signed=signed)


def _le32(data: bytes, offset: int) -> int:
    end = offset + 4
    if offset < 0 or end > len(data):
        raise UiAudioDecodeError("DSP-Header ist abgeschnitten")
    return int.from_bytes(data[offset:end], "little")


def _chunks(asset: bytes):
    try:
        if csmp_codec.is_internal_csmp_asset(asset):
            return tuple(csmp_codec.parse_internal_csmp_asset(asset)["chunks"])
        if csmp_codec.is_raw_csmp(asset):
            parsed = csmp_codec.parse_raw_csmp(asset)
            return tuple({"tag": item["tag"], "payload": item["payload"]} for item in parsed["chunks"])
    except Exception as exc:
        raise UiAudioDecodeError(str(exc)) from exc
    raise UiAudioDecodeError("Keine unterstützte CSMP-Ressource")


def _parse_channel(block: bytes) -> DspChannelInfo:
    if len(block) < _DSP_HEADER_SIZE:
        raise UiAudioDecodeError("CSMP-DATA-Kanal ist kleiner als der DSP-Header")
    sample_count = _le32(block, 0x00)
    nibble_count = _le32(block, 0x04)
    sample_rate = _le32(block, 0x08)
    loop_flag = _le16(block, 0x0C)
    format_code = _le16(block, 0x0E)
    if format_code not in (0,):
        raise UiAudioDecodeError(f"Nicht unterstütztes DSP-Format {format_code}")
    if not (1 <= sample_count <= _MAX_SAMPLES_PER_CHANNEL):
        raise UiAudioDecodeError(f"Unplausible Sample-Anzahl {sample_count}")
    if not (4000 <= sample_rate <= 192000):
        raise UiAudioDecodeError(f"Unplausible Sample-Rate {sample_rate}")
    if nibble_count < 2:
        raise UiAudioDecodeError("DSP-Nibble-Anzahl ist ungültig")
    coefficients = tuple(_le16(block, 0x1C + index * 2, signed=True) for index in range(16))
    return DspChannelInfo(
        sample_count=sample_count,
        nibble_count=nibble_count,
        sample_rate=sample_rate,
        loop=bool(loop_flag),
        loop_start=_le32(block, 0x10),
        loop_end=_le32(block, 0x14),
        current_address=_le32(block, 0x18),
        coefficients=coefficients,
        gain=_le16(block, 0x3C),
        initial_predictor_scale=_le16(block, 0x3E),
        initial_history_1=_le16(block, 0x40, signed=True),
        initial_history_2=_le16(block, 0x42, signed=True),
    )


def _decode_channel(block: bytes, info: DspChannelInfo) -> list[int]:
    encoded = memoryview(block)[_DSP_HEADER_SIZE:]
    required_frames = (info.sample_count + 13) // 14
    required_bytes = required_frames * 8
    if required_bytes > len(encoded):
        raise UiAudioDecodeError(
            f"DSP-Daten abgeschnitten: benötigt {required_bytes}, vorhanden {len(encoded)}"
        )
    history_1 = int(info.initial_history_1)
    history_2 = int(info.initial_history_2)
    output: list[int] = []
    for frame_index in range(required_frames):
        frame = encoded[frame_index * 8:(frame_index + 1) * 8]
        predictor_scale = int(frame[0])
        predictor = (predictor_scale >> 4) & 0x0F
        exponent = predictor_scale & 0x0F
        coefficient_index = predictor * 2
        if coefficient_index + 1 >= len(info.coefficients):
            raise UiAudioDecodeError(f"DSP-Prädiktor {predictor} liegt außerhalb der Koeffiziententabelle")
        coefficient_1 = info.coefficients[coefficient_index]
        coefficient_2 = info.coefficients[coefficient_index + 1]
        scale = 1 << exponent
        for sample_index in range(14):
            packed = int(frame[1 + sample_index // 2])
            nibble = (packed >> 4) if sample_index % 2 == 0 else (packed & 0x0F)
            if nibble >= 8:
                nibble -= 16
            value = (
                ((nibble * scale) << 11)
                + 1024
                + coefficient_1 * history_1
                + coefficient_2 * history_2
            ) >> 11
            value = max(-32768, min(32767, int(value)))
            output.append(value)
            history_2, history_1 = history_1, value
            if len(output) >= info.sample_count:
                return output
    return output


def _label_count(payload: bytes) -> int:
    # LABL currently matters only as diagnostics.  Each known record is 16 bytes and the
    # first four bytes are a float timestamp, followed by an integer label identifier.
    return len(payload) // 16 if payload else 0


def decode_csmp_pcm(asset: bytes, output_channels: int | None = None):
    chunks = _chunks(bytes(asset))
    fmta = next((bytes(item["payload"]) for item in chunks if item["tag"] == "FMTA"), None)
    data = next((bytes(item["payload"]) for item in chunks if item["tag"] == "DATA"), None)
    labels = next((bytes(item["payload"]) for item in chunks if item["tag"] == "LABL"), b"")
    if fmta is None or len(fmta) < 5:
        raise UiAudioDecodeError("CSMP enthält keinen gültigen FMTA-Chunk")
    if data is None:
        raise UiAudioDecodeError("CSMP enthält keinen DATA-Chunk")
    source_channels = int(fmta[0])
    format_code = int.from_bytes(fmta[1:5], "big")
    if not (1 <= source_channels <= _MAX_CHANNELS):
        raise UiAudioDecodeError(f"Nicht unterstützte Kanalzahl {source_channels}")
    if len(data) % source_channels:
        raise UiAudioDecodeError("CSMP-DATA lässt sich nicht gleichmäßig auf Kanäle verteilen")
    stride = len(data) // source_channels
    if stride < _DSP_HEADER_SIZE:
        raise UiAudioDecodeError("CSMP-Kanalblock ist zu klein")
    infos = []
    channels = []
    for channel_index in range(source_channels):
        block = data[channel_index * stride:(channel_index + 1) * stride]
        info = _parse_channel(block)
        infos.append(info)
        channels.append(_decode_channel(block, info))
    sample_rate = infos[0].sample_rate
    sample_count = infos[0].sample_count
    for info in infos[1:]:
        if info.sample_rate != sample_rate or info.sample_count != sample_count:
            raise UiAudioDecodeError("CSMP-Kanäle besitzen unterschiedliche Formate")
    if sample_count * max(1, source_channels) * 2 > _MAX_PCM_BYTES:
        raise UiAudioDecodeError("Dekodierte CSMP-Daten überschreiten das Speicherlimit")

    wanted = int(output_channels or (1 if source_channels == 1 else 2))
    wanted = 1 if wanted <= 1 else 2
    if wanted == 1:
        if source_channels == 1:
            output = channels
        else:
            output = [[int(sum(values) / len(values)) for values in zip(*channels)]]
    elif source_channels == 1:
        output = [channels[0], channels[0]]
    elif source_channels == 2:
        output = channels
    else:
        left_sources = channels[0::2]
        right_sources = channels[1::2] or channels[0::2]
        left = [int(sum(values) / len(values)) for values in zip(*left_sources)]
        right = [int(sum(values) / len(values)) for values in zip(*right_sources)]
        output = [left, right]

    info = DecodedCsmpInfo(
        source_channels=source_channels,
        output_channels=len(output),
        sample_rate=sample_rate,
        sample_count=sample_count,
        duration_seconds=sample_count / float(sample_rate),
        loop=any(item.loop for item in infos),
        format_code=format_code,
        label_count=_label_count(labels),
    )
    return output, info


def pcm_to_wav(channels: list[list[int]], sample_rate: int, volume: float = 1.0) -> bytes:
    if not channels or not channels[0]:
        raise UiAudioDecodeError("Keine PCM-Samples vorhanden")
    count = len(channels[0])
    if any(len(channel) != count for channel in channels):
        raise UiAudioDecodeError("PCM-Kanäle besitzen unterschiedliche Längen")
    volume = max(0.0, min(2.0, float(volume)))
    interleaved = bytearray(count * len(channels) * 2)
    offset = 0
    for index in range(count):
        for channel in channels:
            value = max(-32768, min(32767, int(round(channel[index] * volume))))
            struct.pack_into("<h", interleaved, offset, value)
            offset += 2
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(len(channels))
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(interleaved)
    return output.getvalue()


def decode_csmp_to_wav(asset: bytes, volume: float = 1.0, output_channels: int | None = None):
    channels, info = decode_csmp_pcm(asset, output_channels=output_channels)
    return pcm_to_wav(channels, info.sample_rate, volume=volume), info
