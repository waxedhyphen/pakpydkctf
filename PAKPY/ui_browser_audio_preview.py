"""CAUD catalog, CSMP decoding cache and fixed local UI-audio backend."""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from pathlib import Path
import threading

from caud_codec import parse_caud_asset
from pak_core import get_entry_asset
from ui_audio_codec import UiAudioDecodeError, decode_csmp_to_wav
from ui_browser_native_callback_catalog import compact_name

_MAX_WAV_CACHE_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class UiSoundRecord:
    name: str
    normalized_name: str
    source_label: str
    caud_uuid: str
    csmp_refs: tuple[str, ...]
    parsed: object
    caud_info: dict
    parser_error: str = ""

    @property
    def loop(self):
        return bool(self.caud_info.get("loop", False))


class WavePreviewBackend:
    """Fixed WAV backend; ActionScript cannot address it directly."""

    def __init__(self):
        self._winsound = None
        self._thread = None
        self._lock = threading.RLock()
        self.last_error = ""
        try:
            import winsound
            self._winsound = winsound
        except Exception:
            pass

    @property
    def available(self):
        return self._winsound is not None

    def stop(self):
        if self._winsound is None:
            return False
        try:
            self._winsound.PlaySound(None, self._winsound.SND_PURGE)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            return False

    def play(self, wav_bytes):
        if self._winsound is None:
            self.last_error = "winsound ist auf dieser Plattform nicht verfügbar"
            return False
        payload = bytes(wav_bytes)
        self.stop()

        def worker():
            try:
                self._winsound.PlaySound(
                    payload,
                    self._winsound.SND_MEMORY | self._winsound.SND_NODEFAULT,
                )
            except Exception as exc:
                self.last_error = str(exc)

        with self._lock:
            self._thread = threading.Thread(
                target=worker, name="PAKPY-UI-Audio", daemon=True,
            )
            self._thread.start()
        return True


def normalize_audio_preview_config(value):
    value = value if isinstance(value, dict) else {}
    try:
        volume = float(value.get("volume", 0.65))
    except Exception:
        volume = 0.65
    return {
        "enabled": bool(value.get("enabled", False)),
        "muted": bool(value.get("muted", False)),
        "volume": max(0.0, min(1.0, volume)),
    }


def ensure_audio_config(movie):
    clean = normalize_audio_preview_config({
        "enabled": getattr(movie, "ui_audio_preview_enabled", False),
        "muted": getattr(movie, "ui_audio_preview_muted", False),
        "volume": getattr(movie, "ui_audio_preview_volume", 0.65),
    })
    movie.ui_audio_preview_enabled = clean["enabled"]
    movie.ui_audio_preview_muted = clean["muted"]
    movie.ui_audio_preview_volume = clean["volume"]
    return clean


def async_audio_state(movie):
    generation = int(getattr(movie, "ui_avm2_runtime_generation", 0))
    value = getattr(movie, "ui_async_audio_state", None)
    if not isinstance(value, dict) or int(value.get("generation", -1)) != generation:
        value = {
            "generation": generation, "next_id": 1,
            "pending": [], "completed": [], "queued": 0, "dispatched": 0,
            "data_notifications": 0, "resolved_audio": 0,
            "unresolved_audio": 0, "decoded_audio": 0, "played_audio": 0,
            "decode_errors": [], "last_sound": "",
        }
        movie.ui_async_audio_state = value
    return value


def source_items(owner):
    result, seen = [], set()

    def add(parsed, label):
        if not isinstance(parsed, dict):
            return
        key = (str(parsed.get("path", "")), id(parsed.get("data")))
        if key in seen:
            return
        seen.add(key)
        result.append((parsed, str(label or Path(parsed.get("path", "PAK")).name)))

    parsed = getattr(owner, "parsed", None)
    add(parsed, Path(parsed.get("path", "Aktuelles PAK")).name if isinstance(parsed, dict) else "Aktuelles PAK")
    store = getattr(owner, "require_store", None)
    for item in getattr(store, "required_paks", ()) if store is not None else ():
        add(item.get("parsed"), Path(item.get("path", "Require")).name)
    return result


def _fallback_caud(asset, csmp_entries):
    name, refs = "", []
    try:
        size = int.from_bytes(asset[32:36], "big")
        if 0 <= size <= len(asset) - 36:
            name = asset[36:36 + size].split(b"\x00", 1)[0].decode("ascii", "replace")
    except Exception:
        pass
    for entry in csmp_entries:
        raw_uuid = entry.get("uuid_bytes") or bytes.fromhex(entry.get("uuid_hex", ""))
        if raw_uuid and raw_uuid in asset:
            refs.append(str(entry.get("uuid_hex", "")))
    return name, tuple(dict.fromkeys(refs))


def build_audio_catalog(owner):
    records = []
    for parsed, label in source_items(owner):
        entries = tuple(parsed.get("entries", ()) or ())
        csmp_entries = [
            entry for entry in entries
            if str(entry.get("type", "")).strip().upper() == "CSMP"
        ]
        mapped = parsed.get("caud_to_csmp", {}) or {}
        for entry in entries:
            if str(entry.get("type", "")).strip().upper() != "CAUD":
                continue
            asset = get_entry_asset(parsed, entry)
            error, info = "", {}
            try:
                info = dict(parse_caud_asset(asset))
                name = str(
                    info.get("name", "") or entry.get("display_name", "")
                    or entry.get("name", "")
                )
                refs = tuple(str(value) for value in info.get("csmp_refs", ()) if value)
            except Exception as exc:
                error = str(exc)
                name, refs = _fallback_caud(asset, csmp_entries)
                info = {"name": name, "loop": False, "volume": 50.0, "gain": 1.0}
            if not refs:
                refs = tuple(
                    str(value) for value in mapped.get(entry.get("uuid_hex", ""), ())
                    if value
                )
            if not name:
                name = str(
                    entry.get("display_name") or entry.get("name")
                    or entry.get("uuid_hex", "CAUD")
                )
            records.append(UiSoundRecord(
                name, compact_name(name), label, str(entry.get("uuid_hex", "")),
                tuple(dict.fromkeys(refs)), parsed, info, error,
            ))
    return tuple(sorted(
        records, key=lambda item: (item.name.lower(), item.source_label.lower(), item.caud_uuid),
    ))


