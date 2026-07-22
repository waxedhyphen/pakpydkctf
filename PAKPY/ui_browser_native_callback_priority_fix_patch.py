"""Ensure manual native-callback overrides suppress every lower callback layer.

The main callback patch preserves the existing registry and DataValue bridge. This
follow-up moves the explicit return override in front of that bridge so a write callback
cannot mutate preview state before its requested override is returned.
"""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_runtime_patch as runtime
import ui_browser_native_callback_patch as native
from ui_browser_native_callback_catalog import callback_spec


_INSTALLED = False
_BASE_NATIVE = None


def native_call(context, name, args):
    native.attach_native_callback_inventory(context.movie)
    native._ensure_config(context.movie)
    overridden, override_value = native._find_override(context.movie, name)
    if not overridden:
        return _BASE_NATIVE(context, name, args)

    context.callbacks += 1
    result = native._json_safe(override_value)
    source = "Native-Override"
    runtime._log(
        context.movie, "callback", name=str(name), status=source,
        result=repr(result), path=context.path,
    )
    return native._record_callback(
        context, str(name), tuple(args), callback_spec(name), source, result,
    )


def install():
    global _INSTALLED, _BASE_NATIVE
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_NATIVE = runtime._native
    runtime._native = native_call
    native.native_call = native_call
    ui_browser.call_ui_native_callback = native_call
