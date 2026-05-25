from pathlib import Path
import os
import re
import struct
import zlib
from pak_core import PakError, get_entry_asset, get_entry_payload, format_uuid_hex, safe_name

def be16(data, offset):
    return struct.unpack_from('>H', data, offset)[0]

def be32(data, offset):
    return struct.unpack_from('>I', data, offset)[0]

def be64(data, offset):
    return struct.unpack_from('>Q', data, offset)[0]

def read_half(data, offset):
    return struct.unpack_from('<e', data, offset)[0]

def parse_chunks(data):
    if len(data) < 0x20 or data[0:4] != b'RFRM' or data[0x14:0x18] not in (b'CMDL', b'SMDL', b'WMDL'):
        raise PakError('Keine gültige Model-Datei')
    offset = 0x20
    chunks = {}
    while offset + 0x18 <= len(data):
        chunk_type = data[offset:offset + 4]
        if chunk_type == b'\x00\x00\x00\x00':
            break
        size = be64(data, offset + 4)
        payload_offset = offset + 0x18
        payload_end = payload_offset + size
        if payload_end > len(data):
            raise PakError('Model-Chunk ist unvollständig')
        chunks[chunk_type.decode('ascii', errors='replace')] = data[payload_offset:payload_end]
        offset = payload_end
    for name in ('HEAD', 'MESH', 'VBUF', 'IBUF', 'GPU '):
        if name not in chunks:
            raise PakError(f'Benötigter Chunk fehlt: {name}')
    return chunks

def parse_head(payload):
    if len(payload) < 0x30:
        raise PakError('HEAD-Chunk ist zu klein')
    counts = [be32(payload, i) for i in range(0, 20, 4)]
    mins = struct.unpack_from('>3f', payload, 20)
    maxs = struct.unpack_from('>3f', payload, 32)
    return {'mesh_buckets': counts, 'bbox_min': mins, 'bbox_max': maxs}

def parse_meshes(payload):
    count = be32(payload, 0)
    offset = 4
    meshes = []
    for index in range(count):
        if offset + 21 > len(payload):
            raise PakError('MESH-Chunk ist unvollständig')
        meshes.append({
            'mesh_index': index,
            'primitive_mode': be32(payload, offset),
            'material_index': be16(payload, offset + 4),
            'vertex_buffer_index': payload[offset + 6],
            'index_buffer_index': payload[offset + 7],
            'index_buffer_offset': be32(payload, offset + 8),
            'index_count': be32(payload, offset + 12),
            'field_10': be16(payload, offset + 16),
            'field_12': payload[offset + 18],
            'field_13': payload[offset + 19],
            'flags': payload[offset + 20],
        })
        offset += 21
    return meshes

def parse_vbufs(payload):
    count = be32(payload, 0)
    offset = 4
    buffers = []
    for _ in range(count):
        if offset + 12 > len(payload):
            raise PakError('VBUF-Chunk ist unvollständig')
        vertex_count = be32(payload, offset)
        component_count = be32(payload, offset + 4)
        offset += 8
        components = []
        for _ in range(component_count):
            if offset + 20 > len(payload):
                raise PakError('VBUF-Komponente ist unvollständig')
            components.append({
                'field_0': be32(payload, offset + 0),
                'offset': be32(payload, offset + 4),
                'stride': be32(payload, offset + 8),
                'format': be32(payload, offset + 12),
                'type': be32(payload, offset + 16),
            })
            offset += 20
        stride = components[0]['stride'] if components else 0
        buffers.append({
            'vertex_count': vertex_count,
            'component_count': component_count,
            'components': components,
            'stride': stride
        })
    return buffers

def parse_ibufs(payload):
    count = be32(payload, 0)
    offset = 4
    buffers = []
    for _ in range(count):
        if offset + 4 > len(payload):
            raise PakError('IBUF-Chunk ist unvollständig')
        buffers.append({'index_type': be32(payload, offset)})
        offset += 4
    return buffers

