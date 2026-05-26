from pak_core import PakError

MISSING_TXTR_ERROR = 'Verlinktes TXTR ist weder im aktuellen PAK noch in den requireten Dateien vorhanden'

def install(App):
    original_build_payload_export = App.build_payload_export
    original_build_whole_export = App.build_whole_export
    def raise_missing_txtr(item):
        ref = item.get('ref') or {}
        uuid_hex = ref.get('uuid_hex', '')
        tag = ref.get('tag', '')
        details = []
        if tag:
            details.append(f'Ref-Tag: {tag}')
        if uuid_hex:
            details.append(f'TXTR-UUID: {uuid_hex}')
        extra = '\n' + '\n'.join(details) if details else ''
        raise PakError(f'{MISSING_TXTR_ERROR}.\nDie Verlinkung wurde im Modell gefunden, aber die verlinkte TXTR-Datei konnte nicht aufgelöst werden.{extra}')
    def build_payload_export(self, item):
        if item.get('kind') == 'model_txtr_child':
            asset, txtr_entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            if txtr_entry is None or asset is None:
                raise_missing_txtr(item)
        return original_build_payload_export(self, item)
    def build_whole_export(self, item):
        if item.get('kind') == 'model_txtr_child':
            data, txtr_entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            if txtr_entry is None or data is None:
                raise_missing_txtr(item)
        return original_build_whole_export(self, item)
    App.build_payload_export = build_payload_export
    App.build_whole_export = build_whole_export
