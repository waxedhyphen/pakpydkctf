import struct
import model_animation_refs_patch as anim_patch

NEUTRAL_U16={0,32767,32768,65535}

def _tag4(data,off):
    if off+4>len(data):
        return ''
    return data[off:off+4].decode('ascii','replace')

def _u16be(data,limit):
    return [int.from_bytes(data[i:i+2],'big') for i in range(0,min(limit,len(data)//2*2),2)]

def _u16le(data,limit):
    return [int.from_bytes(data[i:i+2],'little') for i in range(0,min(limit,len(data)//2*2),2)]

def _u32be(data,off):
    if off+4>len(data):
        return None
    return int.from_bytes(data[off:off+4],'big')

def _f32le(data,off):
    if off+4>len(data):
        return None
    try:
        value=struct.unpack_from('<f',data,off)[0]
    except Exception:
        return None
    if abs(value)<0.00000001:
        value=0.0
    return round(value,6)

def _f32be(data,off):
    if off+4>len(data):
        return None
    try:
        value=struct.unpack_from('>f',data,off)[0]
    except Exception:
        return None
    if abs(value)<0.00000001:
        value=0.0
    return round(value,6)

def _start_candidates(body):
    out=[]
    limit=min(128,len(body))
    for off in range(0,limit,2):
        row=[]
        for pos in range(off,min(off+32,len(body)),2):
            if pos+2<=len(body):
                row.append(int.from_bytes(body[pos:pos+2],'big'))
        if len(row)<6:
            continue
        neutral=sum(1 for value in row if value in NEUTRAL_U16)
        repeated=sum(1 for value in row if value==32768)
        score=neutral*2+repeated
        if neutral>=4:
            out.append({'offset':off,'score':score,'neutral_count':neutral,'u16be':row[:16],'hex':body[off:off+32].hex()})
    out.sort(key=lambda item:(-item['score'],item['offset']))
    return out[:8]

def _raw_family(control,body_used):
    top=(control>>24)&255
    if top==0xC1:
        return 'single_frame_large_or_state'
    if top==0xC2:
        return 'single_frame_large_state_c2'
    if top==0x81:
        return 'normal_clip'
    if len(body_used)==21:
        return 'compact21'
    return 'unknown_raw'

def _enhance(asset,probe):
    payload=asset[32:]
    desc=payload[16:32] if len(payload)>=32 else b''
    pre=payload[32:52] if len(payload)>=52 else b''
    body=payload[52:] if len(payload)>=52 else b''
    body_used=body.rstrip(b'\x00')
    control=_u32be(payload,8) or 0
    frame_count=probe.get('frame_count_guess') or (control&255)
    node_count_guess=0
    if desc:
        if desc[0] in range(1,128):
            node_count_guess=desc[0]
        if desc[0]>64 and len(desc)>1 and desc[1] in range(1,128):
            node_count_guess=desc[1]
    probe['raw_family']=_raw_family(control,body_used)
    probe['descriptor_bytes']=list(desc)
    probe['descriptor_node_count_guess']=node_count_guess
    probe['descriptor_be_floats_at_offsets']=[{'offset':i,'value':_f32be(desc,i)} for i in range(0,max(0,len(desc)-3)) if _f32be(desc,i) in (0.5,1.0,-1.0)]
    probe['pre_data_le_floats']=[_f32le(pre,i) for i in range(0,len(pre),4)]
    probe['pre_data_be_u32']=[_u32be(pre,i) for i in range(0,len(pre),4)]
    probe['body_used_hex_prefix_160']=body_used[:160].hex()
    probe['body_used_u16be_prefix_80']=_u16be(body_used,80)
    probe['body_used_u16le_prefix_40']=_u16le(body_used,40)
    probe['body_start_candidates']=_start_candidates(body_used)
    probe['body_used_bytes_per_frame']=round(len(body_used)/frame_count,6) if frame_count else 0
    probe['body_size_bytes_per_frame']=round(len(body)/frame_count,6) if frame_count else 0
    probe['body_header_guess']={'hex':body_used[:40].hex(),'u16be':_u16be(body_used[:40],40),'u16le':_u16le(body_used[:40],40)}
    return probe

def install(App):
    original_parse=anim_patch.parse_anim_probe21
    original_lines=anim_patch._anim_summary_lines
    def parse_anim_probe21(asset):
        return _enhance(asset,original_parse(asset))
    def anim_summary_lines(ref,anim_entry,asset,source,source_path):
        lines=original_lines(ref,anim_entry,asset,source,source_path)
        if asset is None:
            return lines
        try:
            probe=parse_anim_probe21(asset)
            lines.append(f'Raw-Familie: {probe.get("raw_family","")}')
            lines.append(f'Node-Count-Guess: {probe.get("descriptor_node_count_guess",0)}')
            lines.append(f'Body/Frame: {probe.get("body_used_bytes_per_frame",0)} Bytes')
            if probe.get('pre_data_le_floats'):
                lines.append(f'Pre-LE-Floats: {probe["pre_data_le_floats"]}')
            starts=probe.get('body_start_candidates') or []
            if starts:
                lines.append('Body-Start-Kandidaten: '+', '.join(f'0x{x["offset"]:X}' for x in starts[:4]))
        except Exception as e:
            lines.append(f'Raw-Probe Fehler: {e}')
        return lines
    anim_patch.parse_anim_probe21=parse_anim_probe21
    anim_patch._anim_summary_lines=anim_summary_lines
