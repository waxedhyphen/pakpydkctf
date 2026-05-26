import json
from pathlib import Path
import char_codec
import char_gui_patch
from pak_core import get_entry_asset, safe_name, kind_to_ext, sha1_bytes
from skeletal_codec import find_known_uuid_refs, parse_skel_asset

ZERO_UUID = '00000000000000000000000000000000'

def _rel(root, path):
    return str(Path(path).relative_to(root)).replace('\\', '/')

def _write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8', newline='\n')
    return path

def _write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path

def _source_name(entry):
    base = entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    return safe_name(base) + kind_to_ext(entry['type'])

def _missing_text(kind, item, uuid_hex):
    lines = [f'{kind} nicht gefunden', f'UUID: {char_codec.format_uuid_hex(uuid_hex)}']
    for key, value in item.items():
        if key == 'extra_hex':
            continue
        if value not in ('', None):
            lines.append(f'{key}: {value}')
    return '\n'.join(lines) + '\n'

def _read_model_package_manifest(package_dir):
    path = Path(package_dir) / 'repack_manifest.json'
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding='utf-8'))

def _join_package_path(package_rel, inner_rel):
    if not package_rel or not inner_rel:
        return ''
    return str(Path(package_rel) / inner_rel).replace('\\', '/')

def _write_report(path, manifest):
    lines = []
    lines.append(f'CHAR: {manifest["char_name"]}')
    lines.append(f'CHAR-UUID: {char_codec.format_uuid_hex(manifest["char_uuid_hex"])}')
    lines.append('')
    lines.append(f'Modelle: {manifest["resolved_model_count"]}/{manifest["model_count"]} als Modellpaket exportiert')
    for item in manifest['models']:
        status = 'OK' if item.get('resolved') and item.get('model_package_dir') else 'FEHLT'
        lines.append(f'- {status} | #{item["index"]} {item["slot_name"]} | {item.get("entry_type") or "unbekannt"} | {char_codec.format_uuid_hex(item["uuid_hex"])}')
        if item.get('obj'):
            lines.append(f'  OBJ: {item["obj"]}')
        if item.get('mtl'):
            lines.append(f'  MTL: {item["mtl"]}')
        if item.get('dae'):
            lines.append(f'  DAE: {item["dae"]}')
        if item.get('experimental_skeletal_dae'):
            lines.append(f'  Experimental Skeletal DAE: {item["experimental_skeletal_dae"]}')
        if item.get('model_debug_json'):
            lines.append(f'  Debug: {item["model_debug_json"]}')
        if item.get('model_package_error'):
            lines.append(f'  Fehler: {item["model_package_error"]}')
    lines.append('')
    lines.append(f'Skeletons: {len(manifest.get("skeletons", []))}')
    for item in manifest.get('skeletons', []):
        status = 'OK' if item.get('resolved') else 'FEHLT'
        lines.append(f'- {status} | {item.get("name", "")} | {char_codec.format_uuid_hex(item["uuid_hex"])}')
        if item.get('summary_file'):
            lines.append(f'  Analyse: {item["summary_file"]}')
    lines.append('')
    lines.append(f'Animationen: {manifest["resolved_animation_count"]}/{manifest["animation_count"]} aufgelöst')
    if manifest.get('missing'):
        lines.append('')
        lines.append('Fehlende Referenzen:')
        for item in manifest['missing']:
            lines.append(f'- {item["kind"]} | {item["name"]} | {char_codec.format_uuid_hex(item["uuid_hex"])}')
    _write_text(path, '\n'.join(lines))

def _collect_skeleton_refs(asset, parsed, require_store):
    refs = []
    for index, ref in enumerate(find_known_uuid_refs(asset, parsed, require_store, wanted_types={'SKEL'})):
        if all(item['uuid_hex'] != ref['uuid_hex'] for item in refs):
            refs.append({'index': len(refs), 'uuid_hex': ref['uuid_hex'], 'name': ref.get('entry_name', ''), 'type': 'SKEL', 'offset': ref.get('offset', 0), 'source_kind': ref.get('source_kind', ''), 'source_path': ref.get('source_path', '')})
    return refs

