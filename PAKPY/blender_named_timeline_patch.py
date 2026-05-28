from pathlib import Path
import anim_track_skel_map_patch as timeline_patch

BLENDER_SCRIPT=r'''
import argparse
import json
import math
import sys
from pathlib import Path

try:
    import bpy
except Exception:
    bpy=None

MODE='rotation_euler'
SCALE=math.pi
FPS=30
SAVE_BLEND=True
EXPORT_GLB=False
GLB_NAME='character_with_anims.glb'
REPORT_NAME='blender_named_timeline_import_report.json'


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')


def strip_blend_virtual_path(path):
    path=Path(path)
    parts=list(path.parts)
    for index,part in enumerate(parts):
        if str(part).lower().endswith('.blend'):
            return Path(*parts[:index+1]).parent
    if str(path).lower().endswith('.blend'):
        return path.parent
    return path.parent if path.suffix else path


def looks_like_package_dir(path):
    path=Path(path)
    return (path/'debug'/'anim_named_timeline').exists() or bool(list(path.glob('models/*/debug/anim_named_timeline')))


def candidates_from(path):
    if not path:
        return []
    base=strip_blend_virtual_path(path)
    out=[base]
    out.extend(base.parents)
    return out


def find_package_dir():
    starts=[]
    try:
        starts.append(Path(__file__).resolve())
    except Exception:
        pass
    if bpy and bpy.data.filepath:
        starts.append(Path(bpy.data.filepath).resolve())
    starts.append(Path.cwd())
    seen=set()
    for start in starts:
        for base in candidates_from(start):
            key=str(base).lower()
            if key in seen:
                continue
            seen.add(key)
            if looks_like_package_dir(base):
                return base
    if bpy and bpy.data.filepath:
        return Path(bpy.data.filepath).resolve().parent
    return Path.cwd()


def collect_timelines(package_dir):
    root=Path(package_dir)
    paths=[]
    paths.extend(root.glob('debug/anim_named_timeline/*.named_timeline.json'))
    paths.extend(root.glob('models/*/debug/anim_named_timeline/*.named_timeline.json'))
    out=[]
    seen=set()
    for path in paths:
        key=str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        data=load_json(path)
        if data.get('type')=='ANIM_NAMED_TIMELINE' and data.get('groups'):
            out.append((path,data))
    return out


def find_armature(name=None):
    if bpy is None:
        raise RuntimeError('Blender Python ist nicht aktiv')
    if name:
        obj=bpy.data.objects.get(name)
        if obj and obj.type=='ARMATURE':
            return obj
    active=bpy.context.view_layer.objects.active
    if active and active.type=='ARMATURE':
        return active
    selected=[obj for obj in bpy.context.selected_objects if obj.type=='ARMATURE']
    if selected:
        return selected[0]
    for obj in bpy.context.scene.objects:
        if obj.type=='ARMATURE':
            return obj
    for obj in bpy.data.objects:
        if obj.type=='ARMATURE':
            return obj
    raise RuntimeError('Keine Armature gefunden')


def norm_name(name):
    value=str(name).lower().replace(' ','').replace('_','').replace('-','').replace('.','')
    for suffix in ('jntskin','skin','joint','jnt'):
        if value.endswith(suffix):
            value=value[:-len(suffix)]
    return value


def bone_lookup(armature):
    lookup={}
    for bone in armature.pose.bones:
        lookup[bone.name]=bone
        lookup[norm_name(bone.name)]=bone
    return lookup


def ensure_pose_bone(lookup,name):
    if name in lookup:
        return lookup[name]
    key=norm_name(name)
    if key in lookup:
        return lookup[key]
    if name=='root/body':
        for fallback in ('root','skeleton_root','root.move','blendspace'):
            if fallback in lookup:
                return lookup[fallback]
            fkey=norm_name(fallback)
            if fkey in lookup:
                return lookup[fkey]
    return None


def clear_action_frame_range(action):
    xs=[]
    for curve in action.fcurves:
        for key in curve.keyframe_points:
            xs.append(key.co.x)
    if xs:
        action.frame_start=min(xs)
        action.frame_end=max(xs)


def set_rotation_euler(pose_bone,value):
    pose_bone.rotation_mode='XYZ'
    x,y,z=value
    pose_bone.rotation_euler=(x*SCALE,y*SCALE,z*SCALE)


def set_location(pose_bone,value):
    x,y,z=value
    pose_bone.location=(x,y,z)


def set_value(pose_bone,value):
    if value is None:
        return False
    if MODE=='location':
        set_location(pose_bone,value)
    else:
        set_rotation_euler(pose_bone,value)
    return True


def insert_value_key(pose_bone,frame):
    if MODE=='location':
        pose_bone.keyframe_insert(data_path='location',frame=frame)
        return 3
    pose_bone.keyframe_insert(data_path='rotation_euler',frame=frame)
    return 3


def animation_name(data,path):
    name=data.get('char_animation_name') or data.get('entry_name') or Path(path).stem.replace('.named_timeline','')
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in name)


def activate_armature(armature):
    if bpy.context.mode!='OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active=armature
    bpy.ops.object.mode_set(mode='POSE')


def apply_timeline(armature,path,data,report):
    action_name=animation_name(data,path)
    existing=bpy.data.actions.get(action_name)
    if existing:
        bpy.data.actions.remove(existing)
    action=bpy.data.actions.new(action_name)
    action.use_fake_user=True
    armature.animation_data_create()
    armature.animation_data.action=action
    armature['pak_anim_uuid']=data.get('uuid_hex','')
    armature['pak_anim_source']=str(path)
    armature['pak_anim_mode']=MODE
    activate_armature(armature)
    lookup=bone_lookup(armature)
    action_report={'action':action_name,'source':str(path),'frames':0,'inserted_key_channels':0,'matched_bones':[],'missing_targets':[]}
    matched=set()
    missing=set()
    for group in data.get('groups',[]):
        for frame in group.get('frames',[]):
            frame_index=frame.get('frame_index',0)+1
            action_report['frames']=max(action_report['frames'],frame_index)
            for item in frame.get('values',[]):
                name=item.get('target_name','')
                value=item.get('value')
                bone=ensure_pose_bone(lookup,name)
                if bone is None:
                    missing.add(name)
                    continue
                matched.add(bone.name)
                if set_value(bone,value):
                    action_report['inserted_key_channels']+=insert_value_key(bone,frame_index)
    clear_action_frame_range(action)
    action_report['matched_bones']=sorted(matched)
    action_report['missing_targets']=sorted(missing)
    report['actions'].append(action_report)
    return action,action_report


def export_glb(package_dir):
    out=Path(package_dir)/GLB_NAME
    bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',export_animations=True,export_skins=True)
    return out


def parse_args(argv):
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',default='')
    parser.add_argument('--armature',default='')
    parser.add_argument('--mode',default=MODE,choices=['rotation_euler','location'])
    parser.add_argument('--scale',default=str(SCALE))
    parser.add_argument('--fps',default=str(FPS))
    parser.add_argument('--no-save',action='store_true')
    parser.add_argument('--glb',action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    global MODE,SCALE,FPS,SAVE_BLEND,EXPORT_GLB
    if bpy is None:
        raise RuntimeError('Dieses Script muss in Blender laufen')
    args=parse_args(argv or [])
    MODE=args.mode
    SCALE=float(args.scale)
    FPS=int(args.fps)
    SAVE_BLEND=not args.no_save
    EXPORT_GLB=args.glb
    package_dir=Path(args.package).resolve() if args.package else find_package_dir()
    bpy.context.scene.render.fps=FPS
    armature=find_armature(args.armature or None)
    timelines=collect_timelines(package_dir)
    report={'package_dir':str(package_dir),'armature':armature.name,'armature_bones':[bone.name for bone in armature.pose.bones],'timeline_count':len(timelines),'actions':[],'errors':[]}
    if not timelines:
        report['errors'].append('Keine *.named_timeline.json gefunden')
        write_json(package_dir/REPORT_NAME,report)
        raise RuntimeError('Keine *.named_timeline.json gefunden. --package auf den Export-Ordner setzen.')
    actions=[]
    total_channels=0
    for path,data in timelines:
        action,action_report=apply_timeline(armature,path,data,report)
        actions.append(action)
        total_channels+=action_report['inserted_key_channels']
    armature['pak_named_timeline_actions']=';'.join(action.name for action in actions)
    if actions:
        armature.animation_data.action=actions[0]
        bpy.context.scene.frame_start=1
        bpy.context.scene.frame_end=max(1,int(actions[0].frame_end or 1))
        bpy.context.scene.frame_set(1)
    activate_armature(armature)
    report['total_inserted_key_channels']=total_channels
    report['active_action']=actions[0].name if actions else ''
    write_json(package_dir/REPORT_NAME,report)
    if total_channels==0:
        raise RuntimeError('0 Keyframes erzeugt. Report prüfen: '+str(package_dir/REPORT_NAME))
    if SAVE_BLEND and bpy.data.filepath:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    if EXPORT_GLB:
        export_glb(package_dir)
    print('Imported actions:',len(actions))
    print('Inserted key channels:',total_channels)
    print('Report:',package_dir/REPORT_NAME)
    for action in actions:
        print(action.name)


if __name__=='__main__':
    main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
'''

