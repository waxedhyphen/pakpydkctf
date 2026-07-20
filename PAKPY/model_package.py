from pathlib import Path
import json
import os

from pak_core import PakError, safe_name, sha1_bytes, get_entry_asset, rebuild_pak, kind_to_ext
from pak_extract import (
    export_txtr_bytes_as_png,
    make_material_texture_png_name,
    get_mtl_slot_for_ref_tag,
    export_model_entry_as_obj,
)
from txtr_repack import png_to_txtr_asset, can_repack_txtr_asset
from dae_export import export_model_dae, write_model_debug_json
from skel_probe import run_skel_probe_for_model


def _package_dir_name(entry):
    base = entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    return f'{safe_name(base)}_{entry["type"].lower()}_package'


def _resolve_txtr_asset(parsed, ref, require_store=None):
    if require_store is not None:
        return require_store.resolve_asset(parsed, ref['uuid_hex'])
    txtr_entry = parsed.get('uuid_to_entry', {}).get(ref['uuid_hex'])
    if txtr_entry is None:
        return None, None, ''
    return get_entry_asset(parsed, txtr_entry), txtr_entry, 'pak'


def _raw_txtr_name(material, ref, txtr_entry):
    return make_material_texture_png_name(material, ref, txtr_entry).rsplit('.', 1)[0] + '.txtr.bin'


def _write_raw_source(package_dir, entry, asset):
    folder = package_dir / 'source' / entry['type'].lower()
    folder.mkdir(parents=True, exist_ok=True)
    base = entry.get('display_name') or entry.get('name') or entry['uuid_hex']
    path = folder / (safe_name(base) + kind_to_ext(entry['type']))
    path.write_bytes(asset)
    return path


def _strict_texture_slots(parsed, entry, package_dir, require_store=None):
    material_texture_map = {}
    textures = []
    editable_count = 0
    raw_only_count = 0
    png_dir = package_dir / 'textures' / 'png'
    raw_dir = package_dir / 'textures' / 'raw_txtr'
    png_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for material in entry.get('model_materials', []):
        slot_map = {}
        fallback_kd = ''
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
                    'source_path': '',
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
                    'source_path': require_store.get_required_source(ref['uuid_hex']) if source == 'require' and require_store is not None else '',
                })
                continue

            raw_name = _raw_txtr_name(material, ref, txtr_entry)
            raw_path = raw_dir / raw_name
            raw_path.write_bytes(raw_asset)
            png_name = make_material_texture_png_name(material, ref, txtr_entry)
            png_path = png_dir / png_name
            export_error = ''
            try:
                export_txtr_bytes_as_png(raw_asset, png_path)
            except Exception as exc:
                export_error = str(exc)
            png_exported = export_error == '' and png_path.is_file()
            editable_png = png_exported and can_repack_txtr_asset(raw_asset)
            if png_exported:
                slot_name = get_mtl_slot_for_ref_tag(ref['tag'])
                rel_png = f'textures/png/{png_name}'
                if slot_name and slot_name not in slot_map:
                    slot_map[slot_name] = rel_png
                tag = str(ref.get('tag', '')).upper()
                blocked = ('NMAP', 'NRML', 'NORM', 'SPCT', 'SPEC', 'SPCF', 'EMIS', 'ICAN', 'REFV', 'REFS', 'FUR')
                if not fallback_kd and not any(part in tag for part in blocked):
                    fallback_kd = rel_png
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
                'png_name': f'textures/png/{png_name}' if png_exported else '',
                'png_sha1': sha1_bytes(png_path.read_bytes()) if png_exported else '',
                'raw_name': f'textures/raw_txtr/{raw_name}',
                'raw_sha1': sha1_bytes(raw_asset),
                'editable_png': editable_png,
                'export_error': export_error or '',
                'source_kind': source,
                'source_path': require_store.get_required_source(ref['uuid_hex']) if source == 'require' and require_store is not None else '',
            })
        if 'map_Kd' not in slot_map and fallback_kd:
            slot_map['map_Kd'] = fallback_kd
        if slot_map:
            material_texture_map[material['index']] = dict(slot_map)
            material_texture_map[str(material['name'])] = dict(slot_map)
    return material_texture_map, textures, editable_count, raw_only_count


