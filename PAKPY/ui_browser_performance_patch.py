"""Make interactive UI timeline playback usable on large Scaleform movies.

The original playback implementation rebuilt the complete Inspector state tree several
 times for every displayed frame and discarded all Scale9 work on every tick.  This
patch adds immutable display-list caching, a light-weight MovieClip path scan, rendered
frame caching, throttled Inspector refreshes and an adaptive reduced-resolution preview
while scrubbing or playing.  Full-resolution PNG export remains unchanged.
"""
from __future__ import annotations

from collections import OrderedDict
import copy
import time
import tkinter as tk
from tkinter import filedialog, ttk

import ui_browser
import ui_browser_scale9_blend_patch as scale9_patch
import ui_browser_state_inspector_patch as state_inspector
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core
import ui_browser_timeline_inspector_patch as timeline_inspector

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None


_INSTALLED = False
_DISPLAY_CACHE_MAX = 4096
_FRAME_CACHE_BYTES = 160 * 1024 * 1024
_INSPECTOR_REFRESH_SECONDS = 0.25
_AUTO_MIN_SCALE = 0.35
_AUTO_MAX_SCALE = 0.75
_QUALITY_SCALES = {
    "Auto": None,
    "100%": 1.0,
    "75%": 0.75,
    "50%": 0.50,
    "35%": 0.35,
}


class DisplayListCache:
    """LRU cache for immutable SWF tag-list/frame display lists."""

    def __init__(self, max_entries=_DISPLAY_CACHE_MAX):
        self.max_entries = max(1, int(max_entries))
        self._items = OrderedDict()
        self.hits = 0
        self.misses = 0

    def clear(self):
        self._items.clear()
        self.hits = 0
        self.misses = 0

    def get_or_build(self, tags, frame, builder):
        frame = max(1, int(frame))
        key = (id(tags), frame)
        cached = self._items.get(key)
        if cached is not None and cached[0] is tags:
            self.hits += 1
            self._items.move_to_end(key)
            return dict(cached[1])
        self.misses += 1
        display = dict(builder(tags, frame))
        self._items[key] = (tags, display)
        self._items.move_to_end(key)
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
        return dict(display)


class RenderFrameCache:
    """Byte-budgeted LRU cache for already composited Pillow stage images."""

    def __init__(self, max_bytes=_FRAME_CACHE_BYTES):
        self.max_bytes = max(1, int(max_bytes))
        self._items = OrderedDict()
        self.total_bytes = 0
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _size(image):
        return max(1, int(image.width) * int(image.height) * 4)

    def clear(self):
        self._items.clear()
        self.total_bytes = 0
        self.hits = 0
        self.misses = 0

    def get(self, key):
        value = self._items.get(key)
        if value is None:
            self.misses += 1
            return None
        self.hits += 1
        self._items.move_to_end(key)
        image, stats, _size = value
        return image, copy.deepcopy(stats)

    def put(self, key, image, stats):
        old = self._items.pop(key, None)
        if old is not None:
            self.total_bytes -= old[2]
        size = self._size(image)
        self._items[key] = (image, copy.deepcopy(stats), size)
        self.total_bytes += size
        self._items.move_to_end(key)
        while self.total_bytes > self.max_bytes and len(self._items) > 1:
            _key, (_image, _stats, removed) = self._items.popitem(last=False)
            self.total_bytes -= removed


DISPLAY_LIST_CACHE = DisplayListCache()
RENDER_FRAME_CACHE = RenderFrameCache()
_SCALE9_SCOPE_CACHES = OrderedDict()
_SCALE9_SCOPE_MAX = 512


def timeline_state_signature(states):
    result = []
    for path, value in (states or {}).items():
        if not isinstance(value, dict):
            continue
        try:
            frame = int(value.get("frame", 1))
        except Exception:
            frame = 1
        try:
            count = int(value.get("frame_count", 1))
        except Exception:
            count = 1
        result.append((str(path), frame, count, bool(value.get("playing", True))))
    return tuple(sorted(result))


