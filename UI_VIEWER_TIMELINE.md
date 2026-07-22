# UI Viewer – Timeline und Roadmap

Stand: 2026-07-22

## Ziel

Der Viewer soll die Scaleform-UIs aus `GFX`, `GFXL`, `TXTR`, `MSBT` und requireten PAKs darstellen und konkrete Ingame-Zustände untersuchbar machen. Alle Änderungen im Viewer bleiben Preview-Overrides; Quelldaten und Repacking werden nicht verändert.

## Verifizierter Ressourcenpfad

```text
GFX-Film
  -> SWF/GFX-Timeline und Display-List
  -> PlaceObject2 / PlaceObject3
  -> Symbol- oder Klassenname
  -> GFXL-Library-Film
  -> Scaleform-Tag 1009 + SymbolClass
  -> GFXL Name-zu-UUID
  -> TXTR im aktuellen oder requireten PAK
```

## Entwicklungsstand

### Phase 0 – Formaterkundung

Status: abgeschlossen

- `GFX`, `GFXL`, `TXTR` und `DGRP` eingeordnet.
- Stage, Frames, Sprites, Klassen, Imports und ActionScript-Blöcke bestätigt.

### Phase 1 – Statischer UI Browser

Status: abgeschlossen

- GFX-Filmauswahl, Root-Frames und Frame-Labels.
- Skalierbare Stage mit korrektem Seitenverhältnis.
- TXTR-Auflösung aus aktuellem und requiretem PAK.
- Matrix, Alpha, ColorTransform, PNG-Export, Bounds und Platzhalter.

### Phase 2 – Vorschauorientierung

Status: abgeschlossen

- Zlib-TXTR und CWS-UI-Vorschauen erhalten eine reine vertikale Ursprungskorrektur.
- Die frühere 180-Grad-Korrektur wurde entfernt, da sie links und rechts vertauschte.

### Phase 3 – GFXL-Library-Symbole

Status: abgeschlossen

- Scaleform-Tag `1009`, `SymbolClass` und GFXL-UUID-Mapping.
- 1446 von 1446 Bildsymbolen verbunden.
- 803 externe Klassen in 1895 Placements aufgelöst.

### Phase 4 – Vektor-Shapes

Status: für den bereitgestellten UI-Corpus abgeschlossen

- `DefineShape1` bis `DefineShape4`, gerade und quadratische Kanten.
- Solid-Fills, lineare Gradients, Linien, Löcher und ColorTransform.
- 625 von 625 Shapes ohne Parserfehler.

Offen bleiben generische Bitmap-/Radial-Fills, pixelgenaue Linien-Sonderfälle und Morph-Shapes.

### Phase 5 – Masken, Scale9 und Effekte

Status: für die im Corpus verwendeten Funktionen umgesetzt

- ClipDepth-Masken einschließlich verschachtelter und überlappender Masken.
- `DefineScalingGrid`/Nine-slice.
- PlaceObject3-Sichtbarkeit und Blend Modes.
- Glow, DropShadow, Blur und Bevel.
- Reihenfolge: Objekt → Filter → Maske → Blend Mode.

Corpus: 13 ClipDepth-Tags, 56 Scaling-Grids, 53 Blend-Placements und 460 Filterdatensätze.

### Phase 6 – Fonts und Texte

Status: eingebettete Fonts und initiale `DefineEditText`-Inhalte abgeschlossen

- Vier importierte `DefineFont3`-Outline-Fonts.
- Unicode-Glyphen, Scaleform-HTML, Größe, Farbe, Ausrichtung und `letterSpacing`.
- 648 EditText-Felder und 647 HTML-Textfelder.

MSBT-Zuordnung und Laufzeittexte sind umgesetzt. Offen bleibt ein pixelgenauer Font-Rasterizer-Abgleich für alle Sprachzeichensätze.

### Phase 6.5 – Display-List-/State-Inspector

Status: abgeschlossen

- Rekursiver Tiefenbaum mit stabilen Instanzpfaden.
- Character-ID, Klasse, Sichtbarkeit, Matrix, ColorTransform, ClipDepth, Scale9, Filter und Blend Mode.
- MovieClip-Frames/Labels sowie Fontklasse und Text.
- Dynamisch erzeugte MovieClips, TextFields, Shapes und Container erscheinen mit Parent-, Transform-, Fokus- und Eingabemetadaten.
- Suche, Sichtbarkeitsfilter, Pfadkopie und JSON-Snapshot.

Siehe `UI_VIEWER_STATE_INSPECTOR.md` und `UI_VIEWER_DYNAMIC_DISPLAY_INPUT.md`.

