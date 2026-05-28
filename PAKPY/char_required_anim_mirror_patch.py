from pathlib import Path
import shutil
import anim_track_skel_map_patch as timeline_patch

def _copy_file(src,dst):
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)
    return True

def _copy_dir_files(src_dir,dst_dir,pattern):
    copied=[]
    src_dir=Path(src_dir)
    dst_dir=Path(dst_dir)
    if not src_dir.exists():
        return copied
    for src in sorted(src_dir.glob(pattern)):
        if not src.is_file():
            continue
        dst=dst_dir/src.name
        if _copy_file(src,dst):
            copied.append(str(dst))
    return copied

def _rel(root,path):
    try:
        return str(Path(path).relative_to(root)).replace('\\','/')
    except Exception:
        return str(path).replace('\\','/')

def _mirror_required_anim_files(package_dir):
    root=Path(package_dir)
    model_dirs=[path for path in sorted(root.glob('models/*_smdl_package')) if path.is_dir()]
    if not model_dirs:
        return []
    mirrored=[]
    for model_dir in model_dirs:
        copied=[]
        copied.extend(_copy_dir_files(root/'source'/'anim',model_dir/'source'/'anim','*.anim'))
        copied.extend(_copy_dir_files(root/'debug'/'anim_probe21',model_dir/'debug'/'anim_probe21','*.probe21.json'))
        copied.extend(_copy_dir_files(root/'debug'/'anim_named_timeline',model_dir/'debug'/'anim_named_timeline','*.named_timeline.json'))
        for name in ('anim_probe21_summary.json','anim_structure_report.json'):
            if _copy_file(root/'debug'/name,model_dir/'debug'/name):
                copied.append(str(model_dir/'debug'/name))
        if copied:
            mirrored.append({'model_package':_rel(root,model_dir),'copied_files':[_rel(root,path) for path in copied]})
    return mirrored

def install(App):
    original=timeline_patch._enrich_package
    def enrich_package(package_dir):
        result=original(package_dir)
        try:
            mirrored=_mirror_required_anim_files(package_dir)
            result['mirrored_required_animation_files']=mirrored
        except Exception as e:
            result['mirror_required_animation_files_error']=str(e)
        return result
    timeline_patch._enrich_package=enrich_package
