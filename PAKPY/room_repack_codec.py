from pathlib import Path
import csv
import math
import struct
from pak_core import PakError, get_entry_asset, rebuild_pak
from clsn_codec import parse_clsn_asset
from dcln_codec import parse_dcln_asset, format_uuid_hex

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def w64(buf, off, value):
    buf[off:off+8] = int(value).to_bytes(8, 'big')

def w32(value):
    return int(value).to_bytes(4, 'big')

def f32(value):
    return struct.pack('>f', float(value))

def parse_vec(text, default):
    text = (text or '').strip()
    if not text:
        return default
    parts = [p.strip() for p in text.split(',')]
    if len(parts) != 3:
        return default
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except Exception:
        return default

def rotate_xyz(point, rotation):
    x, y, z = point
    rx, ry, rz = rotation
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    y, z = y * cx - z * sx, y * sx + z * cx
    x, z = x * cy + z * sy, -x * sy + z * cy
    x, y = x * cz - y * sz, x * sz + y * cz
    return (x, y, z)

def inverse_rotate_xyz(point, rotation):
    x, y, z = point
    rx, ry, rz = rotation
    cz, sz = math.cos(-rz), math.sin(-rz)
    x, y = x * cz - y * sz, x * sz + y * cz
    cy, sy = math.cos(-ry), math.sin(-ry)
    x, z = x * cy + z * sy, -x * sy + z * cy
    cx, sx = math.cos(-rx), math.sin(-rx)
    y, z = y * cx - z * sx, y * sx + z * cx
    return (x, y, z)

def world_to_local(point, position, rotation, scale):
    p = (point[0] - position[0], point[1] - position[1], point[2] - position[2])
    p = inverse_rotate_xyz(p, rotation)
    sx = scale[0] if abs(scale[0]) > 0.000001 else 1.0
    sy = scale[1] if abs(scale[1]) > 0.000001 else 1.0
    sz = scale[2] if abs(scale[2]) > 0.000001 else 1.0
    return (p[0] / sx, p[1] / sy, p[2] / sz)

def parse_obj(path):
    vertices = []
    faces = []
    for raw in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if parts[0] == 'v' and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == 'f' and len(parts) >= 4:
            ids = []
            for token in parts[1:]:
                head = token.split('/')[0]
                if not head:
                    continue
                idx = int(head)
                if idx < 0:
                    idx = len(vertices) + idx + 1
                ids.append(idx - 1)
            for i in range(1, len(ids) - 1):
                faces.append((ids[0], ids[i], ids[i + 1]))
    if not vertices or not faces:
        raise PakError(f'OBJ enthält keine nutzbare Geometrie: {path}')
    return vertices, faces