### Phase 7 – Verschachtelte Timelines

Status: laufende strukturelle Vorschau umgesetzt; AVM2-Frame-Scripts, Lifecycle-Ereignisse und dynamische MovieClips steuern einen sicheren Teilumfang

- eigener Framezustand pro stabilem MovieClip-Instanzpfad;
- globale Play-/Pause-Steuerung und `F7`;
- Vorwärts-/Rückwärts-Einzelschritt und Reset;
- Looping anhand der jeweiligen Root- und Sprite-Frameanzahl;
- Wiedergabe mit der SWF-Framerate und Tempo `0.25×` bis `4×`;
- Root- und Sprite-Label-Sprünge;
- manueller `sprite_frame`-Override besitzt Vorrang;
- Wiedergabestatus, Geschwindigkeit und Instanzframes werden in JSON-Presets gespeichert;
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay` werden aus kontrolliert interpretierten Frame Scripts angewendet;
- `ENTER_FRAME`, Timer und Event-Handler können Root- und Untertimelines verändern;
- dynamisch erzeugte MovieClips mit verknüpfter SWF-Definition verwenden ihre echte Timeline und laufen mit der UI-Timeline;
- Button-MovieClips wechseln automatisch zwischen `up`, `over`, `down` und `disabled`.

Wichtige Grenzen: vollständiges Flash-Capture/Bubbling, editierbare TextFields und echte Gamepad-Hardware fehlen weiterhin. Klassische Buttons sowie Shape-/Alpha-/Masken-HitTests sind umgesetzt.

Siehe `UI_VIEWER_TIMELINE_PLAYBACK.md`, `UI_VIEWER_AVM2.md`, `UI_VIEWER_AVM2_RUNTIME.md`, `UI_VIEWER_AVM2_LIFECYCLE.md`, `UI_VIEWER_DYNAMIC_DISPLAY_INPUT.md` und `UI_VIEWER_BUTTON_NAVIGATION.md`.

### Phase 7.5 – Interaktive Performance

Status: umgesetzt

- Display-List-, Stage-Frame- und pfadspezifische Scale9-Caches;
- leichter MovieClip-Pfad-Scan statt vollständigem Inspector-Aufbau pro Tick;
- gedrosselte Inspector-Aktualisierung;
- adaptive Vorschauauflösung von 35 bis 75 Prozent während Play/Scrubbing;
- volle native Auflösung nach Pause und beim PNG-Export;
- AVM2- und Dynamic-State-Revisionsnummern im Frame-Cache-Schlüssel;
- gecachte SymbolClass- und AVM2-Klassenauflösung für dynamische Konstruktionen.

Siehe `UI_VIEWER_PERFORMANCE.md`.

### Phase 8 – Manuelle States, Profile und Game-Mocks

Status: generische Overrides, Playback-Zustände, Profile, Text-Mocks und Callback-Overrides abgeschlossen

Implementiert:

- Sichtbarkeit, MovieClip-Frame, Text/HTML, Filter und Blend Mode pro Instanzpfad überschreibbar;
- Presets speichern Root-Frame, Overrides, Wiedergabe und MovieClip-Instanzzustände;
- acht mitgelieferte Analyseprofile für HUD, Time Attack, Pause, Optionen, Frontend, Shop und Charakterwahl;
- Mock-Werte für Spielerzahl, Leben, Banana Coins, Puzzle Pieces, Timer, Punkte, Levelname, Bananen, KONG-Buchstaben und Fortschritt;
- automatische EditText-Zuordnung anhand `variable_name`, Instanzname und stabilen Elternpfaden;
- Mock-Editor mit Zuordnungsübersicht und `F8`;
- manuelle Text-Overrides besitzen Vorrang vor AVM2-Runtime und Mocks;
- Profile und Mock-Werte werden im JSON-Preset gespeichert;
- aktive Game-Mocks können über sichere `ExternalInterface.call`- und `GetDataValue`-Stubs gelesen werden;
- AVM2 kann vorhandene und dynamische TextFields im Vorschauzustand aktualisieren;
- Rückgabewerte nativer Callbacks können im `F11`-Inspector JSON-basiert überschrieben und im Preset gespeichert werden;
- Zustände bleiben während der Sitzung pro Film getrennt.

Siehe `UI_VIEWER_STATE_PRESETS.md`, `UI_VIEWER_GAME_STATE_MOCKS.md` und `UI_VIEWER_NATIVE_CALLBACKS.md`.

Noch offen:

- semantische Mock-Zuordnung für erst zur Laufzeit erzeugte, frei benannte TextFields;
- exakter Abgleich einzelner Completion-Eventnamen mit dem ursprünglichen Host.

### Phase 9 – ActionScript 3

Status: Strukturparser, Frame-Script-Inventar, kontrollierte Interpreter-Runtime, Lifecycle-/Event-/Timer-Grundlage, dynamische Display-List und native Callback-Schicht umgesetzt; vollständige AVM2-Semantik offen

Implementiert:

- `DoABC`-Inventar mit Modulname, Flags, Quelle und Parserdiagnosen;
- ABC-Constant-Pools für Integer, UInt, Double, Strings, Namespaces, Namespace-Sets und Multinames;
- Methoden, optionale Parameter, Metadaten, Traits, Klassen, Scripts, Methodenbodies und Exception-Tabellen;
- AVM2-Disassembly mit aufgelösten Constant-Pool-Referenzen;
- `addFrameScript`-Erkennung in Instance-Initializern;
- Zuordnung zu Dokumentklasse und exportierten MovieClip-Klassen;
- Operand-Stack und lokale Variablen;
- direkte Konstanten, einfache Konvertierungen, Arithmetik und Vergleiche;
- `jump`, bedingte Sprünge und `lookupswitch`;
- direkte Hilfsmethoden-Aufrufe derselben Klasse;
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay` für Root-, Unter- und dynamische Timelines;
- Property-Lesen und -Schreiben auf vorhandenen und dynamischen Instanzen;
- `visible`, `alpha`, `text`, `htmlText`, `x`, `y`, `scaleX`, `scaleY`, `rotation`, `enabled`, `mouseEnabled`, `tabEnabled` und Fokusstatus;
- Whitelist-Registry für sichere native Callback-Stubs;
- lesende Anbindung vorhandener Game-State-Mocks an `ExternalInterface.call` und corpus-typische Datenfelder;
- Script-, Klassen- und Instanz-Initializer für Root-, Timeline- und verknüpfte dynamische Instanzen;
- Basisklassen-Initializer vor abgeleiteten Konstruktoren, wenn die Klassen im selben ABC-Modul liegen;
- EventDispatcher-Grundfunktionen mit Listenern, Priorität und direktem Dispatch;
- Event-Konstanten und sichere Custom-Eventobjekte;
- `Timer`, `getTimer`, `setTimeout`, `setInterval` und die zugehörigen Clear-Funktionen;
- deterministische Runtime-Uhr anhand der SWF-Timeline;
- `ENTER_FRAME`, `TIMER` und `TIMER_COMPLETE`;
- sichere Konstruktion von MovieClip, Sprite, TextField, Shape, DisplayObject sowie verknüpften SymbolClass-Instanzen;
- `addChild`, `addChildAt`, `removeChild`, `removeChildAt`, `getChildByName`, `getChildAt`, `contains`, `numChildren`, Child-Reihenfolge und Swap-Operationen;
- dynamische Objekte im Renderer, State Inspector und Render-Cache;
- statisches Inventar von `ExternalInterface`-, `Controller`-, `Model`- und Data-Value-Brücken;
- 134 klassifizierte native Callback-Namen an 6.730 deduplizierten Call-Sites im vollständigen `UIPak.pak`-Scan;
- sichere Preview-Implementierungen für Data Read/Write/Listen, Navigation, Controller, Save/Profile, Shop, Extras, Leaderboard, Audio-Requests, Telemetrie, Lifecycle und Gameplay-Events;
- deterministische Completion-Queue für Data-Value-, Save-, Loading-, Leaderboard-, Replay-, Extras- und Audio-Abschlüsse;
- CAUD-Katalog aus aktuellem und requireten PAK sowie CAUD-zu-CSMP-Auflösung;
- DSP-ADPCM-Dekodierung nach 16-Bit-PCM/WAV und `soundComplete` anhand der realen Sampledauer;
- Native-Callback-Inspector über `F11`, JSON-Export und Rückgabe-Overrides;
- AVM2-Inspector über `F9` und Runtime-Neuausführung über `F10`;
- Frame-Script-, Runtime-, Lifecycle-, Dynamic-, Input- und Native-Callback-Metadaten im Analysefeld.

