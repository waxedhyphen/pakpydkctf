import json
import struct
import tempfile
import unittest
from pathlib import Path

import mesh_partition_export_patch as patch


def read_glb_json(path):
    data = Path(path).read_bytes()
    magic, version, total = struct.unpack_from('<III', data, 0)
    assert magic == 0x46546C67 and version == 2 and total == len(data)
    size, kind = struct.unpack_from('<I4s', data, 12)
    assert kind == b'JSON'
    return json.loads(data[20:20 + size].decode('utf-8'))


class MeshPartitionExportTests(unittest.TestCase):
    def test_each_source_mesh_becomes_a_named_gltf_mesh_node(self):
        model = {
            'materials': ['Body Mat', 'Cannon Mat'],
            'vertex_sets': {
                0: {
                    'positions': [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                    'normals': [[0, 0, 1]] * 4,
                    'uvs': [[0, 0], [1, 0], [1, 1], [0, 1]],
                    'joints': [[0, 0, 0, 0]] * 4,
                    'weights': [[1, 0, 0, 0]] * 4,
                },
                1: {
                    'positions': [[0, 0, 1], [1, 0, 1], [0, 1, 1]],
                    'normals': [[0, 0, 1]] * 3,
                    'uvs': [[0, 0], [1, 0], [0, 1]],
                    'joints': [[1, 0, 0, 0]] * 3,
                    'weights': [[1, 0, 0, 0]] * 3,
                },
            },
            'index_sets': {0: [0, 1, 2, 0, 2, 3], 1: [0, 1, 2]},
            'meshes': [
                {'mesh_index': 0, 'primitive_mode': 3, 'material_index': 0, 'vertex_buffer_index': 0, 'index_buffer_index': 0, 'index_buffer_offset': 0, 'index_count': 6, 'field_10': 10, 'field_12': 12, 'field_13': 13, 'flags': 7},
                {'mesh_index': 1, 'primitive_mode': 3, 'material_index': 1, 'vertex_buffer_index': 1, 'index_buffer_index': 1, 'index_buffer_offset': 0, 'index_count': 3, 'field_10': 0, 'field_12': 0, 'field_13': 0, 'flags': 1},
            ],
        }
        bones = [
            {'index': 0, 'node_index': 0, 'name': 'root_skin', 'parent_index': -1, 'head': [0, 0, 0], 'tail': [0, 0.035, 0]},
            {'index': 1, 'node_index': 2, 'name': 'cannon_skin', 'parent_index': 0, 'head': [0, 0, 1], 'tail': [0, 0.035, 1]},
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'partitioned.glb'
            result = patch._write_partitioned_glb(path, model, bones, 'UnitModel', include_skin=True)
            gltf = read_glb_json(path)
        self.assertEqual(result['mesh_count'], 2)
        self.assertEqual(len(gltf['meshes']), 2)
        mesh_nodes = [node for node in gltf['nodes'] if 'mesh' in node]
        self.assertEqual(len(mesh_nodes), 2)
        self.assertEqual(mesh_nodes[0]['name'], 'UnitModel__mesh_000__Body_Mat')
        self.assertEqual(mesh_nodes[1]['name'], 'UnitModel__mesh_001__Cannon_Mat__cannon_skin')
        self.assertEqual(mesh_nodes[1]['extras']['pakpy_source_mesh_index'], 1)
        self.assertEqual(mesh_nodes[1]['extras']['pakpy_vertex_buffer_index'], 1)
        primitive = gltf['meshes'][1]['primitives'][0]
        self.assertIn('_PAKPY_SOURCE_VERTEX_INDEX', primitive['attributes'])
        self.assertEqual(gltf['skins'][0]['joints'], [0, 1])

    def test_non_skin_skel_nodes_are_preserved_as_helpers(self):
        model = {
            'materials': ['Body'],
            'vertex_sets': {0: {'positions': [[0, 0, 0], [1, 0, 0], [0, 1, 0]], 'normals': [[0, 0, 1]] * 3, 'uvs': [[0, 0], [1, 0], [0, 1]], 'joints': [[0, 0, 0, 0]] * 3, 'weights': [[1, 0, 0, 0]] * 3}},
            'index_sets': {0: [0, 1, 2]},
            'meshes': [{'mesh_index': 0, 'primitive_mode': 3, 'material_index': 0, 'vertex_buffer_index': 0, 'index_buffer_index': 0, 'index_buffer_offset': 0, 'index_count': 3, 'field_10': 0, 'field_12': 0, 'field_13': 0, 'flags': 0}],
        }
        bones = [{'index': 0, 'node_index': 0, 'name': 'root_skin', 'parent_index': -1, 'head': [0, 0, 0], 'tail': [0, 0.035, 0]}]
        skeleton = {
            'bones': bones,
            'raw_skel_summary': {
                'nodes': [
                    {'index': 0, 'name_index': 0, 'name': 'root_skin', 'parent_index': 255, 'flags': 0, 'matrix': [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]},
                    {'index': 1, 'name_index': 1, 'name': 'projectile_attach_skin', 'parent_index': 0, 'flags': 4, 'matrix': [1, 0, 0, 0.5, 0, 1, 0, 1.0, 0, 0, 1, 1.5, 0, 0, 0, 1]},
                ]
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'helper.glb'
            patch._write_partitioned_glb(path, model, bones, 'UnitModel', include_skin=True)
            helpers = patch._patch_skel_helper_nodes(path, skeleton)
            gltf = read_glb_json(path)
        self.assertEqual(len(helpers), 1)
        helper = next(node for node in gltf['nodes'] if node.get('name') == 'projectile_attach_skin')
        self.assertTrue(helper['extras']['pakpy_non_deform_helper'])
        self.assertEqual(helper['extras']['pakpy_skel_parent_name'], 'root_skin')
        self.assertIn(gltf['nodes'].index(helper), gltf['nodes'][0]['children'])


if __name__ == '__main__':
    unittest.main()
