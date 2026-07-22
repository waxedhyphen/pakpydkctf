# UI Viewer – Morph-Shapes, Fills, Scale9-HitTests und Pixelvergleich

Stand: 2026-07-23

## Zweck

Diese Stufe schließt die wichtigsten verbliebenen klassischen SWF-Renderformate im
UI Browser:

- `DefineMorphShape` und `DefineMorphShape2`;
- `PlaceObject2`-/`PlaceObject3`-Morph-Ratios;
- radiale und fokale Gradients einschließlich Spread- und Interpolationsmodus;
- eingebettete JPEG- und Lossless-Bitmaps als Shape-Fills;
- nichtlineare Scale9-Rücktransformation für präzise HitTests;
- reproduzierbare PNG-Pixelvergleiche.

Alle Änderungen sind reine Vorschaufunktionen. SWF/GFX-, GFXL-, TXTR-, MSBT- und
PAK-Daten werden weder verändert noch neu gepackt.

## Morph-Shapes

### Unterstützte Tags

| SWF-Tag | Funktion |
|---|---|
| 46 | `DefineMorphShape` |
| 84 | `DefineMorphShape2` |
| 26 | `PlaceObject2` einschließlich `Ratio` |
| 70 | `PlaceObject3` einschließlich `Ratio` |

Der Parser liest:

- Start- und End-Bounds;
- bei Version 2 zusätzliche Start-/End-Edge-Bounds;
- skalierende und nicht skalierende Stroke-Flags;
- Morph-Fill- und Morph-Line-Styles;
- Start- und End-SHAPE-Records;
- gerade und quadratische Kanten;
- Solid-, Gradient- und Bitmap-Fills.

Die Kanten werden anhand ihrer SWF-Reihenfolge gepaart. SWF-konforme Morph-Shapes
haben korrespondierende Start- und End-Records. Abweichende Recordzahlen werden
diagnostiziert; der sichere gemeinsame Teil bleibt darstellbar.

### Ratio-Auswertung

`Ratio` liegt im Bereich `0..65535`:

```text
0       = vollständiger Startzustand
32768   = ungefähr 50 Prozent
65535   = vollständiger Endzustand
```

Interpoliert werden:

- Bounds und Edge-Bounds;
- Kantenstart, Kantenende und Kontrollpunkte;
- Farben und Alpha;
- Linienbreiten;
- Fill- und Bitmap-Matrizen;
- Gradient-Stop-Positionen;
- fokale Gradientposition.

Gerade und gekrümmte Kanten können ineinander übergehen. Dafür wird eine gerade
Kante intern als quadratische Kante mit Kontrollpunkt auf ihrer Mitte behandelt.

Morph-Raster werden nach Definition und exaktem 16-Bit-Ratio begrenzt gecacht.
Synthetische Renderdefinitionen pro Film sind ebenfalls auf 512 Zustände begrenzt.

## Gradients

Der bisherige lineare Gradientpfad wurde auf folgende Fill-Typen erweitert:

```text
0x10  linear
0x12  radial
0x13  focal
```

Unterstützte Spread-Modi:

```text
0  pad
1  reflect
2  repeat
```

Unterstützte Farbrauminterpolation:

```text
0  normale sRGB-Kanalinterpolation
1  Linear-RGB-Interpolation
```

Fokale Gradients verwenden den signierten `FIXED8`-Fokuswert. Der Fokus wird auf
einen sicheren Innenbereich des Einheitskreises begrenzt, um degenerierte
Schnittberechnungen zu verhindern.

Gradientquellen werden als begrenzte 512×512-Raster erzeugt und über die inverse
SWF-Fill-Matrix in das lokale Shape-Raster transformiert. Der gemeinsame
Gradientcache ist auf 32 MiB begrenzt.

## Eingebettete Bitmaps und Bitmap-Fills

Unterstützte Bitmap-Tags:

| Tag | Format |
|---|---|
| 6 | `DefineBits` mit `JPEGTables` |
| 21 | `DefineBitsJPEG2` |
| 35 | `DefineBitsJPEG3` mit separatem Alphakanal |
| 90 | `DefineBitsJPEG4` |
| 20 | `DefineBitsLossless` |
| 36 | `DefineBitsLossless2` |

Unterstützte Lossless-Formate:

- 8-Bit-Palette;
- 15-Bit-RGB;
- 32-Bit-RGB;
- 32-Bit-ARGB.

Bitmap-Fill-Typen:

```text
0x40  wiederholt, geglättet
0x41  abgeschnitten, geglättet
0x42  wiederholt, nearest-neighbor
0x43  abgeschnitten, nearest-neighbor
```

Die inverse Bitmap-Fill-Matrix wird direkt auf das lokale Shape-Raster angewandt.
Wiederholte Fills erzeugen nur den tatsächlich benötigten, begrenzten Tile-Bereich.
Fehlende Bitmapdefinitionen bleiben als sichtbare Diagnosefläche erhalten, statt
den gesamten Filmrender abzubrechen.

### Sicherheitsgrenzen

- maximale Bitmapkante: 8192 Pixel;
- maximal 32 Millionen Pixel pro eingebetteter Bitmap;
- maximal 256 MiB dekomprimierte eingebettete Bitmapdaten pro Film;
- maximal 8192×8192 Pixel pro temporärem Shape-/Tile-Raster;
- maximal 65.536 Tiles pro wiederholtem Fill;
- 128-MiB-LRU für ressourcenabhängige Shape-Raster.

