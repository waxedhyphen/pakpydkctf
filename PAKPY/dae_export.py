from pathlib import Path
import os
import html
import json
import math
import re
from pak_core import PakError, get_entry_asset, safe_name
from pak_extract import build_faces
from rigged_gltf import load_model_with_skin
from skeletal_codec import parse_skel_asset, resolve_ref

ZERO_UUID = '00000000000000000000000000000000'

def _sid(text, fallback='item'):
    text = str(text or fallback)
    text = re.sub(r'[^A-Za-z0-9_\-]+', '_', text).strip('_')
    if not text:
        text = fallback
    if text[0].isdigit():
        text = '_' + text
    return text

def _xf(value):
    value = float(value)
    if not math.isfinite(value):
        value = 0.0
    if abs(value) < 0.00000001:
        value = 0.0
    return f'{value:.9g}'

def _join_floats(values):
    return ' '.join(_xf(v) for v in values)

def _join_ints(values):
    return ' '.join(str(int(v)) for v in values)

def _e(text):
    return html.escape(str(text or ''), quote=True)

def _indent(lines, level, text):
    lines.append('  ' * level + text)

def _material_names(model, entry):
    names = list(model.get('materials', []))
    if entry.get('model_materials'):
        max_index = max((m['index'] for m in entry['model_materials']), default=-1)
        while len(names) <= max_index:
            names.append(f'material_{len(names)}')
        for material in entry['model_materials']:
            idx = material['index']
            names[idx] = str(material.get('name') or f'material_{idx}')
    if not names:
        names = ['material_0']
    return names

def _texture_info(texture_map, index, name):
    texture_map = texture_map or {}
    info = texture_map.get(index) or texture_map.get(str(name)) or {}
    if isinstance(info, str):
        info = {'map_Kd': info}
    if not info:
        for key, value in texture_map.items():
            if isinstance(key, str) and key.strip().lower() == str(name).strip().lower():
                info = value
                break
    if isinstance(info, str):
        info = {'map_Kd': info}
    return info if isinstance(info, dict) else {}

def _dae_texture_path(path_text, texture_root, out_path):
    if not path_text:
        return ''
    text = str(path_text).replace('\\', '/')
    if texture_root:
        root = Path(texture_root)
        full = root / text
        try:
            return os.path.relpath(str(full), str(Path(out_path).parent)).replace('\\', '/')
        except Exception:
            return str(full).replace('\\', '/')
    return text

def _merge_arrays(model, bone_count):
    positions = []
    normals = []
    uvs = []
    joints = []
    weights = []
    vertex_base = {}
    for vbuf_index in sorted(model['vertex_sets']):
        vertex_set = model['vertex_sets'][vbuf_index]
        vertex_base[vbuf_index] = len(positions)
        positions.extend(vertex_set.get('positions', []))
        normals.extend(vertex_set.get('normals', []))
        uvs.extend(vertex_set.get('uvs', []))
        for joint in vertex_set.get('joints', []):
            joints.append([min(max(0, int(x)), max(0, bone_count - 1)) for x in joint])
        for weight in vertex_set.get('weights', []):
            total = sum(max(0.0, float(x)) for x in weight)
            if total <= 0.000001:
                weights.append([1.0, 0.0, 0.0, 0.0])
            else:
                weights.append([max(0.0, float(x)) / total for x in weight])
    while len(normals) < len(positions):
        normals.append([0.0, 0.0, 1.0])
    while len(uvs) < len(positions):
        uvs.append([0.0, 0.0])
    while len(joints) < len(positions):
        joints.append([0, 0, 0, 0])
    while len(weights) < len(positions):
        weights.append([1.0, 0.0, 0.0, 0.0])
    primitives = []
    face_count = 0
    for mesh in model['meshes']:
        vbuf_index = mesh['vertex_buffer_index']
        ibuf_index = mesh['index_buffer_index']
        if vbuf_index not in model['vertex_sets'] or ibuf_index not in model['index_sets']:
            continue
        vertex_limit = len(model['vertex_sets'][vbuf_index].get('positions', []))
        indices = model['index_sets'][ibuf_index]
        mesh_indices = indices[mesh['index_buffer_offset']:mesh['index_buffer_offset'] + mesh['index_count']]
        faces = build_faces(mesh['primitive_mode'], mesh_indices, vertex_limit=vertex_limit)
        out = []
        base = vertex_base[vbuf_index]
        for a, b, c in faces:
            out.extend([a + base, b + base, c + base])
        if out:
            primitives.append({'name': f'mesh_{mesh["mesh_index"]}', 'indices': out, 'material_index': mesh['material_index']})
            face_count += len(faces)
    if face_count <= 0:
        raise PakError('DAE-Export erzeugte 0 Faces')
    return positions, normals, uvs, joints, weights, primitives, face_count