def _map_texture_paths_for_folder(material_texture_map, package_dir, target_dir):
    out = {}
    for key, value in (material_texture_map or {}).items():
        if isinstance(value, str):
            out[key] = os.path.relpath(package_dir / value, target_dir).replace('\\', '/')
            continue
        if isinstance(value, dict):
            slot_map = {}
            for slot, rel_path in value.items():
                slot_map[slot] = os.path.relpath(package_dir / rel_path, target_dir).replace('\\', '/') if rel_path else ''
            out[key] = slot_map
    return out


def _write_report(package_dir, manifest):
    lines = [
        f'Modell: {manifest["entry_name"]}',
        f'Typ: {manifest["entry_type"]}',
        f'OBJ: {manifest["obj"]}',
        f'MTL: {manifest["mtl"]}',
        f'DAE: {manifest["dae"]}',
    ]
    if manifest.get('experimental_skeletal_dae'):
        lines.append(f'Experimental Skeletal DAE: {manifest["experimental_skeletal_dae"]}')
    if manifest.get('experimental_skeletal_glb'):
        lines.append(f'Experimental Skeletal GLB: {manifest["experimental_skeletal_glb"]}')
    if manifest.get('experimental_skeletal_blend'):
        lines.append(f'Blender Connected Rig: {manifest["experimental_skeletal_blend"]}')
    elif manifest.get('experimental_skeletal_blend_error'):
        lines.append(f'Blender Connected Rig Fehler: {manifest["experimental_skeletal_blend_error"]}')
    lines.extend([
        f'Bones: {manifest.get("bone_count", 0)}',
        f'Faces: {manifest.get("face_count", 0)}',
    ])
    if manifest.get('skel_probe_summary'):
        lines.append(f'SKEL-Probe: {manifest["skel_probe_summary"]}')
    lines.extend([
        f'Bearbeitbare PNGs: {manifest["editable_png_count"]}',
        f'Nur Roh-Sicherung: {manifest["raw_only_count"]}',
        '',
        'Texturen:',
    ])
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


