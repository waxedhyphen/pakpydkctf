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
    tables_offset = p
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
    skin_bone_count = fields.get('skin_bone_count', 0)
    bone_start = 3 if len(names) > 3 else 0
    bones = []
    for index in range(skin_bone_count):
        name_index = bone_start + index
        if name_index >= len(names):
            break
        parent_index = 0 if index > 0 else -1
        bones.append({
            'index': index,
            'name_index': name_index,
            'name': names[name_index]['name'],
            'parent_index': parent_index,
            'head': [0.0, 0.0, round(index * 0.035, 6)],
            'tail': [0.0, 0.0, round((index + 1) * 0.035, 6)]
        })
    tail = asset[tables_offset:]
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
        'tables_offset': tables_offset,
        'tail_size': len(tail),
        'tail_sha1': sha1_bytes(tail),
        'skin_bone_count': skin_bone_count,
        'bone_name_start_index': bone_start,
        'bones': bones,
        'status': 'Bone-Namen und SKHD-kompatible Bone-Anzahl werden gelesen. Parent-Struktur und Bind-Pose sind noch konservativ als Root-Armature abgebildet.'
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
    return {
        'type': typ,
        'size': len(asset),
        'sha1': sha1_bytes(asset),
        'chunks': parse_rfrm_chunks(asset)
    }

