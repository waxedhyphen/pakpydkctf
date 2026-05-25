import array
import math
import os
import queue
import struct
import sys
import tempfile
import threading
import traceback
import wave
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

def clamp16(value):
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return int(value)

def get_wav_info(path):
    with wave.open(path, 'rb') as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        comp_type = wav_file.getcomptype()
    if comp_type != 'NONE':
        raise ValueError('Nur unkomprimierte WAV-Dateien werden unterstützt.')
    if sample_width != 2:
        raise ValueError('Nur 16-Bit-PCM-WAV-Dateien werden unterstützt.')
    if channels not in (1, 2):
        raise ValueError('Vorerst werden nur Mono- und Stereo-WAV-Dateien unterstützt.')
    return channels, sample_rate, frame_count

def read_pcm_chunk_as_int16(raw):
    values = array.array('h')
    values.frombytes(raw)
    if sys.byteorder != 'little':
        values.byteswap()
    return values

def solve_ar2(segment):
    if len(segment) < 3:
        return None
    s11 = 0.0
    s12 = 0.0
    s22 = 0.0
    b1 = 0.0
    b2 = 0.0
    for index in range(2, len(segment)):
        x1 = float(segment[index - 1])
        x2 = float(segment[index - 2])
        y = float(segment[index])
        s11 += x1 * x1
        s12 += x1 * x2
        s22 += x2 * x2
        b1 += x1 * y
        b2 += x2 * y
    det = s11 * s22 - s12 * s12
    if abs(det) < 1e-9:
        return None
    a1 = (b1 * s22 - b2 * s12) / det
    a2 = (s11 * b2 - s12 * b1) / det
    c1 = max(-4096.0, min(4095.0, a1 * 2048.0))
    c2 = max(-4096.0, min(4095.0, a2 * 2048.0))
    return c1, c2

def finalize_coefficient_pairs(candidates, weights):
    if not candidates:
        return [(0, 0)] * 8
    cluster_count = min(7, len(candidates))
    if cluster_count == 1:
        centroids = [list(candidates[0])]
    else:
        centroids = []
        for index in range(cluster_count):
            source_index = round(index * (len(candidates) - 1) / (cluster_count - 1))
            centroids.append(list(candidates[source_index]))
    for _ in range(24):
        groups = [[] for _ in range(cluster_count)]
        group_weights = [[] for _ in range(cluster_count)]
        for candidate, weight in zip(candidates, weights):
            best_index = 0
            best_distance = None
            for centroid_index, centroid in enumerate(centroids):
                distance = (candidate[0] - centroid[0]) ** 2 + (candidate[1] - centroid[1]) ** 2
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_index = centroid_index
            groups[best_index].append(candidate)
            group_weights[best_index].append(weight)
        changed = False
        for centroid_index in range(cluster_count):
            if not groups[centroid_index]:
                continue
            weight_sum = sum(group_weights[centroid_index])
            new_c1 = sum(pair[0] * weight for pair, weight in zip(groups[centroid_index], group_weights[centroid_index])) / weight_sum
            new_c2 = sum(pair[1] * weight for pair, weight in zip(groups[centroid_index], group_weights[centroid_index])) / weight_sum
            if abs(centroids[centroid_index][0] - new_c1) > 1e-3 or abs(centroids[centroid_index][1] - new_c2) > 1e-3:
                centroids[centroid_index] = [new_c1, new_c2]
                changed = True
        if not changed:
            break
    coefficient_pairs = [(0, 0)]
    for c1, c2 in centroids:
        pair = (int(round(c1)), int(round(c2)))
        if pair not in coefficient_pairs:
            coefficient_pairs.append(pair)
    while len(coefficient_pairs) < 8:
        coefficient_pairs.append((0, 0))
    return coefficient_pairs[:8]

