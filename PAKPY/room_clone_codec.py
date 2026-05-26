from pathlib import Path
from collections import defaultdict
import math
import re
import struct
import uuid
from pak_core import PakError
from room_scene_codec import parse_room_asset

CLONE_NAME_RE = re.compile(r'^(clone[0-9]+)\.(.+)\.obj$', re.IGNORECASE)
UUID_RE = re.compile(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32})')

def clean_hex(text):
    return ''.join(ch for ch in (text or '').lower() if ch in '0123456789abcdef')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def w64(buf, off, value):
    buf[off:off+8] = int(value).to_bytes(8, 'big')

def obj_transform(item):
    transform = item.get('transform') or {}
    return {'position': tuple(float(x) for x in (transform.get('position') or (0.0, 0.0, 0.0))), 'rotation': tuple(float(x) for x in (transform.get('rotation') or (0.0, 0.0, 0.0))), 'scale': tuple(float(x) for x in (transform.get('scale') or (1.0, 1.0, 1.0)))}

def parse_obj(path):
    vertices = []
    faces = []
    for raw_line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0] == 'v' and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == 'f' and len(parts) >= 4:
            indexes = []
            for token in parts[1:]:
                raw = token.split('/')[0]
                if not raw:
                    raise PakError(f'OBJ-Face ohne Vertex-Index: {path}')
                index = int(raw)
                if index < 0:
                    index = len(vertices) + index + 1
                indexes.append(index - 1)
            for i in range(1, len(indexes) - 1):
                faces.append((indexes[0], indexes[i], indexes[i + 1]))
    if not vertices or not faces:
        raise PakError(f'OBJ enthält keine nutzbare Geometrie: {path}')
    for face in faces:
        for index in face:
            if index < 0 or index >= len(vertices):
                raise PakError(f'OBJ-Face verweist auf ungültigen Vertex: {path}')
    return vertices, faces

def proxy_vertices_from_obj(obj):
    proxy_bounds = obj.get('proxy_bounds') or [[-0.5, -0.5, -0.5], [0.5, 0.5, 0.5]]
    mn = tuple(float(x) for x in proxy_bounds[0])
    mx = tuple(float(x) for x in proxy_bounds[1])
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    return [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]

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

def apply_transform(point, transform):
    scale = transform['scale']
    position = transform['position']
    p = (point[0] * scale[0], point[1] * scale[1], point[2] * scale[2])
    p = rotate_xyz(p, transform['rotation'])
    return (p[0] + position[0], p[1] + position[1], p[2] + position[2])

def bounds(vertices):
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

def solve4(matrix, vector):
    a = [list(row) + [float(vector[i])] for i, row in enumerate(matrix)]
    n = 4
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        if abs(a[pivot][col]) < 0.000000000001:
            return None
        if pivot != col:
            a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        for j in range(col, n + 1):
            a[col][j] /= div
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            if factor == 0:
                continue
            for j in range(col, n + 1):
                a[row][j] -= factor * a[col][j]
    return [a[i][n] for i in range(n)]

def solve_affine(source_vertices, target_vertices):
    normal = [[0.0 for _ in range(4)] for _ in range(4)]
    rhs = [[0.0 for _ in range(3)] for _ in range(4)]
    for src, dst in zip(source_vertices, target_vertices):
        row = (src[0], src[1], src[2], 1.0)
        for i in range(4):
            for j in range(4):
                normal[i][j] += row[i] * row[j]
            for axis in range(3):
                rhs[i][axis] += row[i] * dst[axis]
    solved = []
    for axis in range(3):
        params = solve4(normal, [rhs[i][axis] for i in range(4)])
        if params is None:
            return None
        solved.append(params)
    return {'matrix': [[solved[0][0], solved[0][1], solved[0][2]], [solved[1][0], solved[1][1], solved[1][2]], [solved[2][0], solved[2][1], solved[2][2]]], 'position': (solved[0][3], solved[1][3], solved[2][3])}

def norm(v):
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])

def matrix_to_euler_xyz(r):
    value = max(-1.0, min(1.0, -r[2][0]))
    ry = math.asin(value)
    cy = math.cos(ry)
    if abs(cy) > 0.000001:
        rx = math.atan2(r[2][1], r[2][2])
        rz = math.atan2(r[1][0], r[0][0])
    else:
        rx = 0.0
        rz = math.atan2(-r[0][1], r[1][1])
    return (rx, ry, rz)

