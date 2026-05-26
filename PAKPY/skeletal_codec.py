from pathlib import Path
import json
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes, kind_to_ext

ZERO_UUID = '00000000000000000000000000000000'
SKELETAL_REF_TYPES = {'SKEL', 'ANIM'}

def be16(data, off):
    return int.from_bytes(data[off:off+2], 'big')

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

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

def _make_node_positions(parent_by_name_index, node_name_indices):
    children = {}
    for name_index in node_name_indices:
        parent_name_index = parent_by_name_index.get(name_index, -1)
        children.setdefault(parent_name_index, []).append(name_index)
    depth = {}
    order = {}
    def visit(name_index, level, slot):
        if name_index in depth:
            return
        depth[name_index] = level
        order[name_index] = slot
        for child_slot, child in enumerate(children.get(name_index, [])):
            visit(child, level + 1, child_slot)
    for root_slot, root in enumerate(children.get(-1, [])):
        visit(root, 0, root_slot)
    for name_index in node_name_indices:
        if name_index not in depth:
            visit(name_index, 0, len(order))
    out = {}
    for name_index in node_name_indices:
        level = depth.get(name_index, 0)
        slot = order.get(name_index, 0)
        x = (slot % 7 - 3) * 0.018
        y = (slot // 7) * 0.018
        z = level * 0.045
        out[name_index] = [round(x, 6), round(y, 6), round(z, 6)]
    return out

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
        fields = {
            'zero_or_flags': be32(asset, p),
            'name_count_repeat': be16(asset, p + 4),
            'node_count': be16(asset, p + 6),
            'skin_bone_count': be16(asset, p + 8),
            'group_count_a': be16(asset, p + 10),
            'group_count_b': be16(asset, p + 12),
            'flags_b': be16(asset, p + 14)
        }
    node_count = fields.get('node_count', 0)
    skin_bone_count = fields.get('skin_bone_count', 0)
    table_start = p + 16
    parent_start = table_start + 1 if node_count and table_start < len(asset) and asset[table_start] == node_count and node_count < name_count else table_start
    parent_raw = list(asset[parent_start:parent_start + node_count]) if node_count else []
    node_name_indices = list(range(name_count)) if node_count == name_count else list(range(1, min(name_count, node_count + 1)))
    parent_by_name_index = {}
    for node_pos, name_index in enumerate(node_name_indices):
        raw = parent_raw[node_pos] if node_pos < len(parent_raw) else 255
        if raw == 255 or raw == node_pos:
            parent_by_name_index[name_index] = -1
        elif node_count == name_count:
            parent_by_name_index[name_index] = raw if raw < name_count else -1
        else:
            parent_by_name_index[name_index] = raw + 1 if raw + 1 < name_count else -1
    bone_index_start = parent_start + len(parent_raw)
    skin_name_indices = []
    if skin_bone_count and bone_index_start + skin_bone_count <= len(asset):
        values = list(asset[bone_index_start:bone_index_start + skin_bone_count])
        if all(v < name_count for v in values) and len(set(values)) >= max(1, skin_bone_count // 2):
            skin_name_indices = values
    if not skin_name_indices:
        start = 3 if name_count > 3 else 0
        skin_name_indices = list(range(start, min(name_count, start + skin_bone_count)))
    positions = _make_node_positions(parent_by_name_index, node_name_indices)
    bone_lookup = {name_index: i for i, name_index in enumerate(skin_name_indices)}
    bones = []
    for index, name_index in enumerate(skin_name_indices):
        parent_name_index = parent_by_name_index.get(name_index, -1)
        parent_index = bone_lookup.get(parent_name_index, -1)
        head = positions.get(name_index, [0.0, 0.0, round(index * 0.045, 6)])
        child_heads = [positions[c] for c, pidx in parent_by_name_index.items() if pidx == name_index and c in positions]
        if child_heads:
            tail = child_heads[0]
        else:
            tail = [head[0], head[1], round(head[2] + 0.035, 6)]
        bones.append({'index': index, 'name_index': name_index, 'name': names[name_index]['name'], 'parent_index': parent_index, 'parent_name_index': parent_name_index, 'head': head, 'tail': tail})
    tail = asset[fields_offset:]
    return {
        'type': 'SKEL',
        'version_a': version_a,
        'version_b': version_b,
        'marker': f'0x{marker:08X}',
        'unknown_a': unknown_a,
        'size': len(asset),
        'sha1': sha1_bytes(asset),
        'name_count': name_count,
        'names': names,
        'fields': fields,
        'fields_offset': fields_offset,
        'parent_table_offset': parent_start,
        'parent_table': parent_raw,
        'skin_name_indices': skin_name_indices,
        'tail_size': len(tail),
        'tail_sha1': sha1_bytes(tail),
        'skin_bone_count': skin_bone_count,
        'bones': bones,
        'status': 'SKEL-Bone-Namen und Parent-Tabelle werden gelesen. Bind-Pose bleibt bis zur vollständigen Matrix-Tabelle noch angenähert.'
    }

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
