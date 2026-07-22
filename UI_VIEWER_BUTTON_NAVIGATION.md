# UI Viewer – Button-Zustände und Richtungsnavigation

Stand: 2026-07-22

## Zweck

Diese Stufe erweitert die Eingabegrundlage um automatisch verwaltete Button-Zustände und eine controllerartige Richtungsnavigation. Alle Änderungen bleiben im isolierten Vorschauzustand des aktuell geöffneten Films. SWF/GFX-, GFXL-, TXTR-, MSBT-, PAK- und Repacking-Daten werden nicht verändert.

## Erkennung von Button-Zielen

Ein vorhandener oder dynamisch erzeugter MovieClip wird als Button behandelt, wenn mindestens eines der folgenden Merkmale vorliegt:

- semantische Frame-Labels wie `up`, `over`, `down`, `pressed`, `highlighted` oder `disabled`;
- `buttonMode` oder `tabEnabled` ist aktiv;
- Klasse, Instanzname oder stabiler Pfad enthält ein eindeutiges Button-Merkmal wie `btn`, `button`, `toggle`, `checkbox`, `radio`, `arrow`, `confirm` oder `cancel`;
- eine dynamische Instanz basiert auf einer SimpleButton-artigen DisplayObject-Klasse.

Die Namenserkennung zerlegt CamelCase, Unterstriche und Pfadsegmente. Dadurch wird beispielsweise `btnBack` erkannt, während `background` nicht wegen des Teilstrings `back` fälschlich als Button gilt.

Hit-Regionen von Texten oder Shapes innerhalb eines Buttons werden dem nächsten passenden Eltern-MovieClip zugeordnet. Mehrere sichtbare Kinder desselben Buttons ergeben dadurch nur ein Navigationsziel und einen gemeinsamen Zustandsautomaten.

## Automatische Zustände

Die Vorschau verwaltet pro stabilem Button-Pfad:

- `up` – normaler Ruhezustand;
- `over` – Maus darüber oder Fokus aktiv;
- `down` – gedrückt beziehungsweise per Tastatur aktiviert;
- `disabled` – nicht aktivierbar;
- `hit` – semantisches Hit-Area-Label, sofern vorhanden.

Die Zuordnung zu Timeline-Frames erfolgt zuerst über Frame-Labels. Unterstützte Bezeichnungen umfassen unter anderem:

```text
up / default / normal / unpressed
hover / over / highlighted / selected / focused
down / pressed / startPressed
disabled / inactive / locked
hit / hitTest / hitArea
```

Fehlen Labels, verwendet ein als Button erkanntes MovieClip mit mehreren Frames den sicheren Fallback:

```text
Frame 1 = up
Frame 2 = over
Frame 3 = down
Frame 4 = disabled
```

Nicht vorhandene Fallback-Frames werden nicht erzwungen. Ein manueller `sprite_frame`-Override im State Inspector besitzt weiterhin den höchsten visuellen Vorrang. Der semantische `buttonState` bleibt trotzdem für AVM2 lesbar.

## Maus und Fokus

Die vorhandenen Mausereignisse steuern nun zusätzlich die Button-Timeline:

- `mouseOver` setzt `over`;
- `mouseOut` setzt `up`, sofern der Button nicht fokussiert oder gedrückt ist;
- `mouseDown` setzt `down`;
- `mouseUp` setzt `over` oder `up`;
- Fokus setzt `over`;
- Enter oder Leertaste erzeugen kurz `down` und danach wieder den passenden Ruhezustand.

`mouseChildren = false` wird für vorhandene und dynamische Container berücksichtigt. Ein Treffer auf einem Unterobjekt wird dann an den entsprechenden Elternpfad weitergeleitet, auch wenn der Container keine eigene rechteckige Hit-Region besitzt.

## Richtungsnavigation

Bei fokussierter Stage stehen folgende Eingaben zur Verfügung:

| Eingabe | Aktion |
|---|---|
| Pfeiltasten oder WASD | nächstes Ziel in der Richtung |
| Tab / Shift+Tab | lineare Fokusreihenfolge |
| Enter oder Leertaste | akzeptieren / klicken |
| Escape oder Backspace | abbrechen / zurück |