def _visual_timeline_signature(states):
    result = []
    for path, value in (states or {}).items():
        if not isinstance(value, dict):
            continue
        try:
            frame = int(value.get("frame", 1))
        except Exception:
            frame = 1
        result.append((str(path), frame))
    return tuple(sorted(result))


def choose_preview_scale(owner, now=None):
    """Return the requested render scale for the current interaction state."""
    if getattr(owner, "_ui_force_full_quality", False):
        return 1.0
    label = "Auto"
    variable = getattr(owner, "preview_quality_var", None)
    if variable is not None:
        try:
            label = variable.get()
        except Exception:
            label = "Auto"
    explicit = _QUALITY_SCALES.get(label)
    if explicit is not None:
        return explicit
    now = time.monotonic() if now is None else float(now)
    fast = bool(getattr(owner, "_ui_playback_running", False)) or (
        now < float(getattr(owner, "_ui_fast_preview_until", 0.0))
    )
    if not fast:
        return 1.0
    scale = float(getattr(owner, "_ui_adaptive_preview_scale", 0.50))
    return max(_AUTO_MIN_SCALE, min(_AUTO_MAX_SCALE, scale))


def _sync_token(owner, states):
    movie = getattr(owner, "_current_movie", None)
    frame_var = getattr(owner, "frame_var", None)
    root_frame = int(frame_var.get()) if frame_var is not None else 1
    return (
        id(movie),
        root_frame,
        int(getattr(owner, "_ui_override_revision", 0)),
        timeline_state_signature(states),
    )


def fast_sync_timeline_instances(owner):
    """Discover active MovieClips without constructing full Inspector metadata."""
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return ()
    states = getattr(owner, "_ui_timeline_states", {})
    timeline_core.register_movie(movie, states)
    token = _sync_token(owner, states)
    if token == getattr(owner, "_ui_fast_sync_token", None):
        return getattr(owner, "_ui_fast_active_paths", ())

    frame_var = getattr(owner, "frame_var", None)
    root_frame = int(frame_var.get()) if frame_var is not None else 1
    overrides = override_patch.normalize_overrides(
        getattr(owner, "_ui_state_overrides", {})
    )
    builder = override_patch._ORIGINAL_BUILD_DISPLAY_LIST or ui_browser.build_display_list
    active = []

    def walk(display, parent_path, stack, level):
        if level > 64:
            return
        for depth in sorted(display):
            raw_item = display[depth]
            item, path, _override = override_patch.apply_item_override(
                movie, parent_path, depth, raw_item, overrides,
            )
            character_id = getattr(item, "character_id", None)
            definition = movie.definitions.get(character_id) if character_id is not None else None
            if not isinstance(definition, ui_browser.SpriteDef):
                continue
            count = max(1, int(getattr(definition, "frame_count", 1) or 1))
            state = states.get(path)
            if state is None:
                state = timeline_core.normalize_timeline_instance({}, count)
                states[path] = state
            else:
                state.update(timeline_core.normalize_timeline_instance(state, count))
            active.append(path)
            if character_id in stack:
                continue
            frame = timeline_core.timeline_frame_for_path(definition, path, overrides)
            child = builder(definition.tags, frame)
            walk(child, path, stack + (character_id,), level + 1)

    root = builder(movie.root_tags, root_frame)
    walk(root, "root", (), 0)
    movie.ui_timeline_states = states
    result = tuple(active)
    owner._ui_fast_active_paths = result
    owner._ui_fast_sync_token = _sync_token(owner, states)
    return result


def _render_cache_key(renderer, frame, scale):
    movie = renderer.movie
    return (
        id(movie),
        id(renderer.resolver),
        int(frame),
        round(float(scale), 3),
        bool(renderer.show_bounds),
        bool(renderer.show_placeholders),
        int(getattr(movie, "ui_override_revision", 0)),
        _visual_timeline_signature(getattr(movie, "ui_timeline_states", {})),
    )


