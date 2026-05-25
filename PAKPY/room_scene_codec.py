from pathlib import Path
import json
import re
import struct
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes
from dcln_codec import parse_dcln_asset, format_uuid_hex

def be16(data, off):
    return int.from_bytes(data[off:off+2], 'big')

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def fmt_num(value):
    text = f'{value:.9g}'
    return '0' if text == '-0' else text

def clean_obj_name(text):
    text = safe_name(text or 'item')
    text = re.sub(r'[^A-Za-z0-9_\-.]+', '_', text)
    return text or 'item'

def is_room_asset(asset):
    return len(asset) >= 32 and asset[:4] == b'RFRM' and tag4(asset, 20) == 'ROOM'

def iter_rfrm_children(asset, start, end):
    p = start
    index = 0
    while p < end:
        if p + 32 > end or asset[p:p+4] != b'RFRM':
            raise PakError(f'ROOM-Unterblock ist kein RFRM bei 0x{p:X}')
        size = be64(asset, p + 4)
        child_end = p + 32 + size
        if child_end > end:
            raise PakError(f'ROOM-Unterblock läuft über Dateiende bei 0x{p:X}')
        yield {'index': index, 'off': p, 'end': child_end, 'size': child_end - p, 'payload_size': size, 'type': tag4(asset, p + 20), 'version_a': be32(asset, p + 24), 'version_b': be32(asset, p + 28)}
        p = child_end
        index += 1

def parse_lhed(asset, off, limit):
    if off + 24 > limit or tag4(asset, off) != 'LHED':
        return {'name': '', 'uuid_hex': '', 'end': off, 'extra_hex': ''}
    size = be64(asset, off + 4)
    payload = off + 24
    end = payload + size
    if end > limit or payload + 4 > end:
        return {'name': '', 'uuid_hex': '', 'end': min(end, limit), 'extra_hex': ''}
    name_len = be32(asset, payload)
    name_start = payload + 4
    name_end = name_start + name_len
    if name_len > 4096 or name_end > end:
        return {'name': '', 'uuid_hex': '', 'end': end, 'extra_hex': ''}
    name = asset[name_start:name_end].decode('utf-8', 'replace').rstrip('\x00')
    uuid_start = name_end
    uuid_end = uuid_start + 16
    uuid_hex = asset[uuid_start:uuid_end].hex() if uuid_end <= end else ''
    extra = asset[uuid_end:end].hex() if uuid_end <= end else ''
    return {'name': name, 'uuid_hex': uuid_hex, 'end': end, 'extra_hex': extra}

def parse_property_blob(data):
    if len(data) < 6:
        return None
    unknown = be32(data, 0)
    count = be16(data, 4)
    if count > 2048:
        return None
    p = 6
    props = []
    for index in range(count):
        if p + 6 > len(data):
            return None
        key = data[p:p+4].hex()
        size = be16(data, p + 4)
        value_start = p + 6
        value_end = value_start + size
        if value_end > len(data):
            return None
        value = data[value_start:value_end]
        props.append({'index': index, 'key': key, 'size': size, 'value_hex': value.hex(), 'value': value})
        p = value_end
    if p != len(data):
        return None
    return {'unknown': unknown, 'count': count, 'properties': props}

def parse_actor_ref_blob(data):
    if len(data) < 25:
        return None
    count = be32(data, 0)
    if count < 1 or count > 512:
        return None
    p = 4
    refs = []
    for index in range(count):
        if p + 21 > len(data) or data[p:p+4] != b'COMP':
            return None
        refs.append({'index': index, 'uuid_hex': data[p+4:p+20].hex(), 'flag': data[p+20]})
        p += 21
    tail = data[p:]
    transform = None
    if len(tail) == 37:
        try:
            values = struct.unpack('>9f', tail[1:37])
            transform = {'flag': tail[0], 'position': values[0:3], 'rotation': values[3:6], 'scale': values[6:9], 'tail_hex': tail.hex()}
        except Exception:
            transform = None
    return {'count': count, 'refs': refs, 'tail_hex': tail.hex(), 'transform': transform}

