from pathlib import Path
from PIL import Image
import importlib
import math
import os
import shutil
import subprocess
import tempfile
from pak_core import PakError, parse_asset_chunks, build_chunk_raw, w64
from txtrpreview import parse_txtr_asset, ASTC_BLOCKS

try:
    from py_tegra_swizzle import swizzle_block_linear, block_height_mip0
except Exception:
    swizzle_block_linear = None
    block_height_mip0 = None

def _encode_legacy_rgba8(image):
    width, height = image.size
    rgba = image.convert('RGBA')
    src = rgba.load()
    out = bytearray()
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            top = bytearray()
            bottom = bytearray()
            for y in range(4):
                for x in range(4):
                    px = bx + x
                    py = by + y
                    if px < width and py < height:
                        r, g, b, a = src[px, py]
                    else:
                        r = 0
                        g = 0
                        b = 0
                        a = 0
                    top.append(a)
                    top.append(r)
                    bottom.append(g)
                    bottom.append(b)
            out += top
            out += bottom
    return bytes(out)

def _encode_linear_rgba8(image):
    return image.convert('RGBA').tobytes('raw', 'RGBA')

def _encode_block_linear_rgba8(image):
    if swizzle_block_linear is None or block_height_mip0 is None:
        raise PakError('Für block-lineares RGBA8 fehlt py_tegra_swizzle mit swizzle_block_linear')
    linear = _encode_linear_rgba8(image)
    block_height = block_height_mip0(image.height)
    swizzled = swizzle_block_linear(image.width, image.height, 1, linear, block_height, 4)
    return bytes(swizzled)

