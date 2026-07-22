"""Bundled UI-state profiles and automatic game-value mocks for the UI Browser.

The patch keeps manual Inspector overrides authoritative.  Game mocks are a separate,
preview-only layer which is matched to EditText fields from variable names, instance
names and stable display-list paths.  Profiles and mock values are persisted in the
existing JSON state-preset format without modifying GFX/GFXL/TXTR/MSBT data.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import json
import re
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ui_browser
import ui_browser_state_inspector_patch as state_inspector
import ui_browser_state_override_patch as override_patch
import ui_browser_timeline_browser_patch as timeline_browser
import ui_browser_timeline_core as timeline_core
import ui_browser_timeline_inspector_patch as timeline_inspector


_INSTALLED = False
_BASE_TEXT_DEFINITION = None
_BASE_INSPECT_MOVIE_STATE = None
_BASE_FORMAT_STATE_NODE = None
_BASE_MAKE_PRESET = None
_BASE_NORMALIZE_PRESET = None
_BASE_RENDER = None


@dataclass(frozen=True)
class MockField:
    key: str
    label: str
    kind: str
    default: object
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class GameStateProfile:
    profile_id: str
    name: str
    description: str
    movie_patterns: tuple[str, ...]
    roles: tuple[str, ...]
    values: dict
    root_frames: tuple[tuple[str, int], ...] = ()
    root_label_patterns: tuple[str, ...] = ()
    playback_running: bool = False
    speed: float = 1.0


MOCK_FIELDS = (
    MockField("players", "Spieler", "int", 1, (
        "playercount", "numplayers", "numberofplayers", "players", "playerstext", "playernum",
    )),
    MockField("lives", "Leben", "int", 5, (
        "lifecount", "livescount", "playerlives", "livestext", "lives", "ballooncount", "balloons",
    )),
    MockField("banana_coins", "Banana Coins", "int", 23, (
        "bananacoincount", "bananacoins", "bananacoin", "coincount", "coinstext", "coins",
    )),
    MockField("puzzle_pieces", "Puzzle Pieces", "int", 4, (
        "puzzlepiececount", "puzzlepieces", "puzzlepiece", "puzzlecount", "puzzlestext", "puzzles",
    )),
    MockField("puzzle_total", "Puzzle Pieces gesamt", "int", 9, (
        "puzzletotal", "puzzlemax", "totalpuzzles", "maxpuzzles", "puzzlepiecestotal",
    )),
    MockField("timer_seconds", "Timer (Sekunden)", "float", 95.42, (
        "countdowntime", "remainingtime", "elapsedtime", "timervalue", "timertext", "timer", "timetext", "time",
    )),
    MockField("score", "Punkte", "int", 12500, (
        "totalscore", "scorevalue", "scoretext", "score", "pointstext", "points",
    )),
    MockField("level_name", "Levelname", "str", "Jungle Hijinxs", (
        "leveltitle", "levelname", "worldtitle", "worldname", "stagetitle", "stagename",
    )),
    MockField("bananas", "Bananen", "int", 73, (
        "bananacount", "bananastext", "bananas", "banana",
    )),
    MockField("kong_letters", "KONG-Buchstaben", "str", "KONG", (
        "kongletters", "kongletter", "lettercount", "letterstext",
    )),
    MockField("progress_percent", "Fortschritt (%)", "int", 42, (
        "progresspercent", "completionpercent", "completion", "percenttext", "progress", "percent",
    )),
)
MOCK_FIELD_BY_KEY = {field.key: field for field in MOCK_FIELDS}
DEFAULT_MOCK_VALUES = {field.key: field.default for field in MOCK_FIELDS}


PROFILES = (
    GameStateProfile(
        "hud_1p", "HUD – 1 Spieler", "Standard-HUD mit typischen Sammel- und Punktwerten.",
        ("hud",),
        ("players", "lives", "banana_coins", "puzzle_pieces", "timer_seconds", "score", "bananas", "kong_letters"),
        {"players": 1, "lives": 5, "banana_coins": 23, "puzzle_pieces": 4,
         "timer_seconds": 95.42, "score": 12500, "bananas": 73, "kong_letters": "KONG"},
    ),
    GameStateProfile(
        "hud_2p", "HUD – 2 Spieler", "Zwei-Spieler-HUD mit erhöhten Leben und Testwerten.",
        ("hud", "character"),
        ("players", "lives", "banana_coins", "puzzle_pieces", "timer_seconds", "score", "bananas", "kong_letters"),
        {"players": 2, "lives": 8, "banana_coins": 47, "puzzle_pieces": 6,
         "timer_seconds": 128.17, "score": 28400, "bananas": 91, "kong_letters": "KON"},
    ),
    GameStateProfile(
        "hud_time_attack", "HUD – Time Attack", "Zeitrennen mit laufendem Timer und Punktestand.",
        ("timeattack", "time_attack", "hud"),
        ("timer_seconds", "score", "level_name", "players"),
        {"timer_seconds": 83.42, "score": 35120, "level_name": "Time Attack", "players": 1},
    ),
    GameStateProfile(
        "pause", "Pause – eingefrorener Zustand", "Pausiert Root- und Untertimelines; Werte bleiben analysierbar.",
        ("pause", "menu"),
        ("players", "lives", "banana_coins", "puzzle_pieces", "level_name"),
        {"players": 1, "lives": 5, "banana_coins": 23, "puzzle_pieces": 4,
         "level_name": "Jungle Hijinxs"},
        root_label_patterns=("pause", "paused", "open", "show"),
    ),
    GameStateProfile(
        "options", "Optionen – Hauptseite", "Öffnet im bekannten Options-Film den strukturellen Hauptzustand.",
        ("options",), (), {}, root_frames=(("options", 20),),
        root_label_patterns=("options", "default", "show"),
    ),
    GameStateProfile(
        "frontend", "Frontend – Hauptmenü", "Statischer Frontend-Testzustand mit einem Spieler.",
        ("frontend", "mastershell", "master_shell"),
        ("players", "progress_percent"), {"players": 1, "progress_percent": 42},
        root_label_patterns=("main", "default", "show", "open"),
    ),
    GameStateProfile(
        "shop", "Shop – 99 Banana Coins", "Shop-Zustand mit hohem Banana-Coin-Testwert.",
        ("shop",), ("banana_coins", "lives"), {"banana_coins": 99, "lives": 5},
        root_label_patterns=("shop", "default", "show"),
    ),
    GameStateProfile(
        "character_select", "Charakterwahl – 2 Spieler", "Charakterauswahl mit zwei Spielern.",
        ("character", "select", "playerselect"),
        ("players", "lives"), {"players": 2, "lives": 8},
        root_label_patterns=("select", "default", "show"),
    ),
)
PROFILE_BY_ID = {profile.profile_id: profile for profile in PROFILES}
PROFILE_ID_BY_NAME = {profile.name: profile.profile_id for profile in PROFILES}
PROFILE_NAMES = ("Kein Profil",) + tuple(profile.name for profile in PROFILES)


_GENERIC_TEXT_PARTS = {
    "text", "txt", "base", "stroke", "dropshadow", "shadow", "glow", "hit",
    "input", "field", "label", "value", "display", "mc", "clip", "container",
}


def _split_words(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(value or ""))
    return tuple(part for part in re.split(r"[^A-Za-z0-9]+", value.lower()) if part)


def _compact(value):
    return "".join(_split_words(value))


def _source_score(source, alias):
    words = _split_words(source)
    compact = "".join(words)
    alias_words = _split_words(alias)
    alias_compact = "".join(alias_words)
    if not compact or not alias_compact:
        return 0
    if compact == alias_compact:
        return 140
    if alias_compact in words:
        return 125
    if len(alias_words) > 1:
        joined = " ".join(words)
        if " ".join(alias_words) in joined:
            return 115
    if len(alias_compact) >= 5 and (compact.startswith(alias_compact) or compact.endswith(alias_compact)):
        return 95
    if len(alias_compact) >= 6 and alias_compact in compact:
        return 75
    return 0


def match_text_role(path, metadata=None, definition=None):
    """Return the best mock key for an EditText field, or ``None``.

    Matching deliberately favours exact variable/instance names over broad path
    substrings.  This lets sibling base/stroke/shadow fields inherit the semantic name
    of their parent without turning generic fields such as ``text_base`` into mocks.
    """
    metadata = metadata or {}
    sources = []
    for value in (
        metadata.get("variable_name", ""), metadata.get("instance_name", ""),
        metadata.get("label", ""), getattr(definition, "variable_name", ""),
    ):
        if value:
            sources.append((str(value), 25))
    segments = [part.split(":", 1)[-1] for part in str(path or "").split("/") if part]
    if segments:
        sources.append((segments[-1], 20))
        for segment in reversed(segments[-4:-1]):
            sources.append((segment, 5))
    best = (0, None)
    for field_index, field in enumerate(MOCK_FIELDS):
        for alias in field.aliases:
            for source, bonus in sources:
                score = _source_score(source, alias)
                if score:
                    compact_source = _compact(source)
                    if compact_source in _GENERIC_TEXT_PARTS:
                        continue
                    candidate = score + bonus - field_index * 0.001
                    if candidate > best[0]:
                        best = (candidate, field.key)
    return best[1] if best[0] >= 80 else None


def coerce_mock_value(key, value):
    field = MOCK_FIELD_BY_KEY[key]
    if field.kind == "str":
        return str(value or "")
    if field.kind == "int":
        try:
            return int(float(str(value).strip()))
        except Exception:
            return int(field.default)
    if field.kind == "float":
        text = str(value).strip()
        if ":" in text:
            try:
                minute_text, second_text = text.split(":", 1)
                return float(minute_text) * 60.0 + float(second_text)
            except Exception:
                return float(field.default)
        try:
            return float(text)
        except Exception:
            return float(field.default)
    return value


def normalize_mock_values(value):
    value = value if isinstance(value, dict) else {}
    result = dict(DEFAULT_MOCK_VALUES)
    for key in result:
        if key in value:
            result[key] = coerce_mock_value(key, value[key])
    return result


def normalize_game_state(value):
    value = value if isinstance(value, dict) else {}
    profile_id = str(value.get("profile", "") or "")
    if profile_id not in PROFILE_BY_ID:
        profile_id = ""
    raw_roles = value.get("roles", ())
    roles = []
    if isinstance(raw_roles, (list, tuple, set)):
        for role in raw_roles:
            role = str(role)
            if role in MOCK_FIELD_BY_KEY and role not in roles:
                roles.append(role)
    if not roles and profile_id:
        roles = list(PROFILE_BY_ID[profile_id].roles)
    return {
        "enabled": bool(value.get("enabled", bool(roles))),
        "profile": profile_id,
        "roles": roles,
        "values": normalize_mock_values(value.get("values", {})),
    }


def _timer_text(value):
    seconds = max(0.0, float(value))
    minutes = int(seconds // 60.0)
    whole = int(seconds) % 60
    centiseconds = int(round((seconds - int(seconds)) * 100.0))
    if centiseconds >= 100:
        whole += 1
        centiseconds = 0
        if whole >= 60:
            minutes += 1
            whole = 0
    return f"{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def format_mock_value(key, value, metadata=None):
    if key == "timer_seconds":
        return _timer_text(value)
    if key == "progress_percent":
        return f"{int(value)}%"
    if key in ("players", "lives", "banana_coins", "puzzle_pieces", "puzzle_total", "score", "bananas"):
        return str(int(value))
    return str(value)


def movie_display_name(owner):
    record = getattr(owner, "_current_movie_record", None)
    return str(getattr(record, "name", "") or "")


def profile_for_name(name):
    return PROFILE_BY_ID.get(PROFILE_ID_BY_NAME.get(str(name or ""), ""))


def profile_matches_movie(profile, movie_name):
    compact_name = _compact(movie_name)
    return not profile.movie_patterns or any(_compact(pattern) in compact_name for pattern in profile.movie_patterns)


def profile_root_frame(profile, movie, movie_name):
    compact_name = _compact(movie_name)
    for pattern, frame in profile.root_frames:
        if _compact(pattern) in compact_name:
            return max(1, min(int(getattr(movie, "frame_count", 1) or 1), int(frame)))
    labels = dict(getattr(movie, "labels", {}) or {})
    for pattern in profile.root_label_patterns:
        needle = _compact(pattern)
        for label, frame in sorted(labels.items(), key=lambda item: item[1]):
            if needle and needle in _compact(label):
                return max(1, min(int(getattr(movie, "frame_count", 1) or 1), int(frame)))
    return None


def _game_state_key(owner):
    helper = getattr(override_patch, "_browser_movie_key", None)
    return helper(owner) if callable(helper) else ""


def register_movie(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return
    movie.ui_game_mock_enabled = bool(getattr(owner, "_ui_game_mock_enabled", False))
    movie.ui_game_mock_roles = tuple(getattr(owner, "_ui_game_mock_roles", ()))
    movie.ui_game_mock_values = getattr(owner, "_ui_game_mock_values", {})
    movie.ui_game_profile_id = str(getattr(owner, "_ui_active_game_profile_id", "") or "")
    for definition in getattr(movie, "definitions", {}).values():
        if isinstance(definition, ui_browser.EditTextDef):
            definition._ui_game_state_movie = movie


def save_current_game_state(owner):
    key = getattr(owner, "_ui_current_game_state_key", "")
    if not key:
        return
    owner._ui_game_state_by_movie[key] = {
        "enabled": bool(getattr(owner, "_ui_game_mock_enabled", False)),
        "profile": str(getattr(owner, "_ui_active_game_profile_id", "") or ""),
        "roles": list(getattr(owner, "_ui_game_mock_roles", ())),
        "values": dict(getattr(owner, "_ui_game_mock_values", DEFAULT_MOCK_VALUES)),
    }


def attach_game_state(owner):
    key = _game_state_key(owner)
    owner._ui_current_game_state_key = key
    stored = normalize_game_state(owner._ui_game_state_by_movie.get(key, {})) if key else normalize_game_state({})
    owner._ui_game_mock_enabled = stored["enabled"]
    owner._ui_active_game_profile_id = stored["profile"]
    owner._ui_game_mock_roles = tuple(stored["roles"])
    owner._ui_game_mock_values = dict(stored["values"])
    register_movie(owner)
    update_profile_controls(owner)


def current_game_state(owner):
    return {
        "enabled": bool(getattr(owner, "_ui_game_mock_enabled", False)),
        "profile": str(getattr(owner, "_ui_active_game_profile_id", "") or ""),
        "roles": list(getattr(owner, "_ui_game_mock_roles", ())),
        "values": dict(getattr(owner, "_ui_game_mock_values", DEFAULT_MOCK_VALUES)),
    }


def touch_game_state(owner, refresh_inspector=True):
    register_movie(owner)
    save_current_game_state(owner)
    invalidator = getattr(override_patch, "_invalidate_overrides", None)
    if callable(invalidator):
        invalidator(owner)
    else:
        owner.request_render()
    update_profile_controls(owner)
    if refresh_inspector:
        window = getattr(owner, "_state_inspector", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.refresh()
            except Exception:
                pass


def apply_profile(owner, profile_id):
    profile = PROFILE_BY_ID.get(str(profile_id or ""))
    if profile is None:
        owner._ui_active_game_profile_id = ""
        owner._ui_game_mock_enabled = False
        owner._ui_game_mock_roles = ()
        touch_game_state(owner)
        return None
    values = dict(DEFAULT_MOCK_VALUES)
    for key, value in profile.values.items():
        if key in MOCK_FIELD_BY_KEY:
            values[key] = coerce_mock_value(key, value)
    owner._ui_active_game_profile_id = profile.profile_id
    owner._ui_game_mock_enabled = bool(profile.roles)
    owner._ui_game_mock_roles = tuple(profile.roles)
    owner._ui_game_mock_values = values
    movie = getattr(owner, "_current_movie", None)
    if movie is not None:
        frame = profile_root_frame(profile, movie, movie_display_name(owner))
        if frame is not None:
            timeline_core.set_root_frame(owner, frame)
        if hasattr(owner, "_ui_playback_speed"):
            owner._ui_playback_speed = float(profile.speed)
            variable = getattr(owner, "timeline_speed_var", None)
            if variable is not None:
                speed_label = getattr(timeline_browser, "speed_label", None)
                if callable(speed_label):
                    variable.set(speed_label(profile.speed))
        if profile.playback_running:
            timeline_browser.play(owner)
        else:
            timeline_browser.pause(owner)
    touch_game_state(owner)
    return profile


def disable_game_mocks(owner):
    owner._ui_game_mock_enabled = False
    touch_game_state(owner)


def _mock_for_definition(definition, path, overrides):
    manual = override_patch.normalize_override((overrides or {}).get(path, {}))
    if "text" in manual:
        return None
    movie = getattr(definition, "_ui_game_state_movie", None)
    if movie is None or not bool(getattr(movie, "ui_game_mock_enabled", False)):
        return None
    role = match_text_role(path, definition=definition)
    if role is None or role not in set(getattr(movie, "ui_game_mock_roles", ()) or ()):
        return None
    values = getattr(movie, "ui_game_mock_values", {}) or {}
    if role not in values:
        return None
    return role, format_mock_value(role, values[role], {"variable_name": getattr(definition, "variable_name", "")})


def text_definition_for_path(definition, path, overrides):
    result = _BASE_TEXT_DEFINITION(definition, path, overrides)
    mock = _mock_for_definition(definition, path, overrides)
    if mock is None:
        return result
    role, text = mock
    clone = copy.copy(result)
    clone.initial_text = text
    if hasattr(clone, "html"):
        clone.html = False
    movie = getattr(definition, "_ui_game_state_movie", None)
    paths = getattr(movie, "_ui_game_mock_render_paths", None) if movie is not None else None
    if paths is not None:
        paths.add(str(path))
    clone._ui_game_mock_role = role
    return clone


def _decorate_mock_nodes(movie, nodes):
    enabled = bool(getattr(movie, "ui_game_mock_enabled", False))
    roles = set(getattr(movie, "ui_game_mock_roles", ()) or ())
    values = getattr(movie, "ui_game_mock_values", {}) or {}
    result = []
    for node in tuple(nodes or ()):
        metadata = dict(node.metadata)
        children = _decorate_mock_nodes(movie, node.children)
        if enabled and node.kind == "EditText":
            manual = override_patch.normalize_override(metadata.get("override", {}))
            if "text" not in manual:
                role = match_text_role(node.path, metadata)
                if role in roles and role in values:
                    replacement = format_mock_value(role, values[role], metadata)
                    metadata.setdefault("original_text", metadata.get("text", ""))
                    metadata["text"] = replacement
                    metadata["display_text"] = replacement
                    metadata["html"] = False
                    metadata["mock_role"] = role
                    metadata["mock_label"] = MOCK_FIELD_BY_KEY[role].label
        result.append(state_inspector.StateNode(
            node.path, node.depth, node.label, node.kind, node.visible,
            node.character_id, node.class_name, metadata, children,
        ))
    return tuple(result)


def inspect_movie_state(movie, frame, max_depth=64):
    return _decorate_mock_nodes(movie, _BASE_INSPECT_MOVIE_STATE(movie, frame, max_depth))


def format_state_node(node, resolver=None):
    text = _BASE_FORMAT_STATE_NODE(node, resolver)
    role = node.metadata.get("mock_role")
    if not role:
        return text
    value = node.metadata.get("display_text", "")
    return text + f"\n\nGame-State-Mock:\n- Rolle: {MOCK_FIELD_BY_KEY[role].label}\n- Wert: {value}"


def render_with_mock_stats(renderer, frame):
    movie = renderer.movie
    movie._ui_game_mock_render_paths = set()
    image, stats = _BASE_RENDER(renderer, frame)
    current = set(getattr(movie, "_ui_game_mock_render_paths", set()) or ())
    cache_hit = bool(getattr(stats, "render_cache_hit", False))
    if current or not cache_hit or not bool(getattr(movie, "ui_game_mock_enabled", False)):
        movie.ui_game_mock_last_paths = current
    stats.game_mock_text_fields = len(getattr(movie, "ui_game_mock_last_paths", current) or ())
    stats.game_mock_enabled = bool(getattr(movie, "ui_game_mock_enabled", False))
    return image, stats


def make_preset(owner):
    result = _BASE_MAKE_PRESET(owner)
    result["game_state"] = current_game_state(owner)
    return result


def normalize_preset(data):
    result = _BASE_NORMALIZE_PRESET(data)
    result["game_state"] = normalize_game_state(data.get("game_state", {}) if isinstance(data, dict) else {})
    return result


def apply_game_state_data(owner, value):
    state = normalize_game_state(value)
    owner._ui_game_mock_enabled = state["enabled"]
    owner._ui_active_game_profile_id = state["profile"]
    owner._ui_game_mock_roles = tuple(state["roles"])
    owner._ui_game_mock_values = dict(state["values"])
    touch_game_state(owner, refresh_inspector=False)


def load_preset(window):
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
        timeline_core.set_root_frame(window.owner, min(int(movie.frame_count), int(preset["root_frame"])))
    timeline_browser.apply_loaded_playback(window.owner, preset["playback"])
    apply_game_state_data(window.owner, preset["game_state"])
    override_patch._invalidate_overrides(window.owner)
    window.override_status_var.set(f"Preset geladen: {Path(path).name}")
    window.refresh()


def flatten_nodes(nodes):
    for node in tuple(nodes or ()):
        yield node
        yield from flatten_nodes(node.children)


def mapped_fields(owner):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return ()
    try:
        nodes = inspect_movie_state(movie, int(owner.frame_var.get()))
    except Exception:
        return ()
    result = []
    for node in flatten_nodes(nodes):
        role = node.metadata.get("mock_role")
        if role:
            result.append((role, node.path, node.metadata.get("variable_name", ""), node.metadata.get("display_text", "")))
    return tuple(result)


class GameMockWindow(tk.Toplevel):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.title("UI Game-State-Mocks")
        self.geometry("1050x720")
        self.minsize(820, 560)
        self.transient(owner)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.value_vars = {}
        self.enabled_vars = {}

        intro = ttk.Label(
            self,
            text="Automatische Zuordnung über Textvariable, Instanzname und stabilen Inspector-Pfad. "
                 "Manuelle Text-Overrides haben Vorrang.",
            wraplength=980,
        )
        intro.pack(fill="x", padx=10, pady=(10, 6))

        values = ttk.LabelFrame(self, text="Mock-Werte", padding=8)
        values.pack(fill="x", padx=10, pady=(0, 8))
        current_values = getattr(owner, "_ui_game_mock_values", DEFAULT_MOCK_VALUES)
        current_roles = set(getattr(owner, "_ui_game_mock_roles", ()))
        for index, field in enumerate(MOCK_FIELDS):
            row = index // 2
            col = (index % 2) * 3
            enabled = tk.BooleanVar(value=field.key in current_roles)
            value = tk.StringVar(value=str(current_values.get(field.key, field.default)))
            self.enabled_vars[field.key] = enabled
            self.value_vars[field.key] = value
            ttk.Checkbutton(values, variable=enabled).grid(row=row, column=col, sticky="w")
            ttk.Label(values, text=field.label + ":").grid(row=row, column=col + 1, sticky="w", padx=(3, 5), pady=2)
            ttk.Entry(values, textvariable=value, width=22).grid(row=row, column=col + 2, sticky="ew", padx=(0, 14), pady=2)
        values.columnconfigure(2, weight=1)
        values.columnconfigure(5, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(buttons, text="Mocks anwenden", command=self.apply).pack(side="left")
        ttk.Button(buttons, text="Standardwerte", command=self.defaults).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Mocks deaktivieren", command=self.disable).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="Zuordnung aktualisieren", command=self.refresh_mapping).pack(side="right")

        ttk.Label(self, text="Zugeordnete EditText-Felder im aktuellen Zustand:").pack(anchor="w", padx=10)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        self.tree = ttk.Treeview(frame, columns=("role", "value", "variable", "path"), show="headings")
        self.tree.heading("role", text="Rolle")
        self.tree.heading("value", text="Mock-Wert")
        self.tree.heading("variable", text="Variable")
        self.tree.heading("path", text="Pfad")
        self.tree.column("role", width=150, stretch=False)
        self.tree.column("value", width=110, stretch=False)
        self.tree.column("variable", width=160, stretch=False)
        self.tree.column("path", width=560)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.pack(side="left", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var).pack(fill="x", padx=10, pady=(0, 10))
        self.refresh_mapping()

    def defaults(self):
        for field in MOCK_FIELDS:
            self.value_vars[field.key].set(str(field.default))

    def apply(self):
        values = {}
        roles = []
        for field in MOCK_FIELDS:
            values[field.key] = coerce_mock_value(field.key, self.value_vars[field.key].get())
            if self.enabled_vars[field.key].get():
                roles.append(field.key)
        self.owner._ui_game_mock_values = values
        self.owner._ui_game_mock_roles = tuple(roles)
        self.owner._ui_game_mock_enabled = bool(roles)
        self.owner._ui_active_game_profile_id = ""
        touch_game_state(self.owner)
        self.refresh_mapping()

    def disable(self):
        for variable in self.enabled_vars.values():
            variable.set(False)
        disable_game_mocks(self.owner)
        self.refresh_mapping()

    def refresh_mapping(self):
        self.tree.delete(*self.tree.get_children())
        fields = mapped_fields(self.owner)
        for index, (role, path, variable, value) in enumerate(fields):
            self.tree.insert("", "end", iid=f"mock_{index}", values=(
                MOCK_FIELD_BY_KEY[role].label, value, variable or "-", path,
            ))
        self.status_var.set(f"{len(fields)} Textfelder automatisch zugeordnet")

    def close(self):
        self.owner._game_mock_window = None
        self.destroy()


def show_mock_editor(owner):
    window = getattr(owner, "_game_mock_window", None)
    try:
        if window is not None and window.winfo_exists():
            window.lift()
            window.focus_force()
            window.refresh_mapping()
            return window
    except Exception:
        pass
    owner._game_mock_window = GameMockWindow(owner)
    return owner._game_mock_window


def update_profile_controls(owner):
    variable = getattr(owner, "game_profile_var", None)
    profile_id = str(getattr(owner, "_ui_active_game_profile_id", "") or "")
    profile = PROFILE_BY_ID.get(profile_id)
    if variable is not None:
        wanted = profile.name if profile else "Kein Profil"
        try:
            if variable.get() != wanted:
                variable.set(wanted)
        except Exception:
            pass
    status = getattr(owner, "game_profile_status_var", None)
    if status is not None:
        if not bool(getattr(owner, "_ui_game_mock_enabled", False)):
            status.set("Mocks aus")
        else:
            name = profile.name if profile else "Benutzerdefiniert"
            status.set(f"{name} | {len(getattr(owner, '_ui_game_mock_roles', ()))} Werte")


def apply_selected_profile(owner):
    profile = profile_for_name(owner.game_profile_var.get())
    result = apply_profile(owner, profile.profile_id if profile else "")
    if result is not None and not profile_matches_movie(result, movie_display_name(owner)):
        owner.game_profile_status_var.set(
            f"{result.name} angewendet; Filmname passt nicht zum empfohlenen Profil"
        )


def install_browser_ui():
    original_init = ui_browser.UIBrowser.__init__
    original_tree_select = ui_browser.UIBrowser._on_tree_select
    original_format_info = ui_browser.UIBrowser._format_info
    original_close = ui_browser.UIBrowser.close

    def browser_init(owner, *args, **kwargs):
        owner._ui_game_state_by_movie = {}
        owner._ui_current_game_state_key = ""
        owner._ui_game_mock_enabled = False
        owner._ui_game_mock_roles = ()
        owner._ui_game_mock_values = dict(DEFAULT_MOCK_VALUES)
        owner._ui_active_game_profile_id = ""
        owner._game_mock_window = None
        original_init(owner, *args, **kwargs)
        owner.game_profile_var = tk.StringVar(value="Kein Profil")
        owner.game_profile_status_var = tk.StringVar(value="Mocks aus")
        bar = ttk.Frame(owner, padding=(8, 0, 8, 5))
        bar.pack(fill="x")
        ttk.Label(bar, text="State-Profil:").pack(side="left")
        owner.game_profile_combo = ttk.Combobox(
            bar, textvariable=owner.game_profile_var, values=PROFILE_NAMES,
            state="readonly", width=27,
        )
        owner.game_profile_combo.pack(side="left", padx=(5, 5))
        ttk.Button(bar, text="Anwenden", command=lambda: apply_selected_profile(owner)).pack(side="left")
        ttk.Button(bar, text="Mocks…", command=lambda: show_mock_editor(owner)).pack(side="left", padx=(5, 0))
        ttk.Button(bar, text="Mocks aus", command=lambda: disable_game_mocks(owner)).pack(side="left", padx=(5, 0))
        ttk.Label(bar, textvariable=owner.game_profile_status_var).pack(side="right")
        owner.bind("<F8>", lambda _event: show_mock_editor(owner))
        attach_game_state(owner)

    def tree_select(owner, event=None):
        save_current_game_state(owner)
        result = original_tree_select(owner, event)
        attach_game_state(owner)
        return result

    def format_info(owner, stats):
        text = original_format_info(owner, stats)
        profile = PROFILE_BY_ID.get(str(getattr(owner, "_ui_active_game_profile_id", "") or ""))
        enabled = bool(getattr(owner, "_ui_game_mock_enabled", False))
        count = int(getattr(stats, "game_mock_text_fields", 0) or 0)
        if not enabled and not profile:
            return text
        return text + "\n\nGame-State-Mocks:\n" + (
            f"- Profil: {profile.name if profile else 'Benutzerdefiniert'}\n"
            f"- Aktiv: {'ja' if enabled else 'nein'}\n"
            f"- Rollen: {len(getattr(owner, '_ui_game_mock_roles', ()))}\n"
            f"- Textfelder im Renderzustand: {count}"
        )

    def close(owner):
        save_current_game_state(owner)
        window = getattr(owner, "_game_mock_window", None)
        try:
            if window is not None and window.winfo_exists():
                window.destroy()
        except Exception:
            pass
        return original_close(owner)

    ui_browser.UIBrowser.__init__ = browser_init
    ui_browser.UIBrowser._on_tree_select = tree_select
    ui_browser.UIBrowser._format_info = format_info
    ui_browser.UIBrowser.close = close
    ui_browser.UIBrowser.apply_ui_game_profile = apply_profile
    ui_browser.UIBrowser.show_ui_game_mocks = show_mock_editor
    ui_browser.UIBrowser.disable_ui_game_mocks = disable_game_mocks


def install():
    global _INSTALLED, _BASE_TEXT_DEFINITION, _BASE_INSPECT_MOVIE_STATE
    global _BASE_FORMAT_STATE_NODE, _BASE_MAKE_PRESET, _BASE_NORMALIZE_PRESET, _BASE_RENDER
    if _INSTALLED:
        return
    _INSTALLED = True

    _BASE_TEXT_DEFINITION = override_patch.text_definition_for_path
    _BASE_INSPECT_MOVIE_STATE = state_inspector.inspect_movie_state
    _BASE_FORMAT_STATE_NODE = state_inspector.format_state_node
    _BASE_MAKE_PRESET = timeline_core.make_preset_with_playback
    _BASE_NORMALIZE_PRESET = timeline_core.normalize_preset_with_playback
    _BASE_RENDER = ui_browser.UIRenderer.render

    override_patch.text_definition_for_path = text_definition_for_path
    state_inspector.inspect_movie_state = inspect_movie_state
    ui_browser.inspect_movie_state = inspect_movie_state
    state_inspector.format_state_node = format_state_node
    ui_browser.UIRenderer.render = render_with_mock_stats

    override_patch.make_preset = make_preset
    override_patch.normalize_preset = normalize_preset
    timeline_core.make_preset_with_playback = make_preset
    timeline_core.normalize_preset_with_playback = normalize_preset
    ui_browser.make_ui_state_preset = make_preset
    ui_browser.normalize_ui_state_preset = normalize_preset

    timeline_inspector.load_preset = load_preset
    state_inspector.StateInspectorWindow.load_override_preset = load_preset

    install_browser_ui()

    ui_browser.UI_GAME_STATE_PROFILES = PROFILES
    ui_browser.UI_GAME_MOCK_FIELDS = MOCK_FIELDS
    ui_browser.match_ui_game_mock_role = match_text_role
    ui_browser.normalize_ui_game_state = normalize_game_state
