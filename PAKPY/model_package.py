from pathlib import Path
import json
from pak_core import PakError, safe_name, sha1_bytes, get_entry_asset, rebuild_pak
from pak_extract import export_model_entry_as_obj, export_txtr_bytes_as_png, make_material_texture_png_name, get_mtl_slot_for_ref_tag
from txtr_repack import png_to_txtr_asset, can_repack_txtr_asset

def _package_dir_name(entry):
    base = entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    return f'{safe_name(base)}_{entry["type"].lower()}_repack'

def _resolve_txtr_asset(parsed, ref, require_store=None):
    if require_store is not None:
        return require_store.resolve_asset(parsed, ref['uuid_hex'])
    txtr_entry = parsed.get('uuid_to_entry', {}).get(ref['uuid_hex'])
    if txtr_entry is None:
        return None, None, ''
    return get_entry_asset(parsed, txtr_entry), txtr_entry, 'pak'

def _raw_txtr_name(material, ref, txtr_entry):
    return make_material_texture_png_name(material, ref, txtr_entry).rsplit('.', 1)[0] + '.txtr.bin'

def _strict_texture_slots(parsed, entry, package_dir, require_store=None):
    material_texture_map = {}
    textures = []
    editable_count = 0
    raw_only_count = 0
    for material in entry.get('model_materials', []):
        slot_map = {}
        for ref in material.get('txtr_refs', []):
            raw_asset, txtr_entry, source = _resolve_txtr_asset(parsed, ref, require_store)
            if txtr_entry is None:
                textures.append({
                    'missing': True,
                    'txtr_entry_index': -1,
                    'txtr_uuid_hex': ref['uuid_hex'],
                    'txtr_name': ref['uuid_hex'],
                    'material_index': material['index'],
                    'material_name': material['name'],
                    'ref_tag': ref['tag'],
                    'mtl_slot': get_mtl_slot_for_ref_tag(ref['tag']),
                    'png_name': '',
                    'png_sha1': '',
                    'raw_name': '',
                    'raw_sha1': '',
                    'editable_png': False,
                    'export_error': 'TXTR weder im aktuellen PAK noch in den requireten Dateien gefunden',
                    'source_kind': '',
                    'source_path': ''
                })
                continue
            if txtr_entry.get('type') != 'TXTR':
                textures.append({
                    'missing': False,
                    'txtr_entry_index': txtr_entry['index'] if source == 'pak' else -1,
                    'txtr_uuid_hex': txtr_entry['uuid_hex'],
                    'txtr_name': txtr_entry.get('display_name') or txtr_entry.get('name') or txtr_entry['uuid_hex'],
                    'material_index': material['index'],
                    'material_name': material['name'],
                    'ref_tag': ref['tag'],
                    'mtl_slot': get_mtl_slot_for_ref_tag(ref['tag']),
                    'png_name': '',
                    'png_sha1': '',
                    'raw_name': '',
                    'raw_sha1': '',
                    'editable_png': False,
                    'export_error': f'Referenz ist kein TXTR sondern {txtr_entry.get("type") or "unbekannt"}',
                    'source_kind': source,
                    'source_path': require_store.get_required_source(ref['uuid_hex']) if source == 'require' and require_store is not None else ''
                })
                continue
            raw_name = _raw_txtr_name(material, ref, txtr_entry)
            raw_path = package_dir / raw_name
            raw_path.write_bytes(raw_asset)
            png_name = make_material_texture_png_name(material, ref, txtr_entry)
            png_path = package_dir / png_name
            export_error = ''
            try:
                export_txtr_bytes_as_png(raw_asset, png_path)
            except Exception as e:
                export_error = str(e)
            png_exported = export_error == '' and png_path.is_file()
            editable_png = png_exported and can_repack_txtr_asset(raw_asset)
            if png_exported:
                slot_name = get_mtl_slot_for_ref_tag(ref['tag'])
                if slot_name and slot_name not in slot_map:
                    slot_map[slot_name] = png_name
            if png_exported and not editable_png:
                export_error = 'PNG-Export ok, aber Rückbau für dieses TXTR ist lokal nicht verfügbar'
            if editable_png:
                editable_count += 1
            else:
                raw_only_count += 1
            textures.append({
                'missing': False,
                'txtr_entry_index': txtr_entry['index'] if source == 'pak' else -1,
                'txtr_uuid_hex': txtr_entry['uuid_hex'],
                'txtr_name': txtr_entry.get('display_name') or txtr_entry.get('name') or txtr_entry['uuid_hex'],
                'material_index': material['index'],
                'material_name': material['name'],
                'ref_tag': ref['tag'],
                'mtl_slot': get_mtl_slot_for_ref_tag(ref['tag']),
                'png_name': png_name if png_exported else '',
                'png_sha1': sha1_bytes(png_path.read_bytes()) if png_exported else '',
                'raw_name': raw_name,
                'raw_sha1': sha1_bytes(raw_asset),
                'editable_png': editable_png,
                'export_error': export_error or '',
                'source_kind': source,
                'source_path': require_store.get_required_source(ref['uuid_hex']) if source == 'require' and require_store is not None else ''
            })
        if slot_map:
            material_texture_map[material['index']] = dict(slot_map)
            material_texture_map[str(material['name'])] = dict(slot_map)
    return material_texture_map, textures, editable_count, raw_only_count

