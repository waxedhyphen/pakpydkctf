import struct
import model_animation_refs_patch as anim_patch

NEUTRAL_U16={0,32767,32768,65535}
FRAME_MARKER=bytes.fromhex('1c0000000000')

def _u16be(data,limit):
    return [int.from_bytes(data[i:i+2],'big') for i in range(0,min(limit,len(data)//2*2),2)]

def _u16le(data,limit):
    return [int.from_bytes(data[i:i+2],'little') for i in range(0,min(limit,len(data)//2*2),2)]

def _s16be(value):
    return value-65536 if value>=32768 else value

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

def _q16(value):
    return round((value-32768)/32768,6)

def _vec3_list(data,limit=8):
    out=[]
    count=min(limit,len(data)//6)
    for index in range(count):
        raw=data[index*6:index*6+6]
        vals=[int.from_bytes(raw[i:i+2],'big') for i in (0,2,4)]
        out.append({'index':index,'raw_hex':raw.hex(),'u16be':vals,'s16be':[_s16be(v) for v in vals],'centered':[_q16(v) for v in vals]})
    return out

def _find_all(data,needle):
    out=[]
    pos=data.find(needle)
    while pos!=-1:
        out.append(pos)
        pos=data.find(needle,pos+1)
    return out

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

def _group_marker_runs(offsets):
    runs=[]
    if not offsets:
        return runs
    start=offsets[0]
    prev=offsets[0]
    stride=None
    count=1
    for off in offsets[1:]:
        diff=off-prev
        if stride is None:
            stride=diff
            count=2
            prev=off
            continue
        if diff==stride:
            count+=1
            prev=off
            continue
        runs.append({'start_offset':start,'last_marker_offset':prev,'marker_count':count,'stride':stride})
        start=off
        prev=off
        stride=None
        count=1
    runs.append({'start_offset':start,'last_marker_offset':prev,'marker_count':count,'stride':stride})
    return runs

def _run_detail(body,run):
    stride=run.get('stride')
    if stride is None:
        end=min(len(body),run['start_offset']+96)
    else:
        end=min(len(body),run['last_marker_offset']+stride)
    run['end_offset']=end
    run['byte_size']=max(0,end-run['start_offset'])
    run['coverage_ratio']=round(run['byte_size']/len(body),6) if body else 0
    marker_size=len(FRAME_MARKER)
    run['marker_size']=marker_size
    vector_count=None
    if stride and stride>marker_size and (stride-marker_size)%6==0:
        vector_count=(stride-marker_size)//6
    run['vector_count_guess']=vector_count
    if vector_count:
        initial_offset=run['start_offset']-vector_count*6
        if initial_offset>=0:
            initial=body[initial_offset:run['start_offset']]
            run['initial_vectors_offset']=initial_offset
            run['initial_vectors']=_vec3_list(initial,vector_count)
            run['initial_vectors_hex']=initial.hex()
    samples=[]
    offsets=_find_all(body,FRAME_MARKER)
    members=[off for off in offsets if off>=run['start_offset'] and off<=run['last_marker_offset']]
    for index,off in enumerate(members[:4]):
        rec_end=members[index+1] if index+1<len(members) else min(len(body),off+(stride or 96))
        payload=body[off+marker_size:rec_end]
        samples.append({'frame_marker_index':index,'offset':off,'record_size':rec_end-off,'payload_hex':payload[:72].hex(),'vectors':_vec3_list(payload,8)})
    run['sample_records']=samples
    return run

def _frame_marker_probe(body):
    offsets=_find_all(body,FRAME_MARKER)
    runs=[]
    for run in _group_marker_runs(offsets):
        runs.append(_run_detail(body,dict(run)))
    strong=[]
    for run in runs:
        if run.get('marker_count',0)>=3:
            strong.append(run)
    return {'marker_hex':FRAME_MARKER.hex(),'marker_count':len(offsets),'marker_offsets':offsets[:120],'runs':runs,'strong_runs':strong}

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
    frame_probe=_frame_marker_probe(body_used)
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
    probe['frame_marker_probe']=frame_probe
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
            marker_probe=probe.get('frame_marker_probe') or {}
            lines.append(f'Frame-Marker: {marker_probe.get("marker_count",0)}')
            run_lines=[]
            for run in marker_probe.get('strong_runs',[])[:4]:
                stride=run.get('stride')
                vec=run.get('vector_count_guess')
                run_lines.append(f'0x{run["start_offset"]:X}/{run.get("marker_count",0)}x/{stride}B/{vec or "?"}v')
            if run_lines:
                lines.append('Frame-Runs: '+', '.join(run_lines))
            starts=probe.get('body_start_candidates') or []
            if starts:
                lines.append('Body-Start-Kandidaten: '+', '.join(f'0x{x["offset"]:X}' for x in starts[:4]))
        except Exception as e:
            lines.append(f'Raw-Probe Fehler: {e}')
        return lines
    anim_patch.parse_anim_probe21=parse_anim_probe21
    anim_patch._anim_summary_lines=anim_summary_lines
