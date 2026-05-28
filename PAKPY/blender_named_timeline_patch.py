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


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def find_package_dir():
    here=Path(__file__).resolve().parent
    if (here/'debug'/'anim_named_timeline').exists():
        return here
    if here.name=='debug' and (here/'anim_named_timeline').exists():
        return here.parent
    return here


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
    for obj in bpy.context.scene.objects:
        if obj.type=='ARMATURE':
            return obj
    for obj in bpy.data.objects:
        if obj.type=='ARMATURE':
            return obj
    raise RuntimeError('Keine Armature gefunden')


def ensure_pose_bone(armature,name):
    if name in armature.pose.bones:
        return armature.pose.bones[name]
    if name=='root/body':
        for fallback in ('root','skeleton_root','root.move','blendspace'):
            if fallback in armature.pose.bones:
                return armature.pose.bones[fallback]
    return None


def clear_action_frame_range(action):
    if action.fcurves:
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
        return
    if MODE=='location':
        set_location(pose_bone,value)
    else:
        set_rotation_euler(pose_bone,value)


def insert_value_key(pose_bone,frame):
    if MODE=='location':
        pose_bone.keyframe_insert(data_path='location',frame=frame)
    else:
        pose_bone.keyframe_insert(data_path='rotation_euler',frame=frame)


def animation_name(data,path):
    name=data.get('char_animation_name') or data.get('entry_name') or Path(path).stem.replace('.named_timeline','')
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in name)


def apply_timeline(armature,path,data):
    action_name=animation_name(data,path)
    action=bpy.data.actions.new(action_name)
    armature.animation_data_create()
    armature.animation_data.action=action
    armature['pak_anim_uuid']=data.get('uuid_hex','')
    armature['pak_anim_source']=str(path)
    armature['pak_anim_mode']=MODE
    bpy.context.view_layer.objects.active=armature
    bpy.ops.object.mode_set(mode='POSE')
    for group in data.get('groups',[]):
        for frame in group.get('frames',[]):
            frame_index=frame.get('frame_index',0)+1
            for item in frame.get('values',[]):
                name=item.get('target_name','')
                value=item.get('value')
                bone=ensure_pose_bone(armature,name)
                if bone is None:
                    continue
                set_value(bone,value)
                insert_value_key(bone,frame_index)
    clear_action_frame_range(action)
    bpy.context.scene.frame_start=1
    bpy.context.scene.frame_end=max(bpy.context.scene.frame_end,int(action.frame_end or 1))
    return action


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
    actions=[]
    for path,data in timelines:
        actions.append(apply_timeline(armature,path,data).name)
    armature['pak_named_timeline_actions']=';'.join(actions)
    if SAVE_BLEND and bpy.data.filepath:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    if EXPORT_GLB:
        export_glb(package_dir)
    print('Imported actions:',len(actions))
    for name in actions:
        print(name)


if __name__=='__main__':
    main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
'''

README='''Blender-Animation Import

1. Charakter-.blend in Blender öffnen.
2. Text Editor > Open > blender_import_named_timelines.py.
3. Run Script.

Standardmodus: rotation_euler.

Optional über Blender CLI:
blender character.blend --python blender_import_named_timelines.py -- --package . --mode rotation_euler

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
