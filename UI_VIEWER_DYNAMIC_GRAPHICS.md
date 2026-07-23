# UI Viewer – dynamische AVM2-Graphics

Stand: 2026-07-23

## Zweck

Diese Stufe ergänzt die dynamische Display-List um einen begrenzten Teil der
ActionScript-3-`Graphics`-API. Sie ist für zur Laufzeit erzeugte `Shape`-, `Sprite`-
und `MovieClip`-Objekte vorgesehen.

Alle Daten bleiben im Vorschauzustand des geöffneten Films. SWF/GFX-, PAK-, TXTR-
und MSBT-Ressourcen werden nicht verändert.

## Unterstütztes ActionScript-Muster

```actionscript
var shape:Shape = new Shape();
shape.graphics.beginFill(0xE05030, 0.9);
shape.graphics.lineStyle(2, 0xFFFFFF, 1.0);
shape.graphics.drawRoundRect(20, 20, 280, 72, 16, 16);
shape.graphics.endFill();
addChild(shape);
```

Die Runtime liefert für `graphics` einen isolierten Proxy. Dieser Proxy besitzt
keinen Host-, Datei-, Netzwerk- oder Prozesszugriff.

## Unterstützte Befehle

### Fills

- `beginFill(color, alpha)`
- `beginGradientFill(type, colors, alphas, ratios, matrix, spread, interpolation, focal)`
- `endFill()`
- `clear()`

Gradienttypen:

```text
linear
radial
radial mit focalPointRatio != 0 → fokaler Gradient
```

Spread-Modi:

```text
pad
reflect
repeat
```

Interpolationsmodi:

```text
rgb
linearRGB
```

Die bereits implementierten SWF-Gradientfunktionen werden wiederverwendet. Dadurch
verwenden statische Shapes, Morph-Shapes und dynamische Graphics denselben radialen,
fokalen und Linear-RGB-Pfad.

### Linien und Pfade

- `lineStyle(...)`
- `moveTo(x, y)`
- `lineTo(x, y)`
- `curveTo(controlX, controlY, anchorX, anchorY)`
- `cubicCurveTo(controlX1, controlY1, controlX2, controlY2, anchorX, anchorY)`

Quadratische und kubische Kurven werden adaptiv in höchstens 96 Segmente pro Kurve
zerlegt. Style-Wechsel schließen den bis dahin aufgebauten Pfad kontrolliert ab.

### Primitive

- `drawRect(x, y, width, height)`
- `drawRoundRect(x, y, width, height, ellipseWidth, ellipseHeight)`
- `drawCircle(x, y, radius)`
- `drawEllipse(x, y, width, height)`

Negative Breiten und Höhen werden normalisiert. Nicht endliche und extrem große
Koordinaten werden auf den sicheren Koordinatenbereich begrenzt.

## Rendering

Jeder dynamische Graphics-Zustand wird in ein lokales RGBA-Raster umgewandelt und
anschließend mit der normalen DisplayObject-Matrix und dem Alpha-/ColorTransform-Pfad
auf die Stage transformiert.

Reihenfolge innerhalb eines dynamischen Objekts:

```text
Graphics des Objekts
→ verknüpfte Symbol-/MovieClip-Definition
→ dynamische Kinder
```

Wenn ein ansonsten definitionsloses Objekt Graphics besitzt, wird sein generischer
Platzhalter unterdrückt.

### Cache

Der Rastercache wird nach Objektidentität und Graphics-Revision indiziert. Er ist auf
64 MiB begrenzt. Änderungen an der Command-Liste erhöhen zugleich die Dynamic- und
AVM2-Revision, sodass der bestehende Frame-Cache keine veraltete Zeichnung liefert.

## Präzise HitTests

Die Alpha-Maske des erzeugten Graphics-Rasters wird direkt in den bestehenden
präzisen HitTest-Pfad eingespeist.

Berücksichtigt werden:

