"""Run linked AVM2 instance initializers when a dynamic object is constructed."""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_avm2_lifecycle_patch as lifecycle
import ui_browser_avm2_runtime_patch as runtime


_INSTALLED = False
_BASE_CONSTRUCT = None


def construct_dynamic(context, class_name, args=()):
    obj = _BASE_CONSTRUCT(context, class_name, args)
    if not isinstance(obj, dynamic.DynamicDisplayObject):
        return obj
    if obj.extras.get("initialized") or lifecycle._find_class(context.movie, obj.class_name) is None:
        return obj
    owner = context.owner or getattr(context.movie, "_ui_avm2_runtime_owner", None)
    try:
        lifecycle.initialize_instance(
            owner, context.movie, obj.path, obj.definition, obj.class_name,
            obj.current_frame, obj.playing,
        )
        obj.extras["initialized"] = True
    except Exception as exc:
        runtime._error(context.movie, obj.path, "dynamic-constructor", exc)
    return obj


def install():
    global _INSTALLED, _BASE_CONSTRUCT
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_CONSTRUCT = dynamic.construct_dynamic
    dynamic.construct_dynamic = construct_dynamic
    ui_browser.construct_dynamic_avm2_object = construct_dynamic
