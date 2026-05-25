#========================
#FILE pak_core.py
#========================

from pathlib import Path
import hashlib
import json
import re
import struct
import zlib
from collections import Counter
from csmp_codec import normalize_csmp_replacement
from caud_codec import is_caud_asset, parse_caud_asset, build_caud_ref_map
from windows_compat import safe_path_component

class PakError(Exception):
    pass

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def be64(data, off):
    return int.from_bytes(data[off:off+8], 'big')

def w32(buf, off, value):
    buf[off:off+4] = int(value).to_bytes(4, 'big')

def w64(buf, off, value):
    buf[off:off+8] = int(value).to_bytes(8, 'big')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def safe_name(text):
    return safe_path_component(text, fallback='asset')

def sha1_bytes(data):
    return hashlib.sha1(data).hexdigest()

def kind_to_ext(kind):
    kind = (kind or '').strip().lower()
    return '.' + kind if kind else '.bin'

def parse_rfrm_header(data, off, label):
    if off + 32 > len(data):
        raise PakError(f'{label} abgeschnitten bei 0x{off:X}')
    if data[off:off+4] != b'RFRM':
        raise PakError(f'{label} hat kein RFRM bei 0x{off:X}')
    size = be64(data, off + 4)
    tag = tag4(data, off + 20)
    version_a = be32(data, off + 24)
    version_b = be32(data, off + 28)
    end = off + 32 + size
    if end > len(data):
        raise PakError(f'{label} läuft über Dateiende')
    return {
        'off': off,
        'size': size,
        'tag': tag,
        'version_a': version_a,
        'version_b': version_b,
        'end': end,
        'header': data[off:off+32]
    }

def parse_chunk(data, off):
    if off + 24 > len(data):
        raise PakError(f'Chunk abgeschnitten bei 0x{off:X}')
    tag = tag4(data, off)
    size = be64(data, off + 4)
    version = be32(data, off + 12)
    payload_off = off + 24
    payload_end = payload_off + size
    if payload_end > len(data):
        raise PakError(f'Chunk {tag} läuft über Dateiende')
    return {
        'tag': tag,
        'off': off,
        'size': size,
        'version': version,
        'payload_off': payload_off,
        'payload_end': payload_end,
        'next_off': payload_end,
        'header': data[off:off+24],
        'raw': data[off:payload_end]
    }

def detect_payload_kind(raw):
    if raw.startswith(b'MsgStdBn'):
        return 'MSBT'
    if len(raw) >= 32 and raw[:4] == b'RFRM':
        return tag4(raw, 20)
    if len(raw) >= 4:
        head = raw[:4]
        if all(32 <= b < 127 for b in head):
            try:
                text = head.decode('ascii')
                if text.isupper():
                    return text
            except Exception:
                pass
    return ''

KNOWN_CHUNK_TAGS = {'FMTA', 'DATA', 'HEAD', 'DESC', 'GPU ', 'MESH', 'VBUF', 'IBUF', 'META', 'ADIR', 'STRG'}

def is_segment_name(text):
    if not text or text in KNOWN_CHUNK_TAGS:
        return False
    return bool(re.fullmatch(r'[A-Z0-9]{4}', text))

def parse_segmented_payload(raw):
    if len(raw) < 48:
        return None
    children = []
    p = 0
    while p < len(raw):
        if p + 24 > len(raw):
            return None
        seg_tag = tag4(raw, p)
        if not is_segment_name(seg_tag):
            return None
        if raw[p+4:p+8] != b'\x00\x00\x00\x00':
            return None
        if raw[p+12:p+24] != b'\x00' * 12:
            return None
        size = be32(raw, p + 8)
        payload_off = p + 24
        payload_end = payload_off + size
        if size <= 0 or payload_end > len(raw):
            return None
        inner = raw[payload_off:payload_end]
        inner_kind = detect_payload_kind(inner)
        if not inner_kind:
            return None
        children.append({
            'index': len(children),
            'segment_tag': seg_tag,
            'off': p,
            'header': raw[p:p+24],
            'size': size,
            'payload_off': payload_off,
            'payload_end': payload_end,
            'inner': inner,
            'inner_kind': inner_kind,
            'inner_sha1': sha1_bytes(inner),
            'whole_sha1': sha1_bytes(raw[p:payload_end])
        })
        p = payload_end
    if len(children) < 2:
        return None
    return {
        'size': len(raw),
        'children': children
    }

def build_segment_blob(child, inner=None):
    use_inner = child['inner'] if inner is None else inner
    head = bytearray(child['header'])
    w32(head, 8, len(use_inner))
    return bytes(head) + use_inner

def build_segmented_payload(bundle, replacements=None):
    replacements = replacements or {}
    parts = []
    for child in bundle['children']:
        inner = replacements.get(child['index'], child['inner'])
        parts.append(build_segment_blob(child, inner))
    return b''.join(parts)

def get_entry_asset(parsed, entry):
    return parsed['data'][entry['offset']:entry['offset'] + entry['size']]

def get_entry_payload(asset):
    if len(asset) >= 32 and asset[:4] == b'RFRM':
        return asset[32:]
    return asset

def detect_wrapped_type(raw):
    if len(raw) >= 32 and raw[:4] == b'RFRM':
        return tag4(raw, 20)
    return ''

def patch_wrapped_payload(original_asset, new_payload):
    if len(original_asset) < 32 or original_asset[:4] != b'RFRM':
        raise PakError('Original-Ressource hat keinen gültigen RFRM-Wrapper')
    wrapped = bytearray(original_asset[:32] + new_payload)
    w64(wrapped, 4, len(new_payload))
    return bytes(wrapped)

def prepare_replacement(entry, original_asset, replacement_path, mode):
    raw = Path(replacement_path).read_bytes()
    if entry['type'] == 'TXTR' and raw.startswith(b'\x89PNG\r\n\x1a\n'):
        from txtr_repack import png_to_txtr_asset
        return png_to_txtr_asset(original_asset, replacement_path)
    normalized_csmp = normalize_csmp_replacement(raw, original_asset)
    if normalized_csmp is not None:
        return normalized_csmp
    chosen_mode = mode
    if chosen_mode == 'auto':
        chosen_mode = 'whole' if raw[:4] == b'RFRM' else 'payload'
    if chosen_mode == 'whole':
        if raw[:4] != b'RFRM':
            raise PakError('Ganze Ressource ersetzen erwartet eine komplette RFRM-Datei')
        inner = detect_wrapped_type(raw)
        if inner != entry['type']:
            raise PakError(f'Falscher Typ: erwartet {entry["type"]}, gefunden {inner or "unbekannt"}')
        fixed = bytearray(raw)
        w64(fixed, 4, len(fixed) - 32)
        return bytes(fixed)
    if chosen_mode == 'payload':
        if raw[:4] == b'RFRM':
            inner = detect_wrapped_type(raw)
            if inner != entry['type']:
                raise PakError(f'Falscher Typ: erwartet {entry["type"]}, gefunden {inner or "unbekannt"}')
            fixed = bytearray(raw)
            w64(fixed, 4, len(fixed) - 32)
            return bytes(fixed)
        return patch_wrapped_payload(original_asset, raw)
    raise PakError('Unbekannter Modus')

def extract_child_inner_for_replace(child, replacement_path, mode):
    raw = Path(replacement_path).read_bytes()
    if child['inner_kind'] == 'TXTR' and raw.startswith(b'\x89PNG\r\n\x1a\n'):
        from txtr_repack import png_to_txtr_asset
        return png_to_txtr_asset(child['inner'], replacement_path)
    normalized_csmp = normalize_csmp_replacement(raw, child['inner'])
    if normalized_csmp is not None:
        return normalized_csmp
    chosen_mode = mode
    if chosen_mode == 'auto':
        wrapped = parse_segmented_payload(raw)
        if wrapped and len(wrapped['children']) == 1:
            chosen_mode = 'whole'
        else:
            chosen_mode = 'payload'
    if chosen_mode == 'whole':
        wrapped = parse_segmented_payload(raw)
        if wrapped and len(wrapped['children']) == 1:
            item = wrapped['children'][0]
            if item['segment_tag'] != child['segment_tag']:
                raise PakError(f'Falscher Sprachblock: erwartet {child["segment_tag"]}, gefunden {item["segment_tag"]}')
            if item['inner_kind'] != child['inner_kind']:
                raise PakError(f'Falscher Inhaltstyp: erwartet {child["inner_kind"]}, gefunden {item["inner_kind"]}')
            return item['inner']
    inner_kind = detect_payload_kind(raw)
    if child['inner_kind'] and inner_kind and inner_kind != child['inner_kind']:
        raise PakError(f'Falscher Inhaltstyp: erwartet {child["inner_kind"]}, gefunden {inner_kind}')
    if child['inner_kind'] == 'MSBT' and not raw.startswith(b'MsgStdBn'):
        raise PakError('Erwartet eine rohe MSBT-Datei mit MsgStdBn am Anfang')
    return raw

