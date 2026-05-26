from pathlib import Path
import json
import math
import struct
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes, kind_to_ext

ZERO_UUID = '00000000000000000000000000000000'
SKELETAL_REF_TYPES = {'SKEL', 'ANIM'}

def be16(data, off):
    return int.from_bytes(data[off:off+2], 'big')

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def le32(data, off):
    return int.from_bytes(data[off:off+4], 'little')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def is_rfrm_type(asset, typ):
    return len(asset) >= 32 and asset[:4] == b'RFRM' and tag4(asset, 20) == typ

def format_uuid(hex_str):
    if not hex_str or len(hex_str) != 32:
        return hex_str
    return f'{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}'

def read_name(asset, p):
    if p + 4 > len(asset):
        raise PakError('Name ist abgeschnitten')
    size = be32(asset, p)
    p += 4
    if size <= 0 or size > 4096 or p + size > len(asset):
        raise PakError('Name hat ungültige Länge')
    name = asset[p:p+size].split(b'\x00', 1)[0].decode('utf-8', 'replace')
    return name, size, p + size

def _safe_float(value):
    value = float(value)
    if not math.isfinite(value) or abs(value) < 0.00000001:
        return 0.0
    return value

def _mat_identity():
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]

def _mat_mul(a, b):
    out = [0.0] * 16
    for r in range(4):
        for c in range(4):
            out[r * 4 + c] = sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
    return out

def _mat3_inv(m):
    a, b, c, d, e, f, g, h, i = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) <= 0.00000001:
        return [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
    inv_det = 1.0 / det
    return [(e * i - f * h) * inv_det, (c * h - b * i) * inv_det, (b * f - c * e) * inv_det, (f * g - d * i) * inv_det, (a * i - c * g) * inv_det, (c * d - a * f) * inv_det, (d * h - e * g) * inv_det, (b * g - a * h) * inv_det, (a * e - b * d) * inv_det]

def _mat_inverse_affine(m):
    r = [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]]
    inv = _mat3_inv(r)
    t = [m[3], m[7], m[11]]
    it = [-(inv[0] * t[0] + inv[1] * t[1] + inv[2] * t[2]), -(inv[3] * t[0] + inv[4] * t[1] + inv[5] * t[2]), -(inv[6] * t[0] + inv[7] * t[1] + inv[8] * t[2])]
    return [inv[0], inv[1], inv[2], it[0], inv[3], inv[4], inv[5], it[1], inv[6], inv[7], inv[8], it[2], 0.0, 0.0, 0.0, 1.0]

def _quat_to_mat4(translation, rotation, scale):
    w, x, y, z = [float(v) for v in rotation]
    qlen = math.sqrt(w * w + x * x + y * y + z * z)
    if qlen > 0.00000001:
        w, x, y, z = w / qlen, x / qlen, y / qlen, z / qlen
    sx, sy, sz = [float(v) for v in scale]
    tx, ty, tz = [float(v) for v in translation]
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    r00 = 1.0 - 2.0 * (yy + zz)
    r01 = 2.0 * (xy - wz)
    r02 = 2.0 * (xz + wy)
    r10 = 2.0 * (xy + wz)
    r11 = 1.0 - 2.0 * (xx + zz)
    r12 = 2.0 * (yz - wx)
    r20 = 2.0 * (xz - wy)
    r21 = 2.0 * (yz + wx)
    r22 = 1.0 - 2.0 * (xx + yy)
    return [r00 * sx, r01 * sy, r02 * sz, tx, r10 * sx, r11 * sy, r12 * sz, ty, r20 * sx, r21 * sy, r22 * sz, tz, 0.0, 0.0, 0.0, 1.0]

def _mat_translation(m):
    return [_safe_float(m[3]), _safe_float(m[7]), _safe_float(m[11])]

def _read_node_name_indices(asset, data_start, node_count, name_count):
    if node_count <= 0 or data_start + 4 + node_count > len(asset):
        return []
    if le32(asset, data_start) != node_count:
        return []
    values = list(asset[data_start + 4:data_start + 4 + node_count])
    if all(v == 255 or v < name_count for v in values):
        return values
    return []

