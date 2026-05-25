from pathlib import Path
from collections import Counter, defaultdict
from room_scene_codec import parse_room_asset, export_room_package as export_room_package_base, format_room_info_lines as format_room_info_lines_base, format_uuid_hex, first_parent_transform, transform_text
from pak_core import get_entry_asset

def asset_uuid_map(parsed):
    wanted = {'WMDL', 'SMDL', 'CMDL', 'CHAR', 'CLSN', 'DCLN', 'TXTR', 'MTRL', 'CSMP', 'CAUD', 'GENP', 'FSMC', 'RSTC', 'LPRB', 'LPRR'}
    out = {}
    for entry in parsed.get('entries', []):
        kind = entry.get('type')
        if kind in wanted:
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

def component_body_bytes(component):
    try:
        return bytes.fromhex(component.get('body_hex') or '')
    except Exception:
        return b''

def collect_room_asset_references(parsed, entry):
    asset = get_entry_asset(parsed, entry)
    info = parse_room_asset(asset)
    known = asset_uuid_map(parsed)
    refs = []
    for component in info['components']:
        body = component_body_bytes(component)
        transform = first_parent_transform(component)
        parent_names = '; '.join(parent['name'] for parent in component.get('parents', []))
        for uuid_hex, ref_entry in known.items():
            needle = bytes.fromhex(uuid_hex)
            for rel in find_all(body, needle):
                refs.append({'uuid_hex': uuid_hex, 'entry_index': ref_entry['index'], 'entry_type': ref_entry['type'], 'entry_name': ref_entry.get('display_name') or ref_entry.get('name') or ref_entry['uuid_hex'], 'component_name': component['name'], 'component_uuid_hex': component['uuid_hex'], 'component_type_hash': component['type_hash'], 'component_off': component['off'], 'body_rel': rel, 'layer_index': component['layer_index'], 'layer_name': component['layer_name'], 'parent_names': parent_names, 'parent_position': transform_text(transform, 'position'), 'parent_rotation': transform_text(transform, 'rotation'), 'parent_scale': transform_text(transform, 'scale'), 'kind': 'component_body'})
    head_refs = []
    head = next((section for section in info['sections'] if section['type'] == 'HEAD'), None)
    if head is not None:
        head_data = asset[head['off']:head['off'] + head['size']]
        for uuid_hex, ref_entry in known.items():
            needle = bytes.fromhex(uuid_hex)
            for rel in find_all(head_data, needle):
                head_refs.append({'uuid_hex': uuid_hex, 'entry_index': ref_entry['index'], 'entry_type': ref_entry['type'], 'entry_name': ref_entry.get('display_name') or ref_entry.get('name') or ref_entry['uuid_hex'], 'head_rel': rel, 'asset_off': head['off'] + rel, 'kind': 'head_dependency'})
    return {'info': info, 'component_refs': refs, 'head_refs': head_refs}