def iter_chunks(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM':
        raise PakError('Asset hat keinen RFRM-Header')
    end = 32 + be64(asset, 4)
    p = 32
    while p < end:
        if p + 24 > end:
            raise PakError('Chunk abgeschnitten')
        size = be64(asset, p + 4)
        payload_off = p + 24
        payload_end = payload_off + size
        if payload_end > end:
            raise PakError('Chunk läuft über Asset-Ende')
        yield {'tag': asset[p:p+4].decode('ascii', 'replace'), 'off': p, 'header': asset[p:p+24], 'payload': asset[payload_off:payload_end], 'end': payload_end}
        p = payload_end

def build_chunk(old_header, payload):
    header = bytearray(old_header)
    w64(header, 4, len(payload))
    return bytes(header) + payload

def bbox(vertices):
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

def build_info_payload(vertices):
    mn, mx = bbox(vertices)
    return b''.join(f32(x) for x in (mn + mx))

def build_vert_payload(vertices):
    out = bytearray()
    out += w32(len(vertices))
    for v in vertices:
        out += f32(v[0]) + f32(v[1]) + f32(v[2])
    return bytes(out)

def old_triangle_attrs(old_asset, kind):
    if kind == 'DCLN':
        old = parse_dcln_asset(old_asset)
        return [(t.get('material_index', 0), t.get('flags', 0), t.get('raw', 0)) for t in old['triangles']]
    old = parse_clsn_asset(old_asset)
    return [(t.get('material_index', 0), t.get('flags', 0), 0) for t in old['triangles']]

def build_tris_payload(faces, attrs, kind):
    out = bytearray()
    out += w32(len(faces))
    for i, face in enumerate(faces):
        mat, flags, raw = attrs[i] if i < len(attrs) else (attrs[-1] if attrs else (0, 0, 0))
        out += w32(face[0]) + w32(face[1]) + w32(face[2])
        if kind == 'DCLN':
            value = raw if raw else ((int(mat) & 0xFFFF) << 16) | (int(flags) & 0xFFFF)
            out += w32(value)
        else:
            out += int(mat & 0xFFFF).to_bytes(2, 'big') + int(flags & 0xFFFF).to_bytes(2, 'big')
    return bytes(out)

def build_tree_payload(vertices, faces):
    mn, mx = bbox(vertices)
    center = ((mn[0] + mx[0]) * 0.5, (mn[1] + mx[1]) * 0.5, (mn[2] + mx[2]) * 0.5)
    half = (max((mx[0] - mn[0]) * 0.5, 0.0001), max((mx[1] - mn[1]) * 0.5, 0.0001), max((mx[2] - mn[2]) * 0.5, 0.0001))
    out = bytearray()
    out += w32(1)
    values = (1.0, 0.0, 0.0, center[0], 0.0, 1.0, 0.0, center[1], 0.0, 0.0, 1.0, center[2], half[0], half[1], half[2])
    for value in values:
        out += f32(value)
    out += w32(0)
    out += w32(len(faces))
    out += w32(0x01000000)
    return bytes(out)

def build_asset_from_obj(old_asset, kind, vertices, faces):
    chunks = list(iter_chunks(old_asset))
    attrs = old_triangle_attrs(old_asset, kind)
    replacements = {
        'VERT': build_vert_payload(vertices),
        'TRIS': build_tris_payload(faces, attrs, kind),
        'TREE': build_tree_payload(vertices, faces)
    }
    if kind == 'DCLN':
        replacements['INFO'] = build_info_payload(vertices)
    body = bytearray()
    replaced_any = False
    for chunk in chunks:
        payload = replacements.get(chunk['tag'], chunk['payload'])
        if chunk['tag'] in replacements:
            replaced_any = True
        body += build_chunk(chunk['header'], payload)
    if not replaced_any:
        raise PakError(f'{kind} enthält keine ersetzbaren VERT/TRIS/TREE-Chunks')
    root = bytearray(old_asset[:32])
    w64(root, 4, len(body))
    return bytes(root) + bytes(body)

def read_scene_rows(folder):
    path = Path(folder) / 'room_scene_objects.tsv'
    if not path.exists():
        raise PakError('room_scene_objects.tsv fehlt im ROOM-Paket')
    rows = []
    with path.open('r', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f, delimiter='\t'):
            rows.append(row)
    return rows

def row_obj_path(folder, row):
    value = (row.get('path') or '').strip()
    if not value:
        return None
    path = Path(folder) / value
    if not path.exists():
        return None
    return path

def find_entry(parsed, uuid_hex, kind):
    compact = uuid_hex.replace('-', '').lower()
    entry = parsed.get('uuid_to_entry', {}).get(compact)
    if entry is None:
        for item in parsed.get('entries', []):
            if item.get('uuid_hex') == compact:
                entry = item
                break
    if entry is None or entry.get('type') != kind:
        return None
    return entry

def collect_room_package_replacements(parsed, folder):
    rows = read_scene_rows(folder)
    replacements = {}
    changed = []
    skipped = []
    seen_assets = set()
    for row in rows:
        kind = (row.get('type') or '').strip().upper()
        if kind not in ('DCLN', 'CLSN'):
            continue
        obj_path = row_obj_path(folder, row)
        if obj_path is None:
            skipped.append(f'{kind} {row.get("uuid", "")} | OBJ fehlt')
            continue
        compact = (row.get('uuid') or '').replace('-', '').lower()
        key = (kind, compact)
        if key in seen_assets:
            skipped.append(f'{kind} {row.get("uuid", "")} | Mehrfachnutzung, Asset wurde bereits aus erstem OBJ gebaut')
            continue
        seen_assets.add(key)
        entry = find_entry(parsed, row.get('uuid', ''), kind)
        if entry is None:
            skipped.append(f'{kind} {row.get("uuid", "")} | nicht im aktuellen PAK')
            continue
        world_vertices, faces = parse_obj(obj_path)
        position = parse_vec(row.get('position'), (0.0, 0.0, 0.0))
        rotation = parse_vec(row.get('rotation'), (0.0, 0.0, 0.0))
        scale = parse_vec(row.get('scale'), (1.0, 1.0, 1.0))
        local_vertices = [world_to_local(v, position, rotation, scale) for v in world_vertices]
        old_asset = get_entry_asset(parsed, entry)
        new_asset = build_asset_from_obj(old_asset, kind, local_vertices, faces)
        if new_asset != old_asset:
            replacements[entry['index']] = {'asset_bytes': new_asset}
            changed.append(f'{kind} {format_uuid_hex(entry["uuid_hex"])} | {obj_path.name} | Vertices {len(local_vertices)} | Faces {len(faces)}')
    return replacements, changed, skipped

def rebuild_room_package_from_folder(parsed, folder, out_path):
    replacements, changed, skipped = collect_room_package_replacements(parsed, folder)
    if not replacements:
        raise PakError('Keine geänderten DCLN/CLSN-OBJs zum Zurückbauen gefunden')
    result_path = rebuild_pak(parsed, replacements, out_path)
    return {'out_path': result_path, 'changed_count': len(changed), 'changed_files': changed, 'skipped': skipped}
