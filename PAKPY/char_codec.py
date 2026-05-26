from pathlib import Path
import json
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes, kind_to_ext, format_uuid_hex

MODEL_TYPES = {'CMDL', 'SMDL', 'WMDL'}
ZERO_UUID = '00000000000000000000000000000000'

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def is_char_asset(asset):
    return len(asset) >= 32 and asset[:4] == b'RFRM' and tag4(asset, 20) == 'CHAR'

def _decode_name(raw):
    return raw.split(b'\x00', 1)[0].decode('utf-8', 'replace')

def _looks_like_name(raw):
    if not raw:
        return False
    useful = raw.split(b'\x00', 1)[0]
    if not useful:
        return False
    for b in useful:
        if b < 32 or b > 126:
            return False
    return any((65 <= b <= 90) or (97 <= b <= 122) or (48 <= b <= 57) for b in useful)

def _find_first_name_off(asset):
    limit = min(len(asset) - 4, 128)
    for off in range(32, limit):
        size = be32(asset, off)
        if 1 <= size <= 160 and off + 4 + size <= len(asset):
            raw = asset[off+4:off+4+size]
            if _looks_like_name(raw):
                return off
    raise PakError('CHAR-Name konnte nicht gefunden werden')

def _read_name(asset, p, label):
    if p + 4 > len(asset):
        raise PakError(f'{label}: Namenslänge fehlt')
    size = be32(asset, p)
    p += 4
    if size < 0 or size > 4096 or p + size > len(asset):
        raise PakError(f'{label}: Name ist abgeschnitten')
    return _decode_name(asset[p:p+size]), size, p + size

def _read_uuid(asset, p, label):
    if p + 16 > len(asset):
        raise PakError(f'{label}: UUID ist abgeschnitten')
    return asset[p:p+16].hex(), p + 16

def _read_count(asset, p, label, limit):
    if p + 4 > len(asset):
        raise PakError(f'{label}: Zähler fehlt')
    count = be32(asset, p)
    if count > limit:
        raise PakError(f'{label}: Zähler wirkt ungültig ({count})')
    return count, p + 4

def parse_char_asset(asset):
    if not is_char_asset(asset):
        raise PakError('Keine CHAR-Ressource')
    name_off = _find_first_name_off(asset)
    info = {
        'header_prefix_hex': asset[32:name_off].hex(),
        'name_offset': name_off,
        'entry_type': 'CHAR',
        'name': '',
        'uuid_hex': '',
        'model_slots': [],
        'animations': [],
        'animation_lookup_hashes': [],
        'tail_offset': 0,
        'tail_size': 0,
        'tail_sha1': ''
    }
    p = name_off
    name, name_size, p = _read_name(asset, p, 'CHAR')
    uuid_hex, p = _read_uuid(asset, p, 'CHAR')
    info['name'] = name
    info['name_size'] = name_size
    info['uuid_hex'] = uuid_hex
    model_count, p = _read_count(asset, p, 'CHAR-Modelle', 1024)
    for index in range(model_count):
        slot_name, slot_name_size, p = _read_name(asset, p, f'CHAR-Modell #{index}')
        model_uuid, p = _read_uuid(asset, p, f'CHAR-Modell #{index}')
        if p + 24 > len(asset):
            raise PakError(f'CHAR-Modell #{index}: Zusatzdaten abgeschnitten')
        extra = asset[p:p+24]
        p += 24
        info['model_slots'].append({
            'index': index,
            'slot_name': slot_name,
            'slot_name_size': slot_name_size,
            'uuid_hex': model_uuid,
            'extra_hex': extra.hex()
        })
    animation_count, p = _read_count(asset, p, 'CHAR-Animationen', 20000)
    for index in range(animation_count):
        anim_name, anim_name_size, p = _read_name(asset, p, f'CHAR-Animation #{index}')
        anim_uuid, p = _read_uuid(asset, p, f'CHAR-Animation #{index}')
        if p + 4 > len(asset):
            raise PakError(f'CHAR-Animation #{index}: Typ fehlt')
        anim_type = tag4(asset, p)
        p += 4
        if p + 33 > len(asset):
            raise PakError(f'CHAR-Animation #{index}: Zusatzdaten abgeschnitten')
        extra = asset[p:p+33]
        p += 33
        info['animations'].append({
            'index': index,
            'name': anim_name,
            'name_size': anim_name_size,
            'uuid_hex': anim_uuid,
            'type': anim_type,
            'extra_hex': extra.hex()
        })
    info['animation_lookup_offset'] = p
    if p + 4 <= len(asset):
        lookup_count = be32(asset, p)
        if lookup_count <= 20000 and p + 4 + lookup_count * 16 <= len(asset):
            p += 4
            for index in range(lookup_count):
                info['animation_lookup_hashes'].append({'index': index, 'hex': asset[p:p+16].hex()})
                p += 16
    info['tail_offset'] = p
    info['tail_size'] = len(asset) - p
    info['tail_sha1'] = sha1_bytes(asset[p:]) if p <= len(asset) else ''
    return info

