import skeletal_codec
import dae_export

def _vec3(value):
    value=value or [0.0,0.0,0.0]
    if len(value)<3:
        return [0.0,0.0,0.0]
    return [float(value[0]),float(value[1]),float(value[2])]

def _sub(a,b):
    return [a[0]-b[0],a[1]-b[1],a[2]-b[2]]

def _len(v):
    return (v[0]*v[0]+v[1]*v[1]+v[2]*v[2])**0.5

def _unit(v,fallback):
    l=_len(v)
    return list(fallback) if l<=0.000001 else [v[0]/l,v[1]/l,v[2]/l]

def _parent(index,children):
    for p,items in children.items():
        if index in items:
            return p
    return -1

def _y_axis(matrix):
    if isinstance(matrix,list) and len(matrix)==16:
        return _unit([float(matrix[1]),float(matrix[5]),float(matrix[9])],[0.0,1.0,0.0])
    return [0.0,1.0,0.0]

def _patched_tail(index,matrix,children,globals_):
    head=_vec3(skeletal_codec._tr(matrix))
    for child in children.get(index,[]):
        if 0<=child<len(globals_):
            child_head=_vec3(skeletal_codec._tr(globals_[child]))
            if _len(_sub(child_head,head))>0.000001:
                return child_head
    parent=_parent(index,children)
    size=0.035
    if 0<=parent<len(globals_):
        size=max(size,_len(_sub(head,_vec3(skeletal_codec._tr(globals_[parent])))))
    axis=_y_axis(matrix)
    return [head[0]+axis[0]*size,head[1]+axis[1]*size,head[2]+axis[2]*size]

def _transform_point(matrix,point):
    return [matrix[0]*point[0]+matrix[1]*point[1]+matrix[2]*point[2]+matrix[3],matrix[4]*point[0]+matrix[5]*point[1]+matrix[6]*point[2]+matrix[7],matrix[8]*point[0]+matrix[9]*point[1]+matrix[10]*point[2]+matrix[11]]

def _local_tail_matrix(bone):
    tail=_vec3(bone.get('tail'))
    matrix=bone.get('global_matrix')
    if isinstance(matrix,list) and len(matrix)==16:
        local=_transform_point(skeletal_codec._inv(matrix),tail)
    else:
        local=_sub(tail,_vec3(bone.get('head')))
    return dae_export._translation_matrix(local)

def _patched_write_bone_node(lines,level,bones,children,index):
    bone=bones[index]
    sid=dae_export._sid(bone.get('name') or f'bone_{index:03d}',f'bone_{index:03d}')
    dae_export._w(lines,level,f'<node id="{sid}" sid="{sid}" name="{dae_export._e(bone.get("name") or sid)}" type="JOINT"><matrix>{dae_export._jf(dae_export._bone_matrix(bone))}</matrix>')
    child_items=children.get(index,[])
    for child in child_items:
        _patched_write_bone_node(lines,level+1,bones,children,child)
    if not child_items:
        end_sid=dae_export._sid((bone.get('name') or f'bone_{index:03d}')+'_end',f'bone_{index:03d}_end')
        dae_export._w(lines,level+1,f'<node id="{end_sid}" sid="{end_sid}" name="{dae_export._e(end_sid)}" type="JOINT"><matrix>{dae_export._jf(_local_tail_matrix(bone))}</matrix></node>')
    dae_export._w(lines,level,'</node>')

def install():
    skeletal_codec._tail=_patched_tail
    dae_export._write_bone_node=_patched_write_bone_node
