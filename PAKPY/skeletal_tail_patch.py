from pathlib import Path
import json
import os
import shlex
import shutil
import struct
import subprocess
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

def _project_axis(axis,normal):
    projected=_sub(axis,[normal[0]*_dot(axis,normal),normal[1]*_dot(axis,normal),normal[2]*_dot(axis,normal)])
    return None if _len(projected)<=0.000001 else _unit(projected,[1.0,0.0,0.0])

def _basis_from_source(head,target,source_matrix):
    y=_unit(_sub(target,head),[0.0,1.0,0.0])
    if isinstance(source_matrix,list) and len(source_matrix)==16:
        source_x=_unit([source_matrix[0],source_matrix[1],source_matrix[2]],[1.0,0.0,0.0])
        source_z=_unit([source_matrix[8],source_matrix[9],source_matrix[10]],[0.0,0.0,1.0])
        x=_project_axis(source_x,y)
        if x is not None:
            z=_unit(_cross(x,y),[0.0,0.0,1.0])
            return x,y,z
        z=_project_axis(source_z,y)
        if z is not None:
            x=_unit(_cross(y,z),[1.0,0.0,0.0])
            return x,y,z
    ref=[0.0,0.0,1.0] if abs(_dot(y,[0.0,0.0,1.0]))<0.95 else [1.0,0.0,0.0]
    x=_unit(_cross(y,ref),[1.0,0.0,0.0])
    z=_unit(_cross(x,y),[0.0,0.0,1.0])
    return x,y,z

def _global_heads(bones):
    local_heads=[_vec3(bone.get('head')) for bone in bones]
    parents=[]
    for bone in bones:
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
        parents.append(parent if 0<=parent<len(bones) else -1)
    memo={}
    visiting=set()
    def resolve(index):
        if index in memo:
            return memo[index]
        parent=parents[index]
        if parent<0 or parent==index or parent in visiting:
            out=local_heads[index]
        else:
            visiting.add(index)
            out=_add(resolve(parent),local_heads[index])
            visiting.discard(index)
        memo[index]=out
        return out
    return [resolve(index) for index in range(len(bones))]

def _capture_export_bones(original):
    def normalise(bones):
        out=original(bones)
        for index,bone in enumerate(out):
            source=bones[index] if index<len(bones) else {}
            for key in ('matrix','global_matrix','inverse_bind_matrix','translation','rotation','scale'):
                if key in source:
                    bone[key]=source[key]
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

def _connected_globals(bones):
    heads=_global_heads(bones)
    children=_children_by_parent(bones)
    globals_=[]
    for index,bone in enumerate(bones):
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
        target=heads[index]
        if 0<=parent<len(heads):
            head=heads[parent]
        else:
            child_items=children.get(index,[])
            if child_items:
                direction=_unit(_sub(heads[child_items[0]],target),[0.0,1.0,0.0])
            else:
                tail=_vec3(bone.get('tail'))
                direction=_unit(_sub(tail,target),[0.0,1.0,0.0])
            head=_sub(target,[direction[0]*0.035,direction[1]*0.035,direction[2]*0.035])
        x,y,z=_basis_from_source(head,target,bone.get('global_matrix') or bone.get('matrix'))
        globals_.append(_cm_from_basis(head,x,y,z))
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
    globals_=_connected_globals(bones[:count])
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

def _find_blender_exe():
    for key in ('PAKPY_BLENDER_EXE','BLENDER_EXE'):
        value=os.environ.get(key,'').strip().strip('"')
        if value and Path(value).is_file():
            return value
    found=shutil.which('blender')
    if found:
        return found
    roots=[]
    for key in ('ProgramFiles','ProgramFiles(x86)','LOCALAPPDATA'):
        value=os.environ.get(key)
        if value:
            roots.append(Path(value))
    candidates=[]
    for root in roots:
        candidates.extend(root.glob('Blender Foundation/Blender*/blender.exe'))
        candidates.extend(root.glob('Programs/Blender Foundation/Blender*/blender.exe'))
    existing=sorted((path for path in candidates if path.is_file()),key=lambda p:str(p),reverse=True)
    return str(existing[0]) if existing else ''

