# UI Viewer – State-Overrides und Presets

Stand: 2026-07-22

## Zweck

State-Presets speichern manuell rekonstruierte UI-Zustände, Timeline-Wiedergabe und optionale Game-State-Mocks. Sie eignen sich für Pause-/Optionsseiten, HUD-Gruppen, alternative MovieClip-Frames, Testtexte, Effektvergleiche und reproduzierbare Screenshots.

Alle Presets wirken ausschließlich auf die Vorschau.

## Preset erstellen

1. Einen GFX-Film im UI Browser öffnen.
2. Root-Frame und optional Timeline-Wiedergabe einstellen.
3. Optional ein State-Profil anwenden oder `Mocks…` öffnen.
4. `State Inspector` oder `F6` öffnen.
5. Instanzen auswählen und manuelle Overrides setzen.
6. `Preset speichern` anklicken.

Gespeichert werden Film, Quell-PAK, Root-Frame, manuelle Overrides, Playback-Zustand sowie Profil und Mock-Werte.

## Preset laden

1. Den passenden GFX-Film öffnen.
2. State Inspector öffnen.
3. `Preset laden` anklicken.
4. JSON-Datei auswählen.

Das Laden ersetzt die aktiven Overrides, Timeline-Zustände und Game-Mocks dieses Films. Root-Frame, Tempo und globaler Play/Pause-Zustand werden wiederhergestellt. Bei einem anderen Filmnamen erscheint eine Warnung; die Pfade werden trotzdem geladen.

## Unterstützte Overrides

### Sichtbarkeit

```json
{"visible": false}
```

### Fester MovieClip-Unterframe

```json
{"sprite_frame": 12}
```

Ein fester Unterframe besitzt Vorrang vor der laufenden Timeline dieses Pfads.

### Text oder HTML

```json
{
  "text": "TEST 999",
  "html": false
}
```

```json
{
  "text": "<p align=\"center\"><font size=\"30\" color=\"#ffffff\">TEST</font></p>",
  "html": true
}
```

Ein manueller Text-Override besitzt Vorrang vor einem automatisch zugeordneten Game-State-Mock. Fontklasse, Textfeldgröße, Transformation, Filter, Masken und Blend Modes bleiben erhalten.

### Filter oder Blend Mode deaktivieren

```json
{
  "disable_filters": true,
  "disable_blend": true
}
```

## Playback-Zustand

```json
{
  "playback": {
    "speed": 1.0,
    "playing": false,
    "instances": {
      "root/5:options_control/1:btnHandheld": {
        "frame": 11,
        "playing": true
      }
    }
  }
}
```

- `speed`: globale Wiedergabegeschwindigkeit;
- `playing`: globaler Play/Pause-Zustand;
- `instances[path].frame`: aktueller Unterframe;
- `instances[path].playing`: ob diese Instanz bei globaler Wiedergabe mitläuft.

## Game-State-Mocks

```json
{
  "game_state": {
    "enabled": true,
    "profile": "hud_1p",
    "roles": ["players", "lives", "banana_coins", "score"],
    "values": {
      "players": 1,
      "lives": 5,
      "banana_coins": 23,
      "score": 12500,
      "timer_seconds": 95.42
    }
  }
}
```

- `enabled`: globale Mock-Aktivierung für diesen Film;
- `profile`: ID der mitgelieferten Vorlage oder leer bei benutzerdefinierten Werten;
- `roles`: tatsächlich aktivierte semantische Textrollen;
- `values`: Werte aller bekannten Mock-Felder.

Ältere Presets ohne `playback` oder `game_state` bleiben kompatibel.

## Vollständiges Schema

```json
{
  "format": "PAKPY_UI_STATE_PRESET",
  "version": 1,
  "pak": "UIPak.pak",
  "movie": "Options.swf",
  "root_frame": 20,
  "overrides": {
    "root/5:options_control/1:btnHandheld": {
      "visible": true
    },
    "root/1:align_Title/1:txt_title": {
      "text": "OPTIONS TEST",
      "html": false,
      "disable_filters": true
    }
  },
  "playback": {
    "speed": 0.5,
    "playing": false,
    "instances": {
      "root/5:options_control/1:btnHandheld": {
        "frame": 11,
        "playing": false
      }
    }
  },
  "game_state": {
    "enabled": false,
    "profile": "options",
    "roles": [],
    "values": {
      "players": 1,
      "lives": 5,
      "banana_coins": 23,
      "puzzle_pieces": 4,
      "puzzle_total": 9,
      "timer_seconds": 95.42,
      "score": 12500,
      "level_name": "Jungle Hijinxs",
      "bananas": 73,
      "kong_letters": "KONG",
      "progress_percent": 42
    }
  }
}
```

## Stabile Pfade

Ein Pfad besteht aus Display-List-Tiefe und Instanzname:

```text
root/5:options_control/1:btnHandheld
```

Ohne Instanznamen werden je nach Objekt SymbolClass, externe Klasse, Textvariable oder `depth N` verwendet. Pfade sind innerhalb desselben Films stabil, können aber bei einer strukturell geänderten SWF ungültig werden.

## Verhalten bei Framewechseln

Overrides und Timeline-Zustände werden pro Renderdurchlauf anhand des Pfads angewendet. Game-Mocks werden zusätzlich bei jedem gerenderten EditText anhand von Variable, Instanzname und Pfad zugeordnet. Nicht vorhandene Pfade bleiben gespeichert und werden wieder aktiv, sobald sie in einem späteren Root- oder Unterframe erneut erscheinen.

## Sitzungsverwaltung

Override-, Timeline- und Mock-Zustände werden während der Browser-Sitzung pro Film getrennt gehalten. Für dauerhafte Speicherung muss ein JSON-Preset gespeichert werden.

## Grenzen

- Keine ActionScript-Konstruktoren oder Frame Scripts.
- Keine dynamisch erzeugten DisplayObjects.
- Keine automatische MSBT-Sprachauswahl oder native Callback-Ausführung.
- Ein manuell rekonstruierter Zustand muss nicht zwingend über den normalen Ingame-Code erreichbar sein.

Details: `UI_VIEWER_TIMELINE_PLAYBACK.md` und `UI_VIEWER_GAME_STATE_MOCKS.md`.
