# UI Viewer – vollständiger begrenzter AVM2-Graphics-Umfang

Stand: 2026-07-23

## Zweck

Diese Stufe schließt die zuvor explizit offenen Punkte der dynamischen
`flash.display.Graphics`-Vorschau:

- `drawPath`;
- `drawTriangles` einschließlich Index-, Culling- und UVT-Daten;
- `beginBitmapFill`;
- `lineGradientStyle` und `lineBitmapStyle`;
- Graphics auf vorhandenen Timeline-`Shape`-/`Sprite`-/`MovieClip`-Instanzen;
- isolierte `BitmapData`- und `Bitmap`-Objekte.

Die Implementierung bleibt eine begrenzte Vorschau-Runtime. Sie verändert keine
SWF/GFX-, PAK-, TXTR- oder MSBT-Ressourcen und stellt keinen Datei-, Netzwerk-, Prozess-
oder beliebigen Python-Zugriff bereit.

## `drawPath`

Unterstützte `GraphicsPathCommand`-Werte:

| Wert | Befehl | Datenwerte |
|---:|---|---:|
| 0 | `NO_OP` | 0 |
| 1 | `MOVE_TO` | 2 |
| 2 | `LINE_TO` | 2 |
| 3 | `CURVE_TO` | 4 |
| 4 | `WIDE_MOVE_TO` | 4 |
| 5 | `WIDE_LINE_TO` | 4 |
| 6 | `CUBIC_CURVE_TO` | 6 |

`WIDE_MOVE_TO` und `WIDE_LINE_TO` konsumieren die beiden historischen
Kompatibilitätswerte und verwenden die letzten beiden Werte als Zielkoordinate.
Abgeschnittene Datenvektoren brechen nur den aktuellen Aufruf ab und erhöhen den
Rejected-Zähler.

Unterstützte Winding-Modi:

```text
EVEN_ODD / evenOdd
NON_ZERO / nonZero
```

`evenOdd` verwendet eine XOR-Maske der geschlossenen Konturen. `nonZero` verwendet die
vereinigte gefüllte Kontur. Beide Modi speisen dieselbe Alpha-Geometrie in den präzisen
HitTest-Pfad ein.

Grenzen:

- höchstens 10.000 Path-Commands pro Aufruf;
- höchstens 80.000 Datenwerte pro Aufruf;
- weiterhin höchstens 10.000 Graphics-Befehle und 2.048 Primitive pro Objekt.

## `drawTriangles`

Unterstützt werden:

- flache `vertices`-Vektoren als `x, y`-Paare;
- optionale `indices`;
- sequenzielle Dreiecke ohne Indexvektor;
- `Culling.NONE`, `POSITIVE` und `NEGATIVE`;
- UV-Daten mit zwei Werten pro Vertex;
- UVT-Daten mit drei Werten pro Vertex;
- perspektivisch gewichtete UVT-Abtastung;
- Solid-, Gradient- und Bitmap-Fills;
- Linien auf Dreieckskanten.

Die perspektivische Interpolation verwendet die drei `t`-Werte im baryzentrischen
Nenner. Wiederholte Bitmap-Fills wickeln `u` und `v` in den Bereich `0..1` zurück.
Abgeschnittene Bitmap-Fills verwerfen Samples außerhalb dieses Bereichs.

Sicherheitsgrenzen:

- höchstens 32.768 Dreiecke pro Aufruf;
- höchstens vier Millionen direkt abgetastete Zielpixel pro UVT-Dreieck;
- degenerierte Dreiecke werden übersprungen;
- ungültige Indizes werden einzeln verworfen.

## Bitmap-Fills und Linien-Paints

### `beginBitmapFill`

```actionscript
shape.graphics.beginBitmapFill(bitmapData, matrix, repeat, smooth);
```

Unterstützt werden:

- isolierte `BitmapData`-Quellen;
- optionale affine Matrix;
- Wiederholung oder Clipping;
- Nearest-Neighbor oder bilineare Abtastung;
- Cache-Invalidierung nach jeder BitmapData-Revision.

