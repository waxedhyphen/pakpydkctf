import json
from pathlib import Path
import model_animation_refs_patch as anim_patch
from pak_core import safe_name

BLENDER_IMPORT_SCRIPT='import argparse\nimport json\nimport sys\nfrom pathlib import Path\ntry:\n    import bpy\nexcept Exception:\n    bpy=None\nMODE=\'raw_props\'\nSCALE=0.25\nFPS=30\nREPORT_NAME=\'blender_named_timeline_import_report.json\'\nGLB_NAME=\'character_with_anims.glb\'\n\ndef load_json(path):\n    return json.loads(Path(path).read_text(encoding=\'utf-8\'))\n\ndef write_json(path,data):\n    path=Path(path)\n    path.parent.mkdir(parents=True,exist_ok=True)\n    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding=\'utf-8\',newline=\'\\n\')\n\ndef strip_blend_virtual_path(path):\n    path=Path(path)\n    parts=list(path.parts)\n    for index,part in enumerate(parts):\n        if str(part).lower().endswith(\'.blend\'):\n            return Path(*parts[:index+1]).parent\n    if str(path).lower().endswith(\'.blend\'):\n        return path.parent\n    return path.parent if path.suffix else path\n\ndef looks_like_package_dir(path):\n    path=Path(path)\n    return (path/\'debug\'/\'anim_named_timeline\').exists() or bool(list(path.glob(\'models/*/debug/anim_named_timeline\')))\n\ndef candidates_from(path):\n    if not path:\n        return []\n    base=strip_blend_virtual_path(path)\n    return [base]+list(base.parents)\n\ndef find_package_dir():\n    starts=[]\n    try:\n        starts.append(Path(__file__).resolve())\n    except Exception:\n        pass\n    if bpy and bpy.data.filepath:\n        starts.append(Path(bpy.data.filepath).resolve())\n    starts.append(Path.cwd())\n    seen=set()\n    for start in starts:\n        for base in candidates_from(start):\n            key=str(base).lower()\n            if key in seen:\n                continue\n            seen.add(key)\n            if looks_like_package_dir(base):\n                return base\n    if bpy and bpy.data.filepath:\n        return Path(bpy.data.filepath).resolve().parent\n    return Path.cwd()\n\ndef timeline_identity(path,data):\n    uuid_hex=data.get(\'uuid_hex\') or \'\'\n    name=data.get(\'char_animation_name\') or data.get(\'entry_name\') or Path(path).stem.replace(\'.named_timeline\',\'\')\n    return uuid_hex or name\n\ndef collect_timelines(package_dir):\n    root=Path(package_dir)\n    paths=[]\n    paths.extend(root.glob(\'debug/anim_named_timeline/*.named_timeline.json\'))\n    paths.extend(root.glob(\'models/*/debug/anim_named_timeline/*.named_timeline.json\'))\n    by_key={}\n    order=[]\n    seen_paths=set()\n    for path in paths:\n        path_key=str(path.resolve())\n        if path_key in seen_paths:\n            continue\n        seen_paths.add(path_key)\n        data=load_json(path)\n        if data.get(\'type\')!=\'ANIM_NAMED_TIMELINE\' or not data.get(\'groups\'):\n            continue\n        key=timeline_identity(path,data)\n        prefer_model=\'models/\' in str(path).replace(\'\\\\\',\'/\')\n        if key not in by_key:\n            by_key[key]=(path,data)\n            order.append(key)\n        elif prefer_model:\n            by_key[key]=(path,data)\n    return [by_key[key] for key in order]\n\ndef find_armature(name=None):\n    if bpy is None:\n        raise RuntimeError(\'Blender Python ist nicht aktiv\')\n    if name:\n        obj=bpy.data.objects.get(name)\n        if obj and obj.type==\'ARMATURE\':\n            return obj\n    active=bpy.context.view_layer.objects.active\n    if active and active.type==\'ARMATURE\':\n        return active\n    selected=[obj for obj in bpy.context.selected_objects if obj.type==\'ARMATURE\']\n    if selected:\n        return selected[0]\n    for obj in bpy.context.scene.objects:\n        if obj.type==\'ARMATURE\':\n            return obj\n    for obj in bpy.data.objects:\n        if obj.type==\'ARMATURE\':\n            return obj\n    raise RuntimeError(\'Keine Armature gefunden\')\n\ndef norm_name(name):\n    value=str(name).lower().replace(\' \',\'\').replace(\'_\',\'\').replace(\'-\',\'\').replace(\'.\',\'\')\n    for suffix in (\'jntskin\',\'skin\',\'joint\',\'jnt\'):\n        if value.endswith(suffix):\n            value=value[:-len(suffix)]\n    return value\n\ndef bone_lookup(armature):\n    lookup={}\n    for bone in armature.pose.bones:\n        lookup[bone.name]=bone\n        lookup[norm_name(bone.name)]=bone\n    return lookup\n\ndef ensure_pose_bone(lookup,name):\n    if name in lookup:\n        return lookup[name]\n    key=norm_name(name)\n    if key in lookup:\n        return lookup[key]\n    if name==\'root/body\':\n        for fallback in (\'root\',\'skeleton_root\',\'root.move\',\'blendspace\'):\n            if fallback in lookup:\n                return lookup[fallback]\n            fkey=norm_name(fallback)\n            if fkey in lookup:\n                return lookup[fkey]\n    return None\n\ndef set_rotation_euler(pose_bone,value):\n    pose_bone.rotation_mode=\'XYZ\'\n    x,y,z=value\n    pose_bone.rotation_euler=(x*SCALE,y*SCALE,z*SCALE)\n\ndef set_location(pose_bone,value):\n    x,y,z=value\n    pose_bone.location=(x*SCALE,y*SCALE,z*SCALE)\n\ndef set_raw_props(pose_bone,value):\n    x,y,z=value\n    pose_bone[\'pak_anim_raw_x\']=float(x)\n    pose_bone[\'pak_anim_raw_y\']=float(y)\n    pose_bone[\'pak_anim_raw_z\']=float(z)\n\ndef set_value(pose_bone,value):\n    if value is None:\n        return False\n    if MODE==\'location\':\n        set_location(pose_bone,value)\n    elif MODE==\'rotation_euler\':\n        set_rotation_euler(pose_bone,value)\n    else:\n        set_raw_props(pose_bone,value)\n    return True\n\ndef insert_value_key(pose_bone,frame):\n    if MODE==\'location\':\n        pose_bone.keyframe_insert(data_path=\'location\',frame=frame)\n        return 3\n    if MODE==\'rotation_euler\':\n        pose_bone.keyframe_insert(data_path=\'rotation_euler\',frame=frame)\n        return 3\n    pose_bone.keyframe_insert(data_path=\'["pak_anim_raw_x"]\',frame=frame)\n    pose_bone.keyframe_insert(data_path=\'["pak_anim_raw_y"]\',frame=frame)\n    pose_bone.keyframe_insert(data_path=\'["pak_anim_raw_z"]\',frame=frame)\n    return 3\n\ndef animation_name(data,path):\n    name=data.get(\'char_animation_name\') or data.get(\'entry_name\') or Path(path).stem.replace(\'.named_timeline\',\'\')\n    clean=\'\'.join(c if c.isalnum() or c in \'.- _\'.replace(\' \',\'\') else \'_\' for c in name)\n    return clean if MODE==\'raw_props\' else clean+\'__\'+MODE\n\ndef activate_armature(armature):\n    if bpy.context.mode!=\'OBJECT\':\n        try:\n            bpy.ops.object.mode_set(mode=\'OBJECT\')\n        except Exception:\n            pass\n    for obj in bpy.context.scene.objects:\n        obj.select_set(False)\n    armature.select_set(True)\n    bpy.context.view_layer.objects.active=armature\n    bpy.ops.object.mode_set(mode=\'POSE\')\n\ndef frame_number(group,frame):\n    if \'absolute_frame_index\' in frame:\n        return int(frame.get(\'absolute_frame_index\') or 0)+1\n    start=group.get(\'timeline_frame_start\')\n    if start is None:\n        start=group.get(\'timeline_start_frame_index\',0)\n    return int(start or 0)+int(frame.get(\'frame_index\',0) or 0)+1\n\ndef group_report(group):\n    frames=group.get(\'frames\') or []\n    absolute=[frame_number(group,frame) for frame in frames]\n    return {\'group_index\':group.get(\'group_index\',0),\'mapping_mode\':group.get(\'mapping_mode\',\'\'),\'vector_count\':group.get(\'vector_count\',0),\'timeline_frame_count\':group.get(\'timeline_frame_count\',len(frames)),\'frame_start\':min(absolute) if absolute else 0,\'frame_end\':max(absolute) if absolute else 0,\'target_names\':group.get(\'target_names\') or [track.get(\'target_guess\',{}).get(\'target_name\',\'\') for track in group.get(\'mapped_tracks\',[])]}\n\ndef apply_timeline(armature,path,data,report):\n    action_name=animation_name(data,path)\n    existing=bpy.data.actions.get(action_name)\n    if existing:\n        bpy.data.actions.remove(existing)\n    action=bpy.data.actions.new(action_name)\n    action.use_fake_user=True\n    armature.animation_data_create()\n    armature.animation_data.action=action\n    armature[\'pak_anim_uuid\']=data.get(\'uuid_hex\',\'\')\n    armature[\'pak_anim_source\']=str(path)\n    armature[\'pak_anim_mode\']=MODE\n    activate_armature(armature)\n    lookup=bone_lookup(armature)\n    action_report={\'action\':action_name,\'source\':str(path),\'frames\':0,\'inserted_key_channels\':0,\'matched_bones\':[],\'missing_targets\':[],\'groups\':[]}\n    matched=set()\n    missing=set()\n    for group in data.get(\'groups\',[]):\n        action_report[\'groups\'].append(group_report(group))\n        for frame in group.get(\'frames\',[]):\n            frame_index=frame_number(group,frame)\n            action_report[\'frames\']=max(action_report[\'frames\'],frame_index)\n            for item in frame.get(\'values\',[]):\n                name=item.get(\'target_name\',\'\')\n                value=item.get(\'value\')\n                bone=ensure_pose_bone(lookup,name)\n                if bone is None:\n                    missing.add(name)\n                    continue\n                matched.add(bone.name)\n                if set_value(bone,value):\n                    action_report[\'inserted_key_channels\']+=insert_value_key(bone,frame_index)\n    for attr,value in ((\'frame_start\',1),(\'frame_end\',max(1,action_report[\'frames\']))):\n        try:\n            setattr(action,attr,value)\n        except Exception:\n            pass\n    action_report[\'matched_bones\']=sorted(matched)\n    action_report[\'missing_targets\']=sorted(missing)\n    report[\'actions\'].append(action_report)\n    return action,action_report\n\ndef parse_args(argv):\n    parser=argparse.ArgumentParser()\n    parser.add_argument(\'--package\',default=\'\')\n    parser.add_argument(\'--armature\',default=\'\')\n    parser.add_argument(\'--mode\',default=MODE,choices=[\'raw_props\',\'rotation_euler\',\'location\'])\n    parser.add_argument(\'--scale\',default=str(SCALE))\n    parser.add_argument(\'--fps\',default=str(FPS))\n    parser.add_argument(\'--no-save\',action=\'store_true\')\n    parser.add_argument(\'--glb\',action=\'store_true\')\n    return parser.parse_args(argv)\n\ndef main(argv=None):\n    global MODE,SCALE,FPS\n    if bpy is None:\n        raise RuntimeError(\'Dieses Script muss in Blender laufen\')\n    args=parse_args(argv or [])\n    MODE=args.mode\n    SCALE=float(args.scale)\n    FPS=int(args.fps)\n    package_dir=Path(args.package).resolve() if args.package else find_package_dir()\n    bpy.context.scene.render.fps=FPS\n    armature=find_armature(args.armature or None)\n    timelines=collect_timelines(package_dir)\n    report={\'package_dir\':str(package_dir),\'mode\':MODE,\'scale\':SCALE,\'armature\':armature.name,\'armature_bones\':[bone.name for bone in armature.pose.bones],\'timeline_count\':len(timelines),\'actions\':[],\'errors\':[]}\n    if not timelines:\n        report[\'errors\'].append(\'Keine *.named_timeline.json gefunden\')\n        write_json(package_dir/REPORT_NAME,report)\n        raise RuntimeError(\'Keine *.named_timeline.json gefunden. --package auf den Export-Ordner setzen.\')\n    actions=[]\n    total_channels=0\n    max_frame=1\n    for path,data in timelines:\n        action,action_report=apply_timeline(armature,path,data,report)\n        actions.append(action)\n        total_channels+=action_report[\'inserted_key_channels\']\n        max_frame=max(max_frame,action_report[\'frames\'])\n    armature[\'pak_named_timeline_actions\']=\';\'.join(action.name for action in actions)\n    if actions:\n        armature.animation_data.action=actions[0]\n        bpy.context.scene.frame_start=1\n        bpy.context.scene.frame_end=max_frame\n        bpy.context.scene.frame_set(1)\n    activate_armature(armature)\n    report[\'total_inserted_key_channels\']=total_channels\n    report[\'active_action\']=actions[0].name if actions else \'\'\n    report[\'scene_frame_start\']=bpy.context.scene.frame_start\n    report[\'scene_frame_end\']=bpy.context.scene.frame_end\n    write_json(package_dir/REPORT_NAME,report)\n    if total_channels==0:\n        raise RuntimeError(\'0 Keyframes erzeugt. Report prüfen: \'+str(package_dir/REPORT_NAME))\n    if not args.no_save and bpy.data.filepath:\n        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)\n    if args.glb:\n        out=Path(package_dir)/GLB_NAME\n        bpy.ops.export_scene.gltf(filepath=str(out),export_format=\'GLB\',export_animations=True,export_skins=True)\n    print(\'Imported actions:\',len(actions))\n    print(\'Inserted key channels:\',total_channels)\n    print(\'Mode:\',MODE)\n    print(\'Report:\',package_dir/REPORT_NAME)\n    for action in actions:\n        print(action.name)\n\nif __name__==\'__main__\':\n    main(sys.argv[sys.argv.index(\'--\')+1:] if \'--\' in sys.argv else [])\n'
BLENDER_PREVIEW_SCRIPT='import sys\nfrom pathlib import Path\n\ndef base_from_blender():\n    try:\n        p=Path(__file__).resolve()\n    except Exception:\n        import bpy\n        p=Path(bpy.data.filepath).resolve() if bpy.data.filepath else Path.cwd()\n    parts=list(p.parts)\n    for i,part in enumerate(parts):\n        if str(part).lower().endswith(\'.blend\'):\n            return Path(*parts[:i])\n    return p.parent if p.suffix else p\n\ndef find_package_root(start):\n    for base in [start]+list(start.parents):\n        if (base/\'blender_import_named_timelines.py\').exists():\n            return base\n        if (base/\'debug\'/\'anim_named_timeline\').exists():\n            return base\n        if list(base.glob(\'models/*/debug/anim_named_timeline\')):\n            return base\n    return None\n\nstart=base_from_blender()\nroot=find_package_root(start)\nif root is None:\n    raise RuntimeError(\'starFish01_character_package nicht gefunden\')\nscript=root/\'blender_import_named_timelines.py\'\nif not script.exists():\n    raise RuntimeError(\'blender_import_named_timelines.py nicht gefunden: \'+str(script))\nsys.argv=[str(script),\'--\',\'--package\',str(root),\'--mode\',\'rotation_euler\',\'--scale\',\'0.25\']\ncode=script.read_text(encoding=\'utf-8\')\nexec(compile(code,str(script),\'exec\'),{\'__name__\':\'__main__\',\'__file__\':str(script)})\n'
BLENDER_README='Blender-Animation Import\n\nAnalyse:\nblender_import_named_timelines.py\n\nSichtbarer Test:\nblender_preview_named_timelines.py\n\nWichtig:\nraw_props bewegt nichts sichtbar.\nrotation_euler ist nur Vorschau.\n'

