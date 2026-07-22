# UI Viewer – Laufende Timeline-Vorschau

Stand: 2026-07-22

## Zweck

Die Timeline-Vorschau lässt Root- und verschachtelte MovieClip-Timelines ohne ActionScript strukturell laufen. Jede MovieClip-Instanz erhält einen eigenen Framezustand, der über den stabilen Pfad des State Inspectors identifiziert wird.

Die Funktion ist ausschließlich eine Vorschau. GFX-, GFXL-, TXTR-, MSBT- und Repacking-Daten werden nicht verändert.

## Browser-Steuerung

Im UI Browser befindet sich eine zusätzliche Timeline-Leiste:

- `▶ Play`: startet Root- und aktive Untertimelines;
- `⏸ Pause`: hält die komplette Vorschau an;
- `−1` und `+1`: Einzelschritt für Root und alle aktuell sichtbaren Untertimelines;
- `Reset`: setzt Root und bekannte MovieClip-Instanzen auf Frame 1;
- `Tempo`: `0.25×`, `0.5×`, `1×`, `2×` oder `4×`;
- `Root-Label`: direkter Sprung zu einem Root-Frame-Label;
- `F7`: globale Wiedergabe umschalten.

Die Framerate stammt aus dem SWF/GFX-Header. Langsame Renderdurchläufe werden mit einem begrenzten Catch-up ausgeglichen, ohne beliebig viele Frames auf einmal nachzuholen.

## Instanzsteuerung im State Inspector

Für einen ausgewählten `MovieClip` zeigt der Inspector den aktuellen Frame und die Frameanzahl. Verfügbar sind:

- einen Frame zurück oder vor;
- Play/Pause nur für diese Instanz;
- Reset dieser Instanz auf Frame 1;
- Sprung zu einem Label aus der Sprite-Timeline.

Der Detailbereich zeigt zusätzlich, ob der Frame aus der laufenden Timeline oder aus einem manuellen `sprite_frame`-Override stammt.

## Vorrangregeln

Die Framequelle wird in dieser Reihenfolge gewählt:

1. manueller `sprite_frame`-Override des State-Presets;
2. laufender Framezustand des MovieClip-Instanzpfads;
3. Frame 1 als Fallback.

Ein manueller MovieClip-Frame fixiert die Instanz. Play, Einzelschritt und Label-Sprung verändern diesen Pfad nicht, bis der Override entfernt wurde.

## Instanzpfade und Lebensdauer

Beispiel:

```text
root/5:options_control/1:btnHandheld
```

Der Framezustand wird pro Film und Pfad gespeichert. Beim Wechsel zu einem anderen Film bleiben die Zustände des bisherigen Films während der laufenden Browser-Sitzung erhalten.

MovieClips, die im aktuellen Root- oder Unterframe nicht sichtbar sind, behalten ihren zuletzt bekannten Zustand. Sobald derselbe Pfad wieder erscheint, wird die Wiedergabe dort fortgesetzt.

## Looping

Root und Sprite-Timelines loopen anhand ihrer jeweiligen `frame_count`:

```text
1, 2, 3, ..., N, 1, 2, ...
```

Rückwärtsschritte loopen entsprechend von Frame 1 zu Frame N.

## Preset-Daten

State-Presets besitzen optional einen `playback`-Block:

```json
{
  "playback": {
    "speed": 1.0,
    "playing": false,
    "instances": {
      "root/5:options_control/1:btnHandheld": {
        "frame": 11,
        "playing": true
      },
      "root/5:options_control/2:btnGamepad": {
        "frame": 1,
        "playing": false
      }
    }
  }
}
```

Ältere Presets ohne `playback` bleiben kompatibel. Sie werden mit Tempo `1×`, global pausiert und ohne gespeicherte Unterframes geladen.

## Cache- und Renderverhalten

- Verschachtelte Frames werden über denselben Display-List-Renderer wie manuelle Overrides aufgebaut.
- ClipDepth, Filter, Blend Modes, Text und ColorTransform werden pro laufendem Frame neu angewendet.
- Scale9-Natural-Size-Caches werden bei Timeline-Änderungen invalidiert, damit kein Unterframe aus einem älteren Zustand wiederverwendet wird.
- Framezustände verändern keine SWF-Tags und keine Definitionen dauerhaft.

## Validierung

- 39 UI-Parser-, Renderer-, Font-, Inspector-, Override- und Timeline-Tests liefen lokal erfolgreich.
- In `Options.swf`, Root-Frame 20, wurden 70 verschachtelte MovieClips mit mehr als einem Frame gefunden.
- `root/5:options_control/1:btnHandheld` besitzt 34 Frames und Labels wie `default`, `startHighlighted`, `highlighted`, `unpressed` und `startPressed`.
- Die Instanz wurde auf Frame 2 geschaltet; der vollständige 1280×720-Frame wurde danach ohne Renderfehler verarbeitet.

## Grenzen

Die Timeline-Vorschau führt noch kein ActionScript aus. Dadurch fehlen insbesondere:

- `stop()`, `play()`, `gotoAndPlay()` und `gotoAndStop()` aus Frame Scripts;
- bedingte Zustandswechsel und Events;
- dynamisch erzeugte DisplayObjects;
- native Spielcallbacks;
- skriptgesteuerte Text- und Sichtbarkeitsänderungen;
- Morph-Shapes.

Die aktuelle Wiedergabe ist deshalb für Animationen, Frame-Inventar, Labels, Übergangsaufbau und manuelle Ingame-State-Rekonstruktion geeignet, aber noch keine vollständige AVM2-Laufzeit.
