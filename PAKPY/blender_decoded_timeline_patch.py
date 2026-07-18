"""Write a Blender importer that consumes typed decoded ANIM channels."""
from pathlib import Path
import blender_named_timeline_patch as blender_patch


BLENDER_SCRIPT = r'''
import argparse
import json
import sys
from pathlib import Path

import bpy

REPORT_NAME = 'blender_decoded_anim_report.json'
FPS = 30


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')


def package_candidates(path):
    path = Path(path)
    if path.suffix:
        path = path.parent
    return [path] + list(path.parents)


def is_package(path):
    return (path / 'debug' / 'anim_named_timeline').exists() or bool(list(path.glob('models/*/debug/anim_named_timeline')))


def find_package(explicit=''):
    if explicit:
        return Path(explicit).resolve()
    starts = [Path.cwd()]
    if bpy.data.filepath:
        starts.insert(0, Path(bpy.data.filepath).resolve())
    try:
        starts.insert(0, Path(__file__).resolve())
    except Exception:
        pass
    seen = set()
    for start in starts:
        for candidate in package_candidates(start):
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            if is_package(candidate):
                return candidate
    raise RuntimeError('Character-Package mit anim_named_timeline wurde nicht gefunden')


def collect_timelines(root):
    paths = list(root.glob('debug/anim_named_timeline/*.named_timeline.json'))
    paths.extend(root.glob('models/*/debug/anim_named_timeline/*.named_timeline.json'))
    out = []
    seen = set()
    for path in paths:
        data = load_json(path)
        identity = data.get('uuid_hex') or data.get('char_animation_name') or str(path)
        if identity in seen or data.get('type') != 'ANIM_NAMED_TIMELINE':
            continue
        seen.add(identity)
        out.append((path, data))
    return out


def normalise_name(value):
    value = str(value or '').lower().replace(' ', '').replace('_', '').replace('-', '').replace('.', '')
    for suffix in ('jntskin', 'skin', 'joint', 'jnt'):
        if value.endswith(suffix):
            value = value[:-len(suffix)]
    return value


def find_armature(name=''):
    if name:
        obj = bpy.data.objects.get(name)
        if obj and obj.type == 'ARMATURE':
            return obj
    active = bpy.context.view_layer.objects.active
    if active and active.type == 'ARMATURE':
        return active
    for obj in list(bpy.context.selected_objects) + list(bpy.context.scene.objects):
        if obj.type == 'ARMATURE':
            return obj
    raise RuntimeError('Keine Armature in der geöffneten .blend-Datei gefunden')


def bone_lookup(armature):
    out = {}
    for bone in armature.pose.bones:
        out[bone.name] = bone
        out[normalise_name(bone.name)] = bone
    return out


def find_bone(lookup, name):
    return lookup.get(name) or lookup.get(normalise_name(name))


def activate(armature):
    if bpy.context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except Exception:
            pass
    for obj in bpy.context.scene.objects:
        obj.select_set(False)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.object.mode_set(mode='POSE')


def set_channel(bone, channel, value, frame):
    if value is None:
        return 0
    if channel == 'rotation_quaternion':
        if len(value) != 4:
            return 0
        bone.rotation_mode = 'QUATERNION'
        bone.rotation_quaternion = tuple(float(item) for item in value)
        bone.keyframe_insert(data_path='rotation_quaternion', frame=frame, group=bone.name)
        return 4
    if channel == 'location':
        if len(value) != 3:
            return 0
        bone.location = tuple(float(item) for item in value)
        bone.keyframe_insert(data_path='location', frame=frame, group=bone.name)
        return 3
    if channel == 'scale':
        if len(value) != 3:
            return 0
        bone.scale = tuple(float(item) for item in value)
        bone.keyframe_insert(data_path='scale', frame=frame, group=bone.name)
        return 3
    return 0


def action_name(path, data):
    value = data.get('char_animation_name') or data.get('entry_name') or path.stem
    return ''.join(char if char.isalnum() or char in '._-' else '_' for char in value)


def import_timeline(armature, lookup, path, data):
    name = action_name(path, data)
    old = bpy.data.actions.get(name)
    if old:
        bpy.data.actions.remove(old)
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    armature.animation_data_create()
    armature.animation_data.action = action
    report = {'action': name, 'source': str(path), 'inserted_channels': 0, 'matched_bones': [], 'missing_targets': [], 'unsupported_channels': [], 'frame_end': 1}
    matched = set()
    missing = set()
    unsupported = set()
    for group in data.get('groups') or []:
        for frame_data in group.get('frames') or []:
            frame = int(frame_data.get('absolute_frame_index', frame_data.get('frame_index', 0))) + 1
            report['frame_end'] = max(report['frame_end'], frame)
            for item in frame_data.get('values') or []:
                channel = item.get('channel') or 'raw'
                if channel not in {'rotation_quaternion', 'location', 'scale'}:
                    unsupported.add(channel)
                    continue
                target = item.get('target_name') or ''
                bone = find_bone(lookup, target)
                if bone is None:
                    missing.add(target)
                    continue
                inserted = set_channel(bone, channel, item.get('value'), frame)
                if inserted:
                    matched.add(bone.name)
                    report['inserted_channels'] += inserted
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'
    report['matched_bones'] = sorted(matched)
    report['missing_targets'] = sorted(missing)
    report['unsupported_channels'] = sorted(unsupported)
    return action, report


def parse_args(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--package', default='')
    parser.add_argument('--armature', default='')
    parser.add_argument('--fps', type=int, default=FPS)
    parser.add_argument('--no-save', action='store_true')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or [])
    root = find_package(args.package)
    armature = find_armature(args.armature)
    activate(armature)
    lookup = bone_lookup(armature)
    timelines = collect_timelines(root)
    report = {'package_dir': str(root), 'armature': armature.name, 'timeline_count': len(timelines), 'actions': [], 'errors': []}
    actions = []
    max_frame = 1
    for path, data in timelines:
        action, action_report = import_timeline(armature, lookup, path, data)
        report['actions'].append(action_report)
        if action_report['inserted_channels']:
            actions.append(action)
            max_frame = max(max_frame, action_report['frame_end'])
    if actions:
        armature.animation_data.action = actions[0]
        bpy.context.scene.frame_start = 1
        bpy.context.scene.frame_end = max_frame
        bpy.context.scene.render.fps = args.fps
        bpy.context.scene.frame_set(1)
    else:
        report['errors'].append('Keine verifiziert dekodierten Transform-Kanäle gefunden')
    write_json(root / REPORT_NAME, report)
    if not args.no_save and bpy.data.filepath and actions:
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)
    print('Imported decoded actions:', len(actions))
    print('Report:', root / REPORT_NAME)


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
'''