def parse_material_names(payload, mesh_count):
    names = []
    if not payload or len(payload) < 4:
        return [f'material_{i}' for i in range(mesh_count)]
    try:
        count = be32(payload, 0)
        offset = 4
        for i in range(count):
            if offset + 4 > len(payload):
                break
            name_len = be32(payload, offset)
            offset += 4
            if name_len <= 0 or offset + name_len > len(payload):
                break
            raw = payload[offset:offset + name_len]
            offset += name_len
            name = raw.decode('utf-8', errors='ignore').strip().replace('\x00', '')
            name = re.sub(r'[^A-Za-z0-9_\\-.:/]+', '_', name)
            if not name:
                name = f'material_{i}'
            names.append(name)
            if offset + 28 > len(payload):
                break
            offset += 16
            offset += 4
            offset += 4
            data_count = be32(payload, offset)
            offset += 4
            for _ in range(data_count):
                if offset + 8 > len(payload):
                    offset = len(payload)
                    break
                data_type = be32(payload, offset + 4)
                offset += 8
                if data_type == 0:
                    if offset + 20 > len(payload):
                        offset = len(payload)
                        break
                    offset += 20
                elif data_type == 1:
                    if offset + 16 > len(payload):
                        offset = len(payload)
                        break
                    offset += 16
                elif data_type == 2:
                    if offset + 4 > len(payload):
                        offset = len(payload)
                        break
                    offset += 4
                elif data_type == 4:
                    if offset + 49 > len(payload):
                        offset = len(payload)
                        break
                    inner = offset
                    inner += 4 + 16 + 16 + 16 + 1
                    for _ in range(3):
                        if inner + 16 > len(payload):
                            inner = len(payload)
                            break
                        object_id = payload[inner:inner + 16]
                        inner += 16
                        if object_id != b'\x00' * 16:
                            if inner + 20 > len(payload):
                                inner = len(payload)
                                break
                            inner += 20
                    offset = inner
                elif data_type == 5:
                    if offset + 16 > len(payload):
                        offset = len(payload)
                        break
                    offset += 16
                else:
                    offset = len(payload)
                    break
        while len(names) < mesh_count:
            names.append(f'material_{len(names)}')
        return names[:mesh_count]
    except Exception:
        return [f'material_{i}' for i in range(mesh_count)]

GPU_MARKERS = {0x0D000000, 0x0C000000, 0x0B000000, 0x0A000000, 0x09000000, 0x08000000, 0x07000000, 0x06000000, 0x05000000, 0x04000000, 0x03000000, 0x02000000, 0x01000000, 0x00000000}

class MemoryInput:
    def __init__(self, data):
        self.data = data
        self.offset = 0
    def read_byte(self):
        if self.offset >= len(self.data):
            raise PakError('GPU-Stream endet unerwartet')
        value = self.data[self.offset]
        self.offset += 1
        return value
    def read(self, size):
        if self.offset + size > len(self.data):
            raise PakError('GPU-Stream endet unerwartet')
        out = self.data[self.offset:self.offset + size]
        self.offset += size
        return out

class LSBBitReader:
    def __init__(self, data):
        self.data = data
        self.offset = 0
        self.current = 0
        self.bits_left = 0
    def read_bit(self):
        if self.bits_left:
            bit = self.current & 1
            self.current >>= 1
            self.bits_left -= 1
            return bit
        if self.offset >= len(self.data):
            return 0
        self.current = self.data[self.offset]
        self.offset += 1
        bit = self.current & 1
        self.current >>= 1
        self.bits_left = 7
        return bit

