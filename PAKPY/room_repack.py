from pathlib import Path
import json
import math
import struct
from pak_core import PakError, get_entry_asset, rebuild_pak, sha1_bytes
from room_scene_codec import parse_room_asset
from clsn_codec import parse_clsn_asset
from dcln_codec import parse_dcln_asset


def clean_hex(text):
    return ''.join(ch for ch in (text or '').lower() if ch in '0123456789abcdef')


def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')


def w64(buf, off, value):
    buf[off:off+8] = int(value).to_bytes(8, 'big')


def read_manifest(folder):
    folder = Path(folder)
    path = folder / 'room_scene_repack_manifest.json'
    if not path.is_file():
        raise PakError('room_scene_repack_manifest.json fehlt')
    return json.loads(path.read_text(encoding='utf-8'))


def validate_room_manifest(parsed, manifest):
    room_index = manifest.get('room_entry_index')
    room_uuid = clean_hex(manifest.get('room_entry_uuid_hex'))
    if room_index is None or room_index < 0 or room_index >= len(parsed['entries']):
        raise PakError('ROOM-Manifest verweist auf einen ungültigen ROOM-Eintrag')
    room_entry = parsed['entries'][room_index]
    if room_entry.get('type') != 'ROOM' or room_entry.get('uuid_hex') != room_uuid:
        raise PakError('ROOM-Manifest passt nicht zum aktuell geladenen PAK')
    return room_entry


def transform_list(value, fallback):
    if value is None:
        return tuple(fallback)
    if len(value) != 3:
        raise PakError('Transform-Wert muss 3 Zahlen haben')
    out = []
    for item in value:
        number = float(item)
        if not math.isfinite(number):
            raise PakError('Transform enthält keine gültige Zahl')
        out.append(number)
    return tuple(out)


def object_transform(item):
    transform = item.get('transform') or {}
    return {'position': transform_list(transform.get('position'), (0.0, 0.0, 0.0)), 'rotation': transform_list(transform.get('rotation'), (0.0, 0.0, 0.0)), 'scale': transform_list(transform.get('scale'), (1.0, 1.0, 1.0))}


def nearly_same_transform(a, b):
    for key in ('position', 'rotation', 'scale'):
        av = a.get(key) or ()
        bv = b.get(key) or ()
        if len(av) != 3 or len(bv) != 3:
            return False
        for x, y in zip(av, bv):
            if abs(float(x) - float(y)) > 0.00001:
                return False
    return True


def patch_room_transform(parsed, room_entry, objects):
    asset = bytearray(get_entry_asset(parsed, room_entry))
    info = parse_room_asset(bytes(asset))
    by_uuid = {item['uuid_hex']: item for item in info['components']}
    patches = 0
    patched_parent_uuids = set()
    for obj in objects:
        transform = object_transform(obj)
        component_uuid = clean_hex(obj.get('component_uuid_hex'))
        component = by_uuid.get(component_uuid)
        if component is None:
            continue
        parents = component.get('parents') or []
        if not parents:
            continue
        parent_uuid = clean_hex(obj.get('parent_component_uuid_hex')) or parents[0]['uuid_hex']
        if parent_uuid in patched_parent_uuids:
            continue
        parent = by_uuid.get(parent_uuid)
        if parent is None or not parent.get('actor_refs'):
            continue
        old_transform = parent['actor_refs'].get('transform')
        if old_transform and nearly_same_transform(old_transform, transform):
            continue
        tail_hex = parent['actor_refs'].get('tail_hex') or ''
        if len(tail_hex) != 74:
            raise PakError(f'Actor-Transform kann nicht gepatcht werden: {parent.get("name") or parent_uuid}')
        tail_off = parent['end'] - 37
        flag = asset[tail_off]
        asset[tail_off:tail_off+37] = bytes([flag]) + struct.pack('>9f', *(transform['position'] + transform['rotation'] + transform['scale']))
        patches += 1
        patched_parent_uuids.add(parent_uuid)
    if patches:
        parsed_again = parse_room_asset(bytes(asset))
        if len(parsed_again['components']) != len(info['components']):
            raise PakError('ROOM-Transform-Patch hat die Komponentenstruktur beschädigt')
        return bytes(asset), patches
    return None, 0


