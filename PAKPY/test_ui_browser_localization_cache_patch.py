import unittest
from types import SimpleNamespace

import ui_browser_localization as localization
import ui_browser_localization_cache_patch as patch


class LocalizationCachePatchTests(unittest.TestCase):
    def test_catalog_is_built_once_and_shared_between_movies(self):
        parsed = {'path': 'UIPak.pak', 'entries': [], 'data': b''}
        owner = SimpleNamespace(parsed=parsed, require_store=None, _current_movie=None)
        first = SimpleNamespace(
            ui_localization_enabled=True, ui_localization_language='EUEN',
            ui_localization_fallback='USEN', avm2_modules=(), definitions={},
            ui_native_callback_summaries=(),
        )
        second = SimpleNamespace(
            ui_localization_enabled=True, ui_localization_language='EUEN',
            ui_localization_fallback='USEN', avm2_modules=(), definitions={},
            ui_native_callback_summaries=(),
        )
        catalog = {
            'records': (), 'errors': (), 'documents': (), 'languages': (),
            'by_language': {}, 'by_bundle_language': {}, 'casefold_labels': {},
        }
        calls = []
        old = patch._BASE_ATTACH
        patch._BASE_ATTACH = lambda _owner, movie=None: (
            calls.append(movie), setattr(movie, 'ui_localization_catalog', catalog),
            setattr(movie, '_ui_localization_catalog_token', patch._catalog_token(_owner)), catalog,
        )[-1]
        try:
            self.assertIs(patch.attach_localization_catalog(owner, first), catalog)
            self.assertIs(patch.attach_localization_catalog(owner, second), catalog)
        finally:
            patch._BASE_ATTACH = old
        self.assertEqual(calls, [first])
        self.assertIs(first.ui_localization_catalog, second.ui_localization_catalog)


if __name__ == '__main__':
    unittest.main()
