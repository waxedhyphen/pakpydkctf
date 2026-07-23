# UI Viewer – Timeline, Runtime und Abschlussstatus

Stand: 2026-07-23

## Ziel und Umfang

Der UI Viewer stellt die Scaleform-Oberflächen aus `GFX`, `GFXL`, `TXTR`, `MSBT`,
`CAUD`, `CSMP` und requireten PAKs dar. Er reproduziert konkrete UI-Zustände in einer
isolierten Vorschau, ohne Quelldaten zu verändern oder neu zu packen.

Der implementierte Umfang ist bewusst ein sicherer, begrenzter Scaleform-Viewer und
kein allgemeiner Flash Player. Innerhalb dieses Viewer-Umfangs sind die geplanten
Render-, Timeline-, Zustands-, Eingabe-, Text-, Audio- und Graphics-Stufen abgeschlossen.

## Verifizierter Ressourcenpfad

```text
GFX-Film
  → SWF/GFX-Timeline und Display-List
  → PlaceObject2 / PlaceObject3
  → Symbol- oder Klassenname
  → GFXL-Library-Film
  → Scaleform-Tag 1009 + SymbolClass
  → GFXL Name-zu-UUID
  → TXTR im aktuellen oder requireten PAK
```

Zusätzliche Laufzeitressourcen:

```text
ActionScript / Native Callback
  → sichere Preview-Registry
  → Game-State-Mocks / Runtime-Daten
  → CAUD → CSMP → PCM/WAV
  → MSBT-Text-ID → Sprachkatalog
```

## Entwicklungsstand

### Phase 0 – Formaterkundung

Status: abgeschlossen

- `GFX`, `GFXL`, `TXTR`, `DGRP`, `MSBT`, `CAUD` und `CSMP` eingeordnet.
- Stage, Frames, Sprites, Klassen, Imports und ActionScript-Blöcke bestätigt.
- Require-PAKs und UUID-Auflösung verifiziert.

### Phase 1 – Statischer UI Browser

Status: abgeschlossen

- GFX-Filmauswahl, Root-Frames und Frame-Labels.
- Skalierbare Stage mit korrektem Seitenverhältnis.
- TXTR-Auflösung aus aktuellem und requiretem PAK.
- Matrix, Alpha, ColorTransform, PNG-Export, Bounds und Platzhalter.

### Phase 2 – Vorschauorientierung

Status: abgeschlossen

- Zlib-TXTR und CWS-UI-Vorschauen verwenden die verifizierte Ursprungskorrektur.
- Die frühere 180-Grad-Korrektur wurde entfernt, weil sie links und rechts vertauschte.

### Phase 3 – GFXL-Library-Symbole

Status: abgeschlossen

- Scaleform-Tag `1009`, `SymbolClass` und GFXL-UUID-Mapping.
- 1.446 von 1.446 Bildsymbolen verbunden.
- 803 externe Klassen in 1.895 Placements aufgelöst.

### Phase 4 – Shapes, Morphs und Fills

Status: abgeschlossen

- `DefineShape1` bis `DefineShape4`.
- `DefineMorphShape` und `DefineMorphShape2` mit 16-Bit-Ratio.
- Gerade, quadratische und interpolierte kubische Laufzeitpfade.
- Solid-, lineare, radiale, fokale und Bitmap-Fills.
- Spread-Modi `pad`, `reflect` und `repeat`.
- sRGB- und Linear-RGB-Interpolation.
- Eingebettete JPEG-, JPEG-Alpha- und Lossless-Bitmaps.
- Linien, Löcher, Winding-Regeln und ColorTransform.
- Reproduzierbarer Visual-Format-Scanner.

Siehe `UI_VIEWER_VISUAL_FORMATS.md`.

### Phase 5 – Masken, Scale9 und Effekte

Status: abgeschlossen