def _load_skeleton(parsed, require_store, skeleton_refs):
    for ref in skeleton_refs or []:
        uuid_hex = ref.get('uuid_hex', '')
        if not uuid_hex or uuid_hex == ZERO_UUID:
            continue
        asset, entry, source, source_path = resolve_ref(parsed, uuid_hex, require_store)
        if entry is None or asset is None or entry.get('type') != 'SKEL':
            continue
        try:
            summary = parse_skel_asset(asset)
            bones = summary.get('bones') or []
            if bones:
                return {'source_uuid': uuid_hex, 'source_kind': source, 'source_path': source_path, 'summary': summary, 'bones': bones}
        except Exception:
            continue
    return {'source_uuid': '', 'source_kind': '', 'source_path': '', 'summary': {}, 'bones': []}

def _bone_matrix(bone):
    head = bone.get('head') or [0.0, 0.0, 0.0]
    if len(head) < 3:
        head = [0.0, 0.0, 0.0]
    return [1.0, 0.0, 0.0, float(head[0]), 0.0, 1.0, 0.0, float(head[1]), 0.0, 0.0, 1.0, float(head[2]), 0.0, 0.0, 0.0, 1.0]

def _inverse_bind_matrix(bone):
    head = bone.get('head') or [0.0, 0.0, 0.0]
    if len(head) < 3:
        head = [0.0, 0.0, 0.0]
    return [1.0, 0.0, 0.0, -float(head[0]), 0.0, 1.0, 0.0, -float(head[1]), 0.0, 0.0, 1.0, -float(head[2]), 0.0, 0.0, 0.0, 1.0]

def _write_sources(lines, level, geom_id, positions, normals, uvs):
    _indent(lines, level, f'<source id="{geom_id}-positions">')
    _indent(lines, level + 1, f'<float_array id="{geom_id}-positions-array" count="{len(positions) * 3}">{_join_floats(x for p in positions for x in p)}</float_array>')
    _indent(lines, level + 1, f'<technique_common><accessor source="#{geom_id}-positions-array" count="{len(positions)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common>')
    _indent(lines, level, '</source>')
    _indent(lines, level, f'<source id="{geom_id}-normals">')
    _indent(lines, level + 1, f'<float_array id="{geom_id}-normals-array" count="{len(normals) * 3}">{_join_floats(x for n in normals for x in n[:3])}</float_array>')
    _indent(lines, level + 1, f'<technique_common><accessor source="#{geom_id}-normals-array" count="{len(normals)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common>')
    _indent(lines, level, '</source>')
    _indent(lines, level, f'<source id="{geom_id}-uvs">')
    _indent(lines, level + 1, f'<float_array id="{geom_id}-uvs-array" count="{len(uvs) * 2}">{_join_floats(x for uv in uvs for x in uv[:2])}</float_array>')
    _indent(lines, level + 1, f'<technique_common><accessor source="#{geom_id}-uvs-array" count="{len(uvs)}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common>')
    _indent(lines, level, '</source>')
    _indent(lines, level, f'<vertices id="{geom_id}-vertices"><input semantic="POSITION" source="#{geom_id}-positions"/></vertices>')