def _export_skeleton_sources(package_dir, parsed, skeleton_refs, require_store):
    skeleton_items = []
    for skel in skeleton_refs:
        asset_data, ref_entry, source, source_path = char_codec._resolve_ref(parsed, skel['uuid_hex'], require_store)
        item = dict(skel)
        item.update({'resolved': ref_entry is not None and asset_data is not None, 'source_kind': source or item.get('source_kind', ''), 'source_path': source_path or item.get('source_path', ''), 'source_file': '', 'summary_file': '', 'summary_error': ''})
        if ref_entry is not None and asset_data is not None:
            skel_path = _write_bytes(package_dir / 'source' / 'skel' / (safe_name(f'{skel["index"]:03d}__{skel.get("name", "skel")}__{skel["uuid_hex"]}') + kind_to_ext(ref_entry['type'])), asset_data)
            item['source_file'] = _rel(package_dir, skel_path)
            summary_path = skel_path.with_suffix(skel_path.suffix + '.json')
            try:
                summary = parse_skel_asset(asset_data)
                summary.update({'uuid_hex': skel['uuid_hex'], 'entry_name': ref_entry.get('display_name') or ref_entry.get('name') or ''})
                summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
            except Exception as e:
                item['summary_error'] = str(e)
                summary_path.write_text(json.dumps({'error': str(e), 'uuid_hex': skel['uuid_hex']}, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
            item['summary_file'] = _rel(package_dir, summary_path)
        skeleton_items.append(item)
    return skeleton_items

def export_clean_char_package(parsed, entry, out_dir, require_store=None):
    if entry.get('type') != 'CHAR':
        raise char_codec.PakError('CHAR-Paket geht nur bei CHAR')
    asset = get_entry_asset(parsed, entry)
    info = char_codec.parse_char_asset(asset)
    base_name = info.get('name') or entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    package_dir = Path(out_dir) / f'{safe_name(base_name)}_character_package'
    package_dir.mkdir(parents=True, exist_ok=True)
    char_source = _write_bytes(package_dir / 'source' / 'char' / _source_name(entry), asset)
    char_analysis_path = package_dir / 'debug' / 'char_parse.json'
    char_analysis_path.parent.mkdir(parents=True, exist_ok=True)
    char_analysis_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    animation_refs = [item for item in info.get('animations', []) if item.get('uuid_hex') and item.get('uuid_hex') != ZERO_UUID]
    skeleton_refs = _collect_skeleton_refs(asset, parsed, require_store)
    skeleton_items = _export_skeleton_sources(package_dir, parsed, skeleton_refs, require_store)
    models = []
    missing = []
    resolved_model_count = 0
    for model in info.get('model_slots', []):
        uuid_hex = model['uuid_hex']
        asset_data, ref_entry, source, source_path = char_codec._resolve_ref(parsed, uuid_hex, require_store)
        rec = dict(model)
        rec.update({'resolved': ref_entry is not None and asset_data is not None, 'source_kind': source, 'source_path': source_path, 'entry_type': ref_entry.get('type') if ref_entry else '', 'model_package_dir': '', 'obj': '', 'mtl': '', 'dae': '', 'experimental_skeletal_dae': '', 'model_debug_json': '', 'skeleton_debug_json': '', 'model_package_error': ''})
        if ref_entry is not None and asset_data is not None and ref_entry.get('type') in char_codec.MODEL_TYPES:
            try:
                from model_package import export_model_package
                model_parsed = parsed if source == 'pak' else char_codec._required_parsed_for_uuid(require_store, uuid_hex)
                if model_parsed is None:
                    raise char_codec.PakError('Kein Parsed-Kontext für Modellpaket verfügbar')
                result = export_model_package(model_parsed, ref_entry, package_dir / 'models', require_store=require_store, animation_refs=animation_refs, skeleton_refs=skeleton_refs)
                resolved_model_count += 1
                rec['model_package_dir'] = _rel(package_dir, result['package_dir'])
                model_manifest = _read_model_package_manifest(result['package_dir'])
                rec['obj'] = _join_package_path(rec['model_package_dir'], model_manifest.get('obj', ''))
                rec['mtl'] = _join_package_path(rec['model_package_dir'], model_manifest.get('mtl', ''))
                rec['dae'] = _join_package_path(rec['model_package_dir'], model_manifest.get('dae', ''))
                rec['experimental_skeletal_dae'] = _join_package_path(rec['model_package_dir'], model_manifest.get('experimental_skeletal_dae', ''))
                rec['model_debug_json'] = _join_package_path(rec['model_package_dir'], model_manifest.get('model_debug_json', ''))
                rec['skeleton_debug_json'] = _join_package_path(rec['model_package_dir'], model_manifest.get('skeleton_debug_json', ''))
                rec['model_package_error'] = model_manifest.get('experimental_skeletal_error', '')
            except Exception as e:
                rec['model_package_error'] = str(e)
                missing_path = _write_text(package_dir / 'missing' / 'models' / (safe_name(f'{model["index"]:03d}__{model["slot_name"]}__{uuid_hex}') + '.missing.txt'), _missing_text('Modell-Export', model, uuid_hex) + f'Fehler: {e}\n')
                rec['missing_file'] = _rel(package_dir, missing_path)
                missing.append({'kind': 'model', 'uuid_hex': uuid_hex, 'name': model.get('slot_name', ''), 'file': rec['missing_file']})
        else:
            missing_path = _write_text(package_dir / 'missing' / 'models' / (safe_name(f'{model["index"]:03d}__{model["slot_name"]}__{uuid_hex}') + '.missing.txt'), _missing_text('Modell-Ref', model, uuid_hex))
            rec['missing_file'] = _rel(package_dir, missing_path)
            missing.append({'kind': 'model', 'uuid_hex': uuid_hex, 'name': model.get('slot_name', ''), 'file': rec['missing_file']})
        models.append(rec)
    animations = []
    resolved_animation_count = 0
    for anim in info.get('animations', []):
        uuid_hex = anim['uuid_hex']
        rec = dict(anim)
        rec.update({'resolved': False, 'source_kind': '', 'source_path': '', 'entry_type': '', 'source_file': ''})
        if uuid_hex and uuid_hex != ZERO_UUID:
            asset_data, ref_entry, source, source_path = char_codec._resolve_ref(parsed, uuid_hex, require_store)
            rec.update({'resolved': ref_entry is not None and asset_data is not None, 'source_kind': source, 'source_path': source_path, 'entry_type': ref_entry.get('type') if ref_entry else ''})
            if ref_entry is not None and asset_data is not None:
                resolved_animation_count += 1
                anim_path = _write_bytes(package_dir / 'source' / 'anim' / (safe_name(f'{anim["index"]:03d}__{anim["name"]}__{uuid_hex}') + kind_to_ext(ref_entry['type'])), asset_data)
                rec['source_file'] = _rel(package_dir, anim_path)
            else:
                missing_path = _write_text(package_dir / 'missing' / 'animations' / (safe_name(f'{anim["index"]:03d}__{anim["name"]}__{uuid_hex}') + '.missing.txt'), _missing_text('Animation-Ref', anim, uuid_hex))
                rec['missing_file'] = _rel(package_dir, missing_path)
                missing.append({'kind': 'animation', 'uuid_hex': uuid_hex, 'name': anim.get('name', ''), 'file': rec['missing_file']})
        animations.append(rec)
    manifest = {'version': 3, 'source_pak': Path(parsed['path']).name, 'entry_index': entry['index'], 'entry_type': entry['type'], 'entry_uuid_hex': entry['uuid_hex'], 'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'], 'char_name': info['name'], 'char_uuid_hex': info['uuid_hex'], 'source_char': _rel(package_dir, char_source), 'source_char_sha1': sha1_bytes(char_source.read_bytes()), 'char_parse_json': _rel(package_dir, char_analysis_path), 'model_count': len(models), 'resolved_model_count': resolved_model_count, 'animation_count': len(animations), 'resolved_animation_count': resolved_animation_count, 'skeletons': skeleton_items, 'models': models, 'animations': animations, 'missing': missing, 'missing_count': len(missing), 'animation_lookup_hashes': info.get('animation_lookup_hashes', []), 'tail_offset': info.get('tail_offset', 0), 'tail_size': info.get('tail_size', 0), 'tail_sha1': info.get('tail_sha1', '')}
    manifest_path = package_dir / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    report_path = package_dir / 'report.txt'
    _write_report(report_path, manifest)
    return {'package_dir': str(package_dir), 'manifest_path': str(manifest_path), 'report_path': str(report_path), 'model_count': len(models), 'resolved_model_count': resolved_model_count, 'animation_count': len(animations), 'resolved_animation_count': resolved_animation_count, 'resource_count': len(skeleton_items), 'missing_count': len(missing)}

def install(App):
    def export_char_package(parsed, entry, out_dir, require_store=None):
        return export_clean_char_package(parsed, entry, out_dir, require_store=require_store)
    char_gui_patch.export_char_package = export_char_package