def parse_comp(asset, off, limit):
    if off + 24 > limit or tag4(asset, off) != 'COMP':
        return None
    size = be64(asset, off + 4)
    payload = off + 24
    end = payload + size
    if end > limit or payload + 24 > end:
        return None
    type_hash = asset[payload:payload+4].hex()
    uuid_hex = asset[payload+4:payload+20].hex()
    name_len = be32(asset, payload + 20)
    name_start = payload + 24
    name_end = name_start + name_len
    if name_len > 4096 or name_end > end:
        return None
    name = asset[name_start:name_end].decode('utf-8', 'replace').rstrip('\x00')
    body = asset[name_end:end]
    prop_blob = parse_property_blob(body)
    actor_refs = None if prop_blob is not None else parse_actor_ref_blob(body)
    return {'off': off, 'end': end, 'size': end - off, 'payload_size': size, 'uuid_hex': uuid_hex, 'type_hash': type_hash, 'name': name, 'body_hex': body.hex(), 'properties': [] if prop_blob is None else prop_blob['properties'], 'property_blob_unknown': None if prop_blob is None else prop_blob['unknown'], 'property_blob_count': 0 if prop_blob is None else prop_blob['count'], 'actor_refs': actor_refs}

def parse_room_asset(asset):
    if not is_room_asset(asset):
        raise PakError('ROOM hat keinen gültigen RFRM/ROOM-Header')
    root_size = be64(asset, 4)
    root_end = 32 + root_size
    if root_end > len(asset):
        raise PakError('ROOM-RFRM-Größe läuft über Dateiende')
    sections = []
    layers = []
    components = []
    for section in iter_rfrm_children(asset, 32, root_end):
        sections.append({'index': section['index'], 'type': section['type'], 'off': section['off'], 'size': section['size'], 'payload_size': section['payload_size']})
        if section['type'] != 'LAYR':
            continue
        lhed = parse_lhed(asset, section['off'] + 32, section['end'])
        layer = {'index': section['index'], 'off': section['off'], 'size': section['size'], 'name': lhed['name'], 'uuid_hex': lhed['uuid_hex'], 'extra_hex': lhed['extra_hex'], 'component_count': 0}
        p = lhed['end']
        srip = None
        while p < section['end']:
            if p + 32 > section['end'] or asset[p:p+4] != b'RFRM':
                break
            child_size = be64(asset, p + 4)
            child_end = p + 32 + child_size
            if tag4(asset, p + 20) == 'SRIP':
                srip = {'off': p, 'end': child_end, 'payload_size': child_size}
            p = child_end
        if srip is not None:
            q = srip['off'] + 32
            while q < srip['end']:
                comp = parse_comp(asset, q, srip['end'])
                if comp is None:
                    break
                comp['layer_index'] = layer['index']
                comp['layer_name'] = layer['name']
                comp['layer_uuid_hex'] = layer['uuid_hex']
                comp['asset_off'] = comp['off']
                components.append(comp)
                layer['component_count'] += 1
                q = comp['end']
        layers.append(layer)
    component_by_uuid = {component['uuid_hex']: component for component in components}
    for component in components:
        component['parents'] = []
    for actor in components:
        actor_refs = actor.get('actor_refs')
        if not actor_refs:
            continue
        for ref in actor_refs['refs']:
            child = component_by_uuid.get(ref['uuid_hex'])
            if child is not None:
                child['parents'].append({'uuid_hex': actor['uuid_hex'], 'name': actor['name'], 'type_hash': actor['type_hash'], 'layer_name': actor['layer_name'], 'transform': actor_refs.get('transform'), 'child_flag': ref['flag']})
    dcln_refs = []
    for component in components:
        for prop in component['properties']:
            if prop['key'] == 'fb4fcb5b' and prop['size'] == 16:
                dcln_refs.append({'dcln_uuid_hex': prop['value_hex'], 'property_key': prop['key'], 'component_uuid_hex': component['uuid_hex'], 'component_name': component['name'], 'component_type_hash': component['type_hash'], 'component_off': component['off'], 'layer_index': component['layer_index'], 'layer_name': component['layer_name'], 'parents': component.get('parents', [])})
    return {'type': 'ROOM', 'root_version_a': be32(asset, 24), 'root_version_b': be32(asset, 28), 'size': len(asset), 'sha1': sha1_bytes(asset), 'sections': sections, 'layers': layers, 'components': components, 'component_by_uuid': component_by_uuid, 'dcln_refs': dcln_refs}

