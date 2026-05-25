from pathlib import Path
import json
import struct
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def f32(data, off):
    return struct.unpack_from('>f', data, off)[0]

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def format_uuid_hex(hex_str):
    if not hex_str or len(hex_str) != 32:
        return hex_str
    return f'{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}'

def _parse_chunks(asset):
    chunks = []
    by_tag = {}
    p = 32
    while p < len(asset):
        if p + 24 > len(asset):
            raise PakError(f'DCLN-Chunk abgeschnitten bei 0x{p:X}')
        tag = tag4(asset, p)
        size = be64(asset, p + 4)
        version = be32(asset, p + 12)
        payload_off = p + 24
        payload_end = payload_off + size
        if payload_end > len(asset):
            raise PakError(f'DCLN-Chunk {tag} läuft über Dateiende')
        chunk = {'tag': tag, 'off': p, 'size': size, 'version': version, 'payload_off': payload_off, 'payload_end': payload_end, 'payload': asset[payload_off:payload_end]}
        chunks.append(chunk)
        by_tag.setdefault(tag, []).append(chunk)
        p = payload_end
    if p != len(asset):
        raise PakError('DCLN endet nicht genau auf Chunk-Grenze')
    return chunks, by_tag

def _one_chunk(by_tag, tag):
    items = by_tag.get(tag, [])
    if len(items) != 1:
        raise PakError(f'DCLN erwartet {tag} genau 1 Mal, gefunden {len(items)}')
    return items[0]

def _parse_info(payload):
    if len(payload) != 24:
        raise PakError(f'DCLN-INFO erwartet 24 Bytes, gefunden {len(payload)}')
    return {'min': (f32(payload, 0), f32(payload, 4), f32(payload, 8)), 'max': (f32(payload, 12), f32(payload, 16), f32(payload, 20))}

def _parse_vertices(payload):
    if len(payload) < 4:
        raise PakError('DCLN-VERT ohne Zähler')
    count = be32(payload, 0)
    expected = 4 + count * 12
    if len(payload) != expected:
        raise PakError(f'DCLN-VERT Größe passt nicht | erwartet {expected}, gefunden {len(payload)}')
    vertices = []
    p = 4
    for index in range(count):
        vertices.append({'index': index, 'pos': (f32(payload, p), f32(payload, p + 4), f32(payload, p + 8))})
        p += 12
    return vertices

def _parse_materials(payload):
    if len(payload) < 4:
        raise PakError('DCLN-MTRL ohne Zähler')
    count = be32(payload, 0)
    expected = 4 + count * 20
    if len(payload) != expected:
        raise PakError(f'DCLN-MTRL Größe passt nicht | erwartet {expected}, gefunden {len(payload)}')
    materials = []
    p = 4
    for index in range(count):
        fields = tuple(be32(payload, p + i * 4) for i in range(5))
        materials.append({'index': index, 'fields': fields, 'hex': [f'0x{x:08X}' for x in fields]})
        p += 20
    return materials

def _parse_triangles(payload, vertex_count, material_count):
    if len(payload) < 4:
        raise PakError('DCLN-TRIS ohne Zähler')
    count = be32(payload, 0)
    expected = 4 + count * 16
    if len(payload) != expected:
        raise PakError(f'DCLN-TRIS Größe passt nicht | erwartet {expected}, gefunden {len(payload)}')
    triangles = []
    p = 4
    for index in range(count):
        a = be32(payload, p)
        b = be32(payload, p + 4)
        c = be32(payload, p + 8)
        raw = be32(payload, p + 12)
        material_index = raw >> 16
        flags = raw & 0xFFFF
        if a >= vertex_count or b >= vertex_count or c >= vertex_count:
            raise PakError(f'DCLN-TRIS Dreieck {index} verweist auf fehlenden Vertex')
        if material_count and material_index >= material_count:
            raise PakError(f'DCLN-TRIS Dreieck {index} verweist auf fehlendes Material {material_index}')
        triangles.append({'index': index, 'vertices': (a, b, c), 'raw': raw, 'material_index': material_index, 'flags': flags})
        p += 16
    return triangles