### `lineGradientStyle`

Der aktuelle `lineStyle` kann mit linearen, radialen oder fokalen Gradients gefärbt
werden. Spread- und Interpolationsmodus verwenden denselben Renderpfad wie statische
SWF-Shapes, Morph-Shapes und normale Graphics-Fills.

### `lineBitmapStyle`

Der aktuelle Stroke kann aus `BitmapData` abgetastet werden. Matrix, Repeat und Smooth
entsprechen `beginBitmapFill`.

Ein Paint-Aufruf ohne aktiven `lineStyle` wird sicher abgewiesen.

## `BitmapData`

### Konstruktion

```actionscript
var data:BitmapData = new BitmapData(width, height, transparent, fillColor);
```

Die Daten liegen ausschließlich als RGBA-Pillow-Bild im aktuellen Vorschauprozess. Es
wird keine Datei angelegt und kein TXTR-/PAK-Asset verändert.

Unterstützte Properties:

```text
width
height
transparent
rect
```

Unterstützte Methoden:

```text
getPixel
getPixel32
setPixel
setPixel32
fillRect
copyPixels
draw
scroll
floodFill
clone
dispose
lock
unlock
```

`draw` akzeptiert eine andere isolierte `BitmapData`- oder `Bitmap`-Quelle, eine affine
Matrix, ein Clip-Rechteck und Smoothing. Allgemeine DisplayObject-Rasterisierung in
`BitmapData.draw` bleibt absichtlich gesperrt, weil sie einen separaten, reentranten
Stage-Renderer benötigen würde.

### `Bitmap`

```actionscript
var view:Bitmap = new Bitmap(data, "auto", true);
addChild(view);
```

Ein dynamisches `Bitmap`-Objekt unterstützt:

```text
bitmapData
pixelSnapping
smoothing
```

Es verwendet die normale DisplayObject-Position, Skalierung, Rotation, Alpha,
Elternmatrix, Display-List-Reihenfolge und `scrollRect`-Logik. Der präzise HitTest liest
den tatsächlichen Alphakanal der BitmapData.

### Grenzen

- maximale Bitmapkante: 8192 Pixel;
- maximal 32 Millionen Pixel pro BitmapData;
- maximal 256 MiB RGBA-Daten pro Einzelobjekt;
- maximal 32 Millionen Pixel pro kontrollierter Bitmap-Operation;
- keine nativen Dateidecoder über `BitmapData`;
- keine Shader, Filter oder beliebigen Blend-Programme.

## Graphics auf vorhandenen Timeline-Instanzen

`graphics` wird jetzt nicht nur für dynamisch erzeugte Objekte, sondern auch für
vorhandene `Shape`, `Sprite` und `MovieClip`-Instanzen angeboten, sofern die AVM2-Runtime
einen stabilen `RuntimeRef` für die Instanz besitzt.

Der Zustand wird pro stabilem Pfad gespeichert:

```text
root/4:panel
root/4:panel/17:highlight
```

Maximal 2.048 Timeline-Pfade können gleichzeitig einen eigenen Graphics-Zustand tragen.
Der Zustand wird mit der AVM2-Runtime-Generation zurückgesetzt.

### Renderreihenfolge

Der Ordering-Follow-up ersetzt den bereits vom State-Override-Renderer erfassten
`draw_unmasked`-Callback. Dadurch wird Timeline-Graphics unmittelbar vor der originalen
Definition derselben Placement-Instanz gezeichnet:

```text
Runtime-Graphics der Instanz
→ originale Shape-/Sprite-/MovieClip-Definition
→ untergeordnete DisplayObjects
```

Die Zeichnung bleibt innerhalb derselben Placement-Transaktion. Deshalb gelten weiterhin:

- Geschwistertiefen;
- ClipDepth-Masken;
- Runtime-Masken;
- Filter;
- Blend Modes;
- ColorTransform und Alpha;
- stabile Inspector- und Eventpfade.

