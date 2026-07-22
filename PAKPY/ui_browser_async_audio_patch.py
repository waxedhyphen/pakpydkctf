"""Install deterministic native completions and CAUD/CSMP UI-audio preview."""
from __future__ import annotations

import ui_browser
import ui_browser_audio_preview as audio
import ui_browser_async_audio_gui as gui
import ui_browser_async_native as async_native
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_native_callback_patch as native
import ui_browser_state_inspector_patch as state_inspector
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_core as timeline_core

try:
    import ui_browser_game_state_patch as game_state
except Exception:
    game_state = None

_INSTALLED = False


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    base_native = runtime._native
    base_clock = lifecycle.advance_runtime_clock
    base_reset = runtime.reset_runtime
    base_init = ui_browser.UIBrowser.__init__
    base_select = ui_browser.UIBrowser._on_tree_select
    base_info = ui_browser.UIBrowser._format_info
    base_close = ui_browser.UIBrowser.close
    base_make = override_patch.make_preset
    base_normalize = override_patch.normalize_preset

    async_native.install_hooks(base_native, base_clock, base_reset)
    gui.install_hooks(
        base_init, base_select, base_info, base_close, base_make, base_normalize,
    )
    ui_browser.UIBrowser.reset_avm2_runtime = async_native.reset_runtime

    override_patch.make_preset = gui.make_preset
    override_patch.normalize_preset = gui.normalize_preset
    timeline_core.make_preset_with_playback = gui.make_preset
    timeline_core.normalize_preset_with_playback = gui.normalize_preset
    ui_browser.make_ui_state_preset = gui.make_preset
    ui_browser.normalize_ui_state_preset = gui.normalize_preset
    native.make_preset = gui.make_preset
    native.normalize_preset = gui.normalize_preset
    native.load_preset = gui.load_preset
    if game_state is not None:
        game_state.make_preset = gui.make_preset
        game_state.normalize_preset = gui.normalize_preset
        game_state.load_preset = gui.load_preset
    try:
        import ui_browser_timeline_inspector_patch as timeline_inspector
        timeline_inspector.load_preset = gui.load_preset
    except Exception:
        pass
    state_inspector.StateInspectorWindow.load_override_preset = gui.load_preset

    ui_browser.UiSoundRecord = audio.UiSoundRecord
    ui_browser.build_ui_audio_catalog = audio.build_audio_catalog
    ui_browser.resolve_ui_sound = audio.resolve_sound
    ui_browser.decode_ui_sound = audio.decode_sound
    ui_browser.play_ui_sound = audio.play_sound
    ui_browser.stop_ui_sound = audio.stop_audio
    ui_browser.queue_ui_native_completion = async_native.queue_completion
    ui_browser.process_ui_native_completions = async_native.process_async_queue
    ui_browser.normalize_ui_audio_preview_config = audio.normalize_audio_preview_config


# Public model helpers used by tests and external preview tooling.
UiSoundRecord = audio.UiSoundRecord
WavePreviewBackend = audio.WavePreviewBackend
normalize_audio_preview_config = audio.normalize_audio_preview_config
build_audio_catalog = audio.build_audio_catalog
attach_audio_catalog = audio.attach_audio_catalog
resolve_sound = audio.resolve_sound
decode_sound = audio.decode_sound
play_sound = audio.play_sound
stop_audio = audio.stop_audio
_async_state = audio.async_audio_state
_find_csmp = audio.find_csmp
decode_csmp_pcm = async_native.decode_csmp_pcm
queue_completion = async_native.queue_completion
process_async_queue = async_native.process_async_queue
native_call = async_native.native_call
_post_audio = async_native._post_audio
_BASE = {"native": None, "normalize_preset": None}


def normalize_preset(data):
    # Test-friendly facade; installed runtime uses gui.normalize_preset directly.
    base = _BASE.get("normalize_preset")
    if callable(base):
        old = gui._BASE.get("normalize_preset")
        gui._BASE["normalize_preset"] = base
        try:
            return gui.normalize_preset(data)
        finally:
            if old is None:
                gui._BASE.pop("normalize_preset", None)
            else:
                gui._BASE["normalize_preset"] = old
    return {**dict(data or {}), "audio_preview": audio.normalize_audio_preview_config(
        data.get("audio_preview", {}) if isinstance(data, dict) else {},
    )}