def _scaled_render(renderer, frame, scale):
    if PILImage is None:
        raise ui_browser.PakError("Pillow fehlt für die schnelle UI-Vorschau")
    movie = renderer.movie
    background = movie.background
    if background[3] == 0:
        background = (28, 31, 38, 255)
    width = max(1, int(round(movie.width * scale)))
    height = max(1, int(round(movie.height * scale)))
    canvas = PILImage.new("RGBA", (width, height), background)
    root = ui_browser.build_display_list(
        movie.root_tags, min(max(1, int(frame)), int(movie.frame_count)),
    )
    stage = ui_browser.Affine(
        scale, 0.0, 0.0, scale,
        -float(movie.stage_bounds[0]) * scale,
        -float(movie.stage_bounds[1]) * scale,
    )
    renderer._ui_render_scale = scale
    renderer._draw_display(canvas, root, stage, ui_browser.IDENTITY_COLOR, set(), 0)
    if getattr(movie, "preview_rotate_180", False):
        transpose = getattr(getattr(PILImage, "Transpose", PILImage), "FLIP_TOP_BOTTOM")
        canvas = canvas.transpose(transpose)
    return canvas, renderer.stats


def _update_adaptive_scale(owner, seconds, cache_hit):
    variable = getattr(owner, "preview_quality_var", None)
    if variable is not None and variable.get() != "Auto":
        return
    if not getattr(owner, "_ui_playback_running", False) and (
        time.monotonic() >= float(getattr(owner, "_ui_fast_preview_until", 0.0))
    ):
        return
    current = float(getattr(owner, "_ui_adaptive_preview_scale", 0.50))
    if cache_hit:
        current = min(_AUTO_MAX_SCALE, current + 0.05)
    elif seconds > 0.45:
        current = max(_AUTO_MIN_SCALE, current - 0.10)
    elif seconds < 0.10:
        current = min(_AUTO_MAX_SCALE, current + 0.05)
    owner._ui_adaptive_preview_scale = current


def _cancel_after(owner, attr):
    after_id = getattr(owner, attr, None)
    if after_id is not None:
        try:
            owner.after_cancel(after_id)
        except Exception:
            pass
    setattr(owner, attr, None)


def schedule_full_quality(owner, delay_ms=400):
    _cancel_after(owner, "_ui_quality_after_id")

    def refine():
        owner._ui_quality_after_id = None
        if getattr(owner, "_closed", False) or getattr(owner, "_ui_playback_running", False):
            return
        owner._ui_fast_preview_until = 0.0
        owner.request_render()

    try:
        owner._ui_quality_after_id = owner.after(max(1, int(delay_ms)), refine)
    except Exception:
        owner._ui_quality_after_id = None


def mark_interactive(owner, delay_ms=400):
    owner._ui_fast_preview_until = time.monotonic() + max(0.05, delay_ms / 1000.0)
    schedule_full_quality(owner, delay_ms)


def clear_performance_caches(owner=None):
    RENDER_FRAME_CACHE.clear()
    DISPLAY_LIST_CACHE.clear()
    _SCALE9_SCOPE_CACHES.clear()
    try:
        scale9_patch._SCALE9_CACHE.clear()
    except Exception:
        pass
    if owner is not None:
        owner._ui_fast_sync_token = None
        owner.request_render()


def _install_display_cache():
    base_builder = override_patch._ORIGINAL_BUILD_DISPLAY_LIST
    if not callable(base_builder) or getattr(base_builder, "_ui_performance_cached", False):
        return

    def cached_builder(tags, target_frame):
        return DISPLAY_LIST_CACHE.get_or_build(tags, target_frame, base_builder)

    cached_builder._ui_performance_cached = True
    cached_builder._ui_uncached_builder = base_builder
    override_patch._ORIGINAL_BUILD_DISPLAY_LIST = cached_builder