Falls ein fremder Patch die bekannte State-Renderer-Closure ersetzt, fällt die
Installation auf den konservativen Overlay-Pfad zurück und setzt
`ui_browser.UI_GRAPHICS_TIMELINE_ORDER_EXACT` auf `False`.

## Rendering, Cache und HitTests

Der vollständige Graphics-Rastercache verwendet:

```text
Objektidentität
+ Graphics-Revision
+ BitmapData-Identität
+ BitmapData-Revision
+ Dispose-Status
```

Eine Pixeländerung in einer verwendeten BitmapData invalidiert damit den betroffenen
Graphics-Rasterzustand, auch wenn die Command-Liste selbst unverändert bleibt.

Alpha-Geometrien werden erzeugt für:

- dynamische Graphics;
- Timeline-Graphics;
- dynamische Bitmap-Objekte;
- UVT-Dreiecke;
- Gradient- und Bitmap-Strokes.

Die Geometrien berücksichtigen DisplayObject-Matrizen, Elternmatrizen, `scrollRect`,
ClipDepth und vorhandene Laufzeit-Clips.

## Inspector und Diagnose

Timeline-Knoten mit Graphics zeigen:

```text
AVM2 Graphics (Timeline-Instanz):
- Befehle
- Primitive
- Bounds
- abgewiesene Befehle
```

Das Analysefeld ergänzt:

- Anzahl der Timeline-Graphics-Zustände;
- Anzahl und Speichergröße isolierter BitmapData-Objekte;
- gerenderte Timeline-Overlays;
- gerenderte Bitmap-Objekte.

Dynamische Graphics behalten ihre vorhandenen Command-, Primitive-, Cache- und
Rejected-Zähler.

## Tests

Neue Tests:

- `test_ui_browser_graphics_complete_model.py`
  - Pixelzugriff, Fill, Copy, Clone, Draw, Scroll, FloodFill und Dispose;
  - alle `drawPath`-Commandtypen;
  - abgeschnittene Path-Daten;
  - Dreieckindizes, UVT-Metadaten und Culling;
  - Bitmap-Fills und Bitmap-Strokes;
  - BitmapData-Revision im Rastercache-Schlüssel.
- `test_ui_browser_avm2_graphics_complete_patch.py`
  - Timeline-Graphics-Proxy;
  - `drawPath`-Raster;
  - UVT-Bitmapdreieck;
  - Gradient-Stroke;
  - `BitmapData`-/`Bitmap`-Konstruktion;
  - BitmapData-Methoden und Revisionen.
- `test_ui_browser_avm2_graphics_order_fix_patch.py`
  - Austausch der gekapselten State-Renderer-Funktion ohne Änderung stabiler Pfade.

Der globale Syntax-Test kompiliert weiterhin jede Python-Datei. Die reine
Graphics-Complete-Modellsuite lief in der lokalen isolierten Testumgebung erfolgreich.
Ein vollständiger Tk-/Windows-Start und die Integrationstests müssen zusätzlich im
kompletten Checkout ausgeführt werden.

## Startprüfung

```powershell
cd C:\Users\jjabo\Documents\roms\switch\modding\PAKPY

git pull

python -m unittest `
  test_repository_python_syntax `
  test_ui_browser_graphics_model `
  test_ui_browser_graphics_complete_model `
  test_ui_browser_avm2_graphics_patch `
  test_ui_browser_avm2_graphics_complete_patch `
  test_ui_browser_avm2_graphics_order_fix_patch

python main.py
```

## Abgrenzung

Der zuvor dokumentierte offene Graphics-Block ist damit abgeschlossen. Nicht Ziel dieser
begrenzten Vorschau sind die vollständige Flash-Player-Implementierung, GPU-Shader,
beliebige BitmapData-Filter, Stage-Reentranz in `BitmapData.draw` oder eine pixelidentische
Reproduktion sämtlicher historischer Scaleform-Sonderfälle.
