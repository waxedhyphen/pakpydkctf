from array import array
from pathlib import Path
from collections import OrderedDict
import hashlib
import io
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
import tkinter as tk
from tkinter import ttk

try:
    import winsound
except Exception:
    winsound = None


def clamp16(value):
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return int(value)


def tag4(data, off):
    return data[off:off + 4].decode('ascii', 'replace')


def read_u32(data, off, little_endian):
    return int.from_bytes(data[off:off + 4], 'little' if little_endian else 'big')


def read_s16(data, off, little_endian):
    return int.from_bytes(data[off:off + 2], 'little' if little_endian else 'big', signed=True)


def decode_dsp_channel(encoded, sample_count, coefficient_pairs, hist1=0, hist2=0):
    samples = array('h')
    append = samples.append
    pos = 0
    out_count = 0
    while out_count < sample_count and pos + 8 <= len(encoded):
        frame0 = encoded[pos]
        pos += 8
        predictor = (frame0 >> 4) & 0x0F
        shift = frame0 & 0x0F
        if predictor >= len(coefficient_pairs):
            predictor = 0
        coef1, coef2 = coefficient_pairs[predictor]
        frame_base = pos - 8
        for index in range(14):
            if out_count >= sample_count:
                break
            value = encoded[frame_base + 1 + index // 2]
            nibble = (value >> 4) & 0x0F if index % 2 == 0 else value & 0x0F
            if nibble >= 8:
                nibble -= 16
            predicted = (coef1 * hist1 + coef2 * hist2 + 1024) >> 11
            sample = predicted + (nibble << shift)
            if sample > 32767:
                sample = 32767
            elif sample < -32768:
                sample = -32768
            append(int(sample))
            out_count += 1
            hist2, hist1 = hist1, sample
    if out_count < sample_count:
        samples.extend(array('h', [0]) * (sample_count - out_count))
    return samples


def _parse_csmp_layout(data):
    if len(data) < 32:
        raise ValueError('CSMP ist zu klein.')
    if data[:4] != b'RFRM':
        raise ValueError('Kein RFRM-Header gefunden.')
    if tag4(data, 20) != 'CSMP':
        raise ValueError('Kein CSMP-Block gefunden.')
    version_be = int.from_bytes(data[24:28], 'big')
    if version_be == 0x0A:
        little_endian = False
        data_align = 3
    elif version_be in (0x11, 0x12):
        little_endian = True
        data_align = 0
    else:
        version_le = int.from_bytes(data[24:28], 'little')
        if version_le in (0x1F, 0x2E):
            raise ValueError('Diese neuere CSMP-Variante ist in der Vorschau noch nicht eingebaut.')
        raise ValueError(f'Unbekannte CSMP-Version: 0x{version_be:08X}')
    fmta_payload = None
    data_payload = None
    pos = 32
    while pos + 24 <= len(data):
        chunk_tag = tag4(data, pos)
        if data[pos + 4:pos + 8] != b'\x00\x00\x00\x00':
            break
        size = int.from_bytes(data[pos + 8:pos + 12], 'big')
        payload_off = pos + 24
        payload_end = payload_off + size
        if payload_end > len(data):
            raise ValueError(f'Chunk {chunk_tag} läuft über das Dateiende.')
        payload = data[payload_off:payload_end]
        if chunk_tag == 'FMTA':
            fmta_payload = payload
        elif chunk_tag == 'DATA':
            data_payload = payload
        pos = payload_end
    if fmta_payload is None or data_payload is None:
        raise ValueError('FMTA oder DATA fehlt.')
    if not fmta_payload:
        raise ValueError('FMTA ist leer.')
    channels = fmta_payload[0]
    if channels <= 0:
        raise ValueError('Ungültige Kanalzahl.')
    if len(data_payload) <= data_align:
        raise ValueError('DATA ist zu klein.')
    channel_area = data_payload[data_align:]
    if len(channel_area) % channels != 0:
        raise ValueError('DATA-Größe passt nicht zur Kanalzahl.')
    interleave = len(channel_area) // channels
    if interleave < 0x60:
        raise ValueError('Kanalblock ist zu klein.')
    sample_count = None
    sample_rate = None
    channel_infos = []
    for channel_index in range(channels):
        base = channel_index * interleave
        header = channel_area[base:base + 0x60]
        encoded = channel_area[base + 0x60:base + interleave]
        this_sample_count = read_u32(header, 0x00, little_endian)
        this_sample_rate = read_u32(header, 0x08, little_endian)
        coefficient_pairs = []
        off = 0x1C
        for _ in range(8):
            coefficient_pairs.append((read_s16(header, off, little_endian), read_s16(header, off + 2, little_endian)))
            off += 4
        hist1 = read_s16(header, 0x40, little_endian)
        hist2 = read_s16(header, 0x42, little_endian)
        channel_infos.append({
            'encoded': encoded,
            'sample_count': this_sample_count,
            'sample_rate': this_sample_rate,
            'coefficient_pairs': coefficient_pairs,
            'hist1': hist1,
            'hist2': hist2
        })
        if sample_count is None:
            sample_count = this_sample_count
        elif this_sample_count != sample_count:
            raise ValueError('Unterschiedliche Sample-Anzahl zwischen den Kanälen.')
        if sample_rate is None:
            sample_rate = this_sample_rate
        elif this_sample_rate != sample_rate:
            raise ValueError('Unterschiedliche Samplerate zwischen den Kanälen.')
    loop_flag = 0
    loop_start_sample = 0
    loop_end_sample = 0
    if channel_area and interleave >= 0x60:
        header_0 = channel_area[:0x60]
        lf = int.from_bytes(header_0[0x0C:0x0E], 'little' if little_endian else 'big')
        if lf:
            loop_flag = 1
            ls_nib = read_u32(header_0, 0x10, little_endian)
            le_nib = read_u32(header_0, 0x14, little_endian)
            if ls_nib >= 2:
                frame = (ls_nib - 2) // 16
                frame_nib = (ls_nib - 2) % 16
                loop_start_sample = frame * 14 + min(frame_nib, 14)
            if le_nib >= 2:
                frame = (le_nib - 2) // 16
                frame_nib = (le_nib - 2) % 16
                loop_end_sample = frame * 14 + min(frame_nib, 14)
    return {
        'channels': channels,
        'sample_rate': sample_rate,
        'sample_count': sample_count,
        'duration': sample_count / sample_rate if sample_rate else 0.0,
        'loop_flag': loop_flag,
        'loop_start_sample': loop_start_sample,
        'loop_end_sample': loop_end_sample,
        'channel_infos': channel_infos
    }


def parse_csmp_info(data):
    info = _parse_csmp_layout(data)
    return {key: value for key, value in info.items() if key != 'channel_infos'}


def parse_csmp_bytes(data):
    info = _parse_csmp_layout(data)
    channels = info['channels']
    sample_count = info['sample_count']
    channel_samples = []
    for channel in info['channel_infos']:
        channel_samples.append(decode_dsp_channel(channel['encoded'], channel['sample_count'], channel['coefficient_pairs'], channel['hist1'], channel['hist2']))
    if channels == 1:
        pcm = channel_samples[0]
    else:
        if channels == 2:
            left = channel_samples[0]
            right = channel_samples[1]
            pcm = array('h', [0]) * (sample_count * 2)
            pcm[0::2] = left
            pcm[1::2] = right
        else:
            pcm = array('h')
            for index in range(sample_count):
                for channel_index in range(channels):
                    pcm.append(channel_samples[channel_index][index])
    if pcm.itemsize != 2:
        raise ValueError('Interner PCM-Fehler.')
    if sys.byteorder != 'little':
        pcm.byteswap()
    info['pcm_bytes'] = pcm.tobytes()
    del info['channel_infos']
    return info


def build_wav_bytes(channels, sample_rate, pcm_bytes):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def format_time(seconds):
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    minutes = total // 60
    secs = total % 60
    return f'{minutes:02d}:{secs:02d}'


class WavPreviewPlayer:
    def __init__(self):
        self.backend = None
        self.process = None
        self.thread = None
        self.ffplay_path = shutil.which('ffplay')
        if self.ffplay_path:
            self.backend = 'ffplay'
        elif winsound is not None:
            self.backend = 'winsound'

    def can_play(self):
        return self.backend is not None

    def stop(self):
        if self.backend == 'winsound':
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        elif self.backend == 'ffplay':
            proc = self.process
            self.process = None
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=0.5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    def play(self, wav_path, start_seconds=0.0):
        self.stop()
        if self.backend == 'winsound':
            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        if self.backend == 'ffplay':
            cmd = [self.ffplay_path, '-nodisp', '-autoexit', '-loglevel', 'quiet']
            if start_seconds > 0:
                cmd.extend(['-ss', f'{start_seconds:.4f}'])
            cmd.append(str(wav_path))
            self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False

    def play_bytes(self, wav_bytes):
        self.stop()
        if self.backend != 'winsound':
            return False

        def worker(payload):
            try:
                winsound.PlaySound(payload, winsound.SND_MEMORY)
            except Exception:
                pass

        self.thread = threading.Thread(target=worker, args=(wav_bytes,), daemon=True)
        self.thread.start()
        return True

    def is_alive(self):
        if self.backend == 'ffplay':
            return self.process is not None and self.process.poll() is None
        return False


class SoundPreview:
    def __init__(self, parent):
        self.parent = parent
        self.player = WavPreviewPlayer()
        self.frame = tk.LabelFrame(parent, text='CSMP Vorschau', padx=10, pady=8)
        self.info_var = tk.StringVar(value='')
        self.time_var = tk.StringVar(value='00:00 / 00:00')
        self.position_var = tk.DoubleVar(value=0.0)
        self.loaded = False
        self.playing = False
        self.duration = 0.0
        self.sample_rate = 0
        self.channels = 0
        self.sample_count = 0
        self.pcm_bytes = b''
        self.after_id = None
        self.decode_generation = 0
        self.decode_thread = None
        self.decode_queue = queue.Queue()
        self.decode_after_id = None
        self.loading = False
        self.cache_key = ''
        self.full_wav_path = None
        self.full_wav_bytes = None
        self.decoded_cache = OrderedDict()
        self.max_cache_items = 6
        self.play_start_seconds = 0.0
        self.play_started_at = 0.0
        self.dragging = False
        self.temp_dir = Path(tempfile.mkdtemp(prefix='csmp_preview_'))
        self.play_index = 0
        top = tk.Frame(self.frame)
        top.pack(fill='x')
        self.start_button = tk.Button(top, text='Start', width=10, command=self.start)
        self.start_button.pack(side='left')
        self.stop_button = tk.Button(top, text='Stopp', width=10, command=self.stop)
        self.stop_button.pack(side='left', padx=(8, 0))
        self.info_label = tk.Label(top, textvariable=self.info_var, anchor='w')
        self.info_label.pack(side='left', fill='x', expand=True, padx=(12, 0))
        self.scale = ttk.Scale(self.frame, from_=0.0, to=1.0, orient='horizontal', variable=self.position_var, command=self.on_scale_move)
        self.scale.pack(fill='x', pady=(8, 2))
        self.scale.bind('<ButtonPress-1>', self.on_scale_press)
        self.scale.bind('<ButtonRelease-1>', self.on_scale_release)
        self.time_label = tk.Label(self.frame, textvariable=self.time_var, anchor='e')
        self.time_label.pack(fill='x')
        self.frame.bind('<Destroy>', self._on_destroy)
        self.hide()
        self._set_idle_state()

    def _on_destroy(self, event=None):
        try:
            self.shutdown()
        except Exception:
            pass

    def shutdown(self):
        self.stop()
        if self.decode_after_id is not None:
            try:
                self.frame.after_cancel(self.decode_after_id)
            except Exception:
                pass
            self.decode_after_id = None
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    def hide(self):
        self.stop()
        self.frame.pack_forget()

    def clear(self):
        self.stop()
        self.decode_generation += 1
        self.loading = False
        if self.decode_after_id is not None:
            try:
                self.frame.after_cancel(self.decode_after_id)
            except Exception:
                pass
            self.decode_after_id = None
        self.cache_key = ''
        self.full_wav_path = None
        self.full_wav_bytes = None
        self.loaded = False
        self.duration = 0.0
        self.sample_rate = 0
        self.channels = 0
        self.sample_count = 0
        self.pcm_bytes = b''
        self.position_var.set(0.0)
        self.time_var.set('00:00 / 00:00')
        self.info_var.set('')
        self._set_idle_state()
        self.frame.pack_forget()

    def load_csmp(self, data, label=''):
        self.stop()
        self.decode_generation += 1
        generation = self.decode_generation
        self.loaded = False
        self.loading = True
        self.pcm_bytes = b''
        self.full_wav_path = None
        self.full_wav_bytes = None
        key = hashlib.sha1(data).hexdigest()
        self.cache_key = key
        info = parse_csmp_info(data)
        self.channels = info['channels']
        self.sample_rate = info['sample_rate']
        self.sample_count = info['sample_count']
        self.duration = info['duration']
        title = label.strip() if label else 'CSMP'
        kanal_text = 'Kanal' if self.channels == 1 else 'Kanäle'
        backend_text = ''
        if self.player.backend == 'winsound':
            backend_text = ' | Wiedergabe über Windows'
        elif self.player.backend == 'ffplay':
            backend_text = ' | Wiedergabe über ffplay'
        else:
            backend_text = ' | Keine Wiedergabe im System gefunden'
        loop_text = ''
        if info.get('loop_flag') and self.sample_rate > 0:
            ls = info['loop_start_sample'] / self.sample_rate
            le = info['loop_end_sample'] / self.sample_rate
            loop_text = f' | Loop {ls:.2f}s - {le:.2f}s'
        self.info_var.set(f'{title} | {self.channels} {kanal_text} | {self.sample_rate} Hz | {format_time(self.duration)}{loop_text}{backend_text} | dekodiere...')
        self.scale.configure(to=max(self.duration, 0.001))
        self.position_var.set(0.0)
        self.time_var.set(f'00:00 / {format_time(self.duration)}')
        self._set_idle_state()
        if not self.frame.winfo_manager():
            self.frame.pack(fill='x', pady=(10, 0))
        cached = self.decoded_cache.get(key)
        if cached is not None:
            self.decoded_cache.move_to_end(key)
            self._apply_decoded_info(generation, cached, title, loop_text, backend_text)
            return

        def worker():
            try:
                decoded = parse_csmp_bytes(data)
                self.decode_queue.put(('done', generation, decoded, title, loop_text, backend_text))
            except Exception as exc:
                self.decode_queue.put(('error', generation, exc))

        self.decode_thread = threading.Thread(target=worker, daemon=True)
        self.decode_thread.start()
        self._schedule_decode_poll()

    def _schedule_decode_poll(self):
        if self.decode_after_id is None:
            self.decode_after_id = self.frame.after(50, self._poll_decode_queue)

    def _poll_decode_queue(self):
        self.decode_after_id = None
        try:
            while True:
                item = self.decode_queue.get_nowait()
                if item[0] == 'done':
                    _, generation, info, title, loop_text, backend_text = item
                    self._apply_decoded_info(generation, info, title, loop_text, backend_text)
                elif item[0] == 'error':
                    _, generation, exc = item
                    self._decode_failed(generation, exc)
        except queue.Empty:
            pass
        if self.loading:
            self._schedule_decode_poll()

    def _apply_decoded_info(self, generation, info, title, loop_text, backend_text):
        if generation != self.decode_generation:
            return
        self.loaded = True
        self.loading = False
        self.channels = info['channels']
        self.sample_rate = info['sample_rate']
        self.sample_count = info['sample_count']
        self.pcm_bytes = info['pcm_bytes']
        self.duration = info['duration']
        if self.cache_key:
            self.decoded_cache[self.cache_key] = info
            self.decoded_cache.move_to_end(self.cache_key)
            while len(self.decoded_cache) > self.max_cache_items:
                self.decoded_cache.popitem(last=False)
        kanal_text = 'Kanal' if self.channels == 1 else 'KanÃ¤le'
        self.info_var.set(f'{title} | {self.channels} {kanal_text} | {self.sample_rate} Hz | {format_time(self.duration)}{loop_text}{backend_text}')
        self.scale.configure(to=max(self.duration, 0.001))
        self._set_idle_state()

    def _decode_failed(self, generation, exc):
        if generation != self.decode_generation:
            return
        self.loading = False
        self.loaded = False
        self.info_var.set(f'CSMP-Vorschau konnte nicht geladen werden: {exc}')
        self._set_idle_state()

    def _set_idle_state(self):
        self.start_button.config(state='normal' if self.loaded and self.player.can_play() else 'disabled')
        self.stop_button.config(state='normal' if self.loaded and self.player.can_play() else 'disabled')
        if self.loaded:
            self.scale.state(['!disabled'])
        else:
            self.scale.state(['disabled'])

    def _write_full_wav(self):
        if self.full_wav_path is not None and self.full_wav_path.is_file():
            return self.full_wav_path
        wav_bytes = build_wav_bytes(self.channels, self.sample_rate, self.pcm_bytes)
        self.play_index += 1
        path = self.temp_dir / f'preview_full_{self.play_index}.wav'
        path.write_bytes(wav_bytes)
        self.full_wav_path = path
        return path

    def _get_full_wav_bytes(self):
        if self.full_wav_bytes is None:
            self.full_wav_bytes = build_wav_bytes(self.channels, self.sample_rate, self.pcm_bytes)
        return self.full_wav_bytes

    def _write_temp_wav(self, start_sample):
        bytes_per_sample = self.channels * 2
        start_byte = max(0, min(self.sample_count, start_sample)) * bytes_per_sample
        wav_bytes = build_wav_bytes(self.channels, self.sample_rate, self.pcm_bytes[start_byte:])
        self.play_index += 1
        path = self.temp_dir / f'preview_{self.play_index}.wav'
        path.write_bytes(wav_bytes)
        return path

    def start(self):
        if not self.loaded or not self.player.can_play() or self.sample_rate <= 0:
            return
        start_seconds = max(0.0, min(self.duration, float(self.position_var.get())))
        start_sample = int(round(start_seconds * self.sample_rate))
        if self.player.backend == 'winsound':
            if start_sample <= 0:
                wav_bytes = self._get_full_wav_bytes()
            else:
                bytes_per_sample = self.channels * 2
                start_byte = max(0, min(self.sample_count, start_sample)) * bytes_per_sample
                wav_bytes = build_wav_bytes(self.channels, self.sample_rate, self.pcm_bytes[start_byte:])
            if not self.player.play_bytes(wav_bytes):
                return
        elif self.player.backend == 'ffplay':
            path = self._write_full_wav()
            player_start_seconds = start_seconds
            if not self.player.play(path, player_start_seconds):
                return
        else:
            if start_sample <= 0:
                path = self._write_full_wav()
            else:
                path = self._write_temp_wav(start_sample)
            if not self.player.play(path, 0.0):
                return
        self.playing = True
        self.play_start_seconds = start_sample / self.sample_rate
        self.play_started_at = time.monotonic()
        self._schedule_tick()

    def stop(self):
        current_pos = self.current_position()
        self.player.stop()
        self.playing = False
        if self.after_id is not None:
            try:
                self.frame.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        if self.loaded:
            current_pos = max(0.0, min(self.duration, current_pos))
            self.position_var.set(current_pos)
            self.time_var.set(f'{format_time(current_pos)} / {format_time(self.duration)}')

    def current_position(self):
        if not self.playing:
            return float(self.position_var.get())
        elapsed = time.monotonic() - self.play_started_at
        pos = self.play_start_seconds + elapsed
        if pos > self.duration:
            pos = self.duration
        return pos

    def _schedule_tick(self):
        if self.after_id is not None:
            try:
                self.frame.after_cancel(self.after_id)
            except Exception:
                pass
        self.after_id = self.frame.after(80, self._tick)

    def _tick(self):
        self.after_id = None
        if not self.playing:
            return
        pos = self.current_position()
        self.position_var.set(pos)
        self.time_var.set(f'{format_time(pos)} / {format_time(self.duration)}')
        if pos >= self.duration:
            self.stop()
            return
        if self.player.backend == 'ffplay' and not self.player.is_alive():
            self.stop()
            return
        self._schedule_tick()

    def on_scale_press(self, event=None):
        self.dragging = True

    def on_scale_move(self, value):
        if not self.loaded:
            return
        if self.dragging and not self.playing:
            pos = max(0.0, min(self.duration, float(value)))
            self.time_var.set(f'{format_time(pos)} / {format_time(self.duration)}')

    def on_scale_release(self, event=None):
        self.dragging = False
        if not self.loaded:
            return
        pos = max(0.0, min(self.duration, float(self.position_var.get())))
        self.position_var.set(pos)
        self.time_var.set(f'{format_time(pos)} / {format_time(self.duration)}')
        if self.playing:
            self.start()