def estimate_dsp_coefficients_from_wav(path, progress_callback=None, progress_start=0.0, progress_end=35.0):
    channels, _, frame_count = get_wav_info(path)
    window_size = 1024
    hop_size = 512
    chunk_frames = 32768
    states = []
    for _ in range(channels):
        states.append({'buffer': [], 'candidates': [], 'weights': []})
    processed_frames = 0
    with wave.open(path, 'rb') as wav_file:
        while processed_frames < frame_count:
            frames_to_read = min(chunk_frames, frame_count - processed_frames)
            raw = wav_file.readframes(frames_to_read)
            if not raw:
                break
            values = read_pcm_chunk_as_int16(raw)
            if channels == 1:
                per_channel = [values]
            else:
                per_channel = [values[channel_index::channels] for channel_index in range(channels)]
            for channel_index in range(channels):
                state = states[channel_index]
                state['buffer'].extend(per_channel[channel_index])
                while len(state['buffer']) >= window_size:
                    segment = state['buffer'][:window_size]
                    energy = sum(float(sample) * float(sample) for sample in segment) / len(segment)
                    if energy >= 1.0:
                        coeffs = solve_ar2(segment)
                        if coeffs is not None:
                            state['candidates'].append(coeffs)
                            state['weights'].append(energy)
                    del state['buffer'][:hop_size]
            processed_frames += frames_to_read
            if progress_callback and frame_count:
                progress = progress_start + (progress_end - progress_start) * (processed_frames / frame_count)
                progress_callback(progress, f'Analyse läuft... {processed_frames:,} / {frame_count:,} Frames')
    coefficient_pairs_per_channel = []
    for state in states:
        if state['buffer']:
            segment = state['buffer'][-min(window_size, len(state['buffer'])):]
            if len(segment) >= 32:
                energy = sum(float(sample) * float(sample) for sample in segment) / len(segment)
                coeffs = solve_ar2(segment)
                if coeffs is not None:
                    state['candidates'].append(coeffs)
                    state['weights'].append(max(energy, 1.0))
        coefficient_pairs_per_channel.append(finalize_coefficient_pairs(state['candidates'], state['weights']))
    return coefficient_pairs_per_channel

def encode_frame(samples, hist1, hist2, coefficient_pairs):
    best_error = None
    best_predictor_index = 0
    best_shift = 0
    best_nibbles = None
    best_last1 = hist1
    best_last2 = hist2
    frame_samples = [int(sample) for sample in samples]
    for predictor_index, (coef1, coef2) in enumerate(coefficient_pairs):
        approx_last1 = hist1
        approx_last2 = hist2
        peak = 0
        for sample in frame_samples:
            predicted = (coef1 * approx_last1 + coef2 * approx_last2 + 1024) >> 11
            diff = abs(sample - predicted)
            if diff > peak:
                peak = diff
            approx_last2, approx_last1 = approx_last1, sample
        base_shift = 0 if peak == 0 else max(0, min(13, (peak.bit_length() - 1) - 2))
        shift_candidates = {base_shift}
        if base_shift > 0:
            shift_candidates.add(base_shift - 1)
        if base_shift < 13:
            shift_candidates.add(base_shift + 1)
        shift_candidates.add(0)
        shift_candidates.add(13)
        for shift in sorted(shift_candidates):
            last1 = hist1
            last2 = hist2
            total_error = 0
            nibbles = []
            for sample in frame_samples:
                predicted = (coef1 * last1 + coef2 * last2 + 1024) >> 11
                step = 1 << shift
                nibble = int(round((sample - predicted) / step))
                if nibble < -8:
                    nibble = -8
                elif nibble > 7:
                    nibble = 7
                reconstructed = clamp16(predicted + (nibble << shift))
                diff = sample - reconstructed
                total_error += diff * diff
                if best_error is not None and total_error >= best_error:
                    break
                nibbles.append(nibble & 0x0F)
                last2, last1 = last1, reconstructed
            else:
                if best_error is None or total_error < best_error:
                    best_error = total_error
                    best_predictor_index = predictor_index
                    best_shift = shift
                    best_nibbles = nibbles
                    best_last1 = last1
                    best_last2 = last2
    payload = bytearray([((best_predictor_index & 0x0F) << 4) | (best_shift & 0x0F)])
    for index in range(0, 14, 2):
        payload.append(((best_nibbles[index] & 0x0F) << 4) | (best_nibbles[index + 1] & 0x0F))
    return bytes(payload), best_last1, best_last2

def get_dsp_nibble_count(sample_count):
    whole_frames, remainder = divmod(sample_count, 14)
    if sample_count == 0:
        return 0
    return whole_frames * 16 + (16 if remainder == 0 else remainder + 2)

def get_encoded_audio_size(sample_count):
    if sample_count <= 0:
        return 0
    return math.ceil(sample_count / 14) * 8

