#========================
#FILE csmp_codec.py
#========================

from collections import defaultdict

class CsmpError(Exception):
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

def is_raw_csmp(data):
    return len(data) >= 8 and data[:4] == b'CSMP'

def is_internal_csmp_asset(data):
    return len(data) >= 32 and data[:4] == b'RFRM' and tag4(data, 20) == 'CSMP'

def _is_printable_tag(text):
    return len(text) == 4 and all(32 <= ord(ch) < 127 for ch in text)

def _parse_internal_csmp_payload(data):
    if len(data) < 24:
        raise CsmpError('CSMP-Payload zu klein')
    chunks = []
    p = 0
    while p < len(data):
        if p + 24 > len(data):
            raise CsmpError('CSMP-Payload endet mitten im Chunk-Header')
        chunk_tag = tag4(data, p)
        if not _is_printable_tag(chunk_tag):
            raise CsmpError(f'Ungültiger CSMP-Chunk bei 0x{p:X}')
        size = be64(data, p + 4)
        payload_off = p + 24
        payload_end = payload_off + size
        if payload_end > len(data):
            raise CsmpError(f'CSMP-Chunk {chunk_tag} läuft über Dateiende')
        chunks.append({
            'index': len(chunks),
            'tag': chunk_tag,
            'off': p,
            'size': size,
            'header': data[p:p+24],
            'payload': data[payload_off:payload_end]
        })
        p = payload_end
    if not chunks:
        raise CsmpError('CSMP-Payload enthält keine Chunks')
    if not any(chunk['tag'] == 'DATA' for chunk in chunks):
        raise CsmpError('CSMP-Payload enthält keinen DATA-Chunk')
    return chunks

def is_internal_csmp_payload(data):
    if is_raw_csmp(data) or is_internal_csmp_asset(data):
        return False
    try:
        _parse_internal_csmp_payload(data)
        return True
    except Exception:
        return False

def parse_raw_csmp(data):
    if not is_raw_csmp(data):
        raise CsmpError('Keine echte CSMP-Datei')
    version = be32(data, 4)
    chunks = []
    p = 8
    while p < len(data):
        if p + 8 > len(data):
            raise CsmpError('CSMP endet mitten im Chunk-Header')
        chunk_tag = tag4(data, p)
        if not _is_printable_tag(chunk_tag):
            raise CsmpError(f'Ungültiger CSMP-Chunk bei 0x{p:X}')
        declared_size = be32(data, p + 4)
        p += 8
        actual_size = declared_size - 4 if chunk_tag == 'DATA' and declared_size >= 4 else declared_size
        if p + actual_size > len(data):
            raise CsmpError(f'CSMP-Chunk {chunk_tag} läuft über Dateiende')
        chunks.append({
            'index': len(chunks),
            'tag': chunk_tag,
            'declared_size': declared_size,
            'payload': data[p:p+actual_size]
        })
        p += actual_size
    if not chunks:
        raise CsmpError('CSMP enthält keine Chunks')
    if not any(chunk['tag'] == 'DATA' for chunk in chunks):
        raise CsmpError('CSMP enthält keinen DATA-Chunk')
    return {
        'version': version,
        'chunks': chunks
    }

def parse_internal_csmp_asset(asset):
    if not is_internal_csmp_asset(asset):
        raise CsmpError('Keine interne CSMP-Ressource')
    return {
        'root_header': asset[:32],
        'chunks': _parse_internal_csmp_payload(asset[32:])
    }

def internal_asset_to_raw_csmp(asset):
    parsed = parse_internal_csmp_asset(asset)
    out = bytearray()
    out += b'CSMP'
    out += (1).to_bytes(4, 'big')
    for chunk in parsed['chunks']:
        declared_size = len(chunk['payload']) + (4 if chunk['tag'] == 'DATA' else 0)
        out += chunk['tag'].encode('ascii')
        out += int(declared_size).to_bytes(4, 'big')
        out += chunk['payload']
    return bytes(out)

def _default_root_header():
    head = bytearray(32)
    head[:4] = b'RFRM'
    head[20:24] = b'CSMP'
    w32(head, 24, 1)
    w32(head, 28, 0)
    return head

def _default_chunk_header(chunk_tag, payload_size):
    head = bytearray(24)
    head[:4] = chunk_tag.encode('ascii')
    w64(head, 4, payload_size)
    w32(head, 12, 1)
    return head

def wrap_internal_csmp_payload(template_asset, payload):
    _parse_internal_csmp_payload(payload)
    if not is_internal_csmp_asset(template_asset):
        raise CsmpError('Kein interner CSMP-Wrapper vorhanden')
    wrapped = bytearray(template_asset[:32] + payload)
    w64(wrapped, 4, len(payload))
    return bytes(wrapped)

def raw_csmp_to_internal_asset(data, template_asset=None):
    parsed = parse_raw_csmp(data)
    old_headers = defaultdict(list)
    root_header = _default_root_header()
    if template_asset is not None and is_internal_csmp_asset(template_asset):
        root_header = bytearray(template_asset[:32])
        for chunk in parse_internal_csmp_asset(template_asset)['chunks']:
            old_headers[chunk['tag']].append(chunk['header'])
    body = bytearray()
    for chunk in parsed['chunks']:
        if old_headers.get(chunk['tag']):
            header = bytearray(old_headers[chunk['tag']].pop(0))
            header[:4] = chunk['tag'].encode('ascii')
            w64(header, 4, len(chunk['payload']))
        else:
            header = bytearray(_default_chunk_header(chunk['tag'], len(chunk['payload'])))
        body += header
        body += chunk['payload']
    root_header = bytearray(root_header)
    root_header[:4] = b'RFRM'
    root_header[20:24] = b'CSMP'
    w64(root_header, 4, len(body))
    return bytes(root_header) + bytes(body)

def exportable_csmp_bytes(data):
    if is_raw_csmp(data):
        return data
    if is_internal_csmp_asset(data):
        return data
    return None

def normalize_csmp_replacement(raw, original):
    if is_internal_csmp_asset(original):
        if is_raw_csmp(raw):
            return raw_csmp_to_internal_asset(raw, original)
        if is_internal_csmp_asset(raw):
            fixed = bytearray(raw)
            w64(fixed, 4, len(raw) - 32)
            return bytes(fixed)
        if is_internal_csmp_payload(raw):
            return wrap_internal_csmp_payload(original, raw)
        return None
    if is_raw_csmp(original):
        if is_raw_csmp(raw):
            return raw
        if is_internal_csmp_asset(raw):
            return internal_asset_to_raw_csmp(raw)
        return None
    return None