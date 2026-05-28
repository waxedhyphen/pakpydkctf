import json
from pathlib import Path
import model_animation_refs_patch as anim_patch
from pak_core import safe_name

def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None

def _write_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')

def _find_skeleton(package_dir):
    root=Path(package_dir)
    candidates=[]
    candidates.extend(root.glob('debug/skeleton_debug.json'))
    candidates.extend(root.glob('source/skel/*.json'))
    candidates.extend(root.glob('models/*/debug/skeleton_debug.json'))
    candidates.extend(root.glob('**/source/skel/*.json'))
    for path in candidates:
        data=_read_json(path)
        if not isinstance(data,dict):
            continue
        if data.get('nodes') and data.get('bones'):
            return data,str(path.relative_to(root)).replace('\\','/')
    return None,''

def _node_targets(skel):
    return [{'target_kind':'node','target_index':node.get('index',i),'target_node_index':node.get('index',i),'target_name':node.get('name',''),'confidence':'medium'} for i,node in enumerate(skel.get('nodes') or [])]

def _bone_targets(skel):
    out=[]
    for i,bone in enumerate(skel.get('bones') or []):
        out.append({'target_kind':'skin_bone','target_index':bone.get('index',i),'target_node_index':bone.get('node_index',-1),'target_name':bone.get('name',''),'confidence':'medium'})
    return out

def _targets_for_group(skel,vector_count):
    nodes=_node_targets(skel)
    bones=_bone_targets(skel)
    if vector_count==len(nodes) and nodes:
        return nodes,'node_order_exact'
    if vector_count==len(bones) and bones:
        return bones,'skin_bone_order_exact'
    if vector_count==len(bones)+1 and bones:
        return [{'target_kind':'root_or_body','target_index':-1,'target_node_index':-1,'target_name':'root/body','confidence':'medium'}]+bones,'root_plus_skin_bone_order'
    return [],'unmapped_count_mismatch'

def _named_frame_timeline(group):
    tracks=group.get('tracks') or []
    frame_count=max([track.get('timeline_frame_count',0) for track in tracks]+[0])
    frames=[]
    for frame_index in range(frame_count):
        values=[]
        by_name={}
        for track in tracks:
            target=track.get('target_guess') or {}
            name=target.get('target_name') or f'lane_{track.get("lane_index",0)}'
            timeline=track.get('timeline_values') or []
            value=timeline[frame_index] if frame_index<len(timeline) else None
            item={'lane_index':track.get('lane_index',0),'target_kind':target.get('target_kind','unknown'),'target_name':name,'value':value}
            values.append(item)
            by_name[name]=value
        frames.append({'frame_index':frame_index,'values':values,'by_name':by_name})
    return frames

def _timeline_doc(probe,probe_rel):
    mapping=probe.get('track_skeleton_map') or {}
    groups=mapping.get('groups') or []
    return {'version':1,'type':'ANIM_NAMED_TIMELINE','source_probe':probe_rel,'entry_name':probe.get('entry_name',''),'char_animation_name':probe.get('char_animation_name',''),'uuid_hex':probe.get('uuid_hex',''),'frame_count_guess':probe.get('frame_count_guess',0),'raw_family':probe.get('raw_family',''),'mapping_status':mapping.get('status',''),'skeleton_file':mapping.get('skeleton_file',''),'node_names':mapping.get('node_names',[]),'skin_bone_names':mapping.get('skin_bone_names',[]),'groups':[{'group_index':group.get('group_index',0),'mapping_mode':group.get('mapping_mode',''),'vector_count':group.get('vector_count',0),'timeline_frame_count':group.get('timeline_frame_count',0),'mapped_tracks':group.get('mapped_tracks',[]),'frames':group.get('named_frame_timeline',[])} for group in groups]}