def _find_parent_table(asset, start, stop, node_count):
    best = {'score': -1, 'offset': 0, 'values': []}
    if node_count <= 0:
        return best
    for off in range(start, max(start, stop - node_count + 1)):
        values = list(asset[off:off + node_count])
        if len(values) != node_count:
            continue
        valid = sum(1 for v in values if v == 255 or v < node_count)
        roots = sum(1 for v in values if v == 255)
        backward = sum(1 for i, v in enumerate(values) if v == 255 or v < i)
        noself = sum(1 for i, v in enumerate(values) if v == 255 or v != i)
        if valid < node_count:
            continue
        score = backward * 4 + noself + roots * 8
        if 1 <= roots <= max(6, node_count // 8):
            score += 60
        if values[:3] == [255, 255, 255]:
            score += 50
        if score > best['score']:
            best = {'score': score, 'offset': off, 'values': values}
    return best

def _find_skin_table(asset, start, stop, name_count, skin_bone_count):
    best = {'score': -1, 'offset': 0, 'values': []}
    if skin_bone_count <= 0:
        return best
    for off in range(start, max(start, stop - skin_bone_count + 1)):
        values = list(asset[off:off + skin_bone_count])
        if len(values) != skin_bone_count:
            continue
        if not all(0 <= v < name_count for v in values):
            continue
        unique = len(set(values))
        ascending = sum(1 for a, b in zip(values, values[1:]) if b > a)
        score = unique * 5 + ascending
        if unique == skin_bone_count:
            score += 100
        if values and values[0] > 0:
            score += 10
        if score > best['score']:
            best = {'score': score, 'offset': off, 'values': values}
    return best

def _score_trs_block(asset, offset, count, endian):
    if count <= 0 or offset + count * 40 > len(asset):
        return None
    fmt = ('>' if endian == 'be' else '<') + 'f' * 10
    score = 0
    translations = []
    rotations = []
    scales = []
    for i in range(count):
        try:
            values = list(struct.unpack_from(fmt, asset, offset + i * 40))
        except Exception:
            return None
        if not all(math.isfinite(v) and abs(v) < 1000000.0 for v in values):
            return None
        t = values[:3]
        q = values[3:7]
        s = values[7:10]
        qlen = math.sqrt(sum(v * v for v in q))
        if 0.98 <= qlen <= 1.02:
            score += 8
        elif 0.75 <= qlen <= 1.25:
            score += 3
        else:
            score -= 10
        if all(abs(abs(v) - 1.0) <= 0.02 for v in s):
            score += 8
        elif all(0.001 <= abs(v) <= 100.0 for v in s):
            score += 2
        else:
            score -= 10
        if sum(abs(v) for v in t) < 100.0:
            score += 4
        translations.append(t)
        rotations.append(q)
        scales.append(s)
    spread = max((sum(abs(x) for x in t) for t in translations), default=0.0)
    if spread < 100.0:
        score += 40
    return {'offset': offset, 'endian': endian, 'score': score, 'translations': translations, 'rotations': rotations, 'scales': scales, 'spread': spread}

def _find_trs_table(asset, start, stop, count):
    best = None
    for off in range(start, max(start, stop - count * 40 + 1)):
        for endian in ('be', 'le'):
            candidate = _score_trs_block(asset, off, count, endian)
            if candidate is not None and (best is None or candidate['score'] > best['score']):
                best = candidate
    return best or {'offset': 0, 'endian': 'be', 'score': 0, 'translations': [], 'rotations': [], 'scales': [], 'spread': 0.0}

def _nearest_skin_parent(node_index, parent_values, skin_node_lookup):
    parent = parent_values[node_index] if 0 <= node_index < len(parent_values) else 255
    seen = {node_index}
    while parent != 255 and parent not in seen:
        if parent in skin_node_lookup:
            return skin_node_lookup[parent]
        seen.add(parent)
        parent = parent_values[parent] if 0 <= parent < len(parent_values) else 255
    return -1

def _make_tail(index, matrix, children, node_global_matrices):
    current = _mat_translation(matrix)
    for child in children.get(index, []):
        if 0 <= child < len(node_global_matrices):
            child_pos = _mat_translation(node_global_matrices[child])
            if sum(abs(child_pos[i] - current[i]) for i in range(3)) > 0.000001:
                return child_pos
    return [current[0], current[1] + 0.035, current[2]]

def parse_skel_asset(asset):
    if not is_rfrm_type(asset, 'SKEL'):
        raise PakError('Keine SKEL-Ressource')
    if len(asset) < 44:
        raise PakError('SKEL ist zu klein')
    p = 32
    marker = be32(asset, p)
    version_a = be32(asset, 24)
    version_b = be32(asset, 28)
    unknown_a = be32(asset, p + 4)
    name_count = be32(asset, p + 8)
    if name_count <= 0 or name_count > 4096:
        raise PakError(f'SKEL-Namenszähler wirkt ungültig ({name_count})')
    p += 12
    names = []
    for index in range(name_count):
        name, size, p = read_name(asset, p)
        names.append({'index': index, 'name': name, 'size': size})
    fields_offset = p
    fields = {}
    if p + 16 <= len(asset):
        fields = {'zero_or_flags': be32(asset, p), 'name_count_repeat': be16(asset, p + 4), 'node_count': be16(asset, p + 6), 'skin_bone_count': be16(asset, p + 8), 'group_count_a': be16(asset, p + 10), 'group_count_b': be16(asset, p + 12), 'flags': be16(asset, p + 14)}
    node_count = int(fields.get('node_count') or 0)
    skin_bone_count = int(fields.get('skin_bone_count') or 0)
    data_start = p + 16
    node_name_indices = _read_node_name_indices(asset, data_start, node_count, name_count)
    if not node_name_indices:
        node_name_indices = list(range(min(node_count, name_count)))
    search_start = data_start + 4 + len(node_name_indices)
    search_stop = min(len(asset), data_start + 4096)
    parent_info = _find_parent_table(asset, search_start, search_stop, node_count)
    parent_values = parent_info.get('values') or [255] * node_count
    skin_info = _find_skin_table(asset, parent_info.get('offset', search_start) + node_count, search_stop, name_count, skin_bone_count)
    skin_name_indices = skin_info.get('values') or [v for v in node_name_indices if 0 <= v < name_count][:skin_bone_count]
    transform_info = _find_trs_table(asset, data_start, len(asset), node_count)
    translations = transform_info.get('translations') or [[0.0, 0.0, 0.0] for _ in range(node_count)]
    rotations = transform_info.get('rotations') or [[1.0, 0.0, 0.0, 0.0] for _ in range(node_count)]
    scales = transform_info.get('scales') or [[1.0, 1.0, 1.0] for _ in range(node_count)]
    node_local_matrices = []
    for i in range(node_count):
        t = translations[i] if i < len(translations) else [0.0, 0.0, 0.0]
        q = rotations[i] if i < len(rotations) else [1.0, 0.0, 0.0, 0.0]
        s = scales[i] if i < len(scales) else [1.0, 1.0, 1.0]
        node_local_matrices.append(_quat_to_mat4(t, q, s))
    node_global_matrices = []
    for i, local in enumerate(node_local_matrices):
        parent = parent_values[i] if i < len(parent_values) else 255
        if parent != 255 and 0 <= parent < i and parent < len(node_global_matrices):
            node_global_matrices.append(_mat_mul(node_global_matrices[parent], local))
        else:
            node_global_matrices.append(local)
    name_to_node = {}
    for node_index, name_index in enumerate(node_name_indices):
        if 0 <= name_index < name_count and name_index not in name_to_node:
            name_to_node[name_index] = node_index
    skin_node_indices = [name_to_node[name_index] for name_index in skin_name_indices if name_index in name_to_node]
    skin_node_lookup = {node_index: i for i, node_index in enumerate(skin_node_indices)}
    children = {i: [] for i in range(node_count)}
    for i, parent in enumerate(parent_values):
        if parent != 255 and 0 <= parent < node_count and parent != i:
            children.setdefault(parent, []).append(i)
    bones = []
    for bone_index, node_index in enumerate(skin_node_indices):
        name_index = node_name_indices[node_index] if node_index < len(node_name_indices) else node_index
        parent_index = _nearest_skin_parent(node_index, parent_values, skin_node_lookup)
        global_matrix = node_global_matrices[node_index]
        if parent_index >= 0:
            parent_global = node_global_matrices[skin_node_indices[parent_index]]
            local_matrix = _mat_mul(_mat_inverse_affine(parent_global), global_matrix)
        else:
            local_matrix = global_matrix
        head = _mat_translation(global_matrix)
        tail = _make_tail(node_index, global_matrix, children, node_global_matrices)
        bones.append({'index': bone_index, 'node_index': node_index, 'name_index': name_index, 'name': names[name_index]['name'] if 0 <= name_index < len(names) else f'bone_{bone_index:03d}', 'parent_index': parent_index, 'parent_node_index': parent_values[node_index] if node_index < len(parent_values) else 255, 'matrix': local_matrix, 'global_matrix': global_matrix, 'inverse_bind_matrix': _mat_inverse_affine(global_matrix), 'translation': translations[node_index] if node_index < len(translations) else [0.0, 0.0, 0.0], 'rotation': rotations[node_index] if node_index < len(rotations) else [1.0, 0.0, 0.0, 0.0], 'scale': scales[node_index] if node_index < len(scales) else [1.0, 1.0, 1.0], 'head': head, 'tail': tail})
    nodes = []
    for node_index, name_index in enumerate(node_name_indices):
        name = names[name_index]['name'] if 0 <= name_index < len(names) else f'node_{node_index:03d}'
        nodes.append({'index': node_index, 'name_index': name_index, 'name': name, 'parent_index': parent_values[node_index] if node_index < len(parent_values) else 255, 'matrix': node_local_matrices[node_index] if node_index < len(node_local_matrices) else _mat_identity(), 'global_matrix': node_global_matrices[node_index] if node_index < len(node_global_matrices) else _mat_identity(), 'translation': translations[node_index] if node_index < len(translations) else [0.0, 0.0, 0.0], 'rotation': rotations[node_index] if node_index < len(rotations) else [1.0, 0.0, 0.0, 0.0], 'scale': scales[node_index] if node_index < len(scales) else [1.0, 1.0, 1.0]})
    tail = asset[fields_offset:]
    return {'type': 'SKEL', 'version_a': version_a, 'version_b': version_b, 'marker': f'0x{marker:08X}', 'unknown_a': unknown_a, 'size': len(asset), 'sha1': sha1_bytes(asset), 'name_count': name_count, 'names': names, 'fields': fields, 'fields_offset': fields_offset, 'data_start': data_start, 'node_name_indices': node_name_indices, 'parent_table_offset': parent_info.get('offset', 0), 'parent_table': parent_values, 'skin_table_offset': skin_info.get('offset', 0), 'skin_name_indices': skin_name_indices, 'skin_node_indices': skin_node_indices, 'transform_offset': transform_info.get('offset', 0), 'transform_endian': transform_info.get('endian', ''), 'transform_format': 'f32_trs_quat_scale', 'transform_stride': 40, 'transform_count': node_count, 'transform_score': transform_info.get('score', 0), 'tail_size': len(tail), 'tail_sha1': sha1_bytes(tail), 'node_count': node_count, 'skin_bone_count': skin_bone_count, 'nodes': nodes, 'bones': bones, 'status': 'SKEL-Node-Tabelle, Parent-Tabelle, Skin-Bone-Liste und 40-Byte-TRS-Bind-Pose werden gelesen.'}

def parse_rfrm_chunks(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM':
        return []
    out = []
    p = 32
    while p < len(asset):
        if p + 24 > len(asset):
            out.append({'tag': 'TRUNCATED', 'off': p, 'size': len(asset) - p, 'version': 0, 'payload_off': p, 'payload_end': len(asset), 'sha1': sha1_bytes(asset[p:])})
            break
        tag = tag4(asset, p)
        size = be64(asset, p + 4)
        version = be32(asset, p + 12)
        payload_off = p + 24
        payload_end = payload_off + size
        if payload_end > len(asset):
            out.append({'tag': tag, 'off': p, 'size': size, 'version': version, 'payload_off': payload_off, 'payload_end': len(asset), 'sha1': sha1_bytes(asset[payload_off:])})
            break
        out.append({'tag': tag, 'off': p, 'size': size, 'version': version, 'payload_off': payload_off, 'payload_end': payload_end, 'sha1': sha1_bytes(asset[payload_off:payload_end])})
        p = payload_end
    return out

def parse_skeletal_asset_summary(asset, fallback_type=''):
    typ = tag4(asset, 20) if len(asset) >= 24 and asset[:4] == b'RFRM' else fallback_type
    if typ == 'SKEL':
        return parse_skel_asset(asset)
    return {'type': typ, 'size': len(asset), 'sha1': sha1_bytes(asset), 'chunks': parse_rfrm_chunks(asset)}

def resolve_ref(parsed, uuid_hex, require_store=None):
    if not uuid_hex or uuid_hex == ZERO_UUID:
        return None, None, '', ''
    entry = parsed.get('uuid_to_entry', {}).get(uuid_hex)
    if entry is not None:
        return get_entry_asset(parsed, entry), entry, 'pak', parsed.get('path', '')
    if require_store is not None:
        asset, entry, source = require_store.resolve_asset(parsed, uuid_hex)
        if entry is not None and asset is not None:
            source_path = require_store.get_required_source(uuid_hex) if source == 'require' else parsed.get('path', '')
            return asset, entry, source, source_path
    return None, None, '', ''

def known_entries_by_uuid(parsed, require_store=None):
    out = {}
    for entry in parsed.get('entries', []):
        out[entry['uuid_hex']] = (entry, 'pak', parsed.get('path', ''))
    if require_store is not None:
        for uuid_hex, item in getattr(require_store, 'required_entries_by_uuid', {}).items():
            out[uuid_hex] = (item['entry'], 'require', item.get('parsed_path', ''))
    return out

def find_known_uuid_refs(asset, parsed, require_store=None, wanted_types=None):
    wanted_types = set(wanted_types or [])
    refs = []
    for uuid_hex, item in known_entries_by_uuid(parsed, require_store).items():
        entry, source, source_path = item
        if uuid_hex == ZERO_UUID:
            continue
        if wanted_types and entry.get('type') not in wanted_types:
            continue
        try:
            needle = bytes.fromhex(uuid_hex)
        except Exception:
            continue
        start = 0
        while True:
            pos = asset.find(needle, start)
            if pos == -1:
                break
            refs.append({'uuid_hex': uuid_hex, 'offset': pos, 'entry_type': entry.get('type', ''), 'entry_name': entry.get('display_name') or entry.get('name') or '', 'source_kind': source, 'source_path': source_path})
            start = pos + 1
    refs.sort(key=lambda item: (item['offset'], item['entry_type'], item['uuid_hex']))
    return refs

def unique_path(path):
    path = Path(path)
    if not path.exists():
        return path
    suffix = ''.join(path.suffixes)
    stem = path.name[:-len(suffix)] if suffix else path.name
    n = 2
    while True:
        candidate = path.with_name(f'{stem}_{n}{suffix}')
        if not candidate.exists():
            return candidate
        n += 1

def rel(root, path):
    return str(Path(path).relative_to(root)).replace('\\', '/')

def asset_file_name(prefix, entry, uuid_hex, fallback_type):
    typ = entry.get('type') if entry is not None else fallback_type
    name = entry.get('display_name') or entry.get('name') or '' if entry is not None else ''
    base = safe_name('__'.join(part for part in (prefix, typ, name, uuid_hex) if part))
    return base + kind_to_ext(typ)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    return path

def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path

def export_skeletal_asset(folder, parsed, ref, require_store=None, prefix=''):
    uuid_hex = ref.get('uuid_hex', '')
    asset, entry, source, source_path = resolve_ref(parsed, uuid_hex, require_store)
    rec = dict(ref)
    rec.update({'resolved': entry is not None and asset is not None, 'entry_type': entry.get('type') if entry else '', 'entry_name': entry.get('display_name') or entry.get('name') or '' if entry else '', 'source_kind': source, 'source_path': source_path, 'raw_file': '', 'summary_file': '', 'summary': {}})
    if entry is None or asset is None:
        return rec
    typ = entry.get('type') or ref.get('type') or 'UNKNOWN'
    raw_name = asset_file_name(prefix or ref.get('name') or typ, entry, uuid_hex, typ)
    raw_path = unique_path(Path(folder) / typ / raw_name)
    write_bytes(raw_path, asset)
    summary_path = raw_path.with_suffix(raw_path.suffix + '.json')
    summary = parse_skeletal_asset_summary(asset, typ)
    summary.update({'uuid_hex': uuid_hex, 'entry_name': rec['entry_name'], 'source_kind': source, 'source_path': source_path})
    write_json(summary_path, summary)
    rec['raw_file'] = str(raw_path)
    rec['summary_file'] = str(summary_path)
    rec['summary'] = summary
    return rec