def _connected_blend_script(glb_path,blend_path,obj_path=None):
    return '\n'.join([
        'import bpy',
        'from pathlib import Path',
        'from mathutils import Vector',
        f'GLB_PATH={json.dumps(str(glb_path))}',
        f'BLEND_PATH={json.dumps(str(blend_path))}',
        f'OBJ_PATH={json.dumps(str(obj_path or ""))}',
        'EPS=0.0001',
        'try:',
        "    bpy.ops.object.mode_set(mode='OBJECT')",
        'except Exception:',
        '    pass',
        "bpy.ops.object.select_all(action='SELECT')",
        'bpy.ops.object.delete()',
        'try:',
        "    bpy.ops.preferences.addon_enable(module='io_scene_gltf2')",
        'except Exception:',
        '    pass',
        'bpy.ops.import_scene.gltf(filepath=GLB_PATH)',
        "armatures=[obj for obj in bpy.context.scene.objects if obj.type=='ARMATURE']",
        "if not armatures:",
        "    raise RuntimeError('No armature imported from GLB')",
        'armature_obj=max(armatures,key=lambda item: len(item.data.bones))',
        "bpy.ops.object.select_all(action='DESELECT')",
        'armature_obj.select_set(True)',
        'bpy.context.view_layer.objects.active=armature_obj',
        "bpy.ops.object.mode_set(mode='EDIT')",
        'eb=armature_obj.data.edit_bones',
        'for bone in eb:',
        '    bone.use_connect=False',
        'connected=0',
        'for bone in eb:',
        '    parent=bone.parent',
        '    if parent is None:',
        '        continue',
        '    tail=bone.tail.copy()',
        '    bone.head=parent.tail.copy()',
        '    if (tail-bone.head).length<EPS:',
        '        tail=bone.head+Vector((0.0,0.035,0.0))',
        '    bone.tail=tail',
        '    bone.use_connect=True',
        '    connected+=1',
        "bpy.ops.object.mode_set(mode='OBJECT')",
        'def _base_material_name(name):',
        "    text=str(name or '')",
        "    if len(text)>4 and text[-4]=='.' and text[-3:].isdigit():",
        '        text=text[:-4]',
        '    return text.strip()',
        "target_meshes=[mesh_obj for mesh_obj in bpy.context.scene.objects if mesh_obj.type=='MESH' and mesh_obj.data.materials]",
        'target_material_names={}',
        'for mesh_obj in target_meshes:',
        '    names=[]',
        '    for mat in mesh_obj.data.materials:',
        '        names.append(_base_material_name(mat.name if mat else ""))',
        '        if mat:',
        '            mat.name="__PAKPY_GLB__"+mat.name',
        '    target_material_names[mesh_obj.name]=names',
        'def _import_obj_materials():',
        '    if not OBJ_PATH or not Path(OBJ_PATH).is_file():',
        '        return {}, 0',
        '    before=set(bpy.context.scene.objects)',
        '    try:',
        '        bpy.ops.wm.obj_import(filepath=OBJ_PATH)',
        '    except Exception:',
        '        try:',
        '            bpy.ops.import_scene.obj(filepath=OBJ_PATH)',
        '        except Exception:',
        '            return {}, 0',
        '    imported=[obj for obj in bpy.context.scene.objects if obj not in before]',
        '    materials={}',
        '    for mesh_obj in imported:',
        "        if mesh_obj.type!='MESH':",
        '            continue',
        '        for mat in mesh_obj.data.materials:',
        '            if mat:',
        '                materials.setdefault(_base_material_name(mat.name), mat)',
        "    bpy.ops.object.select_all(action='DESELECT')",
        '    for mesh_obj in imported:',
        '        mesh_obj.select_set(True)',
        '    if imported:',
        '        bpy.ops.object.delete()',
        '    return materials, len(materials)',
        'obj_materials, obj_material_count=_import_obj_materials()',
        'material_copies=0',
        'if obj_materials:',
        '    for mesh_obj in target_meshes:',
        '        for material_index,mat in enumerate(list(mesh_obj.data.materials)):',
        '            names=target_material_names.get(mesh_obj.name, [])',
        '            material_name=names[material_index] if material_index<len(names) else _base_material_name(mat.name if mat else "")',
        '            source=obj_materials.get(material_name)',
        '            if source:',
        '                source.name=material_name',
        '                mesh_obj.data.materials[material_index]=source',
        '                material_copies+=1',
        '            elif mat and material_name:',
        '                mat.name=material_name',
        '    if material_copies:',
        '        try:',
        '            bpy.ops.file.pack_all()',
        '        except Exception:',
        '            pass',
        'else:',
        '    for mesh_obj in target_meshes:',
        '        names=target_material_names.get(mesh_obj.name, [])',
        '        for material_index,mat in enumerate(list(mesh_obj.data.materials)):',
        '            if mat and material_index<len(names):',
        '                mat.name=names[material_index]',
        'Path(BLEND_PATH).parent.mkdir(parents=True,exist_ok=True)',
        'bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)',
        "print('PAKPY_CONNECTED_BONES=%d' % connected)",
        "print('PAKPY_OBJ_MATERIALS=%d' % obj_material_count)",
        "print('PAKPY_MATERIAL_COPIES=%d' % material_copies)",
        ''
    ])

