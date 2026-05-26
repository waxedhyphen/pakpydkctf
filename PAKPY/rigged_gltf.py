from pathlib import Path
import json
import mimetypes
import struct
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes
from pak_extract import parse_chunks, parse_head, parse_meshes, parse_vbufs, parse_ibufs, parse_material_names, decompress_gpu_blocks, decode_gpu_block_data, parse_indices, build_faces, read_half
from skeletal_codec import parse_skel_asset, resolve_ref, ZERO_UUID

def _align4(data, pad=b'\x00'):
    while len(data) % 4:
        data += pad
    return data

def _pack_floats(values):
    return struct.pack('<' + 'f' * len(values), *values) if values else b''

def _pack_u32(values):
    return struct.pack('<' + 'I' * len(values), *values) if values else b''

def _pack_u16(values):
    return struct.pack('<' + 'H' * len(values), *values) if values else b''

def _read_vec4_half(data, off):
    return [read_half(data, off + i * 2) for i in range(4)]

def _read_u8x4(data, off):
    return [data[off], data[off + 1], data[off + 2], data[off + 3]]

def _normalise_weights(weights):
    total = sum(max(0.0, x) for x in weights)
    if total <= 0.000001:
        return [1.0, 0.0, 0.0, 0.0]
    return [max(0.0, x) / total for x in weights]

