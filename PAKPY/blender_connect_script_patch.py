import json
import skeletal_tail_patch

def _global_heads(bones):
    heads=[]
    for bone in bones:
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
        h=bone.get('head') or [0.0,0.0,0.0]
        head=[float(h[0]),float(h[1]),float(h[2])] if len(h)>=3 else [0.0,0.0,0.0]
        heads.append([heads[parent][0]+head[0],heads[parent][1]+head[1],heads[parent][2]+head[2]] if 0<=parent<len(heads) else head)
    return heads

def _connect_script_text(armature_hint,bones):
    real=[bone for bone in bones if not bone.get('_end_node')]
    heads=_global_heads(real)
    names=[str(bone.get('name') or f'bone_{i:03d}') for i,bone in enumerate(real)]
    head_map={names[i]:heads[i] for i in range(len(names))}
    roots=[];connections=[]
    for index,bone in enumerate(real):
        parent=bone.get('parent_index',-1)
        try:
            parent=int(parent)
        except Exception:
            parent=-1
        if 0<=parent<len(real):
            connections.append([names[parent],names[index]])
        else:
            roots.append(names[index])
    return '\n'.join([
        'import bpy',
        'from mathutils import Vector',
        f'ARMATURE_HINT={json.dumps(armature_hint)}',
        f'HEADS={json.dumps(head_map,separators=(",",":"))}',
        f'CONNECTIONS={json.dumps(connections,separators=(",",":"))}',
        f'ROOTS={json.dumps(roots,separators=(",",":"))}',
        'EPS=0.0001',
        'def armature_object():',
        '    obj=bpy.context.object',
        "    if obj is not None and obj.type=='ARMATURE':",
        '        return obj',
        '    for obj in bpy.context.scene.objects:',
        "        if obj.type=='ARMATURE' and (ARMATURE_HINT in obj.name or not ARMATURE_HINT):",
        '            return obj',
        '    for obj in bpy.context.scene.objects:',
        "        if obj.type=='ARMATURE':",
        '            return obj',
        "    raise RuntimeError('No armature found')",
        'def run():',
        '    obj=armature_object()',
        "    bpy.ops.object.mode_set(mode='OBJECT') if bpy.context.object else None",
        "    bpy.ops.object.select_all(action='DESELECT')",
        '    obj.select_set(True)',
        '    bpy.context.view_layer.objects.active=obj',
        "    bpy.ops.object.mode_set(mode='EDIT')",
        '    def P(name):',
        '        return Vector(HEADS[name])',
        '    eb=obj.data.edit_bones',
        '    for name in list(eb.keys()):',
        "        if name.endswith('_end'):",
        '            eb.remove(eb[name])',
        '    children_by_parent={}',
        '    for parent,child in CONNECTIONS:',
        '        children_by_parent.setdefault(parent,[]).append(child)',
        '    for root in ROOTS:',
        '        if root in eb and root in HEADS:',
        '            b=eb[root]',
        '            b.head=P(root)',
        '            children=children_by_parent.get(root,[])',
        '            if children:',
        '                b.tail=P(children[0])',
        '            else:',
        '                h=HEADS[root];b.tail=Vector((h[0],h[1]+0.035,h[2]))',
        '            b.use_connect=False',
        '    for parent,child in CONNECTIONS:',
        '        if child not in eb or parent not in HEADS or child not in HEADS:',
        '            continue',
        '        b=eb[child]',
        '        b.head=P(parent)',
        '        b.tail=P(child)',
        '        if (b.tail-b.head).length<EPS:',
        '            b.tail=b.head+Vector((0.0,0.035,0.0))',
        '        if parent in eb:',
        '            b.parent=eb[parent]',
        '    for parent,child in CONNECTIONS:',
        '        if child not in eb or parent not in eb:',
        '            continue',
        '        b=eb[child];p=eb[parent]',
        '        if (b.head-p.tail).length<EPS:',
        '            b.use_connect=True',
        "    bpy.ops.object.mode_set(mode='OBJECT')",
        'run()',
        ''
    ])

def install():
    skeletal_tail_patch._connect_script_text=_connect_script_text
