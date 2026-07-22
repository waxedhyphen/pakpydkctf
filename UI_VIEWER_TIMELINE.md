# UI Viewer – Timeline und Roadmap

Stand: 2026-07-22

## Ziel

Der Viewer soll die Scaleform-UIs aus `GFX`, `GFXL`, `TXTR`, `MSBT` und requireten PAKs darstellen. Das Fenster bleibt frei skalierbar; die native Stage-Proportion bleibt erhalten. Das Ziel ist zuerst eine visuell vollständige, danach eine interaktive Vorschau.

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

Die Bild-Libraries benutzen Scaleform-Tag `1009` statt normaler SWF-`DefineBits`-Tags. Der Tag enthält Character-ID, Format-ID, vorgesehene Breite/Höhe, Symbolname und ursprünglichen TGA-Dateinamen. `SymbolClass` verbindet die Character-ID mit dem exportierten Klassennamen.

## Entwicklungs-Timeline

### Phase 0 – Formaterkundung

Status: abgeschlossen

- `GFX`, `GFXL`, `TXTR` und `DGRP` eingeordnet.
- Stage-Größe, Framerate, Frames, Sprites, Platzierungen, Klassen und ActionScript-Blöcke bestätigt.

### Phase 1 – Statischer UI Browser

Status: abgeschlossen

- GFX-Dateien und eingebettete Filme auswählbar.
- Skalierbare Stage mit beibehaltenem Seitenverhältnis.
- Root-Timeline, Frames und Frame-Labels.
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
- Neuer GFXL-Library-Baum im UI Browser.
- Einzelne Symbole zeigen Name, Character-ID, TGA-Dateiname, UUID, Maße, Codec und Quell-PAK.

Validierung am bereitgestellten `UIPak.pak`:

| Library | Bildsymbole |
|---|---:|
| `UIFlashLib.swf` | 882 |
| `MasterShellLib.swf` | 440 |
| `PauseLib.swf` | 91 |
| `TransitionsLib.swf` | 17 |
| `LoadScreenJuiceLib.swf` | 16 |
| **Gesamt** | **1446** |

- 1446 von 1446 Bildsymbolen wurden ohne Parserfehler mit UUIDs verbunden.
- In 16 GFX-Containern wurden 803 unterschiedliche externe Klassen in 1895 `PlaceObject3`-Vorkommen gefunden.
- Alle 803 Klassen werden vom neuen Library-Index aufgelöst.
- `AudioUI.swf` enthält 120 Audio-Zuordnungen, aber keine Tag-1009-Bildsymbole.

## Zusätzliche Dateien

- `PreLoadPak.pak`: 9580 Assets, darunter 263 TXTR; keine GFX/GFXL. Als requirete Ressourcenquelle weiterhin relevant.
- `MiscData.pak`: 13 Assets mit unter anderem MSBT, Audio und Metadaten; keine GFX/GFXL.
- `MaterialArchive.arc`: einzelnes RFRM-MTRL-Archiv, kein PACK/TOCC-PAK; für den aktuellen Scaleform-Pfad nicht erforderlich.

## Was Phase 3 praktisch ermöglicht

- Alle bildbasierten UI-Symbole durchsuchen.
- Scaleform-Klassenname, TXTR-UUID und Quell-PAK eines Buttons, Icons oder Hintergrunds feststellen.
- Unterschiede zwischen TXTR-Speichermaß und Scaleform-Anzeigemaß erkennen.
- Fehlende requirete Texturen gezielt diagnostizieren.
- Externe Bilder in normalen GFX-Filmen mit den vorgesehenen Maßen rendern.

## Noch zu erledigen

### Phase 4 – Vektor-Shapes

Status: für den bereitgestellten UI-Corpus abgeschlossen; generische SWF-Sonderfälle bleiben offen

Implementiert:

- `DefineShape1`, `DefineShape2`, `DefineShape3` und `DefineShape4` werden aus den Shape Records dekodiert.
- Gerade Kanten und quadratische Kurven werden zu verbundenen Konturen zusammengesetzt.
- `StateMoveTo`, FillStyle0/1, LineStyle und `StateNewStyles` werden berücksichtigt.
- Solid-Fills, RGBA, padded lineare Gradients und solide Linien werden gerendert.
- Even/Odd-Konturen, Löcher, Alpha und der Display-List-`ColorTransform` werden angewendet.
- Die Vektor-Shapes ersetzen im normalen UI-Frame die früheren Bounds-Platzhalter.

