# UI Viewer – Button-Zustände und Richtungsnavigation

Stand: 2026-07-22

## Zweck

Diese Stufe verwaltet MovieClip- und klassische SWF-Buttonzustände, verbindet Maus und Tastatur mit dem isolierten AVM2-/AVM1-Ereignispfad und bietet controllerartige Richtungsnavigation. Alle Änderungen bleiben im Vorschauzustand; SWF/GFX-, GFXL-, TXTR-, MSBT- und PAK-Daten werden nicht verändert.

## Unterstützte Buttonarten

### MovieClip-/AVM2-Buttons

Ein vorhandener oder dynamisch erzeugter MovieClip wird als Button behandelt, wenn mindestens eines der folgenden Merkmale vorliegt:

- semantische Frame-Labels wie `up`, `over`, `down`, `pressed`, `highlighted` oder `disabled`;
- `buttonMode` oder `tabEnabled` ist aktiv;
- Klasse, Instanzname oder stabiler Pfad enthält ein eindeutiges Button-Merkmal wie `btn`, `button`, `toggle`, `checkbox`, `radio`, `arrow`, `confirm` oder `cancel`;
- eine dynamische Instanz basiert auf einer SimpleButton-artigen DisplayObject-Klasse.

Die Namenserkennung zerlegt CamelCase, Unterstriche und Pfadsegmente. `btnBack` wird erkannt; `background` wird nicht wegen des enthaltenen Wortteils `back` als Button klassifiziert.

### Klassische SWF-Buttons

`DefineButton` und `DefineButton2` werden als Sprite-kompatible Definitionen mit vier Zuständen eingebunden:

```text
up = Frame 1
over = Frame 2
down = Frame 3
hit = Frame 4
```

ButtonRecords, HitTest-Records, TrackAsMenu, Tastencodes und AVM1-ActionRecords werden inventarisiert. Automatisch ausgeführt werden ausschließlich `NextFrame`, `PreviousFrame`, `Play`, `Stop`, `GotoFrame` und `GotoLabel`. Alle anderen AVM1-Aktionen bleiben Diagnoseeinträge.

Details: `UI_VIEWER_CLASSIC_BUTTON_HITTEST.md`.

## Button-Owner-Routing

Hit-Geometrien von Texten, Shapes und Bildern innerhalb eines Buttons werden dem nächsten passenden Eltern-Button zugeordnet. Mehrere sichtbare Kinder desselben Buttons ergeben dadurch:

- ein Eventziel;
- einen Fokuspunkt;
- einen gemeinsamen Zustandsautomaten;
- eine gemeinsame Button-Timeline.

`mouseChildren = false` leitet Treffer ebenfalls an den entsprechenden Elterncontainer weiter.

## Automatische Zustände

Die Vorschau verwaltet pro stabilem Button-Pfad:

- `up` – normaler Ruhezustand;
- `over` – Maus darüber oder Fokus aktiv;
- `down` – gedrückt oder per Tastatur aktiviert;
- `disabled` – nicht aktivierbar;
- `hit` – HitTest-Zustand klassischer Buttons beziehungsweise semantisches Hit-Area-Label.

Bei MovieClip-Buttons erfolgt die Framezuordnung zuerst über Labels:

```text
up / default / normal / unpressed
over / hover / highlighted / selected / focused
down / pressed / startPressed
disabled / inactive / locked
hit / hitTest / hitArea
```

Fehlen Labels, gilt für erkannte mehrteilige MovieClips der Fallback Frame 1 bis 4. Nicht vorhandene Frames werden nicht erzwungen. Ein manueller `sprite_frame`-Override besitzt den höchsten visuellen Vorrang.

## Maus und Fokus

Die Eingabe steuert Timeline und Ereignisse gemeinsam:

- `mouseOver` setzt `over`;
- `mouseOut` setzt den passenden Ruhe- oder OutDown-Zustand;
- `mouseDown` setzt `down`;
- `mouseUp` setzt `over` oder `up` und kann `click` auslösen;
- Fokus setzt `over`;
- Enter oder Leertaste zeigen kurz `down` und aktivieren das Ziel.