class AdaptiveArithmeticDecoder:
    HALF = 0x8000
    FIRST_QTR = 0x4000
    THIRD_QTR = 0xC000
    EOF_SYMBOL = 257
    SYMBOL_COUNT = 257
    MAX_FREQ = 0x3FFF
    def __init__(self, data):
        self.reader = LSBBitReader(data)
        self.low = 0
        self.high = 0xFFFF
        self.code = 0
        self.initialized = False
        self.char_to_index = [i + 1 for i in range(256)]
        self.index_to_char = [None] * (self.SYMBOL_COUNT + 1)
        for i in range(256):
            self.index_to_char[i + 1] = i
        self.freq = [0] * (self.SYMBOL_COUNT + 1)
        self.cum = [0] * (self.SYMBOL_COUNT + 1)
        for i in range(1, self.SYMBOL_COUNT + 1):
            self.freq[i] = 1
        self.cum[self.SYMBOL_COUNT] = 0
        for i in range(self.SYMBOL_COUNT - 1, -1, -1):
            self.cum[i] = self.cum[i + 1] + self.freq[i + 1]
    def _init_code(self):
        if self.initialized:
            return
        self.initialized = True
        for _ in range(16):
            self.code = (self.code << 1) | self.reader.read_bit()
    def update_model(self, symbol):
        if self.cum[0] >= self.MAX_FREQ:
            for i in range(1, self.SYMBOL_COUNT + 1):
                self.freq[i] = (self.freq[i] + 1) // 2
            self.cum[self.SYMBOL_COUNT] = 0
            for i in range(self.SYMBOL_COUNT - 1, -1, -1):
                self.cum[i] = self.cum[i + 1] + self.freq[i + 1]
        i = symbol
        while i > 0 and self.freq[i] == self.freq[i - 1]:
            i -= 1
        if i < symbol:
            left = self.index_to_char[i]
            right = self.index_to_char[symbol]
            self.index_to_char[i], self.index_to_char[symbol] = right, left
            if left is not None:
                self.char_to_index[left] = symbol
            if right is not None:
                self.char_to_index[right] = i
            symbol = i
        self.freq[symbol] += 1
        while symbol > 0:
            symbol -= 1
            self.cum[symbol] += 1
    def read_byte(self):
        self._init_code()
        value_range = self.high - self.low + 1
        scaled = (((self.code - self.low + 1) * self.cum[0] - 1) // value_range)
        lo = 1
        hi = self.SYMBOL_COUNT
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cum[mid] > scaled:
                lo = mid + 1
            else:
                hi = mid
        symbol = lo
        self.high = self.low + (value_range * self.cum[symbol - 1] // self.cum[0]) - 1
        self.low = self.low + (value_range * self.cum[symbol] // self.cum[0])
        while True:
            if self.high < self.HALF:
                pass
            elif self.low >= self.HALF:
                self.code -= self.HALF
                self.low -= self.HALF
                self.high -= self.HALF
            elif self.low >= self.FIRST_QTR and self.high < self.THIRD_QTR:
                self.code -= self.FIRST_QTR
                self.low -= self.FIRST_QTR
                self.high -= self.FIRST_QTR
            else:
                break
            self.low <<= 1
            self.high = (self.high << 1) | 1
            self.code = (self.code << 1) | self.reader.read_bit()
        if symbol == self.EOF_SYMBOL:
            raise EOFError
        out = self.index_to_char[symbol]
        self.update_model(symbol)
        return out

class ArithmeticInput:
    def __init__(self, data):
        self.decoder = AdaptiveArithmeticDecoder(data)
    def read_byte(self):
        try:
            return self.decoder.read_byte()
        except EOFError:
            raise PakError('Arithmetik-Stream endet unerwartet')
    def read(self, size):
        out = bytearray()
        for _ in range(size):
            out.append(self.read_byte())
        return bytes(out)

def decode_lzss_stream(stream, out_size, unit, count_bias, use_three_bytes):
    out = bytearray(out_size)
    dst = 0
    header = 0
    group = 0
    while dst < out_size:
        if group == 0:
            header = stream.read_byte()
            group = 8
        if header & 0x80:
            a = stream.read_byte()
            if use_three_bytes:
                b = stream.read_byte()
                c = stream.read_byte()
                count = a + count_bias
                length = ((b << 8) | c) * unit
            else:
                b = stream.read_byte()
                count = (a >> 4) + count_bias
                length = (((a & 0x0F) << 8) | b) * unit
            seek = dst - length
            if seek < 0:
                raise PakError('LZSS-Rücksprung liegt vor dem Ausgabepuffer')
            total = count * unit
            if dst + total > out_size:
                raise PakError('LZSS-Ausgabe läuft über die erwartete Zielgröße')
            for _ in range(total):
                out[dst] = out[seek]
                dst += 1
                seek += 1
        else:
            total = unit
            raw = stream.read(total)
            if dst + total > out_size:
                raise PakError('LZSS-Ausgabe läuft über die erwartete Zielgröße')
            out[dst:dst + total] = raw
            dst += total
        header = (header << 1) & 0xFF
        group -= 1
    return bytes(out)

def decode_gpu_block_data(tag, payload, expected_size=0):
    if tag == 0x00000000:
        return payload
    if tag == 0x0D000000:
        return zlib.decompress(payload)
    if expected_size <= 0:
        raise PakError(f'GPU-Typ 0x{tag:08X} braucht eine bekannte Zielgröße')
    if tag == 0x01000000:
        return decode_lzss_stream(MemoryInput(payload), expected_size, 1, 3, False)
    if tag == 0x02000000:
        return decode_lzss_stream(MemoryInput(payload), expected_size, 2, 2, False)
    if tag == 0x03000000:
        return decode_lzss_stream(MemoryInput(payload), expected_size, 4, 1, False)
    if tag == 0x04000000:
        return decode_lzss_stream(ArithmeticInput(payload), expected_size, 1, 3, False)
    if tag == 0x05000000:
        return decode_lzss_stream(ArithmeticInput(payload), expected_size, 2, 2, False)
    if tag == 0x06000000:
        return decode_lzss_stream(ArithmeticInput(payload), expected_size, 4, 1, False)
    if tag == 0x07000000:
        return decode_lzss_stream(MemoryInput(payload), expected_size, 1, 1, True)
    if tag == 0x08000000:
        return decode_lzss_stream(MemoryInput(payload), expected_size, 2, 1, True)
    if tag == 0x09000000:
        return decode_lzss_stream(MemoryInput(payload), expected_size, 4, 1, True)
    if tag == 0x0A000000:
        return decode_lzss_stream(ArithmeticInput(payload), expected_size, 1, 1, True)
    if tag == 0x0B000000:
        return decode_lzss_stream(ArithmeticInput(payload), expected_size, 2, 1, True)
    if tag == 0x0C000000:
        return decode_lzss_stream(ArithmeticInput(payload), expected_size, 4, 1, True)
    raise PakError(f'Nicht unterstützter GPU-Typ 0x{tag:08X}')

def decompress_gpu_blocks(payload):
    blocks = []
    offset = 0
    while offset < len(payload):
        if offset + 4 > len(payload):
            break
        tag = be32(payload, offset)
        data_start = offset + 4
        if tag == 0x0D000000:
            dec = zlib.decompressobj()
            data = dec.decompress(payload[data_start:])
            consumed = len(payload[data_start:]) - len(dec.unused_data)
            if consumed <= 0:
                raise PakError('GPU-Zlibstream konnte nicht gelesen werden')
            blocks.append({'tag': tag, 'payload': payload[data_start:data_start + consumed], 'data': data, 'handled': True})
            offset = data_start + consumed
            continue
        next_positions = []
        for marker in GPU_MARKERS:
            idx = payload.find(marker.to_bytes(4, 'big'), data_start)
            if idx != -1:
                next_positions.append(idx)
        next_offset = min(next_positions) if next_positions else len(payload)
        raw = payload[data_start:next_offset]
        handled = tag == 0x00000000
        data = raw if handled else b''
        blocks.append({'tag': tag, 'payload': raw, 'data': data, 'handled': handled})
        offset = next_offset
    return blocks

def parse_vertices(vertex_buffer, raw_vertex_data):
    stride = vertex_buffer['stride']
    reported_vertex_count = vertex_buffer['vertex_count']
    if stride <= 0:
        raise PakError('Vertex-Stride ist ungültig')
    actual_vertex_count = min(reported_vertex_count, len(raw_vertex_data) // stride)
    if actual_vertex_count <= 0:
        raise PakError('Keine lesbaren Vertexdaten gefunden')
    positions = []
    normals = []
    uvs = []
    uv_semantics = {4, 5, 6, 7, 8, 9, 10}
    normal_semantics = {1}
    tangent_semantics = {2, 3, 12, 13}
    for index in range(actual_vertex_count):
        base = index * stride
        position = (0.0, 0.0, 0.0)
        normal = None
        uv = None
        for component in vertex_buffer['components']:
            entry = base + component['offset']
            fmt = component['format']
            typ = component['type']
            if fmt == 37 and entry + 12 <= len(raw_vertex_data):
                value = struct.unpack_from('<3f', raw_vertex_data, entry)
                if typ == 0:
                    position = value
            elif fmt == 34 and entry + 8 <= len(raw_vertex_data):
                value = (
                    read_half(raw_vertex_data, entry + 0),
                    read_half(raw_vertex_data, entry + 2),
                    read_half(raw_vertex_data, entry + 4),
                    read_half(raw_vertex_data, entry + 6),
                )
                if typ in normal_semantics and normal is None:
                    normal = value[:3]
                elif typ in tangent_semantics and normal is None:
                    normal = value[:3]
            elif fmt in (20, 21) and entry + 4 <= len(raw_vertex_data):
                value = (read_half(raw_vertex_data, entry + 0), read_half(raw_vertex_data, entry + 2))
                if typ in uv_semantics and uv is None:
                    uv = value
        positions.append(position)
        normals.append(normal)
        uvs.append(uv)
    return {
        'positions': positions,
        'normals': normals,
        'uvs': uvs,
        'reported_vertex_count': reported_vertex_count,
        'actual_vertex_count': actual_vertex_count,
        'truncated': actual_vertex_count < reported_vertex_count
    }

def parse_indices(index_buffer, raw_index_data):
    index_type = index_buffer['index_type']
    if index_type in (0, 1):
        usable = len(raw_index_data) - (len(raw_index_data) % 2)
        return list(struct.unpack('<' + 'H' * (usable // 2), raw_index_data[:usable]))
    if index_type == 2:
        usable = len(raw_index_data) - (len(raw_index_data) % 4)
        return list(struct.unpack('<' + 'I' * (usable // 4), raw_index_data[:usable]))
    raise PakError(f'Nicht unterstützter Indextyp: {index_type}')

def build_faces(primitive_mode, index_values, vertex_limit=None):
    faces = []
    if primitive_mode == 3:
        for offset in range(0, len(index_values) - 2, 3):
            a, b, c = index_values[offset:offset + 3]
            if vertex_limit is not None and (a >= vertex_limit or b >= vertex_limit or c >= vertex_limit):
                continue
            if a != b and b != c and a != c:
                faces.append((a, b, c))
        return faces
    if primitive_mode == 4:
        flip = False
        for offset in range(len(index_values) - 2):
            a, b, c = index_values[offset:offset + 3]
            if vertex_limit is not None and (a >= vertex_limit or b >= vertex_limit or c >= vertex_limit):
                flip = not flip
                continue
            if a == b or b == c or a == c:
                flip = not flip
                continue
            faces.append((b, a, c) if flip else (a, b, c))
            flip = not flip
        return faces
    raise PakError(f'Primitive Mode {primitive_mode} wird noch nicht unterstützt')

def load_model_bytes(data):
    chunks = parse_chunks(data)
    head = parse_head(chunks['HEAD'])
    meshes = parse_meshes(chunks['MESH'])
    vbufs = parse_vbufs(chunks['VBUF'])
    ibufs = parse_ibufs(chunks['IBUF'])
    materials = parse_material_names(chunks.get('MTRL', b''), max(1, len(meshes)))
    gpu_blocks = decompress_gpu_blocks(chunks['GPU '])
    if not gpu_blocks:
        raise PakError('GPU-Block konnte nicht gelesen werden')
    used_vbuf_indices = sorted({mesh['vertex_buffer_index'] for mesh in meshes})
    used_ibuf_indices = sorted({mesh['index_buffer_index'] for mesh in meshes})
    if used_vbuf_indices and max(used_vbuf_indices) >= len(gpu_blocks):
        raise PakError('Es fehlen GPU-Blöcke für Vertexdaten')
    index_block_start = len(vbufs)
    if used_ibuf_indices and index_block_start + max(used_ibuf_indices) >= len(gpu_blocks):
        raise PakError('Es fehlen GPU-Blöcke für Indexdaten')
    for i in used_vbuf_indices:
        block = gpu_blocks[i]
        expected = vbufs[i]['vertex_count'] * vbufs[i]['stride']
        if not block.get('handled'):
            block['data'] = decode_gpu_block_data(block['tag'], block['payload'], expected)
            block['handled'] = True
        actual = len(block['data'])
        if actual < expected:
            raise PakError(f'Vertex-Block {i} ist zu kurz | erwartet {expected} Bytes | gefunden {actual} Bytes')
    for i in used_ibuf_indices:
        block = gpu_blocks[index_block_start + i]
        if not block.get('handled'):
            bytes_per_index = 2 if ibufs[i]['index_type'] in (0, 1) else 4 if ibufs[i]['index_type'] == 2 else 0
            if bytes_per_index <= 0:
                raise PakError(f'Nicht unterstützter Indextyp: {ibufs[i]["index_type"]}')
            expected = 0
            for mesh in meshes:
                if mesh['index_buffer_index'] == i:
                    end = mesh['index_buffer_offset'] + mesh['index_count']
                    if end > expected:
                        expected = end
            expected *= bytes_per_index
            block['data'] = decode_gpu_block_data(block['tag'], block['payload'], expected)
            block['handled'] = True
    vertex_sets = {}
    for i in used_vbuf_indices:
        vertex_sets[i] = parse_vertices(vbufs[i], gpu_blocks[i]['data'])
    index_sets = {}
    for i in used_ibuf_indices:
        index_sets[i] = parse_indices(ibufs[i], gpu_blocks[index_block_start + i]['data'])
    return {
        'file_type': data[0x14:0x18].decode('ascii'),
        'head': head,
        'materials': materials,
        'meshes': meshes,
        'vertex_sets': vertex_sets,
        'index_sets': index_sets,
    }

def pick_best_txtr_refs(material):
    refs = list(material.get('txtr_refs', []))
    if not refs:
        return []
    priority = (
        'DIFFTXTR',
        'COLRTXTR',
        'ALBDTXTR',
        'BASETXTR',
        'BASEXTR',
        'ALBRTXTR',
    )
    ordered = []
    used = set()
    for wanted in priority:
        for ref in refs:
            key = (ref['tag'], ref['uuid_hex'])
            if ref['tag'].upper() == wanted and key not in used:
                ordered.append(ref)
                used.add(key)
    for ref in refs:
        key = (ref['tag'], ref['uuid_hex'])
        if key not in used:
            ordered.append(ref)
            used.add(key)
    return ordered

def get_mtl_slot_for_ref_tag(tag):
    tag = str(tag or '').upper()
    if tag in ('DIFFTXTR', 'DIFTTXTR', 'COLRTXTR', 'ALBDTXTR', 'BASETXTR', 'BASEXTR', 'ALBRTXTR'):
        return 'map_Kd'
    if tag in ('NMAPTXTR', 'NRMLTXTR', 'NORMTXTR'):
        return 'map_Bump'
    if tag in ('SPCTTXTR', 'SPECXTR', 'SPECTXTR'):
        return 'map_Ks'
    if tag in ('ICANTXTR', 'EMISTXTR', 'EMISXTR'):
        return 'map_Ke'
    return ''

def make_fs_name(text):
    return safe_name(text)

def make_material_texture_png_name(material, ref, txtr_entry):
    txtr_base = txtr_entry.get('display_name') or txtr_entry.get('name') or txtr_entry['uuid_hex']
    mat_base = material.get('name') or material['uuid_hex']
    return f'{make_fs_name(mat_base)}__{ref["tag"].lower()}__{make_fs_name(txtr_base)}.png'

def write_obj(model, output_obj_path, write_mtl=True, material_texture_map=None):
    material_texture_map = material_texture_map or {}
    os.makedirs(os.path.dirname(output_obj_path) or '.', exist_ok=True)
    base_name = os.path.splitext(os.path.basename(output_obj_path))[0]
    mtl_name = base_name + '.mtl'
    used_vbuf_indices = sorted(model['vertex_sets'])
    vertex_base = {}
    positions = []
    normals = []
    uvs = []
    next_base = 1
    for vbuf_index in used_vbuf_indices:
        vertex_set = model['vertex_sets'][vbuf_index]
        vertex_base[vbuf_index] = next_base
        positions.extend(vertex_set['positions'])
        normals.extend(vertex_set['normals'])
        uvs.extend(vertex_set['uvs'])
        next_base += len(vertex_set['positions'])
    face_count = 0
    with open(output_obj_path, 'w', encoding='utf-8', newline='\n') as handle:
        if write_mtl:
            handle.write(f'mtllib {mtl_name}\n')
        handle.write(f'o {base_name}\n')
        for x, y, z in positions:
            handle.write(f'v {x:.9g} {y:.9g} {z:.9g}\n')
        for uv in uvs:
            if uv is None:
                handle.write('vt 0 0\n')
            else:
                u, v = uv
                handle.write(f'vt {u:.9g} {1.0 - v:.9g}\n')
        for normal in normals:
            if normal is None:
                handle.write('vn 0 0 1\n')
            else:
                x, y, z = normal
                handle.write(f'vn {x:.9g} {y:.9g} {z:.9g}\n')
        for mesh in model['meshes']:
            vbuf_index = mesh['vertex_buffer_index']
            if vbuf_index not in model['vertex_sets']:
                continue
            if mesh['index_buffer_index'] not in model['index_sets']:
                continue
            vertex_set = model['vertex_sets'][vbuf_index]
            vertex_limit = len(vertex_set['positions'])
            handle.write(f'g mesh_{mesh["mesh_index"]}\n')
            material_name = str(model['materials'][mesh['material_index']]) if mesh['material_index'] < len(model['materials']) else f'material_{mesh["material_index"]}'
            if write_mtl:
                handle.write(f'usemtl {material_name}\n')
            indices = model['index_sets'][mesh['index_buffer_index']]
            start = mesh['index_buffer_offset']
            end = start + mesh['index_count']
            mesh_indices = indices[start:end]
            faces = build_faces(mesh['primitive_mode'], mesh_indices, vertex_limit=vertex_limit)
            base = vertex_base[vbuf_index] - 1
            for a, b, c in faces:
                a += 1 + base
                b += 1 + base
                c += 1 + base
                handle.write(f'f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n')
            face_count += len(faces)
    if face_count <= 0:
        raise PakError('OBJ-Export erzeugte 0 Faces')
    mtl_path = ''
    if write_mtl:
        mtl_path = os.path.join(os.path.dirname(output_obj_path), mtl_name)
        used_indices = []
        for mesh in model['meshes']:
            if mesh['material_index'] not in used_indices:
                used_indices.append(mesh['material_index'])
        with open(mtl_path, 'w', encoding='utf-8', newline='\n') as handle:
            for index in used_indices:
                name = str(model['materials'][index]) if index < len(model['materials']) else f'material_{index}'
                handle.write(f'newmtl {name}\n')
                handle.write('Ka 0 0 0\n')
                handle.write('Kd 1 1 1\n')
                handle.write('Ks 0 0 0\n')
                handle.write('d 1\n')
                texture_info = material_texture_map.get(index, {})
                if isinstance(texture_info, str):
                    texture_info = {'map_Kd': texture_info}
                if not texture_info:
                    texture_info = material_texture_map.get(name, {})
                if isinstance(texture_info, str):
                    texture_info = {'map_Kd': texture_info}
                if not texture_info:
                    for candidate_name, candidate_info in material_texture_map.items():
                        if isinstance(candidate_name, str) and str(candidate_name).strip().lower() == name.strip().lower():
                            texture_info = candidate_info
                            break
                if isinstance(texture_info, str):
                    texture_info = {'map_Kd': texture_info}
                for slot_name in ('map_Kd', 'map_Bump', 'map_Ks', 'map_Ke'):
                    texture_name = texture_info.get(slot_name, '')
                    if texture_name:
                        handle.write(f'{slot_name} {texture_name}\n')
                handle.write('\n')
    return {'obj_path': output_obj_path, 'mtl_path': mtl_path, 'face_count': face_count}

def export_model_entry_as_obj(parsed, entry, out_dir, write_mtl=True, material_texture_map=None):
    asset = get_entry_asset(parsed, entry)
    model = load_model_bytes(asset)
    if entry.get('model_materials'):
        material_names = list(model.get('materials', []))
        max_index = max((m['index'] for m in entry['model_materials']), default=-1)
        target_len = max(len(material_names), max_index + 1)
        while len(material_names) < target_len:
            material_names.append(f'material_{len(material_names)}')
        for material in entry['model_materials']:
            idx = material['index']
            material_names[idx] = str(material.get('name') or f'material_{idx}')
        model['materials'] = material_names
    base = entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    base = safe_name(base)
    obj_path = str(Path(out_dir) / f'{base}_{entry["type"].lower()}.obj')
    result = write_obj(model, obj_path, write_mtl=write_mtl, material_texture_map=material_texture_map)
    result['vertex_count'] = sum(len(v['positions']) for v in model['vertex_sets'].values())
    result['mesh_count'] = len(model['meshes'])
    result['material_count'] = len(model['materials'])
    return result

def export_linked_txtrs_for_material(parsed, material, out_dir):
    written = []
    uuid_to_entry = parsed.get('uuid_to_entry', {})
    for ref in material.get('txtr_refs', []):
        txtr_entry = uuid_to_entry.get(ref['uuid_hex'])
        if txtr_entry is None:
            continue
        out_path = Path(out_dir) / make_material_texture_png_name(material, ref, txtr_entry)
        try:
            export_txtr_item_as_png(parsed, txtr_entry, out_path)
            written.append(str(out_path))
        except Exception:
            continue
    return written

def try_export_txtr_item_as_png(parsed, entry, out_path):
    try:
        export_txtr_item_as_png(parsed, entry, out_path)
        return None
    except Exception as e:
        return str(e)
    
def build_material_texture_map(parsed, entry, out_dir):
    material_texture_map = {}
    written = []
    errors = []
    uuid_to_entry = parsed.get('uuid_to_entry', {})
    exported_by_uuid = {}
    ignored_tags = {'ICANTXTR', 'REFVTXTR'}
    for material in entry.get('model_materials', []):
        slot_map = {}
        fallback_kd = ''
        for ref in material.get('txtr_refs', []):
            tag = str(ref['tag']).upper()
            txtr_entry = uuid_to_entry.get(ref['uuid_hex'])
            if txtr_entry is None:
                if tag not in ignored_tags:
                    errors.append(f'{material["name"]} | {ref["tag"]} | TXTR nicht im PAK gefunden')
                continue
            if txtr_entry.get('type') != 'TXTR':
                if tag not in ignored_tags:
                    errors.append(f'{material["name"]} | {ref["tag"]} | {txtr_entry.get("display_name") or txtr_entry.get("name") or txtr_entry["uuid_hex"]} | Referenz ist kein TXTR sondern {txtr_entry.get("type") or "unbekannt"}')
                continue
            filename = exported_by_uuid.get(txtr_entry['uuid_hex'])
            if not filename:
                filename = make_material_texture_png_name(material, ref, txtr_entry)
                out_path = Path(out_dir) / filename
                err = try_export_txtr_item_as_png(parsed, txtr_entry, out_path)
                if err is not None:
                    if tag not in ignored_tags:
                        errors.append(f'{material["name"]} | {ref["tag"]} | {txtr_entry.get("display_name") or txtr_entry.get("name") or txtr_entry["uuid_hex"]} | {err}')
                    continue
                exported_by_uuid[txtr_entry['uuid_hex']] = filename
                written.append(str(out_path))
            slot_name = get_mtl_slot_for_ref_tag(ref['tag'])
            if slot_name and slot_name not in slot_map:
                slot_map[slot_name] = filename
            if not fallback_kd and 'NMAP' not in tag and 'NRML' not in tag and 'NORM' not in tag and 'SPCT' not in tag and 'SPEC' not in tag and 'SPCF' not in tag and 'EMIS' not in tag and 'ICAN' not in tag and 'REFV' not in tag and 'REFS' not in tag and 'FUR' not in tag:
                fallback_kd = filename
        if 'map_Kd' not in slot_map and fallback_kd:
            slot_map['map_Kd'] = fallback_kd
        if slot_map:
            material_texture_map[material['index']] = dict(slot_map)
            material_texture_map[str(material['name'])] = dict(slot_map)
    return material_texture_map, written, errors

def export_model_with_options(parsed, entry, out_dir, write_mtl=True, export_textures=False):
    material_texture_map = {}
    texture_paths = []
    texture_errors = []
    if export_textures:
        material_texture_map, texture_paths, texture_errors = build_material_texture_map(parsed, entry, out_dir)
        if texture_errors:
            raise PakError('Texture-Export unvollständig:\n' + '\n'.join(texture_errors[:80]))
    result = export_model_entry_as_obj(parsed, entry, out_dir, write_mtl=write_mtl, material_texture_map=material_texture_map)
    result['texture_paths'] = texture_paths
    result['texture_errors'] = texture_errors
    result['material_texture_map'] = material_texture_map
    return result

def convert_txtr_to_png_bytes(raw):
    from txtrpreview import txtr_to_png_bytes
    return txtr_to_png_bytes(raw)

def export_txtr_bytes_as_png(asset, out_path):
    if len(asset) < 64:
        raise PakError('TXTR ist zu klein für PNG-Export')
    png = convert_txtr_to_png_bytes(asset)
    if not png or len(png) < 32:
        raise PakError('TXTR konnte nicht sinnvoll als PNG erzeugt werden')
    Path(out_path).write_bytes(png)
    return str(out_path)

def export_txtr_item_as_png(parsed, entry, out_path):
    if entry.get('type') != 'TXTR':
        raise PakError(f'Eintrag ist kein TXTR sondern {entry.get("type") or "unbekannt"}')
    asset = get_entry_asset(parsed, entry)
    return export_txtr_bytes_as_png(asset, out_path)