def _resolve_ref(parsed, uuid_hex, require_store=None):
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

def _required_parsed_for_uuid(require_store, uuid_hex):
    if require_store is None:
        return None
    source = require_store.get_required_source(uuid_hex)
    for item in getattr(require_store, 'required_paks', []):
        if item.get('path') == source:
            return item.get('parsed')
    return None

def _known_uuids(parsed, require_store=None):
    out = set(parsed.get('uuid_to_entry', {}).keys())
    if require_store is not None:
        out.update(getattr(require_store, 'required_entries_by_uuid', {}).keys())
    out.discard(ZERO_UUID)
    return out

def _find_uuid_occurrences(asset, uuid_set):
    refs = []
    for uuid_hex in sorted(uuid_set):
        try:
            needle = bytes.fromhex(uuid_hex)
        except Exception:
            continue
        start = 0
        while True:
            pos = asset.find(needle, start)
            if pos == -1:
                break
            refs.append({'uuid_hex': uuid_hex, 'offset': pos})
            start = pos + 1
    refs.sort(key=lambda item: (item['offset'], item['uuid_hex']))
    return refs

def _unique_path(path):
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

def _write_bytes(folder, filename, data):
    folder.mkdir(parents=True, exist_ok=True)
    path = _unique_path(folder / filename)
    path.write_bytes(data)
    return path

def _write_text(folder, filename, text):
    folder.mkdir(parents=True, exist_ok=True)
    path = _unique_path(folder / filename)
    path.write_text(text, encoding='utf-8', newline='\n')
    return path

def _rel(package_dir, path):
    return str(Path(path).relative_to(package_dir)).replace('\\', '/')

def _asset_file_name(prefix, entry, uuid_hex, fallback_type):
    typ = entry.get('type') if entry is not None else fallback_type
    name = ''
    if entry is not None:
        name = entry.get('display_name') or entry.get('name') or ''
    base = safe_name('__'.join(part for part in (prefix, typ, name, uuid_hex) if part))
    return base + kind_to_ext(typ)

def _missing_text(kind, item, uuid_hex):
    lines = [f'{kind} nicht gefunden', f'UUID: {format_uuid_hex(uuid_hex)}']
    for key, value in item.items():
        if key in ('extra_hex',):
            continue
        if value not in ('', None):
            lines.append(f'{key}: {value}')
    return '\n'.join(lines) + '\n'

def _export_model_package_if_possible(package_dir, parsed, model_entry, model_uuid, source, require_store):
    if model_entry is None or model_entry.get('type') not in MODEL_TYPES:
        return '', ''
    try:
        from model_package import export_model_package
        model_parsed = parsed if source == 'pak' else _required_parsed_for_uuid(require_store, model_uuid)
        if model_parsed is None:
            return '', 'Kein Parsed-Kontext für Modellpaket verfügbar'
        result = export_model_package(model_parsed, model_entry, package_dir / 'model_packages', require_store=require_store)
        return result.get('package_dir', ''), ''
    except Exception as e:
        return '', str(e)