def _build_mip_images(image, mip_count):
    images = [image.convert('RGBA')]
    while len(images) < mip_count:
        prev = images[-1]
        nw = max(1, prev.width // 2)
        nh = max(1, prev.height // 2)
        images.append(prev.resize((nw, nh), Image.BOX))
    return images

_ASTCENC_NAMES = [
    'astcenc',
    'astcenc.exe',
    'astcenc-avx2',
    'astcenc-avx2.exe',
    'astcenc-sse4.1',
    'astcenc-sse4.1.exe',
    'astcenc-sse2',
    'astcenc-sse2.exe',
    'astcenc-neon',
    'astcenc-neon.exe',
    'astcenc-sve_128',
    'astcenc-sve_128.exe',
    'astcenc-sve_256',
    'astcenc-sve_256.exe',
]

def _find_astcenc():
    env_path = os.environ.get('ASTCENC', '').strip()
    if env_path:
        env_file = Path(env_path).expanduser()
        if env_file.is_file():
            return str(env_file)
        if env_file.is_dir():
            for name in _ASTCENC_NAMES:
                candidate = env_file / name
                if candidate.is_file():
                    return str(candidate)
    for name in _ASTCENC_NAMES:
        path = shutil.which(name)
        if path:
            return path
    module_dir = Path(__file__).resolve().parent
    project_dir = module_dir.parent
    search_dirs = [
        module_dir,
        Path.cwd(),
        module_dir / 'tools',
        module_dir / 'tools' / 'windows',
        module_dir / 'tools' / 'win64',
        project_dir / 'tools',
        project_dir / 'tools' / 'windows',
        project_dir / 'tools' / 'win64',
        Path.cwd() / 'tools',
        Path.cwd() / 'tools' / 'windows',
        Path.cwd() / 'tools' / 'win64',
    ]
    for base in search_dirs:
        if not base.is_dir():
            continue
        for name in _ASTCENC_NAMES:
            candidate = base / name
            if candidate.is_file():
                return str(candidate)
    return ''

def _has_astc_python():
    try:
        importlib.import_module('astc_encoder.pil_codec')
        return True
    except Exception:
        return False

def _expected_astc_size(width, height, block_w, block_h):
    return math.ceil(width / block_w) * math.ceil(height / block_h) * 16

def _read_astc_payload(astc_path):
    data = Path(astc_path).read_bytes()
    if len(data) < 16:
        raise PakError('ASTC-Ausgabe ist zu klein')
    magic = int.from_bytes(data[0:4], 'little')
    if magic != 0x5CA1AB13:
        raise PakError('ASTC-Ausgabe hat keinen gültigen Header')
    return data[16:]

def _encode_astc_linear_python(image, block_w, block_h):
    try:
        importlib.import_module('astc_encoder.pil_codec')
        data = image.convert('RGBA').tobytes('astc', (1, 60, block_w, block_h))
    except Exception as e:
        raise PakError(f'Python-ASTC-Encoder fehlgeschlagen: {e}')
    expected = _expected_astc_size(image.width, image.height, block_w, block_h)
    if len(data) != expected:
        raise PakError(f'Python-ASTC-Encoder lieferte {len(data)} Bytes statt {expected}')
    return data

def _encode_astc_linear_cli(image, block_w, block_h):
    astcenc_path = _find_astcenc()
    if not astcenc_path:
        raise PakError('Kein astcenc gefunden')
    with tempfile.TemporaryDirectory(prefix='astc_repack_') as td:
        td_path = Path(td)
        in_path = td_path / 'input.png'
        out_path = td_path / 'output.astc'
        image.convert('RGBA').save(in_path)
        cmd = [astcenc_path, '-cl', str(in_path), str(out_path), f'{block_w}x{block_h}', '-medium']
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            text = (proc.stderr or proc.stdout).decode('utf-8', 'replace').strip()
            raise PakError(f'ASTC-Encoder fehlgeschlagen: {text or proc.returncode}')
        data = _read_astc_payload(out_path)
        expected = _expected_astc_size(image.width, image.height, block_w, block_h)
        if len(data) != expected:
            raise PakError(f'astcenc lieferte {len(data)} Bytes statt {expected}')
        return data

def _encode_astc_linear(image, block_w, block_h):
    python_error = ''
    if _has_astc_python():
        try:
            return _encode_astc_linear_python(image, block_w, block_h)
        except Exception as e:
            python_error = str(e)
    try:
        return _encode_astc_linear_cli(image, block_w, block_h)
    except Exception as e:
        if python_error:
            raise PakError(f'ASTC-Encode fehlgeschlagen | Python: {python_error} | CLI: {e}')
        raise PakError('Für ASTC fehlt ein Encoder. Installiere astc-encoder-py oder lege astcenc.exe neben txtr_repack.py bzw. in tools/windows oder tools/win64.')

def _encode_astc_swizzled(image, fmt):
    if fmt not in ASTC_BLOCKS:
        raise PakError(f'ASTC-Format nicht bekannt: {fmt}')
    if swizzle_block_linear is None or block_height_mip0 is None:
        raise PakError('Für ASTC fehlt py_tegra_swizzle mit swizzle_block_linear')
    block_w, block_h = ASTC_BLOCKS[fmt]
    linear = _encode_astc_linear(image, block_w, block_h)
    width_blocks = math.ceil(image.width / block_w)
    height_blocks = math.ceil(image.height / block_h)
    block_height = block_height_mip0(height_blocks)
    swizzled = swizzle_block_linear(width_blocks, height_blocks, 1, linear, block_height, 16)
    return bytes(swizzled)

def _encode_mip_payload(info, mip_image):
    if info['format'] == 9:
        return _encode_legacy_rgba8(mip_image)
    if info['format'] in (12, 13) and info['tile_mode'] == 1 and info['swizzle'] == 0:
        return _encode_linear_rgba8(mip_image)
    if info['format'] in (12, 13) and info['tile_mode'] == 0:
        return _encode_block_linear_rgba8(mip_image)
    if info['format'] in ASTC_BLOCKS and info['tile_mode'] == 0:
        return _encode_astc_swizzled(mip_image, info['format'])
    raise PakError(f'TXTR-Format noch nicht eingebaut: Format {info["format"]}, TileMode {info["tile_mode"]}, Swizzle {info["swizzle"]}')

def _encode_mip_chain(info, image):
    mip_images = _build_mip_images(image, info['mip_count'])
    return [_encode_mip_payload(info, mip_image) for mip_image in mip_images]

def can_repack_txtr_asset(original_asset):
    try:
        info = parse_txtr_asset(original_asset)
    except Exception:
        return False
    if info['format'] == 9:
        return True
    if info['format'] in (12, 13) and info['tile_mode'] == 1 and info['swizzle'] == 0:
        return True
    if info['format'] in (12, 13) and info['tile_mode'] == 0:
        return swizzle_block_linear is not None and block_height_mip0 is not None
    if info['format'] in ASTC_BLOCKS and info['tile_mode'] == 0:
        if swizzle_block_linear is None or block_height_mip0 is None:
            return False
        return _has_astc_python() or bool(_find_astcenc())
    return False

def png_to_txtr_asset(original_asset, png_path):
    png_path = Path(png_path)
    if not png_path.is_file():
        raise PakError(f'PNG fehlt: {png_path}')
    info = parse_txtr_asset(original_asset)
    image = Image.open(png_path).convert('RGBA')
    if image.size != (info['width'], info['height']):
        raise PakError(f'PNG-Größe passt nicht | erwartet {info["width"]}x{info["height"]} | gefunden {image.width}x{image.height}')
    mip_payloads = _encode_mip_chain(info, image)
    raw_gpu = b''.join(mip_payloads)
    new_gpu_payload = (0).to_bytes(4, 'big') + raw_gpu
    parts = []
    for chunk in parse_asset_chunks(original_asset):
        payload = original_asset[chunk['payload_off']:chunk['payload_end']]
        if chunk['tag'] == 'GPU ':
            payload = new_gpu_payload
        parts.append(build_chunk_raw(chunk, payload))
    root = bytearray(original_asset[:32])
    w64(root, 4, sum(len(part) for part in parts))
    return bytes(root) + b''.join(parts)
