from pathlib import Path
import math
import struct
from pak_core import PakError, get_entry_asset, safe_name
from dcln_codec import parse_dcln_asset, format_uuid_hex
from clsn_codec import parse_clsn_asset
from room_scene_codec import parse_room_asset, first_parent_transform, transform_text, fmt_num

def asset_uuid_map(parsed):
    wanted = {'WMDL', 'SMDL', 'CMDL', 'CHAR', 'CLSN', 'DCLN'}
    out = {}
    for entry in parsed.get('entries', []):
        if entry.get('type') in wanted:
            out[entry['uuid_hex'].lower()] = entry
    return out

def find_all(data, needle):
    out = []
    start = 0
    while True:
        off = data.find(needle, start)
        if off < 0:
            return out
        out.append(off)
        start = off + 1

def component_body(component):
    try:
        return bytes.fromhex(component.get('body_hex') or '')
    except Exception:
        return b''

def collect_preview_refs(parsed, room_entry):
    asset = get_entry_asset(parsed, room_entry)
    info = parse_room_asset(asset)
    known = asset_uuid_map(parsed)
    refs = []
    seen = set()
    for component in info['components']:
        body = component_body(component)
        transform = first_parent_transform(component)
        parents = component.get('parents') or []
        parent_name = parents[0]['name'] if parents else ''
        for uuid_hex, entry in known.items():
            if find_all(body, bytes.fromhex(uuid_hex)):
                key = (component['uuid_hex'], uuid_hex)
                if key in seen:
                    continue
                seen.add(key)
                refs.append({'uuid_hex': uuid_hex, 'entry': entry, 'entry_type': entry['type'], 'component_name': component['name'], 'component_uuid_hex': component['uuid_hex'], 'component_type_hash': component['type_hash'], 'layer_name': component['layer_name'], 'parent_name': parent_name, 'transform': transform})
    return info, refs

def rotate_xyz(point, rotation):
    x, y, z = point
    if not rotation:
        return (x, y, z)
    rx, ry, rz = rotation
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return (x, y, z)

def apply_transform(point, transform):
    if not transform:
        return point
    scale = transform.get('scale') or (1.0, 1.0, 1.0)
    rotation = transform.get('rotation') or (0.0, 0.0, 0.0)
    position = transform.get('position') or (0.0, 0.0, 0.0)
    p = (point[0] * scale[0], point[1] * scale[1], point[2] * scale[2])
    p = rotate_xyz(p, rotation)
    return (p[0] + position[0], p[1] + position[1], p[2] + position[2])

def parse_head_bounds(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM':
        return None
    root_end = min(len(asset), 32 + int.from_bytes(asset[4:12], 'big'))
    p = 32
    while p + 24 <= root_end:
        tag = asset[p:p+4]
        size = int.from_bytes(asset[p+4:p+12], 'big')
        payload = p + 24
        end = payload + size
        if end > root_end:
            break
        if tag == b'HEAD' and size >= 44:
            values = struct.unpack('>11f', asset[payload:payload+44])
            mn = values[5:8]
            mx = values[8:11]
            if all(math.isfinite(v) for v in mn + mx):
                if all(abs(v) < 1000000 for v in mn + mx):
                    return (mn, mx)
        p = end
    return None

def fallback_bounds(entry_type):
    if entry_type == 'CHAR':
        return ((-0.5, 0.0, -0.5), (0.5, 2.0, 0.5))
    if entry_type == 'SMDL':
        return ((-0.5, -0.5, -0.5), (0.5, 0.5, 0.5))
    return ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0))

def box_vertices(bounds):
    mn, mx = bounds
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    return [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]

def box_faces(base):
    faces = [(0,1,2),(0,2,3),(4,6,5),(4,7,6),(0,4,5),(0,5,1),(1,5,6),(1,6,2),(2,6,7),(2,7,3),(3,7,4),(3,4,0)]
    return [(base+a, base+b, base+c) for a,b,c in faces]