def _install_scale9_scoped_cache():
    """Keep Scale9 natural renders per instance frame instead of flushing every tick."""
    original = scale9_patch._render_natural_sprite
    if getattr(original, "_ui_performance_scoped", False):
        return

    def render_natural_sprite(renderer, definition, character_id, grid, stack, level):
        movie = renderer.movie
        path = str(getattr(renderer, "_ui_current_path", "") or "")
        overrides = getattr(movie, "ui_state_overrides", {}) or {}
        manual = timeline_core.manual_frame_override(overrides, path)
        state = (getattr(movie, "ui_timeline_states", {}) or {}).get(path, {})
        try:
            frame = int(manual if manual is not None else state.get("frame", 1))
        except Exception:
            frame = 1
        scope = (
            id(movie), id(renderer.resolver), path, int(character_id), frame,
            int(getattr(movie, "ui_override_revision", 0)),
        )
        scoped = _SCALE9_SCOPE_CACHES.get(scope)
        if scoped is None:
            scoped = {}
            _SCALE9_SCOPE_CACHES[scope] = scoped
        _SCALE9_SCOPE_CACHES.move_to_end(scope)
        while len(_SCALE9_SCOPE_CACHES) > _SCALE9_SCOPE_MAX:
            _SCALE9_SCOPE_CACHES.popitem(last=False)
        previous = scale9_patch._SCALE9_CACHE
        scale9_patch._SCALE9_CACHE = scoped
        try:
            return original(renderer, definition, character_id, grid, stack, level)
        finally:
            scale9_patch._SCALE9_CACHE = previous

    render_natural_sprite._ui_performance_scoped = True
    scale9_patch._render_natural_sprite = render_natural_sprite


def _install_renderer_cache():
    original_render = ui_browser.UIRenderer.render

    def render(renderer, frame):
        scale = max(0.25, min(1.0, float(
            getattr(renderer.movie, "ui_preview_render_scale", 1.0)
        )))
        key = _render_cache_key(renderer, frame, scale)
        cached = RENDER_FRAME_CACHE.get(key)
        if cached is not None:
            image, stats = cached
            renderer.stats = stats
            renderer.stats.render_cache_hit = True
            renderer.movie.ui_last_render_cache_hit = True
            return image, renderer.stats
        if scale >= 0.999:
            image, stats = original_render(renderer, frame)
        else:
            image, stats = _scaled_render(renderer, frame, scale)
        stats.render_cache_hit = False
        stats.preview_render_scale = scale
        renderer.movie.ui_last_render_cache_hit = False
        RENDER_FRAME_CACHE.put(key, image, stats)
        return image, stats

    ui_browser.UIRenderer.render = render


def _install_inspector_throttle():
    cls = state_inspector.StateInspectorWindow
    original_refresh = cls.refresh

    def refresh(window):
        owner = window.owner
        if not getattr(owner, "_ui_playback_running", False):
            window._ui_perf_last_refresh = time.monotonic()
            return original_refresh(window)
        now = time.monotonic()
        last = float(getattr(window, "_ui_perf_last_refresh", 0.0))
        remaining = _INSPECTOR_REFRESH_SECONDS - (now - last)
        if remaining <= 0.0:
            window._ui_perf_last_refresh = now
            return original_refresh(window)
        if getattr(window, "_ui_perf_refresh_after", None) is None:
            def deferred():
                window._ui_perf_refresh_after = None
                try:
                    if window.winfo_exists():
                        window._ui_perf_last_refresh = time.monotonic()
                        original_refresh(window)
                except Exception:
                    pass
            try:
                window._ui_perf_refresh_after = window.after(
                    max(1, int(remaining * 1000.0)), deferred,
                )
            except Exception:
                window._ui_perf_refresh_after = None
        return None

    cls.refresh = refresh


