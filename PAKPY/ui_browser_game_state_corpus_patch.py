"""Tune automatic game-mock matching to names present in the shipped UI corpus."""
from __future__ import annotations

from dataclasses import replace

import ui_browser
import ui_browser_game_state_patch as game_state


_INSTALLED = False
_CORPUS_ALIASES = {
    "lives": ("ballooncounter",),
    "banana_coins": ("coincounter", "txtcoins"),
    "puzzle_pieces": ("puzzletally",),
    "timer_seconds": ("currenttime", "timetally", "texttime", "txttime"),
    "kong_letters": ("kongtally",),
}


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    fields = []
    for field in game_state.MOCK_FIELDS:
        aliases = list(field.aliases)
        for alias in _CORPUS_ALIASES.get(field.key, ()):
            if alias not in aliases:
                aliases.append(alias)
        fields.append(replace(field, aliases=tuple(aliases)))
    game_state.MOCK_FIELDS = tuple(fields)
    game_state.MOCK_FIELD_BY_KEY = {field.key: field for field in fields}
    ui_browser.UI_GAME_MOCK_FIELDS = game_state.MOCK_FIELDS