README='''Blender-Animation Import

1. Charakter-.blend in Blender öffnen.
2. Armature auswählen.
3. Text Editor > Open > blender_import_named_timelines.py.
4. Run Script.
5. In Dope Sheet > Action Editor die Action auswählen.

Nach dem Lauf entsteht blender_named_timeline_import_report.json im Export-Ordner.

Standardmodus: rotation_euler.

Wenn keine Keys sichtbar sind, zuerst den Report prüfen:
- timeline_count muss größer als 0 sein
- total_inserted_key_channels muss größer als 0 sein
- missing_targets zeigt nicht gefundene Bone-Namen

Optional über Blender CLI:
blender character.blend --python blender_import_named_timelines.py -- --package . --mode rotation_euler

Mit Armature-Name:
blender character.blend --python blender_import_named_timelines.py -- --package . --armature Armature --mode rotation_euler

GLB-Export zusätzlich:
blender character.blend --python blender_import_named_timelines.py -- --package . --mode rotation_euler --glb

Wenn die Animation falsch aussieht:
blender character.blend --python blender_import_named_timelines.py -- --package . --mode location
'''


def _write_blender_files(package_dir):
    root=Path(package_dir)
    script=root/'blender_import_named_timelines.py'
    readme=root/'BLENDER_ANIMATION_IMPORT.txt'
    script.write_text(BLENDER_SCRIPT.strip()+"\n",encoding='utf-8',newline='\n')
    readme.write_text(README,encoding='utf-8',newline='\n')
    return {'script':script.name,'readme':readme.name}


def install(App):
    original=timeline_patch._enrich_package
    def enrich_package(package_dir):
        result=original(package_dir)
        try:
            result['blender_named_timeline_import']=_write_blender_files(package_dir)
        except Exception as e:
            result['blender_named_timeline_import_error']=str(e)
        return result
    timeline_patch._enrich_package=enrich_package