def _write_connected_blend(glb_path,debug_dir=None,obj_path=None):
    glb_path=Path(glb_path)
    blend_path=glb_path.with_suffix('.blend')
    blender=_find_blender_exe()
    if not blender:
        return {'blend_path':'','error':'Blender nicht gefunden; setze PAKPY_BLENDER_EXE auf blender.exe, wenn automatisch eine .blend erzeugt werden soll.'}
    script_dir=Path(debug_dir) if debug_dir else glb_path.parent
    script_dir.mkdir(parents=True,exist_ok=True)
    script_path=script_dir/(glb_path.stem+'.connected_blend_tmp.py')
    script_path.write_text(_connected_blend_script(glb_path,blend_path,obj_path=obj_path),encoding='utf-8',newline='\n')
    creationflags=0x08000000 if os.name=='nt' else 0
    try:
        completed=subprocess.run([blender,'--background','--factory-startup','--python',str(script_path)],capture_output=True,text=True,timeout=300,creationflags=creationflags)
    except Exception as e:
        return {'blend_path':'','error':str(e)}
    finally:
        try:
            script_path.unlink()
        except Exception:
            pass
    if completed.returncode!=0 or not blend_path.is_file():
        output=((completed.stdout or '')+'\n'+(completed.stderr or '')).strip()
        return {'blend_path':'','error':output[-2000:] or f'Blender returned {completed.returncode}'}
    return {'blend_path':str(blend_path),'error':''}

def _texture_png_path_from_manifest(package_dir,item):
    text=str(item.get('png_name') or '').replace('\\','/')
    if not text:
        return ''
    if '/' in text:
        return text
    nested=Path(package_dir)/'textures'/'png'/text
    return f'textures/png/{text}' if nested.is_file() else text

def _is_base_color_candidate(item):
    tag=str(item.get('ref_tag') or '').upper()
    if str(item.get('mtl_slot') or '')=='map_Kd':
        return True
    blocked=('NMAP','NRML','NORM','SPCT','SPEC','SPCF','EMIS','ICAN','REFV','REFS','FUR')
    return not any(part in tag for part in blocked)

def _texture_map_from_manifest(package_dir,manifest):
    material_slots={}
    material_names={}
    fallback_kd={}
    for item in (manifest or {}).get('textures',[]):
        if item.get('missing'):
            continue
        png_name=_texture_png_path_from_manifest(package_dir,item)
        if not png_name:
            continue
        try:
            material_index=int(item.get('material_index',0))
        except Exception:
            material_index=0
        material_name=str(item.get('material_name') or '')
        key=(material_index,material_name)
        material_names[material_index]=material_name
        slot=str(item.get('mtl_slot') or '')
        if slot:
            material_slots.setdefault(material_index,{}).setdefault(slot,png_name)
        if key not in fallback_kd and _is_base_color_candidate(item):
            material_slots.setdefault(material_index,{})
            fallback_kd[key]=png_name
    out={}
    for material_index,slot_map in material_slots.items():
        material_name=material_names.get(material_index,'')
        fallback=fallback_kd.get((material_index,material_name),'')
        if 'map_Kd' not in slot_map and fallback:
            slot_map['map_Kd']=fallback
        if slot_map:
            out[material_index]=dict(slot_map)
            if material_name:
                out[material_name]=dict(slot_map)
    return out

