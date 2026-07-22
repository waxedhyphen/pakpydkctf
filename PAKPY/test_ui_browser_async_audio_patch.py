import unittest
from types import SimpleNamespace

import ui_browser_async_audio_patch as patch
import ui_browser_audio_preview as audio
import ui_browser_async_native as async_native
import ui_browser_native_callback_patch as native
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_avm2_lifecycle_patch as lifecycle


class Owner:
    def __init__(self, movie):
        self._current_movie = movie
        self.parsed = {'path': 'UIPak.pak', 'data': b'', 'entries': [], 'uuid_to_entry': {}}
        self.require_store = None
        self.renders = 0
    def request_render(self): self.renders += 1


def movie():
    value = SimpleNamespace(
        ui_avm2_runtime_generation=0,
        ui_avm2_runtime_revision=0,
        ui_avm2_runtime_log=[],
        ui_avm2_runtime_errors=[],
        ui_native_callback_mode='simulate',
        ui_native_callback_overrides={},
        ui_native_callback_sites=(),
        ui_native_callback_summaries=(),
        avm2_modules=(),
        ui_game_mock_enabled=False,
        ui_game_mock_roles=(),
        ui_game_mock_values={},
    )
    value.ui_avm2_lifecycle_state = {
        'modules': set(), 'classes': set(), 'instances': set(), 'objects': {},
        'listeners': {}, 'timers': {}, 'clock_ms': 0.0, 'next_token': 1,
        'constructors': 0, 'events': 0,
    }
    return value


class Context:
    def __init__(self, movie):
        self.movie = movie
        self.path = 'root/1:test'
        self.callbacks = 0