def parse_model_chunks(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM':
        raise PakError('Keine RFRM-Modellressource')
    chunks = {}
    p = 32
    while p + 24 <= len(asset):
        tag = tag4(asset, p)
        size = be64(asset, p + 4)
        payload_off = p + 24
        payload_end = payload_off + size
        if payload_end > len(asset):
            break
        chunks[tag] = asset[payload_off:payload_end]
        p = payload_end
    return chunks

def parse_model_skin_summary(asset):
    chunks = parse_model_chunks(asset)
    typ = tag4(asset, 20) if len(asset) >= 24 else ''
    bone_count = 0
    if 'SKHD' in chunks and len(chunks['SKHD']) >= 4:
        bone_count = be32(chunks['SKHD'], 0)
    vbufs = []
    skin_components = []
    payload = chunks.get('VBUF', b'')
    if len(payload) >= 4:
        count = be32(payload, 0)
        p = 4
        for buffer_index in range(count):
            if p + 8 > len(payload):
                break
            vertex_count = be32(payload, p)
            component_count = be32(payload, p + 4)
            p += 8
            components = []
            for component_index in range(component_count):
                if p + 20 > len(payload):
                    break
                component = {
                    'component_index': component_index,
                    'field_0': be32(payload, p),
                    'offset': be32(payload, p + 4),
                    'stride': be32(payload, p + 8),
                    'format': be32(payload, p + 12),
                    'semantic': be32(payload, p + 16)
                }
                components.append(component)
                if component['semantic'] in (8, 9, 10, 11):
                    skin_components.append({'buffer_index': buffer_index, **component})
                p += 20
            vbufs.append({'buffer_index': buffer_index, 'vertex_count': vertex_count, 'component_count': component_count, 'components': components})
    inferred_bones = []
    for index in range(bone_count):
        inferred_bones.append({
            'index': index,
            'name': f'bone_{index:03d}',
            'parent_index': 0 if index > 0 else -1,
            'head': [0.0, 0.0, round(index * 0.035, 6)],
            'tail': [0.0, 0.0, round((index + 1) * 0.035, 6)]
        })
    return {
        'model_type': typ,
        'bone_count_from_skhd': bone_count,
        'has_skeleton_header': 'SKHD' in chunks,
        'vbufs': vbufs,
        'skin_components': skin_components,
        'inferred_bones': inferred_bones,
        'note': 'SKHD liefert sicher die Bone-Anzahl. Wenn eine passende SKEL-Referenz vorhanden ist, werden die echten Bone-Namen aus SKEL verwendet.'
    }

def merge_skel_into_model_summary(model_summary, skel_summary):
    bones = skel_summary.get('bones') or []
    if not bones:
        return model_summary
    expected = model_summary.get('bone_count_from_skhd', 0)
    use_bones = bones[:expected] if expected else bones
    model_summary['skel'] = skel_summary
    model_summary['inferred_bones'] = use_bones
    model_summary['bone_names_from_skel'] = True
    return model_summary

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

def blender_model_import_script():
    return r'''import bpy
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
manifest_path = root / 'repack_manifest.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
obj_name = manifest.get('obj_name') or ''
if obj_name:
    bpy.ops.wm.obj_import(filepath=str(root / obj_name)) if hasattr(bpy.ops.wm, 'obj_import') else bpy.ops.import_scene.obj(filepath=str(root / obj_name))
skel_path = root / 'skeleton' / 'model_skeleton_summary.json'
if skel_path.is_file():
    info = json.loads(skel_path.read_text(encoding='utf-8'))
    bones = info.get('inferred_bones') or []
    if bones:
        bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
        arm = bpy.context.object
        arm.name = 'Armature_' + manifest.get('entry_name', 'model')
        data = arm.data
        data.name = arm.name + '_data'
        created = {}
        first = data.edit_bones[0]
        b0 = bones[0]
        first.name = b0.get('name', 'bone_000')
        first.head = tuple(b0.get('head', [0, 0, 0]))
        first.tail = tuple(b0.get('tail', [0, 0, 0.035]))
        created[int(b0.get('index', 0))] = first
        for bone in bones[1:]:
            idx = int(bone.get('index', len(created)))
            eb = data.edit_bones.new(bone.get('name', f'bone_{idx:03d}'))
            eb.head = tuple(bone.get('head', [0, 0, idx * 0.035]))
            eb.tail = tuple(bone.get('tail', [0, 0, (idx + 1) * 0.035]))
            parent = created.get(int(bone.get('parent_index', 0)))
            if parent is not None and parent != eb:
                eb.parent = parent
            created[idx] = eb
        bpy.ops.object.mode_set(mode='OBJECT')
anim_manifest = root / 'animations' / 'animation_manifest.json'
if anim_manifest.is_file():
    data = json.loads(anim_manifest.read_text(encoding='utf-8'))
    for item in data.get('animations', []):
        name = item.get('name') or item.get('uuid_hex') or 'ANIM'
        action = bpy.data.actions.new(name=name)
        action['source_uuid'] = item.get('uuid_hex', '')
        action['source_file'] = item.get('raw_file', '')
'''

def blender_char_import_script():
    return r'''import bpy
import json
from pathlib import Path
root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / 'char_manifest.json').read_text(encoding='utf-8'))
for model in manifest.get('models', []):
    package_dir = model.get('model_package_dir') or ''
    if not package_dir:
        continue
    pkg = root / package_dir
    repack = pkg / 'repack_manifest.json'
    if not repack.is_file():
        continue
    data = json.loads(repack.read_text(encoding='utf-8'))
    obj_name = data.get('obj_name') or ''
    if obj_name:
        path = pkg / obj_name
        if path.is_file():
            bpy.ops.wm.obj_import(filepath=str(path)) if hasattr(bpy.ops.wm, 'obj_import') else bpy.ops.import_scene.obj(filepath=str(path))
    skel_path = pkg / 'skeleton' / 'model_skeleton_summary.json'
    if skel_path.is_file():
        info = json.loads(skel_path.read_text(encoding='utf-8'))
        bones = info.get('inferred_bones') or []
        if bones:
            bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
            arm = bpy.context.object
            arm.name = 'Armature_' + model.get('slot_name', data.get('entry_name', 'model'))
            created = {}
            first = arm.data.edit_bones[0]
            b0 = bones[0]
            first.name = b0.get('name', 'bone_000')
            first.head = tuple(b0.get('head', [0, 0, 0]))
            first.tail = tuple(b0.get('tail', [0, 0, 0.035]))
            created[int(b0.get('index', 0))] = first
            for bone in bones[1:]:
                idx = int(bone.get('index', len(created)))
                eb = arm.data.edit_bones.new(bone.get('name', f'bone_{idx:03d}'))
                eb.head = tuple(bone.get('head', [0, 0, idx * 0.035]))
                eb.tail = tuple(bone.get('tail', [0, 0, (idx + 1) * 0.035]))
                parent = created.get(int(bone.get('parent_index', 0)))
                if parent is not None and parent != eb:
                    eb.parent = parent
                created[idx] = eb
            bpy.ops.object.mode_set(mode='OBJECT')
for anim in manifest.get('animations', []):
    if anim.get('resolved'):
        action = bpy.data.actions.new(name=anim.get('name') or anim.get('uuid_hex') or 'ANIM')
        action['source_uuid'] = anim.get('uuid_hex', '')
        action['source_file'] = anim.get('file', '')
'''

def export_model_skeletal_sidecar(parsed, entry, package_dir, require_store=None, animation_refs=None, skeleton_refs=None):
    package_dir = Path(package_dir)
    asset = get_entry_asset(parsed, entry)
    skeleton_dir = package_dir / 'skeleton'
    animations_dir = package_dir / 'animations'
    blender_dir = package_dir / 'blender'
    summary = parse_model_skin_summary(asset)
    summary.update({'entry_uuid_hex': entry['uuid_hex'], 'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'], 'entry_type': entry['type']})
    refs = find_known_uuid_refs(asset, parsed, require_store, wanted_types=SKELETAL_REF_TYPES)
    detected_skel = []
    detected_anims = []
    for ref in refs:
        if ref.get('entry_type') == 'SKEL':
            detected_skel.append({'uuid_hex': ref['uuid_hex'], 'name': ref.get('entry_name', ''), 'type': 'SKEL'})
        elif ref.get('entry_type') == 'ANIM':
            detected_anims.append({'uuid_hex': ref['uuid_hex'], 'name': ref.get('entry_name', ''), 'type': 'ANIM'})
    skeleton_refs = list(skeleton_refs or []) + detected_skel
    seen_skel = set()
    exported_skel = []
    selected_skel_summary = None
    for skel in skeleton_refs:
        uuid_hex = skel.get('uuid_hex', '')
        if not uuid_hex or uuid_hex == ZERO_UUID or uuid_hex in seen_skel:
            continue
        seen_skel.add(uuid_hex)
        exported = export_skeletal_asset(skeleton_dir / 'raw', parsed, {'uuid_hex': uuid_hex, 'name': skel.get('name', ''), 'type': 'SKEL'}, require_store=require_store, prefix=f'{skel.get("index", len(exported_skel)):03d}__{skel.get("name", "skel")}')
        exported['name'] = skel.get('name', '')
        exported['char_skel_index'] = skel.get('index', -1)
        if exported.get('raw_file'):
            exported['raw_file'] = rel(package_dir, exported['raw_file'])
            exported['summary_file'] = rel(package_dir, exported['summary_file'])
        if exported.get('resolved') and selected_skel_summary is None and exported.get('summary', {}).get('type') == 'SKEL':
            selected_skel_summary = exported.get('summary')
        exported.pop('summary', None)
        exported_skel.append(exported)
    if selected_skel_summary is not None:
        summary = merge_skel_into_model_summary(summary, selected_skel_summary)
    skeleton_summary_path = write_json(skeleton_dir / 'model_skeleton_summary.json', summary)
    animation_refs = list(animation_refs or []) + detected_anims
    seen_anim = set()
    exported_anim = []
    for anim in animation_refs:
        uuid_hex = anim.get('uuid_hex', '')
        if not uuid_hex or uuid_hex == ZERO_UUID or uuid_hex in seen_anim:
            continue
        seen_anim.add(uuid_hex)
        exported = export_skeletal_asset(animations_dir / 'raw', parsed, {'uuid_hex': uuid_hex, 'name': anim.get('name', ''), 'type': anim.get('type', 'ANIM')}, require_store=require_store, prefix=f'{anim.get("index", len(exported_anim)):03d}__{anim.get("name", "anim")}')
        exported['name'] = anim.get('name', '')
        exported['char_anim_index'] = anim.get('index', -1)
        if exported.get('raw_file'):
            exported['raw_file'] = rel(package_dir, exported['raw_file'])
            exported['summary_file'] = rel(package_dir, exported['summary_file'])
        exported.pop('summary', None)
        exported_anim.append(exported)
    anim_manifest_path = write_json(animations_dir / 'animation_manifest.json', {'animations': exported_anim})
    script_path = blender_dir / 'import_model_package.py'
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(blender_model_import_script(), encoding='utf-8', newline='\n')
    readme = [
        'Blender:',
        '1. Blender öffnen.',
        '2. Scripting öffnen.',
        '3. blender/import_model_package.py ausführen.',
        '',
        'Status:',
        '- OBJ/MTL wird importiert.',
        '- Wenn SKEL vorhanden ist, werden echte Bone-Namen aus SKEL verwendet.',
        '- Die Armature ist aktuell noch eine sichere Root-Hierarchie ohne echte Bind-Pose.',
        '- ANIM-Dateien werden als Actions mit Source-Metadaten angelegt, solange das echte ANIM-Keyframe-Layout noch nicht vollständig bekannt ist.'
    ]
    readme_path = blender_dir / 'README.txt'
    readme_path.write_text('\n'.join(readme), encoding='utf-8', newline='\n')
    return {
        'skeleton_summary_file': rel(package_dir, skeleton_summary_path),
        'animation_manifest_file': rel(package_dir, anim_manifest_path),
        'blender_script_file': rel(package_dir, script_path),
        'blender_readme_file': rel(package_dir, readme_path),
        'bone_count': summary.get('bone_count_from_skhd', 0),
        'skin_component_count': len(summary.get('skin_components', [])),
        'linked_skeleton_count': len([x for x in exported_skel if x.get('resolved')]),
        'animation_count': len(exported_anim),
        'resolved_animation_count': len([x for x in exported_anim if x.get('resolved')]),
        'bone_names_from_skel': summary.get('bone_names_from_skel', False),
        'linked_skeletons': exported_skel,
        'animations': exported_anim
    }