def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None

def _write_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')

def _write_text(path,text):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text,encoding='utf-8',newline='\n')

def _rel(root,path):
    return str(Path(path).relative_to(root)).replace('\\','/')

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
            return data,_rel(root,path)
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

def _timeline_frame_count(group):
    count=group.get('timeline_frame_count') or 0
    if count:
        return count
    tracks=group.get('tracks') or []
    return max([track.get('timeline_frame_count',0) for track in tracks]+[0])

def _group_target_names(group):
    names=[]
    for track in group.get('mapped_tracks') or []:
        target=track.get('target_guess') or {}
        name=target.get('target_name') or f'lane_{track.get("lane_index",0)}'
        names.append(name)
    return names

def _named_frame_timeline(group,start_frame_index):
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
        frames.append({'frame_index':frame_index,'absolute_frame_index':start_frame_index+frame_index,'values':values,'by_name':by_name})
    return frames

def _valid_groups(probe,groups):
    if probe.get('raw_family')!='normal_clip':
        return [],'not_normal_clip'
    frame_count=probe.get('frame_count_guess') or 0
    if not frame_count:
        return [],'missing_frame_count'
    usable=[]
    for group in groups:
        if group.get('mapping_mode','')=='unmapped_count_mismatch':
            continue
        frames=_timeline_frame_count(group)
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
    return [],f'frame_coverage_mismatch:{total}!={frame_count}'