def export_model_package(parsed, entry, out_dir, require_store=None, animation_refs=None, skeleton_refs=None):
    if entry['type'] not in ('CMDL', 'SMDL', 'WMDL'):
        raise PakError('Modellpaket geht nur bei CMDL, SMDL oder WMDL')
    out_dir = Path(out_dir)
    package_dir = out_dir / _package_dir_name(entry)
    package_dir.mkdir(parents=True, exist_ok=True)
    asset = get_entry_asset(parsed, entry)
    raw_source = _write_raw_source(package_dir, entry, asset)
    material_texture_map, textures, editable_count, raw_only_count = _strict_texture_slots(
        parsed, entry, package_dir, require_store=require_store
    )
    model_dir = package_dir / 'model'
    debug_dir = package_dir / 'debug'
    model_dir.mkdir(parents=True, exist_ok=True)
    debug_dir.mkdir(parents=True, exist_ok=True)
    base = safe_name(entry.get('display_name') or entry.get('name') or entry['uuid_hex'])
    obj_texture_map = _map_texture_paths_for_folder(material_texture_map, package_dir, model_dir)
    obj_result = export_model_entry_as_obj(
        parsed, entry, model_dir, write_mtl=True, material_texture_map=obj_texture_map
    )
    dae_path = model_dir / f'{base}.dae'
    dae_result = export_model_dae(
        parsed,
        entry,
        dae_path,
        require_store=require_store,
        skeleton_refs=[],
        texture_map=material_texture_map,
        texture_root=package_dir,
        include_skin=False,
    )
    skeletal_dae_path = model_dir / f'{base}.experimental_skeletal.dae'
    skeletal_dae = {
        'dae_path': '',
        'bone_count': 0,
        'skeleton': {},
        'skeleton_uuid_hex': '',
        'skeleton_source_kind': '',
        'skeleton_source_path': '',
    }
    skeletal_error = ''
    if skeleton_refs:
        try:
            skeletal_dae = export_model_dae(
                parsed,
                entry,
                skeletal_dae_path,
                require_store=require_store,
                skeleton_refs=skeleton_refs,
                texture_map=material_texture_map,
                texture_root=package_dir,
                include_skin=True,
            )
        except Exception as exc:
            skeletal_error = str(exc)

    debug_json_path = debug_dir / 'model_debug.json'
    try:
        write_model_debug_json(
            parsed,
            entry,
            debug_json_path,
            require_store=require_store,
            skeleton_refs=skeleton_refs or [],
        )
    except Exception as exc:
        debug_json_path.write_text(
            json.dumps({'error': str(exc)}, indent=2, ensure_ascii=False),
            encoding='utf-8',
            newline='\n',
        )
    skeleton_json_path = debug_dir / 'skeleton_debug.json'
    skeleton_json_path.write_text(
        json.dumps(skeletal_dae.get('skeleton') or {}, indent=2, ensure_ascii=False),
        encoding='utf-8',
        newline='\n',
    )
    skel_probe = {'model_usage': {}, 'skeleton_count': 0, 'skeletons': []}
    skel_probe_error = ''
    if skeleton_refs:
        try:
            skel_probe = run_skel_probe_for_model(
                parsed, entry, skeleton_refs, debug_dir / 'skel_probe', require_store=require_store
            )
        except Exception as exc:
            skel_probe_error = str(exc)
    skel_probe_path = debug_dir / 'skel_probe_summary.json'
    skel_probe_path.write_text(
        json.dumps({'probe': skel_probe, 'error': skel_probe_error}, indent=2, ensure_ascii=False),
        encoding='utf-8',
        newline='\n',
    )

    obj_path = Path(obj_result['obj_path'])
    mtl_path = Path(obj_result['mtl_path']) if obj_result.get('mtl_path') else None
    manifest = {
        'version': 8,
        'source_pak': Path(parsed['path']).name,
        'entry_index': entry['index'],
        'entry_type': entry['type'],
        'entry_uuid_hex': entry['uuid_hex'],
        'entry_name': entry.get('display_name') or entry.get('name') or entry['uuid_hex'],
        'obj': str(obj_path.relative_to(package_dir)).replace('\\', '/'),
        'obj_sha1': sha1_bytes(obj_path.read_bytes()),
        'mtl': str(mtl_path.relative_to(package_dir)).replace('\\', '/') if mtl_path else '',
        'mtl_sha1': sha1_bytes(mtl_path.read_bytes()) if mtl_path else '',
        'dae': str(dae_path.relative_to(package_dir)).replace('\\', '/'),
        'dae_sha1': sha1_bytes(dae_path.read_bytes()),
        'experimental_skeletal_dae': str(skeletal_dae_path.relative_to(package_dir)).replace('\\', '/') if skeletal_dae_path.is_file() else '',
        'experimental_skeletal_dae_sha1': sha1_bytes(skeletal_dae_path.read_bytes()) if skeletal_dae_path.is_file() else '',
        'experimental_skeletal_error': skeletal_error,
        'source_model': str(raw_source.relative_to(package_dir)).replace('\\', '/'),
        'source_model_sha1': sha1_bytes(raw_source.read_bytes()),
        'model_debug_json': str(debug_json_path.relative_to(package_dir)).replace('\\', '/'),
        'skeleton_debug_json': str(skeleton_json_path.relative_to(package_dir)).replace('\\', '/'),
        'skel_probe_summary': str(skel_probe_path.relative_to(package_dir)).replace('\\', '/'),
        'skel_probe_error': skel_probe_error,
        'skeleton_uuid_hex': skeletal_dae.get('skeleton_uuid_hex', ''),
        'skeleton_source_kind': skeletal_dae.get('skeleton_source_kind', ''),
        'skeleton_source_path': skeletal_dae.get('skeleton_source_path', ''),
        'bone_count': skeletal_dae.get('bone_count', 0),
        'vertex_count': dae_result.get('vertex_count', 0),
        'face_count': dae_result.get('face_count', 0),
        'editable_png_count': editable_count,
        'raw_only_count': raw_only_count,
        'textures': textures,
        'animations': animation_refs or [],
        'skeleton_refs': skeleton_refs or [],
    }
    manifest_path = package_dir / 'repack_manifest.json'
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n'
    )
    _write_report(package_dir, manifest)
    return {
        'package_dir': str(package_dir),
        'manifest_path': str(manifest_path),
        'obj': str(obj_path),
        'obj_path': str(obj_path),
        'mtl': str(mtl_path) if mtl_path else '',
        'mtl_path': str(mtl_path) if mtl_path else '',
        'dae': str(dae_path),
        'experimental_skeletal_dae': str(skeletal_dae_path) if skeletal_dae_path.is_file() else '',
        'texture_count': len(textures),
        'editable_png_count': editable_count,
        'raw_only_count': raw_only_count,
        'bone_count': skeletal_dae.get('bone_count', 0),
        'vertex_count': dae_result.get('vertex_count', 0),
        'face_count': dae_result.get('face_count', 0),
        'animation_count': len(animation_refs or []),
        'experimental_skeletal_error': skeletal_error,
        'skel_probe_error': skel_probe_error,
    }