- Objektposition, Skalierung und Rotation;
- verschachtelte Elternmatrizen;
- `scrollRect` und vorhandene Clip-Geometrien;
- tatsächliche transparente Pixel des gerasterten Graphics-Objekts.

Der frühere rechteckige Fallback `dynamic-bounds` wird für ein definitionsloses Objekt
entfernt, sobald eine echte Graphics-Alpha-Geometrie vorhanden ist. Transparente
Bereiche innerhalb eines Kreises, einer Kurve oder eines Gradients werden daher nicht
als rechteckiges Klickziel behandelt.

## Inspector und Diagnose

Dynamische State-Inspector-Knoten zeigen zusätzlich:

```text
AVM2 Graphics:
- Befehle
- Primitive
- lokale Bounds
- abgewiesene Befehle
```

Das Analysefeld ergänzt:

- Objekte und Primitive;
- Runtime-Aufrufe;
- gerenderte Raster und Cache-Treffer;
- abgewiesene Aufrufe.

## Sicherheitsgrenzen

- höchstens 10.000 Graphics-Befehle pro Objekt;
- höchstens 2.048 Primitive pro Objekt;
- Koordinatenbereich `-1.000.000 .. +1.000.000`;
- höchstens 96 Segmente pro Kurve;
- maximal 8192 Pixel pro temporärer Rasterkante;
- maximal 32 Millionen Pixel pro Graphics-Raster;
- 64-MiB-LRU-Rastercache;
- höchstens 15 Gradient-Stops pro Fill.

Nicht unterstützte Befehle verändern den Zustand nicht und werden als abgewiesen
gezählt.

## Noch nicht unterstützt

- `beginBitmapFill` und `lineBitmapStyle`;
- `lineGradientStyle`;
- `drawPath`, `drawTriangles` und Winding-Modi;
- native `BitmapData`-Objekte;
- Graphics auf bereits vorhandenen statischen Timeline-Instanzen;
- exakte Scaleform-Pixelidentität für Caps, Joins und Pixel-Hinting.

Diese Grenzen sind absichtlich enger als die vollständige Flash-API.

## Syntaxschutz

Der gemeldete Startfehler in `ui_browser_precise_hit.py` wurde korrigiert. Die Schleife
über die umgekehrten Hit-Regionen hatte eine fehlende schließende Klammer.

Zusätzlich kompiliert `test_repository_python_syntax.py` jetzt jede Python-Datei im
`PAKPY`-Verzeichnis, ohne sie zu importieren:

```bash
cd PAKPY
python -m unittest test_repository_python_syntax
```

Damit werden reine Parserfehler künftig unabhängig von Tk, PAK-Dateien und optionalen
Laufzeitabhängigkeiten erkannt.

## Fokussierte Tests

`test_ui_browser_graphics_model.py` prüft:

- Filled-Rectangle-Bounds;
- Pfadabschluss bei Style-Wechsel;
- quadratische und kubische Kurven;
- Gradient-Stop- und Fokalbegrenzung;
- geschlossene RoundRect-/Circle-Konturen;
- Command-Limit;
- `clear()` und Revisionen.

`test_ui_browser_avm2_graphics_patch.py` prüft zusätzlich den Runtime-Proxy, das
erzeugte Alpha-Raster und die sichere Ablehnung eines nicht unterstützten
`drawTriangles`-Aufrufs.

## Nächster Arbeitsblock

Als nächste Stufe folgen:

1. `drawPath` mit begrenztem Command-/Data-Vektor;
2. `beginBitmapFill` auf isolierten Vorschau-BitmapData-Objekten;
3. Graphics auf vorhandenen Timeline-Sprites;
4. ein visueller Regression-Runner, der mehrere Film-/Frame-Paare in einem Durchlauf
   rendert und mit Referenzbildern vergleicht;
5. danach optionales Gamepad-Mapping und IME-Unterstützung.