def _write_report(package_dir, manifest):
    lines = []
    lines.append(f'Modell: {manifest["entry_name"]}')
    lines.append(f'Typ: {manifest["entry_type"]}')
    lines.append(f'OBJ: {manifest["obj_name"]}')
    lines.append(f'MTL: {manifest["mtl_name"]}')
    lines.append(f'Bearbeitbare PNGs: {manifest["editable_png_count"]}')
    lines.append(f'Nur Roh-Sicherung: {manifest["raw_only_count"]}')
    lines.append('')
    lines.append('Texturen:')
    for item in manifest.get('textures', []):
        status = 'PNG+RAW' if item.get('editable_png') else 'RAW'
        if item.get('missing'):
            status = 'FEHLT'
        line = f'- {item["material_name"]} | {item["ref_tag"]} | {item["txtr_uuid_hex"]} | {status}'
        if item.get('png_name'):
            line += f' | {item["png_name"]}'
        if item.get('raw_name'):
            line += f' | {item["raw_name"]}'
        if item.get('export_error'):
            line += f' | {item["export_error"]}'
        lines.append(line)
    (package_dir / 'repack_report.txt').write_text('\n'.join(lines), encoding='utf-8')

def export_model_package(parsed, entry, out_dir, require_store=None):
    if entry['type'] not in ('CMDL', 'SMDL', 'WMDL'):
        raise PakError('Modellpaket geht nur bei CMDL, SMDL oder WMDL')
    out_dir = Path(out_dir)
    package_dir = out_dir / _package_dir_name(entry)
    package_dir.mkdir(parents=True, exist_ok=True)
    material_texture_map, textures, editable_count, raw_only_count = _strict_texture_slots(parsed, entry, package_dir, require_store=require_store)
    result = export_model_entry_as_obj(parsed, entry, package_dir, write_mtl=True, material_texture_map=material_texture_map)
    obj_path = Path(result['obj_path']) if result.get('obj_path') else None
    mtl_path = Path(result['mtl_path']) if result.get('mtl_path') else None
    manifest = {
        'version': 2,
        'source_pak': Path(parsed['path']).name,
        'entry_index': entry['index'],
        'entry_type': entry['type'],
        'entry_uuid_hex': entry['uuid_hex'],
        'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'],
        'obj_name': obj_path.name if obj_path else '',
        'obj_sha1': sha1_bytes(obj_path.read_bytes()) if obj_path and obj_path.is_file() else '',
        'mtl_name': mtl_path.name if mtl_path else '',
        'mtl_sha1': sha1_bytes(mtl_path.read_bytes()) if mtl_path and mtl_path.is_file() else '',
        'editable_png_count': editable_count,
        'raw_only_count': raw_only_count,
        'textures': textures
    }
    manifest_path = package_dir / 'repack_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    _write_report(package_dir, manifest)
    return {
        'package_dir': str(package_dir),
        'manifest_path': str(manifest_path),
        'obj_path': str(obj_path) if obj_path else '',
        'mtl_path': str(mtl_path) if mtl_path else '',
        'texture_count': len(textures),
        'editable_png_count': editable_count,
        'raw_only_count': raw_only_count
    }

def rebuild_model_package_from_folder(parsed, folder, out_path):
    folder = Path(folder)
    manifest_path = folder / 'repack_manifest.json'
    if not manifest_path.is_file():
        raise PakError('repack_manifest.json fehlt')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entry_index = manifest.get('entry_index')
    entry_uuid_hex = manifest.get('entry_uuid_hex')
    if entry_index is None or entry_index >= len(parsed['entries']):
        raise PakError('Manifest verweist auf einen ungültigen Modell-Eintrag')
    model_entry = parsed['entries'][entry_index]
    if model_entry['uuid_hex'] != entry_uuid_hex:
        raise PakError('Manifest passt nicht zum aktuell geladenen PAK')
    obj_name = manifest.get('obj_name', '')
    obj_sha1 = manifest.get('obj_sha1', '')
    if obj_name:
        obj_path = folder / obj_name
        if obj_path.is_file() and obj_sha1 and sha1_bytes(obj_path.read_bytes()) != obj_sha1:
            raise PakError('OBJ wurde geändert, aber der Mesh-Rückweg ist noch nicht drin')
    replacements = {}
    changed = []
    for item in manifest.get('textures', []):
        txtr_index = item.get('txtr_entry_index', -1)
        if txtr_index < 0 or txtr_index >= len(parsed['entries']):
            continue
        txtr_entry = parsed['entries'][txtr_index]
        if txtr_entry['uuid_hex'] != item.get('txtr_uuid_hex') or txtr_entry['type'] != 'TXTR':
            raise PakError(f'TXTR-Verknüpfung passt nicht mehr: {item.get("txtr_uuid_hex", "unbekannt")}')
        raw_name = item.get('raw_name', '')
        raw_sha1 = item.get('raw_sha1', '')
        if raw_name:
            raw_path = folder / raw_name
            if raw_path.is_file():
                new_raw_sha1 = sha1_bytes(raw_path.read_bytes())
                if raw_sha1 and new_raw_sha1 != raw_sha1:
                    replacements[txtr_index] = {'asset_bytes': raw_path.read_bytes()}
                    changed.append(raw_name)
                    continue
        png_name = item.get('png_name', '')
        png_sha1 = item.get('png_sha1', '')
        if png_name:
            png_path = folder / png_name
            if png_path.is_file():
                new_png_sha1 = sha1_bytes(png_path.read_bytes())
                if png_sha1 and new_png_sha1 != png_sha1:
                    original_asset = get_entry_asset(parsed, txtr_entry)
                    new_asset = png_to_txtr_asset(original_asset, png_path)
                    replacements[txtr_index] = {'asset_bytes': new_asset}
                    changed.append(png_name)
    if not replacements:
        raise PakError('Keine geänderten PNGs oder TXTR-Rohdateien gefunden')
    built = rebuild_pak(parsed, replacements, out_path)
    return {
        'out_path': built,
        'changed_count': len(changed),
        'changed_files': changed
    }