def _write_named_timeline(root,probe_path,probe):
    root=Path(root)
    probe_path=Path(probe_path)
    rel=str(probe_path.relative_to(root)).replace('\\','/')
    name=probe.get('char_animation_name') or probe.get('entry_name') or probe_path.stem.replace('.probe21','')
    uuid_hex=probe.get('uuid_hex','')
    base=safe_name(f'{name}__{uuid_hex}' if uuid_hex else name)
    out_dir=probe_path.parent.parent/'anim_named_timeline'
    out_path=out_dir/(base+'.named_timeline.json')
    _write_json(out_path,_timeline_doc(probe,rel))
    return str(out_path.relative_to(root)).replace('\\','/')

def _apply_mapping(probe,skel,skel_file):
    track_decode=probe.get('track_decode') or {}
    groups=track_decode.get('groups') or []
    mapped_groups=[]
    node_names=[node.get('name','') for node in skel.get('nodes') or []]
    bone_names=[bone.get('name','') for bone in skel.get('bones') or []]
    for group in groups:
        vector_count=group.get('vector_count') or 0
        targets,mode=_targets_for_group(skel,vector_count)
        mapped_tracks=[]
        for track in group.get('tracks') or []:
            lane_index=track.get('lane_index',0)
            target=targets[lane_index] if lane_index<len(targets) else {'target_kind':'unknown','target_index':-1,'target_node_index':-1,'target_name':'','confidence':'low'}
            track['target_guess']=target
            mapped_tracks.append({'lane_index':lane_index,'target_guess':target,'timeline_frame_count':track.get('timeline_frame_count',0),'summary':track.get('summary',{})})
        group['mapping_mode']=mode
        group['mapped_tracks']=mapped_tracks
        group['named_frame_timeline']=_named_frame_timeline(group)
        mapped_groups.append({'group_index':group.get('group_index',0),'mapping_mode':mode,'vector_count':vector_count,'timeline_frame_count':group.get('timeline_frame_count',0),'mapped_tracks':mapped_tracks,'named_frame_timeline':group['named_frame_timeline']})
    probe['track_skeleton_map']={'version':3,'status':'ok' if mapped_groups else 'no_track_groups','skeleton_file':skel_file,'node_count':len(node_names),'skin_bone_count':len(bone_names),'node_names':node_names,'skin_bone_names':bone_names,'groups':mapped_groups}
    probe['track_decode']=track_decode
    return probe

def _enrich_package(package_dir):
    skel,skel_file=_find_skeleton(package_dir)
    if skel is None:
        return {'status':'no_skeleton'}
    root=Path(package_dir)
    changed=0
    named=[]
    probe_paths=list(root.glob('debug/anim_probe21/*.probe21.json'))
    probe_paths.extend(root.glob('models/*/debug/anim_probe21/*.probe21.json'))
    seen=set()
    for path in probe_paths:
        key=str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        probe=_read_json(path)
        if not isinstance(probe,dict):
            continue
        if not probe.get('track_decode'):
            continue
        probe=_apply_mapping(probe,skel,skel_file)
        rel_named=_write_named_timeline(root,path,probe)
        probe['named_timeline_file']=rel_named
        _write_json(path,probe)
        named.append(rel_named)
        changed+=1
    summary_paths=list(root.glob('debug/anim_probe21_summary.json'))
    summary_paths.extend(root.glob('models/*/debug/anim_probe21_summary.json'))
    for path in summary_paths:
        data=_read_json(path)
        if not isinstance(data,dict):
            continue
        data['track_skeleton_map']={'version':3,'status':'ok','skeleton_file':skel_file,'node_count':len(skel.get('nodes') or []),'skin_bone_count':len(skel.get('bones') or []),'named_timeline_files':named}
        _write_json(path,data)
    return {'status':'ok','changed_probe_count':changed,'skeleton_file':skel_file,'named_timeline_count':len(named),'named_timeline_files':named}

def install(App):
    original=anim_patch._write_animation_probe_set
    def write_animation_probe_set(parsed,entry,package_dir,refs,require_store=None,root_name='char'):
        result=original(parsed,entry,package_dir,refs,require_store=require_store,root_name=root_name)
        try:
            result['track_skeleton_map']=_enrich_package(package_dir)
        except Exception as e:
            result['track_skeleton_map_error']=str(e)
        return result
    anim_patch._write_animation_probe_set=write_animation_probe_set