Validierung am bereitgestellten UI-Corpus:

- 625 Shape-Definitionen aus 55 GFX/GFXL-Filmen.
- 203 × `DefineShape1`, 47 × `DefineShape2`, 28 × `DefineShape3`, 347 × `DefineShape4`.
- 883 Solid-Fills, 96 lineare Gradients und 381 LineStyles.
- 39.986 gerade und 43.333 gekrümmte Kanten.
- 625 von 625 Shapes ohne Parserfehler dekodiert.

Noch offen innerhalb der generischen Shape-Unterstützung:

- Radial-/Focal-Gradients und Bitmap-Fills werden geparst, sind im untersuchten UI-Corpus aber nicht vorhanden und besitzen vorerst nur einen Fallback.
- Exakte SWF-Caps, Miter- und Spezial-Joins müssen noch pixelgenau nachgebildet werden.
- Morph-Shapes gehören weiterhin zur Timeline-/Animationsphase.

### Phase 5 – Masken und Effekte

Status: für die im bereitgestellten UI-Corpus verwendeten Masken, Scale9-Grids, Blend Modes und Filter visuell umgesetzt; pixelgenaue Scaleform-Sonderfälle bleiben offen

Implementiert – ClipDepth:

- Ein Placement mit `clip_depth` wird als unsichtbare Alpha-Maske behandelt.
- Die Maske gilt für alle höheren Tiefen bis einschließlich `clip_depth`.
- Gleichzeitig aktive Masken werden miteinander multipliziert und dadurch korrekt geschnitten.
- Masken in verschachtelten Sprites werden rekursiv ausgewertet; äußere Masken schneiden das komplette Sprite-Ergebnis.
- Debug-Bounds und Platzhalter werden beim Aufbau der Masken-Alphaebene unterdrückt.
- Die Analyse zeigt Anzahl der Masken, maskierte Placements und leere Masken.

Validierung – ClipDepth:

- 13 echte ClipDepth-Placement-Tags in 11 eingebetteten GFX-Filmen.
- Unter Einbezug aller Timeline-Frames ergeben sich 381 aktive Masken-Vorkommen.
- Vorkommen unter anderem in `LoadingScreen_Common.swf`, `HUD_Bonus.swf`, `HUD_Characters.swf`, `DeathScreen/Source` und `Transition/Source`.

Implementiert – Scale9/`DefineScalingGrid`:

- `DefineScalingGrid` (Tag 78) wird gelesen und an die jeweilige Sprite-Definition gebunden.
- Skalierte Sprites werden als Nine-slice-Fläche aufgebaut: Ecken behalten ihre Größe, Kanten werden nur auf einer Achse und das Zentrum auf beiden Achsen skaliert.
- Negative X/Y-Skalierung bleibt als Spiegelung erhalten.
- Nicht unterstützte oder beschädigte Sonderfälle fallen auf das normale affine Rendering zurück und werden gezählt.
- Die Analyse zeigt Scale9-Placements und Fallbacks.

Validierung – Scale9:

- 56 `DefineScalingGrid`-Definitionen; alle 56 verweisen auf `SpriteDef`-Symbole.
- 558 Grid-Placements über die untersuchten Timeline-Frames.
- Alle 558 Placements sind achsenparallel; 527 davon verwenden eine tatsächliche X- oder Y-Skalierung.
- Repräsentative Frames aller 49 GFX-Filme wurden mit Dummy-Ressourcen ohne Scale9-Fallback oder Renderfehler verarbeitet.

Implementiert – PlaceObject3 und Blend Modes:

- Filterlisten werden strukturiert gelesen und am jeweiligen Placement behalten.
- Explizite `visible`-Werte aus `PlaceObject3` werden angewendet.
- `Layer`, `Multiply` und `Alpha` werden als isolierte Ebenen beziehungsweise Zielkomposition gerendert.
- Die generischen Modi `Screen`, `Lighten`, `Darken`, `Difference`, `Add`, `Subtract`, `Invert`, `Erase`, `Overlay` und `HardLight` sind ebenfalls implementiert.
- Blend-Komposition erfolgt nach ClipDepth-Masking, damit maskierte Blend-Ebenen korrekt mit dem Zielbild verrechnet werden.
- Die Analyse listet verwendete Blend Modes und ihre Placement-Anzahl.

