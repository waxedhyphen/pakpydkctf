# UI Viewer – Timeline und Roadmap

Stand: 2026-07-22

## Ziel

Der Viewer soll die Scaleform-UIs aus `GFX`, `GFXL`, `TXTR`, `MSBT` und requireten PAKs zunächst visuell vollständig und danach interaktiv darstellen. Die Vorschau bleibt frei skalierbar und erhält das native Stage-Seitenverhältnis.

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

Die Bild-Libraries benutzen Scaleform-Tag `1009` statt normaler SWF-`DefineBits`-Tags. Der Tag enthält Character-ID, Format-ID, vorgesehene Breite/Höhe, Symbolname und ursprünglichen TGA-Dateinamen.

## Entwicklungs-Timeline

### Phase 0 – Formaterkundung

Status: abgeschlossen

- `GFX`, `GFXL`, `TXTR` und `DGRP` eingeordnet.
- Stage-Größe, Framerate, Frames, Sprites, Platzierungen, Klassen und ActionScript-Blöcke bestätigt.

### Phase 1 – Statischer UI Browser

Status: abgeschlossen

- GFX-Dateien und eingebettete Filme auswählbar.
- Root-Timeline, Frames und Frame-Labels.
- Skalierbare Stage mit beibehaltenem Seitenverhältnis.
- TXTR-Auflösung aus aktuellem und requiretem PAK.
- Position, Skalierung, Rotation, Alpha und ColorTransform.
- PNG-Export, Bounds und Platzhalter.

### Phase 2 – Vorschauorientierung

Status: abgeschlossen

- Zlib-TXTR-Vorschauen werden nur zur Anzeige vertikal gespiegelt.
- CWS-UI-Filme erhalten dieselbe vertikale Ursprungskorrektur nach dem vollständigen Frame-Rendering.
- Die frühere 180-Grad-Korrektur wurde ersetzt, weil sie links und rechts vertauschte.
- Rohdaten und Repacking bleiben unverändert.

### Phase 3 – GFXL-Library-Symbole

Status: abgeschlossen

- Parser für Scaleform-Tag `1009`.
- Verknüpfung mit `SymbolClass` und GFXL-UUID-Mapping.
- Scaleform-Anzeigemaße werden beim Rendern verwendet.
- GFXL-Library-Baum mit Einzelvorschau und Metadaten.

Validierung am bereitgestellten `UIPak.pak`:

| Library | Bildsymbole |
|---|---:|
| `UIFlashLib.swf` | 882 |
| `MasterShellLib.swf` | 440 |
| `PauseLib.swf` | 91 |
| `TransitionsLib.swf` | 17 |
| `LoadScreenJuiceLib.swf` | 16 |
| **Gesamt** | **1446** |

- 1446 von 1446 Bildsymbolen wurden mit UUIDs verbunden.
- 803 unterschiedliche externe Klassen in 1895 `PlaceObject3`-Vorkommen.
- Alle 803 Klassen werden vom Library-Index aufgelöst.
- `AudioUI.swf` enthält 120 Audio-Zuordnungen, aber keine Tag-1009-Bildsymbole.

### Phase 4 – Vektor-Shapes

Status: für den bereitgestellten UI-Corpus abgeschlossen

- `DefineShape1` bis `DefineShape4`.
- Gerade Kanten und quadratische Kurven.
- `StateMoveTo`, FillStyle0/1, LineStyle und `StateNewStyles`.
- Solid-Fills, RGBA, lineare Gradients und Linien.
- Konturen, Löcher, Alpha und ColorTransform.

Validierung:

- 625 Shape-Definitionen.
- 203 × `DefineShape1`, 47 × `DefineShape2`, 28 × `DefineShape3`, 347 × `DefineShape4`.
- 883 Solid-Fills, 96 lineare Gradients und 381 LineStyles.
- 39.986 gerade und 43.333 gekrümmte Kanten.
- 625 von 625 Shapes ohne Parserfehler.

Offen bleiben generische SWF-Sonderfälle wie Radial-/Focal-Gradients, Bitmap-Fills, exakte Caps/Joins und Morph-Shapes.

### Phase 5 – Masken, Scale9 und Effekte

Status: für die im bereitgestellten UI-Corpus verwendeten Funktionen visuell umgesetzt

Implementiert:

- `clip_depth`-Masken mit verschachtelten und gleichzeitig aktiven Masken.
- `DefineScalingGrid`/Scale9-Nine-slice.
- `PlaceObject3`-Sichtbarkeit, Ratio, CacheAsBitmap und OpaqueBackground-Metadaten.
- Blend Modes einschließlich Layer, Multiply, Alpha, Screen, Add, Erase, Overlay und HardLight.
- Filterreihenfolge: Objekt → Filter → ClipDepth → Blend Mode.
- `Glow`, `DropShadow`, `Blur` und `Bevel`.

Validierung:

- 13 ClipDepth-Tags in 11 Filmen; 381 Maskenvorkommen über die Frames.
- 56 Scaling-Grids; 558 Grid-Placements, davon 527 tatsächlich skaliert.
- 53 BlendMode-Placements: 27 Layer, 17 Multiply, 7 Alpha, 2 Normal.
- 37 Placements mit expliziter Sichtbarkeit.
- 460 Filterdatensätze:
  - 258 Glow
  - 186 DropShadow
  - 14 Blur
  - 2 Bevel

