from pak_core import PakError, safe_name

MISSING_TXTR_ERROR = 'Verlinktes TXTR ist weder im aktuellen PAK noch in den requireten Dateien vorhanden'

def install(App):
    original_build_payload_export = App.build_payload_export
    original_build_whole_export = App.build_whole_export
    def missing_txtr_message(item):
        ref = item.get('ref') or {}
        material = item.get('material') or {}
        entry = item.get('entry') or {}
        uuid_hex = ref.get('uuid_hex', '')
        tag = ref.get('tag', '')
        lines = [
            MISSING_TXTR_ERROR + '.',
            'Die Verlinkung wurde im Modell gefunden, aber die verlinkte TXTR-Datei konnte nicht aufgelöst werden.'
        ]
        if entry.get('type'):
            lines.append(f'Modell-Typ: {entry["type"]}')
        if entry.get('uuid_hex'):
            lines.append(f'Modell-UUID: {entry["uuid_hex"]}')
        if material.get('name'):
            lines.append(f'Material: {material["name"]}')
        if tag:
            lines.append(f'Ref-Tag: {tag}')
        if uuid_hex:
            lines.append(f'TXTR-UUID: {uuid_hex}')
        return '\n'.join(lines) + '\n'
    def missing_txtr_filename(item):
        ref = item.get('ref') or {}
        material = item.get('material') or {}
        tag = ref.get('tag') or 'TXTR'
        uuid_hex = ref.get('uuid_hex') or 'missing'
        material_name = material.get('name') or 'material'
        return safe_name(f'{material_name}_{tag}_{uuid_hex}') + '.missing_txtr.txt'
    def build_payload_export(self, item):
        if item.get('kind') == 'model_txtr_child':
            asset, txtr_entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            if txtr_entry is None or asset is None:
                return missing_txtr_filename(item), missing_txtr_message(item).encode('utf-8')
        return original_build_payload_export(self, item)
    def build_whole_export(self, item):
        if item.get('kind') == 'model_txtr_child':
            data, txtr_entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            if txtr_entry is None or data is None:
                return missing_txtr_filename(item), missing_txtr_message(item).encode('utf-8')
        return original_build_whole_export(self, item)
    App.build_payload_export = build_payload_export
    App.build_whole_export = build_whole_export