def _apply_frame_layout(groups):
    cursor=0
    for group in groups:
        frames=group.get('timeline_frame_count') or 0
        group['timeline_frame_start']=cursor
        group['timeline_frame_end']=cursor+max(0,frames-1) if frames else cursor
        group['named_frame_timeline']=_named_frame_timeline(group,cursor)
        cursor+=frames
    return cursor

def _group_doc(group):
    return {'group_index':group.get('group_index',0),'mapping_mode':group.get('mapping_mode',''),'vector_count':group.get('vector_count',0),'timeline_frame_count':group.get('timeline_frame_count',0),'timeline_frame_start':group.get('timeline_frame_start',0),'timeline_frame_end':group.get('timeline_frame_end',0),'target_names':_group_target_names(group),'mapped_tracks':group.get('mapped_tracks',[]),'frames':group.get('named_frame_timeline',[])}

def _timeline_doc(probe,probe_rel):
    mapping=probe.get('track_skeleton_map') or {}
    groups=mapping.get('groups') or []
    return {'version':4,'type':'ANIM_NAMED_TIMELINE','source_probe':probe_rel,'entry_name':probe.get('entry_name',''),'char_animation_name':probe.get('char_animation_name',''),'uuid_hex':probe.get('uuid_hex',''),'frame_count_guess':probe.get('frame_count_guess',0),'absolute_frame_count':mapping.get('absolute_frame_count',0),'raw_family':probe.get('raw_family',''),'mapping_status':mapping.get('status',''),'mapping_note':mapping.get('note',''),'skeleton_file':mapping.get('skeleton_file',''),'node_names':mapping.get('node_names',[]),'skin_bone_names':mapping.get('skin_bone_names',[]),'groups':[_group_doc(group) for group in groups]}

