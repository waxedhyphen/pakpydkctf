# UI Viewer – Performance und Vorschauqualität

Stand: 2026-07-22

## Hintergrund

Die erste laufende Timeline-Vorschau baute pro Bild mehrfach den vollständigen State-Inspector-Baum auf, rekonstruierte dieselben SWF-Display-Lists wiederholt und verwarf Scale9-Zwischenergebnisse bei jedem Tick. Bei komplexen Filmen wie `Options.swf` führte das zu ungefähr einem sichtbaren Bild pro Sekunde.

## Optimierungen

Der Viewer verwendet jetzt:

- einen LRU-Cache für `build_display_list(tags, frame)`;
- einen leichten MovieClip-Pfad-Scan statt eines vollständigen Inspector-Aufbaus für jeden Statusaufruf;
- einen Cache für fertig zusammengesetzte Stage-Frames;
- getrennte Scale9-Caches pro Instanzpfad und Unterframe;
- gedrosselte Inspector-Aktualisierung während laufender Wiedergabe;
- eine reduzierte Renderauflösung beim Abspielen oder schnellen Framewechsel;
- bilineare Skalierung während der schnellen Vorschau;
- volle native Auflösung beim PNG-Export.

Movie-Definitionen werden nur erneut an einen Timeline-State-Store gebunden, wenn der Store tatsächlich gewechselt wurde.

## Vorschauqualität

Unterhalb der Timeline-Leiste befindet sich `Vorschauqualität`:

- `Auto`: während Play und Scrubbing adaptive Auflösung zwischen 35 und 75 Prozent; nach einer kurzen Pause wird der aktuelle Frame in voller Auflösung nachgerendert;
- `100%`: immer native Stage-Auflösung;
- `75%`, `50%`, `35%`: feste Vorschauauflösung für langsame Rechner oder besonders komplexe Filme.

`Auto` ist der Standard. Falls ein Film weiterhin zu langsam ist, sollte zuerst `35%` getestet werden. Die Displaygröße im Fenster bleibt gleich; nur die intern gerenderte Pixelzahl wird reduziert.

## Caches

`Render-Cache leeren` entfernt:

- fertig gerenderte Frame-Bilder;
- rekonstruierte Display-Lists;
- pfad- und framebezogene Scale9-Zwischenergebnisse.

Der Frame-Cache besitzt ein Speicherbudget von 160 MiB und verwirft die ältesten Bilder automatisch.

## Qualitätsverhalten

Die schnelle Vorschau ist für Navigation und Zustandsanalyse gedacht. Glow-, Blur- und Drop-Shadow-Radien können bei reduzierter Auflösung leicht von der nativen Darstellung abweichen. Nach dem Pausieren wird im Modus `Auto` wieder mit 100 Prozent gerendert.

`PNG speichern` rendert den ausgewählten Zustand unabhängig von der Vorschauqualität immer in der nativen SWF-Stage-Auflösung.

## Diagnose

Im Analysefeld wird zusätzlich angezeigt:

```text
Performance:
- Renderzeit: 84.2 ms
- Vorschauauflösung: 50%
- Frame-Cache: Treffer
- Display-List-Cache: 1240 Treffer / 91 neu
```

Damit lässt sich unterscheiden, ob ein Frame neu zusammengesetzt oder direkt aus dem Cache geladen wurde.