Das nächste Ziel wird anhand der Mittelpunkte der aktuellen Hit-Regionen gewählt. Kandidaten außerhalb eines Richtungssektors werden verworfen; danach werden Hauptdistanz, seitliche Abweichung und Gesamtdistanz gewichtet. Dadurch wird ein nur minimal tiefer liegendes Element rechts vom Fokus nicht fälschlich als `down`-Ziel gewählt.

Button-Ziele werden gegenüber allgemeinen Hit-Regionen bevorzugt. Existieren keine erkannten Buttons, bleibt die allgemeine Fokusnavigation als Fallback verfügbar.

## Controllerartige Events

Zusätzlich zu den vorhandenen Mouse-, Key- und Focus-Events werden sichere Vorschauereignisse erzeugt:

```text
controllerNavigate
controllerButtonDown
controllerButtonUp
controllerAccept
controllerCancel
```

Die Eventdaten enthalten:

- `action`, beispielsweise `left`, `right`, `accept` oder `cancel`;
- den auslösenden Tastennamen;
- `controller = "keyboard"` als Herkunft.

Diese Ereignisse laufen ausschließlich durch den vorhandenen isolierten EventDispatcher. Es erfolgt kein Zugriff auf ein Gamepad-Gerät, Betriebssystem-APIs oder native Spielprozesse.

## Bedienung

Im UI Browser gibt es die Option `Button States + Navigation`. Ist sie aktiv, werden automatische Zustände und Richtungsnavigation angewendet. Die ältere Option `Input Events` steuert weiterhin, ob Browser-Eingaben grundsätzlich an die AVM2-Eventebene weitergegeben werden.

Im Analysefeld erscheinen zusätzlich:

```text
Button / Navigation:
- Erkannte Button-Ziele
- Aktive Zustände
- Zustandswechsel
- Richtungs-Fokuswechsel
- Controller-Listener
- Letzte Richtung
```

Der State Inspector zeigt bei bereits aktivierten Button-Pfaden den semantischen Zustand und den zugeordneten Ziel-Frame.

## Tests

Zwölf fokussierte Modelltests prüfen:

- Label-Zuordnung für `up`, `over`, `down` und `disabled`;
- sicheren Frame-Fallback ohne Labels;
- Button-Erkennung über Labels, Flags und tokenisierte Namen;
- Ausschluss des Fehlers `background` → `back`;
- Richtungswahl mit geometrischem Sektor;
- `mouseChildren = false`;
- statische und dynamische MovieClip-Zustände;
- Vorrang manueller Frame-Overrides;
- Inspector-Metadaten;
- Zuordnung von Child-Hit-Regionen zum Button-Owner;
- schwache Container-Fallbacks;
- Deduplizierung mehrerer Kinder desselben Buttons.

Die zwölf Tests liefen gegen ein minimales lokales Runtime-Modell erfolgreich. Die neuen Dateien wurden außerdem syntaktisch kompiliert. Eine vollständige visuelle Tk-End-to-End-Prüfung aller Filme ist in der headless Entwicklungsumgebung nicht möglich.

## Grenzen

Noch nicht enthalten sind:

- separates Parsen und Rendern klassischer SWF-Tags `DefineButton` und `DefineButton2`;
- die vollständige Flash-SimpleButton-Zustandsmaschine mit eigener HitTest-Display-List;
- pixelgenaue Shape-, Masken- und ScrollRect-HitTests;
- `mouseChildren` zusammen mit allen Flash-Capture- und Bubbling-Sonderfällen;
- manuell definierte Nachbarschaftsgraphen aus ActionScript;
- echte Gamepad-Hardware und Plattform-Controller-APIs;
- native DKCTF-Callback-Implementierungen;
- UI-Audio sowie MSBT- und Sprachlogik.

## Nächster Schritt

Als nächster Arbeitsblock folgt das native Callback-Inventar:

1. alle über `ExternalInterface`, `Controller` und ähnliche Brücken verwendeten Callback-Namen erfassen;
2. Aufrufe nach Lesen, Schreiben, Navigation, Audio und Telemetrie klassifizieren;
3. sichere DKCTF-spezifische Implementierungen mit Game-State-Mocks verbinden;
4. anschließend CAUD/CSMP-UI-Audio und MSBT-Sprachtexte anbinden.
