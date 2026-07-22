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

Status: `clip_depth`-Masken abgeschlossen; Filter, Blend Modes und Scale9 bleiben offen

Implementiert:

- Ein Placement mit `clip_depth` wird als unsichtbare Alpha-Maske behandelt.
- Die Maske gilt für alle höheren Tiefen bis einschließlich `clip_depth`.
- Gleichzeitig aktive Masken werden miteinander multipliziert und dadurch korrekt geschnitten.
- Masken in verschachtelten Sprites werden rekursiv ausgewertet; äußere Masken schneiden das komplette Sprite-Ergebnis.
- Debug-Bounds und Platzhalter werden beim Aufbau der Masken-Alphaebene unterdrückt, damit sie die Maske nicht verfälschen.
- Die Analyse zeigt Anzahl der Masken, maskierte Placements und leere Masken.

Validierung am bereitgestellten UI-Corpus:

- 13 echte ClipDepth-Placement-Tags in 11 eingebetteten GFX-Filmen.
- Unter Einbezug aller Timeline-Frames ergeben sich 381 aktive Masken-Vorkommen.
- Vorkommen unter anderem in `LoadingScreen_Common.swf`, `HUD_Bonus.swf`, `HUD_Characters.swf`, `DeathScreen/Source` und `Transition/Source`.
- Alle 11 maskenhaltigen Testfilme konnten mit dem neuen Renderer ohne Maskenfehler gerendert werden.

Noch offen innerhalb von Phase 5:

- Blend Modes aus `PlaceObject3`.
- Blur, Glow, Drop Shadow, Bevel und ColorMatrix.
- Scale9/`DefineScalingGrid`.
- Pixelgenaue Sonderfälle bei animierten Masken hängen zusätzlich von Phase 7 ab.

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

`DefineScalingGrid`/Scale9 und anschließend die in `PlaceObject3` gespeicherten Blend Modes umsetzen. Damit können skalierte Dialogfelder und Buttons ihre Randstärken behalten und additive beziehungsweise multiplizierte UI-Ebenen näher am Spiel dargestellt werden.