Sicherheitsgrenzen:

- höchstens 8192 Instruktionen pro Ausführung;
- maximale Aufruftiefe 16;
- höchstens acht direkt verkettete Frame-Sprünge;
- höchstens 32 Timer-Auslösungen pro Runtime-Tick;
- höchstens 32 Klassen in einer lokal aufgelösten Vererbungskette;
- höchstens 2048 dynamische DisplayObjects pro Film;
- maximale dynamische Verschachtelungstiefe 64;
- unbekannte Nicht-Display-Klassen werden nicht als visuelle Objekte konstruiert;
- höchstens 2.000 Native-Callback-Logeinträge, 500 Einträge pro Ereignispuffer und 256 Rückgabe-Overrides;
- höchstens 256 ausstehende Completion-Requests und 32 Abschlüsse pro Timeline-Tick;
- höchstens 4 Audiokanäle, 20.000.000 Samples pro Kanal, 256 MiB PCM pro Sound und 64 MiB WAV-Cache;
- nicht unterstützte Opcodes brechen nur die betroffene Methode ab;
- keine beliebigen Host-, Datei-, Prozess-, Netzwerk-, Audio- oder Gamepad-Aufrufe.

Validierung:

- fünf synthetische ABC-/Frame-Script-Tests für Strukturparser, DoABC, Disassembly, `addFrameScript`, Timeline-Aktionen und JSON-Inventar;
- elf Tests für Property-Zuweisungen, Branches, Callback-Mocks, Corpus-Muster, Timeline-Sprünge und manuellen Override-Vorrang;
- acht Lifecycle-Tests für Initializer-Reihenfolge, EventDispatcher, Event-Konstanten, Timer, `ENTER_FRAME`, `setTimeout` und verschachtelte Timeline-Zustände;
- neun Dynamic-Display-Modelltests für Konstruktion, Containeroperationen, Transform, Text, Fokus und Timeline-Fortschritt;
- zwei Tests für den genauen Konstruktorzeitpunkt verknüpfter dynamischer AVM2-Klassen;
- zwölf Tests für Button-Zustände, Owner-Routing und Richtungsnavigation;
- 14 Native-Callback-Tests für Inventar, Klassifikation, Priorität, Data-Value-Aliase, isolierte Subsysteme und JSON-Sicherheit;
- vollständiger Native-Scan: 47 Filmpayloads, 40 eindeutige ABC-Payloads, 0 Parserfehler, 134 Namen, 6.730 Call-Sites;
- Dry-Run aller 134 Namen mit repräsentativen Argumenten ohne Exception;
- 15 Async-/Audio-Tests für DSP-Dekodierung, WAV, Queue, Eventdispatch, Priorität, konservative Callback-Auswahl und Presets;
- Audio-Corpus-Scan: 1.010 CAUD, 1.248 CSMP, 680 Audio-Call-Sites, 67 von 68 normalisierten Namen aufgelöst und 67 von 67 Prüfvarianten ohne Decoderfehler;
- elf MSBT-/Lokalisierungstests sowie Corpus-Scan mit 36 Sprachdateien, 7.641 Nachrichtensätzen, neun Sprachen und null Parserfehlern;
- acht Tests für klassische SWF-Buttons, AVM1-Sicherheitsgrenzen, Alpha-/Clip-HitTests und ClipDepth-Erkennung;
- Button-/HitTest-Corpus-Scan: 60 eingebettete Filmpayloads, null klassische Button-Tags, 13 ClipDepth-Placements und null Scannerfehler.

