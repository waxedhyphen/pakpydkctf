import json
from pathlib import Path
import char_codec
import char_gui_patch
from pak_core import get_entry_asset
from skeletal_codec import find_known_uuid_refs, write_char_blender_helper

def install(App):
    original_export_char_package = char_gui_patch.export_char_package
    def export_char_package(parsed, entry, out_dir, require_store=None):
        asset = get_entry_asset(parsed, entry)
        info = char_codec.parse_char_asset(asset)
        animation_refs = list(info.get('animations', []))
        skeleton_refs = []
        for index, ref in enumerate(find_known_uuid_refs(asset, parsed, require_store, wanted_types={'SKEL'})):
            skeleton_refs.append({'index': index, 'uuid_hex': ref['uuid_hex'], 'name': ref.get('entry_name', ''), 'type': 'SKEL'})
        original_helper = char_codec._export_model_package_if_possible
        def helper(package_dir, parsed_arg, model_entry, model_uuid, source, require_store_arg):
            if model_entry is None or model_entry.get('type') not in char_codec.MODEL_TYPES:
                return '', ''
            try:
                from model_package import export_model_package
                model_parsed = parsed_arg if source == 'pak' else char_codec._required_parsed_for_uuid(require_store_arg, model_uuid)
                if model_parsed is None:
                    return '', 'Kein Parsed-Kontext für Modellpaket verfügbar'
                result = export_model_package(model_parsed, model_entry, Path(package_dir) / 'model_packages', require_store=require_store_arg, animation_refs=animation_refs, skeleton_refs=skeleton_refs)
                return result.get('package_dir', ''), ''
            except Exception as e:
                return '', str(e)
        char_codec._export_model_package_if_possible = helper
        try:
            result = original_export_char_package(parsed, entry, out_dir, require_store=require_store)
        finally:
            char_codec._export_model_package_if_possible = original_helper
        manifest_path = Path(result.get('manifest_path', ''))
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            manifest['skeletons'] = skeleton_refs
            helper_result = write_char_blender_helper(Path(result['package_dir']), manifest)
            manifest['blender'] = helper_result
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
        return result
    char_gui_patch.export_char_package = export_char_package