def sample_to_nibble(sample):
    frame = sample // 14
    frame_sample = sample % 14
    return frame * 16 + 2 + frame_sample


def build_dsp_header(sample_count, sample_rate, coefficient_pairs, loop_start_sample=0, loop_end_sample=0):
    nibble_count = get_dsp_nibble_count(sample_count)
    header = bytearray(0x60)
    struct.pack_into('<I', header, 0x00, sample_count)
    struct.pack_into('<I', header, 0x04, nibble_count)
    struct.pack_into('<I', header, 0x08, sample_rate)
    loop_flag = 1 if loop_end_sample > loop_start_sample else 0
    struct.pack_into('<H', header, 0x0C, loop_flag)
    struct.pack_into('<H', header, 0x0E, 0)
    if loop_flag:
        struct.pack_into('<I', header, 0x10, sample_to_nibble(loop_start_sample))
        struct.pack_into('<I', header, 0x14, sample_to_nibble(loop_end_sample))
    else:
        struct.pack_into('<I', header, 0x10, 2 if sample_count else 0)
        struct.pack_into('<I', header, 0x14, max(0, nibble_count - 1))
    struct.pack_into('<I', header, 0x18, 2 if sample_count else 0)
    offset = 0x1C
    for coef1, coef2 in coefficient_pairs:
        struct.pack_into('<h', header, offset, coef1)
        offset += 2
        struct.pack_into('<h', header, offset, coef2)
        offset += 2
    return bytes(header)

def get_channel_block_size(sample_count):
    size = 0x60 + get_encoded_audio_size(sample_count)
    remainder = size % 0x40
    if remainder:
        size += 0x40 - remainder
    return size

def copy_file_object(source_file, target_file, chunk_size=1024 * 1024):
    while True:
        chunk = source_file.read(chunk_size)
        if not chunk:
            break
        target_file.write(chunk)

def convert_wav_to_csmp(source_path, target_path, progress_callback=None, loop_start_sample=0, loop_end_sample=0):
    channels, sample_rate, frame_count = get_wav_info(source_path)
    coefficient_pairs_per_channel = estimate_dsp_coefficients_from_wav(source_path, progress_callback, 0.0, 35.0)
    chunk_frames = 32768
    temp_paths = []
    temp_files = []
    channel_states = []
    try:
        for _ in range(channels):
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_paths.append(temp_file.name)
            temp_files.append(temp_file)
            channel_states.append({'hist1': 0, 'hist2': 0, 'pending': []})
        processed_frames = 0
        with wave.open(source_path, 'rb') as wav_file:
            while processed_frames < frame_count:
                frames_to_read = min(chunk_frames, frame_count - processed_frames)
                raw = wav_file.readframes(frames_to_read)
                if not raw:
                    break
                values = read_pcm_chunk_as_int16(raw)
                if channels == 1:
                    state = channel_states[0]
                    pending = state['pending']
                    for sample in values:
                        pending.append(int(sample))
                        if len(pending) == 14:
                            payload, state['hist1'], state['hist2'] = encode_frame(pending, state['hist1'], state['hist2'], coefficient_pairs_per_channel[0])
                            temp_files[0].write(payload)
                            pending.clear()
                else:
                    for index in range(0, len(values), channels):
                        for channel_index in range(channels):
                            state = channel_states[channel_index]
                            pending = state['pending']
                            pending.append(int(values[index + channel_index]))
                            if len(pending) == 14:
                                payload, state['hist1'], state['hist2'] = encode_frame(pending, state['hist1'], state['hist2'], coefficient_pairs_per_channel[channel_index])
                                temp_files[channel_index].write(payload)
                                pending.clear()
                processed_frames += frames_to_read
                if progress_callback and frame_count:
                    progress = 35.0 + 55.0 * (processed_frames / frame_count)
                    progress_callback(progress, f'Kodierung läuft... {processed_frames:,} / {frame_count:,} Frames')
        for channel_index in range(channels):
            state = channel_states[channel_index]
            if state['pending']:
                padded = state['pending'] + [0] * (14 - len(state['pending']))
                payload, state['hist1'], state['hist2'] = encode_frame(padded, state['hist1'], state['hist2'], coefficient_pairs_per_channel[channel_index])
                temp_files[channel_index].write(payload)
            temp_files[channel_index].flush()
            temp_files[channel_index].close()
        fmta_channel_map = {1: 1, 2: 3}
        channel_block_size = get_channel_block_size(frame_count)
        data_payload_size = channel_block_size * channels
        fmta_payload = bytes([channels, 0, 0, 0, fmta_channel_map[channels]])
        chunks_size = (0x18 + len(fmta_payload)) + (0x18 + data_payload_size)
        total_size = 0x20 + chunks_size
        with open(target_path, 'wb') as target_file:
            target_file.write(b'RFRM')
            target_file.write(b'\x00' * 4)
            target_file.write(struct.pack('>I', total_size - 0x20))
            target_file.write(b'\x00' * 8)
            target_file.write(b'CSMP')
            target_file.write(struct.pack('>I', 0x12))
            target_file.write(struct.pack('>I', 0x12))
            target_file.write(b'FMTA')
            target_file.write(b'\x00' * 4)
            target_file.write(struct.pack('>I', len(fmta_payload)))
            target_file.write(b'\x00' * 12)
            target_file.write(fmta_payload)
            target_file.write(b'DATA')
            target_file.write(b'\x00' * 4)
            target_file.write(struct.pack('>I', data_payload_size))
            target_file.write(b'\x00' * 12)
            for channel_index in range(channels):
                if progress_callback:
                    progress_callback(90.0 + 10.0 * (channel_index / max(1, channels)), f'Ausgabe wird geschrieben... Kanal {channel_index + 1} / {channels}')
                target_file.write(build_dsp_header(frame_count, sample_rate, coefficient_pairs_per_channel[channel_index], loop_start_sample, loop_end_sample))
                with open(temp_paths[channel_index], 'rb') as temp_file:
                    copy_file_object(temp_file, target_file)
                written_size = 0x60 + get_encoded_audio_size(frame_count)
                padding_size = channel_block_size - written_size
                if padding_size > 0:
                    target_file.write(b'\x00' * padding_size)
        if progress_callback:
            progress_callback(100.0, 'Fertig.')
        return channels, sample_rate, frame_count, os.path.getsize(target_path)
    finally:
        for temp_file in temp_files:
            try:
                temp_file.close()
            except Exception:
                pass
        for temp_path in temp_paths:
            try:
                os.remove(temp_path)
            except Exception:
                pass

