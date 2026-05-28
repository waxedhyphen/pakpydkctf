import json
from pathlib import Path
import anim_track_skel_map_patch as timeline_patch

def _read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None

def _write(path,data):
    Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')

def _rel(root,path):
    return str(Path(path).relative_to(root)).replace('\\','/')

def _scope_named(root,summary_path,items):
    rel=_rel(root,summary_path)
    if rel.startswith('models/'):
        prefix=rel.split('/debug/')[0]+'/debug/'
    else:
        prefix='debug/'
    return [item for item in items if item.startswith(prefix)]

def _scope_skipped(root,summary_path,items):
    rel=_rel(root,summary_path)
    want_model=rel.startswith('models/')
    return [item for item in items if (item.get('probe','').startswith('models/'))==want_model]

def _rewrite_summaries(root,named,skipped,skel_file,node_count,skin_bone_count):
    paths=list(root.glob('debug/anim_probe21_summary.json'))
    paths.extend(root.glob('models/*/debug/anim_probe21_summary.json'))
    for path in paths:
        data=_read(path)
        if not isinstance(data,dict):
            continue
        data['track_skeleton_map']={'version':5,'status':'ok','skeleton_file':skel_file,'node_count':node_count,'skin_bone_count':skin_bone_count,'named_timeline_files':_scope_named(root,path,named),'skipped_timeline_files':_scope_skipped(root,path,skipped)}
        _write(path,data)

def install(App):
    original=timeline_patch._enrich_package
    def enrich_package(package_dir):
        result=original(package_dir)
        try:
            root=Path(package_dir)
            skel,skel_file=timeline_patch._find_skeleton(package_dir)
            if skel is None:
                return result
            named=result.get('named_timeline_files') or []
            skipped=result.get('skipped_timeline_files') or []
            _rewrite_summaries(root,named,skipped,skel_file,len(skel.get('nodes') or []),len(skel.get('bones') or []))
        except Exception as e:
            result['summary_scope_error']=str(e)
        return result
    timeline_patch._enrich_package=enrich_package
