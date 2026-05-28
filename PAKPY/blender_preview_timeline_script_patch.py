from pathlib import Path
import blender_named_timeline_patch as blender_patch

PREVIEW_SCRIPT=r'''
import sys
from pathlib import Path

def base_from_blender():
    try:
        p=Path(__file__).resolve()
    except Exception:
        import bpy
        p=Path(bpy.data.filepath).resolve() if bpy.data.filepath else Path.cwd()
    parts=list(p.parts)
    for i,part in enumerate(parts):
        if str(part).lower().endswith('.blend'):
            return Path(*parts[:i])
    return p.parent if p.suffix else p

def find_package_root(start):
    for base in [start]+list(start.parents):
        if (base/'blender_import_named_timelines.py').exists():
            return base
        if (base/'debug'/'anim_named_timeline').exists():
            return base
        if list(base.glob('models/*/debug/anim_named_timeline')):
            return base
    return None

start=base_from_blender()
root=find_package_root(start)
if root is None:
    raise RuntimeError('character_package nicht gefunden')

script=root/'blender_import_named_timelines.py'
if not script.exists():
    raise RuntimeError('blender_import_named_timelines.py nicht gefunden: '+str(script))

sys.argv=[str(script),'--','--package',str(root),'--mode','rotation_euler','--scale','0.25']
code=script.read_text(encoding='utf-8')
exec(compile(code,str(script),'exec'),{'__name__':'__main__','__file__':str(script)})
'''

PREVIEW_README='''Blender sichtbare Vorschau

Diese Datei bewegt das Modell testweise sichtbar:
blender_preview_named_timelines.py

Sie nutzt automatisch den gefundenen Package-Ordner.

Sie funktioniert nur, wenn debug/anim_named_timeline/*.named_timeline.json existiert.
Wenn keine named_timeline-Datei existiert, ist dieses ANIM-Format noch nicht sichtbar dekodiert.

Die Werte sind noch nicht endgültig als echte Rotation geknackt.
Die sichere Analyse-Datei bleibt:
blender_import_named_timelines.py
'''


def install(App):
    original=blender_patch._write_blender_files
    def write_blender_files(package_dir):
        result=original(package_dir)
        root=Path(package_dir)
        script=root/'blender_preview_named_timelines.py'
        readme=root/'BLENDER_PREVIEW_ANIMATION.txt'
        script.write_text(PREVIEW_SCRIPT.strip()+"\n",encoding='utf-8',newline='\n')
        readme.write_text(PREVIEW_README,encoding='utf-8',newline='\n')
        result['preview_script']=script.name
        result['preview_readme']=readme.name
        return result
    blender_patch._write_blender_files=write_blender_files