class _LegacyRebuildCount(int):
    """Keep the old GUI readable while exposing geometry counts without patching App."""

    def __new__(cls, texture_count, geometry_count, package_count):
        value = int(texture_count) + int(geometry_count)
        obj = int.__new__(cls, value)
        obj.texture_count = int(texture_count)
        obj.geometry_count = int(geometry_count)
        obj.package_count = int(package_count)
        return obj

    def __str__(self):
        return (
            f'{self.texture_count}\n'
            f'Geänderte Modellressourcen: {self.geometry_count}\n'
            f'Modellpakete geprüft: {self.package_count}'
        )


def _direct_rebuild_model_package_from_folder(parsed, folder, out_path):
    """Always use the BLEND-aware rebuild path, independent of the application entrypoint."""
    import blend_model_repack_patch

    blend_model_repack_patch.install()
    try:
        result = blend_model_repack_patch.rebuild_from_blend_package(parsed, folder, out_path)
    finally:
        globals()['rebuild_model_package_from_folder'] = _direct_rebuild_model_package_from_folder
    result['changed_count'] = _LegacyRebuildCount(
        result.get('texture_changed_count', 0),
        result.get('geometry_changed_count', 0),
        result.get('model_package_count', 0),
    )
    return result


rebuild_model_package_from_folder = _direct_rebuild_model_package_from_folder


def _install_geometry_repack_runtime():
    """Install export/repack support whenever model_package is imported, not only from main.py."""
    try:
        import skeletal_tail_patch
        import exact_skeletal_rig_patch
        import mesh_partition_export_patch
        import mesh_partition_outliner_cleanup_patch
        import blend_model_repack_patch

        skeletal_tail_patch.install()
        exact_skeletal_rig_patch.install()
        mesh_partition_export_patch.install()
        mesh_partition_outliner_cleanup_patch.install()
        blend_model_repack_patch.install()
        return ''
    except Exception as exc:
        return str(exc)


geometry_repack_install_error = _install_geometry_repack_runtime()
# The patch installer assigns its core function here. Restore the stable public
# dispatcher so direct imports and older GUI entrypoints receive the same path.
rebuild_model_package_from_folder = _direct_rebuild_model_package_from_folder