- ClipDepth-Masken einschließlich verschachtelter und überlappender Masken.
- `DefineScalingGrid`/Nine-slice.
- Nichtlineare Scale9-Rücktransformation für präzise HitTests.
- PlaceObject3-Sichtbarkeit und Blend Modes.
- Glow, DropShadow, Blur und Bevel.
- Reihenfolge: Objekt → Filter → Maske → Blend Mode.

Bekannter Corpus: 13 ClipDepth-Tags, 56 Scaling-Grids, 53 Blend-Placements und
460 Filterdatensätze.

### Phase 6 – Fonts, Texte und Lokalisierung

Status: abgeschlossen

- Vier importierte `DefineFont3`-Outline-Fonts.
- Unicode-Glyphen, Scaleform-HTML, Größe, Farbe, Ausrichtung und `letterSpacing`.
- 648 EditText-Felder und 647 HTML-Textfelder im bekannten UI-Corpus.
- MSBT-Katalog mit neun Sprachcodes, exakter Text-ID-Auflösung und Fallback.
- Laufzeitlokalisierung für statische und dynamische TextFields.
- Editierbare Textfelder mit Caret, Auswahl, Passwortdarstellung, `maxChars`,
  `restrict`, Undo/Redo und begrenzter Zwischenablage.

Siehe `UI_VIEWER_LOCALIZATION.md` und `UI_VIEWER_EDIT_TEXT_INPUT.md`.

### Phase 6.5 – Display-List-/State-Inspector

Status: abgeschlossen

- Rekursiver Tiefenbaum mit stabilen Instanzpfaden.
- Character-ID, Klasse, Sichtbarkeit, Matrix, ColorTransform, ClipDepth, Scale9,
  Filter und Blend Mode.
- MovieClip-Frames, Labels, Fonts und Texte.
- Dynamische MovieClips, TextFields, Shapes, Bitmaps und Container.
- AVM2-, Lifecycle-, Callback-, Localization-, EditText- und Graphics-Metadaten.
- Suche, Sichtbarkeitsfilter, Pfadkopie und JSON-Snapshot.

### Phase 7 – Verschachtelte Timelines

Status: abgeschlossen für den begrenzten Viewer-Umfang

