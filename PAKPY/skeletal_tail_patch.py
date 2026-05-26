import skeletal_codec

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

def install():
    skeletal_codec._tail=_patched_tail
