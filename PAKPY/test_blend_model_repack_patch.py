import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

import blend_model_repack_patch as patch
import pak_extract
import rigged_gltf


def chunk(tag, payload, version=0):
    return tag.encode('ascii') + len(payload).to_bytes(8, 'big') + int(version).to_bytes(4, 'big') + b'\x00' * 8 + payload


def model_asset(parts):
    body = b''.join(parts)
    root = bytearray(32)
    root[0:4] = b'RFRM'
    root[4:12] = len(body).to_bytes(8, 'big')
    root[20:24] = b'SMDL'
    root[24:28] = (58).to_bytes(4, 'big')
    root[28:32] = (60).to_bytes(4, 'big')
    return bytes(root) + body


def skinned_descriptor(vertex_count):
    components = [
        {'field_0': 0, 'offset': 0, 'stride': 44, 'format': 37, 'type': 0},
        {'field_0': 0, 'offset': 12, 'stride': 44, 'format': 34, 'type': 1},
        {'field_0': 0, 'offset': 20, 'stride': 44, 'format': 34, 'type': 2},
        {'field_0': 0, 'offset': 28, 'stride': 44, 'format': 20, 'type': 4},
        {'field_0': 0, 'offset': 32, 'stride': 44, 'format': 22, 'type': 9},
        {'field_0': 0, 'offset': 36, 'stride': 44, 'format': 34, 'type': 10},
    ]
    return {'vertex_count': vertex_count, 'component_count': len(components), 'components': components, 'stride': 44}


