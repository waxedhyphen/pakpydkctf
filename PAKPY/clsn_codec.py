from pathlib import Path
import struct
from pak_core import PakError, sha1_bytes

def be16(data, off):
    return int.from_bytes(data[off:off+2], 'big')

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def parse_chunk(asset, off, limit):
    if off + 24 > limit:
        raise PakError(f'CLSN-Chunk abgeschnitten bei 0x{off:X}')
    size = be64(asset, off + 4)
    payload = off + 24
    end = payload + size
    if end > limit:
        raise PakError(f'CLSN-Chunk läuft über Dateiende bei 0x{off:X}')
    return {'tag': tag4(asset, off), 'off': off, 'size': size, 'payload_off': payload, 'end': end, 'version': be32(asset, off + 12)}

def iter_chunks(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM' or tag4(asset, 20) != 'CLSN':
        raise PakError('CLSN hat keinen gültigen RFRM/CLSN-Header')
    root_end = 32 + be64(asset, 4)
    if root_end > len(asset):
        raise PakError('CLSN-RFRM-Größe läuft über Dateiende')
    p = 32
    while p < root_end:
        chunk = parse_chunk(asset, p, root_end)
        yield chunk
        p = chunk['end']

def parse_vertices(payload):
    if len(payload) < 4:
        raise PakError('CLSN-VERT ist zu kurz')
    count = be32(payload, 0)
    need = 4 + count * 12
    if need > len(payload):
        raise PakError('CLSN-VERT läuft über Dateiende')
    vertices = []
    p = 4
    for index in range(count):
        x, y, z = struct.unpack('>fff', payload[p:p+12])
        vertices.append({'index': index, 'pos': (x, y, z)})
        p += 12
    return vertices

def parse_triangles(payload):
    if len(payload) < 4:
        raise PakError('CLSN-TRIS ist zu kurz')
    count = be32(payload, 0)
    need = 4 + count * 16
    if need > len(payload):
        raise PakError('CLSN-TRIS läuft über Dateiende')
    triangles = []
    p = 4
    for index in range(count):
        a = be32(payload, p)
        b = be32(payload, p + 4)
        c = be32(payload, p + 8)
        material_index = be16(payload, p + 12)
        flags = be16(payload, p + 14)
        triangles.append({'index': index, 'vertices': (a, b, c), 'material_index': material_index, 'flags': flags})
        p += 16
    return triangles

def parse_materials(payload):
    if len(payload) < 4:
        return []
    count = be32(payload, 0)
    materials = []
    p = 4
    for index in range(count):
        if p + 20 > len(payload):
            break
        values = tuple(be32(payload, p + i * 4) for i in range(5))
        materials.append({'index': index, 'values': values})
        p += 20
    return materials

def parse_tree(payload):
    if len(payload) < 4:
        return {'count': 0, 'raw_hex': payload.hex()}
    count = be32(payload, 0)
    return {'count': count, 'raw_hex': payload.hex()}

def parse_clsn_asset(asset):
    chunks = []
    vertices = []
    triangles = []
    materials = []
    tree = None
    for chunk in iter_chunks(asset):
        payload = asset[chunk['payload_off']:chunk['end']]
        chunks.append({'tag': chunk['tag'], 'off': chunk['off'], 'size': chunk['size'], 'version': chunk['version']})
        if chunk['tag'] == 'VERT':
            vertices = parse_vertices(payload)
        elif chunk['tag'] == 'TRIS':
            triangles = parse_triangles(payload)
        elif chunk['tag'] == 'MTRL':
            materials = parse_materials(payload)
        elif chunk['tag'] == 'TREE':
            tree = parse_tree(payload)
    return {'type': 'CLSN', 'sha1': sha1_bytes(asset), 'root_version_a': be32(asset, 24), 'root_version_b': be32(asset, 28), 'chunks': chunks, 'vertices': vertices, 'triangles': triangles, 'materials': materials, 'tree': tree, 'vertex_count': len(vertices), 'triangle_count': len(triangles), 'material_count': len(materials)}

def fmt_num(value):
    text = f'{value:.9g}'
    return '0' if text == '-0' else text

def write_clsn_obj(asset, path, object_name='clsn'):
    clsn = parse_clsn_asset(asset)
    lines = [f'o {object_name}']
    for vertex in clsn['vertices']:
        x, y, z = vertex['pos']
        lines.append(f'v {fmt_num(x)} {fmt_num(y)} {fmt_num(z)}')
    last_mat = None
    for tri in clsn['triangles']:
        mat = tri['material_index']
        if mat != last_mat:
            lines.append(f'g {object_name}_m{mat}')
            last_mat = mat
        a, b, c = tri['vertices']
        lines.append(f'f {a + 1} {b + 1} {c + 1}')
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return clsn