def _parse_tree(payload):
    if len(payload) < 4:
        raise PakError('DCLN-TREE ohne Zähler')
    count = be32(payload, 0)
    expected = 4 + count * 72
    if len(payload) != expected:
        raise PakError(f'DCLN-TREE Größe passt nicht | erwartet {expected}, gefunden {len(payload)}')
    nodes = []
    p = 4
    for index in range(count):
        values = [f32(payload, p + i * 4) for i in range(15)]
        start = be32(payload, p + 60)
        end = be32(payload, p + 64)
        kind = be32(payload, p + 68)
        nodes.append({
            'index': index,
            'axis_x': tuple(values[0:3]),
            'axis_y': tuple(values[4:7]),
            'axis_z': tuple(values[8:11]),
            'center': (values[3], values[7], values[11]),
            'half_size': tuple(values[12:15]),
            'range_start': start,
            'range_end': end,
            'kind': kind,
            'is_leaf': kind == 0x01000000
        })
        p += 72
    return nodes

def parse_dcln_asset(asset):
    if len(asset) < 32:
        raise PakError('DCLN ist zu klein')
    if asset[:4] != b'RFRM':
        raise PakError('DCLN hat keinen RFRM-Header')
    if tag4(asset, 20) != 'DCLN':
        raise PakError(f'Erwartet DCLN, gefunden {tag4(asset, 20)}')
    root_size = be64(asset, 4)
    if root_size + 32 != len(asset):
        raise PakError(f'DCLN-RFRM-Größe passt nicht | erwartet {root_size + 32}, gefunden {len(asset)}')
    chunks, by_tag = _parse_chunks(asset)
    info = _parse_info(_one_chunk(by_tag, 'INFO')['payload'])
    vertices = _parse_vertices(_one_chunk(by_tag, 'VERT')['payload'])
    materials = _parse_materials(_one_chunk(by_tag, 'MTRL')['payload'])
    triangles = _parse_triangles(_one_chunk(by_tag, 'TRIS')['payload'], len(vertices), len(materials))
    tree_nodes = _parse_tree(_one_chunk(by_tag, 'TREE')['payload'])
    material_use = {}
    for tri in triangles:
        material_use[tri['material_index']] = material_use.get(tri['material_index'], 0) + 1
    return {
        'root_version_a': be32(asset, 24),
        'root_version_b': be32(asset, 28),
        'size': len(asset),
        'sha1': sha1_bytes(asset),
        'chunks': [{'tag': c['tag'], 'size': c['size'], 'version': c['version'], 'off': c['off']} for c in chunks],
        'bbox': info,
        'vertices': vertices,
        'materials': materials,
        'triangles': triangles,
        'tree_nodes': tree_nodes,
        'material_use': material_use
    }

def _entry_base(entry):
    uid = entry['uuid_hex']
    formatted_uid = format_uuid_hex(uid)
    display_name = entry.get('display_name') or entry.get('name') or ''
    if display_name:
        return f'{safe_name(display_name)}_{formatted_uid}'
    return formatted_uid

def _fmt_num(value):
    text = f'{value:.9g}'
    return '0' if text == '-0' else text