def parse_obj(path):
    vertices = []
    faces = []
    current_material = 0
    material_map = {}
    for raw_line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0] == 'v' and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == 'usemtl' and len(parts) >= 2:
            key = parts[1]
            if key not in material_map:
                material_map[key] = len(material_map)
            current_material = material_map[key]
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
                faces.append((indexes[0], indexes[i], indexes[i + 1], current_material))
    if not vertices or not faces:
        raise PakError(f'OBJ enthält keine nutzbare Geometrie: {path}')
    for face in faces:
        for index in face[:3]:
            if index < 0 or index >= len(vertices):
                raise PakError(f'OBJ-Face verweist auf ungültigen Vertex: {path}')
    return vertices, faces


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


def to_local(point, transform):
    position = transform['position']
    rotation = transform['rotation']
    scale = transform['scale']
    p = (point[0] - position[0], point[1] - position[1], point[2] - position[2])
    p = inverse_rotate_xyz(p, rotation)
    out = []
    for value, factor in zip(p, scale):
        if abs(factor) < 0.0000001:
            raise PakError('Scale darf beim OBJ-Rückbau nicht 0 sein')
        out.append(value / factor)
    return tuple(out)


def bounds(vertices):
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def chunk(tag, payload, version=0):
    head = bytearray(24)
    head[0:4] = tag.encode('ascii')
    head[4:12] = len(payload).to_bytes(8, 'big')
    head[12:16] = int(version).to_bytes(4, 'big')
    return bytes(head) + payload


def tree_payload(vertices, triangle_count):
    mn, mx = bounds(vertices)
    center = tuple((a + b) * 0.5 for a, b in zip(mn, mx))
    half = tuple(max((b - a) * 0.5, 0.0001) for a, b in zip(mn, mx))
    values = (1.0, 0.0, 0.0, center[0], 0.0, 1.0, 0.0, center[1], 0.0, 0.0, 1.0, center[2], half[0], half[1], half[2])
    return (1).to_bytes(4, 'big') + struct.pack('>15fIII', *(values + (0, triangle_count, 0x01000000)))


def build_clsn_from_obj(original_asset, obj_path, transform):
    vertices, faces = parse_obj(obj_path)
    local_vertices = [to_local(vertex, transform) for vertex in vertices]
    original = parse_clsn_asset(original_asset)
    vert_payload = len(local_vertices).to_bytes(4, 'big') + b''.join(struct.pack('>fff', *vertex) for vertex in local_vertices)
    tris = bytearray()
    tris += len(faces).to_bytes(4, 'big')
    old_triangles = original.get('triangles') or []
    for index, face in enumerate(faces):
        a, b, c, material_index = face
        flags = 0
        if index < len(old_triangles):
            material_index = old_triangles[index].get('material_index', material_index)
            flags = old_triangles[index].get('flags', 0)
        tris += int(a).to_bytes(4, 'big')
        tris += int(b).to_bytes(4, 'big')
        tris += int(c).to_bytes(4, 'big')
        tris += int(material_index).to_bytes(2, 'big')
        tris += int(flags).to_bytes(2, 'big')
    parts = []
    source = bytes(original_asset)
    for item in original['chunks']:
        tag = item['tag']
        version = item.get('version', 0)
        if tag == 'VERT':
            parts.append(chunk('VERT', vert_payload, version))
        elif tag == 'TRIS':
            parts.append(chunk('TRIS', bytes(tris), version))
        elif tag == 'TREE':
            parts.append(chunk('TREE', tree_payload(local_vertices, len(faces)), version))
        else:
            parts.append(source[item['off']:item['off'] + 24 + item['size']])
    body = b''.join(parts)
    root = bytearray(original_asset[:32])
    w64(root, 4, len(body))
    rebuilt = bytes(root) + body
    parse_clsn_asset(rebuilt)
    return rebuilt


def dcln_chunk_items(asset):
    out = []
    p = 32
    root_end = 32 + be64(asset, 4)
    while p < root_end:
        tag = asset[p:p+4].decode('ascii', 'replace')
        size = be64(asset, p + 4)
        version = int.from_bytes(asset[p+12:p+16], 'big')
        out.append({'tag': tag, 'off': p, 'size': size, 'version': version})
        p += 24 + size
    return out


