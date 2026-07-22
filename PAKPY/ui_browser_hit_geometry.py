"""Traverse visible display lists and collect clipped hit geometry."""
from __future__ import annotations

from dataclasses import replace

import ui_browser
import ui_browser_avm2_dynamic_patch as dynamic
import ui_browser_classic_button as classic
import ui_browser_hit_geometry_base as base
import ui_browser_shape_patch as shape_patch
import ui_browser_state_override_patch as overrides_patch

_MAX_GEOMETRIES = 20_000
_runtime_values = base._runtime_values
_property = base._property
_reference_path = base._reference_path
_rect_geometry = base._rect_geometry
_alpha_geometry = base._alpha_geometry
_scroll_clip = base._scroll_clip
_union_bounds = base._union_bounds


class GeometryCollector:
    def __init__(self, renderer, frame):
        self.renderer = renderer
        self.movie = renderer.movie
        self.frame = max(1, min(int(frame), int(getattr(self.movie, "frame_count", 1) or 1)))
        self.overrides = overrides_patch.normalize_overrides(
            getattr(self.movie, "ui_state_overrides", {}) or {},
        )
        self.geometries = []
        self.meta = {}
        self.mask_count = 0
        self.scroll_paths = set()
        self.alpha_count = 0
        self.truncated = False

    def add(self, geometry, name="", enabled=True, tab_enabled=False, dynamic_flag=False):
        if len(self.geometries) >= _MAX_GEOMETRIES:
            self.truncated = True
            return
        self.geometries.append(geometry)
        self.meta[str(geometry.path)] = {
            "name": str(name or str(geometry.path).rsplit(":", 1)[-1]),
            "enabled": bool(enabled), "tab_enabled": bool(tab_enabled),
            "dynamic": bool(dynamic_flag),
        }
        if geometry.alpha is not None:
            self.alpha_count += 1

    def _leaf(self, definition, matrix, path, clips, character_id=None, name="",
              enabled=True, tab_enabled=False, dynamic_flag=False):
        vector_type = getattr(ui_browser, "VectorShapeDef", ())
        if vector_type and isinstance(definition, vector_type):
            try:
                image, origin = shape_patch._cached_shape(definition)
                alpha = image.getchannel("A")
                bounds = (
                    float(origin[0]), float(origin[1]),
                    float(origin[0] + image.width), float(origin[1] + image.height),
                )
                self.add(_alpha_geometry(
                    path, matrix, bounds, alpha, origin, clips, "vector-alpha", character_id,
                ), name, enabled, tab_enabled, dynamic_flag)
                return
            except Exception:
                pass
        if isinstance(definition, ui_browser.EditTextDef):
            bounds = tuple(definition.bounds)
            self.add(_rect_geometry(path, matrix, bounds, clips, "text", character_id),
                     name, enabled, tab_enabled, dynamic_flag)
            return
        if isinstance(definition, ui_browser.ShapeDef):
            bounds = tuple(definition.bounds)
            self.add(_rect_geometry(path, matrix, bounds, clips, "shape-bounds", character_id),
                     name, enabled, tab_enabled, dynamic_flag)
            return
        bounds = getattr(definition, "bounds", None)
        if bounds is not None:
            self.add(_rect_geometry(path, matrix, tuple(bounds), clips, "bounds", character_id),
                     name, enabled, tab_enabled, dynamic_flag)

    def _external(self, item, matrix, path, clips, name, enabled, tab_enabled):
        try:
            lookup = self.renderer.resolver.get(item.class_name)
            image = lookup.image
            if image is None:
                return
            alpha = image.getchannel("A")
            bounds = (0.0, 0.0, float(image.width), float(image.height))
            self.add(_alpha_geometry(path, matrix, bounds, alpha, (0.0, 0.0), clips,
                                     "texture-alpha", None),
                     name or item.class_name, enabled, tab_enabled, False)
        except Exception:
            return

    def _classic(self, definition, matrix, path, clips, stack, sink):
        records = definition.hit_records or definition.records
        for record in records:
            child = self.movie.definitions.get(record.character_id)
            if child is None:
                continue
            child_matrix = matrix.then(record.matrix)
            self._definition(child, child_matrix, path, clips,
                             stack | {definition.character_id}, sink, owner_path=path)

    def _frame_for(self, definition, path):
        try:
            return int(overrides_patch.sprite_frame_for_path(definition, path, self.overrides))
        except Exception:
            return 1

    def _definition(self, definition, matrix, path, clips, stack, sink,
                    owner_path=None, name="", enabled=True, tab_enabled=False,
                    dynamic_flag=False):
        output_path = owner_path or path
        object_clips = _scroll_clip(self.movie, path, matrix, clips)
        if len(object_clips) > len(clips):
            self.scroll_paths.add(str(path))
        if isinstance(definition, classic.ClassicButtonDef):
            self._classic(definition, matrix, output_path, object_clips, stack, sink)
            return
        if isinstance(definition, ui_browser.SpriteDef):
            if definition.character_id in stack:
                return
            frame = 1 if owner_path else self._frame_for(definition, path)
            display = ui_browser.build_display_list(definition.tags, frame)
            self._display(display, matrix, path, object_clips,
                          stack | {definition.character_id}, sink, owner_path)
            return
        before = len(self.geometries)
        self._leaf(definition, matrix, output_path, object_clips,
                   getattr(definition, "character_id", None), name, enabled,
                   tab_enabled, dynamic_flag)
        if sink is not self.geometries and len(self.geometries) > before:
            sink.extend(self.geometries[before:])
            del self.geometries[before:]

    def _mask_geometry(self, item, definition, matrix, path, clips, stack):
        temp = []
        if getattr(item, "class_name", ""):
            before = len(self.geometries)
            self._external(item, matrix, path, clips, getattr(item, "name", ""), True, False)
            temp.extend(self.geometries[before:])
            del self.geometries[before:]
        elif definition is not None:
            self._definition(definition, matrix, path, clips, stack, temp, owner_path=path)
        return tuple(temp)

    def _display(self, display, parent_matrix, parent_path, inherited_clips, stack, sink=None,
                 owner_path=None):
        sink = self.geometries if sink is None else sink
        active_masks = []
        for depth in sorted(display):
            active_masks = [value for value in active_masks if int(depth) <= value[0]]
            raw_item = display[depth]
            try:
                item, path, _override = overrides_patch.apply_item_override(
                    self.movie, parent_path, depth, raw_item, self.overrides,
                )
            except Exception:
                item = raw_item
                label = getattr(item, "name", "") or f"depth {depth}"
                path = f"{parent_path}/{int(depth)}:{label}"
            if not bool(getattr(item, "visible", True)):
                continue
            matrix = parent_matrix.then(getattr(item, "matrix", ui_browser.Affine()))
            character_id = getattr(item, "character_id", None)
            definition = self.movie.definitions.get(character_id) if character_id is not None else None
            clips = tuple(inherited_clips) + tuple(value[1] for value in active_masks)
            clip_depth = getattr(item, "clip_depth", None)
            if clip_depth is not None and int(clip_depth) > int(depth):
                geoms = self._mask_geometry(item, definition, matrix, path, clips, stack)
                if geoms:
                    active_masks.append((int(clip_depth), classic.HitClip(geoms, "clipDepth")))
                    self.mask_count += 1
                continue
            name = str(getattr(item, "name", "") or path.rsplit(":", 1)[-1])
            enabled = bool(getattr(item, "_ui_enabled", True) and getattr(item, "_ui_mouse_enabled", True))
            tab_enabled = bool(getattr(item, "_ui_tab_enabled", False))
            output_path = owner_path or path
            if getattr(item, "class_name", ""):
                before = len(self.geometries)
                self._external(item, matrix, output_path, clips, name, enabled, tab_enabled)
                if sink is not self.geometries and len(self.geometries) > before:
                    sink.extend(self.geometries[before:])
                    del self.geometries[before:]
            elif definition is not None:
                self._definition(definition, matrix, path, clips, stack, sink,
                                 owner_path, name, enabled, tab_enabled, False)
        if owner_path is None:
            self._dynamic_children(parent_path, parent_matrix, inherited_clips, stack, sink)

    def _dynamic_children(self, parent_path, parent_matrix, clips, stack, sink):
        try:
            values = dynamic._children(self.movie, parent_path)
        except Exception:
            values = ()
        for obj in values:
            if not bool(getattr(obj, "visible", True)):
                continue
            matrix = parent_matrix.then(dynamic._matrix(
                obj.x, obj.y, obj.scale_x, obj.scale_y, obj.rotation,
            ))
            object_clips = _scroll_clip(self.movie, obj.path, matrix, clips)
            if len(object_clips) > len(clips):
                self.scroll_paths.add(str(obj.path))
            definition = getattr(obj, "definition", None)
            if isinstance(definition, ui_browser.SpriteDef):
                frame = max(1, min(int(getattr(definition, "frame_count", 1) or 1),
                                   int(getattr(obj, "current_frame", 1) or 1)))
                display = ui_browser.build_display_list(definition.tags, frame)
                self._display(display, matrix, obj.path, object_clips,
                              stack | {id(obj)}, sink)
            elif definition is not None:
                self._definition(definition, matrix, obj.path, object_clips, stack, sink,
                                 name=obj.name, enabled=obj.enabled and obj.mouse_enabled,
                                 tab_enabled=obj.tab_enabled, dynamic_flag=True)
                self._dynamic_children(obj.path, matrix, object_clips, stack | {id(obj)}, sink)
            else:
                bounds = (0.0, 0.0, max(1.0, float(obj.width)), max(1.0, float(obj.height)))
                before = len(self.geometries)
                self.add(_rect_geometry(obj.path, matrix, bounds, object_clips,
                                        "dynamic-bounds"), obj.name,
                         obj.enabled and obj.mouse_enabled, obj.tab_enabled, True)
                if sink is not self.geometries and len(self.geometries) > before:
                    sink.extend(self.geometries[before:])
                    del self.geometries[before:]
                self._dynamic_children(obj.path, matrix, object_clips, stack | {id(obj)}, sink)

    def collect(self):
        stage = ui_browser.Affine(
            1.0, 0.0, 0.0, 1.0,
            -float(self.movie.stage_bounds[0]), -float(self.movie.stage_bounds[1]),
        )
        root = ui_browser.build_display_list(self.movie.root_tags, self.frame)
        self._display(root, stage, "root", (), set())
        return self.geometries


def _ancestor_paths(path):
    result = []
    current = str(path or "")
    while current:
        result.append(current)
        if current == "root" or "/" not in current:
            break
        current = current.rsplit("/", 1)[0]
    return tuple(result)


def _apply_runtime_masks(movie, mapping):
    original = {path: tuple(values) for path, values in mapping.items()}
    result = {}
    for path, values in original.items():
        clips = []
        for ancestor in _ancestor_paths(path):
            target = _reference_path(_property(movie, ancestor, "mask"))
            if target and target != path and original.get(target):
                clips.append(classic.HitClip(original[target], f"mask:{target}"))
        result[path] = tuple(
            replace(value, clips=tuple(value.clips) + tuple(clips)) if clips else value
            for value in values
        )
    return result


def _apply_hit_areas(movie, mapping, order):
    result = dict(mapping)
    for path in tuple(result):
        target = _reference_path(_property(movie, path, "hitArea"))
        if not target or target == path or not result.get(target):
            continue
        result[path] = tuple(replace(value, path=path, kind=f"hitArea:{value.kind}")
                             for value in result[target])
        if path not in order:
            order.append(path)
    return result