def signed_nibble(value):
    return value - 16 if value >= 8 else value

def read_s16(data, offset, little_endian):
    return struct.unpack_from('<h' if little_endian else '>h', data, offset)[0]

def read_u32(data, offset, little_endian):
    return struct.unpack_from('<I' if little_endian else '>I', data, offset)[0]

def decode_dsp_channel(encoded_audio, sample_count, coefficients, hist1, hist2, progress_callback=None, progress_start=0.0, progress_end=100.0):
    pcm = array.array('h')
    offset = 0
    decoded_samples = 0
    total_frames = math.ceil(sample_count / 14) if sample_count else 0
    current_frame = 0
    while decoded_samples < sample_count:
        if offset + 8 > len(encoded_audio):
            raise ValueError('CSMP-Audiodaten sind unvollständig.')
        header = encoded_audio[offset]
        offset += 1
        predictor_index = (header >> 4) & 0x0F
        shift = header & 0x0F
        coef1 = coefficients[predictor_index * 2]
        coef2 = coefficients[predictor_index * 2 + 1]
        for _ in range(7):
            byte_value = encoded_audio[offset]
            offset += 1
            for nibble_value in ((byte_value >> 4) & 0x0F, byte_value & 0x0F):
                sample = clamp16(((((signed_nibble(nibble_value) << shift) << 11) + 1024) + (coef1 * hist1) + (coef2 * hist2)) >> 11)
                hist2, hist1 = hist1, sample
                pcm.append(sample)
                decoded_samples += 1
                if decoded_samples >= sample_count:
                    break
            if decoded_samples >= sample_count:
                break
        current_frame += 1
        if progress_callback and total_frames and current_frame % 512 == 0:
            progress = progress_start + (progress_end - progress_start) * (current_frame / total_frames)
            progress_callback(progress, f'Dekodierung läuft... {decoded_samples:,} / {sample_count:,} Samples')
    return pcm

