"""Share the read-only MSBT catalog between movies in one UI Browser session."""
from __future__ import annotations

import ui_browser_localization as localization


_INSTALLED = False
_BASE_ATTACH = None


def _catalog_token(owner):
    return tuple(
        (str(parsed.get("path", "")), len(parsed.get("entries", ())), id(parsed.get("data")))
        for parsed, _label in localization.source_items(owner)
    )


def attach_localization_catalog(owner, movie=None):
    movie = movie or getattr(owner, "_current_movie", None)
    if movie is None:
        return {}
    token = _catalog_token(owner)
    shared_token = getattr(owner, "_ui_localization_catalog_cache_token", None)
    shared_catalog = getattr(owner, "_ui_localization_catalog_cache", None)
    if shared_token == token and isinstance(shared_catalog, dict):
        if getattr(movie, "_ui_localization_catalog_token", None) != token:
            movie.ui_localization_catalog = shared_catalog
            movie._ui_localization_catalog_token = token
            movie.ui_localization_revision = int(
                getattr(movie, "ui_localization_revision", 0)
            ) + 1
        movie._ui_localization_owner = owner
        localization.ensure_localization_config(movie)
        localization.attach_localization_links(movie)
        return movie.ui_localization_catalog

    catalog = _BASE_ATTACH(owner, movie)
    owner._ui_localization_catalog_cache_token = token
    owner._ui_localization_catalog_cache = catalog
    return catalog


def clear_localization_catalog_cache(owner):
    owner._ui_localization_catalog_cache_token = None
    owner._ui_localization_catalog_cache = None


def install():
    global _INSTALLED, _BASE_ATTACH
    if _INSTALLED:
        return
    _INSTALLED = True
    _BASE_ATTACH = localization.attach_localization_catalog
    localization.attach_localization_catalog = attach_localization_catalog
