from pathlib import Path
import math
import zlib
import tkinter as tk
from tkinter import filedialog, ttk
import io

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    from py_tegra_swizzle import deswizzle_block_linear, block_height_mip0
except Exception:
    deswizzle_block_linear = None
    block_height_mip0 = None

try:
    import texture2ddecoder
except Exception:
    texture2ddecoder = None

class TxtrError(Exception):
    pass

def be32(data, off):
    return int.from_bytes(data[off:off + 4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off + 8], 'big')

def tag4(data, off):
    return data[off:off + 4].decode('ascii', 'replace')

def clamp8(value):
    if value < 0:
        return 0
    if value > 255:
        return 255
    return value

def txtr_to_png_bytes(raw, block_mode='Auto'):
    if Image is None:
        raise TxtrError('Pillow fehlt.')
    info = parse_txtr_asset(raw)
    image, _ = decode_txtr_image(info, block_mode)
    buf = io.BytesIO()
    image.save(buf, 'PNG')
    return buf.getvalue()

def lzss_decompress(data, mode, out_size):
    out = bytearray(out_size)
    src = 0
    dst = 0
    header = 0
    group = 0
    while src < len(data) and dst < out_size:
        if group == 0:
            header = data[src]
            src += 1
            group = 8
        if header & 0x80:
            if src + 2 > len(data):
                break
            a = data[src]
            b = data[src + 1]
            src += 2
            if mode == 1:
                count = (a >> 4) + 3
                length = ((a & 0x0F) << 8) | b
                unit = 1
            elif mode == 2:
                count = (a >> 4) + 2
                length = (((a & 0x0F) << 8) | b) << 1
                unit = 2
            else:
                count = (a >> 4) + 1
                length = (((a & 0x0F) << 8) | b) << 2
                unit = 4
            seek = dst - length
            for _ in range(count):
                for _ in range(unit):
                    if 0 <= seek < len(out) and dst < out_size:
                        out[dst] = out[seek]
                    dst += 1
                    seek += 1
        else:
            if mode == 1:
                unit = 1
            elif mode == 2:
                unit = 2
            else:
                unit = 4
            for _ in range(unit):
                if src >= len(data) or dst >= out_size:
                    break
                out[dst] = data[src]
                src += 1
                dst += 1
        header = (header << 1) & 0xFF
        group -= 1
    return bytes(out)

def decompress_gpu_buffer(gpu_payload, expected_size=0):
    if not gpu_payload:
        return b'', 'leer', 0
    if len(gpu_payload) < 4:
        return gpu_payload, 'roh', None
    comp_be = int.from_bytes(gpu_payload[:4], 'big')
    comp_le = int.from_bytes(gpu_payload[:4], 'little')
    comp_type = comp_le if comp_le in (0, 1, 2, 3, 0x0D) else comp_be
    data = gpu_payload[4:]
    if comp_type == 0:
        return data, 'none', comp_type
    if comp_type == 1:
        return lzss_decompress(data, 1, expected_size or len(data) * 8), 'lzss8', comp_type
    if comp_type == 2:
        return lzss_decompress(data, 2, expected_size or len(data) * 8), 'lzss16', comp_type
    if comp_type == 3:
        return lzss_decompress(data, 3, expected_size or len(data) * 8), 'lzss32', comp_type
    if comp_type == 0x0D:
        return zlib.decompress(data), 'zlib', comp_type
    return gpu_payload, f'raw_0x{comp_be:08X}', comp_be

