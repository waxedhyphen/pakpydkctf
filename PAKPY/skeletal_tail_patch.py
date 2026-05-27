from pathlib import Path
import json
import rigged_gltf
import model_package

def _vec3(value):
    value=value or [0.0,0.0,0.0]
    if len(value)<3:
        return [0.0,0.0,0.0]
    return [float(value[0]),float(value[1]),float(value[2])]

def _sub(a,b):
    return [a[0]-b[0],a[1]-b[1],a[2]-b[2]]

def _add(a,b):
    return [a[0]+b[0],a[1]+b[1],a[2]+b[2]]

def _len(v):
    return (v[0]*v[0]+v[1]*v[1]+v[2]*v[2])**0.5

def _global_heads(bones):
    heads=[]
    for bone in bones:
        parent=int(bone.get('parent_index',-1)) if bone.get('parent_index',-1) is not None else -1
        head=_vec3(bone.get('head'))
        heads.append(_add(heads[parent],head) if 0<=parent<len(heads) else head)
    return heads

def _append_leaf_end_nodes(original):
    def normalise(bones):
        out=original(bones)
        base_count=len(out)
        heads=_global_heads(out)
        has_child=set()
        for bone in out[:base_count]:
            parent=bone.get('parent_index',-1)
            try:
                parent=int(parent)
            except Exception:
                parent=-1
            if 0<=parent<base_count:
                has_child.add(parent)
        for index,bone in enumerate(out[:base_count]):
            if index in has_child:
                continue
            tail=_vec3(bone.get('tail'))
            delta=_sub(tail,heads[index])
            if _len(delta)<=0.000001:
                continue
            out.append({'index':len(out),'name':str(bone.get('name') or f'bone_{index:03d}')+'_end','parent_index':index,'head':delta,'tail':tail})
        return out
    return normalise

def _export_package_with_glb(original):
    def export_model_package(parsed,entry,out_dir,require_store=None,animation_refs=None,skeleton_refs=None):
        result=original(parsed,entry,out_dir,require_store=require_store,animation_refs=animation_refs,skeleton_refs=skeleton_refs)
        if not skeleton_refs:
            return result
        package_dir=Path(result['package_dir'])
        base=model_package.safe_name(entry.get('display_name') or entry.get('name') or entry['uuid_hex'])
        glb_path=package_dir/'model'/f'{base}.experimental_skeletal.glb'
        try:
            rigged_gltf.export_rigged_model_glb(parsed,entry,glb_path,require_store=require_store,skeleton_refs=skeleton_refs,texture_map={},texture_root=package_dir)
            result['experimental_skeletal_glb']=str(glb_path)
            result['experimental_skeletal_glb_error']=''
            manifest_path=package_dir/'repack_manifest.json'
            if manifest_path.is_file():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest['experimental_skeletal_glb']=str(glb_path.relative_to(package_dir)).replace('\\','/')
                manifest['experimental_skeletal_glb_sha1']=model_package.sha1_bytes(glb_path.read_bytes())
                manifest['experimental_skeletal_glb_error']=''
                manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
        except Exception as e:
            result['experimental_skeletal_glb']=''
            result['experimental_skeletal_glb_error']=str(e)
        return result
    return export_model_package

def install():
    if not getattr(rigged_gltf._normalise_bone_nodes,'_leaf_end_nodes_patch',False):
        patched=_append_leaf_end_nodes(rigged_gltf._normalise_bone_nodes)
        patched._leaf_end_nodes_patch=True
        rigged_gltf._normalise_bone_nodes=patched
    if not getattr(model_package.export_model_package,'_glb_package_patch',False):
        patched_package=_export_package_with_glb(model_package.export_model_package)
        patched_package._glb_package_patch=True
        model_package.export_model_package=patched_package
        try:
            import gui
            gui.export_model_package=patched_package
        except Exception:
            pass
        try:
            import char_skeletal_package_patch
            char_skeletal_package_patch.export_model_package=patched_package
        except Exception:
            pass
