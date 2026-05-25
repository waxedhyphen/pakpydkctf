import os
import re
import struct
import zlib
from windows_compat import safe_path_component


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
        raise ValueError('Keine gueltige Retro-Studios-Modelldatei.')
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
            raise ValueError('Chunk ist unvollstaendig.')
        chunks[chunk_type.decode('ascii', errors='replace')] = data[payload_offset:payload_end]
        offset = payload_end
    needed = ['HEAD', 'MESH', 'VBUF', 'IBUF', 'GPU ']
    for name in needed:
        if name not in chunks:
            raise ValueError(f'Benötigter Chunk fehlt: {name}')
    return chunks


def parse_head(payload):
    if len(payload) < 0x30:
        raise ValueError('HEAD-Chunk ist zu klein.')
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
            raise ValueError('MESH-Chunk ist unvollstaendig.')
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
            raise ValueError('VBUF-Chunk ist unvollstaendig.')
        vertex_count = be32(payload, offset)
        component_count = be32(payload, offset + 4)
        offset += 8
        components = []
        for _ in range(component_count):
            if offset + 20 > len(payload):
                raise ValueError('VBUF-Komponente ist unvollstaendig.')
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
            raise ValueError('IBUF-Chunk ist unvollstaendig.')
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
            name = re.sub(r'[^A-Za-z0-9_\-.:/]+', '_', name)
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


GPU_MARKERS = {0x0D000000, 0x0C000000, 0x04000000, 0x01000000, 0x09000000, 0x00000000}


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
                raise ValueError('GPU-Zlibstream konnte nicht gelesen werden.')
            blocks.append({'tag': tag, 'data': data})
            offset = data_start + consumed
            continue
        next_positions = []
        for marker in GPU_MARKERS:
            idx = payload.find(marker.to_bytes(4, 'big'), data_start)
            if idx != -1:
                next_positions.append(idx)
        next_offset = min(next_positions) if next_positions else len(payload)
        raw = payload[data_start:next_offset]
        blocks.append({'tag': tag, 'data': raw})
        offset = next_offset
    return blocks


def parse_vertices(vertex_buffer, raw_vertex_data):
    stride = vertex_buffer['stride']
    reported_vertex_count = vertex_buffer['vertex_count']
    if stride <= 0:
        raise ValueError('Vertex-Stride ist ungueltig.')
    actual_vertex_count = min(reported_vertex_count, len(raw_vertex_data) // stride)
    if actual_vertex_count <= 0:
        raise ValueError('Keine lesbaren Vertexdaten gefunden.')
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
    raise ValueError(f'Nicht unterstuetzter Indextyp: {index_type}')


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
    raise ValueError(f'Primitive Mode {primitive_mode} wird noch nicht unterstuetzt.')


def load_cmdl(path):
    data = open(path, 'rb').read()
    chunks = parse_chunks(data)
    head = parse_head(chunks['HEAD'])
    meshes = parse_meshes(chunks['MESH'])
    vbufs = parse_vbufs(chunks['VBUF'])
    ibufs = parse_ibufs(chunks['IBUF'])
    materials = parse_material_names(chunks.get('MTRL', b''), max(1, len(meshes)))
    gpu_blocks = decompress_gpu_blocks(chunks['GPU '])
    if not gpu_blocks:
        raise ValueError('GPU-Block konnte nicht gelesen werden.')
    used_vbuf_indices = sorted({mesh['vertex_buffer_index'] for mesh in meshes})
    used_ibuf_indices = sorted({mesh['index_buffer_index'] for mesh in meshes})
    if used_vbuf_indices and max(used_vbuf_indices) >= len(gpu_blocks):
        raise ValueError('Es fehlen GPU-Blöcke für Vertexdaten.')
    index_block_start = len(vbufs)
    if used_ibuf_indices and index_block_start + max(used_ibuf_indices) >= len(gpu_blocks):
        raise ValueError('Es fehlen GPU-Blöcke für Indexdaten.')
    vertex_sets = {}
    vertex_warnings = []
    for i in used_vbuf_indices:
        parsed = parse_vertices(vbufs[i], gpu_blocks[i]['data'])
        vertex_sets[i] = parsed
        if parsed['truncated']:
            vertex_warnings.append(f'VBUF {i}: Header {parsed["reported_vertex_count"]}, lesbar {parsed["actual_vertex_count"]}')
    index_sets = {}
    for i in used_ibuf_indices:
        index_sets[i] = parse_indices(ibufs[i], gpu_blocks[index_block_start + i]['data'])
    return {
        'path': path,
        'file_type': data[0x14:0x18].decode('ascii'),
        'head': head,
        'materials': materials,
        'meshes': meshes,
        'vertex_sets': vertex_sets,
        'index_sets': index_sets,
        'vbufs': vbufs,
        'ibufs': ibufs,
        'gpu_block_count': len(gpu_blocks),
        'vertex_warnings': vertex_warnings,
    }


def write_obj(model, output_obj_path):
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
            material_name = model['materials'][mesh['material_index']] if mesh['material_index'] < len(model['materials']) else f'material_{mesh["material_index"]}'
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
    mtl_path = os.path.join(os.path.dirname(output_obj_path), mtl_name)
    material_names = []
    used_indices = []
    for mesh in model['meshes']:
        if mesh['material_index'] not in used_indices:
            used_indices.append(mesh['material_index'])
    for index in used_indices:
        if index < len(model['materials']):
            material_names.append(model['materials'][index])
        else:
            material_names.append(f'material_{index}')
    with open(mtl_path, 'w', encoding='utf-8', newline='\n') as handle:
        for name in material_names:
            handle.write(f'newmtl {name}\n')
            handle.write('Ka 0 0 0\n')
            handle.write('Kd 1 1 1\n')
            handle.write('Ks 0 0 0\n')
            handle.write('d 1\n\n')
    return output_obj_path, mtl_path, face_count


def convert_cmdl_to_obj(source_path, output_dir):
    model = load_cmdl(source_path)
    base = safe_path_component(os.path.splitext(os.path.basename(source_path))[0])
    output_obj_path = os.path.join(output_dir, base + '.obj')
    obj_path, mtl_path, face_count = write_obj(model, output_obj_path)
    return {
        'source_path': source_path,
        'output_obj_path': obj_path,
        'output_mtl_path': mtl_path,
        'vertex_count': sum(len(v['positions']) for v in model['vertex_sets'].values()),
        'mesh_count': len(model['meshes']),
        'index_count_total': sum(mesh['index_count'] for mesh in model['meshes']),
        'face_count': face_count,
        'material_count': len(model['materials']),
        'bbox_min': model['head']['bbox_min'],
        'bbox_max': model['head']['bbox_max'],
        'file_type': model['file_type'],
        'vertex_warnings': model['vertex_warnings'],
    }