def _install_playback_hooks():
    original_play = timeline_browser.play
    original_pause = timeline_browser.pause
    original_step = timeline_browser.step
    original_jump = timeline_browser.jump_root_label

    def play(owner):
        owner._ui_fast_preview_until = float("inf")
        return original_play(owner)

    def pause(owner):
        result = original_pause(owner)
        if not getattr(owner, "_ui_perf_step_in_progress", False):
            owner._ui_fast_preview_until = 0.0
            owner.request_render()
        return result

    def step(owner, delta):
        owner._ui_perf_step_in_progress = True
        mark_interactive(owner)
        try:
            return original_step(owner, delta)
        finally:
            owner._ui_perf_step_in_progress = False
            schedule_full_quality(owner)

    def jump_root_label(owner):
        owner._ui_perf_step_in_progress = True
        mark_interactive(owner)
        try:
            return original_jump(owner)
        finally:
            owner._ui_perf_step_in_progress = False
            schedule_full_quality(owner)

    timeline_browser.play = play
    timeline_browser.pause = pause
    timeline_browser.step = step
    timeline_browser.jump_root_label = jump_root_label
    ui_browser.UIBrowser.play_ui_timelines = play
    ui_browser.UIBrowser.pause_ui_timelines = pause
    ui_browser.UIBrowser.step_ui_timelines = step

    for name in ("change_frame", "reset_selected", "jump_selected_label"):
        original = getattr(timeline_inspector, name, None)
        if not callable(original):
            continue

        def wrapped(window, *args, _original=original, **kwargs):
            mark_interactive(window.owner)
            result = _original(window, *args, **kwargs)
            schedule_full_quality(window.owner)
            return result

        setattr(timeline_inspector, name, wrapped)


