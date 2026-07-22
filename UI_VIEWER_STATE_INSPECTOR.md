# UI Viewer – Display-List-/State-Inspector

Stand: 2026-07-22

## Status

Der State Inspector zeigt den tatsächlich resultierenden Vorschauzustand: Root- und Untertimelines, manuelle Overrides, AVM2-Runtimewerte, dynamische DisplayObjects, Buttonzustände, Game-Mocks, MSBT-Lokalisierung sowie klassische SWF-Button- und HitTest-Metadaten.

Alle Änderungen bleiben Preview-Zustand. Quelldaten und Repacking werden nicht verändert.

## Öffnen

1. Einen GFX-Film im UI Browser auswählen.
2. `State Inspector` anklicken oder `F6` drücken.
3. Root-Frame, Wiedergabe, Profile, Sprache oder Runtimezustand ändern.
4. Der Inspector aktualisiert sich automatisch; während Play wird die Aktualisierung zur Performance gedrosselt.

## Angezeigte Daten

Für jedes Placement beziehungsweise dynamische Objekt werden je nach Typ angezeigt:

- stabiler Instanzpfad aus Tiefe und Instanzname;
- Character-ID, SymbolClass, externe Klasse und Definitionstyp;
- Sichtbarkeit, Parent und Kindanzahl;
- Matrix, ColorTransform, Alpha und Laufzeit-Properties;
- ClipDepth, Scale9, Filter, Blend Mode und Maskendiagnosen;
- Root-/MovieClip-Frame, Labels, Play/Pause und manueller Framevorrang;
- Font, Textvariable, Text/HTML und MSBT-Quelle;
- Game-State-Mock-Rolle und resultierender Wert;
- AVM2-Frame-Scripts, Runtimewrites, Events, Timer und native Callbackdaten;
- dynamische Fokus-, Maus-, Tab- und Buttoninformationen;
- klassische `DefineButton`-/`DefineButton2`-Version, Records, HitRecords, Actionblöcke und TrackAsMenu;
- präzise HitTest-Geometrie, soweit für den Pfad vorhanden.

## Suche und Navigation

- Freitextsuche über Pfad, Name, Typ, Klasse, IDs, Texte und Metadaten;
- `Nur sichtbare` berücksichtigt den resultierenden Zustand;
- Baum vollständig öffnen oder schließen;
- stabilen Pfad kopieren;
- vollständigen JSON-Snapshot speichern.

## Manuelle Overrides

Ausgewählte Knoten unterstützen:

- Sichtbarkeit;
- festen MovieClip-Unterframe;
- Plaintext oder HTML für EditText;
- Filter deaktivieren;
- Blend Mode deaktivieren.

Priorität bei Texten:

```text
manueller Textoverride
-> direkter AVM2-Text/htmlText
-> Game-State-Mock
-> exakte MSBT-Auflösung
-> ursprünglicher DefineEditText-Inhalt
```

Ein manueller MovieClip-Frame besitzt Vorrang vor Timeline, Buttonzustand und AVM2-Sprüngen dieses Pfads.

## Laufende und dynamische Zustände

Untertimelines besitzen einen eigenen Frame- und Play/Pause-Zustand. Dynamisch erzeugte MovieClips, Sprites, TextFields, Shapes und Container erscheinen im selben Baum. Konstruktoren, Eventhandler, Timer, Native-Callbacks und Eingaben können den angezeigten Zustand verändern.

Klassische Buttons erscheinen Sprite-kompatibel als MovieClips mit `up`, `over`, `down` und `hit`. Der Inspector weist zusätzlich aus, dass die Definition aus Tag 7 oder 34 stammt.

## Presets

`Preset speichern` beziehungsweise `Preset laden` umfasst derzeit:

- Quell-PAK, Film und Root-Frame;
- manuelle Overrides;
- globales und pfadspezifisches Playback;
- Game-State-Profil und Mock-Werte;
- Native-Callback-Modus und Rückgabe-Overrides;
- Audio-Vorschauoptionen;
- MSBT-Aktivierung, Sprache und Fallback.

Transiente Objektgraphen, Logs, Eventqueues, WAV-Caches und präzise Hit-Geometrien werden nicht serialisiert, sondern aus dem Filmzustand neu aufgebaut.

## Verbleibende Grenzen

- vollständige Flash-Capture-/Bubbling-Semantik;
- vollständige AVM1- und AVM2-Semantik;
- editierbare TextFields mit Cursor, Auswahl und IME;
- pixelgenaue Glyphen-HitTests;
- echte Gamepad-Hardware;
- Morph-Shapes und verbleibende seltene Fills.

Weitere Details: `UI_VIEWER_STATE_PRESETS.md`, `UI_VIEWER_TIMELINE_PLAYBACK.md`, `UI_VIEWER_DYNAMIC_DISPLAY_INPUT.md`, `UI_VIEWER_BUTTON_NAVIGATION.md`, `UI_VIEWER_CLASSIC_BUTTON_HITTEST.md`, `UI_VIEWER_NATIVE_CALLBACKS.md`, `UI_VIEWER_ASYNC_AUDIO.md` und `UI_VIEWER_LOCALIZATION.md`.
