"""Install classic SWF buttons and precise, clipped UI hit testing."""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_button_navigation_patch as button
import ui_browser_button_owner_fix_patch as button_owner
import ui_browser_classic_button as classic
import ui_browser_classic_button_gui as gui
import ui_browser_classic_button_runtime as button_runtime
import ui_browser_precise_hit as precise
import ui_browser_state_inspector_patch as inspector

_INSTALLED = False


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    precise.install_hooks(
        ui_browser.UIRenderer.render, button_owner._BASE_HIT,
        runtime._set_property, runtime._get_property,
    )
    button_runtime.install_hooks(
        ui_browser.parse_swf_movie, dynamic._dispatch_path, button.mouse_event,
        button.key_event, button.activate_focus, runtime.reset_runtime,
    )
    gui.install_hooks(
        inspector.inspect_movie_state, inspector.format_state_node,
        ui_browser.UIBrowser.__init__, ui_browser.UIBrowser._on_tree_select,
        ui_browser.UIBrowser._format_info, ui_browser.UIBrowser.close,
    )

    ui_browser.parse_swf_movie = button_runtime.parse_swf_movie
    ui_browser.UIRenderer.render = precise.renderer_render
    button_owner._BASE_HIT = precise.precise_raw_hit
    runtime._set_property = precise.set_property
    runtime._get_property = precise.get_property
    dynamic._dispatch_path = button_runtime.dispatch_path
    button.mouse_event = button_runtime.mouse_event
    button.key_event = button_runtime.key_event
    button.activate_focus = button_runtime.activate_focus
    runtime.reset_runtime = button_runtime.reset_runtime
    lifecycle.reset_runtime = button_runtime.reset_runtime
    ui_browser.UIBrowser.reset_avm2_runtime = button_runtime.reset_runtime
    inspector.inspect_movie_state = gui.inspect_movie_state
    inspector.format_state_node = gui.format_state_node
    ui_browser.inspect_movie_state = gui.inspect_movie_state

    ui_browser.ClassicButtonDef = classic.ClassicButtonDef
    ui_browser.ClassicButtonRecord = classic.ButtonRecord
    ui_browser.ClassicButtonAction = classic.Avm1Action
    ui_browser.PreciseHitGeometry = classic.HitGeometry
    ui_browser.parse_classic_swf_button = classic.parse_classic_button
    ui_browser.build_precise_ui_hit_map = precise.build_precise_hit_map
    ui_browser.trigger_classic_button_condition = button_runtime.trigger_condition
