from pathlib import Path
import blender_named_timeline_patch as blender_patch

PREVIEW_SCRIPT=r'''
import sys
from pathlib import Path

try:
    here=Path(__file__).resolve().parent
except Exception:
    import bpy
    here=Path(bpy.data.filepath).resolve().parent if bpy.data.filepath else Path.cwd()

script=here/'blender_import_named_timelines.py'
if not script.exists():
    raise RuntimeError('blender_import_named_timelines.py nicht gefunden')

sys.argv=[str(script),'--','--mode','rotation_euler','--scale','0.25']
code=script.read_text(encoding='utf-8')
exec(compile(code,str(script),'exec'),{'__name__':'__main__','__file__':str(script)})
'''

PREVIEW_README='''Blender sichtbare Vorschau

Diese Datei bewegt das Modell testweise sichtbar:
blender_preview_named_timelines.py

Sie ist nur eine Vorschau.
Die Werte sind noch nicht endgültig als echte Rotation geknackt.

Wenn die Bewegung falsch aussieht, ist das erwartbar.
Die sichere Datei bleibt:
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
