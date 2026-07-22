# UI Viewer – Display-List-/State-Inspector

Stand: 2026-07-22

## Status

Der read-only Display-List-/State-Inspector ist implementiert. Er zeigt den exakt vom statischen UI-Renderer verwendeten Root-Frame und rekonstruiert alle verschachtelten MovieClip-Display-Lists rekursiv.

## Öffnen

1. `UIPak.pak` laden.
2. Einen GFX-Film im UI Browser auswählen.
3. `State Inspector` anklicken oder `F6` drücken.
4. Mit dem normalen Frame-Regler durch Root-Frames wechseln. Der Inspector aktualisiert sich automatisch.

## Angezeigte Daten

Für jedes Placement werden angezeigt:

- stabiler Instanzpfad aus Tiefe und Instanzname;
- Tiefe, Character-ID, SymbolClass und externe Klasse;
- Sichtbarkeit;
- Matrix mit Skalierung, Rotation/Schrägung und Translation;
- vollständiger ColorTransform;
- ClipDepth;
- Scale9-Grid;
- Filterliste und Blend Mode;
- Sprite-Frameanzahl und Frame-Labels;
- Fontklasse, Fontgröße, Textvariable, initialer/aktueller statischer Text und HTML-Status;
- für externe Bilder bei Auswahl: TXTR-UUID, Quell-PAK und Bildgröße.

## Bedienung

- Freitextsuche durchsucht Pfad, Name, Typ, Klasse, IDs, Text und Metadaten.
- `Nur sichtbare` blendet unsichtbare Blattknoten aus; unsichtbare Eltern bleiben sichtbar, wenn sie einen passenden sichtbaren Nachfolger enthalten.
- `Alles öffnen` und `Alles schließen` steuern den Tiefenbaum.
- Doppelklick oder `Pfad kopieren` kopiert den stabilen Instanzpfad.
- `JSON speichern` exportiert den vollständigen State-Snapshot des aktuellen Root-Frames.

## Wichtige Grenze

Der Inspector zeigt bewusst denselben Zustand wie der aktuelle statische Renderer:

- der Root-Frame entspricht dem Frame-Regler;
- verschachtelte MovieClips stehen derzeit auf Frame 1;
- ActionScript wird noch nicht ausgeführt;
- Textwerte entsprechen dem initialen `DefineEditText`-Inhalt oder einem Variablenplatzhalter;
- dynamisch erzeugte DisplayObjects existieren noch nicht.

Dadurch ist der Inspector bereits für Struktur-, Asset-, Effekt- und Layoutanalyse geeignet, aber noch nicht für automatisch ausgeführte Ingame-Zustände.

## Nächster Arbeitsblock

Manuelle State-Overrides und speicherbare Presets:

- Sichtbarkeit pro Instanzpfad überschreiben;
- MovieClip-Frame pro Instanz wählen;
- Text und HTML-Text ersetzen;
- optional Filter und Blend Modes deaktivieren;
- Presets als JSON speichern und laden;
- Presets für Pause, Optionen, Frontend, Charakterwahl und HUD aufbauen.

Diese Overrides werden vor dem Rendern auf eine Kopie der Display-List angewendet und verändern keine GFX-, GFXL-, TXTR- oder MSBT-Daten.