def export_char_package(parsed, entry, out_dir, require_store=None):
    if entry.get('type') != 'CHAR':
        raise PakError('CHAR-Paket geht nur bei CHAR')
    asset = get_entry_asset(parsed, entry)
    info = parse_char_asset(asset)
    base_name = info.get('name') or entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    package_dir = Path(out_dir) / f'{safe_name(base_name)}_char_package'
    package_dir.mkdir(parents=True, exist_ok=True)
    raw_path = _write_bytes(package_dir / 'raw' / 'CHAR', _asset_file_name('character', entry, entry['uuid_hex'], 'CHAR'), asset)
    model_uuid_set = {item['uuid_hex'] for item in info['model_slots'] if item['uuid_hex'] != ZERO_UUID}
    anim_uuid_set = {item['uuid_hex'] for item in info['animations'] if item['uuid_hex'] != ZERO_UUID}
    excluded = set(model_uuid_set) | set(anim_uuid_set) | {entry['uuid_hex'], info.get('uuid_hex', '')}
    occurrences = _find_uuid_occurrences(asset, _known_uuids(parsed, require_store))
    models = []
    animations = []
    resources_by_uuid = {}
    missing = []
    resolved_model_count = 0
    resolved_animation_count = 0
    for model in info['model_slots']:
        uuid_hex = model['uuid_hex']
        asset_data, ref_entry, source, source_path = _resolve_ref(parsed, uuid_hex, require_store)
        rec = dict(model)
        rec.update({'resolved': ref_entry is not None and asset_data is not None, 'source_kind': source, 'source_path': source_path, 'entry_type': ref_entry.get('type') if ref_entry else '', 'file': '', 'model_package_dir': '', 'model_package_error': ''})
        if rec['resolved']:
            resolved_model_count += 1
            folder = package_dir / 'models' / rec['entry_type']
            prefix = f'{model["index"]:03d}__{model["slot_name"]}'
            file_path = _write_bytes(folder, _asset_file_name(prefix, ref_entry, uuid_hex, rec['entry_type']), asset_data)
            rec['file'] = _rel(package_dir, file_path)
            model_package_dir, model_package_error = _export_model_package_if_possible(package_dir, parsed, ref_entry, uuid_hex, source, require_store)
            rec['model_package_dir'] = _rel(package_dir, model_package_dir) if model_package_dir else ''
            rec['model_package_error'] = model_package_error
        else:
            missing_path = _write_text(package_dir / 'missing' / 'models', safe_name(f'{model["index"]:03d}__{model["slot_name"]}__{uuid_hex}') + '.missing.txt', _missing_text('Modell-Ref', model, uuid_hex))
            rec['missing_file'] = _rel(package_dir, missing_path)
            missing.append({'kind': 'model', 'uuid_hex': uuid_hex, 'name': model.get('slot_name', ''), 'file': rec['missing_file']})
        models.append(rec)
    for anim in info['animations']:
        uuid_hex = anim['uuid_hex']
        rec = dict(anim)
        rec.update({'resolved': False, 'source_kind': '', 'source_path': '', 'entry_type': '', 'file': ''})
        if uuid_hex != ZERO_UUID:
            asset_data, ref_entry, source, source_path = _resolve_ref(parsed, uuid_hex, require_store)
            rec.update({'resolved': ref_entry is not None and asset_data is not None, 'source_kind': source, 'source_path': source_path, 'entry_type': ref_entry.get('type') if ref_entry else ''})
            if rec['resolved']:
                resolved_animation_count += 1
                folder = package_dir / 'animations' / (rec['entry_type'] or anim['type'] or 'ANIM')
                prefix = f'{anim["index"]:03d}__{anim["name"]}'
                file_path = _write_bytes(folder, _asset_file_name(prefix, ref_entry, uuid_hex, rec['entry_type'] or anim['type'] or 'ANIM'), asset_data)
                rec['file'] = _rel(package_dir, file_path)
            else:
                missing_path = _write_text(package_dir / 'missing' / 'animations', safe_name(f'{anim["index"]:03d}__{anim["name"]}__{uuid_hex}') + '.missing.txt', _missing_text('Animation-Ref', anim, uuid_hex))
                rec['missing_file'] = _rel(package_dir, missing_path)
                missing.append({'kind': 'animation', 'uuid_hex': uuid_hex, 'name': anim.get('name', ''), 'file': rec['missing_file']})
        animations.append(rec)
    for occ in occurrences:
        uuid_hex = occ['uuid_hex']
        if uuid_hex in excluded or uuid_hex == ZERO_UUID:
            continue
        asset_data, ref_entry, source, source_path = _resolve_ref(parsed, uuid_hex, require_store)
        if ref_entry is None or asset_data is None:
            continue
        rec = resources_by_uuid.setdefault(uuid_hex, {'uuid_hex': uuid_hex, 'entry_type': ref_entry.get('type', ''), 'entry_name': ref_entry.get('display_name') or ref_entry.get('name') or '', 'source_kind': source, 'source_path': source_path, 'offsets': [], 'file': ''})
        rec['offsets'].append(occ['offset'])
    resources = []
    for uuid_hex, rec in sorted(resources_by_uuid.items(), key=lambda item: (item[1]['entry_type'], item[1]['entry_name'], item[0])):
        asset_data, ref_entry, source, source_path = _resolve_ref(parsed, uuid_hex, require_store)
        typ = rec['entry_type'] or 'UNKNOWN'
        folder = package_dir / 'resources' / typ
        prefix = f'{typ}__{rec["entry_name"]}'
        file_path = _write_bytes(folder, _asset_file_name(prefix, ref_entry, uuid_hex, typ), asset_data)
        rec['file'] = _rel(package_dir, file_path)
        resources.append(rec)
    refs_dir = package_dir / 'refs'
    refs_dir.mkdir(parents=True, exist_ok=True)
    occurrences_path = refs_dir / 'uuid_occurrences.json'
    occurrences_path.write_text(json.dumps(occurrences, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    manifest = {
        'version': 1,
        'source_pak': Path(parsed['path']).name,
        'entry_index': entry['index'],
        'entry_type': entry['type'],
        'entry_uuid_hex': entry['uuid_hex'],
        'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'],
        'char_name': info['name'],
        'char_uuid_hex': info['uuid_hex'],
        'raw_file': _rel(package_dir, raw_path),
        'model_count': len(models),
        'resolved_model_count': resolved_model_count,
        'animation_count': len(animations),
        'resolved_animation_count': resolved_animation_count,
        'resource_count': len(resources),
        'missing_count': len(missing),
        'models': models,
        'animations': animations,
        'resources': resources,
        'missing': missing,
        'animation_lookup_hashes': info['animation_lookup_hashes'],
        'tail_offset': info['tail_offset'],
        'tail_size': info['tail_size'],
        'tail_sha1': info['tail_sha1'],
        'uuid_occurrences_file': _rel(package_dir, occurrences_path)
    }
    manifest_path = package_dir / 'char_manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    report_path = package_dir / 'char_report.txt'
    report_path.write_text('\n'.join(format_char_manifest_report(manifest)), encoding='utf-8', newline='\n')
    return {
        'package_dir': str(package_dir),
        'manifest_path': str(manifest_path),
        'report_path': str(report_path),
        'model_count': len(models),
        'resolved_model_count': resolved_model_count,
        'animation_count': len(animations),
        'resolved_animation_count': resolved_animation_count,
        'resource_count': len(resources),
        'missing_count': len(missing)
    }

def format_char_manifest_report(manifest):
    lines = []
    lines.append(f'CHAR: {manifest["char_name"]}')
    lines.append(f'CHAR-UUID: {format_uuid_hex(manifest["char_uuid_hex"])}')
    lines.append(f'PAK-Eintrag: #{manifest["entry_index"]} {manifest["entry_type"]} {format_uuid_hex(manifest["entry_uuid_hex"])}')
    lines.append('')
    lines.append(f'Modelle: {manifest["resolved_model_count"]}/{manifest["model_count"]} aufgelöst')
    for item in manifest['models']:
        status = 'OK' if item.get('resolved') else 'FEHLT'
        typ = item.get('entry_type') or 'unbekannt'
        lines.append(f'- {status} | #{item["index"]} {item["slot_name"]} | {typ} | {format_uuid_hex(item["uuid_hex"])}')
    lines.append('')
    lines.append(f'Animationen: {manifest["resolved_animation_count"]}/{manifest["animation_count"]} aufgelöst')
    for item in manifest['animations']:
        if item['uuid_hex'] == ZERO_UUID:
            status = 'OHNE UUID'
        else:
            status = 'OK' if item.get('resolved') else 'FEHLT'
        typ = item.get('entry_type') or item.get('type') or 'ANIM'
        lines.append(f'- {status} | #{item["index"]} {item["name"]} | {typ} | {format_uuid_hex(item["uuid_hex"])}')
    lines.append('')
    by_type = {}
    for item in manifest['resources']:
        by_type[item['entry_type']] = by_type.get(item['entry_type'], 0) + 1
    lines.append(f'Ressourcen: {manifest["resource_count"]}')
    for typ in sorted(by_type):
        lines.append(f'- {typ}: {by_type[typ]}')
    if manifest['missing']:
        lines.append('')
        lines.append('Fehlende Referenzen:')
        for item in manifest['missing']:
            lines.append(f'- {item["kind"]} | {item["name"]} | {format_uuid_hex(item["uuid_hex"])}')
    return lines

def format_char_info_lines(parsed, entry, require_store=None):
    asset = get_entry_asset(parsed, entry)
    info = parse_char_asset(asset)
    lines = []
    lines.append('CHAR-Analyse:')
    lines.append(f'- Name: {info["name"]}')
    lines.append(f'- Interne UUID: {format_uuid_hex(info["uuid_hex"])}')
    lines.append(f'- Modelle: {len(info["model_slots"])}')
    for model in info['model_slots']:
        asset_data, ref_entry, source, source_path = _resolve_ref(parsed, model['uuid_hex'], require_store)
        status = 'OK' if ref_entry is not None and asset_data is not None else 'FEHLT'
        typ = ref_entry.get('type') if ref_entry is not None else 'unbekannt'
        source_label = 'aktuelles PAK' if source == 'pak' else 'Require' if source == 'require' else ''
        suffix = f' | {source_label}' if source_label else ''
        lines.append(f'  - {status} | #{model["index"]} {model["slot_name"]} | {typ} | {format_uuid_hex(model["uuid_hex"])}{suffix}')
    lines.append(f'- Animationen: {len(info["animations"])}')
    resolved_anim = 0
    missing_anim = 0
    zero_anim = 0
    for anim in info['animations']:
        if anim['uuid_hex'] == ZERO_UUID:
            zero_anim += 1
            continue
        asset_data, ref_entry, source, source_path = _resolve_ref(parsed, anim['uuid_hex'], require_store)
        if ref_entry is not None and asset_data is not None:
            resolved_anim += 1
        else:
            missing_anim += 1
    lines.append(f'  - aufgelöst: {resolved_anim}')
    lines.append(f'  - fehlt: {missing_anim}')
    if zero_anim:
        lines.append(f'  - ohne UUID: {zero_anim}')
    model_uuid_set = {item['uuid_hex'] for item in info['model_slots'] if item['uuid_hex'] != ZERO_UUID}
    anim_uuid_set = {item['uuid_hex'] for item in info['animations'] if item['uuid_hex'] != ZERO_UUID}
    excluded = set(model_uuid_set) | set(anim_uuid_set) | {entry['uuid_hex'], info.get('uuid_hex', '')}
    by_type = {}
    for occ in _find_uuid_occurrences(asset, _known_uuids(parsed, require_store)):
        uuid_hex = occ['uuid_hex']
        if uuid_hex in excluded:
            continue
        asset_data, ref_entry, source, source_path = _resolve_ref(parsed, uuid_hex, require_store)
        if ref_entry is not None and asset_data is not None:
            typ = ref_entry.get('type') or 'unbekannt'
            by_type[typ] = by_type.get(typ, 0) + 1
    if by_type:
        lines.append('- Weitere auflösbare Referenzen:')
        for typ in sorted(by_type):
            lines.append(f'  - {typ}: {by_type[typ]} Treffer')
    lines.append(f'- Restdaten nach bekannten Tabellen: {info["tail_size"]} Bytes')
    return lines
