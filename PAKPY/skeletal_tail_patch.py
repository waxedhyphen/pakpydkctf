from pathlib import Path
import json
import struct
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

def _dot(a,b):
    return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

def _cross(a,b):
    return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]

def _len(v):
    return max(0.0,_dot(v,v))**0.5

def _unit(v,fallback):
    l=_len(v)
    return list(fallback) if l<=0.000001 else [v[0]/l,v[1]/l,v[2]/l]

def _cm_identity():
    return [1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0]

def _cm_mul(a,b):
    out=[0.0]*16
    for c in range(4):
        for r in range(4):
            out[c*4+r]=sum(a[k*4+r]*b[c*4+k] for k in range(4))
    return out

def _cm_inv_rt(m):
    x=[m[0],m[1],m[2]];y=[m[4],m[5],m[6]];z=[m[8],m[9],m[10]];t=[m[12],m[13],m[14]]
    out=_cm_identity()
    out[0]=x[0];out[1]=y[0];out[2]=z[0]
    out[4]=x[1];out[5]=y[1];out[6]=z[1]
    out[8]=x[2];out[9]=y[2];out[10]=z[2]
    out[12]=-_dot(x,t);out[13]=-_dot(y,t);out[14]=-_dot(z,t)
    return out

def _cm_from_basis(head,x,y,z):
    return [x[0],x[1],x[2],0.0,y[0],y[1],y[2],0.0,z[0],z[1],z[2],0.0,head[0],head[1],head[2],1.0]

def _basis_to_target(head,target):
    y=_unit(_sub(target,head),[0.0,1.0,0.0])
    ref=[0.0,0.0,1.0] if abs(_dot(y,[0.0,0.0,1.0]))<0.95 else [1.0,0.0,0.0]
    x=_unit(_cross(ref,y),[1.0,0.0,0.0])
    z=_unit(_cross(x,y),[0.0,0.0,1.0])
    return x,y,z

def _global_heads(bones):
    heads=[]
    for bone in bones:
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
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
            out.append({'index':len(out),'name':str(bone.get('name') or f'bone_{index:03d}')+'_end','parent_index':index,'head':delta,'tail':tail,'_end_node':True})
        rigged_gltf._last_skeletal_export_bones=out
        return out
    return normalise

def _children_by_parent(bones):
    children={i:[] for i in range(len(bones))}
    for index,bone in enumerate(bones):
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
        if 0<=parent<len(bones) and parent!=index:
            children.setdefault(parent,[]).append(index)
    return children

def _oriented_globals(bones):
    heads=_global_heads(bones)
    children=_children_by_parent(bones)
    globals_=[]
    for index,bone in enumerate(bones):
        child_items=children.get(index,[])
        if child_items:
            target=heads[child_items[0]]
        else:
            parent=bone.get('parent_index',-1)
            try:
                parent=int(parent)
            except Exception:
                parent=-1
            if 0<=parent<len(heads):
                target=_add(heads[index],_sub(heads[index],heads[parent]))
            else:
                target=_add(heads[index],[0.0,0.035,0.0])
        x,y,z=_basis_to_target(heads[index],target)
        globals_.append(_cm_from_basis(heads[index],x,y,z))
    return globals_

def _local_matrices(bones,globals_):
    locals_=[]
    for index,bone in enumerate(bones):
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
        locals_.append(_cm_mul(_cm_inv_rt(globals_[parent]),globals_[index]) if 0<=parent<len(globals_) else globals_[index])
    return locals_

def _read_glb(path):
    data=Path(path).read_bytes()
    if len(data)<20:
        return None
    magic,version,total=struct.unpack_from('<III',data,0)
    if magic!=0x46546C67 or version!=2:
        return None
    offset=12;chunks=[]
    while offset+8<=len(data):
        size,kind=struct.unpack_from('<I4s',data,offset);offset+=8
        chunks.append([kind,bytearray(data[offset:offset+size])]);offset+=size
    if not chunks or chunks[0][0]!=b'JSON':
        return None
    return chunks

def _align4(data,pad):
    while len(data)%4:
        data+=pad
    return data

def _write_glb(path,chunks,gltf):
    json_blob=_align4(json.dumps(gltf,separators=(',',':'),ensure_ascii=False).encode('utf-8'),b' ')
    chunks[0]=[b'JSON',bytearray(json_blob)]
    total=12+sum(8+len(chunk) for kind,chunk in chunks)
    out=bytearray(struct.pack('<III',0x46546C67,2,total))
    for kind,chunk in chunks:
        out.extend(struct.pack('<I4s',len(chunk),kind));out.extend(chunk)
    Path(path).write_bytes(out)

