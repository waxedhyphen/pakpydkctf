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

Offen bleiben MSBT-Zuordnung, Laufzeittexte und ein pixelgenauer Font-Rasterizer-Abgleich.

### Phase 6.5 – Display-List-/State-Inspector

Status: abgeschlossen

- Rekursiver Tiefenbaum mit stabilen Instanzpfaden.
- Character-ID, Klasse, Sichtbarkeit, Matrix, ColorTransform, ClipDepth, Scale9, Filter und Blend Mode.
- MovieClip-Frames/Labels sowie Fontklasse und Text.
- Suche, Sichtbarkeitsfilter, Pfadkopie und JSON-Snapshot.

Siehe `UI_VIEWER_STATE_INSPECTOR.md`.

### Phase 7 – Verschachtelte Timelines

Status: laufende strukturelle Vorschau umgesetzt; AVM2-Frame-Scripts steuern inzwischen einen sicheren Teilumfang

- eigener Framezustand pro stabilem MovieClip-Instanzpfad;
- globale Play-/Pause-Steuerung und `F7`;
- Vorwärts-/Rückwärts-Einzelschritt und Reset;
- Looping anhand der jeweiligen Root- und Sprite-Frameanzahl;
- Wiedergabe mit der SWF-Framerate und Tempo `0.25×` bis `4×`;
- Root- und Sprite-Label-Sprünge;
- manueller `sprite_frame`-Override besitzt Vorrang;
- Wiedergabestatus, Geschwindigkeit und Instanzframes werden in JSON-Presets gespeichert;
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay` werden aus kontrolliert interpretierten Frame Scripts angewendet.

Wichtige Grenze: Events, Timer, dynamisch erzeugte DisplayObjects und allgemeine Konstruktorlogik fehlen weiterhin.

Siehe `UI_VIEWER_TIMELINE_PLAYBACK.md`, `UI_VIEWER_AVM2.md` und `UI_VIEWER_AVM2_RUNTIME.md`.

### Phase 7.5 – Interaktive Performance

Status: umgesetzt

- Display-List-, Stage-Frame- und pfadspezifische Scale9-Caches;
- leichter MovieClip-Pfad-Scan statt vollständigem Inspector-Aufbau pro Tick;
- gedrosselte Inspector-Aktualisierung;
- adaptive Vorschauauflösung von 35 bis 75 Prozent während Play/Scrubbing;
- volle native Auflösung nach Pause und beim PNG-Export;
- AVM2-Runtime-Revisionsnummer im Frame-Cache-Schlüssel.

Siehe `UI_VIEWER_PERFORMANCE.md`.

### Phase 8 – Manuelle States, Profile und Game-Mocks

Status: generische Overrides, Playback-Zustände, Profile und Text-Mocks abgeschlossen

Implementiert:

- Sichtbarkeit, MovieClip-Frame, Text/HTML, Filter und Blend Mode pro Instanzpfad überschreibbar;
- Presets speichern Root-Frame, Overrides, Wiedergabe und MovieClip-Instanzzustände;
- acht mitgelieferte Analyseprofile für HUD, Time Attack, Pause, Optionen, Frontend, Shop und Charakterwahl;
- Mock-Werte für Spielerzahl, Leben, Banana Coins, Puzzle Pieces, Timer, Punkte, Levelname, Bananen, KONG-Buchstaben und Fortschritt;
- automatische EditText-Zuordnung anhand `variable_name`, Instanzname und stabilen Elternpfaden;
- Mock-Editor mit Zuordnungsübersicht und `F8`;
- manuelle Text-Overrides besitzen Vorrang vor AVM2-Runtime und Mocks;
- Profile und Mock-Werte werden im JSON-Preset gespeichert;
- aktive Game-Mocks können über sichere `ExternalInterface.call`-Stubs gelesen werden;
- Zustände bleiben während der Sitzung pro Film getrennt.

Siehe `UI_VIEWER_STATE_PRESETS.md` und `UI_VIEWER_GAME_STATE_MOCKS.md`.

Noch offen:

- vollständige Zuordnung realer nativer Callback-Namen des Spiels;
- MSBT-Text-IDs und Sprachauswahl;
- dynamisch erst durch AVM2 erzeugte Textfelder und DisplayObjects.

### Phase 9 – ActionScript 3

Status: Strukturparser, Frame-Script-Inventar und kontrollierte Interpreter-Runtime umgesetzt; vollständige AVM2-Semantik offen

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
- `stop`, `play`, `gotoAndStop` und `gotoAndPlay` für Root- und Untertimelines;
- Property-Lesen und -Schreiben auf vorhandenen Instanzen;
- `visible`, `alpha`, `text` und `htmlText`;
- Whitelist-Registry für sichere native Callback-Stubs;
- lesende Anbindung vorhandener Game-State-Mocks an `ExternalInterface.call`;
- AVM2-Inspector über `F9` und Runtime-Neuausführung über `F10`;
- Frame-Script- und Runtime-Metadaten im State Inspector.

Sicherheitsgrenzen:

- höchstens 8192 Instruktionen pro Ausführung;
- maximale Aufruftiefe 16;
- höchstens acht direkt verkettete Frame-Sprünge;
- nicht unterstützte Opcodes brechen nur die betroffene Methode ab;
- keine beliebigen Host-, Datei-, Prozess- oder Netzwerkaufrufe.

Validierung:

- fünf synthetische ABC-/Frame-Script-Tests für Strukturparser, DoABC, Disassembly, `addFrameScript`, Timeline-Aktionen und JSON-Inventar;
- fünf Runtime-Tests für Property-Zuweisungen, Branches, Callback-Mocks, Timeline-Sprünge und manuellen Override-Vorrang.

Noch offen:

- vollständige AVM2-Objekt-, Prototyp- und Klassen-Semantik;
- Konstruktor- und Script-Initializer-Ausführung außerhalb der Frame-Script-Zuordnung;
- Exception-Handling und komplexe Iteration;
- Events und Timer;
- dynamische DisplayObjects;
- corpus-spezifische native Callback-Implementierungen;
- MSBT- und Sprachlogik.

Siehe `UI_VIEWER_AVM2.md` und `UI_VIEWER_AVM2_RUNTIME.md`.

### Phase 10 – Eingabe und Audio

Status: offen

- Maus-, Tastatur- und Controller-Fokus.
- Hit-Testing und Button-Zustände.
- CAUD/CSMP und UI-Sounds.
- Anbindung kontrollierbarer Game-State-Mocks an native Callbacks.

## Zusätzliche Dateien

- `PreLoadPak.pak`: 9580 Assets, darunter 263 TXTR; keine GFX/GFXL.
- `MiscData.pak`: 13 Assets mit unter anderem MSBT, Audio und Metadaten.
- `MaterialArchive.arc`: RFRM-MTRL-Archiv, kein PACK/TOCC-PAK.

## Endprodukt-Kriterien

Visuell vollständig:

- Bilder, Shapes, Masken, Texte, Fonts, Filter und Blend Modes werden korrekt dargestellt.
- Verschachtelte Timelines und skriptgesteuerte Zustände laufen synchron.
- Requirete Ressourcen werden eindeutig aufgelöst.
- Referenzframes aus dem Spiel können strukturell reproduziert werden.

Funktional vollständig:

- ActionScript-Zustände laufen.
- Maus/Controller-Navigation funktioniert.
- Spielwerte können über Mocks und Callback-Stubs eingespeist werden.
- Native Callbacks werden sicher simuliert.
- UI-Audio kann abgespielt werden.

## Nächster Arbeitsblock

AVM2-Objekt- und Event-Grundlagen:

1. kontrollierte Ausführung ausgewählter Konstruktor- und Script-Initializer;
2. zusätzliche DisplayObject-Properties und einfache Objekt-/Array-Semantik;
3. EventDispatcher-Grundfunktionen für Frame-, Button- und Fokusereignisse;
4. corpus-spezifische Inventarisierung realer `ExternalInterface`- und nativer Callback-Namen;
5. sichere Callback-Implementierungen für die vorhandenen Game-State-Rollen.
