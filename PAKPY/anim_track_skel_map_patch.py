import json
from pathlib import Path
import model_animation_refs_patch as anim_patch

def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None

def _write_json(path,data):
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')

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
        mapped_groups.append({'group_index':group.get('group_index',0),'mapping_mode':mode,'vector_count':vector_count,'timeline_frame_count':group.get('timeline_frame_count',0),'mapped_tracks':mapped_tracks})
    probe['track_skeleton_map']={'version':1,'status':'ok' if mapped_groups else 'no_track_groups','skeleton_file':skel_file,'node_count':len(node_names),'skin_bone_count':len(bone_names),'node_names':node_names,'skin_bone_names':bone_names,'groups':mapped_groups}
    probe['track_decode']=track_decode
    return probe

def _enrich_package(package_dir):
    skel,skel_file=_find_skeleton(package_dir)
    if skel is None:
        return {'status':'no_skeleton'}
    root=Path(package_dir)
    changed=0
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
        _write_json(path,_apply_mapping(probe,skel,skel_file))
        changed+=1
    summary_paths=list(root.glob('debug/anim_probe21_summary.json'))
    summary_paths.extend(root.glob('models/*/debug/anim_probe21_summary.json'))
    for path in summary_paths:
        data=_read_json(path)
        if not isinstance(data,dict):
            continue
        data['track_skeleton_map']={'version':1,'status':'ok','skeleton_file':skel_file,'node_count':len(skel.get('nodes') or []),'skin_bone_count':len(skel.get('bones') or [])}
        _write_json(path,data)
    return {'status':'ok','changed_probe_count':changed,'skeleton_file':skel_file}

def install(App):
    original=anim_patch._write_animation_probe_set
    def write_animation_probe_set(parsed,entry,package_dir,refs,require_store=None,root_name='char'):
        result=original(parsed,entry,package_dir,refs,require_store= require_store,root_name=root_name)
        try:
            result['track_skeleton_map']=_enrich_package(package_dir)
        except Exception as e:
            result['track_skeleton_map_error']=str(e)
        return result
    anim_patch._write_animation_probe_set=write_animation_probe_set