Validierung – PlaceObject3:

- 53 BlendMode-Placements: 27 × `Layer`, 17 × `Multiply`, 7 × `Alpha`, 2 × explizites `Normal`.
- 37 Placements mit explizitem Sichtbarkeitsfeld.
- 460 einzelne Filterdatensätze konnten ohne Parsefehler gelesen werden.

Implementiert – im Spielmaterial verwendete Filter:

- `Glow`, `DropShadow`, `Blur` und `Bevel` werden aus ihren FIXED-/FIXED8-Parametern dekodiert.
- Farbe, Alpha, Blur-Ausdehnung, Stärke, Winkel, Distanz, Passes sowie Inner-/Knockout-/CompositeSource-/OnTop-Flags werden berücksichtigt.
- Filter werden in Dateireihenfolge auf eine isolierte Placement-Ebene angewendet.
- Die Reihenfolge ist Objekt → Filter → ClipDepth-Maske → Blend Mode.
- Filterberechnungen werden auf den sichtbaren Objektbereich samt Effekt-Rand zugeschnitten, damit große Stage-Flächen nicht unnötig vollständig weichgezeichnet werden.
- Die Analyse zeigt gefilterte Placements, angewendete Filtertypen und nicht unterstützte Datensätze.

Filter-Inventar im bereitgestellten UI-Corpus:

- 258 × `Glow`
- 186 × `DropShadow`
- 14 × `Blur`
- 2 × `Bevel`
- 0 × `ColorMatrix`, `Convolution`, `GradientGlow` oder `GradientBevel`

Noch offen innerhalb von Phase 5:

- Die Pillow-GaussianBlur-Approximation muss für pixelgenaue Vergleiche noch gegen Scaleforms anisotropen Blur-Kernel abgeglichen werden.
- Bevel-Caps und komplexe innere/äußere Knockout-Kombinationen sind funktional vorhanden, aber noch nicht pixelgenau validiert.
- Exakte SWF-Gruppen-/Isolationsecken bei komplex verschachtelten Blend-Ebenen müssen noch abgeglichen werden.
- Pixelgenaue Sonderfälle bei animierten Scale9-Sprites, Masken und Filtern hängen zusätzlich von Phase 7 ab.

### Phase 6 – Fonts, Texte und MSBT

- Eingebettete Fonts und Glyphen.
- `DefineText`, `DefineText2` und vollständiges `DefineEditText`.
- `gfxfontlib.swf`-Imports.
- MSBT-Text-IDs und Sprachauswahl.

### Phase 7 – Verschachtelte Timelines

- Eigener Framezustand pro MovieClip-Instanz.
- Play, Stop, Loop, Labels und echte Framerate.
- Morphs und Übergangsanimationen.

### Phase 8 – Zustands-Presets

- Display-List-Inspector.
- Sichtbarkeit, Frames und Textwerte manuell überschreiben.
- Presets für Pause, Optionen, Frontend, Charakterwahl und HUD.
- Mock-Werte für Spielerzahl, Leben, Inventar und Fortschritt.

### Phase 9 – ActionScript 3

- `DoABC` und AVM2-Laufzeit.
- Konstruktoren, Frame Scripts, Events und Timer.
- Dynamische DisplayObjects und Textupdates.
- Sichere Stubs für native Spielcallbacks.

### Phase 10 – Eingabe und Audio

- Maus-, Tastatur- und Controller-Fokus.
- Hit-Testing und Button-Zustände.
- CAUD/CSMP und UI-Sounds.
- Kontrollierbare Game-State-Mocks.

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

Phase 6 beginnt mit eingebetteten Fonts und statischen Text-Tags. Danach folgt ein Display-List-/State-Inspector, mit dem Instanznamen, Sichtbarkeit, Frames, Filter, Blend Modes und Textwerte pro UI-Zustand untersucht und manuell überschrieben werden können, bevor eine vollständige AVM2-Laufzeit vorhanden ist.