Noch offen:

- vollständige AVM2-Objekt-, Prototyp-, Klassen- und Namespace-Semantik;
- Initializer und Vererbung über ABC-Modulgrenzen hinweg;
- Exception-Handling und vollständige Iteration;
- vollständiges Event-Bubbling, Capture und Weak-Listener-Semantik;
- dynamische Vektorzeichenbefehle und editierbare TextFields;
- exakter Host-Abgleich der simulierten Completion-Eventnamen und Payloads;
- exakter Signaturabgleich einzelner nativer Callbacks mit Spielcode;
- vollständige Message-Studio-Parameter- und Kontrolltagsemantik.

Siehe `UI_VIEWER_AVM2.md`, `UI_VIEWER_AVM2_RUNTIME.md`, `UI_VIEWER_AVM2_RUNTIME_CORPUS.md`, `UI_VIEWER_AVM2_LIFECYCLE.md`, `UI_VIEWER_DYNAMIC_DISPLAY_INPUT.md`, `UI_VIEWER_BUTTON_NAVIGATION.md`, `UI_VIEWER_CLASSIC_BUTTON_HITTEST.md`, `UI_VIEWER_NATIVE_CALLBACKS.md`, `UI_VIEWER_ASYNC_AUDIO.md` und `UI_VIEWER_LOCALIZATION.md`.

### Phase 10 – Eingabe, Audio und Lokalisierung