def affine_to_transform(affine):
    m = affine['matrix']
    columns = [(m[0][0], m[1][0], m[2][0]), (m[0][1], m[1][1], m[2][1]), (m[0][2], m[1][2], m[2][2])]
    scale = tuple(norm(col) for col in columns)
    if any(value <= 0.0000001 for value in scale):
        return None
    r = [[columns[0][0] / scale[0], columns[1][0] / scale[1], columns[2][0] / scale[2]], [columns[0][1] / scale[0], columns[1][1] / scale[1], columns[2][1] / scale[2]], [columns[0][2] / scale[0], columns[1][2] / scale[1], columns[2][2] / scale[2]]]
    return {'position': affine['position'], 'rotation': matrix_to_euler_xyz(r), 'scale': scale}

def max_transform_error(source_vertices, target_vertices, transform):
    max_error = 0.0
    for src, dst in zip(source_vertices, target_vertices):
        p = apply_transform(src, transform)
        error = math.sqrt((p[0] - dst[0]) ** 2 + (p[1] - dst[1]) ** 2 + (p[2] - dst[2]) ** 2)
        if error > max_error:
            max_error = error
    return max_error

def infer_proxy_transform(obj, obj_vertices):
    vertices = proxy_vertices_from_obj(obj)
    if len(vertices) != len(obj_vertices):
        return None
    affine = solve_affine(vertices, obj_vertices)
    if affine is None:
        return None
    transform = affine_to_transform(affine)
    if transform is None:
        return None
    mn, mx = bounds(obj_vertices)
    diag = math.sqrt((mx[0] - mn[0]) ** 2 + (mx[1] - mn[1]) ** 2 + (mx[2] - mn[2]) ** 2)
    allowed = max(0.025, diag * 0.0015)
    if max_transform_error(vertices, obj_vertices, transform) > allowed:
        return None
    return transform

def manifest_indexes(manifest):
    objects = manifest.get('objects') or []
    by_rel = {}
    by_uuid = {}
    for obj in objects:
        rel = (obj.get('path') or '').replace('\\', '/')
        if rel:
            by_rel[rel] = obj
        for key in ('component_uuid_hex', 'entry_uuid_hex'):
            value = clean_hex(obj.get(key))
            if value:
                by_uuid.setdefault(value, obj)
    return by_rel, by_uuid

def find_clone_source(rest, rel_parent, by_rel, by_uuid):
    exact = (rel_parent / (rest + '.obj')).as_posix()
    if exact in by_rel:
        return by_rel[exact]
    match = UUID_RE.search(rest)
    if not match:
        return None
    key = clean_hex(match.group(1))
    return by_uuid.get(key)

def collect_clone_plans(folder, manifest):
    folder = Path(folder)
    root = folder / (manifest.get('object_root') or 'room_scene_objects')
    if not root.is_dir():
        return [], [], []
    objects = manifest.get('objects') or []
    manifest_paths = set((obj.get('path') or '').replace('\\', '/') for obj in objects if obj.get('path'))
    by_rel, by_uuid = manifest_indexes(manifest)
    plans = []
    changed = []
    unsupported = []
    for path in sorted(root.rglob('*.obj')):
        rel = path.relative_to(folder).as_posix()
        if rel in manifest_paths:
            continue
        match = CLONE_NAME_RE.match(path.name)
        if not match:
            continue
        clone_id = match.group(1).lower()
        rest = match.group(2)
        source = find_clone_source(rest, path.parent.relative_to(folder), by_rel, by_uuid)
        if source is None:
            unsupported.append(f'CLONE Quelle fehlt: {rel}')
            continue
        if not (source.get('entry_type') == 'ROOMCTRL' or source.get('mode') == 'room_control'):
            unsupported.append(f'CLONE nur für ROOMCTRL: {rel}')
            continue
        source_actor_uuid = clean_hex(source.get('component_uuid_hex'))
        if not source_actor_uuid:
            unsupported.append(f'CLONE ohne Source-Actor: {rel}')
            continue
        try:
            vertices, faces = parse_obj(path)
            transform = infer_proxy_transform(source, vertices)
        except PakError as e:
            unsupported.append(str(e))
            continue
        if transform is None:
            unsupported.append(f'CLONE Transform nicht erkannt: {rel}')
            continue
        plans.append({'clone_id': clone_id, 'path': rel, 'source_obj': source, 'source_actor_uuid': source_actor_uuid, 'transform': transform})
        changed.append(f'{rel} (Clone)')
    return plans, changed, unsupported