def dcln_entry_map(parsed):
    return {entry['uuid_hex'].lower(): entry for entry in parsed.get('entries', []) if entry.get('type') == 'DCLN'}

def transform_text(transform, key):
    if not transform or not transform.get(key):
        return ''
    return ','.join(fmt_num(x) for x in transform[key])

def first_parent_transform(item):
    parents = item.get('parents') or []
    if not parents:
        return None
    return parents[0].get('transform')

def format_room_info_lines(parsed, entry):
    info = parse_room_asset(get_entry_asset(parsed, entry))
    known = dcln_entry_map(parsed)
    actor_count = sum(1 for component in info['components'] if component.get('actor_refs'))
    transform_count = sum(1 for component in info['components'] if component.get('actor_refs') and component['actor_refs'].get('transform'))
    lines = ['ROOM-Analyse:', f'- Version: {info["root_version_a"]} / {info["root_version_b"]}', f'- Sections: {len(info["sections"])}', f'- Layer: {len(info["layers"])}', f'- Komponenten: {len(info["components"])}', f'- Actor-Komponenten: {actor_count}', f'- Actor-Transforms: {transform_count}', f'- DCLN-Referenzen: {len(info["dcln_refs"])}', f'- DCLN-Referenzen mit Eintrag im aktuellen PAK: {sum(1 for ref in info["dcln_refs"] if ref["dcln_uuid_hex"] in known)}']
    if info['layers']:
        lines.append('')
        lines.append('Layer mit Komponenten:')
        for layer in sorted(info['layers'], key=lambda item: (-item['component_count'], item['index']))[:30]:
            if layer['component_count']:
                lines.append(f'- #{layer["index"]} {layer["name"] or "<ohne Namen>"} | Komponenten {layer["component_count"]}')
    if info['dcln_refs']:
        lines.append('')
        lines.append('DCLN-Referenzen:')
        for ref in info['dcln_refs'][:80]:
            status = 'im PAK' if ref['dcln_uuid_hex'] in known else 'nicht im PAK'
            transform = first_parent_transform(ref)
            pos = transform_text(transform, 'position')
            lines.append(f'- {format_uuid_hex(ref["dcln_uuid_hex"])} | {status} | Layer {ref["layer_name"]} | {ref["component_name"]} | ParentPos {pos}')
        if len(info['dcln_refs']) > 80:
            lines.append(f'... {len(info["dcln_refs"]) - 80} weitere')
    return lines

def serializable_component(component):
    item = {k: v for k, v in component.items()}
    for prop in item.get('properties', []):
        prop.pop('value', None)
    return item