Status: Maus, Tastatur, Fokus, MovieClip- und klassische Buttonzustände, Richtungsnavigation, präzise HitTests, sichere Native-Completion-Events, CAUD/CSMP-Audio und MSBT-Laufzeittexte umgesetzt; echte Gamepads und editierbare TextFields offen

Implementiert:

- Maus-, Tastatur-, Fokus- und Click-Events entlang stabiler Parent-Pfade;
- Fokuswechsel per Maus, Tab/Shift+Tab, Pfeiltasten und WASD;
- automatische MovieClip-Buttonzustände und Button-Owner-Routing;
- `DefineButton` und `DefineButton2` als vierteilige Sprite-kompatible Definitionen;
- Inventar von ButtonRecords, HitTest-Records, TrackAsMenu, Tastencodes und AVM1-Aktionen;
- sichere Ausführung ausschließlich der AVM1-Timeline-Aktionen `NextFrame`, `PreviousFrame`, `Play`, `Stop`, `GotoFrame` und `GotoLabel`;
- Vektor- und TXTR-Alpha-HitTests in nativen Stage-Koordinaten;
- ClipDepth-, `scrollRect`-, Runtime-`mask`- und `hitArea`-bewusste Treffer;
- controllerartige Ereignisse für Navigate, Accept und Cancel;
- sichere DKCTF-Callback-Simulation und timelinebasierte Completion-Events;
- gemeinsamer CAUD-Katalog, CSMP-DSP-ADPCM-Decoder, WAV-Export und optionale Windows-Wiedergabe;
- MSBT-Katalog mit neun Sprachcodes, exakter Text-ID-Auflösung, Fallback und dynamischen Laufzeittexten;
- Audio-/Async-, Localization- und Button-/HitTest-Inspector;
- Audio- und Lokalisierungsoptionen im kompatiblen State-Presetformat.

Noch offen:

- vollständige Capture-/Bubbling- und Weak-Listener-Semantik;
- vollständige AVM1-Ausführung außerhalb der sicheren Timeline-Aktionen;
- echte Gamepad-Hardware;
- TextField-Cursor, Auswahl, Texteingabe und IME;
- dauerhafte Audio-Loops, Mehrstimmen-Mixing und Voice-Prioritäten;
- Message-Studio-Parameterformatierung;
- Scale9-spezifische Hit-Flächen, dynamische Graphics-HitTests und seltene Shape-Formate;
- exakter Abgleich der Completion-Payloads mit dem ursprünglichen Spielhost.

Siehe `UI_VIEWER_DYNAMIC_DISPLAY_INPUT.md`, `UI_VIEWER_BUTTON_NAVIGATION.md`, `UI_VIEWER_CLASSIC_BUTTON_HITTEST.md`, `UI_VIEWER_NATIVE_CALLBACKS.md`, `UI_VIEWER_ASYNC_AUDIO.md` und `UI_VIEWER_LOCALIZATION.md`.

## Zusätzliche Dateien

- `PreLoadPak.pak`: 9580 Assets, darunter 263 TXTR; keine GFX/GFXL.
- `MiscData.pak`: 13 Assets mit unter anderem MSBT, Audio und Metadaten.
- `MaterialArchive.arc`: RFRM-MTRL-Archiv, kein PACK/TOCC-PAK.

## Endprodukt-Kriterien

Visuell vollständig:

- Bilder, Shapes, Masken, Texte, Fonts, Filter und Blend Modes werden korrekt dargestellt.
- Verschachtelte und dynamische Timelines sowie skriptgesteuerte Zustände laufen synchron.
- Requirete Ressourcen werden eindeutig aufgelöst.
- Referenzframes aus dem Spiel können strukturell reproduziert werden.

Funktional vollständig:

- ActionScript-Zustände laufen.
- Maus/Controller-Navigation funktioniert.
- Spielwerte können über Mocks und Callback-Stubs eingespeist werden.
- Native Callbacks werden sicher simuliert.
- UI-Audio kann abgespielt werden.

## Nächster Arbeitsblock

Finale Eingabe- und EditText-Stufe:

1. editierbare `TextField`-Instanzen mit Cursor, Auswahl und begrenzter Texteingabe;
2. Fokus- und Keyboard-Semantik für Inputfelder einschließlich kontrollierter Passwortdarstellung;
3. optionales Plattform-Gamepad-Mapping auf die vorhandenen Controller-Events;
4. danach Scale9-/Graphics-HitTest-Sonderfälle, Morph-Shapes und verbleibende visuelle Formatlücken.