def _install_browser_hooks():
    original_init = ui_browser.UIBrowser.__init__
    original_render = ui_browser.UIBrowser._render
    original_draw_scaled = ui_browser.UIBrowser._draw_scaled
    original_on_frame_scale = ui_browser.UIBrowser._on_frame_scale
    original_step_frame = ui_browser.UIBrowser._step_frame
    original_close = ui_browser.UIBrowser.close
    original_format_info = ui_browser.UIBrowser._format_info

    def browser_init(owner, *args, **kwargs):
        owner._ui_adaptive_preview_scale = 0.50
        owner._ui_fast_preview_until = 0.0
        owner._ui_quality_after_id = None
        owner._ui_fast_sync_token = None
        owner._ui_fast_active_paths = ()
        owner._ui_last_render_seconds = 0.0
        owner._ui_force_full_quality = False
        original_init(owner, *args, **kwargs)
        owner.preview_quality_var = tk.StringVar(value="Auto")
        bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
        bar.pack(fill="x")
        ttk.Label(bar, text="Vorschauqualität:").pack(side="left")
        combo = ttk.Combobox(
            bar, textvariable=owner.preview_quality_var,
            values=tuple(_QUALITY_SCALES), state="readonly", width=7,
        )
        combo.pack(side="left", padx=(5, 10))
        owner.preview_quality_var.trace_add("write", lambda *_args: owner.request_render())
        ttk.Button(
            bar, text="Render-Cache leeren",
            command=lambda: clear_performance_caches(owner),
        ).pack(side="left")
        ttk.Label(
            bar,
            text="Auto: schnelle Wiedergabe, volle Qualität nach Pause",
        ).pack(side="left", padx=(10, 0))

    def browser_render(owner):
        movie = getattr(owner, "_current_movie", None)
        if movie is not None:
            movie.ui_preview_render_scale = choose_preview_scale(owner)
        started = time.perf_counter()
        result = original_render(owner)
        elapsed = time.perf_counter() - started
        owner._ui_last_render_seconds = elapsed
        cache_hit = bool(getattr(movie, "ui_last_render_cache_hit", False)) if movie is not None else False
        owner._ui_last_render_cache_hit = cache_hit
        _update_adaptive_scale(owner, elapsed, cache_hit)
        return result

    def draw_scaled(owner, event=None):
        scale = float(getattr(owner, "_ui_current_render_scale", 1.0))
        movie = getattr(owner, "_current_movie", None)
        if movie is not None:
            scale = float(getattr(movie, "ui_preview_render_scale", scale))
        if scale >= 0.999 or owner._stage_image is None:
            return original_draw_scaled(owner, event)
        owner.canvas.delete("all")
        canvas_width = max(1, owner.canvas.winfo_width())
        canvas_height = max(1, owner.canvas.winfo_height())
        margin = 18
        draw_width, draw_height = owner._fit_size(
            owner._stage_image.width, owner._stage_image.height,
            max(1, canvas_width - margin * 2), max(1, canvas_height - margin * 2),
        )
        resampling = getattr(getattr(ui_browser.Image, "Resampling", ui_browser.Image), "BILINEAR")
        owner._display_image = owner._stage_image.resize((draw_width, draw_height), resampling)
        owner._photo = ui_browser.ImageTk.PhotoImage(owner._display_image)
        x = (canvas_width - draw_width) // 2
        y = (canvas_height - draw_height) // 2
        owner.canvas.create_rectangle(
            x - 1, y - 1, x + draw_width + 1, y + draw_height + 1,
            outline="#8090a0",
        )
        owner.canvas.create_image(x, y, anchor="nw", image=owner._photo)

    def on_frame_scale(owner, value):
        if not getattr(owner, "_ui_playback_running", False):
            mark_interactive(owner)
        return original_on_frame_scale(owner, value)

    def step_frame(owner, delta):
        mark_interactive(owner)
        result = original_step_frame(owner, delta)
        schedule_full_quality(owner)
        return result

    def save_png(owner):
        if owner._current_movie is None or owner._current_movie_record is None:
            return
        safe = "".join(
            ch if ch.isalnum() or ch in ("-", "_", ".") else "_"
            for ch in owner._current_movie_record.name
        )
        path = filedialog.asksaveasfilename(
            parent=owner,
            title="UI-Frame als PNG speichern",
            defaultextension=".png",
            initialfile=f"{safe}_frame_{owner.frame_var.get():03d}.png",
            filetypes=[("PNG-Dateien", "*.png"), ("Alle Dateien", "*.*")],
        )
        if not path:
            return
        movie = owner._current_movie
        old_scale = float(getattr(movie, "ui_preview_render_scale", 1.0))
        owner._ui_force_full_quality = True
        movie.ui_preview_render_scale = 1.0
        try:
            renderer = ui_browser.UIRenderer(
                movie, owner._current_resolver,
                owner.show_bounds_var.get(), owner.show_placeholders_var.get(),
            )
            image, _stats = renderer.render(owner.frame_var.get())
            image.save(path, "PNG")
        finally:
            owner._ui_force_full_quality = False
            movie.ui_preview_render_scale = old_scale

    def close(owner):
        _cancel_after(owner, "_ui_quality_after_id")
        return original_close(owner)

    def format_info(owner, stats):
        text = original_format_info(owner, stats)
        movie = getattr(owner, "_current_movie", None)
        if movie is None:
            return text
        scale = float(getattr(movie, "ui_preview_render_scale", 1.0))
        return text + "\n\nPerformance:\n" + (
            f"- Renderzeit: {float(getattr(owner, '_ui_last_render_seconds', 0.0)) * 1000.0:.1f} ms\n"
            f"- Vorschauauflösung: {scale * 100.0:.0f}%\n"
            f"- Frame-Cache: {'Treffer' if getattr(stats, 'render_cache_hit', False) else 'neu gerendert'}\n"
            f"- Display-List-Cache: {DISPLAY_LIST_CACHE.hits} Treffer / {DISPLAY_LIST_CACHE.misses} neu"
        )

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._render = browser_render
    ui_browser.UIBrowser._draw_scaled = draw_scaled
    ui_browser.UIBrowser._on_frame_scale = on_frame_scale
    ui_browser.UIBrowser._step_frame = step_frame
    ui_browser.UIBrowser.save_png = save_png
    ui_browser.UIBrowser.close = close
    ui_browser.UIBrowser._format_info = format_info


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    if PILImage is None:
        return
    _install_display_cache()
    timeline_core.sync_timeline_instances = fast_sync_timeline_instances
    _install_scale9_scoped_cache()
    _install_renderer_cache()
    _install_inspector_throttle()
    _install_playback_hooks()
    _install_browser_hooks()

    ui_browser.clear_ui_performance_caches = clear_performance_caches
    ui_browser.ui_preview_scale = choose_preview_scale
    ui_browser.fast_sync_ui_timeline_instances = fast_sync_timeline_instances
