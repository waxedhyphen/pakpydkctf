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

def install_into():
    m=__import__('anim_track_skel_map_patch')
    raw=__import__('anim_raw_probe_patch')
    old_targets=m._targets_for_group
    def targets_for_group(skel,count):
        targets,mode=old_targets(skel,count)
        if targets:
            return targets,mode
        bones=m._bone_targets(skel)
        nodes=m._node_targets(skel)
        if count and bones and count<=len(bones):
            return bones[:count],'skin_bone_prefix_order'
        if count and nodes and count<=len(nodes):
            return nodes[:count],'node_prefix_order'
        return targets,mode
    def build_track_decode(probe,body=None):
        family=probe.get('raw_family','')
        if family in PACKED_FAMILIES:
            groups=decode(probe,body)
            status='ok:packed_sample_decode' if groups else f'pending:{family}'
        else:
            marker_probe=probe.get('frame_marker_probe') or {}
            groups=list(marker_probe.get('decoded_groups') or [])
            status='ok:marker_decode' if groups else f'pending:{family}'
        best=None
        for group in groups:
            if best is None or group.get('timeline_frame_count',0)>best.get('timeline_frame_count',0):
                best=group
        return {'version':3,'status':status,'frame_count_guess':probe.get('frame_count_guess',0),'group_count':len(groups),'groups':groups,'primary_group_index':best.get('group_index') if best else None,'primary_timeline_frame_count':best.get('timeline_frame_count') if best else 0}
    def valid_groups(probe,groups):
        if probe.get('raw_family') not in {'normal_clip','packed_clip_82','packed_state_c1','packed_state_c2'}:
            return [],'raw_family_pending'
        status=(probe.get('track_decode') or {}).get('status','')
        if not status.startswith('ok'):
            return [],status or 'missing_track_decode'
        frame_count=probe.get('frame_count_guess') or 0
        if not frame_count:
            return [],'missing_frame_count'
        usable=[]
        for group in groups:
            if group.get('mapping_mode','')=='unmapped_count_mismatch':
                continue
            frames=m._timeline_frame_count(group)
            if frames>0:
                group['timeline_frame_count']=frames
                usable.append(group)
        if not usable:
            return [],'no_usable_groups'
        total=sum(group.get('timeline_frame_count') or 0 for group in usable)
        if total==frame_count:
            return usable,'ok:sequential_groups'
        exact=[group for group in usable if (group.get('timeline_frame_count') or 0)==frame_count]
        if exact:
            return exact,'ok:single_full_group'
        if status.startswith('ok:packed'):
            return usable,'ok:packed_groups'
        return [],f'frame_coverage_mismatch:{total}!={frame_count}'
    m._targets_for_group=targets_for_group
    m._valid_groups=valid_groups
    raw._build_track_decode=build_track_decode
