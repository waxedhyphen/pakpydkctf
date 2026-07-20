import unittest
from pathlib import Path

import pak_core
import mesh_repack_diagnostics_patch as patch


class MeshRepackDiagnosticsTests(unittest.TestCase):
    def test_export_script_adds_stable_index_name_and_mesh_property(self):
        def original(_output):
            return "mesh_parts=[]\narmature.data.pose_position='REST'\n"

        text = patch._wrap_export_script(original)(Path('out.glb'))
        self.assertIn("__PAKPY_REPACK__mesh_%03d__%s", text)
        self.assertIn("obj.data['pakpy_source_mesh_index']=source_index", text)
        self.assertLess(
            text.index("__PAKPY_REPACK__mesh_%03d__%s"),
            text.index("armature.data.pose_position='REST'"),
        )

    def test_mesh_level_property_is_copied_to_node(self):
        gltf = {
            'nodes': [{'name': 'bake', 'mesh': 0}],
            'meshes': [{'extras': {'pakpy_source_mesh_index': 1}}],
        }
        prepared = patch._prepare_gltf(gltf)
        self.assertEqual(prepared['nodes'][0]['extras']['pakpy_source_mesh_index'], 1)
        records = patch._mesh_node_records(prepared, {})
        self.assertEqual(records[0]['source_index'], 1)

    def test_error_explains_which_specific_part_is_missing(self):
        gltf = {
            'nodes': [
                {'name': '__PAKPY_REPACK__mesh_000__body', 'mesh': 0},
                {'name': 'bake', 'mesh': 1},
            ],
            'meshes': [{}, {}],
        }
        manifest = {
            'source_mesh_objects': [
                {'name': 'old_body', 'pakpy_source_mesh_index': 0},
                {'name': 'old_hat', 'pakpy_source_mesh_index': 1},
            ]
        }
        message = patch._mapping_error_message(gltf, manifest, 2)
        self.assertIn('Originalmodell enthält 2 MESH-Part(s)', message)
        self.assertIn('Fehlende Quellindizes (1): [1]', message)
        self.assertIn('Quellindex 1: "old_hat"', message)
        self.assertIn('Objekt "bake"', message)
        self.assertIn('NICHT ZUGEORDNET', message)
        self.assertIn("nicht 'einen Fehler pro Objekt'", message)

    def test_duplicate_error_lists_every_object_name(self):
        def original(*_args):
            raise AssertionError('must not reach original extractor')

        wrapped = patch._wrap_extract(original)
        gltf = {
            'nodes': [
                {'name': 'first', 'mesh': 0, 'extras': {'pakpy_source_mesh_index': 1}},
                {'name': 'second', 'mesh': 1, 'extras': {'pakpy_source_mesh_index': 1}},
            ],
            'meshes': [{}, {}],
        }
        with self.assertRaises(pak_core.PakError) as caught:
            wrapped(gltf, b'', {}, [], 2)
        text = str(caught.exception)
        self.assertIn('Quellindex 1 ist 2-mal vergeben', text)
        self.assertIn('"first"', text)
        self.assertIn('"second"', text)


if __name__ == '__main__':
    unittest.main()