Zlib-Daten werden mit einem Ausgabelimit dekomprimiert. JPEGs werden vollständig
geladen und anschließend gegen Abmessungs- und Pixellimits geprüft.

## Scale9-HitTests

Scale9 ist nicht affine Geometrie. Ein normaler inverser Matrix-HitTest kann deshalb
die gestreckte Mittelzone nicht korrekt auf das natürliche Sprite zurückführen.

Der neue Trefferpfad führt einen Stage-Punkt in vier Schritten zurück:

```text
Stage
→ inverse Parent-Matrix
→ gerenderte Scale9-Zielkoordinate
→ inverse Nine-Slice-Segmentabbildung
→ natürliche Sprite-/Shape-Koordinate
```

Dabei werden berücksichtigt:

- unveränderte linke/rechte und obere/untere Randsegmente;
- gestreckte oder auf null kollabierte Mittelbereiche;
- negative X-/Y-Skalierung;
- rotierte oder gescherte Elterncontainer;
- untergeordnete Alpha-, Shape-, Masken- und `scrollRect`-Geometrien.

Der Eventpfad bleibt der tatsächliche untergeordnete DisplayObject-Pfad. Nur die
Koordinatenabbildung wird nichtlinear korrigiert.

## Diagnose

Der State Inspector kennzeichnet:

- `MorphShape`;
- aktives Ratio und Prozentwert;
- Start-/End-Bounds;
- Start-/End-Kantenanzahl;
- Parserwarnungen;
- `EmbeddedBitmap`;
- Bitmapformat, Tag und Abmessungen.

Das Analysefeld ergänzt:

- Morphdefinitionen und gerenderte Morph-Placements;
- eingebettete Bitmaps;
- verwendete und fehlende Bitmap-Fills;
- Scale9-Hit-Geometrien;
- Parserfehler.

## Reproduzierbarer Format-Scanner

```bash
python PAKPY/scan_ui_visual_formats.py UIPak.pak \
  --require PreLoadPak.pak \
  --require MiscData.pak \
  --decode-bitmaps \
  --json ui_visual_formats.json
```

Der Scanner:

- sucht eingebettete `FWS`-, `CWS`- und `GFX`-Filme;
- traversiert `DefineSprite` rekursiv;
- zählt Shape-, Morph-, Bitmap- und Ratio-Tags;
- inventarisiert Fill-Typen;
- prüft optional eingebettete Bitmapdaten;
- führt weder AVM1 noch AVM2 aus;
- verändert keine Quelldatei.

Die großen DKCTF-PAKs sind nicht Teil des Repositorys. Deshalb enthält diese
Änderung keine angenommenen Corpus-Zahlen. Der Scanner erzeugt sie reproduzierbar
auf dem lokalen Datensatz.

## Pixelvergleich

```bash
python PAKPY/compare_ui_frames.py reference.png actual.png \
  --threshold 8 \
  --heatmap difference.png \
  --overlay overlay.png \
  --json comparison.json \
  --fail-above 0.5
```

Der Vergleich verlangt standardmäßig identische Abmessungen und liefert:

- exakt unterschiedliche Pixel;
- Pixel oberhalb des gewählten Kanal-Schwellwerts;
- exakten und tolerierten Übereinstimmungsprozentsatz;
- mittleren absoluten Fehler pro Kanal;
- RMSE;
- PSNR;
- maximale Kanalabweichung;
- Bounds aller Abweichungen;
- SHA-256 beider dekodierter RGBA-Bilder.

`--ignore-alpha` beschränkt die Messung auf RGB. `--fail-above` eignet sich für
automatisierte Regressionstests und beendet den Prozess mit Code 2, wenn der
zulässige Anteil überschritten wird.

Heatmaps sind für identische Pixel transparent. Abweichungen werden abhängig von
ihrer Stärke von Dunkelrot bis Gelb/Weiß dargestellt.

## Tests

Die fokussierten Tests decken ab:

- ARGB-Lossless-Dekodierung;
- lineare, radiale und fokale Gradientparameter;
- Pad-, Reflect- und Repeat-Spread;
- inverse Scale9-Segmentabbildung einschließlich Spiegelung;
- Morph-Interpolation von Bounds, Farben und Kanten;
- ungültige Morph-Offsets;
- exakte und tolerierte PNG-Vergleiche;
- Alpha-Ignorierung;
- Difference-Bounds;
- Heatmap-Transparenz;
- Größenfehler.

Die reine Pixelvergleichssuite kann ohne Tk oder PAK-Dateien ausgeführt werden.
Die vollständige Tk-Renderintegration und reale Corpusauswertung müssen weiterhin
auf einem System mit den DKCTF-PAKs geprüft werden.

## Verbleibende Grenzen

Noch offen sind:

- dynamische AVM2-`Graphics`-Zeichenbefehle und deren Hit-Geometrie;
- seltene Morph-Record-Abweichungen außerhalb des gemeinsamen Kantenbereichs;
- exakte Scaleform-Pixelidentität bei Stroke-Caps, Joins und Pixel-Hinting;
- `DefineBits`-Sonderfälle mit ungewöhnlich fragmentierten JPEG-Tabellen;
- IME, bidirektionaler Text und komplexe Graphemcluster;
- optionales echtes Plattform-Gamepad-Mapping.

Der nächste Arbeitsblock ist die dynamische `Graphics`-Runtime mit begrenzten
Zeichenbefehlen, Rendercache und präzisen Laufzeit-HitTests.