def build_bundle_replaced_asset(parsed, entry, child_replacements):
    asset = get_entry_asset(parsed, entry)
    payload = get_entry_payload(asset)
    bundle = entry.get('bundle') or parse_segmented_payload(payload)
    if bundle is None:
        raise PakError('Ausgewählter Eintrag ist kein ausklappbares Bundle')
    replacement_map = {}
    for child in bundle['children']:
        if child['index'] in child_replacements:
            spec = child_replacements[child['index']]
            replacement_map[child['index']] = extract_child_inner_for_replace(child, spec['path'], spec['mode'])
    new_payload = build_segmented_payload(bundle, replacement_map)
    rebuilt_bundle = parse_segmented_payload(new_payload)
    if rebuilt_bundle is None or len(rebuilt_bundle['children']) != len(bundle['children']):
        raise PakError('Neu gebautes Bundle ist ungültig')
    return patch_wrapped_payload(asset, new_payload)

GPU_MARKERS = {
    0x0D000000: 'zlib',
    0x0C000000: 'kind_0c',
    0x04000000: 'kind_04',
    0x01000000: 'kind_01',
    0x09000000: 'kind_09',
    0x00000000: 'kind_00'
}

REFERENCE_META_TYPES = {'GENP', 'SWSH'}
MODEL_META_TYPES = {'CMDL', 'SMDL', 'WMDL'}