def parse_txtr_asset(data):
    if len(data) < 32:
        raise TxtrError('TXTR-Datei ist zu klein.')
    if data[:4] != b'RFRM':
        raise TxtrError('Kein RFRM-Header gefunden.')
    if tag4(data, 20) != 'TXTR':
        raise TxtrError('Kein TXTR-Wrapper gefunden.')
    root_version_a = be32(data, 24)
    root_version_b = be32(data, 28)
    head_payload = None
    gpu_payload = None
    chunks = []
    p = 32
    while p + 24 <= len(data):
        chunk_tag = tag4(data, p)
        size = be64(data, p + 4)
        version = be32(data, p + 12)
        payload_off = p + 24
        payload_end = payload_off + size
        if payload_end > len(data):
            raise TxtrError(f'Chunk {chunk_tag} läuft über Dateiende.')
        payload = data[payload_off:payload_end]
        chunks.append({'tag': chunk_tag, 'size': size, 'version': version})
        if chunk_tag == 'HEAD':
            head_payload = payload
        elif chunk_tag == 'GPU ':
            gpu_payload = payload
        p = payload_end
    if head_payload is None:
        raise TxtrError('HEAD-Chunk fehlt.')
    if gpu_payload is None:
        raise TxtrError('GPU-Chunk fehlt.')
    if len(head_payload) < 36 or len(head_payload) % 4 != 0:
        raise TxtrError('HEAD-Chunk ist ungültig.')
    words = [be32(head_payload, i) for i in range(0, len(head_payload), 4)]
    tex_type = words[0]
    fmt = words[1]
    width = words[2]
    height = words[3]
    depth = words[4]
    tile_mode = words[5]
    swizzle = words[6]
    mip_count = words[7]
    if 8 + mip_count + 2 > len(words):
        raise TxtrError('HEAD-Felder sind abgeschnitten.')
    mip_sizes = words[8:8 + mip_count]
    texture_size = words[8 + mip_count]
    unknown = words[9 + mip_count]
    gpu_data, gpu_codec, comp_type = decompress_gpu_buffer(gpu_payload, texture_size)
    return {
        'root_version_a': root_version_a,
        'root_version_b': root_version_b,
        'is_switch': root_version_a >= 0x0F,
        'tex_type': tex_type,
        'format': fmt,
        'width': width,
        'height': height,
        'depth': depth,
        'tile_mode': tile_mode,
        'swizzle': swizzle,
        'mip_count': mip_count,
        'mip_sizes': mip_sizes,
        'texture_size': texture_size,
        'unknown': unknown,
        'head_words': words,
        'gpu_codec': gpu_codec,
        'gpu_comp_type': comp_type,
        'gpu_data': gpu_data,
        'gpu_size': len(gpu_payload),
        'gpu_decompressed_size': len(gpu_data),
        'chunks': chunks,
    }

ASTC_BLOCKS = {
    53: (4, 4),
    54: (5, 4),
    55: (5, 5),
    56: (6, 5),
    57: (6, 6),
    58: (8, 5),
    59: (8, 6),
    60: (8, 8),
    61: (10, 5),
    62: (10, 6),
}

FORMAT_NAMES = {
    0: 'I4',
    1: 'I8',
    2: 'IA4',
    3: 'IA8',
    4: 'C4',
    5: 'C8',
    6: 'C14X2',
    7: 'RGB565',
    8: 'RGB5A3',
    9: 'RGBA8',
    10: 'CMPR',
    12: 'R8G8B8A8_UNORM',
    13: 'R8G8B8A8_UNORM_SRGB',
    20: 'BC1_UNORM',
    21: 'BC1_UNORM_SRGB',
    22: 'BC2_UNORM',
    23: 'BC2_UNORM_SRGB',
    24: 'BC3_UNORM',
    25: 'BC3_UNORM_SRGB',
    26: 'BC4_UNORM',
    27: 'BC4_SNORM',
    28: 'BC5_UNORM',
    29: 'BC5_SNORM',
    30: 'R11G11B10_FLOAT',
    31: 'R32_FLOAT',
    32: 'R16G16_FLOAT',
    33: 'R8G8_UNORM',
}
FORMAT_NAMES.update({k: f'ASTC_{v[0]}x{v[1]}' for k, v in ASTC_BLOCKS.items()})