def _write_mtl(path, materials):
    palette = [(1.0, 0.18, 0.18), (0.18, 1.0, 0.18), (0.18, 0.35, 1.0), (1.0, 0.85, 0.18), (1.0, 0.18, 1.0), (0.18, 1.0, 1.0), (0.8, 0.8, 0.8), (1.0, 0.55, 0.18)]
    lines = []
    for mat in materials:
        r, g, b = palette[mat['index'] % len(palette)]
        lines.append(f'newmtl dcln_mtrl_{mat["index"]:03d}')
        lines.append(f'Kd {_fmt_num(r)} {_fmt_num(g)} {_fmt_num(b)}')
        lines.append('Ka 0 0 0')
        lines.append('Ks 0 0 0')
        lines.append('d 1')
        lines.append('')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def _write_mesh_obj(info, obj_path, mtl_name=''):
    lines = []
    base = Path(obj_path).stem
    lines.append(f'o {base}')
    if mtl_name:
        lines.append(f'mtllib {mtl_name}')
    for vertex in info['vertices']:
        x, y, z = vertex['pos']
        lines.append(f'v {_fmt_num(x)} {_fmt_num(y)} {_fmt_num(z)}')
    last_mat = None
    for tri in info['triangles']:
        mat = tri['material_index']
        if mat != last_mat:
            lines.append(f'usemtl dcln_mtrl_{mat:03d}')
            lines.append(f'g dcln_mtrl_{mat:03d}')
            last_mat = mat
        a, b, c = tri['vertices']
        lines.append(f'f {a + 1} {b + 1} {c + 1}')
    Path(obj_path).write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')

def _add_vec(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])

def _mul_vec(a, value):
    return (a[0] * value, a[1] * value, a[2] * value)

def _node_corners(node):
    center = node['center']
    ax = _mul_vec(node['axis_x'], node['half_size'][0])
    ay = _mul_vec(node['axis_y'], node['half_size'][1])
    az = _mul_vec(node['axis_z'], node['half_size'][2])
    corners = []
    for sx, sy, sz in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1), (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]:
        p = center
        p = _add_vec(p, _mul_vec(ax, sx))
        p = _add_vec(p, _mul_vec(ay, sy))
        p = _add_vec(p, _mul_vec(az, sz))
        corners.append(p)
    return corners

def _write_tree_obj(info, obj_path):
    lines = ['o dcln_tree']
    edges = [(1, 2), (2, 3), (3, 4), (4, 1), (5, 6), (6, 7), (7, 8), (8, 5), (1, 5), (2, 6), (3, 7), (4, 8)]
    index_base = 1
    for node in info['tree_nodes']:
        lines.append(f'g tree_node_{node["index"]:03d}_{"leaf" if node["is_leaf"] else "branch"}')
        for x, y, z in _node_corners(node):
            lines.append(f'v {_fmt_num(x)} {_fmt_num(y)} {_fmt_num(z)}')
        for a, b in edges:
            lines.append(f'l {index_base + a - 1} {index_base + b - 1}')
        index_base += 8
    Path(obj_path).write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')

def _manifest(entry, info, obj_name, mtl_name, tree_name):
    return {
        'version': 1,
        'entry_index': entry['index'],
        'entry_type': entry['type'],
        'entry_uuid_hex': entry['uuid_hex'],
        'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'],
        'asset_sha1': info['sha1'],
        'root_version_a': info['root_version_a'],
        'root_version_b': info['root_version_b'],
        'obj_name': obj_name,
        'mtl_name': mtl_name,
        'tree_obj_name': tree_name,
        'bbox': info['bbox'],
        'chunks': info['chunks'],
        'vertices': [{'index': v['index'], 'pos': v['pos']} for v in info['vertices']],
        'materials': [{'index': m['index'], 'fields': m['fields'], 'hex': m['hex'], 'triangle_count': info['material_use'].get(m['index'], 0)} for m in info['materials']],
        'triangles': [{'index': t['index'], 'vertices': t['vertices'], 'material_index': t['material_index'], 'flags': t['flags'], 'raw': t['raw']} for t in info['triangles']],
        'tree_nodes': info['tree_nodes']
    }