def write_mtl(path):
    mats = {'dcln': (1, 0.2, 0.2), 'clsn': (0.2, 0.8, 1), 'wmdl': (0.6, 0.6, 0.6), 'cmdl': (0.8, 0.8, 0.4), 'smdl': (0.8, 0.4, 0.8), 'char': (0.4, 0.8, 0.4)}
    lines = []
    for name, color in mats.items():
        lines.append(f'newmtl {name}')
        lines.append(f'Kd {fmt_num(color[0])} {fmt_num(color[1])} {fmt_num(color[2])}')
        lines.append('Ka 0 0 0')
        lines.append('Ks 0 0 0')
        lines.append('d 1')
        lines.append('')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def obj_name(ref):
    return safe_name(f'{ref["entry_type"]}_{format_uuid_hex(ref["uuid_hex"])}_{ref["parent_name"]}_{ref["component_name"]}')

def add_mesh(lines, vertices, triangles, transform, material, name, vertex_base):
    lines.append(f'g {name}')
    lines.append(f'usemtl {material}')
    for vertex in vertices:
        p = apply_transform(vertex, transform)
        lines.append(f'v {fmt_num(p[0])} {fmt_num(p[1])} {fmt_num(p[2])}')
    for tri in triangles:
        a, b, c = tri
        lines.append(f'f {vertex_base + a} {vertex_base + b} {vertex_base + c}')
    return vertex_base + len(vertices)

def write_room_scene_preview(parsed, room_entry, package_dir):
    package_dir = Path(package_dir)
    info, refs = collect_preview_refs(parsed, room_entry)
    obj_path = package_dir / 'room_scene_preview.obj'
    mtl_path = package_dir / 'room_scene_preview.mtl'
    write_mtl(mtl_path)
    lines = ['o room_scene_preview', 'mtllib room_scene_preview.mtl']
    vertex_base = 1
    counts = {'DCLN': 0, 'CLSN': 0, 'WMDL': 0, 'CMDL': 0, 'SMDL': 0, 'CHAR': 0, 'errors': 0}
    report = ['index\ttype\tuuid\tlayer\tparent_actor\tcomponent\tposition\trotation\tscale\tmode']
    for index, ref in enumerate(refs):
        entry = ref['entry']
        transform = ref.get('transform')
        material = ref['entry_type'].lower()
        name = obj_name(ref)
        mode = 'box'
        try:
            asset = get_entry_asset(parsed, entry)
            if ref['entry_type'] == 'DCLN':
                dcln = parse_dcln_asset(asset)
                vertices = [v['pos'] for v in dcln['vertices']]
                triangles = [t['vertices'] for t in dcln['triangles']]
                vertex_base = add_mesh(lines, vertices, triangles, transform, 'dcln', name, vertex_base)
                mode = 'mesh'
            elif ref['entry_type'] == 'CLSN':
                clsn = parse_clsn_asset(asset)
                vertices = [v['pos'] for v in clsn['vertices']]
                triangles = [t['vertices'] for t in clsn['triangles']]
                vertex_base = add_mesh(lines, vertices, triangles, transform, 'clsn', name, vertex_base)
                mode = 'mesh'
            else:
                bounds = parse_head_bounds(asset) or fallback_bounds(ref['entry_type'])
                vertices = box_vertices(bounds)
                triangles = [(a-1,b-1,c-1) for a,b,c in box_faces(1)]
                vertex_base = add_mesh(lines, vertices, triangles, transform, material, name, vertex_base)
            counts[ref['entry_type']] += 1
        except Exception as e:
            counts['errors'] += 1
            mode = f'error:{e}'
        report.append(f'{index}\t{ref["entry_type"]}\t{format_uuid_hex(ref["uuid_hex"])}\t{ref["layer_name"]}\t{ref["parent_name"]}\t{ref["component_name"]}\t{transform_text(transform, "position")}\t{transform_text(transform, "rotation")}\t{transform_text(transform, "scale")}\t{mode}')
    obj_path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    report_path = package_dir / 'room_scene_preview.tsv'
    report_path.write_text('\n'.join(report), encoding='utf-8', newline='\n')
    return {'preview_obj_path': str(obj_path), 'preview_mtl_path': str(mtl_path), 'preview_tsv_path': str(report_path), 'preview_counts': counts, 'preview_ref_count': len(refs)}