def _write_geometry(lines, geom_id, entry_name, positions, normals, uvs, primitives, material_symbols):
    _indent(lines, 1, '<library_geometries>')
    _indent(lines, 2, f'<geometry id="{geom_id}" name="{_e(entry_name)}">')
    _indent(lines, 3, '<mesh>')
    _write_sources(lines, 4, geom_id, positions, normals, uvs)
    for primitive in primitives:
        mat_idx = primitive['material_index'] if primitive['material_index'] < len(material_symbols) else 0
        symbol = material_symbols[mat_idx]
        idx = primitive['indices']
        p_values = []
        for value in idx:
            p_values.extend([value, value, value])
        _indent(lines, 4, f'<triangles material="{symbol}" count="{len(idx) // 3}">')
        _indent(lines, 5, f'<input semantic="VERTEX" source="#{geom_id}-vertices" offset="0"/>')
        _indent(lines, 5, f'<input semantic="NORMAL" source="#{geom_id}-normals" offset="1"/>')
        _indent(lines, 5, f'<input semantic="TEXCOORD" source="#{geom_id}-uvs" offset="2" set="0"/>')
        _indent(lines, 5, f'<p>{_join_ints(p_values)}</p>')
        _indent(lines, 4, '</triangles>')
    _indent(lines, 3, '</mesh>')
    _indent(lines, 2, '</geometry>')
    _indent(lines, 1, '</library_geometries>')

def _write_materials(lines, material_names, texture_map, texture_root, out_path):
    image_items = []
    for index, name in enumerate(material_names):
        info = _texture_info(texture_map, index, name)
        tex = info.get('map_Kd') or info.get('baseColorTexture') or ''
        tex_path = _dae_texture_path(tex, texture_root, out_path)
        image_items.append((index, name, tex_path))
    if any(tex for _, _, tex in image_items):
        _indent(lines, 1, '<library_images>')
        for index, name, tex in image_items:
            if tex:
                _indent(lines, 2, f'<image id="image_{index}" name="{_e(name)}"><init_from>{_e(tex)}</init_from></image>')
        _indent(lines, 1, '</library_images>')
    _indent(lines, 1, '<library_effects>')
    for index, name, tex in image_items:
        _indent(lines, 2, f'<effect id="effect_{index}">')
        _indent(lines, 3, '<profile_COMMON>')
        if tex:
            _indent(lines, 4, f'<newparam sid="surface_{index}"><surface type="2D"><init_from>image_{index}</init_from></surface></newparam>')
            _indent(lines, 4, f'<newparam sid="sampler_{index}"><sampler2D><source>surface_{index}</source></sampler2D></newparam>')
        _indent(lines, 4, '<technique sid="common"><phong>')
        if tex:
            _indent(lines, 5, f'<diffuse><texture texture="sampler_{index}" texcoord="UVMap"/></diffuse>')
        else:
            _indent(lines, 5, '<diffuse><color>1 1 1 1</color></diffuse>')
        _indent(lines, 5, '<specular><color>0 0 0 1</color></specular>')
        _indent(lines, 5, '<shininess><float>1</float></shininess>')
        _indent(lines, 4, '</phong></technique>')
        _indent(lines, 3, '</profile_COMMON>')
        _indent(lines, 2, '</effect>')
    _indent(lines, 1, '</library_effects>')
    _indent(lines, 1, '<library_materials>')
    for index, name in enumerate(material_names):
        _indent(lines, 2, f'<material id="material_{index}" name="{_e(name)}"><instance_effect url="#effect_{index}"/></material>')
    _indent(lines, 1, '</library_materials>')