BC_FORMATS = {
    20: ('bc1', 8),
    21: ('bc1', 8),
    24: ('bc3', 16),
    25: ('bc3', 16),
    26: ('bc4', 8),
    28: ('bc5', 16),
    31: ('bc6', 16),
    55: None,
}

def rgb565_to_rgba(value):
    r = ((value >> 11) & 0x1F) * 255 // 31
    g = ((value >> 5) & 0x3F) * 255 // 63
    b = (value & 0x1F) * 255 // 31
    return r, g, b, 255

def rgb5a3_to_rgba(value):
    if value & 0x8000:
        r = ((value >> 10) & 0x1F) * 255 // 31
        g = ((value >> 5) & 0x1F) * 255 // 31
        b = (value & 0x1F) * 255 // 31
        return r, g, b, 255
    a = ((value >> 12) & 0x07) * 255 // 7
    r = ((value >> 8) & 0x0F) * 255 // 15
    g = ((value >> 4) & 0x0F) * 255 // 15
    b = (value & 0x0F) * 255 // 15
    return r, g, b, a

def decode_i4(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 8):
        for bx in range(0, width, 8):
            for y in range(8):
                for x in range(0, 8, 2):
                    value = data[off] if off < len(data) else 0
                    off += 1
                    left = ((value >> 4) & 0x0F) * 17
                    right = (value & 0x0F) * 17
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = (left, left, left, 255)
                    if bx + x + 1 < width and by + y < height:
                        px[bx + x + 1, by + y] = (right, right, right, 255)
    return image

def decode_i8(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 8):
            for y in range(4):
                for x in range(8):
                    value = data[off] if off < len(data) else 0
                    off += 1
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = (value, value, value, 255)
    return image

def decode_ia4(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 8):
            for y in range(4):
                for x in range(8):
                    value = data[off] if off < len(data) else 0
                    off += 1
                    a = ((value >> 4) & 0x0F) * 17
                    i = (value & 0x0F) * 17
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = (i, i, i, a)
    return image

