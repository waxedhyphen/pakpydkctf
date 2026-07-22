"""Run in-module AVM2 base-class initializers before derived instance constructors."""
from __future__ import annotations

import ui_browser
import ui_browser_avm2_patch as avm2
import ui_browser_avm2_lifecycle_patch as lifecycle

_INSTALLED = False
_BASE_INITIALIZE = None
_MAX_CHAIN = 32


def class_chain(module, class_index):
    abc = module.abc
    by_name = {
        avm2._canonical_name(abc.class_name(index)): index
        for index in range(len(abc.instances))
    }
    result = []
    seen = set()
    current = int(class_index)
    while current not in seen and 0 <= current < len(abc.instances) and len(result) < _MAX_CHAIN:
        seen.add(current)
        result.append(current)
        parent = avm2._canonical_name(
            abc.multiname_name(abc.instances[current].super_name_index)
        )
        current = by_name.get(parent, -1)
    return tuple(reversed(result))


def initialize_instance(owner, movie, path, definition, class_name, frame=1, playing=True):
    found = lifecycle._find_class(movie, class_name)
    if found is None:
        return _BASE_INITIALIZE(owner, movie, path, definition, class_name, frame, playing)
    module, class_index = found
    changed = False
    chain = class_chain(module, class_index)
    for index in chain[:-1]:
        changed = _BASE_INITIALIZE(
            owner, movie, path, definition,
            module.abc.class_name(index), frame, playing,
        ) or changed
    return _BASE_INITIALIZE(
        owner, movie, path, definition, class_name, frame, playing,
    ) or changed


def install():
    global _INSTALLED, _BASE_INITIALIZE
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_INITIALIZE = lifecycle.initialize_instance
    lifecycle.initialize_instance = initialize_instance
    ui_browser.initialize_avm2_instance = initialize_instance
