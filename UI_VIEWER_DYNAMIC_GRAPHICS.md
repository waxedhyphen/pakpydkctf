# UI Viewer – dynamische AVM2-Graphics

Stand: 2026-07-23

## Status

Der begrenzte Graphics-Umfang des UI Viewers ist abgeschlossen.

Die erste Stufe implementierte:

- `clear`, `beginFill`, `beginGradientFill` und `endFill`;
- `lineStyle`;
- `moveTo`, `lineTo`, `curveTo` und `cubicCurveTo`;
- `drawRect`, `drawRoundRect`, `drawCircle` und `drawEllipse`;
- dynamische Shape-/Sprite-/MovieClip-Raster;
- Alpha-basierte Laufzeit-HitTests;
- begrenzte Command-, Primitive- und Rastercaches.

Die Abschlussstufe ergänzt:

- `drawPath` mit `evenOdd` und `nonZero`;
- `drawTriangles` mit Indizes, Culling und UVT;
- `beginBitmapFill`;
- `lineGradientStyle` und `lineBitmapStyle`;
- isolierte `BitmapData`- und `Bitmap`-Objekte;
- Graphics auf vorhandenen Timeline-Instanzen;
- korrekte Einordnung in Geschwistertiefen, Masken, Filter und Blend Modes;
- BitmapData-revisionsabhängige Rastercaches;
- präzise Hit-Geometrie für Timeline-Graphics und BitmapData.

Die vollständige technische Beschreibung, Sicherheitsgrenzen, unterstützten
BitmapData-Methoden und Testanweisungen stehen in:

- `UI_VIEWER_GRAPHICS_COMPLETE.md`
- `UI_VIEWER_VISUAL_FORMATS.md`
- `UI_VIEWER_CLASSIC_BUTTON_HITTEST.md`

## Sicherheitsprofil

Alle Graphics- und BitmapData-Zustände bleiben im Vorschauprozess. Es gibt keinen
Datei-, Netzwerk-, Prozess- oder beliebigen Python-Zugriff. SWF/GFX-, PAK-, TXTR- und
MSBT-Ressourcen werden nicht verändert.

Die Runtime bleibt bewusst auf den für die UI-Vorschau relevanten Flash-Teilumfang
begrenzt. Eine vollständige Flash-Player-, Shader- oder beliebige BitmapFilter-Runtime
ist nicht Bestandteil dieses Viewers.