def vertices(positions):
    return [
        {
            'position': position,
            'normal': [0.0, 0.0, 1.0],
            'tangent': [1.0, 0.0, 0.0, 1.0],
            'uv': [float(index % 2), float((index // 2) % 2)],
            'joints': [0, 0, 0, 0],
            'weights': [1.0, 0.0, 0.0, 0.0],
        }
        for index, position in enumerate(positions)
    ]


def source_asset():
    descriptor = skinned_descriptor(3)
    raw_vertices = patch._encode_vertex_buffer(descriptor, vertices([[0, 0, 0], [1, 0, 0], [0, 1, 0]]), bytes(44))
    raw_indices = struct.pack('<3H', 0, 1, 2)
    head = bytearray(96)
    head[0:20] = b''.join(value.to_bytes(4, 'big') for value in [1, 0, 0, 0, 0])
    head[20:32] = struct.pack('>3f', 0.0, 0.0, 0.0)
    head[32:44] = struct.pack('>3f', 1.0, 1.0, 0.0)
    mesh = {
        'mesh_index': 0,
        'primitive_mode': 3,
        'material_index': 0,
        'vertex_buffer_index': 0,
        'index_buffer_index': 0,
        'index_buffer_offset': 0,
        'index_count': 3,
        'field_10': 65535,
        'field_12': 0,
        'field_13': 0,
        'flags': 3,
    }
    gpu = (0x0D000000).to_bytes(4, 'big') + zlib.compress(raw_vertices, 9)
    gpu += (0x0D000000).to_bytes(4, 'big') + zlib.compress(raw_indices, 9)
    return model_asset([
        chunk('SKHD', (1).to_bytes(4, 'big')),
        chunk('HEAD', bytes(head)),
        chunk('MESH', patch._serialize_meshes([mesh])),
        chunk('VBUF', patch._serialize_vbufs([descriptor])),
        chunk('IBUF', patch._serialize_ibufs([{'index_type': 1}])),
        chunk('GPU ', gpu),
    ])


class BlendModelRepackTests(unittest.TestCase):
    def test_rebuild_accepts_arbitrary_vertex_and_triangle_counts(self):
        positions = [[0, 0, 0], [2, 0, 0], [2, 2, 0], [0, 2, 0], [1, 1, 1]]
        attrs = vertices(positions)
        replacement = [{
            'mesh_index': 0,
            'positions': positions,
            'normals': [item['normal'] for item in attrs],
            'tangents': [item['tangent'] for item in attrs],
            'uvs': [item['uv'] for item in attrs],
            'joints': [item['joints'] for item in attrs],
            'weights': [item['weights'] for item in attrs],
            'indices': [0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4],
        }]
        rebuilt, summary = patch._build_model_asset(source_asset(), replacement)
        parsed = rigged_gltf.load_model_with_skin(rebuilt)
        self.assertEqual(summary['vertex_count'], 5)
        self.assertEqual(summary['face_count'], 4)
        self.assertEqual(len(parsed['vertex_sets'][0]['positions']), 5)
        self.assertEqual(parsed['meshes'][0]['index_count'], 12)
        self.assertEqual(len(parsed['index_sets'][0]), 12)
        self.assertEqual(parsed['bone_count'], 1)
        chunks = pak_extract.parse_chunks(rebuilt)
        blocks = pak_extract.decompress_gpu_blocks(chunks['GPU '])
        self.assertEqual([block['tag'] for block in blocks], [0x0D000000, 0x0D000000])

    def test_extracts_named_source_part_and_remaps_joint_by_name(self):
        binary = bytearray()
        views = []
        accessors = []

        def add(values, fmt, component_type, type_name, target=None):
            while len(binary) % 4:
                binary.append(0)
            offset = len(binary)
            binary.extend(struct.pack('<' + fmt * len(values), *values))
            component_size = struct.calcsize('<' + fmt)
            count = len(values) // {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[type_name]
            view = {'buffer': 0, 'byteOffset': offset, 'byteLength': len(values) * component_size}
            if target is not None:
                view['target'] = target
            views.append(view)
            accessors.append({'bufferView': len(views) - 1, 'byteOffset': 0, 'componentType': component_type, 'count': count, 'type': type_name})
            return len(accessors) - 1

        position = add([0, 0, 0, 1, 0, 0, 0, 1, 0], 'f', 5126, 'VEC3', 34962)
        normal = add([0, 0, 1] * 3, 'f', 5126, 'VEC3', 34962)
        uv = add([0, 0, 1, 0, 0, 1], 'f', 5126, 'VEC2', 34962)
        joints = add([0, 0, 0, 0] * 3, 'H', 5123, 'VEC4', 34962)
        weights = add([1, 0, 0, 0] * 3, 'f', 5126, 'VEC4', 34962)
        indices = add([0, 1, 2], 'H', 5123, 'SCALAR', 34963)
        gltf = {
            'nodes': [
                {'name': 'root_skin'},
                {'name': 'Unit__mesh_000__Body', 'mesh': 0, 'skin': 0, 'translation': [2, 0, 0], 'extras': {'pakpy_source_mesh_index': 0}},
            ],
            'meshes': [{'primitives': [{'attributes': {'POSITION': position, 'NORMAL': normal, 'TEXCOORD_0': uv, 'JOINTS_0': joints, 'WEIGHTS_0': weights}, 'indices': indices, 'mode': 4}]}],
            'skins': [{'joints': [0]}],
            'bufferViews': views,
            'accessors': accessors,
        }
        parts = patch._extract_parts_from_glb(gltf, bytes(binary), {'source_mesh_objects': []}, [{'name': 'root_skin'}], 1)
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0]['positions'][0], [2.0, 0.0, 0.0])
        self.assertEqual(parts[0]['joints'][0], [0, 0, 0, 0])
        self.assertEqual(parts[0]['indices'], [0, 1, 2])

    def test_char_package_root_discovers_nested_model_packages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            package_a = root / 'models' / 'a_smdl_package'
            package_b = root / 'models' / 'b_smdl_package'
            package_a.mkdir(parents=True)
            package_b.mkdir(parents=True)
            (package_a / 'repack_manifest.json').write_text('{}', encoding='utf-8')
            (package_b / 'repack_manifest.json').write_text('{}', encoding='utf-8')
            (root / 'manifest.json').write_text(json.dumps({'models': [{'model_package_dir': 'models/a_smdl_package'}, {'model_package_dir': 'models/b_smdl_package'}]}), encoding='utf-8')
            self.assertEqual(patch._model_package_dirs(root), [package_a, package_b])

    def test_blender_script_requires_unchanged_rest_pose(self):
        script = patch._blender_export_script(Path('out.glb'))
        self.assertIn('Rest-Pose wurde verändert', script)
        self.assertIn('Bone-Hierarchie wurde verändert', script)
        self.assertIn("armature.data.pose_position='REST'", script)


if __name__ == '__main__':
    unittest.main()