def _parse_vertices(vertex_buffer, raw_vertex_data):
    stride = vertex_buffer['stride']
    reported_vertex_count = vertex_buffer['vertex_count']
    if stride <= 0:
        raise PakError('Vertex-Stride ist ungültig')
    actual_vertex_count = min(reported_vertex_count, len(raw_vertex_data) // stride)
    if actual_vertex_count <= 0:
        raise PakError('Keine lesbaren Vertexdaten gefunden')
    positions = []
    normals = []
    uvs = []
    joints = []
    weights = []
    normal_semantics = {1}
    tangent_semantics = {2, 3, 12, 13}
    uv_semantics = {4, 5, 6, 7, 8}
    for index in range(actual_vertex_count):
        base = index * stride
        position = [0.0, 0.0, 0.0]
        normal = [0.0, 0.0, 1.0]
        uv = [0.0, 0.0]
        joint = [0, 0, 0, 0]
        weight = [1.0, 0.0, 0.0, 0.0]
        for component in vertex_buffer['components']:
            entry = base + component['offset']
            fmt = component['format']
            typ = component['type']
            if fmt == 37 and typ == 0 and entry + 12 <= len(raw_vertex_data):
                position = list(struct.unpack_from('<3f', raw_vertex_data, entry))
            elif fmt == 34 and entry + 8 <= len(raw_vertex_data):
                value = _read_vec4_half(raw_vertex_data, entry)
                if typ in normal_semantics:
                    normal = value[:3]
                elif typ == 10:
                    weight = _normalise_weights(value)
                elif typ in tangent_semantics and normal == [0.0, 0.0, 1.0]:
                    normal = value[:3]
            elif fmt in (20, 21) and typ in uv_semantics and entry + 4 <= len(raw_vertex_data):
                uv = [read_half(raw_vertex_data, entry), 1.0 - read_half(raw_vertex_data, entry + 2)]
            elif fmt == 22 and typ == 9 and entry + 4 <= len(raw_vertex_data):
                joint = _read_u8x4(raw_vertex_data, entry)
        positions.append(position)
        normals.append(normal)
        uvs.append(uv)
        joints.append(joint)
        weights.append(weight)
    return {'positions': positions, 'normals': normals, 'uvs': uvs, 'joints': joints, 'weights': weights, 'reported_vertex_count': reported_vertex_count, 'actual_vertex_count': actual_vertex_count, 'truncated': actual_vertex_count < reported_vertex_count}

def load_model_with_skin(data):
    chunks = parse_chunks(data)
    head = parse_head(chunks['HEAD'])
    meshes = parse_meshes(chunks['MESH'])
    vbufs = parse_vbufs(chunks['VBUF'])
    ibufs = parse_ibufs(chunks['IBUF'])
    materials = parse_material_names(chunks.get('MTRL', b''), max(1, len(meshes)))
    bone_count = 0
    if 'SKHD' in chunks and len(chunks['SKHD']) >= 4:
        bone_count = int.from_bytes(chunks['SKHD'][:4], 'big')
    gpu_blocks = decompress_gpu_blocks(chunks['GPU '])
    if not gpu_blocks:
        raise PakError('GPU-Block konnte nicht gelesen werden')
    used_vbuf_indices = sorted({mesh['vertex_buffer_index'] for mesh in meshes})
    used_ibuf_indices = sorted({mesh['index_buffer_index'] for mesh in meshes})
    if used_vbuf_indices and max(used_vbuf_indices) >= len(gpu_blocks):
        raise PakError('Es fehlen GPU-Blöcke für Vertexdaten')
    index_block_start = len(vbufs)
    if used_ibuf_indices and index_block_start + max(used_ibuf_indices) >= len(gpu_blocks):
        raise PakError('Es fehlen GPU-Blöcke für Indexdaten')
    for i in used_vbuf_indices:
        block = gpu_blocks[i]
        expected = vbufs[i]['vertex_count'] * vbufs[i]['stride']
        if not block.get('handled'):
            block['data'] = decode_gpu_block_data(block['tag'], block['payload'], expected)
            block['handled'] = True
        if len(block['data']) < expected:
            raise PakError(f'Vertex-Block {i} ist zu kurz | erwartet {expected} Bytes | gefunden {len(block["data"])} Bytes')
    for i in used_ibuf_indices:
        block = gpu_blocks[index_block_start + i]
        if not block.get('handled'):
            bytes_per_index = 2 if ibufs[i]['index_type'] in (0, 1) else 4 if ibufs[i]['index_type'] == 2 else 0
            if bytes_per_index <= 0:
                raise PakError(f'Nicht unterstützter Indextyp: {ibufs[i]["index_type"]}')
            expected = 0
            for mesh in meshes:
                if mesh['index_buffer_index'] == i:
                    expected = max(expected, mesh['index_buffer_offset'] + mesh['index_count'])
            block['data'] = decode_gpu_block_data(block['tag'], block['payload'], expected * bytes_per_index)
            block['handled'] = True
    vertex_sets = {i: _parse_vertices(vbufs[i], gpu_blocks[i]['data']) for i in used_vbuf_indices}
    index_sets = {i: parse_indices(ibufs[i], gpu_blocks[index_block_start + i]['data']) for i in used_ibuf_indices}
    return {'file_type': data[0x14:0x18].decode('ascii'), 'head': head, 'materials': materials, 'meshes': meshes, 'vertex_sets': vertex_sets, 'index_sets': index_sets, 'bone_count': bone_count}

def _fallback_bones(count):
    if count <= 0:
        count = 1
    bones = []
    for index in range(count):
        bones.append({'index': index, 'name': f'bone_{index:03d}', 'parent_index': -1 if index == 0 else 0, 'head': [0.0, 0.0, 0.0], 'tail': [0.0, 0.0, 0.035]})
    return bones

def _load_skeleton(parsed, model, require_store, skeleton_refs):
    for ref in skeleton_refs or []:
        uuid_hex = ref.get('uuid_hex', '')
        asset, entry, source, source_path = resolve_ref(parsed, uuid_hex, require_store)
        if entry is None or asset is None or entry.get('type') != 'SKEL':
            continue
        try:
            skel = parse_skel_asset(asset)
            bones = skel.get('bones') or []
            if bones:
                count = model.get('bone_count') or len(bones)
                return {'source_uuid': uuid_hex, 'source_kind': source, 'source_path': source_path, 'summary': skel, 'bones': bones[:count]}
        except Exception:
            continue
    return {'source_uuid': '', 'source_kind': '', 'source_path': '', 'summary': {}, 'bones': _fallback_bones(model.get('bone_count', 0))}

def _mesh_arrays(model, bone_count):
    positions = []
    normals = []
    uvs = []
    joints = []
    weights = []
    vertex_base = {}
    for vbuf_index in sorted(model['vertex_sets']):
        vertex_set = model['vertex_sets'][vbuf_index]
        vertex_base[vbuf_index] = len(positions)
        positions.extend(vertex_set['positions'])
        normals.extend(vertex_set['normals'])
        uvs.extend(vertex_set['uvs'])
        for joint in vertex_set['joints']:
            joints.append([min(max(0, int(x)), max(0, bone_count - 1)) for x in joint])
        weights.extend(vertex_set['weights'])
    primitives = []
    face_count = 0
    for mesh in model['meshes']:
        vbuf_index = mesh['vertex_buffer_index']
        if vbuf_index not in model['vertex_sets'] or mesh['index_buffer_index'] not in model['index_sets']:
            continue
        vertex_limit = len(model['vertex_sets'][vbuf_index]['positions'])
        indices = model['index_sets'][mesh['index_buffer_index']]
        mesh_indices = indices[mesh['index_buffer_offset']:mesh['index_buffer_offset'] + mesh['index_count']]
        faces = build_faces(mesh['primitive_mode'], mesh_indices, vertex_limit=vertex_limit)
        out_indices = []
        base = vertex_base[vbuf_index]
        for a, b, c in faces:
            out_indices.extend([a + base, b + base, c + base])
        if out_indices:
            primitives.append({'name': f'mesh_{mesh["mesh_index"]}', 'indices': out_indices, 'material_index': mesh['material_index']})
            face_count += len(faces)
    if face_count <= 0:
        raise PakError('GLB-Export erzeugte 0 Faces')
    return positions, normals, uvs, joints, weights, primitives, face_count

def _inverse_translation_matrix(t):
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, -float(t[0]), -float(t[1]), -float(t[2]), 1.0]