def write_char_blender_helper(package_dir, manifest):
    package_dir = Path(package_dir)
    blender_dir = package_dir / 'blender'
    blender_dir.mkdir(parents=True, exist_ok=True)
    script_path = blender_dir / 'import_char_package.py'
    script_path.write_text(blender_char_import_script(), encoding='utf-8', newline='\n')
    readme_path = blender_dir / 'README.txt'
    readme = [
        'Blender:',
        '1. Blender öffnen.',
        '2. Scripting öffnen.',
        '3. blender/import_char_package.py ausführen.',
        '',
        'Status:',
        '- Alle im CHAR-Paket vorhandenen Modellpakete werden als OBJ importiert.',
        '- Pro Modell wird eine Armature erzeugt.',
        '- Wenn SKEL vorhanden ist, nutzt die Armature echte Bone-Namen aus SKEL.',
        '- Aufgelöste ANIMs werden als leere Actions mit Source-Metadaten angelegt.',
        '- Echte Parent-Struktur, Bind-Pose und Keyframes folgen im ANIM/SKEL-Ausbau.'
    ]
    readme_path.write_text('\n'.join(readme), encoding='utf-8', newline='\n')
    return {'blender_script_file': rel(package_dir, script_path), 'blender_readme_file': rel(package_dir, readme_path)}
