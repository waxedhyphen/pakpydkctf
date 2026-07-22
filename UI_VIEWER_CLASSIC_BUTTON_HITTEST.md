# UI Viewer – Klassische SWF-Buttons und präzise HitTests

Stand: 2026-07-22

## Zweck

Diese Stufe schließt zwei bisher getrennte Eingabepfade zusammen:

1. klassische Flash-Buttons aus `DefineButton` und `DefineButton2` werden als echte vierteilige Buttondefinitionen inventarisiert und in die vorhandene Timeline-/Navigationslogik eingebunden;
2. die bisher rein rechteckigen Trefferbereiche werden durch transformierte Shape-, Textur- und Clip-Geometrien ersetzt.

Die Implementierung wirkt ausschließlich auf die Vorschau. SWF/GFX-, GFXL-, TXTR-, MSBT- und PAK-Daten werden nicht verändert.

## Klassische Buttonformate

Unterstützt werden:

- `DefineButton` (`Tag 7`);
- `DefineButton2` (`Tag 34`);
- ButtonRecords mit Character-ID, Tiefe, Matrix und Zustandsflags;
- `CXFORMWITHALPHA`, FilterList und BlendMode in `DefineButton2`;
- `TrackAsMenu`;
- ButtonCondActions einschließlich Zustandsbedingungen und Tastencode;
- begrenztes AVM1-Aktionsinventar.

### Zustände

Jede klassische Definition wird intern als Sprite-kompatible Timeline mit vier Frames dargestellt:

```text
Frame 1 = up
Frame 2 = over
Frame 3 = down
Frame 4 = hit
```

Die Frames werden aus normalen synthetischen `PlaceObject2`-/`PlaceObject3`-, `RemoveObject2`- und `ShowFrame`-Datensätzen aufgebaut. Dadurch funktionieren die vorhandenen Display-List-Caches, der State Inspector, das Button-Owner-Routing und die Timeline-Steuerung ohne einen parallelen Sonderrenderer.

Die HitTest-Liste verwendet primär die Records mit `StateHitTest`. Fehlen solche Records, wird konservativ die `up`-Liste verwendet.

## AVM1-Button-Aktionen

Alle ActionRecords werden mit Code, Name, Rohdaten und statisch erkennbarem Argument inventarisiert. Automatisch ausführbar sind ausschließlich harmlose Timeline-Aktionen:

```text
NextFrame
PreviousFrame
Play
Stop
GotoFrame
GotoLabel
```

`GotoFrame` wird von der nullbasierten AVM1-Zählung auf die einsbasierte Viewer-Timeline umgesetzt.

Andere Aktionen bleiben sichtbar, werden aber nicht ausgeführt. Dazu gehören insbesondere:

- `GetURL` und `GetURL2`;
- Variablen- und Property-Zugriffe;
- Objektkonstruktion;
- Funktions- und Methodenaufrufe;
- Sprite-Erzeugung oder -Entfernung;
- beliebige Kontrollflussprogramme.

Damit kann ein klassischer Button weder Netzwerk-, Datei- oder Prozesszugriffe auslösen noch die sichere AVM2-/Native-Callback-Schicht umgehen.

### Ereigniszuordnung

Die vorhandenen Maus- und Fokusereignisse werden auf die SWF-Bedingungen abgebildet, beispielsweise:

```text
idle -> overUp
overUp -> overDown
overDown -> overUp
overUp -> idle
```

Tastengebundene ButtonCondActions werden über die bereits isolierten Tastaturereignisse ausgelöst. Die sichere Timeline-Aktion wirkt auf die Eltern-Timeline des Buttons; bei Root-Buttons auf den Root-Film, ansonsten auf den stabilen MovieClip-Elternpfad.

## Präzise Treffergeometrie

Der Trefferpfad arbeitet in nativen Stage-Koordinaten. Das behebt zugleich die frühere Abweichung zwischen reduzierter 35–75-Prozent-Renderauflösung und den vollständigen Stage-Koordinaten des Mauszeigers.

### Vektor-Shapes

Für `DefineShape1` bis `DefineShape4` verwendet der HitTest den bereits gecachten Shape-Rasterizer:

```text
lokaler Shape-Punkt
-> inverse Placement-Matrix
-> gecachte Alpha-Maske
-> Alpha >= 8
```

Transparente Flächen innerhalb der Bounding Box sind damit nicht mehr klickbar. Löcher und gekrümmte Konturen folgen derselben gerasterten Geometrie wie die Darstellung.

### Externe TXTR-Symbole

GFXL-/TXTR-Bilder verwenden ihren tatsächlichen Alpha-Kanal. Vollständig transparente Bildbereiche werden nicht als Treffer akzeptiert.

### Text und Fallbacks

`EditText` und nicht genauer beschriebene Definitionen verwenden weiterhin transformierte lokale Bounds. Das ist bewusst konservativ, da ein pixelgenauer Glyphen-HitTest für Texte meist nicht dem Flash-Bedienmodell entspricht.

### Transformationen

Jede Geometrie speichert:

- lokale Bounds;
- Welt-Bounds für den schnellen Grobtest;
- inverse Weltmatrix;
- optionalen Alpha-Kanal und dessen lokalen Ursprung;
- aktive Clip-Geometrien.

Rotation, Skalierung, Scherung und Verschachtelung werden dadurch vor dem Alpha-Test korrekt zurückgerechnet.

## ClipDepth, scrollRect, mask und hitArea

### ClipDepth

Maskenquellen werden aus ihrer tatsächlichen Shape-/Textur-Geometrie aufgebaut. Mehrere gleichzeitig aktive ClipDepth-Masken werden geschnitten. Die Maske selbst erzeugt kein normales Klickziel.

### scrollRect

AVM2-Zuweisungen an `scrollRect` werden als lokales Rechteck des jeweiligen DisplayObjects gespeichert. Alle Treffergeometrien des Objekts und seiner Kinder erhalten diesen zusätzlichen Clip.

Unterstützt werden Rectangle-artige Werte als:

```text
{x, y, width, height}
{left, top, right, bottom}
(x, y, width, height)
Rectangle-Objekt mit x/y/width/height
```

Negative Breite oder Höhe wird auf null begrenzt.

### mask

Eine Runtime-Zuweisung an `mask` verweist ausschließlich auf einen vorhandenen stabilen DisplayObject-Pfad. Die Geometrien des Maskenobjekts werden dem Ziel und seinen Nachfahren als Clip hinzugefügt. Es findet keine dynamische Namensauswertung statt.

### hitArea

Ein vorhandener `hitArea`-Pfad ersetzt die Treffergeometrie des Zielobjekts. Der Eventpfad bleibt der Pfad des Zielobjekts, nicht der des Hilfsobjekts.

## Caches und Grenzen

Der präzise Geometrieaufbau verwendet einen LRU-Cache mit höchstens 128 Zuständen. Ein Schlüssel berücksichtigt:

- Film und Resolver;
- Root-Frame;
- manuelle Overrides;
- sichtbare Untertimeline-Frames;
- AVM2-Runtime-Revision;
- dynamische Display-List-Revision;
- klassische Button-Aktionsrevision.

Pro Zustand werden höchstens 20.000 Geometrien erzeugt. Bei Überschreitung wird der Zustand als abgeschnitten diagnostiziert, statt unbegrenzt Speicher zu belegen.

Die Geometrien werden auch nach einem Treffer im gerenderten Frame-Cache wiederhergestellt. Ein Cache-Treffer kann daher nicht mehr die Hit-Regionen eines anderen Frames übernehmen.

## Bedienung

Im UI Browser gibt es:

- `Buttons / HitTests`: öffnet den Inspector;
- `Präzise HitTests`: aktiviert oder deaktiviert die neue Geometrieprüfung;
- `Ctrl+B`: öffnet denselben Inspector.

Der Inspector besitzt zwei Registerkarten.

### DefineButton / DefineButton2

Angezeigt werden:

- Character-ID und Formatversion;
- Record- und HitRecord-Anzahl;
- TrackAsMenu;
- Zustände, Tiefen und referenzierte Characters;
- Action-Bedingungen und Tastencodes;
- sichere beziehungsweise nur inventarisierte Aktionen;
- JSON-Export.