Offen bleiben pixelgenaue Scaleform-Abgleiche für anisotropen Blur, Bevel-Sonderfälle und komplexe Gruppenisolation.

### Phase 6 – Fonts und Texte

Status: eingebettete Fonts und statische/initiale `DefineEditText`-Inhalte abgeschlossen

Implementiert:

- `gfxfontlib.gfx`/`gfxfontlib.swf` aus aktuellem oder requiretem PAK.
- `DefineFont3`, `DefineFontName` und `SymbolClass`.
- `$DialogFont`, `$SubTitleFont`, `$TitleFont` und `$NormalFont`.
- Lazy-Dekodierung eingebetteter Outline-Glyphen.
- Unicode-Glyphen, Konturen und Löcher.
- Korrektes `FontClass`-Layout mit `FontHeight`.
- Scaleform-HTML, Ausrichtung, Farbe, Größe, `letterSpacing`, Absätze und HTML-Entities.
- Text durchläuft ColorTransform, Filter, Masken und Blend Modes.
- Leere dynamische Felder bleiben als Variablenplatzhalter sichtbar.

Validierung:

- 4 `DefineFont3`-Fonts mit jeweils ungefähr 9.200 Unicode-Glyphen.
- 648 `DefineEditText`-Felder.
- 348 × `$SubTitleFont`, 189 × `$NormalFont`, 111 × `$TitleFont`.
- 647 HTML-Textfelder und 885 initiale Absätze.
- Keine `DefineText`-/`DefineText2`-Tags im untersuchten Spielmaterial.

Offen:

- MSBT-Text-IDs und Sprachauswahl.
- ActionScript-Änderungen an Text, Sichtbarkeit und Formatierung.
- Pixelgenauer Font-Rasterizer-Abgleich.

### Phase 6.5 – Display-List-/State-Inspector

Status: read-only Inspector abgeschlossen

Implementiert:

- Öffnen über `State Inspector` oder `F6`.
- Root-Frame und rekursive MovieClip-Display-Lists als Tiefenbaum.
- Stabiler Instanzpfad aus Tiefe und Instanzname.
- Character-ID, SymbolClass, externe Klasse und Sichtbarkeit.
- Matrix und vollständiger ColorTransform.
- ClipDepth, Scale9, Filter und Blend Mode.
- MovieClip-Frameanzahl und Frame-Labels.
- Fontklasse, Textvariable, Initialtext und HTML-Status.
- Lazy TXTR-Auflösung für ausgewählte externe Klassen.
- Suche über Pfade, Namen, IDs, Klassen, Texte und Metadaten.
- Filter für sichtbare Instanzen.
- Öffnen/Schließen des gesamten Tiefenbaums.
- Kopierbarer Instanzpfad.
- Vollständiger JSON-State-Snapshot pro Root-Frame.
- Automatische Aktualisierung beim Film- oder Framewechsel.

Wichtige Grenze:

- Der Root-Frame entspricht dem Viewer-Regler.
- Verschachtelte MovieClips stehen wie im aktuellen statischen Renderer noch auf Frame 1.
- ActionScript und dynamisch erzeugte DisplayObjects werden noch nicht ausgeführt.

Siehe auch `UI_VIEWER_STATE_INSPECTOR.md`.

### Phase 7 – Verschachtelte Timelines

Status: offen

- Eigener Framezustand pro MovieClip-Instanz.
- Play, Stop, Loop, Labels und echte Framerate.
- Morphs und Übergangsanimationen.

### Phase 8 – Manuelle States und Presets

Status: Inspector-Grundlage abgeschlossen; Overrides und Presets offen

- Sichtbarkeit pro Instanzpfad überschreiben.
- MovieClip-Frame pro Instanz auswählen.
- Text und HTML-Text ersetzen.
- Filter und Blend Modes testweise deaktivieren.
- Presets als JSON speichern und laden.
- Presets für Pause, Optionen, Frontend, Charakterwahl und HUD.
- Mock-Werte für Spielerzahl, Leben, Inventar und Fortschritt.

### Phase 9 – ActionScript 3

Status: offen

- `DoABC` und AVM2-Laufzeit.
- Konstruktoren, Frame Scripts, Events und Timer.
- Dynamische DisplayObjects und Textupdates.
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
- Verschachtelte Timelines laufen synchron.
- Requirete Ressourcen werden eindeutig aufgelöst.
- Referenzframes aus dem Spiel können strukturell reproduziert werden.

Funktional vollständig:

- ActionScript-Zustände laufen.
- Maus/Controller-Navigation funktioniert.
- Spielwerte können über Mocks eingespeist werden.
- Native Callbacks werden sicher simuliert.
- UI-Audio kann abgespielt werden.

## Nächster Arbeitsblock

Manuelle State-Overrides und speicherbare Presets auf Basis der stabilen Inspector-Pfade:

1. Sichtbarkeit überschreiben.
2. MovieClip-Frame pro Instanz wählen.
3. Text und HTML-Text ersetzen.
4. Presets als JSON speichern und laden.
5. Erste Zustandsprofile für Pause, Optionen, Frontend und HUD erstellen.

Die Overrides werden ausschließlich auf die Vorschau-Display-List angewendet und verändern keine GFX-, GFXL-, TXTR- oder MSBT-Daten.
