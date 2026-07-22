"""Add Scaleform GFXL external-image libraries to the UI Browser.

Tropical Freeze's image GFXL movies do not contain normal DefineBits tags. They
use Scaleform tag 1009 (DefineExternalImage2-like) plus SymbolClass entries. The
base UI Browser already resolves GFXL names to TXTR UUIDs, but it previously
ignored the embedded library movie and therefore lost the intended image size,
file name, and browsable library symbol list.

This patch keeps ActionScript out of scope. It adds the next static-rendering
layer:

* parse tag 1009 and link it to SymbolClass and the GFXL UUID mapping;
* use the library-declared display dimensions when drawing imported images;
* expose every image symbol from current and required PAKs in the UI Browser;
* retain source/storage metadata for diagnostics.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import ui_browser

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

try:
    from preview_orientation_patch import rotate_preview_image
except Exception:
    rotate_preview_image = None


SCALEFORM_DEFINE_EXTERNAL_IMAGE2 = 1009
_INSTALLED = False
_LIBRARY_CACHE = {}


@dataclass(frozen=True)
class ExternalImageTag:
    character_id: int
    format_id: int
    width: int
    height: int
    name: str
    filename: str
    tail: bytes = b""


@dataclass(frozen=True)
class LibraryImageSymbol:
    library: object
    movie: object
    character_id: int
    format_id: int
    width: int
    height: int
    name: str
    class_name: str
    filename: str
    uuid_hex: str

    @property
    def source(self) -> str:
        return str(getattr(self.library, "source", ""))

    @property
    def aliases(self) -> tuple[str, ...]:
        values = [self.name, self.class_name, self.filename]
        if self.filename:
            values.append(Path(self.filename).stem)
        result = []
        seen = set()
        for value in values:
            value = str(value or "")
            if value and value not in seen:
                seen.add(value)
                result.append(value)
        return tuple(result)


def parse_external_image_tag(payload: bytes) -> ExternalImageTag:
    """Parse Scaleform tag 1009 used by the DKCTF image libraries."""
    if len(payload) < 12:
        raise ui_browser.PakError("Scaleform-ExternalImage-Tag ist abgeschnitten")
    character_id = int.from_bytes(payload[0:4], "little")
    format_id = int.from_bytes(payload[4:6], "little")
    width = int.from_bytes(payload[6:8], "little")
    height = int.from_bytes(payload[8:10], "little")
    name_length = payload[10]
    p = 11
    if p + name_length + 1 > len(payload):
        raise ui_browser.PakError("Scaleform-ExternalImage-Name ist abgeschnitten")
    name = payload[p:p + name_length].decode("utf-8", "replace")
    p += name_length
    filename_length = payload[p]
    p += 1
    if p + filename_length > len(payload):
        raise ui_browser.PakError("Scaleform-ExternalImage-Dateiname ist abgeschnitten")
    filename = payload[p:p + filename_length].decode("utf-8", "replace")
    p += filename_length
    if width <= 0 or height <= 0:
        raise ui_browser.PakError(f"Scaleform-ExternalImage {name or character_id} hat ungültige Maße {width}×{height}")
    return ExternalImageTag(character_id, format_id, width, height, name, filename, payload[p:])


def _short_name(value: str) -> str:
    return str(value or "").rsplit(".", 1)[-1].rsplit("::", 1)[-1]


def _library_cache_key(library) -> tuple[str, str, int, int]:
    data = bytes(getattr(library, "movie_data", b""))
    return (
        str(getattr(library, "entry_uuid", "")),
        str(getattr(library, "name", "")),
        len(data),
        hash(data),
    )


def parse_library_symbols(library) -> tuple[object, tuple[LibraryImageSymbol, ...], tuple[str, ...]]:
    """Parse one GFXL movie and return its external-image symbols."""
    key = _library_cache_key(library)
    cached = _LIBRARY_CACHE.get(key)
    if cached is not None:
        return cached
    errors = []
    try:
        movie = ui_browser.parse_swf_movie(library.movie_data)
    except Exception as exc:
        result = (None, tuple(), (str(exc),))
        _LIBRARY_CACHE[key] = result
        return result

    mappings = dict(getattr(library, "mappings", {}) or {})
    symbols = []
    for code, payload in movie.root_tags:
        if code != SCALEFORM_DEFINE_EXTERNAL_IMAGE2:
            continue
        try:
            external = parse_external_image_tag(payload)
            class_name = movie.symbol_classes.get(external.character_id) or external.name
            uuid_hex = mappings.get(external.name) or mappings.get(class_name) or mappings.get(_short_name(class_name), "")
            if not uuid_hex:
                errors.append(f"{external.name}: keine UUID in {getattr(library, 'name', 'GFXL')}")
            symbols.append(LibraryImageSymbol(
                library=library,
                movie=movie,
                character_id=external.character_id,
                format_id=external.format_id,
                width=external.width,
                height=external.height,
                name=external.name,
                class_name=class_name,
                filename=external.filename,
                uuid_hex=uuid_hex,
            ))
        except Exception as exc:
            errors.append(str(exc))
    symbols.sort(key=lambda item: (item.name.lower(), item.character_id))
    result = (movie, tuple(symbols), tuple(errors))
    _LIBRARY_CACHE[key] = result
    return result


def build_library_symbol_index(libraries) -> tuple[tuple[LibraryImageSymbol, ...], dict[str, tuple[LibraryImageSymbol, ...]], tuple[str, ...]]:
    symbols = []
    errors = []
    for library in libraries:
        _movie, items, item_errors = parse_library_symbols(library)
        symbols.extend(items)
        errors.extend(f"{getattr(library, 'name', 'GFXL')}: {text}" for text in item_errors)
    index = {}
    for symbol in symbols:
        for alias in symbol.aliases:
            for key in (alias, _short_name(alias)):
                index.setdefault(key, []).append(symbol)
    frozen_index = {key: tuple(value) for key, value in index.items()}
    return tuple(symbols), frozen_index, tuple(errors)


def find_library_symbol(resolver, name: str, uuid_hex: str = "") -> LibraryImageSymbol | None:
    index = getattr(resolver, "library_symbol_index", {})
    candidates = list(index.get(name, ()))
    if not candidates:
        candidates = list(index.get(_short_name(name), ()))
    if uuid_hex:
        for symbol in candidates:
            if symbol.uuid_hex == uuid_hex:
                return symbol
    preferred = str(getattr(resolver, "preferred_library_uuid", ""))
    if preferred:
        for symbol in candidates:
            if str(getattr(symbol.library, "entry_uuid", "")) == preferred:
                return symbol
    return candidates[0] if candidates else None


def resize_external_image(image, width: int, height: int):
    if image is None or PILImage is None:
        return image
    size = (max(1, int(width)), max(1, int(height)))
    if image.size == size:
        return image
    resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS")
    return image.resize(size, resampling)


def _load_lookup_metadata(resolver, result, symbol: LibraryImageSymbol) -> None:
    result.library_symbol = symbol
    result.library_name = str(getattr(symbol.library, "name", ""))
    result.external_filename = symbol.filename
    result.external_format_id = symbol.format_id
    result.external_size = (symbol.width, symbol.height)
    result.source_texture_size = result.image.size if result.image is not None else None
    result.gpu_codec = ""
    result.preview_rotate_180 = False
    if not symbol.uuid_hex:
        return
    try:
        asset, _entry, _source = resolver._resolve_asset(symbol.uuid_hex)
        if asset is None or ui_browser.parse_txtr_asset is None:
            return
        info = ui_browser.parse_txtr_asset(asset)
        result.gpu_codec = str(info.get("gpu_codec", ""))
        result.preview_rotate_180 = result.gpu_codec.strip().lower() == "zlib"
        result.txtr_size = (int(info.get("width", 0)), int(info.get("height", 0)))
        result.txtr_format = info.get("format")
    except Exception:
        return


def _format_library_symbol_info(symbol: LibraryImageSymbol, lookup) -> str:
    txtr_size = getattr(lookup, "txtr_size", None)
    source_size = getattr(lookup, "source_texture_size", None)
    lines = [
        f"PAK: {symbol.source or 'unbekannt'}",
        f"GFXL: {getattr(symbol.library, 'name', '')}",
        f"Symbol: {symbol.name}",
        f"SymbolClass: {symbol.class_name}",
        f"Character-ID: {symbol.character_id}",
        f"Scaleform-Format-ID: {symbol.format_id}",
        f"Dateiname: {symbol.filename or '-'}",
        f"TXTR-UUID: {symbol.uuid_hex or '-'}",
        "",
        f"Scaleform-Anzeigemaße: {symbol.width} × {symbol.height}",
    ]
    if txtr_size:
        lines.append(f"TXTR-HEAD-Maße: {txtr_size[0]} × {txtr_size[1]}")
    if source_size:
        lines.append(f"Dekodierte Ausgangsmaße: {source_size[0]} × {source_size[1]}")
    codec = getattr(lookup, "gpu_codec", "")
    if codec:
        lines.append(f"GPU-Codec: {codec}")
    if getattr(lookup, "source", ""):
        lines.append(f"TXTR-Quelle: {lookup.source}")
    lines.extend([
        "",
        "Status:",
        "Das Symbol wurde aus dem eingebetteten GFXL-Library-Film (Tag 1009 + SymbolClass) rekonstruiert und mit seiner TXTR-UUID verbunden.",
        "",
        "Hinweis:",
        "Dies ist ein einzelnes Library-Bildsymbol. Zusammengesetzte MovieClips, Vektor-Shapes, Masken und ActionScript-Zustände sind spätere Viewer-Stufen.",
    ])
    return "\n".join(lines)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_resolver_init = ui_browser.TextureResolver.__init__
    original_resolver_get = ui_browser.TextureResolver.get

    def resolver_init(self, *args, **kwargs):
        original_resolver_init(self, *args, **kwargs)
        symbols, index, errors = build_library_symbol_index(self.libraries)
        self.library_symbols = symbols
        self.library_symbol_index = index
        self.library_parse_errors = errors

    def resolver_get(self, name):
        result = original_resolver_get(self, name)
        symbol = find_library_symbol(self, name, getattr(result, "uuid_hex", ""))
        if symbol is not None and getattr(result, "library_symbol", None) is None:
            _load_lookup_metadata(self, result, symbol)
            if result.image is not None:
                result.image = resize_external_image(result.image, symbol.width, symbol.height)
        return result

    ui_browser.TextureResolver.__init__ = resolver_init
    ui_browser.TextureResolver.get = resolver_get
    ui_browser.TextureResolver.find_library_symbol = find_library_symbol

    original_browser_init = ui_browser.UIBrowser.__init__
    original_tree_select = ui_browser.UIBrowser._on_tree_select
    original_render = ui_browser.UIBrowser._render

    def browser_init(self, *args, **kwargs):
        self._library_tree_data = {}
        self._current_library_symbol = None
        self._library_catalog_resolver = None
        original_browser_init(self, *args, **kwargs)
        try:
            self._library_catalog_resolver = ui_browser.TextureResolver(self.parsed, self.require_store)
            _populate_library_tree(self)
        except Exception as exc:
            self._set_info(f"GFXL-Library-Katalog konnte nicht aufgebaut werden:\n{exc}")

    def tree_select(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return original_tree_select(self, event)
        iid = selection[0]
        symbol = self._library_tree_data.get(iid)
        if symbol is not None:
            _select_library_symbol(self, symbol)
            return
        if iid not in self._tree_data:
            return
        self._current_library_symbol = None
        try:
            self.frame_scale.configure(state="normal")
        except Exception:
            pass
        return original_tree_select(self, event)

    def render(self):
        symbol = getattr(self, "_current_library_symbol", None)
        if symbol is None:
            return original_render(self)
        self._render_pending = False
        if self._closed or self._current_resolver is None:
            return
        try:
            lookup = self._current_resolver.get(symbol.name)
            if lookup.image is None:
                raise ui_browser.PakError(lookup.error or f"TXTR für {symbol.name} konnte nicht geladen werden")
            image = lookup.image.copy()
            if getattr(lookup, "preview_rotate_180", False) and rotate_preview_image is not None:
                image = rotate_preview_image(image)
            self._stage_image = image
            self.status_var.set(f"GFXL | {symbol.width}×{symbol.height} | {symbol.name}")
            self._set_info(_format_library_symbol_info(symbol, lookup))
            self._draw_scaled()
        except Exception as exc:
            self.status_var.set("GFXL-Renderfehler")
            self._set_info(str(exc))

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = tree_select
    ui_browser.UIBrowser._render = render


def _populate_library_tree(browser) -> None:
    resolver = browser._library_catalog_resolver
    symbols = list(getattr(resolver, "library_symbols", ()))
    root_iid = "gfxl_library_root"
    if browser.tree.exists(root_iid):
        browser.tree.delete(root_iid)
    browser.tree.insert("", "end", iid=root_iid, text=f"GFXL Libraries ({len(symbols)} Bildsymbole)", open=False)

    source_nodes = {}
    libraries = list(getattr(resolver, "libraries", ()))
    symbols_by_library = {}
    for symbol in symbols:
        symbols_by_library.setdefault(id(symbol.library), []).append(symbol)

    for library_index, library in enumerate(libraries):
        source = str(getattr(library, "source", "") or "unbekannte Quelle")
        source_iid = source_nodes.get(source)
        if source_iid is None:
            source_iid = f"gfxl_source_{len(source_nodes)}"
            source_nodes[source] = source_iid
            browser.tree.insert(root_iid, "end", iid=source_iid, text=source, open=False)
        items = symbols_by_library.get(id(library), [])
        library_iid = f"gfxl_library_{library_index}"
        mapping_count = len(getattr(library, "mappings", {}) or {})
        label = f"{getattr(library, 'name', 'GFXL')} ({len(items)} Bilder"
        if mapping_count != len(items):
            label += f", {mapping_count} Zuordnungen"
        label += ")"
        browser.tree.insert(source_iid, "end", iid=library_iid, text=label, open=False)
        if not items:
            browser.tree.insert(library_iid, "end", iid=f"{library_iid}_empty", text="Keine Tag-1009-Bildsymbole")
            continue
        for symbol_index, symbol in enumerate(items):
            iid = f"gfxl_symbol_{library_index}_{symbol_index}"
            browser.tree.insert(library_iid, "end", iid=iid, text=f"{symbol.name}  [{symbol.width}×{symbol.height}]")
            browser._library_tree_data[iid] = symbol


def _select_library_symbol(browser, symbol: LibraryImageSymbol) -> None:
    resolver = ui_browser.TextureResolver(
        browser.parsed,
        browser.require_store,
        preferred_library_uuid=str(getattr(symbol.library, "entry_uuid", "")),
        imports=[str(getattr(symbol.library, "name", ""))],
    )
    browser._current_library_symbol = symbol
    browser._current_resolver = resolver
    browser._current_container = None
    browser._current_source = SimpleNamespace(
        source_label=symbol.source or "GFXL",
        entry={"name": str(getattr(symbol.library, "name", "GFXL")), "display_name": str(getattr(symbol.library, "name", "GFXL"))},
    )
    browser._current_movie_record = SimpleNamespace(name=symbol.name)
    browser._current_movie = SimpleNamespace(
        width=max(1, symbol.width),
        height=max(1, symbol.height),
        frame_count=1,
        frame_rate=0.0,
        version=getattr(symbol.movie, "version", 0),
        labels={},
        imports=[],
        definitions={},
        stage_bounds=(0.0, 0.0, float(max(1, symbol.width)), float(max(1, symbol.height))),
    )
    browser.frame_var.set(1)
    browser.frame_scale.configure(from_=1, to=1, state="disabled")
    browser.frame_scale.set(1)
    browser._update_frame_text()
    browser.request_render()