- Eigener Framezustand pro stabilem MovieClip-Instanzpfad.
- Play, Pause, Vorwärts-/Rückwärtsschritt und Reset.
- SWF-Framerate und Tempo `0.25×` bis `4×`.
- Root- und Sprite-Label-Sprünge.
- Manueller `sprite_frame`-Override mit höchster Priorität.
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay` aus kontrollierten Frame Scripts.
- `ENTER_FRAME`, Timer und Event-Handler für Root- und Untertimelines.
- Dynamisch erzeugte verknüpfte MovieClips mit echter SWF-Timeline.
- Automatische Buttonzustände `up`, `over`, `down` und `disabled`.

### Phase 7.5 – Interaktive Performance

Status: abgeschlossen

- Display-List-, Stage-Frame-, Scale9-, Graphics- und Geometriecaches.
- Leichter MovieClip-Pfad-Scan statt vollständigem Inspector-Aufbau pro Tick.
- Gedrosselte Inspector-Aktualisierung.
- Adaptive Vorschauauflösung von 35 bis 75 Prozent während Play/Scrubbing.
- Volle native Auflösung nach Pause und beim PNG-Export.
- AVM2-, Dynamic-, Input-, BitmapData- und Graphics-Revisionen im Cache-Schlüssel.
- Begrenzte LRU-Caches für WAV, Vektorraster, Gradients, eingebettete Bitmaps und
  dynamische Graphics.

### Phase 8 – Manuelle States, Profile und Game-Mocks

Status: abgeschlossen

- Sichtbarkeit, MovieClip-Frame, Text/HTML, Filter und Blend Mode pro Pfad.
- Presets für Root-Frame, Overrides, Playback und MovieClip-Instanzzustände.
- Profile für HUD, Time Attack, Pause, Optionen, Frontend, Shop und Charakterwahl.
- Mocks für Spieler, Leben, Banana Coins, Puzzle Pieces, Timer, Punkte, Level,
  Bananen, KONG-Buchstaben und Fortschritt.
- Automatische Textzuordnung über Variable, Instanzname und Elternpfad.
- Sichere Callback-Rückgabe-Overrides.
- Zustände bleiben pro Film getrennt.

### Phase 9 – ActionScript 3 und Native Brücken

Status: abgeschlossen für den kontrollierten Preview-Teilumfang

Implementiert:

- vollständiger struktureller ABC-Parser;
- Constant Pools, Namespaces, Multinames, Methoden, Traits, Klassen, Scripts,
  Methodenbodies und Exception-Tabellen;
- AVM2-Disassembly und `addFrameScript`-Zuordnung;
- Operand-Stack, Locals, Konvertierungen, Arithmetik, Vergleiche und Branches;
- direkte Hilfsmethoden und Timeline-Befehle;
- Script-, Klassen- und Instanz-Initializer;
- lokal aufgelöste Vererbung;
- EventDispatcher-Grundlage, Prioritäten und sichere Events;
- Timer, `getTimer`, Timeout, Interval und `ENTER_FRAME`;
- dynamische Display-List und SymbolClass-Konstruktionen;
- DisplayObject- und TextField-Properties;
- 134 klassifizierte Native-Callback-Namen an 6.730 deduplizierten Call-Sites;
- sichere Preview-Subsysteme für Daten, Navigation, Controller, Save/Profile, Shop,
  Extras, Leaderboards, Replay, Audio, Telemetrie und Gameplay-Ereignisse;
- deterministische Completion-Queue;
- F9-/F10-/F11-Inspector und Runtime-Neuausführung.

Corpus-Validierung:

- 47 Filmpayloads mit DoABC;
- 40 eindeutige ABC-Payloads;
- 0 strukturelle Parserfehler;
- 1.460 Klassen;
- 14.642 Methoden;
- 1.342 Frame-Script-Bindings;
- 1.215 direkte sichere Timeline-Aktionen.

### Phase 9.5 – Dynamische und Timeline-Graphics

Status: abgeschlossen

Unterstützte API:

```text
clear
beginFill
beginGradientFill
beginBitmapFill
endFill
lineStyle
lineGradientStyle
lineBitmapStyle
moveTo
lineTo
curveTo
cubicCurveTo
drawRect
drawRoundRect
drawCircle
drawEllipse
drawPath
drawTriangles
```

Zusätzlich:

- `BitmapData` mit Pixel-, Fill-, Copy-, Draw-, Scroll-, FloodFill-, Clone- und
  Dispose-Operationen;
- dynamische `Bitmap`-DisplayObjects;
- UVT- und Culling-Unterstützung für Dreiecke;
- Graphics auf vorhandenen Timeline-Shape-/Sprite-/MovieClip-Instanzen;
- korrekte Einordnung in Geschwistertiefen, Masken, Filter und Blend Modes;
- Alpha-HitTests für dynamische und Timeline-Graphics sowie BitmapData;
- BitmapData-revisionsabhängige Rastercaches.

Siehe `UI_VIEWER_DYNAMIC_GRAPHICS.md` und `UI_VIEWER_GRAPHICS_COMPLETE.md`.

### Phase 10 – Eingabe, Audio und Lokalisierung

Status: abgeschlossen für den Viewer-Umfang

- Maus-, Tastatur-, Fokus- und Click-Events entlang stabiler Parent-Pfade.
- Tab-, Pfeiltasten- und WASD-Navigation.
- Controllerartige Navigate-, Accept- und Cancel-Events.
- MovieClip- und klassische Buttonzustände.
- `DefineButton` und `DefineButton2` mit sicherem AVM1-Timeline-Teilumfang.
- Präzise Shape-, TXTR-, BitmapData-, Graphics-, Masken- und Scale9-HitTests.
- Editierbare statische und dynamische TextFields.
- CAUD-Katalog, CSMP-DSP-ADPCM-Decoder, WAV-Export und optionale Windows-Wiedergabe.
- Deterministische Completion- und `soundComplete`-Events.
- MSBT-Sprachumschaltung und Laufzeittexte.

## Sicherheitsgrenzen

Wesentliche Grenzen:

- 8.192 AVM2-Instruktionen pro Ausführung;
- Aufruftiefe 16 und höchstens acht verkettete Frame-Sprünge;
- 32 Timer-Auslösungen und 32 Completion-Abschlüsse pro Tick;
- 2.048 dynamische DisplayObjects und 2.048 Timeline-Graphics-Pfade;
- dynamische Verschachtelungstiefe 64;
- 10.000 Graphics-Befehle und 2.048 Primitive pro Objekt;
- 32.768 Dreiecke pro `drawTriangles`-Aufruf;
- 8.192 Pixel maximale Bitmap-/Rasterkante;
- 32 Millionen Pixel pro kontrolliertem Raster oder BitmapData-Objekt;
- 256 MiB pro BitmapData und 64 MiB Graphics-Rastercache;
- 1.000.000 Zeichen pro TextField und 65.536 Clipboard-Zeichen pro Aktion;
- keine beliebigen Datei-, Prozess-, Netzwerk-, Shader- oder Host-Aufrufe.

## Reproduzierbare Prüfwerkzeuge

- `scan_ui_native_callbacks.py`
- `scan_ui_audio_links.py`
- `scan_ui_localization_links.py`
- `scan_ui_classic_buttons.py`
- `scan_ui_edit_texts.py`
- `scan_ui_visual_formats.py`
- `compare_ui_frames.py`
- `test_repository_python_syntax.py`

Der Syntax-Test kompiliert alle Python-Dateien und läuft in CI unter Python 3.12 und
3.14.

## Abschlusskriterien

Innerhalb des begrenzten Viewer-Umfangs erfüllt:

- Bilder, Vektoren, Morphs, Masken, Texte, Fonts, Filter, Blend Modes und Scale9 werden
  dargestellt.
- Statische, verschachtelte, dynamische und skriptgesteuerte Timelines laufen.
- Requirete Ressourcen werden aufgelöst.
- Referenzframes können exportiert und pixelweise verglichen werden.
- Maus-, Tastatur- und controllerartige Navigation funktionieren.
- Textfelder sind im Vorschauzustand bearbeitbar.
- Spielwerte werden über Mocks und sichere Callback-Stubs eingespeist.
- Native Callbacks werden isoliert simuliert.
- UI-Audio kann dekodiert, exportiert und optional abgespielt werden.
- Dynamische und Timeline-Graphics einschließlich BitmapData sind verfügbar.

## Bewusste Nicht-Ziele

Folgende Punkte sind keine offenen Viewer-Arbeitsblöcke, sondern außerhalb des sicheren
begrenzten Produktumfangs:

- vollständige Flash-Player-/AVM1-/AVM2-Spezifikation;
- beliebige Prototype-, Namespace-, Reflection- und JIT-Semantik;
- GPU-Shader und beliebige BitmapFilter;
- uneingeschränkte Stage-Reentranz aus `BitmapData.draw`;
- betriebssystemweite Gamepad- und IME-Abstraktion;
- pixelidentische Reproduktion jedes historischen Scaleform-Rasterizer-Sonderfalls;
- Kommunikation mit dem originalen Spielprozess oder dessen proprietärem Host.

Weitere Arbeit ist damit Wartung, Corpus-Validierung und gezielte Kompatibilitätskorrektur
für konkrete reproduzierbare Dateien, nicht mehr die Umsetzung eines geplanten
Funktionsblocks.