class AsyncAudioPatchTests(unittest.TestCase):
    def test_audio_config_is_bounded(self):
        self.assertEqual(audio.normalize_audio_preview_config({'volume': 5})['volume'], 1.0)
        self.assertEqual(audio.normalize_audio_preview_config({'volume': -1})['volume'], 0.0)

    def test_case_and_separator_insensitive_sound_resolution(self):
        value = movie()
        record = audio.UiSoundRecord('UI_Razz_Polite', 'uirazzpolite', 'UI', 'a', ('b',), {}, {})
        value.ui_audio_name_index = {'uirazzpolite': [record]}
        self.assertIs(audio.resolve_sound(value, 'ui-razz polite'), record)

    def test_completion_updates_data_and_dispatches_events(self):
        value = movie(); owner = Owner(value)
        delivered = []
        old = lifecycle._dispatch_key
        lifecycle._dispatch_key = lambda _movie, key, event: delivered.append((key, event.type, event.data)) or 1
        try:
            async_native.queue_completion(
                value, 'save', (), True, 'root', 10,
                ('SaveBusy', 'nativeComplete'),
                (('mRuntimeData', 'SaveBusy', False),),
            )
            value.ui_avm2_lifecycle_state['clock_ms'] = 9
            self.assertEqual(async_native.process_async_queue(owner), 0)
            value.ui_avm2_lifecycle_state['clock_ms'] = 10
            self.assertEqual(async_native.process_async_queue(owner), 1)
        finally:
            lifecycle._dispatch_key = old
        self.assertFalse(native._native_data(value)[('mRuntimeData', 'SaveBusy')])
        self.assertIn(('global', 'Controller.mEventDispatcher'), [item[0] for item in delivered])
        self.assertEqual(len(audio.async_audio_state(value)['pending']), 0)

    def test_completed_listener_count_is_per_item(self):
        value = movie(); owner = Owner(value)
        old = lifecycle._dispatch_key
        lifecycle._dispatch_key = lambda *_args: 1
        try:
            async_native.queue_completion(value, 'one', events=('done',))
            async_native.queue_completion(value, 'two', events=('done',))
            self.assertEqual(async_native.process_async_queue(owner, True), 2)
        finally:
            lifecycle._dispatch_key = old
        completed = audio.async_audio_state(value)['completed']
        self.assertEqual([item['listeners'] for item in completed], [2, 2])

    def test_data_write_queues_field_notification(self):
        value = movie(); context = Context(value)
        native._callback_state(value)['calls'].append({'source': 'Basis/Registry'})
        old = async_native._BASE_NATIVE
        async_native._BASE_NATIVE = lambda *_args: True
        try:
            async_native.native_call(context, 'SetDataValue', ('debug', 'mRuntimeData', 'Count_Balloons', 7))
        finally:
            async_native._BASE_NATIVE = old
        self.assertTrue(any(
            'Count_Balloons' in item['events']
            for item in audio.async_audio_state(value)['pending']
        ))

    def test_manual_override_does_not_schedule_lower_effects(self):
        value = movie(); context = Context(value)
        old = async_native._BASE_NATIVE
        def base(*_args):
            native._callback_state(value)['calls'].append({'source': 'Native-Override'})
            return False
        async_native._BASE_NATIVE = base
        try:
            self.assertFalse(async_native.native_call(
                context, 'SetDataValue', ('mRuntimeData', 'SaveBusy', True),
            ))
        finally:
            async_native._BASE_NATIVE = old
        self.assertEqual(audio.async_audio_state(value)['pending'], [])

    def test_save_operation_gets_deterministic_completion(self):
        value = movie(); context = Context(value)
        old = async_native._BASE_NATIVE
        def base(*_args):
            native._callback_state(value)['calls'].append({'source': 'DKCTF-Simulation:save/profile'})
            return True
        async_native._BASE_NATIVE = base
        try:
            async_native.native_call(context, 'newSaveGame', (1, False))
        finally:
            async_native._BASE_NATIVE = old
        pending = audio.async_audio_state(value)['pending']
        self.assertEqual(len(pending), 2)
        self.assertTrue(any('isSaveDataPopulated' in item['events'] for item in pending))
        self.assertTrue(native._native_data(value)[('mRuntimeData', 'SaveBusy')])

    def test_simple_save_setter_does_not_fake_async_save_completion(self):
        value = movie(); context = Context(value)
        old = async_native._BASE_NATIVE
        def base(*_args):
            native._callback_state(value)['calls'].append({'source': 'DKCTF-Simulation:save/profile'})
            return True
        async_native._BASE_NATIVE = base
        try:
            async_native.native_call(context, 'setBalloonCount', (7,))
        finally:
            async_native._BASE_NATIVE = old
        self.assertEqual(audio.async_audio_state(value)['pending'], [])

    def test_audio_setting_callback_is_not_treated_as_sound_name(self):
        value = movie(); context = Context(value)
        old_native, old_post = async_native._BASE_NATIVE, async_native._post_audio
        calls = []
        def base(*_args):
            native._callback_state(value)['calls'].append({'source': 'DKCTF-Simulation:audio'})
            return True
        async_native._BASE_NATIVE = base
        async_native._post_audio = lambda *_args: calls.append(True)
        try:
            async_native.native_call(context, 'EffectsSetting', (0.5,))
        finally:
            async_native._BASE_NATIVE, async_native._post_audio = old_native, old_post
        self.assertEqual(calls, [])

    def test_audio_resolution_queues_real_duration_completion_without_autoplay(self):
        value = movie(); owner = Owner(value); value._ui_audio_owner = owner
        context = Context(value)
        record = audio.UiSoundRecord('UI_Test', 'uitest', 'UIPak', 'caud', ('csmp',), {}, {'loop': False})
        value.ui_audio_catalog = (record,)
        value.ui_audio_name_index = {'uitest': [record]}
        native._callback_state(value)['audio_requests'].append({'sound': 'UI_Test'})
        old_attach, old_find, old_decode = audio.attach_audio_catalog, audio.find_csmp, async_native.decode_csmp_pcm
        audio.attach_audio_catalog = lambda *_args: (record,)
        audio.find_csmp = lambda *_args: ('csmp', b'asset')
        async_native.decode_csmp_pcm = lambda *_args: ([], SimpleNamespace(duration_seconds=0.25))
        try:
            async_native._post_audio(context, 'playSound', ('UI_Test',))
        finally:
            audio.attach_audio_catalog, audio.find_csmp = old_attach, old_find
            async_native.decode_csmp_pcm = old_decode
        request = native._callback_state(value)['audio_requests'][-1]
        self.assertTrue(request['resolved'])
        self.assertEqual(request['caud_uuid'], 'caud')
        pending = audio.async_audio_state(value)['pending']
        self.assertEqual(len(pending), 1)
        self.assertAlmostEqual(pending[0]['due_ms'], 250.0)
        self.assertIn('soundComplete', pending[0]['events'])

    def test_audio_preset_schema_is_backward_compatible(self):
        result = patch.normalize_preset({'format': 'x'})
        self.assertEqual(result['audio_preview']['volume'], 0.65)
        self.assertFalse(result['audio_preview']['enabled'])


if __name__ == '__main__':
    unittest.main()
