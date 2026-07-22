"""MSBT catalog and exact, preview-only runtime text resolution for the UI Browser."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
import re

from msbt_codec import parse_msbt
from pak_core import get_entry_asset, get_entry_payload, parse_segmented_payload


LANGUAGE_NAMES = {
    "USEN": "English (US)", "USFR": "Français (US)", "USSP": "Español (US)",
    "EUEN": "English (EU)", "EUFR": "Français (EU)", "EUSP": "Español (EU)",
    "EUGE": "Deutsch", "EUIT": "Italiano", "JPJP": "日本語", "UNKN": "Unbekannt",
}
LANGUAGE_ORDER = tuple(LANGUAGE_NAMES)
DEFAULT_LANGUAGE = "EUEN"
DEFAULT_FALLBACK = "USEN"
_MAX_RECORDS = 2_000_000
_MAX_ERRORS = 500
_MAX_LINKS = 20_000


@dataclass(frozen=True)
class LocalizationRecord:
    source_label: str
    entry_name: str
    entry_uuid: str
    bundle: str
    language: str
    label: str
    text: str
    message_index: int
    attribute_hex: str = ""


@dataclass(frozen=True)
class LocalizationResolution:
    requested: str
    language: str
    record: LocalizationRecord
    fallback_used: bool = False

    @property
    def text(self):
        return self.record.text


@dataclass(frozen=True)
class LocalizationLink:
    text_id: str
    source_kind: str
    source: str
    count: int = 1


def compact(value):
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


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
    return tuple(result)


def _entry_name(entry):
    return str(entry.get("display_name") or entry.get("name") or entry.get("uuid_hex") or "MSBT")


def _language_from_name(value):
    upper = str(value or "").upper()
    for code in LANGUAGE_ORDER:
        if code != "UNKN" and code in upper:
            return code
    return "UNKN"


def iter_msbt_payloads(parsed, source_label=""):
    for entry in tuple(parsed.get("entries", ()) or ()):
        try:
            asset = get_entry_asset(parsed, entry)
            payload = get_entry_payload(asset)
        except Exception as exc:
            yield None, None, None, None, f"{_entry_name(entry)}: {exc}"
            continue
        entry_name = _entry_name(entry)
        if payload.startswith(b"MsgStdBn"):
            yield entry, entry_name, _language_from_name(entry_name), bytes(payload), None
        bundle = entry.get("bundle")
        if bundle is None:
            try:
                bundle = parse_segmented_payload(payload)
            except Exception:
                bundle = None
        if not bundle:
            continue
        for child in tuple(bundle.get("children", ()) or ()):
            inner = bytes(child.get("inner", b""))
            if not inner.startswith(b"MsgStdBn"):
                continue
            language = str(child.get("segment_tag", "") or "UNKN").strip().upper()
            yield entry, entry_name, language or "UNKN", inner, None


def build_localization_catalog(owner):
    records, errors, documents = [], [], []
    for parsed, source_label in source_items(owner):
        for entry, entry_name, language, raw, error in iter_msbt_payloads(parsed, source_label):
            if error:
                if len(errors) < _MAX_ERRORS:
                    errors.append(error)
                continue
            try:
                document = parse_msbt(raw)
            except Exception as exc:
                if len(errors) < _MAX_ERRORS:
                    errors.append(f"{source_label}/{entry_name}/{language}: {exc}")
                continue
            documents.append({
                "source": source_label, "entry": entry_name, "language": language,
                "messages": len(document.messages), "encoding": document.encoding,
                "version": document.version, "size": document.file_size,
            })
            for message in document.messages:
                if len(records) >= _MAX_RECORDS:
                    errors.append("MSBT-Katalog hat das globale Datensatzlimit erreicht")
                    break
                records.append(LocalizationRecord(
                    str(source_label), entry_name,
                    str(entry.get("uuid_hex", "") if entry else ""), entry_name,
                    str(language or "UNKN"), message.label, message.text, message.index,
                    message.attribute.hex(),
                ))
    records.sort(key=lambda item: (
        LANGUAGE_ORDER.index(item.language) if item.language in LANGUAGE_ORDER else len(LANGUAGE_ORDER),
        item.bundle.casefold(), item.label.casefold(), item.source_label.casefold(), item.entry_uuid,
    ))
    by_language = defaultdict(lambda: defaultdict(list))
    by_bundle_language = defaultdict(lambda: defaultdict(list))
    labels_casefold = defaultdict(set)
    for record in records:
        by_language[record.language][record.label].append(record)
        by_bundle_language[(record.bundle.casefold(), record.language)][record.label].append(record)
        labels_casefold[record.label.casefold()].add(record.label)
    return {
        "records": tuple(records), "errors": tuple(errors), "documents": tuple(documents),
        "languages": tuple(code for code in LANGUAGE_ORDER if code in by_language) + tuple(
            sorted(code for code in by_language if code not in LANGUAGE_ORDER)
        ),
        "by_language": {
            language: {label: tuple(values) for label, values in labels.items()}
            for language, labels in by_language.items()
        },
        "by_bundle_language": {
            key: {label: tuple(values) for label, values in labels.items()}
            for key, labels in by_bundle_language.items()
        },
        "casefold_labels": {
            key: next(iter(values)) for key, values in labels_casefold.items() if len(values) == 1
        },
    }


def normalize_localization_config(value, available_languages=()):
    value = value if isinstance(value, dict) else {}
    available = tuple(str(item) for item in available_languages if item)
    language = str(value.get("language", DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE).upper()
    fallback = str(value.get("fallback", DEFAULT_FALLBACK) or DEFAULT_FALLBACK).upper()
    if available and language not in available:
        language = DEFAULT_LANGUAGE if DEFAULT_LANGUAGE in available else (
            DEFAULT_FALLBACK if DEFAULT_FALLBACK in available else available[0]
        )
    if available and fallback not in available:
        fallback = DEFAULT_FALLBACK if DEFAULT_FALLBACK in available else available[0]
    return {"enabled": bool(value.get("enabled", True)), "language": language, "fallback": fallback}


def ensure_localization_config(movie):
    catalog = getattr(movie, "ui_localization_catalog", {}) or {}
    clean = normalize_localization_config({
        "enabled": getattr(movie, "ui_localization_enabled", True),
        "language": getattr(movie, "ui_localization_language", DEFAULT_LANGUAGE),
        "fallback": getattr(movie, "ui_localization_fallback", DEFAULT_FALLBACK),
    }, catalog.get("languages", ()))
    movie.ui_localization_enabled = clean["enabled"]
    movie.ui_localization_language = clean["language"]
    movie.ui_localization_fallback = clean["fallback"]
    return clean


def attach_localization_catalog(owner, movie=None):
    movie = movie or getattr(owner, "_current_movie", None)
    if movie is None:
        return {}
    token = tuple(
        (str(parsed.get("path", "")), len(parsed.get("entries", ())), id(parsed.get("data")))
        for parsed, _label in source_items(owner)
    )
    if getattr(movie, "_ui_localization_catalog_token", None) != token:
        movie.ui_localization_catalog = build_localization_catalog(owner)
        movie._ui_localization_catalog_token = token
        movie.ui_localization_revision = int(getattr(movie, "ui_localization_revision", 0)) + 1
    movie._ui_localization_owner = owner
    ensure_localization_config(movie)
    attach_localization_links(movie)
    return movie.ui_localization_catalog


def language_chain(movie):
    catalog = getattr(movie, "ui_localization_catalog", {}) or {}
    available = tuple(catalog.get("languages", ()))
    config = ensure_localization_config(movie)
    chain = []
    for value in (config["language"], config["fallback"], DEFAULT_LANGUAGE, DEFAULT_FALLBACK, *available):
        if value and value in available and value not in chain:
            chain.append(value)
    return tuple(chain)


_WRAPPED_PATTERNS = (
    re.compile(r"^\$\{([^{}]+)\}$"), re.compile(r"^@([^@]+)@$"),
    re.compile(r"^#([^#]+)#$"), re.compile(r"^\[([^\[\]]+)\]$"),
)


def text_id_candidates(value):
    if not isinstance(value, str):
        return ()
    text = value.strip()
    if not text or len(text) > 4096:
        return ()
    candidates = [text]
    lower = text.casefold()
    for prefix in ("loc:", "msbt:", "text:", "message:"):
        if lower.startswith(prefix):
            candidates.append(text[len(prefix):].strip())
    for pattern in _WRAPPED_PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            candidates.append(match.group(1).strip())
    result = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)
    return tuple(result)


def _split_bundle_candidate(candidate, catalog):
    for separator in (":", "/"):
        if separator not in candidate:
            continue
        bundle, label = candidate.split(separator, 1)
        if any(key[0] == bundle.casefold() for key in catalog.get("by_bundle_language", {})):
            return bundle, label
    return "", candidate


def _canonical_label(catalog, candidate):
    for language_values in catalog.get("by_language", {}).values():
        if candidate in language_values:
            return candidate
    return catalog.get("casefold_labels", {}).get(candidate.casefold(), "")


def label_is_unambiguous(catalog, label):
    found = False
    for language in catalog.get("languages", ()):
        values = catalog.get("by_language", {}).get(language, {}).get(label, ())
        if not values:
            continue
        found = True
        if len({item.text for item in values}) > 1:
            return False
    return found


def resolve_text_id(movie, value, bundle_hint=""):
    if not bool(getattr(movie, "ui_localization_enabled", True)):
        return None
    catalog = getattr(movie, "ui_localization_catalog", {}) or {}
    if not catalog.get("records"):
        return None
    for candidate in text_id_candidates(value):
        explicit_bundle, raw_label = _split_bundle_candidate(candidate, catalog)
        label = _canonical_label(catalog, raw_label)
        if not label:
            continue
        bundle = explicit_bundle or str(bundle_hint or "")
        chain = language_chain(movie)
        selected = chain[0] if chain else ""
        for language in chain:
            values = ()
            if bundle:
                values = catalog.get("by_bundle_language", {}).get(
                    (bundle.casefold(), language), {}
                ).get(label, ())
            if not values:
                values = catalog.get("by_language", {}).get(language, {}).get(label, ())
                if len(values) > 1:
                    unique_texts = {item.text for item in values}
                    values = values[:1] if len(unique_texts) == 1 else ()
            if values:
                return LocalizationResolution(candidate, language, values[0], bool(selected and language != selected))
    return None


def localize_value(movie, value, bundle_hint=""):
    resolution = resolve_text_id(movie, value, bundle_hint)
    return resolution.text if resolution is not None else value


def available_translations(movie, label, bundle_hint=""):
    catalog = getattr(movie, "ui_localization_catalog", {}) or {}
    canonical = _canonical_label(catalog, str(label or ""))
    if not canonical:
        return {}
    result = {}
    for language in catalog.get("languages", ()):
        values = ()
        if bundle_hint:
            values = catalog.get("by_bundle_language", {}).get(
                (str(bundle_hint).casefold(), language), {}
            ).get(canonical, ())
        if not values:
            values = catalog.get("by_language", {}).get(language, {}).get(canonical, ())
        if values:
            result[language] = values[0]
    return result


def _definition_strings(movie):
    for character_id, definition in (getattr(movie, "definitions", {}) or {}).items():
        for attr in ("initial_text", "variable_name"):
            value = getattr(definition, attr, None)
            if isinstance(value, str) and value:
                yield value, f"DefineEditText {character_id}.{attr}"


def _abc_strings(movie):
    for module in tuple(getattr(movie, "avm2_modules", ()) or ()):
        abc = getattr(module, "abc", None)
        for value in tuple(getattr(abc, "strings", ()) or ()) if abc is not None else ():
            if isinstance(value, str) and value:
                yield value, f"ABC {getattr(module, 'name', '<unnamed>')}"


def _callback_strings(movie):
    for summary in tuple(getattr(movie, "ui_native_callback_summaries", ()) or ()):
        for sample in tuple(getattr(summary, "argument_samples", ()) or ()):
            for value in tuple(sample or ()):
                if isinstance(value, str) and value and value != "<dynamic>":
                    yield value, f"Callback {summary.name}"


def attach_localization_links(movie):
    catalog = getattr(movie, "ui_localization_catalog", {}) or {}
    token = (
        id(catalog), tuple((id(module), id(getattr(module, "abc", None)))
                           for module in tuple(getattr(movie, "avm2_modules", ()) or ())),
        len(getattr(movie, "definitions", {}) or {}),
        len(tuple(getattr(movie, "ui_native_callback_summaries", ()) or ())),
    )
    if getattr(movie, "_ui_localization_links_token", None) == token:
        return tuple(getattr(movie, "ui_localization_links", ()))
    counts = Counter()
    sources = defaultdict(set)
    for kind, iterator in (("AVM2", _abc_strings(movie)), ("EditText", _definition_strings(movie)),
                           ("Callback", _callback_strings(movie))):
        for value, source in iterator:
            canonical = ""
            for candidate in text_id_candidates(value):
                _bundle, label = _split_bundle_candidate(candidate, catalog)
                canonical = _canonical_label(catalog, label)
                if canonical:
                    break
            if not canonical or not label_is_unambiguous(catalog, canonical):
                continue
            counts[(canonical, kind)] += 1
            if len(sources[(canonical, kind)]) < 32:
                sources[(canonical, kind)].add(source)
    links = [
        LocalizationLink(text_id, kind, ", ".join(sorted(sources[(text_id, kind)])), count)
        for (text_id, kind), count in counts.most_common(_MAX_LINKS)
    ]
    movie.ui_localization_links = tuple(links)
    movie._ui_localization_links_token = token
    return movie.ui_localization_links


def localization_snapshot(movie, include_texts=False):
    catalog = getattr(movie, "ui_localization_catalog", {}) or {}
    config = ensure_localization_config(movie)
    language_counts = Counter(record.language for record in catalog.get("records", ()))
    bundle_counts = Counter(record.bundle for record in catalog.get("records", ()))
    result = {
        "schema": 1, "config": config, "languages": dict(language_counts),
        "bundles": dict(bundle_counts), "documents": list(catalog.get("documents", ())),
        "errors": list(catalog.get("errors", ())),
        "links": [link.__dict__ for link in attach_localization_links(movie)],
    }
    if include_texts:
        result["texts"] = [record.__dict__ for record in catalog.get("records", ())]
    return result
