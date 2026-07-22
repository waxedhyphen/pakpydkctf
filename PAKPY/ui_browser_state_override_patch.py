"""Add manual UI-state overrides and JSON presets to the static UI Browser.

Overrides are keyed by the stable paths exposed by the State Inspector.  They can
change placement visibility, choose a nested MovieClip frame, replace EditText text,
and temporarily disable filters or blend modes.  The renderer applies them to shallow
copies of display objects and text definitions; source GFX/GFXL/TXTR/MSBT bytes are
never modified.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import inspect
import json
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ui_browser
import ui_browser_mask_patch as mask_patch
import ui_browser_scale9_blend_patch as scale9_patch
import ui_browser_state_inspector_patch as inspector


PRESET_FORMAT = "PAKPY_UI_STATE_PRESET"
PRESET_VERSION = 1
_INSTALLED = False
_ORIGINAL_BUILD_DISPLAY_LIST = None
_FORCED_DISPLAY_STACKS = {}


def _movie_definition(movie, item):
    character_id = getattr(item, "character_id", None)
    return movie.definitions.get(character_id) if character_id is not None else None


def state_item_path(movie, parent_path, depth, item):
    definition = _movie_definition(movie, item)
    label = inspector._node_label(movie, item, definition)
    return f"{parent_path}/{int(depth)}:{label}"


def normalize_override(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    if "visible" in value:
        result["visible"] = bool(value["visible"])
    if "sprite_frame" in value:
        try:
            frame = int(value["sprite_frame"])
        except Exception:
            frame = 0
        if frame > 0:
            result["sprite_frame"] = frame
    if "text" in value:
        result["text"] = str(value.get("text", ""))
        result["html"] = bool(value.get("html", False))
    if value.get("disable_filters"):
        result["disable_filters"] = True
    if value.get("disable_blend"):
        result["disable_blend"] = True
    return result


def normalize_overrides(value):
    if not isinstance(value, dict):
        return {}
    result = {}
    for path, override in value.items():
        clean = normalize_override(override)
        if clean:
            result[str(path)] = clean
    return result


def apply_item_override(movie, parent_path, depth, item, overrides):
    path = state_item_path(movie, parent_path, depth, item)
    override = normalize_override((overrides or {}).get(path, {}))
    if not override:
        return item, path, {}
    clone = copy.copy(item)
    if "visible" in override:
        clone.visible = override["visible"]
    if override.get("disable_filters"):
        clone.filters = ()
    if override.get("disable_blend"):
        clone.blend_mode = 0
    clone._ui_state_path = path
    clone._ui_state_override = dict(override)
    return clone, path, override


def sprite_frame_for_path(definition, path, overrides):
    override = normalize_override((overrides or {}).get(path, {}))
    frame_count = max(1, int(getattr(definition, "frame_count", 1) or 1))
    return max(1, min(frame_count, int(override.get("sprite_frame", 1))))


def text_definition_for_path(definition, path, overrides):
    override = normalize_override((overrides or {}).get(path, {}))
    if "text" not in override:
        return definition
    clone = copy.copy(definition)
    clone.initial_text = override["text"]
    if hasattr(clone, "html"):
        clone.html = bool(override.get("html", False))
    return clone


def _renderer_overrides(renderer):
    return normalize_overrides(getattr(renderer.movie, "ui_state_overrides", {}))


def _prepare_renderer_item(renderer, parent_path, depth, item):
    clone, path, override = apply_item_override(
        renderer.movie, parent_path, depth, item, _renderer_overrides(renderer),
    )
    if override:
        renderer.stats.state_overrides_applied = getattr(
            renderer.stats, "state_overrides_applied", 0,
        ) + 1
        paths = getattr(renderer.stats, "state_override_paths", None)
        if paths is None:
            renderer.stats.state_override_paths = set()
            paths = renderer.stats.state_override_paths
        paths.add(path)
    return clone, path, override


@contextmanager
def _render_path(renderer, path):
    old_current = getattr(renderer, "_ui_current_path", "")
    old_parent = getattr(renderer, "_ui_state_parent_path", "root")
    renderer._ui_current_path = path
    renderer._ui_state_parent_path = path
    try:
        yield
    finally:
        renderer._ui_current_path = old_current
        renderer._ui_state_parent_path = old_parent


@contextmanager
def _force_sprite_frame(renderer, item, path):
    definition = _movie_definition(renderer.movie, item)
    if not isinstance(definition, ui_browser.SpriteDef):
        yield
        return
    overrides = _renderer_overrides(renderer)
    frame = sprite_frame_for_path(definition, path, overrides)
    if frame == 1 or _ORIGINAL_BUILD_DISPLAY_LIST is None:
        yield
        return
    display = _ORIGINAL_BUILD_DISPLAY_LIST(definition.tags, frame)
    key = id(definition.tags)
    stack = _FORCED_DISPLAY_STACKS.setdefault(key, [])
    stack.append(display)
    try:
        yield
    finally:
        stack.pop()
        if not stack:
            _FORCED_DISPLAY_STACKS.pop(key, None)


def inspect_movie_state_with_overrides(movie, frame, overrides=None, max_depth=64):
    overrides = normalize_overrides(
        getattr(movie, "ui_state_overrides", {}) if overrides is None else overrides,
    )
    build = _ORIGINAL_BUILD_DISPLAY_LIST or ui_browser.build_display_list
    root_frame = max(1, min(int(frame), int(getattr(movie, "frame_count", 1) or 1)))

    def recurse(display, parent_path, stack, level):
        if level > max_depth:
            return ()
        result = []
        for depth in sorted(display):
            raw_item = display[depth]
            item, path, override = apply_item_override(
                movie, parent_path, depth, raw_item, overrides,
            )
            character_id = getattr(item, "character_id", None)
            definition = _movie_definition(movie, item)
            kind = "External" if getattr(item, "class_name", "") else inspector._definition_kind(definition)
            label = inspector._node_label(movie, item, definition)
            sprite_frame = 1
            if isinstance(definition, ui_browser.SpriteDef):
                sprite_frame = sprite_frame_for_path(definition, path, overrides)
            metadata = inspector._metadata_for(movie, item, definition, sprite_frame)
            if override:
                metadata["override"] = dict(override)
                metadata["original_visible"] = bool(getattr(raw_item, "visible", True))
                metadata["original_filter_count"] = len(tuple(getattr(raw_item, "filters", ()) or ()))
                metadata["original_blend_mode"] = int(getattr(raw_item, "blend_mode", 0) or 0)
            if isinstance(definition, ui_browser.EditTextDef) and "text" in override:
                metadata["original_text"] = str(getattr(definition, "initial_text", "") or "")
                metadata["text"] = override["text"]
                metadata["display_text"] = override["text"]
                metadata["html"] = bool(override.get("html", False))
            children = ()
            if isinstance(definition, ui_browser.SpriteDef):
                if character_id in stack:
                    metadata["cycle"] = True
                elif level >= max_depth:
                    metadata["max_depth_reached"] = True
                else:
                    child_display = build(definition.tags, sprite_frame)
                    children = recurse(
                        child_display, path, stack + (character_id,), level + 1,
                    )
            result.append(inspector.StateNode(
                path=path,
                depth=int(depth),
                label=label,
                kind=kind,
                visible=bool(getattr(item, "visible", True)),
                character_id=character_id,
                class_name=str(getattr(item, "class_name", "") or ""),
                metadata=metadata,
                children=children,
            ))
        return tuple(result)

    return recurse(build(movie.root_tags, root_frame), "root", (), 0)


def make_preset(owner):
    record = getattr(owner, "_current_movie_record", None)
    source = getattr(owner, "_current_source", None)
    frame_var = getattr(owner, "frame_var", None)
    frame = int(frame_var.get()) if frame_var is not None else 1
    return {
        "format": PRESET_FORMAT,
        "version": PRESET_VERSION,
        "pak": str(getattr(source, "source_label", "") or ""),
        "movie": str(getattr(record, "name", "") or ""),
        "root_frame": frame,
        "overrides": normalize_overrides(getattr(owner, "_ui_state_overrides", {})),
    }


def normalize_preset(data):
    if not isinstance(data, dict):
        raise ui_browser.PakError("UI-Preset ist kein JSON-Objekt")
    if data.get("format") not in (None, PRESET_FORMAT):
        raise ui_browser.PakError("Unbekanntes UI-Preset-Format")
    try:
        version = int(data.get("version", PRESET_VERSION))
    except Exception as exc:
        raise ui_browser.PakError("Ungültige UI-Preset-Version") from exc
    if version != PRESET_VERSION:
        raise ui_browser.PakError(f"UI-Preset-Version {version} wird nicht unterstützt")
    try:
        root_frame = max(1, int(data.get("root_frame", 1)))
    except Exception:
        root_frame = 1
    return {
        "format": PRESET_FORMAT,
        "version": PRESET_VERSION,
        "pak": str(data.get("pak", "") or ""),
        "movie": str(data.get("movie", "") or ""),
        "root_frame": root_frame,
        "overrides": normalize_overrides(data.get("overrides", {})),
    }


def _browser_movie_key(browser):
    source = getattr(browser, "_current_source", None)
    record = getattr(browser, "_current_movie_record", None)
    if source is None or record is None:
        return ""
    entry = getattr(source, "entry", {}) or {}
    return "|".join((
        str(getattr(source, "source_label", "") or ""),
        str(entry.get("uuid_hex", "") or entry.get("index", "")),
        str(getattr(record, "name", "") or ""),
    ))


def _attach_browser_overrides(browser):
    key = _browser_movie_key(browser)
    browser._ui_current_override_key = key
    if key:
        overrides = browser._ui_overrides_by_movie.setdefault(key, {})
    else:
        overrides = {}
    browser._ui_state_overrides = overrides
    movie = getattr(browser, "_current_movie", None)
    if movie is not None:
        movie.ui_state_overrides = overrides
        movie.ui_override_revision = int(getattr(browser, "_ui_override_revision", 0))


def _invalidate_overrides(owner):
    owner._ui_override_revision = int(getattr(owner, "_ui_override_revision", 0)) + 1
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        movie.ui_state_overrides = getattr(owner, "_ui_state_overrides", {})
        movie.ui_override_revision = owner._ui_override_revision
    try:
        scale9_patch._SCALE9_CACHE.clear()
    except Exception:
        pass
    owner.request_render()


def _selected_inspector_node(window):
    selection = window.tree.selection()
    return window._node_by_iid.get(selection[0]) if selection else None


def _sync_override_controls(window):
    if not hasattr(window, "override_visibility_var"):
        return
    node = _selected_inspector_node(window)
    owner = window.owner
    overrides = getattr(owner, "_ui_state_overrides", {})
    override = normalize_override(overrides.get(node.path, {})) if node is not None else {}
    if "visible" not in override:
        window.override_visibility_var.set("Original")
    else:
        window.override_visibility_var.set("Sichtbar" if override["visible"] else "Versteckt")
    window.override_frame_var.set(str(override.get("sprite_frame", 0)))
    window.override_text_enabled_var.set("text" in override)
    window.override_html_var.set(bool(override.get("html", False)))
    window.override_disable_filters_var.set(bool(override.get("disable_filters", False)))
    window.override_disable_blend_var.set(bool(override.get("disable_blend", False)))
    window.override_text.delete("1.0", "end")
    if node is not None:
        text = override.get("text", node.metadata.get("display_text", ""))
        window.override_text.insert("1.0", str(text))
    frame_state = "normal" if node is not None and node.kind == "MovieClip" else "disabled"
    text_state = "normal" if node is not None and node.kind == "EditText" else "disabled"
    window.override_frame_spin.configure(state=frame_state)
    window.override_text.configure(state=text_state)
    window.override_text_toggle.configure(state=text_state)
    window.override_html_toggle.configure(state=text_state)
    if node is None:
        window.override_status_var.set("Keine Instanz ausgewählt")
    elif override:
        window.override_status_var.set(f"Aktiver Override: {node.path}")
    else:
        window.override_status_var.set(f"Originalzustand: {node.path}")


def _apply_selected_override(window):
    node = _selected_inspector_node(window)
    if node is None:
        return
    override = {}
    visibility = window.override_visibility_var.get()
    if visibility == "Sichtbar":
        override["visible"] = True
    elif visibility == "Versteckt":
        override["visible"] = False
    if node.kind == "MovieClip":
        try:
            frame = int(window.override_frame_var.get() or 0)
        except Exception:
            frame = 0
        if frame > 0:
            count = max(1, int(node.metadata.get("sprite_frame_count", 1) or 1))
            override["sprite_frame"] = max(1, min(count, frame))
    if node.kind == "EditText" and window.override_text_enabled_var.get():
        override["text"] = window.override_text.get("1.0", "end-1c")
        override["html"] = bool(window.override_html_var.get())
    if window.override_disable_filters_var.get():
        override["disable_filters"] = True
    if window.override_disable_blend_var.get():
        override["disable_blend"] = True
    overrides = window.owner._ui_state_overrides
    clean = normalize_override(override)
    if clean:
        overrides[node.path] = clean
    else:
        overrides.pop(node.path, None)
    _invalidate_overrides(window.owner)
    window.refresh()


def _clear_selected_override(window):
    node = _selected_inspector_node(window)
    if node is None:
        return
    window.owner._ui_state_overrides.pop(node.path, None)
    _invalidate_overrides(window.owner)
    window.refresh()


def _clear_all_overrides(window):
    window.owner._ui_state_overrides.clear()
    _invalidate_overrides(window.owner)
    window.refresh()


def _save_preset(window):
    owner = window.owner
    preset = make_preset(owner)
    record = getattr(owner, "_current_movie_record", None)
    name = str(getattr(record, "name", "ui_state") or "ui_state")
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name)
    path = filedialog.asksaveasfilename(
        parent=window,
        title="UI-State-Preset speichern",
        defaultextension=".json",
        initialfile=f"{safe}_preset.json",
        filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
    )
    if not path:
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(preset, handle, ensure_ascii=False, indent=2)
    window.override_status_var.set(f"Preset gespeichert: {Path(path).name}")


def _load_preset(window):
    path = filedialog.askopenfilename(
        parent=window,
        title="UI-State-Preset laden",
        filetypes=[("JSON-Dateien", "*.json"), ("Alle Dateien", "*.*")],
    )
    if not path:
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            preset = normalize_preset(json.load(handle))
    except Exception as exc:
        messagebox.showerror("UI-Preset", str(exc), parent=window)
        return
    current = make_preset(window.owner)
    if preset.get("movie") and current.get("movie") and preset["movie"] != current["movie"]:
        messagebox.showwarning(
            "UI-Preset",
            f"Preset gehört zu {preset['movie']}, aktuell geöffnet ist {current['movie']}. "
            "Die Pfade werden trotzdem geladen.",
            parent=window,
        )
    overrides = window.owner._ui_state_overrides
    overrides.clear()
    overrides.update(preset["overrides"])
    movie = getattr(window.owner, "_current_movie", None)
    if movie is not None:
        frame = max(1, min(int(movie.frame_count), int(preset["root_frame"])))
        window.owner.frame_var.set(frame)
        window.owner.frame_scale.set(frame)
        window.owner._update_frame_text()
    _invalidate_overrides(window.owner)
    window.override_status_var.set(f"Preset geladen: {Path(path).name}")
    window.refresh()


def _install_inspector_controls():
    cls = inspector.StateInspectorWindow
    original_init = cls.__init__
    original_select = cls._on_select
    original_refresh = cls.refresh

    def window_init(self, owner):
        original_init(self, owner)
        self.geometry("1220x930")
        self.override_visibility_var = tk.StringVar(value="Original")
        self.override_frame_var = tk.StringVar(value="0")
        self.override_text_enabled_var = tk.BooleanVar(value=False)
        self.override_html_var = tk.BooleanVar(value=False)
        self.override_disable_filters_var = tk.BooleanVar(value=False)
        self.override_disable_blend_var = tk.BooleanVar(value=False)
        self.override_status_var = tk.StringVar(value="Originalzustand")

        box = ttk.LabelFrame(self, text="Manueller State-Override", padding=8)
        box.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Label(box, text="Sichtbarkeit:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            box, textvariable=self.override_visibility_var,
            values=("Original", "Sichtbar", "Versteckt"),
            state="readonly", width=12,
        ).grid(row=0, column=1, sticky="w", padx=(5, 14))
        ttk.Label(box, text="MovieClip-Frame (0 = Original):").grid(row=0, column=2, sticky="w")
        self.override_frame_spin = ttk.Spinbox(
            box, from_=0, to=100000, textvariable=self.override_frame_var, width=8,
        )
        self.override_frame_spin.grid(row=0, column=3, sticky="w", padx=(5, 14))
        ttk.Checkbutton(
            box, text="Filter deaktivieren", variable=self.override_disable_filters_var,
        ).grid(row=0, column=4, sticky="w", padx=(0, 12))
        ttk.Checkbutton(
            box, text="Blend Mode deaktivieren", variable=self.override_disable_blend_var,
        ).grid(row=0, column=5, sticky="w")

        self.override_text_toggle = ttk.Checkbutton(
            box, text="Text überschreiben", variable=self.override_text_enabled_var,
        )
        self.override_text_toggle.grid(row=1, column=0, sticky="nw", pady=(7, 0))
        self.override_html_toggle = ttk.Checkbutton(
            box, text="als HTML", variable=self.override_html_var,
        )
        self.override_html_toggle.grid(row=1, column=1, sticky="nw", pady=(7, 0))
        self.override_text = tk.Text(box, height=3, wrap="word")
        self.override_text.grid(row=1, column=2, columnspan=4, sticky="ew", pady=(7, 0))
        box.columnconfigure(5, weight=1)

        buttons = ttk.Frame(box)
        buttons.grid(row=2, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Override anwenden", command=self.apply_selected_override).pack(side="left")
        ttk.Button(buttons, text="Ausgewählten löschen", command=self.clear_selected_override).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Alle löschen", command=self.clear_all_overrides).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Preset laden", command=self.load_override_preset).pack(side="right")
        ttk.Button(buttons, text="Preset speichern", command=self.save_override_preset).pack(side="right", padx=(0, 6))
        ttk.Label(box, textvariable=self.override_status_var).grid(
            row=3, column=0, columnspan=6, sticky="w", pady=(6, 0),
        )
        _sync_override_controls(self)

    def on_select(self, event=None):
        result = original_select(self, event)
        _sync_override_controls(self)
        return result

    def refresh(self):
        result = original_refresh(self)
        _sync_override_controls(self)
        return result

    cls.__init__ = window_init
    cls._on_select = on_select
    cls.refresh = refresh
    cls.apply_selected_override = _apply_selected_override
    cls.clear_selected_override = _clear_selected_override
    cls.clear_all_overrides = _clear_all_overrides
    cls.save_override_preset = _save_preset
    cls.load_override_preset = _load_preset
    cls._sync_override_controls = _sync_override_controls


def install():
    global _INSTALLED, _ORIGINAL_BUILD_DISPLAY_LIST
    if _INSTALLED:
        return
    _INSTALLED = True

    _ORIGINAL_BUILD_DISPLAY_LIST = ui_browser.build_display_list

    def build_display_list(tags, target_frame):
        stack = _FORCED_DISPLAY_STACKS.get(id(tags))
        if stack and int(target_frame) == 1:
            return dict(stack[-1])
        return _ORIGINAL_BUILD_DISPLAY_LIST(tags, target_frame)

    ui_browser.build_display_list = build_display_list

    current_draw = ui_browser.UIRenderer._draw_display
    try:
        draw_unmasked = inspect.getclosurevars(current_draw).nonlocals.get("draw_unmasked")
    except Exception:
        draw_unmasked = None
    if not callable(draw_unmasked):
        draw_unmasked = current_draw

    def draw_display(self, canvas, display, parent_matrix, parent_color, stack, level):
        if level > 64:
            self.stats.recursion_skips += 1
            return
        parent_path = getattr(self, "_ui_state_parent_path", "root") or "root"
        active_masks = []
        for depth in sorted(display):
            active_masks = mask_patch.active_masks_at_depth(active_masks, depth)
            item, path, _override = _prepare_renderer_item(
                self, parent_path, depth, display[depth],
            )
            with _render_path(self, path), _force_sprite_frame(self, item, path):
                if not item.visible:
                    continue
                clip_depth = item.clip_depth
                if clip_depth is not None and int(clip_depth) > int(depth):
                    mask_layer = mask_patch._render_mask_source(
                        self, draw_unmasked, canvas, item,
                        parent_matrix, parent_color, stack, level,
                    )
                    alpha = mask_layer.getchannel("A")
                    if active_masks:
                        alpha = mask_patch.intersect_mask_alpha(alpha, active_masks)
                    active_masks.append(mask_patch.ActiveClipMask(int(depth), int(clip_depth), alpha))
                    self.stats.masks_defined = getattr(self.stats, "masks_defined", 0) + 1
                    if alpha.getbbox() is None:
                        self.stats.empty_masks = getattr(self.stats, "empty_masks", 0) + 1
                    continue

                blend_mode = int(getattr(item, "blend_mode", 0) or 0)
                filters = tuple(getattr(item, "filters", ()) or ())
                if active_masks or blend_mode not in (0, 1) or filters:
                    layer = mask_patch._new_layer(canvas)
                    draw_unmasked(
                        self, layer, {depth: item},
                        parent_matrix, parent_color, stack, level,
                    )
                    if filters:
                        layer = mask_patch._apply_item_filters(self, layer, item)
                    if active_masks:
                        mask_patch.apply_clip_masks(layer, active_masks)
                        self.stats.masked_placements = getattr(
                            self.stats, "masked_placements", 0,
                        ) + 1
                    compositor = getattr(self, "_composite_ui_layer", None)
                    if compositor is not None:
                        compositor(canvas, layer, blend_mode)
                    else:
                        canvas.alpha_composite(layer)
                else:
                    draw_unmasked(
                        self, canvas, {depth: item},
                        parent_matrix, parent_color, stack, level,
                    )

    ui_browser.UIRenderer._draw_display = draw_display

    original_draw_text = ui_browser.UIRenderer._draw_edit_text

    def draw_edit_text(self, canvas, definition, matrix, color):
        path = getattr(self, "_ui_current_path", "")
        definition = text_definition_for_path(
            definition, path, _renderer_overrides(self),
        )
        return original_draw_text(self, canvas, definition, matrix, color)

    ui_browser.UIRenderer._draw_edit_text = draw_edit_text

    original_natural_sprite = scale9_patch._render_natural_sprite

    def render_natural_sprite(renderer, definition, character_id, grid, stack, level):
        if _renderer_overrides(renderer):
            scale9_patch._SCALE9_CACHE.clear()
        return original_natural_sprite(renderer, definition, character_id, grid, stack, level)

    scale9_patch._render_natural_sprite = render_natural_sprite

    def inspect_movie_state(movie, frame, max_depth=64):
        return inspect_movie_state_with_overrides(movie, frame, None, max_depth)

    inspector.inspect_movie_state = inspect_movie_state
    ui_browser.inspect_movie_state = inspect_movie_state
    original_format_node = inspector.format_state_node

    def format_state_node(node, resolver=None):
        text = original_format_node(node, resolver)
        override = node.metadata.get("override", {})
        if not override:
            return text
        lines = ["", "Manueller Override:"]
        if "visible" in override:
            lines.append(f"- Sichtbarkeit: {'sichtbar' if override['visible'] else 'versteckt'}")
        if "sprite_frame" in override:
            lines.append(f"- MovieClip-Frame: {override['sprite_frame']}")
        if "text" in override:
            lines.append(f"- Text ersetzt ({'HTML' if override.get('html') else 'Plaintext'})")
        if override.get("disable_filters"):
            lines.append("- Filter deaktiviert")
        if override.get("disable_blend"):
            lines.append("- Blend Mode deaktiviert")
        return text + "\n" + "\n".join(lines)

    inspector.format_state_node = format_state_node

    original_browser_init = ui_browser.UIBrowser.__init__
    original_tree_select = ui_browser.UIBrowser._on_tree_select
    original_format_info = ui_browser.UIBrowser._format_info

    def browser_init(self, *args, **kwargs):
        self._ui_overrides_by_movie = {}
        self._ui_state_overrides = {}
        self._ui_current_override_key = ""
        self._ui_override_revision = 0
        original_browser_init(self, *args, **kwargs)

    def tree_select(self, event=None):
        old_key = getattr(self, "_ui_current_override_key", "")
        if old_key:
            self._ui_overrides_by_movie[old_key] = self._ui_state_overrides
        result = original_tree_select(self, event)
        _attach_browser_overrides(self)
        return result

    def format_info(self, stats):
        text = original_format_info(self, stats)
        count = len(getattr(self, "_ui_state_overrides", {}) or {})
        applied = getattr(stats, "state_overrides_applied", 0)
        if not count and not applied:
            return text
        return text + "\n\nState Overrides:\n" + \
            f"- Gespeicherte Pfade: {count}\n- In diesem Frame angewendet: {applied}"

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = tree_select
    ui_browser.UIBrowser._format_info = format_info

    _install_inspector_controls()

    ui_browser.PRESET_FORMAT = PRESET_FORMAT
    ui_browser.normalize_ui_state_override = normalize_override
    ui_browser.inspect_movie_state_with_overrides = inspect_movie_state_with_overrides
    ui_browser.make_ui_state_preset = make_preset
    ui_browser.normalize_ui_state_preset = normalize_preset