def _write_report(path, entry, info):
    lines = []
    lines.append(f'DCLN: {entry.get("display_name") or entry.get("name") or entry["uuid_hex"]}')
    lines.append(f'UUID: {format_uuid_hex(entry["uuid_hex"])}')
    lines.append(f'Vertices: {len(info["vertices"])}')
    lines.append(f'Triangles: {len(info["triangles"])}')
    lines.append(f'Materialien: {len(info["materials"])}')
    lines.append(f'TREE-Nodes: {len(info["tree_nodes"])}')
    lines.append(f'Leaf-Nodes: {sum(1 for n in info["tree_nodes"] if n["is_leaf"])}')
    lines.append('')
    lines.append(f'BBox Min: {info["bbox"]["min"]}')
    lines.append(f'BBox Max: {info["bbox"]["max"]}')
    lines.append('')
    lines.append('Materialien:')
    for mat in info['materials']:
        lines.append(f'- #{mat["index"]}: {", ".join(mat["hex"])} | Triangles {info["material_use"].get(mat["index"], 0)}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def export_dcln_as_obj(parsed, entry, out_dir):
    if entry['type'] != 'DCLN':
        raise PakError('DCLN-Export geht nur bei DCLN')
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    asset = get_entry_asset(parsed, entry)
    info = parse_dcln_asset(asset)
    base = _entry_base(entry)
    obj_path = out_dir / f'{base}_collision.obj'
    mtl_path = out_dir / f'{base}_collision.mtl'
    tree_path = out_dir / f'{base}_collision_tree.obj'
    _write_mtl(mtl_path, info['materials'])
    _write_mesh_obj(info, obj_path, mtl_path.name)
    _write_tree_obj(info, tree_path)
    return {'obj_path': str(obj_path), 'mtl_path': str(mtl_path), 'tree_obj_path': str(tree_path), 'vertex_count': len(info['vertices']), 'triangle_count': len(info['triangles']), 'material_count': len(info['materials']), 'tree_node_count': len(info['tree_nodes'])}

def export_dcln_package(parsed, entry, out_dir):
    if entry['type'] != 'DCLN':
        raise PakError('Collisionpaket geht nur bei DCLN')
    out_dir = Path(out_dir)
    package_dir = out_dir / f'{_entry_base(entry)}_dcln_collision'
    package_dir.mkdir(parents=True, exist_ok=True)
    asset = get_entry_asset(parsed, entry)
    info = parse_dcln_asset(asset)
    obj_name = 'collision.obj'
    mtl_name = 'collision.mtl'
    tree_name = 'collision_tree.obj'
    _write_mtl(package_dir / mtl_name, info['materials'])
    _write_mesh_obj(info, package_dir / obj_name, mtl_name)
    _write_tree_obj(info, package_dir / tree_name)
    manifest = _manifest(entry, info, obj_name, mtl_name, tree_name)
    manifest_path = package_dir / 'dcln_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    report_path = package_dir / 'report.txt'
    _write_report(report_path, entry, info)
    return {'package_dir': str(package_dir), 'manifest_path': str(manifest_path), 'obj_path': str(package_dir / obj_name), 'mtl_path': str(package_dir / mtl_name), 'tree_obj_path': str(package_dir / tree_name), 'vertex_count': len(info['vertices']), 'triangle_count': len(info['triangles']), 'material_count': len(info['materials']), 'tree_node_count': len(info['tree_nodes'])}

def format_dcln_info_lines(info):
    lines = []
    lines.append('DCLN-Analyse:')
    lines.append(f'- Version: {info["root_version_a"]} / {info["root_version_b"]}')
    lines.append(f'- Vertices: {len(info["vertices"])}')
    lines.append(f'- Triangles: {len(info["triangles"])}')
    lines.append(f'- Materialien: {len(info["materials"])}')
    lines.append(f'- TREE-Nodes: {len(info["tree_nodes"])}')
    lines.append(f'- TREE-Leaves: {sum(1 for n in info["tree_nodes"] if n["is_leaf"])}')
    lines.append(f'- BBox Min: ({", ".join(_fmt_num(x) for x in info["bbox"]["min"])})')
    lines.append(f'- BBox Max: ({", ".join(_fmt_num(x) for x in info["bbox"]["max"])})')
    if info['materials']:
        lines.append('Materialien:')
        for mat in info['materials']:
            use = info['material_use'].get(mat['index'], 0)
            lines.append(f'- #{mat["index"]}: {", ".join(mat["hex"])} | Triangles {use}')
    return lines