def parse_csmp(path, progress_callback=None):
    with open(path, 'rb') as source_file:
        data = source_file.read()
    if len(data) < 0x20:
        raise ValueError('Datei ist zu klein.')
    if data[0:4] != b'RFRM':
        raise ValueError('Ungültige Datei. RFRM fehlt.')
    if data[0x14:0x18] != b'CSMP':
        raise ValueError('Ungültige Datei. CSMP fehlt.')
    version_be = struct.unpack_from('>I', data, 0x18)[0]
    if version_be not in (0x0A, 0x11, 0x12):
        raise ValueError(f'Diese Rückwandlung unterstützt hier nur CSMP-Version 0x0A, 0x11 und 0x12. Gefunden: 0x{version_be:02X}')
    little_endian = version_be in (0x11, 0x12)
    fmta_offset = None
    data_offset = None
    data_size = None
    chunk_offset = 0x20
    while chunk_offset + 0x18 <= len(data):
        chunk_type = data[chunk_offset:chunk_offset + 4]
        chunk_size = struct.unpack_from('>I', data, chunk_offset + 0x08)[0]
        if chunk_type == b'FMTA':
            fmta_offset = chunk_offset + 0x18
        elif chunk_type == b'DATA':
            data_offset = chunk_offset + 0x18
            data_size = chunk_size
            break
        chunk_offset += 0x18 + chunk_size
    if fmta_offset is None or data_offset is None or data_size is None:
        raise ValueError('FMTA- oder DATA-Block wurde nicht gefunden.')
    channels = data[fmta_offset]
    if channels <= 0:
        raise ValueError('Ungültige Kanalzahl in CSMP.')
    if channels > 8:
        raise ValueError('Zu viele Kanäle für diese einfache Rückwandlung.')
    align = 0x03 if version_be == 0x0A else 0x00
    header_offset = data_offset + align
    data_size -= align
    if data_size <= 0:
        raise ValueError('Ungültige DATA-Größe.')
    if data_size % channels != 0:
        raise ValueError('DATA-Größe passt nicht zur Kanalzahl.')
    channel_block_size = data_size // channels
    sample_count = read_u32(data, header_offset + 0x00, little_endian)
    sample_rate = read_u32(data, header_offset + 0x08, little_endian)
    pcm = []
    for channel_index in range(channels):
        block_offset = header_offset + channel_index * channel_block_size
        channel_sample_count = read_u32(data, block_offset + 0x00, little_endian)
        channel_sample_rate = read_u32(data, block_offset + 0x08, little_endian)
        if channel_sample_count != sample_count:
            raise ValueError('Die Kanalblöcke haben unterschiedliche Sample-Anzahlen.')
        if channel_sample_rate != sample_rate:
            raise ValueError('Die Kanalblöcke haben unterschiedliche Sampleraten.')
        coefficients = []
        for coefficient_offset in range(0x1C, 0x3C, 2):
            coefficients.append(read_s16(data, block_offset + coefficient_offset, little_endian))
        hist1 = read_s16(data, block_offset + 0x40, little_endian)
        hist2 = read_s16(data, block_offset + 0x42, little_endian)
        audio_offset = block_offset + 0x60
        audio_end = block_offset + channel_block_size
        encoded_audio = data[audio_offset:audio_end]
        start = 5.0 + (70.0 * channel_index / max(1, channels))
        end = 5.0 + (70.0 * (channel_index + 1) / max(1, channels))
        pcm.append(decode_dsp_channel(encoded_audio, sample_count, coefficients, hist1, hist2, progress_callback, start, end))
    return channels, sample_rate, sample_count, pcm