def attach_audio_catalog(owner, movie=None):
    movie = movie or getattr(owner, "_current_movie", None)
    if movie is None:
        return ()
    token = tuple(
        (str(parsed.get("path", "")), len(parsed.get("entries", ())), id(parsed.get("data")))
        for parsed, _label in source_items(owner)
    )
    if getattr(movie, "_ui_audio_catalog_token", None) != token:
        records = build_audio_catalog(owner)
        index = defaultdict(list)
        for record in records:
            index[record.normalized_name].append(record)
        movie.ui_audio_catalog = records
        movie.ui_audio_name_index = dict(index)
        movie._ui_audio_catalog_token = token
    movie._ui_audio_owner = owner
    ensure_audio_config(movie)
    async_audio_state(movie)
    return tuple(getattr(movie, "ui_audio_catalog", ()))


def resolve_sound(movie, name):
    values = (getattr(movie, "ui_audio_name_index", {}) or {}).get(compact_name(name), ())
    return values[0] if values else None


def sound_name(movie, args, fallback=""):
    strings = [str(item) for item in tuple(args or ()) if isinstance(item, str) and item]
    for value in strings:
        if resolve_sound(movie, value) is not None:
            return value
    return strings[0] if strings else str(fallback or "")


def find_csmp(owner, record, variant=0):
    if not record.csmp_refs:
        raise UiAudioDecodeError(f"{record.name} besitzt keine CSMP-Referenz")
    ref = record.csmp_refs[max(0, int(variant)) % len(record.csmp_refs)]
    parsed = record.parsed
    entry = (parsed.get("uuid_to_entry", {}) or {}).get(ref)
    if entry is None:
        for source_parsed, _label in source_items(owner):
            entry = (source_parsed.get("uuid_to_entry", {}) or {}).get(ref)
            if entry is not None:
                parsed = source_parsed
                break
    if entry is None:
        raise UiAudioDecodeError(f"CSMP {ref} wurde in aktuellem und requireten PAK nicht gefunden")
    return ref, get_entry_asset(parsed, entry)


def owner_backend(owner):
    backend = getattr(owner, "_ui_audio_backend", None)
    if backend is None:
        backend = WavePreviewBackend()
        owner._ui_audio_backend = backend
    return backend


def wav_cache(owner):
    value = getattr(owner, "_ui_audio_wav_cache", None)
    if not isinstance(value, OrderedDict):
        value = OrderedDict()
        owner._ui_audio_wav_cache = value
        owner._ui_audio_wav_cache_bytes = 0
    return value


def decode_sound(owner, record, variant=0, volume=None):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        raise UiAudioDecodeError("Kein UI-Film ausgewählt")
    config = ensure_audio_config(movie)
    user_volume = config["volume"] if volume is None else max(0.0, min(1.0, float(volume)))
    try:
        caud_volume = float(record.caud_info.get("volume", 50.0))
        caud_volume = caud_volume / 50.0 if caud_volume > 2.0 else caud_volume
    except Exception:
        caud_volume = 1.0
    try:
        gain = float(record.caud_info.get("gain", 1.0))
    except Exception:
        gain = 1.0
    effective = max(0.0, min(2.0, user_volume * caud_volume * gain))
    ref, asset = find_csmp(owner, record, variant)
    key = (ref, round(effective, 4))
    cache = wav_cache(owner)
    cached = cache.get(key)
    if cached is not None:
        cache.move_to_end(key)
        return cached
    wav_bytes, info = decode_csmp_to_wav(asset, volume=effective)
    cache[key] = (wav_bytes, info, ref)
    owner._ui_audio_wav_cache_bytes += len(wav_bytes)
    while cache and owner._ui_audio_wav_cache_bytes > _MAX_WAV_CACHE_BYTES:
        _old_key, old = cache.popitem(last=False)
        owner._ui_audio_wav_cache_bytes -= len(old[0])
    async_audio_state(movie)["decoded_audio"] += 1
    return wav_bytes, info, ref


def play_sound(owner, name, variant=0, force=False):
    movie = getattr(owner, "_current_movie", None)
    if movie is None:
        return False
    attach_audio_catalog(owner, movie)
    config = ensure_audio_config(movie)
    if (not force and not config["enabled"]) or config["muted"]:
        return False
    record = name if isinstance(name, UiSoundRecord) else resolve_sound(movie, name)
    state = async_audio_state(movie)
    if record is None:
        state["unresolved_audio"] += 1
        state["last_sound"] = str(name or "")
        return False
    try:
        wav_bytes, _info, _ref = decode_sound(owner, record, variant)
        played = owner_backend(owner).play(wav_bytes)
    except Exception as exc:
        state["decode_errors"].append({"sound": record.name, "error": str(exc)})
        del state["decode_errors"][:-100]
        return False
    state["last_sound"] = record.name
    if played:
        state["played_audio"] += 1
    return played


def stop_audio(owner):
    return owner_backend(owner).stop()