def _global_bind_positions(bones):
    out = []
    for index, bone in enumerate(bones):
        head = bone.get('head') or [0.0, 0.0, 0.0]
        parent = bone.get('parent_index', -1)
        if parent >= 0 and parent < len(out):
            p = out[parent]
            out.append([p[0] + head[0], p[1] + head[1], p[2] + head[2]])
        else:
            out.append(list(head))
    return out

def _normalise_bone_nodes(bones):
    globals_by_index = []
    for index, bone in enumerate(bones):
        head = bone.get('head') or [0.0, 0.0, 0.0]
        globals_by_index.append([float(head[0]), float(head[1]), float(head[2])])
    out = []
    for index, bone in enumerate(bones):
        parent = bone.get('parent_index', -1)
        if parent == index or parent < 0 or parent >= len(bones):
            parent = -1
        head_global = globals_by_index[index]
        if parent >= 0:
            parent_global = globals_by_index[parent]
            local = [head_global[0] - parent_global[0], head_global[1] - parent_global[1], head_global[2] - parent_global[2]]
        else:
            local = head_global
        tail = bone.get('tail') or [head_global[0], head_global[1], head_global[2] + 0.035]
        if head_global == tail:
            tail = [head_global[0], head_global[1], head_global[2] + 0.035]
        out.append({'index': index, 'name': bone.get('name') or f'bone_{index:03d}', 'parent_index': parent, 'head': local, 'tail': tail})
    return out