def _write_controller(lines, controller_id, geom_id, bones, joints, weights):
    joint_names = [_sid(bone.get('name') or f'bone_{i:03d}', f'bone_{i:03d}') for i, bone in enumerate(bones)]
    bind_values = []
    for bone in bones:
        bind_values.extend(_inverse_bind_matrix(bone))
    weight_values = []
    vcount = []
    v = []
    for joint_set, weight_set in zip(joints, weights):
        pairs = []
        for joint_index, weight in zip(joint_set, weight_set):
            weight = max(0.0, float(weight))
            if weight > 0.000001 and 0 <= int(joint_index) < len(bones):
                pairs.append((int(joint_index), weight))
        if not pairs:
            pairs = [(0, 1.0)]
        total = sum(weight for _, weight in pairs)
        pairs = [(j, weight / total if total > 0 else 1.0) for j, weight in pairs]
        vcount.append(len(pairs))
        for joint_index, weight in pairs:
            weight_values.append(weight)
            v.extend([joint_index, len(weight_values) - 1])
    _indent(lines, 1, '<library_controllers>')
    _indent(lines, 2, f'<controller id="{controller_id}">')
    _indent(lines, 3, f'<skin source="#{geom_id}">')
    _indent(lines, 4, '<bind_shape_matrix>1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1</bind_shape_matrix>')
    _indent(lines, 4, f'<source id="{controller_id}-joints"><Name_array id="{controller_id}-joints-array" count="{len(joint_names)}">{_e(" ".join(joint_names))}</Name_array><technique_common><accessor source="#{controller_id}-joints-array" count="{len(joint_names)}" stride="1"><param name="JOINT" type="Name"/></accessor></technique_common></source>')
    _indent(lines, 4, f'<source id="{controller_id}-bindposes"><float_array id="{controller_id}-bindposes-array" count="{len(bind_values)}">{_join_floats(bind_values)}</float_array><technique_common><accessor source="#{controller_id}-bindposes-array" count="{len(bones)}" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common></source>')
    _indent(lines, 4, f'<source id="{controller_id}-weights"><float_array id="{controller_id}-weights-array" count="{len(weight_values)}">{_join_floats(weight_values)}</float_array><technique_common><accessor source="#{controller_id}-weights-array" count="{len(weight_values)}" stride="1"><param name="WEIGHT" type="float"/></accessor></technique_common></source>')
    _indent(lines, 4, f'<joints><input semantic="JOINT" source="#{controller_id}-joints"/><input semantic="INV_BIND_MATRIX" source="#{controller_id}-bindposes"/></joints>')
    _indent(lines, 4, f'<vertex_weights count="{len(joints)}"><input semantic="JOINT" source="#{controller_id}-joints" offset="0"/><input semantic="WEIGHT" source="#{controller_id}-weights" offset="1"/><vcount>{_join_ints(vcount)}</vcount><v>{_join_ints(v)}</v></vertex_weights>')
    _indent(lines, 3, '</skin>')
    _indent(lines, 2, '</controller>')
    _indent(lines, 1, '</library_controllers>')

def _bone_children(bones):
    children = {i: [] for i in range(len(bones))}
    roots = []
    for index, bone in enumerate(bones):
        parent = int(bone.get('parent_index', -1)) if str(bone.get('parent_index', -1)).lstrip('-').isdigit() else -1
        if parent >= 0 and parent < len(bones) and parent != index:
            children[parent].append(index)
        else:
            roots.append(index)
    if not roots and bones:
        roots = [0]
    return roots, children

def _write_bone_node(lines, level, bones, children, index):
    bone = bones[index]
    sid = _sid(bone.get('name') or f'bone_{index:03d}', f'bone_{index:03d}')
    _indent(lines, level, f'<node id="{sid}" sid="{sid}" name="{_e(bone.get("name") or sid)}" type="JOINT">')
    _indent(lines, level + 1, f'<matrix>{_join_floats(_bone_matrix(bone))}</matrix>')
    for child in children.get(index, []):
        _write_bone_node(lines, level + 1, bones, children, child)
    _indent(lines, level, '</node>')

def _write_scene(lines, entry_name, geom_id, controller_id, material_symbols, bones, skinned):
    _indent(lines, 1, '<library_visual_scenes>')
    _indent(lines, 2, '<visual_scene id="Scene" name="Scene">')
    roots, children = _bone_children(bones)
    if skinned:
        for root in roots:
            _write_bone_node(lines, 3, bones, children, root)
        _indent(lines, 3, f'<node id="{_sid(entry_name)}_mesh" name="{_e(entry_name)}">')
        _indent(lines, 4, f'<instance_controller url="#{controller_id}">')
        if roots:
            root_sid = _sid(bones[roots[0]].get('name') or f'bone_{roots[0]:03d}', f'bone_{roots[0]:03d}')
            _indent(lines, 5, f'<skeleton>#{root_sid}</skeleton>')
        _write_bind_material(lines, 5, material_symbols)
        _indent(lines, 4, '</instance_controller>')
        _indent(lines, 3, '</node>')
    else:
        _indent(lines, 3, f'<node id="{_sid(entry_name)}_mesh" name="{_e(entry_name)}"><instance_geometry url="#{geom_id}">')
        _write_bind_material(lines, 4, material_symbols)
        _indent(lines, 3, '</instance_geometry></node>')
    _indent(lines, 2, '</visual_scene>')
    _indent(lines, 1, '</library_visual_scenes>')
    _indent(lines, 1, '<scene><instance_visual_scene url="#Scene"/></scene>')