### Hit-Geometrien

Angezeigt werden:

- stabiler Eventpfad;
- Geometrietyp;
- Welt-Bounds;
- Anzahl aktiver Clips;
- Gesamtzahl der Shape-/Textur-Alpha-Geometrien;
- ClipDepth-, scrollRect-, mask- und hitArea-Diagnosen.

Der State Inspector ergänzt bei klassischen Buttons Formatversion, Recordzahlen, Actionzahlen, TrackAsMenu und lokale Button-Bounds.

## Reproduzierbarer Scanner

```bash
python PAKPY/scan_ui_classic_buttons.py UIPak.pak \
  --json ui_classic_buttons.json
```

Der Scanner:

1. sucht eingebettete `FWS`-, `CWS`- und `GFX`-Filme;
2. untersucht Root- und Sprite-Tagstreams;
3. parst `DefineButton` und `DefineButton2` ohne Aktionen auszuführen;
4. inventarisiert Zustände, Tastencodes und AVM1-Aktionen;
5. zählt ClipDepth-Placements;
6. dedupliziert ausschließlich ABC-Module und prüft dort bekannte Eingabe-Property-Namen.

### Ergebnis des bereitgestellten Corpus

Für `UIPak.pak`:

| Messwert | Ergebnis |
|---|---:|
| eingebettete Filmpayloads | 60 |
| `DefineButton` | 0 |
| `DefineButton2` | 0 |
| klassische Button-Aktionen | 0 |
| ClipDepth-Placements | 13 |
| eindeutige ABC-Module | 40 |
| Scannerfehler | 0 |

`PreLoadPak.pak` enthält einen eingebetteten Filmpayload, aber keine klassischen Buttons oder ClipDepth-Placements. `MiscData.pak` enthält keinen eingebetteten SWF-/GFX-Film.

Die klassischen Formate sind damit generisch und synthetisch validiert; im bereitgestellten UI-Corpus werden die sichtbaren Buttons weiterhin überwiegend als MovieClips mit AVM2-Logik umgesetzt. Die präzise Shape-, Textur- und Maskengeometrie ist dagegen unmittelbar für die vorhandenen Filme relevant.

## Tests und Validierung

Acht fokussierte Modelltests decken ab:

- `DefineButton`-Records und Vier-Frame-Timeline;
- `DefineButton2`-ActionOffset, TrackAsMenu und Bedingungen;
- sichere und blockierte AVM1-Aktionen;
- einsbasierte `GotoFrame`-Umsetzung;
- Shape-Alpha zusammen mit Clip-Geometrie;
- Rectangle-Normalisierung;
- rekursive Button-Bounds ohne Endlosschleife;
- ClipDepth-Erkennung für `PlaceObject2` und `PlaceObject3`.

Sechs isolierte Parser-/Geometriemodelltests liefen lokal erfolgreich. Die Repository-Suite enthält acht fokussierte Tests; Parser, Integrationspatch und Scanner wurden syntaktisch kompiliert. Der Scanner lief über `UIPak.pak`, `PreLoadPak.pak` und `MiscData.pak` ohne Parserfehler. Das vollständige Tk-Fenster konnte in der Headless-Umgebung nicht visuell end-to-end geprüft werden.

## Verbleibende Grenzen

Noch offen sind:

- vollständige AVM1-Ausführung außerhalb der sicheren Timeline-Aktionen;
- sämtliche Flash-Capture- und Bubbling-Sonderfälle;
- Scale9-spezifische Rücktransformation einer separat skalierten Hit-Fläche;
- pixelgenaue Glyphen- und dynamische Graphics-HitTests;
- editierbare TextFields mit Cursor, Auswahl und IME;
- echte Gamepad-Hardware;
- Morph-Shapes und die verbleibenden seltenen Fill-Sonderfälle.

Der nächste Arbeitsblock ist die **finale Eingabe- und EditText-Stufe**: editierbare TextFields, Cursor/Selektion, kontrollierte Texteingabe, optionales Plattform-Gamepad-Mapping und danach die verbleibenden visuellen Format-Sonderfälle.
