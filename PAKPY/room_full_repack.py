from pathlib import Path
from pak_core import PakError, get_entry_asset, rebuild_pak
from room_repack import read_manifest, validate_room_manifest, detect_room_object_changes
from room_clone_codec import apply_room_clones


def rebuild_room_package_from_folder(parsed, folder, out_path):
    manifest = read_manifest(folder)
    replacements, changed_objects, unsupported, transform_patches = detect_room_object_changes(parsed, folder, manifest)
    room_entry = validate_room_manifest(parsed, manifest)
    room_index = room_entry['index']
    room_asset = replacements.get(room_index, {}).get('asset_bytes') or get_entry_asset(parsed, room_entry)
    cloned_asset, clone_count, clone_changed, clone_unsupported = apply_room_clones(parsed, folder, manifest, room_asset)
    if cloned_asset is not None:
        replacements[room_index] = {'asset_bytes': cloned_asset}
        changed_objects.extend(clone_changed)
        transform_patches += clone_count
    unsupported.extend(clone_unsupported)
    if not replacements:
        raise PakError('Keine geänderten ROOM-Objekte, Transform-Werte oder Clone-Dateien gefunden')
    if unsupported:
        raise PakError('ROOM-Rückbau nicht möglich: ' + '; '.join(unsupported[:20]))
    built = rebuild_pak(parsed, replacements, out_path)
    return {'out_path': built, 'changed_count': len(replacements), 'changed_objects': changed_objects, 'transform_patch_count': transform_patches, 'room_entry_index': manifest.get('room_entry_index')}