def write_asset_refs_tsv(path, refs):
    lines = ['index\ttype\tuuid\tentry_index\tentry_name\tlayer\tcomponent\tcomponent_type_hash\tcomponent_offset\tbody_offset\tparent_actor\tparent_position\tparent_rotation\tparent_scale']
    for index, ref in enumerate(refs):
        lines.append(f'{index}\t{ref["entry_type"]}\t{format_uuid_hex(ref["uuid_hex"])}\t{ref["entry_index"]}\t{ref["entry_name"]}\t{ref["layer_name"]}\t{ref["component_name"]}\t{ref["component_type_hash"]}\t0x{ref["component_off"]:X}\t0x{ref["body_rel"]:X}\t{ref["parent_names"]}\t{ref["parent_position"]}\t{ref["parent_rotation"]}\t{ref["parent_scale"]}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def write_head_refs_tsv(path, refs):
    lines = ['index\ttype\tuuid\tentry_index\tentry_name\thead_offset\tasset_offset']
    for index, ref in enumerate(refs):
        lines.append(f'{index}\t{ref["entry_type"]}\t{format_uuid_hex(ref["uuid_hex"])}\t{ref["entry_index"]}\t{ref["entry_name"]}\t0x{ref["head_rel"]:X}\t0x{ref["asset_off"]:X}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def append_deep_report(path, refs, head_refs):
    lines = Path(path).read_text(encoding='utf-8').splitlines() if Path(path).exists() else []
    lines.append('')
    lines.append('ROOM-Asset-Referenzen aus Komponenten:')
    by_type = Counter(ref['entry_type'] for ref in refs)
    if by_type:
        for kind, count in sorted(by_type.items()):
            lines.append(f'- {kind}: {count}')
    else:
        lines.append('- keine')
    lines.append('')
    lines.append('ROOM-Asset-Referenzen aus HEAD/Dependency-Liste:')
    by_head_type = Counter(ref['entry_type'] for ref in head_refs)
    if by_head_type:
        for kind, count in sorted(by_head_type.items()):
            lines.append(f'- {kind}: {count}')
    else:
        lines.append('- keine')
    if refs:
        lines.append('')
        lines.append('Komponenten-Referenzen:')
        grouped = defaultdict(list)
        for ref in refs:
            grouped[(ref['layer_name'], ref['component_name'], ref['component_type_hash'])].append(ref)
        for (layer, component, type_hash), items in sorted(grouped.items(), key=lambda item: (item[0][0], item[0][1], item[0][2]))[:200]:
            names = ', '.join(f'{ref["entry_type"]}:{format_uuid_hex(ref["uuid_hex"])}' for ref in items[:8])
            if len(items) > 8:
                names += f', ... +{len(items) - 8}'
            parent = items[0].get('parent_names', '')
            pos = items[0].get('parent_position', '')
            lines.append(f'- {layer} | {component} | {type_hash} | Parent {parent} | Pos {pos} | {names}')
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')

def format_room_info_lines(parsed, entry):
    base = format_room_info_lines_base(parsed, entry)
    deep = collect_room_asset_references(parsed, entry)
    refs = deep['component_refs']
    head_refs = deep['head_refs']
    base.append('')
    base.append('Asset-Referenzen aus ROOM-Komponenten:')
    by_type = Counter(ref['entry_type'] for ref in refs)
    if by_type:
        for kind, count in sorted(by_type.items()):
            base.append(f'- {kind}: {count}')
    else:
        base.append('- keine auflösbaren Referenzen im aktuellen PAK')
    base.append('')
    base.append('Asset-Referenzen aus HEAD/Dependency-Liste:')
    by_head_type = Counter(ref['entry_type'] for ref in head_refs)
    if by_head_type:
        for kind, count in sorted(by_head_type.items()):
            base.append(f'- {kind}: {count}')
    else:
        base.append('- keine auflösbaren Referenzen im aktuellen PAK')
    if refs:
        base.append('')
        base.append('Beispiele aus Komponenten:')
        for ref in refs[:80]:
            base.append(f'- {ref["entry_type"]} {format_uuid_hex(ref["uuid_hex"])} | Layer {ref["layer_name"]} | {ref["component_name"]} | Parent {ref["parent_names"]} | Pos {ref["parent_position"]}')
        if len(refs) > 80:
            base.append(f'... {len(refs) - 80} weitere')
    return base

def export_room_package(parsed, entry, out_dir):
    result = export_room_package_base(parsed, entry, out_dir)
    deep = collect_room_asset_references(parsed, entry)
    package_dir = Path(result['package_dir'])
    asset_refs_path = package_dir / 'asset_references.tsv'
    head_refs_path = package_dir / 'head_references.tsv'
    write_asset_refs_tsv(asset_refs_path, deep['component_refs'])
    write_head_refs_tsv(head_refs_path, deep['head_refs'])
    append_deep_report(result['report_path'], deep['component_refs'], deep['head_refs'])
    result['asset_refs_path'] = str(asset_refs_path)
    result['head_refs_path'] = str(head_refs_path)
    result['component_asset_ref_count'] = len(deep['component_refs'])
    result['head_asset_ref_count'] = len(deep['head_refs'])
    return result