def write_wav_pcm16(path, sample_rate, pcm, progress_callback=None, progress_start=75.0, progress_end=100.0):
    channels = len(pcm)
    if channels == 0:
        raise ValueError('Keine Audiodaten vorhanden.')
    frame_count = len(pcm[0])
    for channel in pcm:
        if len(channel) != frame_count:
            raise ValueError('Die Kanäle haben unterschiedliche Längen.')
    chunk_frames = 32768
    with wave.open(path, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        written_frames = 0
        while written_frames < frame_count:
            end = min(written_frames + chunk_frames, frame_count)
            interleaved = array.array('h')
            if channels == 1:
                interleaved.extend(pcm[0][written_frames:end])
            else:
                for frame_index in range(written_frames, end):
                    for channel_index in range(channels):
                        interleaved.append(clamp16(pcm[channel_index][frame_index]))
            if sys.byteorder != 'little':
                interleaved.byteswap()
            wav_file.writeframes(interleaved.tobytes())
            written_frames = end
            if progress_callback and frame_count:
                progress = progress_start + (progress_end - progress_start) * (written_frames / frame_count)
                progress_callback(progress, f'WAV wird geschrieben... {written_frames:,} / {frame_count:,} Frames')
    return channels, sample_rate, frame_count, os.path.getsize(path)

def convert_csmp_to_wav(source_path, target_path, progress_callback=None):
    if progress_callback:
        progress_callback(0.0, 'CSMP wird gelesen...')
    channels, sample_rate, frame_count, pcm = parse_csmp(source_path, progress_callback)
    result = write_wav_pcm16(target_path, sample_rate, pcm, progress_callback, 75.0, 100.0)
    if progress_callback:
        progress_callback(100.0, 'Fertig.')
    return result

def get_mode_from_path(path):
    extension = os.path.splitext(path)[1].lower()
    if extension == '.wav':
        return 'wav_to_csmp'
    if extension == '.csmp':
        return 'csmp_to_wav'
    return ''

class App:
    def __init__(self, root):
        self.root = root
        self.root.title('WAV <-> CSMP')
        self.root.geometry('820x420')
        self.root.resizable(True, True)
        self.source_path = ''
        self.target_path = ''
        self.worker_thread = None
        self.progress_queue = queue.Queue()
        self.status_text = tk.StringVar(value='1. WAV oder CSMP auswählen. 2. Zielpfad wählen. 3. Auf Umwandeln klicken.')
        self.source_text = tk.StringVar(value='Keine Quelldatei ausgewählt.')
        self.target_text = tk.StringVar(value='Keine Zieldatei ausgewählt.')
        self.info_text = tk.StringVar(value='Wird automatisch erkannt: WAV wird zu CSMP, CSMP wird zu WAV.')
        self.progress_text = tk.StringVar(value='Bereit.')
        self.progress_value = tk.DoubleVar(value=0.0)
        outer = tk.Frame(root, padx=18, pady=18)
        outer.pack(fill='both', expand=True)
        tk.Label(outer, text='WAV <-> CSMP Konverter', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        tk.Label(outer, textvariable=self.status_text, justify='left', wraplength=760, pady=10, font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(outer, textvariable=self.info_text, justify='left', wraplength=760, pady=6, font=('Segoe UI', 9)).pack(anchor='w')
        box1 = tk.LabelFrame(outer, text='Quelle', padx=10, pady=10)
        box1.pack(fill='x', pady=(12, 8))
        self.source_button = tk.Button(box1, text='Datei auswählen', width=24, command=self.choose_source)
        self.source_button.pack(anchor='w')
        tk.Label(box1, textvariable=self.source_text, justify='left', wraplength=740, pady=8).pack(anchor='w')
        box2 = tk.LabelFrame(outer, text='Ziel', padx=10, pady=10)
        box2.pack(fill='x', pady=8)
        self.target_button = tk.Button(box2, text='Zieldatei auswählen', width=24, command=self.choose_target)
        self.target_button.pack(anchor='w')
        tk.Label(box2, textvariable=self.target_text, justify='left', wraplength=740, pady=8).pack(anchor='w')
        box_loop = tk.LabelFrame(outer, text='Loop-Punkte (optional, in Sekunden)', padx=10, pady=10)
        box_loop.pack(fill='x', pady=8)
        loop_row = tk.Frame(box_loop)
        loop_row.pack(fill='x')
        self.loop_enabled_var = tk.BooleanVar(value=False)
        tk.Checkbutton(loop_row, text='Loop aktivieren', variable=self.loop_enabled_var, command=self.on_loop_toggle).pack(side='left')
        tk.Label(loop_row, text='Start (s):').pack(side='left', padx=(16, 4))
        self.loop_start_var = tk.StringVar(value='0.0')
        self.loop_start_entry = tk.Entry(loop_row, textvariable=self.loop_start_var, width=12, state='disabled')
        self.loop_start_entry.pack(side='left')
        tk.Label(loop_row, text='Ende (s):').pack(side='left', padx=(16, 4))
        self.loop_end_var = tk.StringVar(value='0.0')
        self.loop_end_entry = tk.Entry(loop_row, textvariable=self.loop_end_var, width=12, state='disabled')
        self.loop_end_entry.pack(side='left')
        self.loop_info_var = tk.StringVar(value='')
        tk.Label(box_loop, textvariable=self.loop_info_var, justify='left', wraplength=740, pady=4).pack(anchor='w')
        box3 = tk.LabelFrame(outer, text='Fortschritt', padx=10, pady=10)
        box3.pack(fill='x', pady=8)
        self.progress_bar = ttk.Progressbar(box3, variable=self.progress_value, maximum=100, mode='determinate')
        self.progress_bar.pack(fill='x')
        tk.Label(box3, textvariable=self.progress_text, justify='left', wraplength=740, pady=8).pack(anchor='w')
        button_row = tk.Frame(outer)
        button_row.pack(fill='x', pady=(16, 0))
        self.convert_button = tk.Button(button_row, text='Umwandeln und speichern', width=24, command=self.convert)
        self.convert_button.pack(side='left')
        tk.Button(button_row, text='Beenden', width=14, command=self.root.destroy).pack(side='left', padx=10)

    def choose_source(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        path = filedialog.askopenfilename(title='Quelldatei auswählen', filetypes=[('Audio-Dateien', '*.wav *.csmp'), ('WAV-Dateien', '*.wav'), ('CSMP-Dateien', '*.csmp'), ('Alle Dateien', '*.*')])
        if not path:
            return
        mode = get_mode_from_path(path)
        if not mode:
            messagebox.showerror('Fehler', 'Bitte eine WAV- oder CSMP-Datei auswählen.')
            return
        self.source_path = path
        self.source_text.set(path)
        source_base = os.path.splitext(path)[0]
        self.target_path = source_base + ('.csmp' if mode == 'wav_to_csmp' else '.wav')
        self.target_text.set(self.target_path)
        self.progress_value.set(0.0)
        self.progress_text.set('Bereit.')
        self.loop_info_var.set('')
        if mode == 'csmp_to_wav':
            try:
                from soundpreview import parse_csmp_bytes
                csmp_data = open(path, 'rb').read()
                info = parse_csmp_bytes(csmp_data)
                parts = [f'Dauer: {info["duration"]:.2f}s | {info["channels"]} Kanäle | {info["sample_rate"]} Hz']
                if info.get('loop_flag') and info['sample_rate'] > 0:
                    sr = info['sample_rate']
                    ls = info['loop_start_sample']
                    le = info['loop_end_sample']
                    parts.append(f'Loop: {ls/sr:.4f}s - {le/sr:.4f}s (Länge: {(le-ls)/sr:.4f}s)')
                else:
                    parts.append('Loop: nein')
                self.loop_info_var.set(' | '.join(parts))
            except Exception:
                pass
        if mode == 'wav_to_csmp':
            self.status_text.set('WAV gesetzt. Jetzt Zielpfad für CSMP wählen oder direkt auf Umwandeln klicken.')
        else:
            self.status_text.set('CSMP gesetzt. Jetzt Zielpfad für WAV wählen oder direkt auf Umwandeln klicken.')

    def choose_target(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self.source_path:
            messagebox.showerror('Fehler', 'Zuerst eine WAV- oder CSMP-Datei auswählen.')
            return
        mode = get_mode_from_path(self.source_path)
        initial_dir = os.path.dirname(self.source_path)
        if mode == 'wav_to_csmp':
            initial_name = os.path.splitext(os.path.basename(self.source_path))[0] + '.csmp'
            path = filedialog.asksaveasfilename(title='Zielpfad für CSMP wählen', defaultextension='.csmp', initialdir=initial_dir, initialfile=initial_name, filetypes=[('CSMP-Dateien', '*.csmp'), ('Alle Dateien', '*.*')])
        else:
            initial_name = os.path.splitext(os.path.basename(self.source_path))[0] + '.wav'
            path = filedialog.asksaveasfilename(title='Zielpfad für WAV wählen', defaultextension='.wav', initialdir=initial_dir, initialfile=initial_name, filetypes=[('WAV-Dateien', '*.wav'), ('Alle Dateien', '*.*')])
        if not path:
            return
        self.target_path = path
        self.target_text.set(path)
        self.status_text.set('Ziel gesetzt. Jetzt auf Umwandeln und speichern klicken.')

    def on_loop_toggle(self):
        state = 'normal' if self.loop_enabled_var.get() else 'disabled'
        self.loop_start_entry.config(state=state)
        self.loop_end_entry.config(state=state)

    def set_busy(self, busy):
        state = 'disabled' if busy else 'normal'
        self.convert_button.config(state=state)
        self.source_button.config(state=state)
        self.target_button.config(state=state)

    def update_progress(self, percent, text):
        self.progress_queue.put(('progress', float(percent), text))

    def convert_worker(self, mode, source_path, target_path):
        try:
            if mode == 'wav_to_csmp':
                channels, sample_rate, frame_count, output_size = convert_wav_to_csmp(source_path, target_path, self.update_progress, self.loop_start_samples, self.loop_end_samples)
                self.progress_queue.put(('done', 'WAV zu CSMP abgeschlossen.', 'CSMP-Datei wurde erstellt.\n\n' f'Kanäle: {channels}\n' f'Samplerate: {sample_rate} Hz\n' f'Samples pro Kanal: {frame_count}\n' f'Ausgabedatei: {target_path}\n' f'Größe: {output_size} Bytes'))
            else:
                channels, sample_rate, frame_count, output_size = convert_csmp_to_wav(source_path, target_path, self.update_progress)
                self.progress_queue.put(('done', 'CSMP zu WAV abgeschlossen.', 'WAV-Datei wurde erstellt.\n\n' f'Kanäle: {channels}\n' f'Samplerate: {sample_rate} Hz\n' f'Samples pro Kanal: {frame_count}\n' f'Ausgabedatei: {target_path}\n' f'Größe: {output_size} Bytes'))
        except Exception as exc:
            self.progress_queue.put(('error', f'{exc}\n\n{traceback.format_exc()}'))

    def poll_progress(self):
        try:
            while True:
                item = self.progress_queue.get_nowait()
                if item[0] == 'progress':
                    _, percent, text = item
                    self.progress_value.set(max(0.0, min(100.0, percent)))
                    self.progress_text.set(text)
                elif item[0] == 'done':
                    _, status, message = item
                    self.progress_value.set(100.0)
                    self.progress_text.set('Fertig.')
                    self.status_text.set(status)
                    self.set_busy(False)
                    self.worker_thread = None
                    messagebox.showinfo('Erfolg', message)
                elif item[0] == 'error':
                    _, message = item
                    self.status_text.set('Umwandlung fehlgeschlagen.')
                    self.progress_text.set('Fehler.')
                    self.set_busy(False)
                    self.worker_thread = None
                    messagebox.showerror('Fehler', message)
        except queue.Empty:
            pass
        if self.worker_thread and self.worker_thread.is_alive():
            self.root.after(100, self.poll_progress)
        elif self.worker_thread is not None:
            self.root.after(100, self.poll_progress)

    def convert(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self.source_path:
            messagebox.showerror('Fehler', 'Es wurde noch keine Quelldatei ausgewählt.')
            return
        if not self.target_path:
            messagebox.showerror('Fehler', 'Es wurde noch keine Zieldatei ausgewählt.')
            return
        mode = get_mode_from_path(self.source_path)
        if not mode:
            messagebox.showerror('Fehler', 'Die Quelldatei muss eine WAV- oder CSMP-Datei sein.')
            return
        self.loop_start_samples = 0
        self.loop_end_samples = 0
        if mode == 'wav_to_csmp' and self.loop_enabled_var.get():
            try:
                ls_sec = float(self.loop_start_var.get().replace(',', '.'))
                le_sec = float(self.loop_end_var.get().replace(',', '.'))
                wav_channels, wav_rate, wav_frames = get_wav_info(self.source_path)
                self.loop_start_samples = max(0, min(wav_frames, round(ls_sec * wav_rate)))
                self.loop_end_samples = max(0, min(wav_frames, round(le_sec * wav_rate)))
                if self.loop_end_samples <= self.loop_start_samples:
                    messagebox.showerror('Fehler', 'Loop-Ende muss nach Loop-Start liegen.')
                    return
            except ValueError:
                messagebox.showerror('Fehler', 'Ungültige Loop-Werte. Bitte Dezimalzahlen in Sekunden eingeben.')
                return
        self.set_busy(True)
        self.progress_value.set(0.0)
        self.progress_text.set('Startet...')
        self.status_text.set('Umwandlung läuft...')
        self.worker_thread = threading.Thread(target=self.convert_worker, args=(mode, self.source_path, self.target_path), daemon=True)
        self.worker_thread.start()
        self.root.after(100, self.poll_progress)

def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()