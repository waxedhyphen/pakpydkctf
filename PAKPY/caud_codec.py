import struct


class CaudError(Exception):
    pass


def _be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')


def _bef32(data, off):
    return struct.unpack_from('>f', data, off)[0]


def _format_uuid(hex_str):
    return f'{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}'


def is_caud_asset(data):
    if len(data) < 64:
        return False
    if data[:4] != b'RFRM':
        return False
    return data[20:24] == b'CAUD'


def parse_caud_asset(data):
    if not is_caud_asset(data):
        raise CaudError('Keine CAUD-Ressource')
    payload = data[32:]
    p = 0
    end = len(payload)
    if p + 4 > end:
        raise CaudError('CAUD-Payload zu klein')
    str_len = _be32(payload, p); p += 4
    if p + str_len > end:
        raise CaudError('CAUD-Name abgeschnitten')
    name = payload[p:p+str_len].split(b'\x00')[0].decode('ascii', 'replace')
    p += str_len
    if p + 16 > end:
        raise CaudError('CAUD-Header zu kurz nach Name')
    unk0 = _be32(payload, p); p += 4
    pre_volume = _bef32(payload, p); p += 4
    volume = _bef32(payload, p); p += 4
    param_flags_size = _be32(payload, p); p += 4
    if p + 8 > end:
        raise CaudError('CAUD-Felder abgeschnitten')
    sound_struct = payload[p]; p += 1
    p += 3
    unk_u8 = payload[p]; p += 1
    loop_flag = payload[p]; p += 1
    p += 1
    if p + 4 > end:
        raise CaudError('CAUD-Gain abgeschnitten')
    gain = _bef32(payload, p); p += 4
    p += 3
    if p + 1 > end:
        raise CaudError('CAUD-Ref-Count abgeschnitten')
    ref_count = payload[p]; p += 1
    csmp_refs = []
    for _ in range(ref_count):
        if p + 16 > end:
            raise CaudError('CAUD-UUID abgeschnitten')
        csmp_refs.append(payload[p:p+16].hex())
        p += 16
    if p + 24 > end:
        raise CaudError('CAUD-Audioparams abgeschnitten')
    fade_in = _bef32(payload, p); p += 4
    spatialize_mode = _be32(payload, p); p += 4
    unk_u32_a = _be32(payload, p); p += 4
    min_dist = _bef32(payload, p); p += 4
    max_dist = _bef32(payload, p); p += 4
    reverb_send = _bef32(payload, p); p += 4
    p += 8
    if p + 4 > end:
        raise CaudError('CAUD-Priority abgeschnitten')
    priority = _be32(payload, p); p += 4
    p += 4
    unk_u32_b = _be32(payload, p); p += 4
    max_voices = _be32(payload, p); p += 4
    p += 8
    if p + 20 > end:
        raise CaudError('CAUD-Pitch abgeschnitten')
    pitch_min = _bef32(payload, p); p += 4
    p += 8
    pitch_max = _bef32(payload, p); p += 4
    p += 4
    tail_raw = payload[p:]
    return {
        'name': name,
        'volume': volume,
        'pre_volume': pre_volume,
        'param_flags_size': param_flags_size,
        'sound_struct': sound_struct,
        'loop': loop_flag,
        'gain': gain,
        'csmp_refs': csmp_refs,
        'fade_in': fade_in,
        'spatialize_mode': spatialize_mode,
        'min_dist': min_dist,
        'max_dist': max_dist,
        'reverb_send': reverb_send,
        'priority': priority,
        'unk_u32_b': unk_u32_b,
        'max_voices': max_voices,
        'pitch_min': pitch_min,
        'pitch_max': pitch_max,
        'tail_size': len(tail_raw)
    }


def format_caud_lines(caud_info):
    lines = []
    lines.append(f'CAUD-Name: {caud_info["name"]}')
    lines.append(f'Volume: {caud_info["volume"]}')
    if caud_info['pre_volume'] != 0.0:
        lines.append(f'Pre-Volume: {caud_info["pre_volume"]}')
    lines.append(f'Gain: {caud_info["gain"]}')
    lines.append(f'Loop: {"ja" if caud_info["loop"] else "nein"}')
    lines.append(f'Sound-Struct: {caud_info["sound_struct"]}')
    lines.append(f'Fade-In: {caud_info["fade_in"]:.2f}s')
    lines.append(f'Min-Distanz: {caud_info["min_dist"]}')
    lines.append(f'Max-Distanz: {caud_info["max_dist"]}')
    lines.append(f'Reverb-Send: {caud_info["reverb_send"]:.4f}')
    lines.append(f'Priorität: {caud_info["priority"]}')
    lines.append(f'Max-Voices: {caud_info["max_voices"]}')
    if caud_info['pitch_min'] != 1.0 or caud_info['pitch_max'] != 1.0:
        lines.append(f'Pitch: {caud_info["pitch_min"]:.4f} - {caud_info["pitch_max"]:.4f}')
    if caud_info['unk_u32_b'] != 0:
        lines.append(f'Unbekannt-B: {caud_info["unk_u32_b"]}')
    for i, ref in enumerate(caud_info['csmp_refs']):
        lines.append(f'CSMP-Ref {i}: {_format_uuid(ref)}')
    return lines


def build_caud_ref_map(entries, data):
    caud_to_csmp = {}
    csmp_to_cauds = {}
    for entry in entries:
        if entry['type'] != 'CAUD':
            continue
        asset = data[entry['offset']:entry['offset'] + entry['size']]
        try:
            info = parse_caud_asset(asset)
        except CaudError:
            continue
        entry['caud_info'] = info
        caud_to_csmp[entry['uuid_hex']] = info['csmp_refs']
        for ref in info['csmp_refs']:
            csmp_to_cauds.setdefault(ref, []).append(entry)
    return caud_to_csmp, csmp_to_cauds