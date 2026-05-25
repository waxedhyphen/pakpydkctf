#========================
#FILE pak_folder.py
#========================

from pathlib import Path
import json
from pak_core import PakError, sha1_bytes, get_entry_asset, get_entry_payload, entry_export_name, kind_to_ext, build_segment_blob, build_bundle_replaced_asset

def export_all(parsed, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    whole_dir = out_dir / 'whole'
    payload_dir = out_dir / 'payload'
    expanded_dir = out_dir / 'expanded'
    meta_dir = out_dir / 'meta'
    whole_dir.mkdir(exist_ok=True)
    payload_dir.mkdir(exist_ok=True)
    expanded_dir.mkdir(exist_ok=True)
    meta_dir.mkdir(exist_ok=True)
    manifest = {
        'source_pak': Path(parsed['path']).name,
        'source_size': len(parsed['data']),
        'source_sha1': sha1_bytes(parsed['data']),
        'entries': []
    }
    for entry in parsed['entries_by_offset']:
        asset = get_entry_asset(parsed, entry)
        payload = get_entry_payload(asset)
        base = entry_export_name(entry)
        whole_name = f'whole/{base}.bin'
        (out_dir / whole_name).write_bytes(asset)
        export_payload_kind = entry['payload_kind']
        if entry['is_bundle']:
            export_payload = payload
        else:
            export_payload = asset
        item = {
            'index': entry['index'],
            'type': entry['type'],
            'name': entry['name'],
            'uuid_hex': entry['uuid_hex'],
            'whole_file': whole_name,
            'whole_size': len(asset),
            'whole_sha1': sha1_bytes(asset),
            'is_bundle': entry['is_bundle'],
            'payload_kind': export_payload_kind,
            'payload_size': len(export_payload),
            'payload_sha1': sha1_bytes(export_payload),
            'has_meta': entry['has_meta']
        }
        if entry['has_meta']:
            meta_name = f'meta/{base}.meta.bin'
            (out_dir / meta_name).write_bytes(entry['meta']['blob'])
            item['meta_file'] = meta_name
            item['meta_size'] = entry['meta']['blob_size']
            item['meta_sha1'] = sha1_bytes(entry['meta']['blob'])
            item['meta_kind'] = entry.get('meta_kind') or ''
        if entry['is_bundle']:
            payload_name = f'payload/{base}.__bundle__.bin'
            (out_dir / payload_name).write_bytes(payload)
            item['payload_file'] = payload_name
            item['bundle_children'] = []
            entry_dir = expanded_dir / base
            entry_dir.mkdir(exist_ok=True)
            for child in entry['bundle']['children']:
                child_base = f'{child["index"]:02d}__{child["segment_tag"]}__{child["inner_kind"].lower()}'
                child_payload = child['inner']
                child_ext = kind_to_ext(child['inner_kind'])
                child_payload_name = f'expanded/{base}/{child_base}{child_ext}'
                child_whole_name = f'expanded/{base}/{child_base}.__wrapped__.bin'
                wrapped = build_segment_blob(child)
                (out_dir / child_payload_name).write_bytes(child_payload)
                (out_dir / child_whole_name).write_bytes(wrapped)
                item['bundle_children'].append({
                    'index': child['index'],
                    'segment_tag': child['segment_tag'],
                    'inner_kind': child['inner_kind'],
                    'payload_file': child_payload_name,
                    'payload_size': len(child_payload),
                    'payload_sha1': sha1_bytes(child_payload),
                    'whole_file': child_whole_name,
                    'whole_size': len(wrapped),
                    'whole_sha1': sha1_bytes(wrapped)
                })
        else:
            payload_name = f'payload/{base}{kind_to_ext(entry["type"])}'
            (out_dir / payload_name).write_bytes(export_payload)
            item['payload_file'] = payload_name
        manifest['entries'].append(item)
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    return manifest

def collect_folder_replacements(parsed, folder):
    folder = Path(folder)
    manifest_path = folder / 'manifest.json'
    if not manifest_path.is_file():
        raise PakError('manifest.json fehlt im Ordner')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    replacements = {}
    for item in manifest.get('entries', []):
        index = item['index']
        entry = parsed['entries'][index]
        whole_path = folder / item['whole_file']
        if whole_path.is_file() and sha1_bytes(whole_path.read_bytes()) != item['whole_sha1']:
            replacements[index] = {'path': str(whole_path), 'mode': 'whole'}
            continue
        payload_path = folder / item['payload_file']
        if payload_path.is_file() and sha1_bytes(payload_path.read_bytes()) != item['payload_sha1']:
            replacements[index] = {'path': str(payload_path), 'mode': 'payload'}
            continue
        if not item.get('is_bundle'):
            continue
        child_changes = {}
        for child_item in item.get('bundle_children', []):
            child_whole_path = folder / child_item['whole_file']
            child_payload_path = folder / child_item['payload_file']
            if child_whole_path.is_file() and sha1_bytes(child_whole_path.read_bytes()) != child_item['whole_sha1']:
                child_changes[child_item['index']] = {'path': str(child_whole_path), 'mode': 'whole'}
                continue
            if child_payload_path.is_file() and sha1_bytes(child_payload_path.read_bytes()) != child_item['payload_sha1']:
                child_changes[child_item['index']] = {'path': str(child_payload_path), 'mode': 'payload'}
        if child_changes:
            replacements[index] = {'asset_bytes': build_bundle_replaced_asset(parsed, entry, child_changes)}
    return replacements