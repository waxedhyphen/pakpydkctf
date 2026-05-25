from pathlib import Path
from collections import defaultdict
import json
import math
import struct
from pak_core import get_entry_asset, safe_name, sha1_bytes
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
    return [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]

def box_triangles():
    return [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 4, 5), (0, 5, 1), (1, 5, 6), (1, 6, 2), (2, 6, 7), (2, 7, 3), (3, 7, 4), (3, 4, 0)]

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

def build_preview_geometry(parsed, ref):
    asset = get_entry_asset(parsed, ref['entry'])
    if ref['entry_type'] == 'DCLN':
        dcln = parse_dcln_asset(asset)
        return [v['pos'] for v in dcln['vertices']], [t['vertices'] for t in dcln['triangles']], 'dcln', 'mesh'
    if ref['entry_type'] == 'CLSN':
        clsn = parse_clsn_asset(asset)
        return [v['pos'] for v in clsn['vertices']], [t['vertices'] for t in clsn['triangles']], 'clsn', 'mesh'
    bounds = parse_head_bounds(asset) or fallback_bounds(ref['entry_type'])
    return box_vertices(bounds), box_triangles(), ref['entry_type'].lower(), 'box'

def transform_json(transform):
    if not transform:
        return None
    return {'position': list(transform.get('position') or (0.0, 0.0, 0.0)), 'rotation': list(transform.get('rotation') or (0.0, 0.0, 0.0)), 'scale': list(transform.get('scale') or (1.0, 1.0, 1.0))}

def unique_split_path(split_root, entry_type, uuid_hex, used_names):
    kind_dir = split_root / entry_type
    kind_dir.mkdir(parents=True, exist_ok=True)
    base = format_uuid_hex(uuid_hex)
    key = (entry_type, base)
    used_names[key] += 1
    idx = used_names[key]
    name = f'{base}.obj' if idx == 1 else f'{base}__{idx:02d}.obj'
    return kind_dir / name

def write_split_obj(path, name, vertices, triangles, transform):
    lines = [f'o {name}']
    for vertex in vertices:
        p = apply_transform(vertex, transform)
        lines.append(f'v {fmt_num(p[0])} {fmt_num(p[1])} {fmt_num(p[2])}')
    for tri in triangles:
        a, b, c = tri
        lines.append(f'f {a + 1} {b + 1} {c + 1}')
    Path(path).write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')

def write_room_scene_preview(parsed, room_entry, package_dir):
    package_dir = Path(package_dir)
    info, refs = collect_preview_refs(parsed, room_entry)
    obj_path = package_dir / 'room_scene_preview.obj'
    mtl_path = package_dir / 'room_scene_preview.mtl'
    tsv_path = package_dir / 'room_scene_preview.tsv'
    split_root = package_dir / 'room_scene_objects'
    split_index_path = package_dir / 'room_scene_objects.tsv'
    repack_manifest_path = package_dir / 'room_scene_repack_manifest.json'
    write_mtl(mtl_path)
    lines = ['o room_scene_preview', 'mtllib room_scene_preview.mtl']
    vertex_base = 1
    counts = {'DCLN': 0, 'CLSN': 0, 'WMDL': 0, 'CMDL': 0, 'SMDL': 0, 'CHAR': 0, 'errors': 0}
    report = ['index\ttype\tuuid\tlayer\tparent_actor\tcomponent\tposition\trotation\tscale\tmode\tsplit_path']
    split_report = ['index\ttype\tuuid\tlayer\tparent_actor\tcomponent\tposition\trotation\tscale\tmode\tpath']
    manifest_objects = []
    used_names = defaultdict(int)
    written_split = 0
    for index, ref in enumerate(refs):
        transform = ref.get('transform')
        name = obj_name(ref)
        split_rel = ''
        mode = ''
        try:
            vertices, triangles, material, mode = build_preview_geometry(parsed, ref)
            vertex_base = add_mesh(lines, vertices, triangles, transform, material, name, vertex_base)
            split_path = unique_split_path(split_root, ref['entry_type'], ref['uuid_hex'], used_names)
            write_split_obj(split_path, name, vertices, triangles, transform)
            split_rel = str(split_path.relative_to(package_dir))
            manifest_objects.append({'index': index, 'path': split_rel, 'obj_sha1': sha1_bytes(split_path.read_bytes()), 'mode': mode, 'entry_index': ref['entry']['index'], 'entry_type': ref['entry_type'], 'entry_uuid_hex': ref['uuid_hex'], 'component_uuid_hex': ref['component_uuid_hex'], 'component_type_hash': ref['component_type_hash'], 'component_name': ref['component_name'], 'layer_name': ref['layer_name'], 'parent_name': ref['parent_name'], 'transform': transform_json(transform)})
            written_split += 1
            counts[ref['entry_type']] += 1
        except Exception as e:
            counts['errors'] += 1
            mode = f'error:{e}'
        report.append(f'{index}\t{ref["entry_type"]}\t{format_uuid_hex(ref["uuid_hex"])}\t{ref["layer_name"]}\t{ref["parent_name"]}\t{ref["component_name"]}\t{transform_text(transform, "position")}\t{transform_text(transform, "rotation")}\t{transform_text(transform, "scale")}\t{mode}\t{split_rel}')
        split_report.append(f'{index}\t{ref["entry_type"]}\t{format_uuid_hex(ref["uuid_hex"])}\t{ref["layer_name"]}\t{ref["parent_name"]}\t{ref["component_name"]}\t{transform_text(transform, "position")}\t{transform_text(transform, "rotation")}\t{transform_text(transform, "scale")}\t{mode}\t{split_rel}')
    obj_path.write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    tsv_path.write_text('\n'.join(report), encoding='utf-8', newline='\n')
    split_index_path.write_text('\n'.join(split_report), encoding='utf-8', newline='\n')
    repack_manifest = {'version': 1, 'source_pak': Path(parsed['path']).name, 'room_entry_index': room_entry['index'], 'room_entry_uuid_hex': room_entry['uuid_hex'], 'room_entry_name': room_entry.get('display_name') or room_entry.get('name') or room_entry['uuid_hex'], 'object_root': str(split_root.relative_to(package_dir)), 'objects': manifest_objects}
    repack_manifest_path.write_text(json.dumps(repack_manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'preview_obj_path': str(obj_path), 'preview_mtl_path': str(mtl_path), 'preview_tsv_path': str(tsv_path), 'preview_split_dir': str(split_root), 'preview_split_tsv_path': str(split_index_path), 'preview_repack_manifest_path': str(repack_manifest_path), 'preview_split_count': written_split, 'preview_counts': counts, 'preview_ref_count': len(refs)}