def _write_bind_material(lines, level, material_symbols):
    _indent(lines, level, '<bind_material><technique_common>')
    for index, symbol in enumerate(material_symbols):
        _indent(lines, level + 1, f'<instance_material symbol="{symbol}" target="#material_{index}"><bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/></instance_material>')
    _indent(lines, level, '</technique_common></bind_material>')

def export_model_dae(parsed, entry, out_path, require_store=None, skeleton_refs=None, texture_map=None, texture_root=None, include_skin=True):
    asset = get_entry_asset(parsed, entry)
    model = load_model_with_skin(asset)
    entry_name = safe_name(entry.get('display_name') or entry.get('name') or entry['uuid_hex'])
    material_names = _material_names(model, entry)
    model['materials'] = material_names
    skeleton = _load_skeleton(parsed, require_store, skeleton_refs or []) if include_skin else {'bones': [], 'summary': {}, 'source_uuid': '', 'source_kind': '', 'source_path': ''}
    bones = skeleton.get('bones') or []
    skinned = include_skin and bool(bones)
    positions, normals, uvs, joints, weights, primitives, face_count = _merge_arrays(model, len(bones) if bones else 1)
    geom_id = _sid(entry_name + '_geometry')
    controller_id = _sid(entry_name + '_controller')
    material_symbols = [f'material_{i}' for i in range(len(material_names))]
    lines = []
    _indent(lines, 0, '<?xml version="1.0" encoding="utf-8"?>')
    _indent(lines, 0, '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">')
    _indent(lines, 1, '<asset><contributor><authoring_tool>PAKPY DAE exporter</authoring_tool></contributor><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>')
    _write_materials(lines, material_names, texture_map or {}, texture_root, out_path)
    _write_geometry(lines, geom_id, entry_name, positions, normals, uvs, primitives, material_symbols)
    if skinned:
        _write_controller(lines, controller_id, geom_id, bones, joints, weights)
    _write_scene(lines, entry_name, geom_id, controller_id, material_symbols, bones, skinned)
    _indent(lines, 0, '</COLLADA>')
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return {'dae_path': str(out_path), 'vertex_count': len(positions), 'face_count': face_count, 'material_count': len(material_names), 'bone_count': len(bones) if skinned else 0, 'skinned': skinned, 'skeleton': skeleton.get('summary', {}), 'skeleton_uuid_hex': skeleton.get('source_uuid', ''), 'skeleton_source_kind': skeleton.get('source_kind', ''), 'skeleton_source_path': skeleton.get('source_path', '')}

def write_model_debug_json(parsed, entry, out_path, require_store=None, skeleton_refs=None):
    asset = get_entry_asset(parsed, entry)
    model = load_model_with_skin(asset)
    skeleton = _load_skeleton(parsed, require_store, skeleton_refs or [])
    data = {
        'entry_index': entry.get('index'),
        'entry_type': entry.get('type'),
        'entry_uuid_hex': entry.get('uuid_hex'),
        'entry_name': entry.get('display_name') or entry.get('name') or entry.get('uuid_hex'),
        'mesh_count': len(model.get('meshes', [])),
        'material_count': len(model.get('materials', [])),
        'bone_count_from_model': model.get('bone_count', 0),
        'vertex_buffers': {str(k): {'reported_vertex_count': v.get('reported_vertex_count'), 'actual_vertex_count': v.get('actual_vertex_count'), 'truncated': v.get('truncated')} for k, v in model.get('vertex_sets', {}).items()},
        'meshes': model.get('meshes', []),
        'materials': _material_names(model, entry),
        'skeleton_uuid_hex': skeleton.get('source_uuid', ''),
        'skeleton_source_kind': skeleton.get('source_kind', ''),
        'skeleton_source_path': skeleton.get('source_path', ''),
        'skeleton': skeleton.get('summary', {})
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    return str(out_path)
