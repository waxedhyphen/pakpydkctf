# UI Viewer – Timeline und Roadmap

Stand: 2026-07-22

## Ziel

Der Viewer soll die Scaleform-UIs aus `GFX`, `GFXL`, `TXTR`, `MSBT` und requireten PAKs darstellen und konkrete Ingame-Zustände untersuchbar machen. Die Vorschau bleibt frei skalierbar, die native Stage-Proportion wird beibehalten und alle manuellen Änderungen bleiben reine Preview-Overrides.

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
- Die frühere 180-Grad-Korrektur wurde ersetzt, da sie links und rechts vertauschte.
- Rohdaten und Repacking bleiben unverändert.

### Phase 3 – GFXL-Library-Symbole

Status: abgeschlossen

- Parser für Scaleform-Tag `1009`.
- Verknüpfung mit `SymbolClass` und GFXL-UUID-Mapping.
- Scaleform-Anzeigemaße werden beim Rendern verwendet.
- GFXL-Library-Baum mit Symbol-, UUID-, Größen-, Codec- und Quellinformationen.

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
- 803 unterschiedliche externe Klassen in 1895 `PlaceObject3`-Vorkommen werden aufgelöst.
- `AudioUI.swf` enthält 120 Audio-Zuordnungen, aber keine Tag-1009-Bildsymbole.

### Phase 4 – Vektor-Shapes

Status: für den bereitgestellten UI-Corpus abgeschlossen; generische SWF-Sonderfälle bleiben offen

Implementiert:

- `DefineShape1`, `DefineShape2`, `DefineShape3` und `DefineShape4`.
- Gerade Kanten und quadratische Kurven.
- FillStyle0/1, LineStyle und `StateNewStyles`.
- Solid-Fills, RGBA, lineare Gradients und Linien.
- Even/Odd-Konturen, Löcher, Alpha und ColorTransform.

Corpus:

- 625 Shape-Definitionen aus 55 GFX/GFXL-Filmen.
- 883 Solid-Fills, 96 lineare Gradients und 381 LineStyles.
- 625 von 625 Shapes ohne Parserfehler.

Offen:

- Radial-/Focal-Gradients und Bitmap-Fills außerhalb des vorhandenen Corpus.
- Pixelgenaue Caps, Miter und Spezial-Joins.
- Morph-Shapes.

### Phase 5 – Masken, Scale9 und Effekte

Status: für die im bereitgestellten UI-Corpus verwendeten Funktionen visuell umgesetzt

Implementiert:

- inklusive `clip_depth`-Masken und Schnitt mehrerer aktiver Masken;
- rekursive Masken in verschachtelten Sprites;
- `DefineScalingGrid` und Nine-slice-Rendering;
- explizite `PlaceObject3`-Sichtbarkeit;
- Layer, Multiply, Screen, Lighten, Darken, Difference, Add, Subtract, Invert, Alpha, Erase, Overlay und HardLight;
- Glow, DropShadow, Blur und Bevel;
- Reihenfolge Objekt → Filter → ClipDepth → Blend Mode.

Corpus:

- 13 ClipDepth-Placement-Tags in 11 Filmen;
- 56 Scaling-Grids und 558 Grid-Placements;
- 53 BlendMode-Placements;
- 258 Glow-, 186 DropShadow-, 14 Blur- und 2 Bevel-Filter.

Offen:

- pixelgenauer Abgleich des Scaleform-Blur-Kernels;
- seltene Bevel-/Knockout-Sonderfälle;
- komplexe Gruppen-Isolation bei stark verschachtelten Blend-Ebenen.

### Phase 6 – Fonts und Texte

Status: eingebettete Fonts und initiale `DefineEditText`-Inhalte abgeschlossen; MSBT- und Laufzeittexte bleiben offen

Implementiert:

- `gfxfontlib.swf`, `DefineFont3`, `DefineFontName` und `SymbolClass`;
- `$DialogFont`, `$SubTitleFont`, `$TitleFont` und `$NormalFont`;
- lazy dekodierte Unicode-Outline-Glyphen;
- korrekte Scaleform-`FontClass`-/`FontHeight`-Anordnung;
- HTML-Absätze, Farbe, Größe, Ausrichtung, `letterSpacing` und Entities;
- Text durch ColorTransform, Filter, Masken und Blend Modes;
- Platzhalter für spätere dynamische Textfelder.

Corpus:

- vier `DefineFont3`-Fonts mit jeweils rund 9.200 Unicode-Glyphen;
- 648 `DefineEditText`-Felder;
- 647 HTML-Textfelder und 885 initiale Absätze;
- keine `DefineText`-/`DefineText2`-Tags im untersuchten Material.

Offen:

- MSBT-Text-IDs und Sprachauswahl;
- ActionScript-Änderungen an `text`, `htmlText` und Formatierung;
- pixelgenauer Font-Rasterizer-Abgleich.

### Phase 6.5 – Display-List-/State-Inspector

Status: read-only Inspector abgeschlossen

- Öffnen über `State Inspector` oder `F6`.
- Root-Frame und rekursive MovieClip-Display-Lists als Tiefenbaum.
- Stabiler Pfad aus Tiefe und Instanzname.
- Character-ID, Klasse, Sichtbarkeit, Matrix und ColorTransform.
- ClipDepth, Scale9, Filter und Blend Mode.
- MovieClip-Frames, Labels, Fontklasse und Text.
- Suche, Sichtbarkeitsfilter, Pfadkopie und JSON-Snapshot.
- Automatische Aktualisierung bei Film- oder Framewechsel.

Siehe `UI_VIEWER_STATE_INSPECTOR.md`.

### Phase 7 – Verschachtelte Timelines

Status: manueller Framezugriff vorhanden; automatische Laufzeit offen

Bereits möglich:

- MovieClip-Frame pro stabilem Instanzpfad manuell auswählen.
- Der Inspector rekonstruiert den gewählten Unterframe und dessen Kinder.

Noch offen:

- eigener laufender Framezustand pro MovieClip-Instanz;
- Play, Stop, Loop und echte Framerate;
- automatische Label- und Übergangssteuerung;
- Morphs und zeitabhängige Filter-/Masken-/Scale9-Zustände.

### Phase 8 – Manuelle States und Presets

Status: generische Overrides und JSON-Presets abgeschlossen; vorgefertigte Spielprofile und Game-Mocks bleiben offen

Implementiert:

- Sichtbarkeit pro stabilem Instanzpfad auf Original, sichtbar oder versteckt setzen.
- MovieClip-Frame pro Instanz auswählen.
- EditText als Plaintext oder Scaleform-HTML ersetzen.
- Filter und Blend Mode pro Placement testweise deaktivieren.
- Overrides werden direkt im Inspector angezeigt und bei Framewechseln neu angewendet.
- Overrides bleiben beim Wechsel zwischen Filmen innerhalb der laufenden Browser-Sitzung getrennt gespeichert.
- Presets speichern Root-Frame, Filmname, Quell-PAK und alle Pfad-Overrides als JSON.
- Presets können geladen, ersetzt und vollständig gelöscht werden.
- Scale9-Caches werden nach Änderungen invalidiert, damit pfadspezifische Unterzustände nicht aus einem alten Frame übernommen werden.
- Keine GFX-, GFXL-, TXTR- oder MSBT-Daten werden verändert.

Bedienung und Preset-Schema: `UI_VIEWER_STATE_PRESETS.md`.

Noch offen:

- mitgelieferte Profile für Pause, Optionen, Frontend, Charakterwahl und HUD;
- Mock-Werte für Spielerzahl, Leben, Inventar, Fortschritt und Leveldaten;
- Zuordnung dieser Mocks zu Textfeldern und nativen Callback-Namen.

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

## Validierung des aktuellen Stands

- 38 UI-Parser-, Renderer-, Font-, Inspector- und Override-Tests liefen lokal erfolgreich.
- Ein realer `Options.swf`-Frame wurde mit Text- und verschachteltem MovieClip-Frame-Override ohne Renderfehler verarbeitet.
- Der vollständige Tk-Dialog kann in der headless Entwicklungsumgebung nicht visuell gegen das laufende Spiel verglichen werden.

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

Phase 7 wird als laufende Vorschau umgesetzt:

1. eigener Framezähler pro MovieClip-Instanzpfad;
2. Play/Pause und Einzelschritt im UI Browser;
3. Looping anhand der jeweiligen Sprite-Frameanzahl;
4. Frame-Labels im Inspector und als direkte Sprungziele;
5. Preset-Optionen für Startframe, Wiedergabestatus und Geschwindigkeit.

Danach folgen erste mitgelieferte State-Profile und Game-State-Mocks für Pause, Optionen, Frontend und HUD.