Klassische ButtonCondActions erhalten daraus die entsprechenden Flash-Zustandsübergänge. Die Events laufen weiterhin durch die isolierte EventDispatcher-Schicht.

## Präzise HitTests

Die Navigation verwendet nicht mehr ausschließlich transformierte Rechtecke. Der präzise Pfad unterstützt:

- Alpha-Test der gerasterten Vektor-Shapes;
- Alpha-Test externer TXTR-Symbole;
- verschachtelte Transformationen;
- ClipDepth-Masken;
- AVM2-`scrollRect`;
- Runtime-`mask`;
- Runtime-`hitArea`;
- volle Stage-Koordinaten auch bei reduzierter Vorschauauflösung.

TextFields und Definitionen ohne genauere Alpha-Geometrie bleiben auf transformierte lokale Bounds begrenzt. Der Aufbau wird pro sichtbarem Filmzustand gecacht.

## Richtungsnavigation

Bei fokussierter Stage gelten:

| Eingabe | Aktion |
|---|---|
| Pfeiltasten oder WASD | nächstes Ziel in der Richtung |
| Tab / Shift+Tab | lineare Fokusreihenfolge |
| Enter oder Leertaste | akzeptieren / klicken |
| Escape oder Backspace | abbrechen / zurück |

Das nächste Ziel wird anhand der Mittelpunkte der resultierenden, bereits geclippten Hit-Regionen gewählt. Kandidaten außerhalb des Richtungssektors werden verworfen; anschließend werden Hauptdistanz, seitliche Abweichung und Gesamtdistanz gewichtet. Erkannte Buttons werden allgemeinen Hit-Regionen vorgezogen.

## Controllerartige Events

Die sichere Vorschau erzeugt zusätzlich:

```text
controllerNavigate
controllerButtonDown
controllerButtonUp
controllerAccept
controllerCancel
```

Eventdaten enthalten Aktion, auslösende Taste und `controller = "keyboard"`. Es erfolgt noch kein Zugriff auf physische Gamepads oder Plattform-Controller-APIs.

## Bedienung

Im UI Browser stehen zur Verfügung:

- `Input Events` – Browser-Eingaben an die Runtime weitergeben;
- `Button States + Navigation` – Zustände und Richtungsfokus aktivieren;
- `Buttons / HitTests` – klassische Definitionen und Geometrien untersuchen;
- `Präzise HitTests` – Shape-/Alpha-/Clip-Prüfung aktivieren;
- `Ctrl+B` – Button-/HitTest-Inspector öffnen.

Analysefeld und State Inspector zeigen Buttonzustand, Ziel-Frame, klassische Definition, Actioninventar, Hit-Geometrien, Masken und Trefferdiagnosen.

## Tests

Die ursprünglichen zwölf Modelltests prüfen Labelzuordnung, Frame-Fallback, tokenisierte Namenserkennung, Richtungsgeometrie, `mouseChildren`, statische und dynamische Zustände, manuellen Override-Vorrang und Button-Owner-Deduplizierung.

Acht weitere Repository-Tests prüfen klassische Buttonformate, AVM1-Sicherheitsgrenzen, Alpha-/Clip-Treffer, Rectangle-Normalisierung und ClipDepth-Erkennung. Sechs isolierte Parser-/Geometriemodelltests liefen lokal erfolgreich; das vollständige Tk-Fenster konnte in der Headless-Umgebung nicht visuell end-to-end geprüft werden.

## Verbleibende Grenzen

- vollständiges Flash-Capture/Bubbling und Weak-Listener-Semantik;
- manuell rekonstruierte Nachbarschaftsgraphen aus beliebigem ActionScript;
- vollständige AVM1-Ausführung;
- editierbare TextFields und IME;
- echte Gamepad-Hardware;
- Scale9-spezifische Hit-Flächen und dynamische Graphics-Zeichenbefehle.

Nächster Arbeitsblock: editierbare TextFields, Cursor/Selektion und optionales Plattform-Gamepad-Mapping.
