from pathlib import Path
import json
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes, kind_to_ext, format_uuid_hex

ZERO_UUID = '00000000000000000000000000000000'
SKELETAL_REF_TYPES = {'SKEL', 'ANIM'}

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def is_rfrm_type(asset, typ):
    return len(asset) >= 32 and asset[:4] == b'RFRM' and tag4(asset, 20) == typ

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
        parent = index - 1 if index > 0 else -1
        inferred_bones.append({'index': index, 'name': f'bone_{index:03d}', 'parent_index': parent, 'matrix': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, index * 0.03, 0, 0, 0, 1]})
    return {
        'model_type': typ,
        'bone_count_from_skhd': bone_count,
        'has_skeleton_header': 'SKHD' in chunks,
        'vbufs': vbufs,
        'skin_components': skin_components,
        'inferred_bones': inferred_bones,
        'note': 'SKHD liefert aktuell sicher die Bone-Anzahl. Echte Bone-Namen, Bind-Pose und Hierarchie brauchen einen echten SKEL/ANIM-Sample oder weitere Formatbestätigung.'
    }

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
    rec.update({'resolved': entry is not None and asset is not None, 'entry_type': entry.get('type') if entry else '', 'entry_name': entry.get('display_name') or entry.get('name') or '' if entry else '', 'source_kind': source, 'source_path': source_path, 'raw_file': '', 'summary_file': ''})
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
        first = data.edit_bones[0]
        first.name = bones[0].get('name', 'bone_000')
        first.head = (0, 0, 0)
        first.tail = (0, 0, 0.03)
        created = {0: first}
        for bone in bones[1:]:
            idx = int(bone.get('index', len(created)))
            parent_idx = int(bone.get('parent_index', idx - 1))
            eb = data.edit_bones.new(bone.get('name', f'bone_{idx:03d}'))
            eb.head = (0, 0, idx * 0.03)
            eb.tail = (0, 0, (idx + 1) * 0.03)
            parent = created.get(parent_idx)
            if parent is not None:
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
            first = arm.data.edit_bones[0]
            first.name = bones[0].get('name', 'bone_000')
            first.head = (0, 0, 0)
            first.tail = (0, 0, 0.03)
            created = {0: first}
            for bone in bones[1:]:
                idx = int(bone.get('index', len(created)))
                parent_idx = int(bone.get('parent_index', idx - 1))
                eb = arm.data.edit_bones.new(bone.get('name', f'bone_{idx:03d}'))
                eb.head = (0, 0, idx * 0.03)
                eb.tail = (0, 0, (idx + 1) * 0.03)
                parent = created.get(parent_idx)
                if parent is not None:
                    eb.parent = parent
                created[idx] = eb
            bpy.ops.object.mode_set(mode='OBJECT')
for anim in manifest.get('animations', []):
    if anim.get('resolved'):
        action = bpy.data.actions.new(name=anim.get('name') or anim.get('uuid_hex') or 'ANIM')
        action['source_uuid'] = anim.get('uuid_hex', '')
        action['source_file'] = anim.get('file', '')
'''

def export_model_skeletal_sidecar(parsed, entry, package_dir, require_store=None, animation_refs=None):
    package_dir = Path(package_dir)
    asset = get_entry_asset(parsed, entry)
    skeleton_dir = package_dir / 'skeleton'
    animations_dir = package_dir / 'animations'
    blender_dir = package_dir / 'blender'
    summary = parse_model_skin_summary(asset)
    summary.update({'entry_uuid_hex': entry['uuid_hex'], 'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'], 'entry_type': entry['type']})
    skeleton_summary_path = write_json(skeleton_dir / 'model_skeleton_summary.json', summary)
    refs = find_known_uuid_refs(asset, parsed, require_store, wanted_types=SKELETAL_REF_TYPES)
    exported_skel = []
    detected_anims = []
    for ref in refs:
        if ref.get('entry_type') == 'SKEL':
            exported = export_skeletal_asset(skeleton_dir / 'raw', parsed, {'uuid_hex': ref['uuid_hex'], 'name': ref.get('entry_name', ''), 'type': 'SKEL'}, require_store=require_store, prefix='linked_skel')
            if exported.get('raw_file'):
                exported['raw_file'] = rel(package_dir, exported['raw_file'])
                exported['summary_file'] = rel(package_dir, exported['summary_file'])
            exported_skel.append(exported)
        elif ref.get('entry_type') == 'ANIM':
            detected_anims.append({'uuid_hex': ref['uuid_hex'], 'name': ref.get('entry_name', ''), 'type': 'ANIM'})
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
        '- SKHD-Bone-Anzahl wird als Platzhalter-Armature angelegt.',
        '- ANIM-Dateien werden als Actions mit Source-Metadaten angelegt, solange das echte ANIM-Keyframe-Layout noch nicht vollständig bekannt ist.',
        '- Echte Bone-Hierarchie, Bind-Pose und Keyframes brauchen echte SKEL/ANIM-Dateien zur Formatbestätigung.'
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
        '- Pro Modell wird die SKHD-Bone-Anzahl als Platzhalter-Armature erzeugt.',
        '- Aufgelöste ANIMs werden als leere Actions mit Source-Metadaten angelegt.',
        '- Das ist absichtlich noch kein echter Animations-Rebuild, solange das SKEL/ANIM-Layout nicht vollständig bestätigt ist.'
    ]
    readme_path.write_text('\n'.join(readme), encoding='utf-8', newline='\n')
    return {'blender_script_file': rel(package_dir, script_path), 'blender_readme_file': rel(package_dir, readme_path)}
