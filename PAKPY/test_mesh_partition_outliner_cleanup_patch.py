import sys
import types
import unittest

mesh_patch = types.ModuleType('mesh_partition_export_patch')
mesh_patch._patch_skel_helper_nodes = lambda path, skeleton: ['old']
mesh_patch._blend_script = lambda glb, blend, obj=None: "import bpy\nfrom pathlib import Path\nentry_name='Unit'\narmature_obj=None\nBLEND_PATH='x.blend'\n"
skeletal_patch = types.ModuleType('skeletal_tail_patch')
skeletal_patch._connected_blend_script = None
diagnostics_patch = types.ModuleType('mesh_repack_diagnostics_patch')
diagnostics_patch.install_calls = 0

def install_diagnostics():
    diagnostics_patch.install_calls += 1

diagnostics_patch.install = install_diagnostics
sys.modules['mesh_partition_export_patch'] = mesh_patch
sys.modules['skeletal_tail_patch'] = skeletal_patch
sys.modules['mesh_repack_diagnostics_patch'] = diagnostics_patch

import mesh_partition_outliner_cleanup_patch as patch


class OutlinerCleanupTests(unittest.TestCase):
    def test_install_disables_visible_helpers(self):
        before = diagnostics_patch.install_calls
        patch.install()
        self.assertEqual(mesh_patch._patch_skel_helper_nodes('x', {}), [])
        self.assertEqual(diagnostics_patch.install_calls, before + 1)

    def test_script_unparents_and_single_links_mesh_parts(self):
        text = patch._minimal_blend_script('x.glb', 'x.blend')
        self.assertIn('obj.parent=None', text)
        self.assertIn('collection.objects.unlink(obj)', text)
        self.assertIn('__MESH_PARTS', text)
        self.assertIn('__SKEL_HELPERS', text)
        self.assertIn('bpy.data.objects.remove(obj,do_unlink=True)', text)
        self.assertIn('edit_bones.remove(bone)', text)


if __name__ == '__main__':
    unittest.main()