def parse_asset_chunks(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM':
        return []
    chunks = []
    p = 32
    while p < len(asset):
        if p + 24 > len(asset):
            raise PakError(f'Asset-Chunk abgeschnitten bei 0x{p:X}')
        chunk = parse_chunk(asset, p)
        chunks.append(chunk)
        p = chunk['next_off']
    if p != len(asset):
        raise PakError('Asset endet nicht exakt auf Chunk-Grenze')
    return chunks

def find_asset_chunk(asset, chunk_tag):
    for chunk in parse_asset_chunks(asset):
        if chunk['tag'] == chunk_tag:
            return chunk
    return None

def decompress_zlib_size(raw):
    try:
        return len(zlib.decompress(raw))
    except Exception as e:
        raise PakError(f'Zlib-Daten konnten nicht gelesen werden: {e}')

def parse_gpu_segments(payload):
    segments = []
    p = 0
    while p < len(payload):
        if p + 4 > len(payload):
            raise PakError('GPU-Payload endet mitten im Marker')
        kind = be32(payload, p)
        if kind == 0x0D000000:
            obj = zlib.decompressobj()
            try:
                out = obj.decompress(payload[p+4:])
            except Exception as e:
                raise PakError(f'GPU-Zlib-Block bei 0x{p:X} ist ungültig: {e}')
            if not obj.eof:
                raise PakError(f'GPU-Zlib-Block bei 0x{p:X} endet nicht sauber')
            used = len(payload[p+4:]) - len(obj.unused_data)
            size = 4 + used
            segments.append({
                'kind': kind,
                'kind_name': GPU_MARKERS[kind],
                'off': p,
                'size': size,
                'decomp_size': len(out),
                'decomp_known': True
            })
            p += size
            continue
        next_positions = []
        for marker in GPU_MARKERS:
            idx = payload.find(marker.to_bytes(4, 'big'), p + 4)
            if idx != -1:
                next_positions.append(idx)
        next_off = min(next_positions) if next_positions else len(payload)
        size = next_off - p
        decomp_size = None
        decomp_known = False
        if kind == 0x00000000:
            decomp_size = max(size - 4, 0)
            decomp_known = True
        segments.append({
            'kind': kind,
            'kind_name': GPU_MARKERS.get(kind, f'0x{kind:08X}'),
            'off': p,
            'size': size,
            'decomp_size': decomp_size,
            'decomp_known': decomp_known
        })
        p = next_off
    return segments

def parse_reference_meta(blob):
    if len(blob) < 8:
        return None
    if be32(blob, 0) != 1:
        return None
    count = be32(blob, 4)
    if len(blob) != 8 + count * 20:
        return None
    refs = []
    p = 8
    for _ in range(count):
        refs.append({'type': tag4(blob, p), 'uuid_hex': blob[p+4:p+20].hex()})
        p += 20
    return {'count': count, 'refs': refs}

def parse_txtr_meta(blob):
    if len(blob) != 40:
        return None
    words = [be32(blob, i) for i in range(0, 40, 4)]
    if words[0] != 4:
        return None
    return {
        'subtype': words[1],
        'gpu_chunk_off': words[2],
        'const_512': words[3],
        'gpu_payload_off': words[4],
        'gpu_comp_size_a': words[5],
        'const_1': words[6],
        'gpu_decomp_size': words[7],
        'gpu_comp_size_b': words[8],
        'tail': words[9]
    }

def parse_mtrl_meta(blob):
    if len(blob) != 20:
        return None
    words = [be32(blob, i) for i in range(0, 20, 4)]
    if words[0] != 1:
        return None
    return {
        'tag': words[0],
        'const_12': words[1],
        'comp_size': words[2],
        'decomp_size': words[3],
        'const_32': words[4]
    }

def parse_csmp_meta(blob):
    if len(blob) != 8:
        return None
    return {
        'marker': be32(blob, 0),
        'data_size': be32(blob, 4)
    }
def format_uuid_hex(hex_str):
    if not hex_str or len(hex_str) != 32:
        return hex_str
    return f'{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}'

def signed32(value):
    return value - 0x100000000 if value >= 0x80000000 else value

def parse_mtrl_asset_info(asset):
    if len(asset) < 32 or asset[:4] != b'RFRM' or tag4(asset, 20) != 'MTRL':
        raise PakError('Keine MTRL-Ressource')
    payload = get_entry_payload(asset)
    outer = zlib.decompress(payload)
    info = {
        'outer_comp_size': len(payload),
        'outer_decomp_size': len(outer),
        'shader_kind': '',
        'expt_table_size': 0,
        'expt_entry_count': 0,
        'inner_root_version_a': None,
        'inner_root_version_b': None,
        'snvn_size': None,
        'snvn_version': None,
        'snvn_prefix_size': None,
        'shader_blob_size': None,
        'shader_blob_sha1': ''
    }
    if len(outer) >= 24 and outer[:4] == b'EXPT':
        table_size = be64(outer, 4)
        info['expt_table_size'] = table_size
        if table_size % 8 == 0:
            info['expt_entry_count'] = table_size // 8
        if len(outer) >= 28:
            info['shader_kind'] = tag4(outer, 24)
        inner_rfrm_off = 24 + table_size
        if inner_rfrm_off + 32 <= len(outer) and outer[inner_rfrm_off:inner_rfrm_off+4] == b'RFRM':
            info['inner_root_version_a'] = be32(outer, inner_rfrm_off + 24)
            info['inner_root_version_b'] = be32(outer, inner_rfrm_off + 28)
            snvn_off = inner_rfrm_off + 32
            if snvn_off + 24 <= len(outer) and tag4(outer, snvn_off) == 'SNVN':
                info['snvn_size'] = be64(outer, snvn_off + 4)
                info['snvn_version'] = be32(outer, snvn_off + 12)
                snvn_payload_off = snvn_off + 24
                shader_zlib_off = outer.find(b'\x78\xda', snvn_payload_off)
                if shader_zlib_off != -1:
                    info['snvn_prefix_size'] = shader_zlib_off - snvn_payload_off
                    shader_blob = zlib.decompress(outer[shader_zlib_off:])
                    info['shader_blob_size'] = len(shader_blob)
                    info['shader_blob_sha1'] = sha1_bytes(shader_blob)
    return info

def mtrl_prop_value_size(prop):
    if prop.endswith('TXTR'):
        return 36
    if prop.endswith('COLR'):
        return 16
    if prop.endswith('SCLR'):
        return 4
    if prop.endswith('INT4'):
        return 16
    return None

def parse_model_material_chunk(payload):
    if len(payload) < 4:
        return []
    p = 0
    count = be32(payload, p)
    p += 4
    materials = []
    for idx in range(count):
        if p + 4 > len(payload):
            raise PakError('Modell-MTRL ist vor der Namenslänge abgeschnitten')
        name_len = be32(payload, p)
        p += 4
        if p + name_len + 28 > len(payload):
            raise PakError('Modell-MTRL ist im Material-Kopf abgeschnitten')
        name = payload[p:p+name_len].split(b'\x00', 1)[0].decode('utf-8', 'replace')
        p += name_len
        uuid_hex = payload[p:p+16].hex()
        p += 16
        mat_type = tag4(payload, p)
        p += 4
        variant = be32(payload, p)
        p += 4
        prop_count = be32(payload, p)
        p += 4
        if p + prop_count * 8 > len(payload):
            raise PakError('Modell-MTRL ist in der Eigenschaftsliste abgeschnitten')
        prop_tags = [payload[p+i*8:p+(i+1)*8].decode('ascii', 'replace') for i in range(prop_count)]
        p += prop_count * 8
        txtr_refs = []
        colors = {}
        scalars = {}
        ints = {}
        values = []
        for prop in prop_tags:
            if p + 8 > len(payload):
                raise PakError('Modell-MTRL ist vor einem Eigenschaftswert abgeschnitten')
            repeated_tag = payload[p:p+8].decode('ascii', 'replace')
            p += 8
            if repeated_tag != prop:
                raise PakError(f'Modell-MTRL Eigenschaft passt nicht: erwartet {prop}, gefunden {repeated_tag}')
            value_size = mtrl_prop_value_size(prop)
            if value_size is None:
                raise PakError(f'Modell-MTRL Eigenschaft wird noch nicht unterstützt: {prop}')
            if p + value_size > len(payload):
                raise PakError(f'Modell-MTRL Wert ist abgeschnitten: {prop}')
            if prop.endswith('TXTR'):
                ref_uuid_hex = payload[p:p+16].hex()
                extra_words = [be32(payload, p + 16 + i * 4) for i in range(5)]
                item = {'tag': prop, 'kind': 'txtr', 'uuid_hex': ref_uuid_hex, 'extra_words': extra_words}
                txtr_refs.append(item)
                values.append(item)
            elif prop.endswith('COLR'):
                value = struct.unpack('>4f', payload[p:p+16])
                item = {'tag': prop, 'kind': 'color', 'value': value}
                colors[prop] = value
                values.append(item)
            elif prop.endswith('SCLR'):
                value = struct.unpack('>f', payload[p:p+4])[0]
                item = {'tag': prop, 'kind': 'scalar', 'value': value}
                scalars[prop] = value
                values.append(item)
            else:
                value = struct.unpack('>4I', payload[p:p+16])
                item = {'tag': prop, 'kind': 'int4', 'value': value}
                ints[prop] = value
                values.append(item)
            p += value_size
        materials.append({
            'index': idx,
            'name': name,
            'uuid_hex': uuid_hex,
            'mat_type': mat_type,
            'variant': variant,
            'prop_tags': prop_tags,
            'values': values,
            'txtr_refs': txtr_refs,
            'colors': colors,
            'scalars': scalars,
            'ints': ints
        })
    tail = payload[p:]
    if any(b != 0 for b in tail):
        raise PakError('Modell-MTRL hat unerwartete Restdaten')
    return materials

def parse_model_materials_from_asset(asset):
    chunk = find_asset_chunk(asset, 'MTRL')
    if chunk is None:
        return []
    return parse_model_material_chunk(asset[chunk['payload_off']:chunk['payload_end']])

def build_model_mtrl_ref_map(entries, data):
    model_to_mtrls = {}
    for entry in entries:
        entry['model_materials'] = []
        if entry['type'] not in MODEL_META_TYPES and entry['type'] != 'CHAR':
            continue
        asset = data[entry['offset']:entry['offset'] + entry['size']]
        try:
            materials = parse_model_materials_from_asset(asset)
        except Exception:
            continue
        if not materials:
            continue
        entry['model_materials'] = materials
        model_to_mtrls[entry['uuid_hex']] = materials
    return model_to_mtrls

def build_uuid_entry_map(entries):
    return {entry['uuid_hex']: entry for entry in entries}

def make_txtr_ref_label(ref, txtr_entry=None):
    txtr_name = ''
    txtr_size = ''
    if txtr_entry is not None:
        txtr_name = txtr_entry.get('display_name') or txtr_entry.get('name') or txtr_entry['uuid_hex']
        txtr_size = f' | Größe {txtr_entry["size"]}'
    extra = ', '.join(str(signed32(x)) for x in ref['extra_words'])
    if txtr_name:
        return f'  TXTR | {txtr_name} | {format_uuid_hex(ref["uuid_hex"])} | {ref["tag"]}{txtr_size} | Zusatz [{extra}]'
    return f'  TXTR | {format_uuid_hex(ref["uuid_hex"])} | {ref["tag"]} | Zusatz [{extra}]'

def format_txtr_ref_lines(ref, txtr_entry=None):
    lines = []
    lines.append(f'TXTR-Ref-Tag: {ref["tag"]}')
    lines.append(f'TXTR-UUID: {format_uuid_hex(ref["uuid_hex"])}')
    lines.append(f'Zusatz: ({", ".join(str(signed32(x)) for x in ref["extra_words"])})')
    if txtr_entry is not None:
        lines.append('')
        lines.append(f'Verlinktes TXTR: #{txtr_entry["index"]}')
        lines.append(f'TXTR-Name: {txtr_entry.get("display_name") or txtr_entry.get("name") or txtr_entry["uuid_hex"]}')
        lines.append(f'TXTR-UUID: {txtr_entry["uuid_hex"]}')
        lines.append(f'TXTR-Größe: {txtr_entry["size"]}')
        lines.append('')
        lines.extend(format_meta_lines(txtr_entry))
    else:
        lines.append('')
        lines.append('Verlinktes TXTR im aktuellen PAK nicht gefunden')
    return lines

def format_mtrl_info_lines(entry, parsed=None):
    lines = []
    info = entry.get('mtrl_info')
    if info is not None:
        lines.append('MTRL-Analyse:')
        if info.get('shader_kind'):
            lines.append(f'- Shader-Familie: {info["shader_kind"]}')
        if info.get('expt_entry_count'):
            lines.append(f'- EXPT-Einträge: {info["expt_entry_count"]}')
        if info.get('expt_table_size'):
            lines.append(f'- EXPT-Tabellengröße: {info["expt_table_size"]}')
        lines.append(f'- Außen gepackt: {info["outer_comp_size"]}')
        lines.append(f'- Außen entpackt: {info["outer_decomp_size"]}')
        if info.get('inner_root_version_a') is not None:
            lines.append(f'- Inneres MTRL: Version {info["inner_root_version_a"]} / {info["inner_root_version_b"]}')
        if info.get('snvn_size') is not None:
            lines.append(f'- SNVN-Größe: {info["snvn_size"]}')
        if info.get('snvn_version') is not None:
            lines.append(f'- SNVN-Version: {info["snvn_version"]}')
        if info.get('snvn_prefix_size') is not None:
            lines.append(f'- SNVN-Vorlauf bis Shader-Zlib: {info["snvn_prefix_size"]} Bytes')
        if info.get('shader_blob_size') is not None:
            lines.append(f'- Innerer Shader entpackt: {info["shader_blob_size"]}')
        if info.get('shader_blob_sha1'):
            lines.append(f'- Innerer Shader-SHA1: {info["shader_blob_sha1"]}')
    else:
        lines.append('MTRL-Analyse: konnte nicht gelesen werden')
    return lines

def format_model_material_lines(material):
    lines = []
    lines.append(f'Material-Slot: #{material["index"]} {material["name"]}')
    lines.append(f'Slot-UUID: {format_uuid_hex(material["uuid_hex"])}')
    lines.append(f'Material-Typ: {material["mat_type"]}')
    lines.append(f'Variante/Flag: {material["variant"]}')
    lines.append(f'Eigenschaften: {len(material["prop_tags"])}')
    if material['txtr_refs']:
        lines.append('Textur-Refs:')
        for ref in material['txtr_refs']:
            extra = ', '.join(str(signed32(x)) for x in ref['extra_words'])
            lines.append(f'- {ref["tag"]}: {format_uuid_hex(ref["uuid_hex"])} | Zusatz [{extra}]')
    if material['colors']:
        lines.append('Farben:')
        for tag, value in material['colors'].items():
            lines.append(f'- {tag}: ({value[0]:.6g}, {value[1]:.6g}, {value[2]:.6g}, {value[3]:.6g})')
    if material['scalars']:
        lines.append('Skalare:')
        for tag, value in material['scalars'].items():
            lines.append(f'- {tag}: {value:.6g}')
    if material['ints']:
        lines.append('INT4-Werte:')
        for tag, value in material['ints'].items():
            lines.append(f'- {tag}: ({", ".join(str(signed32(x)) for x in value)})')
    return lines

def make_mtrl_ref_label(material):
    return f'  MTRL | {format_uuid_hex(material["uuid_hex"])} | Slot #{material["index"]} {material["name"]} | {material["mat_type"]} | Flag {material["variant"]}'

def detect_model_meta_variant(blob, asset):
    words = [be32(blob, i) for i in range(0, len(blob), 4)]
    if len(words) < 8 or words[0] != 4:
        return None
    gpu = find_asset_chunk(asset, 'GPU ')
    if gpu is None:
        return None
    segments = parse_gpu_segments(asset[gpu['payload_off']:gpu['payload_end']])
    n = len(segments)
    if n < 2:
        return None
    if len(words) == 8 + (4 * n - 1) and words[2] == 1 and words[6] == 0 and words[7] == 0:
        if words[5] == n - 1:
            return 'A'
        if words[5] == n - 2:
            return 'B'
    if len(words) == 10 + (4 * n - 1) and words[2] == 2 and words[8] == 0 and words[9] == 0 and words[7] == n - 2:
        return 'C'
    if len(words) == 12 + (4 * n - 1) and words[2] == 3 and words[10] == 0 and words[11] == 0 and words[9] == n - 2:
        return 'D'
    return None

def parse_model_meta_template(blob, asset):
    words = [be32(blob, i) for i in range(0, len(blob), 4)]
    variant = detect_model_meta_variant(blob, asset)
    if variant is None:
        return None
    gpu = find_asset_chunk(asset, 'GPU ')
    gpu_payload_off = gpu['payload_off']
    segments = parse_gpu_segments(asset[gpu_payload_off:gpu['payload_end']])
    n = len(segments)
    template = {
        'variant': variant,
        'old_segments': segments,
        'old_decomp_sizes': [],
        'group_a_mid_markers': [],
        'group_a_final_pair': None,
        'group_b_first_marker': None,
        'group_b_mid_markers': [],
        'group_b_final_pair': None,
        'final_regular_marker': None,
        'final_single_pair': None,
        'group_a_count': 0,
        'group_b_count': 0,
        'group_c_count': 0
    }
    if variant == 'A':
        start = 8
        template['group_a_count'] = n
        idx = start
        template['old_decomp_sizes'].append(words[idx+1])
        if segments[0]['off'] != 0 or segments[0]['size'] != words[idx]:
            raise PakError('Modell-META A passt nicht zum alten Asset')
        idx += 2
        for seg_index in range(1, n - 1):
            marker = words[idx]
            off = words[idx+1]
            size = words[idx+2]
            dec = words[idx+3]
            seg = segments[seg_index]
            if seg['off'] != off or seg['size'] != size:
                raise PakError('Modell-META A Segmentliste passt nicht zum alten Asset')
            template['group_a_mid_markers'].append(marker)
            template['old_decomp_sizes'].append(dec)
            idx += 4
        final_pair = (words[idx], words[idx+1])
        off = words[idx+2]
        size = words[idx+3]
        dec = words[idx+4]
        seg = segments[-1]
        if seg['off'] != off or seg['size'] != size:
            raise PakError('Modell-META A Finalsegment passt nicht zum alten Asset')
        template['group_a_final_pair'] = final_pair
        template['old_decomp_sizes'].append(dec)
        return template
    if variant == 'B':
        start = 8
        group_a_count = n - 1
        template['group_a_count'] = group_a_count
        template['group_c_count'] = 1
        idx = start
        template['old_decomp_sizes'].append(words[idx+1])
        if segments[0]['off'] != 0 or segments[0]['size'] != words[idx]:
            raise PakError('Modell-META B passt nicht zum alten Asset')
        idx += 2
        for seg_index in range(1, group_a_count - 1):
            marker = words[idx]
            off = words[idx+1]
            size = words[idx+2]
            dec = words[idx+3]
            seg = segments[seg_index]
            if seg['off'] != off or seg['size'] != size:
                raise PakError('Modell-META B Gruppe A passt nicht zum alten Asset')
            template['group_a_mid_markers'].append(marker)
            template['old_decomp_sizes'].append(dec)
            idx += 4
        final_pair = (words[idx], words[idx+1])
        off = words[idx+2]
        size = words[idx+3]
        dec = words[idx+4]
        seg = segments[group_a_count - 1]
        if seg['off'] != off or seg['size'] != size:
            raise PakError('Modell-META B Gruppenende passt nicht zum alten Asset')
        template['group_a_final_pair'] = final_pair
        template['old_decomp_sizes'].append(dec)
        idx += 5
        marker = words[idx]
        off = words[idx+1]
        size = words[idx+2]
        dec = words[idx+3]
        seg = segments[-1]
        if seg['off'] != off or seg['size'] != size:
            raise PakError('Modell-META B letztes Segment passt nicht zum alten Asset')
        template['final_regular_marker'] = marker
        template['old_decomp_sizes'].append(dec)
        return template
    if variant == 'C':
        split_off = words[3]
        group_a_count = sum(1 for seg in segments if seg['off'] < split_off)
        group_b_count = n - group_a_count
        template['group_a_count'] = group_a_count
        template['group_b_count'] = group_b_count
        idx = 10
        template['old_decomp_sizes'].append(words[idx+1])
        if segments[0]['off'] != 0 or segments[0]['size'] != words[idx]:
            raise PakError('Modell-META C passt nicht zum alten Asset')
        idx += 2
        for seg_index in range(1, group_a_count - 1):
            marker = words[idx]
            off = words[idx+1]
            size = words[idx+2]
            dec = words[idx+3]
            seg = segments[seg_index]
            if seg['off'] != off or seg['size'] != size:
                raise PakError('Modell-META C Gruppe A passt nicht zum alten Asset')
            template['group_a_mid_markers'].append(marker)
            template['old_decomp_sizes'].append(dec)
            idx += 4
        final_pair = (words[idx], words[idx+1])
        off = words[idx+2]
        size = words[idx+3]
        dec = words[idx+4]
        seg = segments[group_a_count - 1]
        if seg['off'] != off or seg['size'] != size:
            raise PakError('Modell-META C Ende Gruppe A passt nicht zum alten Asset')
        template['group_a_final_pair'] = final_pair
        template['old_decomp_sizes'].append(dec)
        idx += 5
        first_marker = words[idx]
        size = words[idx+1]
        dec = words[idx+2]
        seg = segments[group_a_count]
        if seg['off'] != split_off or size != seg['size']:
            raise PakError('Modell-META C Start Gruppe B passt nicht zum alten Asset')
        template['group_b_first_marker'] = first_marker
        template['old_decomp_sizes'].append(dec)
        idx += 3
        for local_index in range(1, group_b_count - 1):
            marker = words[idx]
            off = words[idx+1]
            size = words[idx+2]
            dec = words[idx+3]
            seg = segments[group_a_count + local_index]
            rel_off = seg['off'] - split_off
            if rel_off != off or seg['size'] != size:
                raise PakError('Modell-META C Gruppe B passt nicht zum alten Asset')
            template['group_b_mid_markers'].append(marker)
            template['old_decomp_sizes'].append(dec)
            idx += 4
        final_pair = (words[idx], words[idx+1])
        off = words[idx+2]
        size = words[idx+3]
        dec = words[idx+4]
        seg = segments[-1]
        rel_off = seg['off'] - split_off
        if rel_off != off or seg['size'] != size:
            raise PakError('Modell-META C Ende Gruppe B passt nicht zum alten Asset')
        template['group_b_final_pair'] = final_pair
        template['old_decomp_sizes'].append(dec)
        return template
    split_off = words[3]
    final_size = words[7]
    final_abs = words[8]
    final_rel = final_abs - gpu_payload_off
    group_a_count = sum(1 for seg in segments if seg['off'] < split_off)
    if not segments or segments[-1]['off'] != final_rel or segments[-1]['size'] != final_size:
        raise PakError('Modell-META D Finalsegment passt nicht zum alten Asset')
    group_b_count = n - group_a_count - 1
    template['group_a_count'] = group_a_count
    template['group_b_count'] = group_b_count
    template['group_c_count'] = 1
    idx = 12
    template['old_decomp_sizes'].append(words[idx+1])
    if segments[0]['off'] != 0 or segments[0]['size'] != words[idx]:
        raise PakError('Modell-META D passt nicht zum alten Asset')
    idx += 2
    for seg_index in range(1, group_a_count - 1):
        marker = words[idx]
        off = words[idx+1]
        size = words[idx+2]
        dec = words[idx+3]
        seg = segments[seg_index]
        if seg['off'] != off or seg['size'] != size:
            raise PakError('Modell-META D Gruppe A passt nicht zum alten Asset')
        template['group_a_mid_markers'].append(marker)
        template['old_decomp_sizes'].append(dec)
        idx += 4
    final_pair = (words[idx], words[idx+1])
    off = words[idx+2]
    size = words[idx+3]
    dec = words[idx+4]
    seg = segments[group_a_count - 1]
    if seg['off'] != off or seg['size'] != size:
        raise PakError('Modell-META D Ende Gruppe A passt nicht zum alten Asset')
    template['group_a_final_pair'] = final_pair
    template['old_decomp_sizes'].append(dec)
    idx += 5
    first_marker = words[idx]
    size = words[idx+1]
    dec = words[idx+2]
    seg = segments[group_a_count]
    if seg['off'] != split_off or size != seg['size']:
        raise PakError('Modell-META D Start Gruppe B passt nicht zum alten Asset')
    template['group_b_first_marker'] = first_marker
    template['old_decomp_sizes'].append(dec)
    idx += 3
    for local_index in range(1, group_b_count - 1):
        marker = words[idx]
        off = words[idx+1]
        size = words[idx+2]
        dec = words[idx+3]
        seg = segments[group_a_count + local_index]
        rel_off = seg['off'] - split_off
        if rel_off != off or seg['size'] != size:
            raise PakError('Modell-META D Gruppe B passt nicht zum alten Asset')
        template['group_b_mid_markers'].append(marker)
        template['old_decomp_sizes'].append(dec)
        idx += 4
    final_pair = (words[idx], words[idx+1])
    off = words[idx+2]
    size = words[idx+3]
    dec = words[idx+4]
    seg = segments[group_a_count + group_b_count - 1]
    rel_off = seg['off'] - split_off
    if rel_off != off or seg['size'] != size:
        raise PakError('Modell-META D Ende Gruppe B passt nicht zum alten Asset')
    template['group_b_final_pair'] = final_pair
    template['old_decomp_sizes'].append(dec)
    idx += 5
    final_pair = (words[idx], words[idx+1])
    size = words[idx+2]
    dec = words[idx+3]
    seg = segments[-1]
    if seg['size'] != size:
        raise PakError('Modell-META D letztes Segment passt nicht zum alten Asset')
    template['final_single_pair'] = final_pair
    template['old_decomp_sizes'].append(dec)
    return template

def infer_txtr_subtype(asset, old_blob=None):
    if old_blob is not None:
        parsed = parse_txtr_meta(old_blob)
        if parsed is not None:
            return parsed['subtype']
    head = find_asset_chunk(asset, 'HEAD')
    if head is None:
        return 0
    payload = asset[head['payload_off']:head['payload_end']]
    if len(payload) < 8:
        return 0
    first = be32(payload, 0)
    second = be32(payload, 4)
    if head['size'] != 44:
        return 0
    if first == 5:
        return 1
    if second in (12, 58):
        return 0
    return 2

def build_txtr_meta_blob(asset, old_blob=None):
    gpu = find_asset_chunk(asset, 'GPU ')
    if gpu is None:
        raise PakError('TXTR ohne GPU-Chunk kann kein META bekommen')
    subtype = infer_txtr_subtype(asset, old_blob)
    gpu_payload = asset[gpu['payload_off']:gpu['payload_end']]
    if len(gpu_payload) >= 4 and be32(gpu_payload, 0) == 0:
        decomp_size = max(len(gpu_payload) - 4, 0)
    else:
        try:
            decomp_size = decompress_zlib_size(gpu_payload)
        except PakError:
            old_view = parse_txtr_meta(old_blob) if old_blob is not None else None
            if old_view is None or old_view['gpu_comp_size_a'] != gpu['size']:
                raise
            decomp_size = old_view['gpu_decomp_size']
    words = [4, subtype, gpu['off'], 512, gpu['payload_off'], gpu['size'], 1, decomp_size, gpu['size'], 0]
    return b''.join(int(x).to_bytes(4, 'big') for x in words)

def build_mtrl_meta_blob(asset):
    payload = get_entry_payload(asset)
    decomp_size = decompress_zlib_size(payload)
    words = [1, 12, len(payload), decomp_size, 32]
    return b''.join(int(x).to_bytes(4, 'big') for x in words)

def build_csmp_meta_blob(asset):
    data_chunk = find_asset_chunk(asset, 'DATA')
    if data_chunk is None:
        raise PakError('CSMP ohne DATA-Chunk kann kein META bekommen')
    return be32(b'\x00U\x00m', 0).to_bytes(4, 'big') + int(data_chunk['size']).to_bytes(4, 'big')

def resolve_model_segment_decomp(old_seg, new_seg, old_decomp):
    if new_seg['decomp_known']:
        return new_seg['decomp_size']
    if old_seg['kind'] == new_seg['kind'] and old_seg['size'] == new_seg['size']:
        return old_decomp
    raise PakError(f'GPU-Segment {new_seg["kind_name"]} hat unbekannte Entpackgröße und änderte seine Größe von {old_seg["size"]} auf {new_seg["size"]}')

def build_model_group_a(segments, decomp_sizes, mid_markers, final_pair):
    words = [segments[0]['size'], decomp_sizes[0]]
    for seg, dec, marker in zip(segments[1:-1], decomp_sizes[1:-1], mid_markers):
        words.extend([marker, seg['off'], seg['size'], dec])
    words.extend([final_pair[0], final_pair[1], segments[-1]['off'], segments[-1]['size'], decomp_sizes[-1]])
    return words

def build_model_group_b(segments, decomp_sizes, first_marker, mid_markers, final_pair, rel_base):
    if not segments:
        return []
    words = [first_marker, segments[0]['size'], decomp_sizes[0]]
    for seg, dec, marker in zip(segments[1:-1], decomp_sizes[1:-1], mid_markers):
        words.extend([marker, seg['off'] - rel_base, seg['size'], dec])
    words.extend([final_pair[0], final_pair[1], segments[-1]['off'] - rel_base, segments[-1]['size'], decomp_sizes[-1]])
    return words

def build_model_meta_blob(entry, old_asset, new_asset):
    old_blob = entry['meta']['blob'] if entry.get('meta') else None
    if not old_blob:
        raise PakError(f'{entry["type"]} hat kein Ausgangs-META')
    template = parse_model_meta_template(old_blob, old_asset)
    if template is None:
        raise PakError(f'{entry["type"]} META-Variante wird noch nicht sicher neu aufgebaut')
    old_gpu = find_asset_chunk(old_asset, 'GPU ')
    new_gpu = find_asset_chunk(new_asset, 'GPU ')
    if new_gpu is None:
        raise PakError(f'{entry["type"]} ohne GPU-Chunk kann kein META bekommen')
    old_segments = template['old_segments']
    new_segments = parse_gpu_segments(new_asset[new_gpu['payload_off']:new_gpu['payload_end']])
    if len(old_segments) != len(new_segments):
        raise PakError(f'{entry["type"]} änderte die Zahl der GPU-Segmente von {len(old_segments)} auf {len(new_segments)}')
    decomp_sizes = []
    for i, (old_seg, new_seg, old_dec) in enumerate(zip(old_segments, new_segments, template['old_decomp_sizes'])):
        if old_seg['kind'] != new_seg['kind']:
            raise PakError(f'{entry["type"]} änderte den GPU-Segmenttyp an Position {i} von {old_seg["kind_name"]} auf {new_seg["kind_name"]}')
        decomp_sizes.append(resolve_model_segment_decomp(old_seg, new_seg, old_dec))
    variant = template['variant']
    total_size = new_gpu['size']
    payload_off = new_gpu['payload_off']
    header = []
    body = []
    if variant == 'A':
        header = [4, new_gpu['off'], 1, total_size, payload_off, len(new_segments) - 1, 0, 0]
        body = build_model_group_a(new_segments, decomp_sizes, template['group_a_mid_markers'], template['group_a_final_pair'])
    elif variant == 'B':
        group_a_count = template['group_a_count']
        header = [4, new_gpu['off'], 1, total_size, payload_off, len(new_segments) - 2, 0, 0]
        body = build_model_group_a(new_segments[:group_a_count], decomp_sizes[:group_a_count], template['group_a_mid_markers'], template['group_a_final_pair'])
        last_seg = new_segments[-1]
        body.extend([template['final_regular_marker'], last_seg['off'], last_seg['size'], decomp_sizes[-1]])
    elif variant == 'C':
        group_a_count = template['group_a_count']
        split_off = new_segments[group_a_count]['off']
        header = [4, new_gpu['off'], 2, split_off, payload_off, total_size - split_off, payload_off + split_off, len(new_segments) - 2, 0, 0]
        body = build_model_group_a(new_segments[:group_a_count], decomp_sizes[:group_a_count], template['group_a_mid_markers'], template['group_a_final_pair'])
        body.extend(build_model_group_b(new_segments[group_a_count:], decomp_sizes[group_a_count:], template['group_b_first_marker'], template['group_b_mid_markers'], template['group_b_final_pair'], split_off))
    else:
        group_a_count = template['group_a_count']
        group_b_count = template['group_b_count']
        split_off = new_segments[group_a_count]['off']
        final_seg = new_segments[-1]
        final_size = final_seg['size']
        header = [4, new_gpu['off'], 3, split_off, payload_off, total_size - split_off - final_size, payload_off + split_off, final_size, payload_off + final_seg['off'], len(new_segments) - 2, 0, 0]
        body = build_model_group_a(new_segments[:group_a_count], decomp_sizes[:group_a_count], template['group_a_mid_markers'], template['group_a_final_pair'])
        middle_segments = new_segments[group_a_count:group_a_count + group_b_count]
        middle_decomp = decomp_sizes[group_a_count:group_a_count + group_b_count]
        body.extend(build_model_group_b(middle_segments, middle_decomp, template['group_b_first_marker'], template['group_b_mid_markers'], template['group_b_final_pair'], split_off))
        body.extend([template['final_single_pair'][0], template['final_single_pair'][1], final_size, decomp_sizes[-1]])
    return b''.join(int(x).to_bytes(4, 'big') for x in header + body)

def build_entry_meta_blob(parsed, entry, old_asset, new_asset):
    if not entry.get('has_meta'):
        return None
    old_blob = entry['meta']['blob'] if entry.get('meta') else None
    if old_blob is not None and old_asset == new_asset:
        return old_blob
    typ = entry['type']
    if typ == 'TXTR':
        return build_txtr_meta_blob(new_asset, old_blob)
    if typ == 'MTRL':
        return build_mtrl_meta_blob(new_asset)
    if typ == 'CSMP':
        return build_csmp_meta_blob(new_asset)
    if typ in REFERENCE_META_TYPES:
        if old_blob is None:
            raise PakError(f'{typ} hat kein altes META zum Erhalten')
        return old_blob
    if typ in MODEL_META_TYPES:
        return build_model_meta_blob(entry, old_asset, new_asset)
    if old_blob is not None:
        return old_blob
    return None

def build_adir_payload(entries, offsets_by_index):
    out = bytearray()
    out += len(entries).to_bytes(4, 'big')
    for entry in entries:
        off, size = offsets_by_index[entry['index']]
        out += entry['type'].encode('ascii')
        out += entry['uuid_bytes']
        out += int(off).to_bytes(8, 'big')
        out += int(size).to_bytes(8, 'big')
    return bytes(out)

def build_meta_payload(entries, meta_blobs):
    items = []
    for entry in entries:
        blob = meta_blobs.get(entry['uuid_hex'])
        if blob is None:
            continue
        items.append((entry['uuid_bytes'], blob))
    out = bytearray()
    out += len(items).to_bytes(4, 'big')
    table_size = len(items) * 20
    rel = 4 + table_size
    blob_parts = []
    for uid_bytes, blob in items:
        out += uid_bytes
        out += int(rel).to_bytes(4, 'big')
        blob_parts.append(len(blob).to_bytes(4, 'big') + blob)
        rel += 4 + len(blob)
    for part in blob_parts:
        out += part
    return bytes(out)

def build_chunk_raw(chunk, payload):
    raw = bytearray(chunk['header'])
    w64(raw, 4, len(payload))
    return bytes(raw) + payload

def build_tocc_bytes(parsed, entries, offsets_by_index, meta_blobs):
    new_chunks = []
    for chunk in parsed['chunks']:
        if chunk['tag'] == 'ADIR':
            payload = build_adir_payload(entries, offsets_by_index)
            new_chunks.append(build_chunk_raw(chunk, payload))
        elif chunk['tag'] == 'META':
            payload = build_meta_payload(entries, meta_blobs)
            new_chunks.append(build_chunk_raw(chunk, payload))
        else:
            new_chunks.append(chunk['raw'])
    tocc_body = b''.join(new_chunks)
    tocc = bytearray(parsed['tocc_root']['header'])
    w64(tocc, 4, len(tocc_body))
    return bytes(tocc) + tocc_body

def parse_pak_from_data(data, virtual_path='<memory>'):
    if len(data) < 64:
        raise PakError('Datei zu klein')
    root = parse_rfrm_header(data, 0, 'Äußeres RFRM')
    if root['tag'] != 'PACK':
        raise PakError(f'Erwartet PACK, gefunden {root["tag"]}')
    tocc_root = parse_rfrm_header(data, 32, 'TOCC-RFRM')
    if tocc_root['tag'] != 'TOCC':
        raise PakError(f'Erwartet TOCC, gefunden {tocc_root["tag"]}')
    pos = 64
    chunks = []
    chunk_by_tag = {}
    while pos < tocc_root['end']:
        chunk = parse_chunk(data, pos)
        if chunk['payload_end'] > tocc_root['end']:
            raise PakError(f'Chunk {chunk["tag"]} läuft aus TOCC heraus')
        chunks.append(chunk)
        chunk_by_tag.setdefault(chunk['tag'], []).append(chunk)
        pos = chunk['next_off']
    if pos != tocc_root['end']:
        raise PakError('TOCC endet nicht genau auf Chunk-Grenze')
    adir_chunks = chunk_by_tag.get('ADIR', [])
    if len(adir_chunks) != 1:
        raise PakError(f'ADIR erwartet genau 1 Mal, gefunden {len(adir_chunks)}')
    adir_chunk = adir_chunks[0]
    p = adir_chunk['payload_off']
    if p + 4 > adir_chunk['payload_end']:
        raise PakError('ADIR ohne Eintragszähler')
    asset_count = be32(data, p)
    p += 4
    entries = []
    for i in range(asset_count):
        if p + 36 > adir_chunk['payload_end']:
            raise PakError(f'ADIR Eintrag {i} abgeschnitten')
        entry = {
            'index': i,
            'table_off': p,
            'type': tag4(data, p),
            'uuid_hex': data[p+4:p+20].hex(),
            'uuid_bytes': data[p+4:p+20],
            'offset': be64(data, p + 20),
            'size': be64(data, p + 28)
        }
        entries.append(entry)
        p += 36
    adir_tail_size = adir_chunk['payload_end'] - p
    strg_chunk = chunk_by_tag.get('STRG', [None])[0]
    strg_names = {}
    strg_records = []
    if strg_chunk is not None:
        p = strg_chunk['payload_off']
        if p + 4 > strg_chunk['payload_end']:
            raise PakError('STRG ohne Zähler')
        name_count = be32(data, p)
        p += 4
        for i in range(name_count):
            if p + 24 > strg_chunk['payload_end']:
                raise PakError(f'STRG Eintrag {i} abgeschnitten')
            typ = tag4(data, p)
            uid = data[p+4:p+20].hex()
            name_len = be32(data, p + 20)
            p += 24
            if p + name_len > strg_chunk['payload_end']:
                raise PakError(f'STRG Name {i} abgeschnitten')
            raw_name = data[p:p+name_len]
            p += name_len
            name = raw_name.split(b'\x00', 1)[0].decode('utf-8', 'replace')
            rec = {'type': typ, 'uuid_hex': uid, 'name_len': name_len, 'name_raw': raw_name, 'name': name}
            strg_records.append(rec)
            strg_names[uid] = rec
        if p != strg_chunk['payload_end']:
            raise PakError('STRG Restdaten unerwartet')
    meta_chunk = chunk_by_tag.get('META', [None])[0]
    meta_map = {}
    meta_entries = []
    if meta_chunk is not None:
        base = meta_chunk['payload_off']
        if base + 4 > meta_chunk['payload_end']:
            raise PakError('META ohne Zähler')
        count = be32(data, base)
        table_off = base + 4
        table_end = table_off + count * 20
        if table_end > meta_chunk['payload_end']:
            raise PakError('META Tabelle abgeschnitten')
        for i in range(count):
            pos = table_off + i * 20
            uid_hex = data[pos:pos+16].hex()
            rel = be32(data, pos + 16)
            blob_off = base + rel
            if blob_off + 4 > meta_chunk['payload_end']:
                raise PakError(f'META Blob {i} abgeschnitten')
            blob_size = be32(data, blob_off)
            blob_end = blob_off + 4 + blob_size
            if blob_end > meta_chunk['payload_end']:
                raise PakError(f'META Blob {i} läuft über Chunk-Ende')
            blob = data[blob_off+4:blob_end]
            rec = {
                'uuid_hex': uid_hex,
                'rel': rel,
                'blob_off': blob_off,
                'blob_size': blob_size,
                'blob': blob
            }
            meta_entries.append(rec)
            meta_map[uid_hex] = rec
    entries_by_offset = sorted(entries, key=lambda x: x['offset'])
    first_asset_off = tocc_root['end']
    if entries_by_offset:
        min_off = entries_by_offset[0]['offset']
        last_end = max(x['offset'] + x['size'] for x in entries_by_offset)
    else:
        min_off = first_asset_off
        last_end = first_asset_off
    tail = data[last_end:]
    for entry in entries:
        asset = get_entry_asset({'data': data}, entry)
        payload = get_entry_payload(asset)
        bundle = parse_segmented_payload(payload)
        meta_blob = meta_map.get(entry['uuid_hex'])
        entry['name'] = strg_names.get(entry['uuid_hex'], {}).get('name', '')
        entry['display_name'] = entry['name']
        entry['mtrl_info'] = None
        entry['model_materials'] = []
        entry['has_meta'] = entry['uuid_hex'] in meta_map
        entry['meta'] = meta_blob
        entry['meta_kind'] = ''
        entry['meta_view'] = None
        if meta_blob is not None:
            blob = meta_blob['blob']
            try:
                if entry['type'] in REFERENCE_META_TYPES:
                    entry['meta_kind'] = 'ref_list'
                    entry['meta_view'] = parse_reference_meta(blob)
                elif entry['type'] == 'TXTR':
                    entry['meta_kind'] = 'txtr'
                    entry['meta_view'] = parse_txtr_meta(blob)
                elif entry['type'] == 'MTRL':
                    entry['meta_kind'] = 'mtrl'
                    entry['meta_view'] = parse_mtrl_meta(blob)
                elif entry['type'] == 'CSMP':
                    entry['meta_kind'] = 'csmp'
                    entry['meta_view'] = parse_csmp_meta(blob)
                elif entry['type'] in MODEL_META_TYPES:
                    entry['meta_kind'] = 'model'
                    entry['meta_view'] = parse_model_meta_template(blob, asset)
            except Exception:
                entry['meta_view'] = None
        entry['asset_sha1'] = sha1_bytes(asset)
        entry['payload_sha1'] = sha1_bytes(payload)
        entry['payload_size'] = len(payload)
        entry['payload_kind'] = detect_payload_kind(payload)
        entry['bundle'] = bundle
        entry['is_bundle'] = bundle is not None
        entry['bundle_count'] = len(bundle['children']) if bundle else 0
    parsed = {
        'path': str(virtual_path),
        'data': data,
        'root': root,
        'tocc_root': tocc_root,
        'chunks': chunks,
        'chunk_by_tag': chunk_by_tag,
        'adir_chunk': adir_chunk,
        'meta_chunk': meta_chunk,
        'strg_chunk': strg_chunk,
        'entries': entries,
        'entries_by_offset': entries_by_offset,
        'first_asset_off': first_asset_off,
        'min_off': min_off,
        'last_end': last_end,
        'tail': tail,
        'adir_tail_size': adir_tail_size,
        'strg_records': strg_records,
        'meta_entries': meta_entries
    }
    caud_to_csmp, csmp_to_cauds = build_caud_ref_map(entries, data)
    parsed['caud_to_csmp'] = caud_to_csmp
    parsed['csmp_to_cauds'] = csmp_to_cauds
    model_to_mtrls = build_model_mtrl_ref_map(entries, data)
    parsed['model_to_mtrls'] = model_to_mtrls
    parsed['uuid_to_entry'] = build_uuid_entry_map(entries)
    parsed['issues'] = validate_parsed(parsed)
    return parsed

def parse_pak(path):
    return parse_pak_from_data(Path(path).read_bytes(), str(path))

def parse_pak_bytes(data, virtual_path='<memory>'):
    return parse_pak_from_data(data, virtual_path)

def validate_parsed(parsed):
    data = parsed['data']
    entries = parsed['entries']
    entries_by_offset = parsed['entries_by_offset']
    issues = []
    def add(level, text):
        issues.append({'level': level, 'text': text})
    if parsed['root']['end'] != parsed['last_end']:
        add('warn', f'PACK-Größe zeigt auf 0x{parsed["root"]["end"]:X}, letzter Asset-Ende ist 0x{parsed["last_end"]:X}')
    if parsed['tocc_root']['end'] != parsed['first_asset_off']:
        add('error', f'TOCC-Ende 0x{parsed["tocc_root"]["end"]:X} passt nicht zu erstem Asset 0x{parsed["first_asset_off"]:X}')
    if parsed['min_off'] != parsed['first_asset_off']:
        add('error', f'Kleinster Asset-Offset 0x{parsed["min_off"]:X} passt nicht zu TOCC-Ende 0x{parsed["first_asset_off"]:X}')
    if parsed['adir_tail_size'] != 0:
        add('warn', f'ADIR hat {parsed["adir_tail_size"]} Restbytes nach der Tabelle')
    seen_uuid = set()
    for entry in entries:
        if entry['uuid_hex'] in seen_uuid:
            add('warn', f'Doppelte UUID: {entry["uuid_hex"]}')
        seen_uuid.add(entry['uuid_hex'])
        if entry['offset'] < parsed['first_asset_off']:
            add('error', f'Eintrag #{entry["index"]} liegt vor dem Asset-Bereich')
        if entry['offset'] + entry['size'] > len(data):
            add('error', f'Eintrag #{entry["index"]} läuft über Dateiende')
        asset = data[entry['offset']:entry['offset'] + entry['size']]
        if len(asset) != entry['size']:
            add('error', f'Eintrag #{entry["index"]} Größe stimmt nicht')
            continue
        if asset[:4] != b'RFRM':
            add('warn', f'Eintrag #{entry["index"]} beginnt nicht mit RFRM')
            continue
        try:
            hdr = parse_rfrm_header(asset, 0, f'Asset #{entry["index"]}')
            if hdr['tag'] != entry['type']:
                add('warn', f'Eintrag #{entry["index"]} Typ {entry["type"]} passt nicht zum Wrapper {hdr["tag"]}')
            if hdr['end'] != len(asset):
                add('warn', f'Eintrag #{entry["index"]} Wrapper-Größe {hdr["size"]} passt nicht exakt zur Asset-Länge {len(asset)}')
            payload = get_entry_payload(asset)
            if entry.get('is_bundle'):
                bundle = entry['bundle']
                if build_segmented_payload(bundle) != payload:
                    add('error', f'Bundle in Eintrag #{entry["index"]} kann nicht verlustfrei rekonstruiert werden')
            if entry.get('has_meta') and entry['type'] in MODEL_META_TYPES and entry.get('meta_view') is None:
                add('warn', f'META von #{entry["index"]} ({entry["type"]}) ist noch nicht als sichere Variante erkannt')
        except Exception as e:
            add('error', str(e))
    for prev, cur in zip(entries_by_offset, entries_by_offset[1:]):
        prev_end = prev['offset'] + prev['size']
        if prev_end > cur['offset']:
            add('error', f'Überlappung zwischen #{prev["index"]} und #{cur["index"]}')
        elif prev_end < cur['offset']:
            add('warn', f'Lücke zwischen #{prev["index"]} und #{cur["index"]}: {cur["offset"] - prev_end} Bytes')
    for rec in parsed['strg_records']:
        if rec['uuid_hex'] not in seen_uuid:
            add('warn', f'STRG ohne ADIR-Eintrag: {rec["uuid_hex"]}')
        if rec['type'] and rec['uuid_hex'] in seen_uuid:
            match = next((e for e in entries if e['uuid_hex'] == rec['uuid_hex']), None)
            if match and rec['type'] != match['type']:
                add('warn', f'STRG-Typ {rec["type"]} passt nicht zu ADIR-Typ {match["type"]} bei {rec["uuid_hex"]}')
    for rec in parsed['meta_entries']:
        if rec['uuid_hex'] not in seen_uuid:
            add('warn', f'META ohne ADIR-Eintrag: {rec["uuid_hex"]}')
    return issues

def format_meta_lines(entry):
    if not entry.get('has_meta'):
        return ['META: nein']
    lines = [f'META: ja', f'META-Größe: {entry["meta"]["blob_size"]}']
    view = entry.get('meta_view')
    kind = entry.get('meta_kind')
    if kind == 'ref_list' and view is not None:
        lines.append(f'META-Form: Referenzliste ({view["count"]})')
        for ref in view['refs'][:12]:
            lines.append(f'- {ref["type"]} {ref["uuid_hex"]}')
        if view['count'] > 12:
            lines.append(f'- ... {view["count"] - 12} weitere')
        return lines
    if kind == 'txtr' and view is not None:
        lines.append('META-Form: TXTR')
        lines.append(f'- Subtyp: {view["subtype"]}')
        lines.append(f'- GPU-Chunk-Offset: {view["gpu_chunk_off"]}')
        lines.append(f'- GPU-Payload-Offset: {view["gpu_payload_off"]}')
        lines.append(f'- GPU gepackt: {view["gpu_comp_size_a"]}')
        lines.append(f'- GPU entpackt: {view["gpu_decomp_size"]}')
        return lines
    if kind == 'mtrl' and view is not None:
        lines.append('META-Form: MTRL')
        lines.append(f'- Gepackt: {view["comp_size"]}')
        lines.append(f'- Entpackt: {view["decomp_size"]}')
        return lines
    if kind == 'csmp' and view is not None:
        lines.append('META-Form: CSMP')
        lines.append(f'- Marker: 0x{view["marker"]:08X}')
        lines.append(f'- DATA-Größe: {view["data_size"]}')
        return lines
    if kind == 'model' and view is not None:
        lines.append(f'META-Form: Modell {view["variant"]}')
        lines.append(f'- GPU-Segmente alt: {len(view["old_segments"])}')
        for i, (seg, dec) in enumerate(zip(view['old_segments'][:12], view['old_decomp_sizes'][:12])):
            lines.append(f'- {i}: {seg["kind_name"]} | Off {seg["off"]} | Größe {seg["size"]} | Entpackt {dec}')
        if len(view['old_segments']) > 12:
            lines.append(f'- ... {len(view["old_segments"]) - 12} weitere')
        return lines
    lines.append(f'META-Hex: {entry["meta"]["blob"].hex()}')
    return lines

def make_entry_label(entry):
    name = entry.get('display_name') or entry['name'] or entry['uuid_hex']
    meta = 'META' if entry['has_meta'] else 'kein META'
    extra = f' | Bundle {entry["bundle_count"]}' if entry['is_bundle'] else ''
    return f'{entry["type"]} | {name} | Größe {entry["size"]} | {meta}{extra}'

def make_child_label(entry, child):
    base = entry.get('display_name') or entry['name'] or entry['uuid_hex']
    return f'  {child["segment_tag"]} | {child["inner_kind"]} | {base} | Größe {len(child["inner"])}'

def entry_export_name(entry):
    uid = entry['uuid_hex']
    formatted_uid = f'{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}'
    display_name = entry.get('display_name') or entry['name']
    if display_name:
        base = safe_name(display_name)
        return f'{base}_{formatted_uid}'
    return f'{entry["index"]:04d}__{entry["type"]}__{formatted_uid}'

def resolve_replacement_asset(parsed, entry, spec):
    original_asset = get_entry_asset(parsed, entry)
    if 'asset_bytes' in spec:
        return spec['asset_bytes']
    return prepare_replacement(entry, original_asset, spec['path'], spec['mode'])

def rebuild_pak(parsed, replacements, out_path):
    original_data = parsed['data']
    new_assets = {}
    meta_blobs = {}
    for entry in parsed['entries_by_offset']:
        original_asset = original_data[entry['offset']:entry['offset'] + entry['size']]
        new_asset = original_asset
        if entry['index'] in replacements:
            new_asset = resolve_replacement_asset(parsed, entry, replacements[entry['index']])
        new_assets[entry['index']] = new_asset
    header_limit = 32
    cur = 0
    offsets_by_index = {}
    placeholder_asset_offsets = {}
    for entry in parsed['entries_by_offset']:
        placeholder_asset_offsets[entry['index']] = (0, len(new_assets[entry['index']]))
    tmp_tocc = build_tocc_bytes(parsed, parsed['entries'], placeholder_asset_offsets, {})
    first_asset_off = 32 + len(tmp_tocc)
    cur = first_asset_off
    for entry in parsed['entries_by_offset']:
        blob = new_assets[entry['index']]
        offsets_by_index[entry['index']] = (cur, len(blob))
        cur += len(blob)
    for entry in parsed['entries']:
        original_asset = original_data[entry['offset']:entry['offset'] + entry['size']]
        new_asset = new_assets[entry['index']]
        blob = build_entry_meta_blob(parsed, entry, original_asset, new_asset)
        if blob is not None:
            meta_blobs[entry['uuid_hex']] = blob
    tocc_bytes = build_tocc_bytes(parsed, parsed['entries'], offsets_by_index, meta_blobs)
    first_asset_off = 32 + len(tocc_bytes)
    cur = first_asset_off
    offsets_by_index = {}
    for entry in parsed['entries_by_offset']:
        blob = new_assets[entry['index']]
        offsets_by_index[entry['index']] = (cur, len(blob))
        cur += len(blob)
    tocc_bytes = build_tocc_bytes(parsed, parsed['entries'], offsets_by_index, meta_blobs)
    first_asset_off = 32 + len(tocc_bytes)
    if first_asset_off != min(off for off, _ in offsets_by_index.values()):
        cur = first_asset_off
        offsets_by_index = {}
        for entry in parsed['entries_by_offset']:
            blob = new_assets[entry['index']]
            offsets_by_index[entry['index']] = (cur, len(blob))
            cur += len(blob)
        tocc_bytes = build_tocc_bytes(parsed, parsed['entries'], offsets_by_index, meta_blobs)
    out = bytearray()
    root = bytearray(parsed['root']['header'])
    body_size = len(tocc_bytes) + sum(len(new_assets[e['index']]) for e in parsed['entries_by_offset']) + len(parsed['tail'])
    w64(root, 4, body_size)
    out += root
    out += tocc_bytes
    for entry in parsed['entries_by_offset']:
        out += new_assets[entry['index']]
    out += parsed['tail']
    reparsed = parse_pak_bytes(bytes(out), str(out_path))
    if any(x['level'] == 'error' for x in reparsed['issues']):
        texts = '\n'.join(x['text'] for x in reparsed['issues'] if x['level'] == 'error')
        raise PakError(f'Neubau fehlgeschlagen:\n{texts}')
    Path(out_path).write_bytes(out)
    return str(out_path)

ASSET_TYPE_LABELS = {
    'TXTR': 'Texturen',
    'CSMP': 'Sound-Daten (DSP)',
    'CAUD': 'Sound-Referenzen / Metadaten',
    'ANIM': 'Animationen',
    'CMDL': 'Statische Modelle',
    'SMDL': 'Skinned Modelle',
    'WMDL': 'Welt-Modelle',
    'MTRL': 'Materialien',
    'GENP': 'Generische Parameter',
    'SWSH': 'Shader / Swoosh',
    'CHAR': 'Character Rigs',
    'SKEL': 'Skelette',
    'CLSN': 'Kollisionsbäume',
    'DCLN': 'Detaillierte Kollision',
    'ROOM': 'Raum- / Level-Daten',
    'MSBT': 'Nachrichtentabellen (Texte)',
    'GFX ': 'Scaleform UI (Flash)',
    'GFXL': 'Scaleform Listen',
    'DGRP': 'Abhängigkeitsgruppen',
    'RSTC': 'Regel-Sets',
    'FSMC': 'State Machines',
}

def analyze_text(parsed):
    lines = []
    bundle_entries = [e for e in parsed['entries'] if e['is_bundle']]
    bundle_children = sum(e['bundle_count'] for e in bundle_entries)
    meta_supported = sum(1 for e in parsed['entries'] if e.get('has_meta') and e.get('meta_view') is not None)
    meta_total = sum(1 for e in parsed['entries'] if e.get('has_meta'))
    lines.append(f'Datei: {parsed["path"]}')
    lines.append(f'Einträge: {len(parsed["entries"])}')
    lines.append(f'Bundle-Einträge: {len(bundle_entries)}')
    lines.append(f'Gefundene Unterdateien: {bundle_children}')
    lines.append(f'PACK-Tag: {parsed["root"]["tag"]}')
    lines.append(f'PACK-Größenfeld: {parsed["root"]["size"]}')
    lines.append(f'TOCC-Größenfeld: {parsed["tocc_root"]["size"]}')
    lines.append(f'Header-Ende / erster Datenblock: 0x{parsed["first_asset_off"]:X}')
    lines.append(f'Tail nach letztem Asset: {len(parsed["tail"])} Bytes')
    lines.append(f'Chunks: {", ".join(c["tag"] for c in parsed["chunks"])}')
    lines.append('')
    if parsed['meta_chunk'] is None:
        lines.append('META: keiner vorhanden')
    else:
        lines.append(f'META: vorhanden, {meta_total} verknüpfte Einträge, {meta_supported} strukturiert erkannt')
    if parsed['strg_chunk'] is None:
        lines.append('STRG: keiner vorhanden')
    else:
        lines.append(f'STRG: {len(parsed["strg_records"])} Namen')
    lines.append('')
    errors = [x['text'] for x in parsed['issues'] if x['level'] == 'error']
    warns = [x['text'] for x in parsed['issues'] if x['level'] == 'warn']
    lines.append(f'Validierung: {len(errors)} Fehler, {len(warns)} Hinweise')
    if errors:
        lines.append('')
        lines.append('Fehler:')
        for text in errors:
            lines.append(f'- {text}')
    if warns:
        lines.append('')
        lines.append('Hinweise:')
        for text in warns[:40]:
            lines.append(f'- {text}')
        if len(warns) > 40:
            lines.append(f'- ... {len(warns) - 40} weitere')
    from collections import Counter
    type_counts = Counter(e['type'] for e in parsed['entries'])
    if type_counts:
        lines.append('')
        lines.append('Typen-Übersicht:')
        for typ, count in sorted(type_counts.items(), key=lambda x: (-x[1], x[0])):
            label = ASSET_TYPE_LABELS.get(typ, '')
            desc = f' ({label})' if label else ''
            lines.append(f'- {typ}{desc}: {count}')
    lines.append('')
    lines.append('Einträge:')
    for entry in parsed['entries_by_offset']:
        name = entry.get('display_name') or entry['name'] or entry['uuid_hex']
        extra = f' | Bundle {entry["bundle_count"]}' if entry['is_bundle'] else ''
        meta_extra = ''
        if entry['has_meta'] and entry.get('meta_kind'):
            meta_extra = f' | META-{entry["meta_kind"]}'
        lines.append(f'- #{entry["index"]} {entry["type"]} | {name} | Offset {entry["offset"]} | Größe {entry["size"]} | {"META" if entry["has_meta"] else "kein META"}{meta_extra}{extra}')
    return '\n'.join(lines)