def decode_ia8(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            for y in range(4):
                for x in range(4):
                    a = data[off] if off < len(data) else 0
                    i = data[off + 1] if off + 1 < len(data) else 0
                    off += 2
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = (i, i, i, a)
    return image

def decode_rgb565(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            for y in range(4):
                for x in range(4):
                    value = ((data[off] if off < len(data) else 0) << 8) | (data[off + 1] if off + 1 < len(data) else 0)
                    off += 2
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = rgb565_to_rgba(value)
    return image

def decode_rgb5a3(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            for y in range(4):
                for x in range(4):
                    value = ((data[off] if off < len(data) else 0) << 8) | (data[off + 1] if off + 1 < len(data) else 0)
                    off += 2
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = rgb5a3_to_rgba(value)
    return image

def decode_rgba8(data, width, height):
    image = Image.new('RGBA', (width, height))
    px = image.load()
    off = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            block = data[off:off + 64]
            off += 64
            if len(block) < 64:
                block = block + b'\x00' * (64 - len(block))
            for y in range(4):
                for x in range(4):
                    i = y * 4 + x
                    a = block[i * 2]
                    r = block[i * 2 + 1]
                    g = block[32 + i * 2]
                    b = block[32 + i * 2 + 1]
                    if bx + x < width and by + y < height:
                        px[bx + x, by + y] = (r, g, b, a)
    return image

def decode_legacy_image(info):
    if Image is None:
        raise TxtrError('Pillow fehlt.')
    data = info['gpu_data']
    fmt = info['format']
    width = info['width']
    height = info['height']
    if fmt == 0:
        return decode_i4(data, width, height), None
    if fmt == 1:
        return decode_i8(data, width, height), None
    if fmt == 2:
        return decode_ia4(data, width, height), None
    if fmt == 3:
        return decode_ia8(data, width, height), None
    if fmt == 7:
        return decode_rgb565(data, width, height), None
    if fmt == 8:
        return decode_rgb5a3(data, width, height), None
    if fmt == 9:
        return decode_rgba8(data, width, height), None
    raise TxtrError(f'Legacy-Format {fmt} wird hier noch nicht dekodiert.')

def count_magenta_pixels(image):
    if Image is None:
        return 0
    total = 0
    for r, g, b, a in image.getdata():
        if r == 255 and g == 0 and b == 255:
            total += 1
    return total

def decode_switch_linear(info, block_height_override=None):
    if Image is None or deswizzle_block_linear is None or block_height_mip0 is None or texture2ddecoder is None:
        raise TxtrError('Es fehlen Pillow, py-tegra-swizzle oder texture2ddecoder.')
    fmt = info['format']
    width = info['width']
    height = info['height']
    src = info['gpu_data']
    if fmt in ASTC_BLOCKS:
        block_w, block_h = ASTC_BLOCKS[fmt]
        bytes_per_block = 16
        width_blocks = math.ceil(width / block_w)
        height_blocks = math.ceil(height / block_h)
        required_size = width_blocks * height_blocks * bytes_per_block
        if len(src) < required_size:
            raise TxtrError(f'TXTR-Daten zu klein für ASTC {block_w}x{block_h}: erwartet mindestens {required_size} Bytes, gefunden {len(src)} Bytes')
        block_height = block_height_override if block_height_override else block_height_mip0(height_blocks)
        try:
            linear = deswizzle_block_linear(width_blocks, height_blocks, 1, src, block_height, bytes_per_block)
        except Exception as e:
            raise TxtrError(str(e))
        linear = linear[:required_size]
        decoded = texture2ddecoder.decode_astc(linear, width, height, block_w, block_h)
        image = Image.frombytes('RGBA', (width, height), decoded, 'raw', 'BGRA')
        return image, block_height
    if fmt in BC_FORMATS and BC_FORMATS[fmt] is not None:
        family, bytes_per_block = BC_FORMATS[fmt]
        width_blocks = math.ceil(width / 4)
        height_blocks = math.ceil(height / 4)
        required_size = width_blocks * height_blocks * bytes_per_block
        if len(src) < required_size:
            raise TxtrError(f'TXTR-Daten zu klein für {FORMAT_NAMES.get(fmt, fmt)}: erwartet mindestens {required_size} Bytes, gefunden {len(src)} Bytes')
        block_height = block_height_override if block_height_override else block_height_mip0(height_blocks)
        try:
            linear = deswizzle_block_linear(width_blocks, height_blocks, 1, src, block_height, bytes_per_block)
        except Exception as e:
            raise TxtrError(str(e))
        linear = linear[:required_size]
        if family == 'bc1':
            decoded = texture2ddecoder.decode_bc1(linear, width, height)
        elif family == 'bc3':
            decoded = texture2ddecoder.decode_bc3(linear, width, height)
        elif family == 'bc4':
            decoded = texture2ddecoder.decode_bc4(linear, width, height)
        elif family == 'bc5':
            decoded = texture2ddecoder.decode_bc5(linear, width, height)
        elif family == 'bc6':
            decoded = texture2ddecoder.decode_bc6(linear, width, height, False)
        else:
            raise TxtrError(f'{FORMAT_NAMES.get(fmt, fmt)} wird noch nicht unterstützt.')
        image = Image.frombytes('RGBA', (width, height), decoded, 'raw', 'BGRA')
        return image, block_height
    if fmt in (12, 13):
        bytes_per_block = 4
        width_blocks = width
        height_blocks = height
        required_size = width * height * 4
        if len(src) < required_size:
            raise TxtrError(f'TXTR-Daten zu klein für RGBA8: erwartet mindestens {required_size} Bytes, gefunden {len(src)} Bytes')
        block_height = block_height_override if block_height_override else block_height_mip0(height_blocks)
        try:
            linear = deswizzle_block_linear(width_blocks, height_blocks, 1, src, block_height, bytes_per_block)
        except Exception as e:
            raise TxtrError(str(e))
        linear = linear[:required_size]
        image = Image.frombytes('RGBA', (width, height), linear, 'raw', 'RGBA')
        return image, block_height
    raise TxtrError(f'Switch-Format {FORMAT_NAMES.get(fmt, fmt)} wird noch nicht unterstützt.')

def decode_txtr_image(info, block_mode='Auto'):
    if info['width'] <= 0 or info['height'] <= 0:
        raise TxtrError('Ungültige Bildgröße.')
    if info['is_switch']:
        override = None if block_mode == 'Auto' else int(block_mode)
        image, used_block_height = decode_switch_linear(info, override)
        return image, used_block_height
    image, _ = decode_legacy_image(info)
    return image, None

def format_info_text(info, label, used_block_height=None):
    name = label.strip() if label else 'TXTR'
    fmt_name = FORMAT_NAMES.get(info['format'], f'0x{info["format"]:X}')
    parts = [name, f'{info["width"]}x{info["height"]}', fmt_name, info['gpu_codec']]
    if info['is_switch'] and used_block_height is not None:
        parts.append(f'Block-Höhe {used_block_height}')
    return ' | '.join(parts)

class TxtrPreview:
    def __init__(self, parent):
        self.parent = parent
        self.frame = tk.LabelFrame(parent, text='TXTR Vorschau', padx=10, pady=8)
        self.info_var = tk.StringVar(value='')
        self.status_var = tk.StringVar(value='')
        self.block_var = tk.StringVar(value='Auto')
        self.block_values = ['Auto', '1', '2', '4', '8', '16', '32']
        self.loaded = False
        self.label = ''
        self.info = None
        self.image = None
        self.tk_image = None
        self.big_image = None
        self.big_window = None
        self.big_canvas = None
        self.big_hscroll = None
        self.big_vscroll = None
        self.big_zoom_var = tk.StringVar(value='Fit')
        top = tk.Frame(self.frame)
        top.pack(fill='x')
        self.info_label = tk.Label(top, textvariable=self.info_var, anchor='w')
        self.info_label.pack(side='left', fill='x', expand=True)
        tk.Label(top, text='Block').pack(side='left', padx=(8, 4))
        self.block_box = ttk.Combobox(top, textvariable=self.block_var, values=self.block_values, state='readonly', width=6)
        self.block_box.pack(side='left')
        self.block_box.bind('<<ComboboxSelected>>', self.on_block_changed)
        self.open_button = tk.Button(top, text='Groß öffnen', width=12, command=self.open_big_window)
        self.open_button.pack(side='left', padx=(8, 0))
        self.save_button = tk.Button(top, text='PNG speichern', width=12, command=self.save_png)
        self.save_button.pack(side='left', padx=(8, 0))
        canvas_wrap = tk.Frame(self.frame)
        canvas_wrap.pack(fill='both', expand=True, pady=(8, 0))
        self.canvas = tk.Canvas(canvas_wrap, height=250, highlightthickness=1, highlightbackground='#808080')
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.vscroll = ttk.Scrollbar(canvas_wrap, orient='vertical', command=self.canvas.yview)
        self.vscroll.grid(row=0, column=1, sticky='ns')
        self.hscroll = ttk.Scrollbar(canvas_wrap, orient='horizontal', command=self.canvas.xview)
        self.hscroll.grid(row=1, column=0, sticky='ew')
        canvas_wrap.grid_rowconfigure(0, weight=1)
        canvas_wrap.grid_columnconfigure(0, weight=1)
        self.canvas.configure(xscrollcommand=self.hscroll.set, yscrollcommand=self.vscroll.set)
        self.canvas.bind('<Configure>', self.on_canvas_configure)
        self.status_label = tk.Label(self.frame, textvariable=self.status_var, anchor='w', justify='left')
        self.status_label.pack(fill='x', pady=(6, 0))
        self.frame.bind('<Destroy>', self._on_destroy)
        self.hide()
        self._set_buttons()

    def _on_destroy(self, event=None):
        try:
            if self.big_window is not None and self.big_window.winfo_exists():
                self.big_window.destroy()
        except Exception:
            pass

    def _set_buttons(self):
        state = 'normal' if self.loaded and self.image is not None else 'disabled'
        self.open_button.config(state=state)
        self.save_button.config(state=state)
        self.block_box.config(state='readonly' if self.loaded else 'disabled')

    def hide(self):
        self.frame.pack_forget()

    def clear(self):
        self.loaded = False
        self.label = ''
        self.info = None
        self.image = None
        self.tk_image = None
        self.big_image = None
        self.info_var.set('')
        self.status_var.set('')
        self.block_var.set('Auto')
        self.canvas.delete('all')
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.hide()
        self._update_big_window()
        self._set_buttons()

    def load_txtr(self, data, label=''):
        self.loaded = False
        self.label = label or 'TXTR'
        self.info = parse_txtr_asset(data)
        self.block_var.set('Auto')
        self.loaded = True
        self.frame.pack(fill='both', expand=False, pady=(10, 0))
        self._render_current()
        self._set_buttons()

    def on_block_changed(self, event=None):
        if not self.loaded:
            return
        self._render_current()

    def _render_current(self):
        if not self.loaded or self.info is None:
            self.canvas.delete('all')
            self.image = None
            self.tk_image = None
            self.info_var.set('')
            self.status_var.set('')
            self._update_big_window()
            self._set_buttons()
            return
        try:
            image, used_block_height = decode_txtr_image(self.info, self.block_var.get())
            self.image = image
            self.info_var.set(format_info_text(self.info, self.label, used_block_height))
            extra = []
            extra.append(f'RFRM-Version: {self.info["root_version_a"]} / {self.info["root_version_b"]}')
            extra.append(f'TileMode: {self.info["tile_mode"]}')
            extra.append(f'Swizzle: {self.info["swizzle"]}')
            extra.append(f'Mips: {self.info["mip_count"]}')
            extra.append(f'GPU gepackt: {self.info["gpu_size"]} Bytes')
            extra.append(f'GPU entpackt: {self.info["gpu_decompressed_size"]} Bytes')
            self.status_var.set(' | '.join(extra))
            self._draw_embedded_image()
            self._update_big_window()
        except Exception as e:
            self.image = None
            self.tk_image = None
            self.canvas.delete('all')
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            self.info_var.set(format_info_text(self.info, self.label, None))
            self.status_var.set(str(e))
            self._update_big_window()
        self._set_buttons()

    def _fit_size(self, image_width, image_height, max_width, max_height):
        if image_width <= 0 or image_height <= 0:
            return 1, 1
        if max_width <= 1 or max_height <= 1:
            return image_width, image_height
        scale = min(max_width / image_width, max_height / image_height)
        scale = min(scale, 1.0)
        return max(1, int(round(image_width * scale))), max(1, int(round(image_height * scale)))

    def _draw_embedded_image(self):
        self.canvas.delete('all')
        if self.image is None:
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        canvas_width = max(200, self.canvas.winfo_width() - 4)
        canvas_height = max(160, self.canvas.winfo_height() - 4)
        draw_w, draw_h = self._fit_size(self.image.width, self.image.height, canvas_width, canvas_height)
        draw_img = self.image if (draw_w, draw_h) == (self.image.width, self.image.height) else self.image.resize((draw_w, draw_h), Image.NEAREST)
        self.tk_image = ImageTk.PhotoImage(draw_img)
        x = max(0, (canvas_width - draw_w) // 2)
        y = max(0, (canvas_height - draw_h) // 2)
        self.canvas.create_image(x, y, anchor='nw', image=self.tk_image)
        self.canvas.configure(scrollregion=(0, 0, max(canvas_width, draw_w), max(canvas_height, draw_h)))

    def on_canvas_configure(self, event=None):
        if self.loaded and self.image is not None:
            self._draw_embedded_image()

    def open_big_window(self):
        if self.image is None:
            return
        if self.big_window is None or not self.big_window.winfo_exists():
            self.big_window = tk.Toplevel(self.frame)
            self.big_window.title('TXTR Vorschau groß')
            self.big_window.geometry('1100x900')
            self.big_window.minsize(480, 360)
            top = tk.Frame(self.big_window, padx=8, pady=8)
            top.pack(fill='x')
            tk.Label(top, textvariable=self.info_var, anchor='w').pack(side='left', fill='x', expand=True)
            tk.Label(top, text='Zoom').pack(side='left', padx=(8, 4))
            zoom_box = ttk.Combobox(top, textvariable=self.big_zoom_var, values=['Fit', '50%', '100%', '200%', '400%'], state='readonly', width=8)
            zoom_box.pack(side='left')
            zoom_box.bind('<<ComboboxSelected>>', self.on_big_zoom_changed)
            big_wrap = tk.Frame(self.big_window, padx=8, pady=(0, 8))
            big_wrap.pack(fill='both', expand=True)
            self.big_canvas = tk.Canvas(big_wrap, highlightthickness=1, highlightbackground='#808080')
            self.big_canvas.grid(row=0, column=0, sticky='nsew')
            self.big_vscroll = ttk.Scrollbar(big_wrap, orient='vertical', command=self.big_canvas.yview)
            self.big_vscroll.grid(row=0, column=1, sticky='ns')
            self.big_hscroll = ttk.Scrollbar(big_wrap, orient='horizontal', command=self.big_canvas.xview)
            self.big_hscroll.grid(row=1, column=0, sticky='ew')
            big_wrap.grid_rowconfigure(0, weight=1)
            big_wrap.grid_columnconfigure(0, weight=1)
            self.big_canvas.configure(xscrollcommand=self.big_hscroll.set, yscrollcommand=self.big_vscroll.set)
            self.big_canvas.bind('<Configure>', self.on_big_canvas_configure)
        self.big_window.deiconify()
        self.big_window.lift()
        self._update_big_window()

    def on_big_zoom_changed(self, event=None):
        self._update_big_window()

    def on_big_canvas_configure(self, event=None):
        if self.big_zoom_var.get() == 'Fit':
            self._update_big_window()

    def _update_big_window(self):
        if self.big_window is None or not self.big_window.winfo_exists() or self.big_canvas is None:
            return
        self.big_canvas.delete('all')
        if self.image is None:
            self.big_canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        zoom = self.big_zoom_var.get()
        if zoom == 'Fit':
            max_w = max(1, self.big_canvas.winfo_width() - 4)
            max_h = max(1, self.big_canvas.winfo_height() - 4)
            draw_w, draw_h = self._fit_size(self.image.width, self.image.height, max_w, max_h)
        else:
            scale = float(zoom.rstrip('%')) / 100.0
            draw_w = max(1, int(round(self.image.width * scale)))
            draw_h = max(1, int(round(self.image.height * scale)))
        draw_img = self.image if (draw_w, draw_h) == (self.image.width, self.image.height) else self.image.resize((draw_w, draw_h), Image.NEAREST)
        self.big_image = ImageTk.PhotoImage(draw_img)
        self.big_canvas.create_image(0, 0, anchor='nw', image=self.big_image)
        self.big_canvas.configure(scrollregion=(0, 0, draw_w, draw_h))

    def save_png(self):
        if self.image is None:
            return
        base = self.label.strip() if self.label.strip() else 'txtr'
        safe = ''.join(ch if ch.isalnum() or ch in ('_', '-', '.') else '_' for ch in base)
        path = filedialog.asksaveasfilename(title='PNG speichern', defaultextension='.png', initialfile=safe + '.png', filetypes=[('PNG-Dateien', '*.png'), ('Alle Dateien', '*.*')])
        if not path:
            return
        self.image.save(path, 'PNG')