def _write_named_timeline(root,probe_path,probe):
    root=Path(root)
    probe_path=Path(probe_path)
    rel=_rel(root,probe_path)
    name=probe.get('char_animation_name') or probe.get('entry_name') or probe_path.stem.replace('.probe21','')
    uuid_hex=probe.get('uuid_hex','')
    base=safe_name(f'{name}__{uuid_hex}' if uuid_hex else name)
    out_dir=probe_path.parent.parent/'anim_named_timeline'
    out_path=out_dir/(base+'.named_timeline.json')
    _write_json(out_path,_timeline_doc(probe,rel))
    return _rel(root,out_path)

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
        group['timeline_frame_count']=_timeline_frame_count(group)
        mapped_groups.append({'group_index':group.get('group_index',0),'mapping_mode':mode,'vector_count':vector_count,'timeline_frame_count':group.get('timeline_frame_count',0),'mapped_tracks':mapped_tracks,'tracks':group.get('tracks') or []})
    valid,note=_valid_groups(probe,mapped_groups)
    absolute_frame_count=_apply_frame_layout(valid) if valid else 0
    status='ok' if valid else note
    probe['track_skeleton_map']={'version':8,'status':status,'note':note,'skeleton_file':skel_file,'node_count':len(node_names),'skin_bone_count':len(bone_names),'node_names':node_names,'skin_bone_names':bone_names,'absolute_frame_count':absolute_frame_count,'groups':valid}
    probe['track_decode']=track_decode
    return probe