PREVIEW_SCRIPT = r'''
import sys
from pathlib import Path

try:
    here = Path(__file__).resolve().parent
except Exception:
    import bpy
    here = Path(bpy.data.filepath).resolve().parent if bpy.data.filepath else Path.cwd()

for root in [here] + list(here.parents):
    script = root / 'blender_import_named_timelines.py'
    if script.is_file():
        sys.argv = [str(script), '--', '--package', str(root)]
        code = script.read_text(encoding='utf-8')
        exec(compile(code, str(script), 'exec'), {'__name__': '__main__', '__file__': str(script)})
        break
else:
    raise RuntimeError('blender_import_named_timelines.py wurde nicht gefunden')
'''


def install(App):
    original = blender_patch._write_blender_files

    def write_blender_files(package_dir):
        result = original(package_dir)
        root = Path(package_dir)
        (root / 'blender_import_named_timelines.py').write_text(BLENDER_SCRIPT.strip() + '\n', encoding='utf-8', newline='\n')
        (root / 'blender_preview_named_timelines.py').write_text(PREVIEW_SCRIPT.strip() + '\n', encoding='utf-8', newline='\n')
        result['decoded_channel_importer'] = 'blender_import_named_timelines.py'
        return result

    blender_patch._write_blender_files = write_blender_files
