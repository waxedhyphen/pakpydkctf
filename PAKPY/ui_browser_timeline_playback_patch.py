"""Install running root and nested Scaleform timelines in the UI Browser.

Playback is preview-only. Manual MovieClip frame overrides retain precedence, and
optional speed/playing/frame state is included in the existing JSON preset schema.
"""
from __future__ import annotations

import ui_browser_timeline_browser_patch as browser_patch
import ui_browser_timeline_core as core
import ui_browser_timeline_inspector_patch as inspector_patch


_INSTALLED = False


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    core.install()
    browser_patch.install()
    inspector_patch.install()


normalize_timeline_instance = core.normalize_timeline_instance
normalize_playback_preset = core.normalize_playback_preset
advance_timeline_instance = core.advance_timeline_instance
timeline_frame_for_path = core.timeline_frame_for_path
register_movie = core.register_movie
_decorate_nodes = core._decorate_nodes