def _probe_structure(root,path,probe):
    mapping=probe.get('track_skeleton_map') or {}
    groups=[]
    for group in mapping.get('groups') or []:
        groups.append({'group_index':group.get('group_index',0),'mapping_mode':group.get('mapping_mode',''),'vector_count':group.get('vector_count',0),'timeline_frame_count':group.get('timeline_frame_count',0),'timeline_frame_start':group.get('timeline_frame_start',0),'timeline_frame_end':group.get('timeline_frame_end',0),'target_names':_group_target_names(group)})
    return {'probe':_rel(root,path),'named_timeline_file':probe.get('named_timeline_file',''),'char_animation_name':probe.get('char_animation_name',''),'entry_name':probe.get('entry_name',''),'uuid_hex':probe.get('uuid_hex',''),'raw_family':probe.get('raw_family',''),'frame_count_guess':probe.get('frame_count_guess',0),'mapping_status':mapping.get('status',''),'mapping_note':mapping.get('note',''),'absolute_frame_count':mapping.get('absolute_frame_count',0),'groups':groups}

def _summary_report_paths(root):
    paths=[]
    for path in list(root.glob('debug/anim_probe21_summary.json'))+list(root.glob('models/*/debug/anim_probe21_summary.json')):
        paths.append(path.parent/'anim_structure_report.json')
    paths.append(root/'debug'/'anim_structure_report.json')
    out=[]
    seen=set()
    for path in paths:
        key=str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out

