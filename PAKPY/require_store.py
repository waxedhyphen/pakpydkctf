from pathlib import Path
from pak_core import PakError, parse_pak, get_entry_asset

class RequireStore:
    def __init__(self):
        self.clear()

    def clear(self):
        self.required_paks = []
        self.required_entries_by_uuid = {}
        self.required_sources_by_uuid = {}

    def add_pak(self, path):
        parsed = parse_pak(path)
        added = 0
        replaced = 0
        for entry in parsed['entries']:
            uuid_hex = entry['uuid_hex']
            asset = get_entry_asset(parsed, entry)
            if uuid_hex in self.required_entries_by_uuid:
                replaced += 1
            else:
                added += 1
            self.required_entries_by_uuid[uuid_hex] = {
                'entry': entry,
                'asset': asset,
                'parsed_path': str(path)
            }
            self.required_sources_by_uuid[uuid_hex] = str(path)
        self.required_paks.append({
            'path': str(path),
            'parsed': parsed
        })
        return {
            'path': str(path),
            'entry_count': len(parsed['entries']),
            'added': added,
            'replaced': replaced
        }

    def add_many(self, paths):
        results = []
        for path in paths:
            results.append(self.add_pak(path))
        return results

    def has_uuid(self, uuid_hex):
        return uuid_hex in self.required_entries_by_uuid

    def get_required_entry(self, uuid_hex):
        item = self.required_entries_by_uuid.get(uuid_hex)
        if item is None:
            return None
        return item['entry']

    def get_required_asset(self, uuid_hex):
        item = self.required_entries_by_uuid.get(uuid_hex)
        if item is None:
            return None
        return item['asset']

    def get_required_source(self, uuid_hex):
        return self.required_sources_by_uuid.get(uuid_hex, '')

    def resolve_entry(self, parsed, uuid_hex):
        entry = parsed.get('uuid_to_entry', {}).get(uuid_hex)
        if entry is not None:
            return entry, 'pak'
        req = self.get_required_entry(uuid_hex)
        if req is not None:
            return req, 'require'
        return None, ''

    def resolve_asset(self, parsed, uuid_hex):
        entry = parsed.get('uuid_to_entry', {}).get(uuid_hex)
        if entry is not None:
            return get_entry_asset(parsed, entry), entry, 'pak'
        asset = self.get_required_asset(uuid_hex)
        req_entry = self.get_required_entry(uuid_hex)
        if asset is not None and req_entry is not None:
            return asset, req_entry, 'require'
        return None, None, ''