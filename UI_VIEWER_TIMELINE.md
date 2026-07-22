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

Status: laufende strukturelle Vorschau umgesetzt; ActionScript-gesteuerte Wiedergabe bleibt offen

Implementiert:

- eigener Framezustand pro stabilem MovieClip-Instanzpfad;
- globale Play-/Pause-Steuerung und `F7`;
- Vorwärts-/Rückwärts-Einzelschritt und Reset;
- Looping anhand der jeweiligen Root- und Sprite-Frameanzahl;
- Wiedergabe mit der SWF-Framerate und Tempo `0.25×` bis `4×`;
- Root-Label-Sprünge im Browser;
- Frame-, Play/Pause-, Reset- und Label-Steuerung für die ausgewählte MovieClip-Instanz im Inspector;
- manueller `sprite_frame`-Override besitzt weiterhin Vorrang;
- Scale9-Caches werden bei laufenden Unterframes invalidiert;
- Wiedergabestatus, Geschwindigkeit und Instanzframes werden in JSON-Presets gespeichert.

Validierung:

- 39 UI-Tests liefen lokal erfolgreich.
- `Options.swf` Frame 20 enthielt 70 verschachtelte MovieClips mit mehr als einem Frame.
- `btnHandheld` wurde strukturell von Frame 1 auf Frame 2 geschaltet und der komplette 1280×720-Frame ohne Renderfehler verarbeitet.

Wichtige Grenze:

- Die Vorschau lässt Timelines strukturell loopen, führt aber noch keine `DoABC`-Frame-Scripts, `gotoAndPlay`, `stop()` oder nativen Spielcallbacks aus.
- Morph-Shapes und skriptgesteuerte Übergänge bleiben offen.

Siehe `UI_VIEWER_TIMELINE_PLAYBACK.md`.

### Phase 8 – Manuelle States und Presets

Status: generische Overrides, Playback-Zustände und JSON-Presets abgeschlossen; vorgefertigte Spielprofile und Game-Mocks bleiben offen

- Sichtbarkeit, MovieClip-Frame, Text/HTML, Filter und Blend Mode pro Instanzpfad überschreibbar.
- Presets speichern Root-Frame, Overrides, Wiedergabegeschwindigkeit, globalen Play/Pause-Zustand sowie Frame/Play-Zustand jeder bekannten MovieClip-Instanz.
- Zustände bleiben während der Sitzung pro Film getrennt.

Siehe `UI_VIEWER_STATE_PRESETS.md`.

Noch offen:

- mitgelieferte Profile für Pause, Optionen, Frontend, Charakterwahl und HUD;
- Mock-Werte für Spielerzahl, Leben, Inventar, Fortschritt und Leveldaten;
- Zuordnung dieser Mocks zu Textfeldern und nativen Callback-Namen.

### Phase 9 – ActionScript 3

Status: offen

- `DoABC` und AVM2-Laufzeit.
- Konstruktoren, Frame Scripts, Events und Timer.
- `gotoAndPlay`, `gotoAndStop`, `play`, `stop`, dynamische DisplayObjects und Textupdates.
- Sichere Stubs für native Spielcallbacks.

### Phase 10 – Eingabe und Audio

Status: offen

- Maus-, Tastatur- und Controller-Fokus.
- Hit-Testing und Button-Zustände.
- CAUD/CSMP und UI-Sounds.
- Kontrollierbare Game-State-Mocks.

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
- Spielwerte können über Mocks eingespeist werden.
- Native Callbacks werden sicher simuliert.
- UI-Audio kann abgespielt werden.

## Nächster Arbeitsblock

Erste mitgelieferte State-Profile und Game-State-Mocks für Pause, Optionen, Frontend und HUD:

1. wiederverwendbare Profile aus stabilen Inspector-Pfaden;
2. benannte Mock-Werte für Leben, Spielerzahl, Banana Coins, Puzzle Pieces und Timer;
3. automatische Textfeldzuordnung anhand Variablen- und Instanznamen;
4. Profil-Auswahl direkt im UI Browser;
5. anschließend Vorbereitung der minimalen AVM2-/Frame-Script-Laufzeit.
