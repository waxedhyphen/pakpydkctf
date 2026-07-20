import unittest
from unittest import mock

import blend_model_repack_patch
import model_package


class DirectGeometryRebuildIntegrationTests(unittest.TestCase):
    def test_public_rebuild_function_always_delegates_to_blend_rebuilder(self):
        expected = {
            'out_path': 'rebuilt.pak',
            'changed_count': 4,
            'changed_files': ['model.blend', 'a.png', 'b.png', 'c.png'],
            'texture_changed_count': 3,
            'geometry_changed_count': 1,
            'model_package_count': 1,
            'geometry_summaries': [],
        }
        with mock.patch.object(blend_model_repack_patch, 'install') as install_mock:
            with mock.patch.object(
                blend_model_repack_patch,
                'rebuild_from_blend_package',
                return_value=dict(expected),
            ) as rebuild_mock:
                result = model_package._direct_rebuild_model_package_from_folder(
                    {'path': 'source.pak'}, 'character_package', 'rebuilt.pak'
                )
        install_mock.assert_called_once_with()
        rebuild_mock.assert_called_once_with(
            {'path': 'source.pak'}, 'character_package', 'rebuilt.pak'
        )
        self.assertEqual(result['geometry_changed_count'], 1)
        self.assertEqual(result['texture_changed_count'], 3)
        self.assertEqual(int(result['changed_count']), 4)
        self.assertIn('Geänderte Modellressourcen: 1', str(result['changed_count']))
        self.assertIs(
            model_package.rebuild_model_package_from_folder,
            model_package._direct_rebuild_model_package_from_folder,
        )

    def test_legacy_gui_count_exposes_all_rebuild_categories(self):
        value = model_package._LegacyRebuildCount(3, 1, 2)
        self.assertEqual(int(value), 4)
        self.assertEqual(
            str(value),
            '3\nGeänderte Modellressourcen: 1\nModellpakete geprüft: 2',
        )


if __name__ == '__main__':
    unittest.main()