def build_dcln_from_obj(original_asset, obj_path, transform):
    vertices, faces = parse_obj(obj_path)
    local_vertices = [to_local(vertex, transform) for vertex in vertices]
    original = parse_dcln_asset(original_asset)
    mn, mx = bounds(local_vertices)
    info_payload = struct.pack('>6f', *(mn + mx))
    vert_payload = len(local_vertices).to_bytes(4, 'big') + b''.join(struct.pack('>fff', *vertex) for vertex in local_vertices)
    old_triangles = original.get('triangles') or []
    tris = bytearray()
    tris += len(faces).to_bytes(4, 'big')
    for index, face in enumerate(faces):
        a, b, c, material_index = face
        flags = 0
        if index < len(old_triangles):
            material_index = old_triangles[index].get('material_index', material_index)
            flags = old_triangles[index].get('flags', 0)
        tris += int(a).to_bytes(4, 'big')
        tris += int(b).to_bytes(4, 'big')
        tris += int(c).to_bytes(4, 'big')
        tris += ((int(material_index) << 16) | int(flags)).to_bytes(4, 'big')
    parts = []
    source = bytes(original_asset)
    for item in dcln_chunk_items(source):
        tag = item['tag']
        version = item.get('version', 0)
        if tag == 'INFO':
            parts.append(chunk('INFO', info_payload, version))
        elif tag == 'VERT':
            parts.append(chunk('VERT', vert_payload, version))
        elif tag == 'TRIS':
            parts.append(chunk('TRIS', bytes(tris), version))
        elif tag == 'TREE':
            parts.append(chunk('TREE', tree_payload(local_vertices, len(faces)), version))
        else:
            parts.append(source[item['off']:item['off'] + 24 + item['size']])
    body = b''.join(parts)
    root = bytearray(original_asset[:32])
    w64(root, 4, len(body))
    rebuilt = bytes(root) + body
    parse_dcln_asset(rebuilt)
    return rebuilt


def detect_room_object_changes(parsed, folder, manifest):
    folder = Path(folder)
    replacements = {}
    changed_objects = []
    unsupported = []
    objects = manifest.get('objects') or []
    room_entry = validate_room_manifest(parsed, manifest)
    new_room_asset, room_transform_patches = patch_room_transform(parsed, room_entry, objects)
    if new_room_asset is not None:
        replacements[room_entry['index']] = {'asset_bytes': new_room_asset}
    for obj in objects:
        rel = obj.get('path') or ''
        if not rel:
            continue
        path = folder / rel
        if not path.is_file():
            continue
        old_sha1 = obj.get('obj_sha1') or ''
        new_sha1 = sha1_bytes(path.read_bytes())
        if old_sha1 and new_sha1 == old_sha1:
            continue
        entry_index = obj.get('entry_index')
        if entry_index is None or entry_index < 0 or entry_index >= len(parsed['entries']):
            raise PakError(f'Objekt verweist auf ungültigen Eintrag: {rel}')
        entry = parsed['entries'][entry_index]
        if entry['uuid_hex'] != clean_hex(obj.get('entry_uuid_hex')):
            raise PakError(f'Objekt passt nicht zum aktuellen PAK: {rel}')
        entry_type = entry.get('type')
        original_asset = get_entry_asset(parsed, entry)
        if entry_type == 'CLSN':
            replacements[entry_index] = {'asset_bytes': build_clsn_from_obj(original_asset, path, object_transform(obj))}
            changed_objects.append(rel)
        elif entry_type == 'DCLN':
            replacements[entry_index] = {'asset_bytes': build_dcln_from_obj(original_asset, path, object_transform(obj))}
            changed_objects.append(rel)
        else:
            unsupported.append(f'{entry_type}: {rel}')
    return replacements, changed_objects, unsupported, room_transform_patches


def rebuild_room_package_from_folder(parsed, folder, out_path):
    manifest = read_manifest(folder)
    replacements, changed_objects, unsupported, transform_patches = detect_room_object_changes(parsed, folder, manifest)
    if not replacements:
        raise PakError('Keine geänderten ROOM-Objekte oder Transform-Werte gefunden')
    if unsupported:
        raise PakError('Geänderte OBJs ohne Rückbaupfad: ' + '; '.join(unsupported[:20]))
    built = rebuild_pak(parsed, replacements, out_path)
    return {'out_path': built, 'changed_count': len(replacements), 'changed_objects': changed_objects, 'transform_patch_count': transform_patches, 'room_entry_index': manifest.get('room_entry_index')}