def _write_structure_report(root,skel,skel_file,named,skipped):
    root=Path(root)
    probes=[]
    paths=list(root.glob('debug/anim_probe21/*.probe21.json'))
    paths.extend(root.glob('models/*/debug/anim_probe21/*.probe21.json'))
    seen=set()
    for path in paths:
        key=str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        probe=_read_json(path)
        if isinstance(probe,dict):
            probes.append(_probe_structure(root,path,probe))
    report={'version':3,'type':'ANIM_STRUCTURE_REPORT','skeleton_file':skel_file,'node_count':len(skel.get('nodes') or []),'skin_bone_count':len(skel.get('bones') or []),'node_names':[node.get('name','') for node in skel.get('nodes') or []],'skin_bone_names':[bone.get('name','') for bone in skel.get('bones') or []],'named_timeline_files':named,'skipped_timeline_files':skipped,'animation_count':len(probes),'animations':probes}
    report_paths=_summary_report_paths(root)
    for out in report_paths:
        _write_json(out,report)
    return [_rel(root,path) for path in report_paths]

def _write_blender_files(root):
    root=Path(root)
    targets=[root]
    targets.extend(path.parent.parent for path in root.glob('models/*/debug/anim_named_timeline'))
    out=[]
    seen=set()
    for target in targets:
        key=str(target.resolve())
        if key in seen:
            continue
        seen.add(key)
        _write_text(target/'blender_import_named_timelines.py',BLENDER_IMPORT_SCRIPT)
        _write_text(target/'blender_preview_named_timelines.py',BLENDER_PREVIEW_SCRIPT)
        _write_text(target/'BLENDER_ANIMATION_IMPORT.txt',BLENDER_README)
        out.append(_rel(root,target/'blender_import_named_timelines.py'))
    return out

def _enrich_package(package_dir):
    skel,skel_file=_find_skeleton(package_dir)
    if skel is None:
        return {'status':'no_skeleton'}
    root=Path(package_dir)
    changed=0
    named=[]
    skipped=[]
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
        status=(probe.get('track_skeleton_map') or {}).get('status','')
        if status=='ok':
            rel_named=_write_named_timeline(root,path,probe)
            probe['named_timeline_file']=rel_named
            named.append(rel_named)
        else:
            skipped.append({'probe':_rel(root,path),'status':status})
        _write_json(path,probe)
        changed+=1
    structure_reports=_write_structure_report(root,skel,skel_file,named,skipped)
    blender_files=_write_blender_files(root)
    summary_paths=list(root.glob('debug/anim_probe21_summary.json'))
    summary_paths.extend(root.glob('models/*/debug/anim_probe21_summary.json'))
    for path in summary_paths:
        data=_read_json(path)
        if not isinstance(data,dict):
            continue
        local_report=_rel(root,path.parent/'anim_structure_report.json')
        data['track_skeleton_map']={'version':8,'status':'ok','skeleton_file':skel_file,'node_count':len(skel.get('nodes') or []),'skin_bone_count':len(skel.get('bones') or []),'named_timeline_files':named,'skipped_timeline_files':skipped,'structure_report':local_report,'structure_reports':structure_reports,'blender_import_files':blender_files}
        _write_json(path,data)
    return {'status':'ok','changed_probe_count':changed,'skeleton_file':skel_file,'named_timeline_count':len(named),'named_timeline_files':named,'skipped_timeline_files':skipped,'structure_report':structure_reports[0] if structure_reports else '','structure_reports':structure_reports,'blender_import_files':blender_files}

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