def _write_glb(path, model, bones, entry_name, texture_map=None, texture_root=None):
    bones = _normalise_bone_nodes(bones)
    positions, normals, uvs, joints, weights, primitives, face_count = _mesh_arrays(model, len(bones))
    texture_map = texture_map or {}
    texture_root = Path(texture_root) if texture_root else None
    bin_blob = bytearray()
    buffer_views = []
    accessors = []
    images = []
    textures = []
    def add_view(data, target=None):
        nonlocal bin_blob
        while len(bin_blob) % 4:
            bin_blob.append(0)
        off = len(bin_blob)
        bin_blob.extend(data)
        view = {'buffer': 0, 'byteOffset': off, 'byteLength': len(data)}
        if target is not None:
            view['target'] = target
        buffer_views.append(view)
        return len(buffer_views) - 1
    def add_accessor(data, component_type, count, typ, target=None, min_value=None, max_value=None):
        view = add_view(data, target=target)
        accessor = {'bufferView': view, 'byteOffset': 0, 'componentType': component_type, 'count': count, 'type': typ}
        if min_value is not None:
            accessor['min'] = min_value
        if max_value is not None:
            accessor['max'] = max_value
        accessors.append(accessor)
        return len(accessors) - 1
    def add_image(path_text):
        if not texture_root or not path_text:
            return None
        image_path = texture_root / path_text
        if not image_path.is_file():
            return None
        data = image_path.read_bytes()
        view = add_view(data)
        mime = mimetypes.guess_type(str(image_path))[0] or 'image/png'
        images.append({'bufferView': view, 'mimeType': mime, 'name': image_path.stem})
        textures.append({'source': len(images) - 1})
        return len(textures) - 1
    flat_pos = [x for item in positions for x in item]
    flat_normals = [x for item in normals for x in item]
    flat_uvs = [x for item in uvs for x in item]
    flat_joints = [x for item in joints for x in item]
    flat_weights = [x for item in weights for x in item]
    mins = [min(p[i] for p in positions) for i in range(3)]
    maxs = [max(p[i] for p in positions) for i in range(3)]
    pos_acc = add_accessor(_pack_floats(flat_pos), 5126, len(positions), 'VEC3', target=34962, min_value=mins, max_value=maxs)
    normal_acc = add_accessor(_pack_floats(flat_normals), 5126, len(normals), 'VEC3', target=34962)
    uv_acc = add_accessor(_pack_floats(flat_uvs), 5126, len(uvs), 'VEC2', target=34962)
    joint_acc = add_accessor(_pack_u16(flat_joints), 5123, len(joints), 'VEC4', target=34962)
    weight_acc = add_accessor(_pack_floats(flat_weights), 5126, len(weights), 'VEC4', target=34962)
    primitive_items = []
    for primitive in primitives:
        idx_acc = add_accessor(_pack_u32(primitive['indices']), 5125, len(primitive['indices']), 'SCALAR', target=34963)
        primitive_items.append({'attributes': {'POSITION': pos_acc, 'NORMAL': normal_acc, 'TEXCOORD_0': uv_acc, 'JOINTS_0': joint_acc, 'WEIGHTS_0': weight_acc}, 'indices': idx_acc, 'material': primitive['material_index'] if primitive['material_index'] < max(1, len(model['materials'])) else 0})
    global_positions = _global_bind_positions(bones)
    ibm = []
    for pos in global_positions:
        ibm.extend(_inverse_translation_matrix(pos))
    ibm_acc = add_accessor(_pack_floats(ibm), 5126, len(bones), 'MAT4')
    nodes = []
    for bone in bones:
        nodes.append({'name': bone['name'], 'translation': bone['head']})
    for index, bone in enumerate(bones):
        parent_index = bone.get('parent_index', -1)
        if parent_index >= 0 and parent_index < len(nodes) and parent_index != index:
            nodes[parent_index].setdefault('children', []).append(index)
    mesh_node_index = len(nodes)
    nodes.append({'name': entry_name, 'mesh': 0, 'skin': 0})
    root_joints = []
    for index, bone in enumerate(bones):
        parent_index = bone.get('parent_index', -1)
        if parent_index < 0 or parent_index >= len(bones) or parent_index == index:
            root_joints.append(index)
    scene_nodes = [mesh_node_index] + root_joints
    materials = []
    for index, name in enumerate(model['materials'] or ['material_0']):
        tex_path = ''
        info = texture_map.get(index) or texture_map.get(str(name)) or {}
        if isinstance(info, str):
            tex_path = info
        elif isinstance(info, dict):
            tex_path = info.get('map_Kd') or info.get('baseColorTexture') or ''
        tex_index = add_image(tex_path)
        mat = {'name': str(name), 'pbrMetallicRoughness': {'baseColorFactor': [1.0, 1.0, 1.0, 1.0], 'metallicFactor': 0.0, 'roughnessFactor': 1.0}}
        if tex_index is not None:
            mat['pbrMetallicRoughness']['baseColorTexture'] = {'index': tex_index}
        materials.append(mat)
    skin = {'name': entry_name + '_skin', 'joints': list(range(len(bones))), 'inverseBindMatrices': ibm_acc}
    if root_joints:
        skin['skeleton'] = root_joints[0]
    gltf = {'asset': {'version': '2.0', 'generator': 'PAKPY'}, 'scene': 0, 'scenes': [{'nodes': scene_nodes}], 'nodes': nodes, 'meshes': [{'name': entry_name, 'primitives': primitive_items}], 'skins': [skin], 'materials': materials, 'buffers': [{'byteLength': len(bin_blob)}], 'bufferViews': buffer_views, 'accessors': accessors}
    if images:
        gltf['images'] = images
        gltf['textures'] = textures
    json_blob = json.dumps(gltf, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    json_blob = _align4(json_blob, b' ')
    bin_data = _align4(bytes(bin_blob), b'\x00')
    total_len = 12 + 8 + len(json_blob) + 8 + len(bin_data)
    out = bytearray()
    out.extend(struct.pack('<III', 0x46546C67, 2, total_len))
    out.extend(struct.pack('<I4s', len(json_blob), b'JSON'))
    out.extend(json_blob)
    out.extend(struct.pack('<I4s', len(bin_data), b'BIN\x00'))
    out.extend(bin_data)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return {'glb_path': str(path), 'vertex_count': len(positions), 'face_count': face_count, 'bone_count': len(bones)}

def export_rigged_model_glb(parsed, entry, out_path, require_store=None, skeleton_refs=None, texture_map=None, texture_root=None):
    asset = get_entry_asset(parsed, entry)
    model = load_model_with_skin(asset)
    entry_name = safe_name(entry.get('display_name') or entry.get('name') or entry['uuid_hex'])
    skeleton = _load_skeleton(parsed, model, require_store, skeleton_refs or [])
    result = _write_glb(out_path, model, skeleton['bones'], entry_name, texture_map=texture_map, texture_root=texture_root)
    skeleton_json = {'entry_uuid_hex': entry['uuid_hex'], 'entry_name': entry_name, 'model_type': entry['type'], 'skhd_bone_count': model.get('bone_count', 0), 'skel_uuid_hex': skeleton.get('source_uuid', ''), 'skel_source_kind': skeleton.get('source_kind', ''), 'skel_source_path': skeleton.get('source_path', ''), 'bones': skeleton['bones'], 'raw_skel_summary': skeleton.get('summary', {})}
    result['skeleton'] = skeleton_json
    return result