def write_components_tsv(path, components):
    lines = ['index\toffset\tlayer\ttype_hash\tuuid\tname\tproperty_count\tactor_ref_count\tparent_count\tparent_position\tparent_rotation\tparent_scale']
    for index, comp in enumerate(components):
        ref_count = 0 if not comp.get('actor_refs') else len(comp['actor_refs']['refs'])
        transform = first_parent_transform(comp)
        lines.append(f'{index}\t0x{comp["off"]:X}\t{comp["layer_name"]}\t{comp["type_hash"]}\t{format_uuid_hex(comp["uuid_hex"])}\t{comp["name"]}\t{len(comp["properties"])}\t{ref_count}\t{len(comp.get("parents", []))}\t{transform_text(transform, "position")}\t{transform_text(transform, "rotation")}\t{transform_text(transform, "scale")}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def write_dcln_refs_tsv(path, refs, known):
    lines = ['index\tdcln_uuid\tstatus\tlayer\tcomponent\tcomponent_uuid\tcomponent_type_hash\tcomponent_offset\tparent_names\tparent_position\tparent_rotation\tparent_scale']
    for index, ref in enumerate(refs):
        status = 'in_pak' if ref['dcln_uuid_hex'] in known else 'missing'
        parents = '; '.join(parent['name'] for parent in ref.get('parents', []))
        transform = first_parent_transform(ref)
        lines.append(f'{index}\t{format_uuid_hex(ref["dcln_uuid_hex"])}\t{status}\t{ref["layer_name"]}\t{ref["component_name"]}\t{format_uuid_hex(ref["component_uuid_hex"])}\t{ref["component_type_hash"]}\t0x{ref["component_off"]:X}\t{parents}\t{transform_text(transform, "position")}\t{transform_text(transform, "rotation")}\t{transform_text(transform, "scale")}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def write_room_report(path, entry, info, known):
    lines = [f'ROOM: {entry.get("display_name") or entry.get("name") or entry["uuid_hex"]}', f'UUID: {format_uuid_hex(entry["uuid_hex"])}', f'Sections: {len(info["sections"])}', f'Layer: {len(info["layers"])}', f'Komponenten: {len(info["components"])}', f'DCLN-Referenzen: {len(info["dcln_refs"])}', f'DCLN im aktuellen PAK auflösbar: {sum(1 for ref in info["dcln_refs"] if ref["dcln_uuid_hex"] in known)}', '', 'DCLN-Referenzen:']
    for ref in info['dcln_refs']:
        status = 'im PAK' if ref['dcln_uuid_hex'] in known else 'nicht im PAK'
        parents = '; '.join(parent['name'] for parent in ref.get('parents', []))
        transform = first_parent_transform(ref)
        lines.append(f'- {format_uuid_hex(ref["dcln_uuid_hex"])} | {status} | Layer {ref["layer_name"]} | {ref["component_name"]} | Parent {parents} | Pos {transform_text(transform, "position")} | Rot {transform_text(transform, "rotation")} | Scale {transform_text(transform, "scale")}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def write_collision_mtl(path):
    lines = []
    palette = [(1, 0.18, 0.18), (0.18, 1, 0.18), (0.18, 0.35, 1), (1, 0.85, 0.18), (1, 0.18, 1), (0.18, 1, 1), (0.8, 0.8, 0.8), (1, 0.55, 0.18)]
    for index, color in enumerate(palette):
        lines += [f'newmtl room_collision_{index:03d}', f'Kd {fmt_num(color[0])} {fmt_num(color[1])} {fmt_num(color[2])}', 'Ka 0 0 0', 'Ks 0 0 0', 'd 1', '']
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def transformed_offset(ref, fallback_index):
    transform = first_parent_transform(ref)
    if transform and transform.get('position'):
        return transform['position']
    return ((fallback_index % 8) * 4.0, 0.0, (fallback_index // 8) * 4.0)

def transformed_scale(ref):
    transform = first_parent_transform(ref)
    if transform and transform.get('scale'):
        return transform['scale']
    return (1.0, 1.0, 1.0)

def write_collision_debug_obj(parsed, refs, known, obj_path, mtl_name):
    lines = ['o room_collision_debug', f'mtllib {mtl_name}']
    vertex_base = 1
    exported = 0
    for ref_index, ref in enumerate(refs):
        entry = known.get(ref['dcln_uuid_hex'])
        if entry is None:
            continue
        dcln = parse_dcln_asset(get_entry_asset(parsed, entry))
        offset = transformed_offset(ref, exported)
        scale = transformed_scale(ref)
        name = clean_obj_name(f'{ref_index:03d}_{ref["layer_name"]}_{ref["component_name"]}_{format_uuid_hex(ref["dcln_uuid_hex"])}')
        lines.append(f'g {name}')
        for vertex in dcln['vertices']:
            x, y, z = vertex['pos']
            lines.append(f'v {fmt_num(x * scale[0] + offset[0])} {fmt_num(y * scale[1] + offset[1])} {fmt_num(z * scale[2] + offset[2])}')
        last_mat = None
        for tri in dcln['triangles']:
            mat = tri['material_index'] % 8
            if mat != last_mat:
                lines.append(f'usemtl room_collision_{mat:03d}')
                last_mat = mat
            a, b, c = tri['vertices']
            lines.append(f'f {vertex_base + a} {vertex_base + b} {vertex_base + c}')
        vertex_base += len(dcln['vertices'])
        exported += 1
    Path(obj_path).write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    return exported

def export_room_package(parsed, entry, out_dir):
    if entry['type'] != 'ROOM':
        raise PakError('ROOM-Paket geht nur bei ROOM')
    out_dir = Path(out_dir)
    package_dir = out_dir / f'{safe_name(entry.get("display_name") or entry.get("name") or entry["uuid_hex"])}_{format_uuid_hex(entry["uuid_hex"])}_room'
    package_dir.mkdir(parents=True, exist_ok=True)
    info = parse_room_asset(get_entry_asset(parsed, entry))
    known = dcln_entry_map(parsed)
    write_components_tsv(package_dir / 'components.tsv', info['components'])
    write_dcln_refs_tsv(package_dir / 'dcln_references.tsv', info['dcln_refs'], known)
    write_room_report(package_dir / 'report.txt', entry, info, known)
    write_collision_mtl(package_dir / 'room_collision_debug.mtl')
    exported_collision_count = write_collision_debug_obj(parsed, info['dcln_refs'], known, package_dir / 'room_collision_debug.obj', 'room_collision_debug.mtl')
    manifest = {'version': 2, 'entry_index': entry['index'], 'entry_type': entry['type'], 'entry_uuid_hex': entry['uuid_hex'], 'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'], 'asset_sha1': info['sha1'], 'root_version_a': info['root_version_a'], 'root_version_b': info['root_version_b'], 'sections': info['sections'], 'layers': info['layers'], 'components': [serializable_component(component) for component in info['components']], 'dcln_refs': info['dcln_refs'], 'world_transforms_known': True, 'collision_debug_obj_note': 'DCLN meshes use parsed parent actor position and scale when available. Rotation is listed but not applied yet.'}
    manifest_path = package_dir / 'room_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return {'package_dir': str(package_dir), 'manifest_path': str(manifest_path), 'components_path': str(package_dir / 'components.tsv'), 'dcln_refs_path': str(package_dir / 'dcln_references.tsv'), 'report_path': str(package_dir / 'report.txt'), 'collision_obj_path': str(package_dir / 'room_collision_debug.obj'), 'component_count': len(info['components']), 'layer_count': len(info['layers']), 'dcln_ref_count': len(info['dcln_refs']), 'resolved_dcln_ref_count': sum(1 for ref in info['dcln_refs'] if ref['dcln_uuid_hex'] in known), 'exported_collision_count': exported_collision_count}

def describe_room_hit(asset, asset_off, uuid_hex):
    try:
        info = parse_room_asset(asset)
    except Exception:
        return None
    for component in info['components']:
        if not (component['off'] <= asset_off < component['end']):
            continue
        hit_prop = None
        rel = asset_off - component['off']
        for prop in component['properties']:
            if prop['size'] == 16 and prop['value_hex'] == uuid_hex:
                hit_prop = prop
                break
        transform = first_parent_transform(component)
        return {'layer_name': component['layer_name'], 'component_name': component['name'], 'component_uuid_hex': component['uuid_hex'], 'component_type_hash': component['type_hash'], 'component_rel': rel, 'property_key': '' if hit_prop is None else hit_prop['key'], 'parent_position': transform_text(transform, 'position')}
    for layer in info['layers']:
        if layer['off'] <= asset_off < layer['off'] + layer['size']:
            return {'layer_name': layer['name'], 'component_name': '', 'component_uuid_hex': '', 'component_type_hash': '', 'component_rel': None, 'property_key': '', 'parent_position': ''}
    return None

def format_room_hit_extra(extra):
    if not extra:
        return ''
    parts = []
    if extra.get('layer_name'):
        parts.append(f'Layer {extra["layer_name"]}')
    if extra.get('component_name'):
        parts.append(f'COMP {extra["component_name"]}')
    if extra.get('component_type_hash'):
        parts.append(f'TypHash {extra["component_type_hash"]}')
    if extra.get('component_rel') is not None:
        parts.append(f'COMP+0x{extra["component_rel"]:X}')
    if extra.get('property_key'):
        parts.append(f'Property {extra["property_key"]}')
    if extra.get('parent_position'):
        parts.append(f'ParentPos {extra["parent_position"]}')
    return ' | '.join(parts)
