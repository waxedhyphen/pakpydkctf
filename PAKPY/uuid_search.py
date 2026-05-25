import re
from pak_core import PakError, get_entry_asset
from room_codec import describe_room_hit, format_room_hit_extra

def normalize_uuid_query(text):
    raw = (text or '').strip()
    raw = raw.strip('{}()[]<>"\'`')
    raw = raw.replace('urn:uuid:', '')
    raw = raw.replace('UUID:', '')
    raw = raw.replace('uuid:', '')
    raw = re.sub(r'[^0-9A-Fa-f]', '', raw)
    if len(raw) != 32:
        raise PakError('Bitte eine UUID mit 32 Hex-Zeichen eingeben')
    try:
        bytes.fromhex(raw)
    except Exception:
        raise PakError('UUID enthält ungültige Hex-Zeichen')
    return raw.lower()

def dashed_uuid(hex_text):
    return f'{hex_text[:8]}-{hex_text[8:12]}-{hex_text[12:16]}-{hex_text[16:20]}-{hex_text[20:]}'

def uuid_needles(hex_text):
    dashed = dashed_uuid(hex_text)
    values = []
    values.append(('raw uuid bytes', bytes.fromhex(hex_text)))
    values.append(('text hex lower', hex_text.encode('ascii')))
    values.append(('text hex upper', hex_text.upper().encode('ascii')))
    values.append(('text dashed lower', dashed.encode('ascii')))
    values.append(('text dashed upper', dashed.upper().encode('ascii')))
    unique = []
    seen = set()
    for label, data in values:
        if data and data not in seen:
            unique.append((label, data))
            seen.add(data)
    return unique

def find_all(data, needle):
    out = []
    start = 0
    while True:
        off = data.find(needle, start)
        if off < 0:
            return out
        out.append(off)
        start = off + 1

def entry_label(entry):
    name = entry.get('display_name') or entry.get('name') or entry.get('uuid_hex') or ''
    return f'#{entry["index"]} {entry["type"]} | {name} | {dashed_uuid(entry["uuid_hex"])}'

def find_direct_entries(parsed, hex_text):
    return [entry for entry in parsed.get('entries', []) if entry.get('uuid_hex', '').lower() == hex_text]

def find_entry_at_offset(parsed, off):
    for entry in parsed.get('entries', []):
        start = entry['offset']
        end = start + entry['size']
        if start <= off < end:
            return entry
    return None

def child_at_offset(entry, off):
    if not entry or not entry.get('is_bundle'):
        return None
    payload_base = entry['offset'] + 32
    for child in entry.get('bundle', {}).get('children', []):
        start = payload_base + child['off']
        end = payload_base + child['payload_end']
        if start <= off < end:
            return child
    return None

def archive_area(parsed, off):
    entries = parsed.get('entries', [])
    if not entries:
        return 'Archivstruktur'
    first = min(entry['offset'] for entry in entries)
    last = max(entry['offset'] + entry['size'] for entry in entries)
    if off < first:
        return 'Archivstruktur vor den Assets'
    if off >= last:
        return 'Archivstruktur nach den Assets'
    return 'Lücke zwischen Assets'

def hit_record(parsed, off, needle_label, uuid_hex):
    entry = find_entry_at_offset(parsed, off)
    if entry is None:
        return {'offset': off, 'needle': needle_label, 'entry': None, 'child': None, 'area': archive_area(parsed, off), 'entry_offset': None, 'child_offset': None, 'room_extra': None}
    child = child_at_offset(entry, off)
    child_offset = None
    if child is not None:
        child_offset = off - (entry['offset'] + 32 + child['off'])
    room_extra = None
    if entry.get('type') == 'ROOM':
        try:
            asset = get_entry_asset(parsed, entry)
            room_extra = describe_room_hit(asset, off - entry['offset'], uuid_hex)
        except Exception:
            room_extra = None
    return {'offset': off, 'needle': needle_label, 'entry': entry, 'child': child, 'area': None, 'entry_offset': off - entry['offset'], 'child_offset': child_offset, 'room_extra': room_extra}

def search_uuid_references(parsed, query):
    hex_text = normalize_uuid_query(query)
    data = parsed.get('data')
    if data is None:
        with open(parsed['path'], 'rb') as f:
            data = f.read()
    direct_entries = find_direct_entries(parsed, hex_text)
    hits = []
    seen = set()
    for label, needle in uuid_needles(hex_text):
        for off in find_all(data, needle):
            key = (off, label)
            if key in seen:
                continue
            seen.add(key)
            hits.append(hit_record(parsed, off, label, hex_text))
    hits.sort(key=lambda item: item['offset'])
    return {'uuid_hex': hex_text, 'uuid_dashed': dashed_uuid(hex_text), 'direct_entries': direct_entries, 'hits': hits}

def format_uuid_search_lines(parsed, query, max_hits=400):
    result = search_uuid_references(parsed, query)
    lines = []
    lines.append('UUID-Suche')
    lines.append(f'UUID: {result["uuid_dashed"]}')
    lines.append('')
    if result['direct_entries']:
        lines.append('Eigener Eintrag im PAK:')
        for entry in result['direct_entries']:
            lines.append(f'- {entry_label(entry)}')
    else:
        lines.append('Eigener Eintrag im PAK: nicht vorhanden')
    lines.append('')
    lines.append(f'Rohtreffer im gesamten Archiv: {len(result["hits"])}')
    grouped = {}
    outside = 0
    for hit in result['hits']:
        entry = hit['entry']
        if entry is None:
            outside += 1
            continue
        grouped.setdefault(entry['index'], {'entry': entry, 'hits': 0}).update({'entry': entry})
        grouped[entry['index']]['hits'] += 1
    if grouped:
        lines.append('')
        lines.append('Treffer nach PAK-Eintrag:')
        for item in sorted(grouped.values(), key=lambda x: (-x['hits'], x['entry']['index'])):
            lines.append(f'- {entry_label(item["entry"])} | Treffer {item["hits"]}')
    if outside:
        lines.append(f'- Archivstruktur ohne direkte Datei-Zuordnung | Treffer {outside}')
    if result['hits']:
        lines.append('')
        lines.append('Einzeltreffer:')
        for hit in result['hits'][:max_hits]:
            off_text = f'0x{hit["offset"]:X}'
            if hit['entry'] is None:
                lines.append(f'- {off_text} | {hit["needle"]} | {hit["area"]}')
                continue
            entry = hit['entry']
            part = f'{off_text} | {hit["needle"]} | {entry_label(entry)} | asset+0x{hit["entry_offset"]:X}'
            child = hit['child']
            if child is not None:
                part += f' | child {child["segment_tag"]} {child["inner_kind"]}+0x{hit["child_offset"]:X}'
            extra = format_room_hit_extra(hit.get('room_extra'))
            if extra:
                part += f' | {extra}'
            lines.append(f'- {part}')
        if len(result['hits']) > max_hits:
            lines.append(f'... {len(result["hits"]) - max_hits} weitere Treffer')
    return lines