def _texture_map_from_mtl(package_dir,mtl_path):
    mtl_path=Path(mtl_path) if mtl_path else None
    if not mtl_path or not mtl_path.is_file():
        return {}
    out={}
    material_name=''
    slot_map={}
    def finish():
        if not material_name or not slot_map:
            return
        data=dict(slot_map)
        out[material_name]=data
    for raw_line in mtl_path.read_text(encoding='utf-8',errors='replace').splitlines():
        line=raw_line.strip()
        if not line or line.startswith('#'):
            continue
        try:
            parts=shlex.split(line)
        except Exception:
            parts=line.split()
        if not parts:
            continue
        key=parts[0]
        if key=='newmtl':
            finish()
            material_name=' '.join(parts[1:]).strip()
            slot_map={}
            continue
        if key not in ('map_Kd','map_Bump','map_Ks','map_Ke') or len(parts)<2:
            continue
        text=' '.join(parts[1:]).replace('\\','/')
        texture_path=Path(text)
        if not texture_path.is_absolute():
            texture_path=mtl_path.parent/texture_path
        try:
            slot_map[key]=os.path.relpath(str(texture_path),str(package_dir)).replace('\\','/')
        except Exception:
            slot_map[key]=str(texture_path).replace('\\','/')
    finish()
    return out

def _export_rigged_with_connected_joints(original):
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
            manifest_path=package_dir/'repack_manifest.json'
            existing_manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {}
            texture_map=_texture_map_from_mtl(package_dir,result.get('mtl','')) or _texture_map_from_manifest(package_dir,existing_manifest)
            glb_result=rigged_gltf.export_rigged_model_glb(parsed,entry,glb_path,require_store=require_store,skeleton_refs=skeleton_refs,texture_map=texture_map,texture_root=package_dir)
            result['experimental_skeletal_glb']=str(glb_path);result['experimental_skeletal_glb_error']=''
            blend_result=_write_connected_blend(glb_path,package_dir/'debug',obj_path=result.get('obj',''))
            result['experimental_skeletal_blend']=blend_result.get('blend_path','')
            result['experimental_skeletal_blend_error']=blend_result.get('error','')
            old_script_path=glb_path.with_suffix('.connect_blender.py')
            if old_script_path.is_file():
                old_script_path.unlink()
            if manifest_path.is_file():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest['experimental_skeletal_glb']=str(glb_path.relative_to(package_dir)).replace('\\','/')
                manifest['experimental_skeletal_glb_sha1']=model_package.sha1_bytes(glb_path.read_bytes())
                manifest['experimental_skeletal_glb_error']=''
                manifest['experimental_skeletal_coordinate_fix']=glb_result.get('coordinate_fix','')
                if blend_result.get('blend_path') and Path(blend_result['blend_path']).is_file():
                    blend_path=Path(blend_result['blend_path'])
                    manifest['experimental_skeletal_blend']=str(blend_path.relative_to(package_dir)).replace('\\','/')
                    manifest['experimental_skeletal_blend_sha1']=model_package.sha1_bytes(blend_path.read_bytes())
                    manifest['experimental_skeletal_blend_error']=''
                else:
                    manifest['experimental_skeletal_blend']=''
                    manifest['experimental_skeletal_blend_sha1']=''
                    manifest['experimental_skeletal_blend_error']=blend_result.get('error','')
                manifest.pop('experimental_skeletal_connect_blender_script',None)
                manifest.pop('experimental_skeletal_connect_blender_script_sha1',None)
                manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
                model_package._write_report(package_dir,manifest)
        except Exception as e:
            result['experimental_skeletal_glb']='';result['experimental_skeletal_glb_error']=str(e)
        return result
    return export_model_package

def install():
    if not getattr(rigged_gltf._normalise_bone_nodes,'_capture_export_bones_patch',False):
        patched=_capture_export_bones(rigged_gltf._normalise_bone_nodes);patched._capture_export_bones_patch=True;rigged_gltf._normalise_bone_nodes=patched
    if not getattr(rigged_gltf.export_rigged_model_glb,'_connected_joint_patch',False):
        patched_glb=_export_rigged_with_connected_joints(rigged_gltf.export_rigged_model_glb);patched_glb._connected_joint_patch=True;rigged_gltf.export_rigged_model_glb=patched_glb
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