def _patch_glb_bind_pose(path,bones):
    chunks=_read_glb(path)
    if chunks is None or len(chunks)<2:
        return False
    gltf=json.loads(bytes(chunks[0][1]).decode('utf-8'))
    nodes=gltf.get('nodes') or []
    skins=gltf.get('skins') or []
    if not skins:
        return False
    skin=skins[0];joints=skin.get('joints') or []
    count=min(len(bones),len(joints),len(nodes))
    if count<=0:
        return False
    globals_=_oriented_globals(bones[:count])
    locals_=_local_matrices(bones[:count],globals_)
    for index in range(count):
        node=nodes[joints[index]]
        node.pop('translation',None);node.pop('rotation',None);node.pop('scale',None)
        node['matrix']=[float(x) for x in locals_[index]]
    accessor_index=skin.get('inverseBindMatrices')
    if accessor_index is not None:
        accessors=gltf.get('accessors') or [];views=gltf.get('bufferViews') or []
        if 0<=accessor_index<len(accessors):
            accessor=accessors[accessor_index];view_index=accessor.get('bufferView')
            if view_index is not None and 0<=view_index<len(views):
                view=views[view_index];offset=int(view.get('byteOffset',0))+int(accessor.get('byteOffset',0));needed=count*64
                if len(chunks[1][1])>=offset+needed:
                    ibm=[]
                    for matrix in globals_:
                        ibm.extend(_cm_inv_rt(matrix))
                    chunks[1][1][offset:offset+needed]=struct.pack('<'+'f'*len(ibm),*ibm)
    _write_glb(path,chunks,gltf)
    return True

def _export_rigged_with_oriented_joints(original):
    def export_rigged_model_glb(parsed,entry,out_path,require_store=None,skeleton_refs=None,texture_map=None,texture_root=None):
        result=original(parsed,entry,out_path,require_store=require_store,skeleton_refs=skeleton_refs,texture_map=texture_map,texture_root=texture_root)
        bones=getattr(rigged_gltf,'_last_skeletal_export_bones',[])
        if bones:
            _patch_glb_bind_pose(result.get('glb_path') or out_path,bones)
        return result
    return export_rigged_model_glb

def _export_package_with_glb(original):
    def export_model_package(parsed,entry,out_dir,require_store=None,animation_refs=None,skeleton_refs=None):
        result=original(parsed,entry,out_dir,require_store=require_store,animation_refs=animation_refs,skeleton_refs=skeleton_refs)
        if not skeleton_refs:
            return result
        package_dir=Path(result['package_dir']);base=model_package.safe_name(entry.get('display_name') or entry.get('name') or entry['uuid_hex'])
        glb_path=package_dir/'model'/f'{base}.experimental_skeletal.glb'
        try:
            rigged_gltf.export_rigged_model_glb(parsed,entry,glb_path,require_store=require_store,skeleton_refs=skeleton_refs,texture_map={},texture_root=package_dir)
            result['experimental_skeletal_glb']=str(glb_path);result['experimental_skeletal_glb_error']=''
            manifest_path=package_dir/'repack_manifest.json'
            if manifest_path.is_file():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest['experimental_skeletal_glb']=str(glb_path.relative_to(package_dir)).replace('\\','/')
                manifest['experimental_skeletal_glb_sha1']=model_package.sha1_bytes(glb_path.read_bytes())
                manifest['experimental_skeletal_glb_error']=''
                manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
        except Exception as e:
            result['experimental_skeletal_glb']='';result['experimental_skeletal_glb_error']=str(e)
        return result
    return export_model_package

def install():
    if not getattr(rigged_gltf._normalise_bone_nodes,'_leaf_end_nodes_patch',False):
        patched=_append_leaf_end_nodes(rigged_gltf._normalise_bone_nodes);patched._leaf_end_nodes_patch=True;rigged_gltf._normalise_bone_nodes=patched
    if not getattr(rigged_gltf.export_rigged_model_glb,'_oriented_joint_patch',False):
        patched_glb=_export_rigged_with_oriented_joints(rigged_gltf.export_rigged_model_glb);patched_glb._oriented_joint_patch=True;rigged_gltf.export_rigged_model_glb=patched_glb
    if not getattr(model_package.export_model_package,'_glb_package_patch',False):
        patched_package=_export_package_with_glb(model_package.export_model_package);patched_package._glb_package_patch=True;model_package.export_model_package=patched_package
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
