# UI Viewer – State-Overrides und Presets

Stand: 2026-07-22

## Zweck

State-Presets speichern manuell rekonstruierte UI-Zustände, Timeline-Wiedergabe, optionale Game-State-Mocks, Native-Callback-Rückgabe-Overrides und Audio-Vorschauoptionen. Sie eignen sich für Pause-/Optionsseiten, HUD-Gruppen, alternative MovieClip-Frames, Testtexte, Effektvergleiche, Callback-gesteuerte Zustände und reproduzierbare Screenshots.

Alle Presets wirken ausschließlich auf die Vorschau.

## Preset erstellen

1. Einen GFX-Film im UI Browser öffnen.
2. Root-Frame und optional Timeline-Wiedergabe einstellen.
3. Optional ein State-Profil anwenden oder `Mocks…` öffnen.
4. Optional `Native Callbacks` oder `F11` öffnen und Rückgabewerte überschreiben.
5. Optional UI-Soundwiedergabe, Mute und Lautstärke einstellen.
6. `State Inspector` oder `F6` öffnen.
7. Instanzen auswählen und manuelle Overrides setzen.
8. `Preset speichern` anklicken.

Gespeichert werden Film, Quell-PAK, Root-Frame, manuelle Overrides, Playback-Zustand, Profil und Mock-Werte, Native-Callback-Modus und Rückgabe-Overrides sowie die Audio-Vorschauoptionen.

Transiente Runtime-Logs, Vorschau-Save-Slots, Audio-Requests, Telemetrie und Navigationseinträge werden bewusst nicht gespeichert.

## Preset laden

1. Den passenden GFX-Film öffnen.
2. State Inspector öffnen.
3. `Preset laden` anklicken.
4. JSON-Datei auswählen.

Das Laden ersetzt die aktiven Overrides, Timeline-Zustände, Game-Mocks und Native-Callback-Overrides dieses Films und stellt die Audio-Vorschauoptionen wieder her. Root-Frame, Tempo und globaler Play/Pause-Zustand werden wiederhergestellt. Bei einem anderen Filmnamen erscheint eine Warnung; die Pfade werden trotzdem geladen.

## Unterstützte Overrides

### Sichtbarkeit

```json
{"visible": false}
```

### Fester MovieClip-Unterframe

```json
{"sprite_frame": 12}
```

Ein fester Unterframe besitzt Vorrang vor der laufenden Timeline, automatischen Button-Zuständen und AVM2-Framewechseln dieses Pfads.

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

Ein manueller Text-Override besitzt Vorrang vor AVM2-Runtime und automatisch zugeordneten Game-State-Mocks. Fontklasse, Textfeldgröße, Transformation, Filter, Masken und Blend Modes bleiben erhalten.

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
- `roles`: tatsächlich aktivierte semantische Text- und Datenrollen;
- `values`: Werte aller bekannten Mock-Felder.

## Native Callbacks

```json
{
  "native_callbacks": {
    "mode": "simulate",
    "overrides": {
      "GetExtrasUnlockState": true,
      "IsDynamicControllerModeActive": false,
      "GetShopText": "Nicht genug Banana Coins"
    }
  }
}
```

### `mode`

- `simulate`: sichere DKCTF-spezifische Vorschauimplementierungen sind aktiv;
- `observe`: nur die bestehende sichere Registry, Data-Value-Grundlage und Game-State-Mocks laufen; weitere DKCTF-Aufrufe werden protokolliert.

### `overrides`

Jeder Eintrag überschreibt den Rückgabewert eines Callback-Namens. Die Namensauflösung ignoriert Groß-/Kleinschreibung. Erlaubt sind JSON-Werte:

- `null`;
- Boolean;
- Zahl;
- String;
- Liste;
- Objekt.

Maximal 256 Native-Callback-Overrides werden aus einem Preset übernommen.

Priorität:

```text
Native-Callback-Override
→ sichere Callback-Registry / Runtime-Daten / Game-State-Mock
→ DKCTF-Vorschauimplementierung
→ konservativer Default oder undefined
```

## Audio-Vorschau

```json
{
  "audio_preview": {
    "enabled": false,
    "muted": false,
    "volume": 0.65
  }
}
```

- `enabled`: automatische lokale Ausgabe aufgelöster UI-Sounds; standardmäßig `false`;
- `muted`: unterdrückt die direkte Ausgabe, ohne Katalog, Dekodierung und Completion-Events abzuschalten;
- `volume`: Viewer-Lautstärke von `0.0` bis `1.0`.

Ausstehende Completion-Requests, fertige WAV-Daten, Audio-Requests und abgespielte Stimmen sind transient und werden nicht serialisiert.

Ältere Presets ohne `playback`, `game_state`, `native_callbacks` oder `audio_preview` bleiben kompatibel.

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
  },
  "native_callbacks": {
    "mode": "simulate",
    "overrides": {
      "GetExtrasUnlockState": true,
      "IsDynamicControllerModeActive": false
    }
  },
  "audio_preview": {
    "enabled": false,
    "muted": false,
    "volume": 0.65
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

Native-Callback-Overrides sind nicht pfadgebunden. Sie gelten für den jeweiligen Callback-Namen im aktuell geöffneten Film.

## Sitzungsverwaltung

Override-, Timeline-, Mock-, Callback- und Audio-Konfigurationen werden während der Browser-Sitzung pro Film getrennt gehalten. Für dauerhafte Speicherung muss ein JSON-Preset gespeichert werden.

## Grenzen

- Transiente AVM2-, Event-, Timer-, Callback-, Audio- und Telemetrie-Logs werden nicht im Preset gespeichert.
- Dynamisch erzeugte DisplayObjects werden nach einem Runtime-Reset neu konstruiert und nicht als Objektgraph serialisiert.
- Keine automatische MSBT-Sprachauswahl.
- Ausstehende asynchrone Completion-Requests werden bewusst nicht gespeichert und nach einem Runtime-Reset neu erzeugt.
- Direkte Audiowiedergabe verwendet unter Windows `winsound`; auf anderen Plattformen bleibt WAV-Export verfügbar.
- Ein manuell rekonstruierter Zustand muss nicht zwingend über den normalen Ingame-Code erreichbar sein.

Details: `UI_VIEWER_TIMELINE_PLAYBACK.md`, `UI_VIEWER_GAME_STATE_MOCKS.md`, `UI_VIEWER_NATIVE_CALLBACKS.md` und `UI_VIEWER_ASYNC_AUDIO.md`.
