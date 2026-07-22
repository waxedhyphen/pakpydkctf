# UI Viewer – Display-List-/State-Inspector

Stand: 2026-07-22

## Status

Der Display-List-/State-Inspector zeigt den vom Viewer verwendeten Root-Frame und rekonstruiert alle verschachtelten MovieClip-Display-Lists rekursiv. Zusätzlich können ausgewählte Instanzen jetzt direkt für die Vorschau überschrieben und als Preset gespeichert werden.

## Öffnen

1. `UIPak.pak` laden.
2. Einen GFX-Film im UI Browser auswählen.
3. `State Inspector` anklicken oder `F6` drücken.
4. Mit dem normalen Frame-Regler durch Root-Frames wechseln. Der Inspector aktualisiert sich automatisch.

## Angezeigte Daten

Für jedes Placement werden angezeigt:

- stabiler Instanzpfad aus Tiefe und Instanzname;
- Tiefe, Character-ID, SymbolClass und externe Klasse;
- aktuelle Sichtbarkeit;
- Matrix mit Skalierung, Rotation/Schrägung und Translation;
- vollständiger ColorTransform;
- ClipDepth und Scale9-Grid;
- Filterliste und Blend Mode;
- Sprite-Frameanzahl, aktuell gewählter Unterframe und Frame-Labels;
- Fontklasse, Fontgröße, Textvariable, aktueller Text und HTML-Status;
- für externe Bilder bei Auswahl: TXTR-UUID, Quell-PAK und Bildgröße;
- vorhandene manuelle Overrides und deren Abweichung vom Originalzustand.

## Suche und Navigation

- Die Freitextsuche durchsucht Pfad, Name, Typ, Klasse, IDs, Text und Metadaten.
- `Nur sichtbare` filtert anhand des aktuell gerenderten Zustands einschließlich Sichtbarkeits-Overrides.
- `Alles öffnen` und `Alles schließen` steuern den Tiefenbaum.
- Doppelklick oder `Pfad kopieren` kopiert den stabilen Instanzpfad.
- `JSON speichern` exportiert einen vollständigen Snapshot des aktuell resultierenden Zustands.

## Manueller State-Override

Nach Auswahl eines Knotens stehen unten folgende Felder bereit:

- `Sichtbarkeit`: Original, sichtbar oder versteckt;
- `MovieClip-Frame`: `0` verwendet den ursprünglichen Frame 1, jeder positive Wert wählt einen konkreten Unterframe;
- `Text überschreiben`: ersetzt ein `EditText`-Feld als Plaintext oder HTML;
- `Filter deaktivieren`: entfernt für dieses Placement testweise Glow, DropShadow, Blur oder Bevel;
- `Blend Mode deaktivieren`: setzt das Placement für die Vorschau auf normalen Source-over-Modus.

`Override anwenden` rendert den Zustand neu. `Ausgewählten löschen` entfernt nur den markierten Pfad. `Alle löschen` setzt den aktuellen Film vollständig auf den Originalzustand zurück.

Die Werte werden auf flache Kopien der DisplayObjects und Textdefinitionen angewendet. GFX-, GFXL-, TXTR- und MSBT-Daten bleiben unverändert.

## MovieClip-Unterframes

Ein Frame-Override rekonstruiert die Display-List des gewählten Unterframes. Dadurch zeigt der Inspector auch dessen tatsächliche Kinder, Texte, Filter und Klassen. Scale9-Sprites werden nach einer Änderung ohne veraltetes Cache-Bild neu aufgebaut.

Dies ist noch keine automatische Timeline-Laufzeit: Der Unterframe bleibt auf dem manuell gewählten Wert, bis der Override geändert oder gelöscht wird.

## Presets

`Preset speichern` exportiert:

- Quell-PAK und Filmname;
- aktuellen Root-Frame;
- alle stabilen Instanzpfade;
- Sichtbarkeits-, MovieClip-Frame-, Text-, Filter- und Blend-Overrides.

`Preset laden` ersetzt die Overrides des aktuell geöffneten Films und stellt den gespeicherten Root-Frame wieder her. Bei einem abweichenden Filmnamen wird gewarnt; das Laden ist trotzdem möglich, da passende Pfade weiterhin angewendet werden können.

Das genaue JSON-Schema und Beispiele stehen in `UI_VIEWER_STATE_PRESETS.md`.

## Wichtige Grenzen

- Der Root-Frame entspricht weiterhin dem normalen Frame-Regler.
- MovieClips laufen noch nicht automatisch mit eigener Zeitbasis.
- ActionScript wird noch nicht ausgeführt.
- Dynamisch durch ActionScript erzeugte DisplayObjects existieren noch nicht.
- Initialtexte und manuelle Text-Overrides sind verfügbar; MSBT- und native Laufzeitwerte folgen später.

Der Inspector ist damit für Struktur-, Asset-, Effekt-, Layout- und manuell rekonstruierte Zustandsanalyse geeignet. Automatisch ausgeführte Ingame-Zustände benötigen die nächste Timeline- und spätere AVM2-Phase.