def collect_bundle(by_uuid, actor_uuid):
    seen = set()
    ordered = []
    stack = [actor_uuid]
    while stack:
        current = clean_hex(stack.pop(0))
        if current in seen:
            continue
        component = by_uuid.get(current)
        if component is None:
            continue
        seen.add(current)
        ordered.append(current)
        actor_refs = component.get('actor_refs')
        if not actor_refs:
            continue
        for ref in actor_refs.get('refs') or []:
            ref_uuid = clean_hex(ref.get('uuid_hex'))
            if ref_uuid and ref_uuid not in seen:
                stack.append(ref_uuid)
        if len(ordered) > 256:
            raise PakError('Clone-Bundle ist unerwartet groß')
    return ordered

def clone_uuid_map(component_uuids):
    return {item: uuid.uuid4().bytes.hex() for item in component_uuids}

def clone_component_block(asset, component, uuid_map, transform):
    block = bytearray(asset[component['off']:component['end']])
    for old_uuid, new_uuid in uuid_map.items():
        block = bytearray(bytes(block).replace(bytes.fromhex(old_uuid), bytes.fromhex(new_uuid)))
    if transform is not None and component.get('actor_refs') and component['actor_refs'].get('transform'):
        if len(block) < 37:
            raise PakError(f'Clone-Transform kann nicht geschrieben werden: {component.get("name") or component["uuid_hex"]}')
        flag = block[-37]
        block[-37:] = bytes([flag]) + struct.pack('>9f', *(transform['position'] + transform['rotation'] + transform['scale']))
    return bytes(block)

def locate_layer_srip(asset, info, layer_index):
    layer = None
    for item in info['layers']:
        if item['index'] == layer_index:
            layer = item
            break
    if layer is None:
        raise PakError('Clone-Layer wurde nicht gefunden')
    p = layer['off'] + 32
    end = layer['off'] + layer['size']
    while p + 24 <= end:
        tag = asset[p:p+4]
        size = be64(asset, p + 4) if p + 12 <= end else 0
        if tag == b'RFRM' and p + 32 <= end:
            child_end = p + 32 + size
            if child_end <= end and asset[p+20:p+24] == b'SRIP':
                return {'layer_off': layer['off'], 'srip_off': p, 'insert_off': child_end}
            if child_end > p and child_end <= end:
                p = child_end
                continue
        if tag in (b'LHED', b'XXXX'):
            chunk_end = p + 24 + size
            if chunk_end > p and chunk_end <= end:
                p = chunk_end
                continue
        p += 1
    raise PakError(f'SRIP für Clone-Layer fehlt: {layer.get("name") or layer_index}')

def insert_clone_blocks(asset_bytes, info, blocks_by_layer):
    asset = bytearray(asset_bytes)
    inserts = []
    for layer_index, blocks in blocks_by_layer.items():
        if not blocks:
            continue
        loc = locate_layer_srip(asset, info, layer_index)
        inserts.append({'insert_off': loc['insert_off'], 'layer_off': loc['layer_off'], 'srip_off': loc['srip_off'], 'payload': b''.join(blocks)})
    for item in sorted(inserts, key=lambda value: value['insert_off'], reverse=True):
        payload = item['payload']
        if not payload:
            continue
        insert_off = item['insert_off']
        asset[insert_off:insert_off] = payload
        delta = len(payload)
        w64(asset, item['srip_off'] + 4, be64(asset, item['srip_off'] + 4) + delta)
        w64(asset, item['layer_off'] + 4, be64(asset, item['layer_off'] + 4) + delta)
        w64(asset, 4, be64(asset, 4) + delta)
    return bytes(asset)

