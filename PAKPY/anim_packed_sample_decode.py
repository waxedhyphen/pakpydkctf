import math

PACKED_FAMILIES={'packed_clip_82','packed_state_c1','packed_state_c2'}

def s16(value):
    return value-65536 if value>=32768 else value

def sn16(data,off):
    raw=data[off:off+2].ljust(2,b'\x00')
    return round(s16(int.from_bytes(raw,'big'))/32767,6)

def quat_to_euler(value):
    if len(value)<4:
        return [0.0,0.0,0.0]
    w,x,y,z=[float(v) for v in value[:4]]
    length=math.sqrt(w*w+x*x+y*y+z*z)
    if length<=0.000001:
        return [0.0,0.0,0.0]
    w,x,y,z=w/length,x/length,y/length,z/length
    t0=2.0*(w*x+y*z)
    t1=1.0-2.0*(x*x+y*y)
    roll=math.atan2(t0,t1)
    t2=2.0*(w*y-z*x)
    t2=max(-1.0,min(1.0,t2))
    pitch=math.asin(t2)
    t3=2.0*(w*z+x*y)
    t4=1.0-2.0*(y*y+z*z)
    yaw=math.atan2(t3,t4)
    return [round(roll,6),round(pitch,6),round(yaw,6)]

def descriptor(probe):
    desc=probe.get('descriptor_bytes') or []
    family=probe.get('raw_family','')
    if len(desc)<4:
        return 0,0
    if family=='packed_clip_82':
        return int(desc[0] or 0),int(desc[1] or 0)
    if family in ('packed_state_c1','packed_state_c2'):
        return max(int(desc[0] or 0),int(desc[1] or 0)),int(desc[2] or 0)
    return 0,0

def stream_start(body):
    candidates=[]
    for needle in (bytes.fromhex('d0da3ccd'),bytes.fromhex('fffc0000'),bytes.fromhex('7f7f')):
        pos=body.find(needle)
        if pos>=0:
            candidates.append(pos)
    return min(candidates) if candidates else 0

def value(chunk,component_count):
    values=[sn16(chunk,index*2) for index in range(component_count)]
    if component_count==1:
        return [values[0],0.0,0.0]
    if component_count==2:
        return [values[0],values[1],0.0]
    if component_count==3:
        return values[:3]
    return quat_to_euler(values[:4])

def lane_summary(values):
    if not values:
        return {}
    cols=list(zip(*values))
    return {'min':[round(min(col),6) for col in cols],'max':[round(max(col),6) for col in cols],'first':values[0],'last':values[-1]}

def track(group_index,lane_index,values,kind):
    return {'group_index':group_index,'lane_index':lane_index,'value_kind':kind,'timeline_values':values,'timeline_frame_count':len(values),'summary':lane_summary(values)}

def decode(probe,body):
    family=probe.get('raw_family','')
    if family not in PACKED_FAMILIES or body is None:
        return []
    vector_count,component_count=descriptor(probe)
    frame_count=probe.get('frame_count_guess') or 1
    if vector_count<=0 or component_count<=0 or frame_count<=0:
        return []
    vector_count=max(1,min(int(vector_count),256))
    component_count=max(1,min(int(component_count),4))
    frame_count=max(1,min(int(frame_count),4096))
    start=stream_start(body)
    value_size=component_count*2
    needed=vector_count*frame_count*value_size
    if start+needed>len(body):
        start=max(0,min(start,len(body)-needed))
    tracks=[]
    kind=f'{family}_s16be_c{component_count}'
    for lane_index in range(vector_count):
        values=[]
        for frame_index in range(frame_count):
            off=start+(frame_index*vector_count+lane_index)*value_size
            chunk=body[off:off+value_size]
            if len(chunk)<value_size:
                chunk=chunk.ljust(value_size,b'\x00')
            values.append(value(chunk,component_count))
        tracks.append(track(0,lane_index,values,kind))
    return [{'group_index':0,'start_offset':start,'end_offset':min(len(body),start+needed),'marker_count':0,'stride':vector_count*value_size,'vector_count':vector_count,'timeline_frame_count':frame_count,'track_value_kind':kind,'target_order_hint':'skin_bone_prefix','tracks':tracks}]