def apply_room_clones(parsed, folder, manifest, room_asset):
    plans, changed, unsupported = collect_clone_plans(folder, manifest)
    if not plans:
        return None, 0, [], unsupported
    asset = bytes(room_asset)
    info = parse_room_asset(asset)
    by_uuid = {item['uuid_hex']: item for item in info['components']}
    groups = defaultdict(list)
    for plan in plans:
        groups[plan['clone_id']].append(plan)
    blocks_by_layer = defaultdict(list)
    clone_count = 0
    for clone_id, group_plans in groups.items():
        source_uuids = []
        source_transforms = {}
        for plan in group_plans:
            actor_uuid = clean_hex(plan['source_actor_uuid'])
            if actor_uuid not in by_uuid:
                unsupported.append(f'CLONE Source-Actor fehlt in ROOM: {plan["path"]}')
                continue
            source_uuids.append(actor_uuid)
            source_transforms[actor_uuid] = plan['transform']
        bundle = []
        for actor_uuid in source_uuids:
            for component_uuid in collect_bundle(by_uuid, actor_uuid):
                if component_uuid not in bundle:
                    bundle.append(component_uuid)
        if not bundle:
            continue
        uuid_map = clone_uuid_map(bundle)
        for component_uuid in bundle:
            component = by_uuid[component_uuid]
            transform = source_transforms.get(component_uuid)
            block = clone_component_block(asset, component, uuid_map, transform)
            blocks_by_layer[component['layer_index']].append(block)
        clone_count += len(source_uuids)
    if not blocks_by_layer:
        return None, 0, changed, unsupported
    cloned = insert_clone_blocks(asset, info, blocks_by_layer)
    parsed_again = parse_room_asset(cloned)
    if len(parsed_again['components']) <= len(info['components']):
        raise PakError('ROOM-Clone hat keine neuen Komponenten erzeugt')
    return cloned, clone_count, changed, unsupported

def next_clone_id(root):
    used = set()
    for path in Path(root).rglob('clone*.obj'):
        match = CLONE_NAME_RE.match(path.name)
        if match:
            try:
                used.add(int(match.group(1)[5:]))
            except Exception:
                pass
    number = 1
    while number in used:
        number += 1
    return f'clone{number:04d}'

def dist(a, b):
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)

def related_sources(source, objects):
    out = [source]
    name = (source.get('component_name') or '').lower()
    layer = source.get('layer_name')
    pos = obj_transform(source)['position']
    if 'barrel' in name or 'throwableobject' in name:
        for obj in objects:
            if obj is source:
                continue
            if not (obj.get('entry_type') == 'ROOMCTRL' or obj.get('mode') == 'room_control'):
                continue
            if obj.get('layer_name') != layer:
                continue
            obj_name = (obj.get('component_name') or '').lower()
            if 'rambi charge vulnerable' not in obj_name:
                continue
            if dist(pos, obj_transform(obj)['position']) <= 8.0:
                out.append(obj)
    return out

def create_room_clone_files(folder, source_obj_path):
    folder = Path(folder)
    source_obj_path = Path(source_obj_path)
    manifest_path = folder / 'room_scene_repack_manifest.json'
    if not manifest_path.is_file():
        raise PakError('room_scene_repack_manifest.json fehlt')
    import json
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    root = folder / (manifest.get('object_root') or 'room_scene_objects')
    if not root.is_dir():
        raise PakError('room_scene_objects fehlt')
    try:
        rel = source_obj_path.relative_to(folder).as_posix()
    except Exception:
        raise PakError('Quelle muss im ROOM-Paket-Ordner liegen')
    by_rel, by_uuid = manifest_indexes(manifest)
    source = by_rel.get(rel)
    if source is None:
        raise PakError('Quelle ist kein Original-ROOMCTRL-Objekt aus dem Manifest')
    if not (source.get('entry_type') == 'ROOMCTRL' or source.get('mode') == 'room_control'):
        raise PakError('Clone-Erstellung geht aktuell nur für ROOMCTRL-Objekte')
    clone_id = next_clone_id(root)
    objects = manifest.get('objects') or []
    sources = related_sources(source, objects)
    written = []
    for item in sources:
        item_rel = (item.get('path') or '').replace('\\', '/')
        src = folder / item_rel
        if not src.is_file():
            continue
        dst = src.with_name(f'{clone_id}.{src.name}')
        if dst.exists():
            raise PakError(f'Clone-Datei existiert bereits: {dst.name}')
        dst.write_bytes(src.read_bytes())
        written.append(str(dst.relative_to(folder)))
    if not written:
        raise PakError('Keine Clone-Dateien erstellt')
    return {'clone_id': clone_id, 'files': written, 'count': len(written)}
