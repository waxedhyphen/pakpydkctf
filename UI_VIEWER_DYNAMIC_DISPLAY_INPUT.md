# UI Viewer – Dynamische Display-List und Eingabegrundlage

Stand: 2026-07-22

## Zweck

Diese Stufe erweitert die kontrollierte AVM2-Runtime um dynamisch erzeugte Vorschauobjekte und direkte Eingabeereignisse im UI Browser. Alle erzeugten Objekte, Transformwerte, Fokuszustände und Events bleiben im isolierten Zustand des aktuell geöffneten Films.

SWF/GFX-, GFXL-, TXTR-, MSBT-, PAK- und Repacking-Daten werden nicht verändert.

## Dynamische Objekte

Unterstützte sichere Konstruktionen sind:

- `new MovieClip()`;
- `new Sprite()`;
- `new TextField()`;
- `new Shape()`;
- `new DisplayObject()`;
- exportierte `SymbolClass`-Klassen, wenn eine vorhandene SWF-Definition zugeordnet werden kann;
- AVM2-Klassen, deren Vererbungskette nachweislich auf einer unterstützten DisplayObject-Klasse basiert.

Beliebige Daten-, Event- oder Spielklassen werden nicht automatisch als DisplayObjects behandelt. Klassen- und Symbolauflösungen werden pro Film gecacht.

Für eine verknüpfte AVM2-Klasse läuft der Instanz-Initializer beim Erzeugen des Objekts, also vor einem späteren `addChild`. Eingebettete Sprite-Definitionen verwenden ihre echten Timeline-Tags und können mit der normalen UI-Timeline mitlaufen.

Zum Schutz gilt ein Limit von 2048 dynamischen DisplayObjects pro Film und eine maximale dynamische Verschachtelungstiefe von 64.

## DisplayObjectContainer-Teilumfang

Unterstützt werden:

- `addChild` und `addChildAt`;
- `removeChild` und `removeChildAt`;
- `getChildByName` und `getChildAt`;
- `contains`;
- `numChildren`;
- `setChildIndex`;
- `swapChildren` und `swapChildrenAt`.

Dynamische Kinder besitzen stabile Vorschaupfade der Form:

```text
root/$dyn3:TextField3
root/5:menu/$dyn8:pkg.LinkedButton
```

Das Entfernen eines statischen Timeline-Kindes setzt in der Vorschau dessen Runtime-Sichtbarkeit auf `false`; die ursprüngliche SWF-Display-List bleibt unverändert.

## Unterstützte Properties

Für vorhandene und dynamische Instanzen werden zusätzlich gelesen beziehungsweise geschrieben:

- `x` und `y`;
- `scaleX` und `scaleY`;
- `rotation`;
- `visible` und `alpha`;
- `enabled`;
- `mouseEnabled`;
- `tabEnabled`;
- `buttonMode`;
- `useHandCursor`;
- `focusRect`;
- `name`;
- `width` und `height` bei dynamischen Objekten;
- `text` und `htmlText` bei dynamischen Textfeldern;
- `currentFrame`, `totalFrames`, `play`, `stop`, `gotoAndStop` und `gotoAndPlay` bei dynamischen MovieClips.

Transform-Properties werden nur auf flüchtige Kopien statischer Placements angewendet. Manuelle State-Inspector-Overrides behalten weiterhin den höchsten Vorrang.

## Rendering und Inspector

Dynamische TextFields werden durch den bestehenden Text-Renderer gezeichnet. Dynamisch erzeugte, exportierte Sprite-Klassen verwenden ihre echte SWF-Definition; generische Container erhalten einen Vorschau-Platzhalter.

Der State Inspector zeigt dynamische Objekte als `DynamicMovieClip`, `DynamicTextField`, `DynamicShape` oder `DynamicDisplayObject` einschließlich:

- stabilem Pfad und Parent;
- Klasse und Instanzname;
- Transform und Alpha;
- Sichtbarkeit und Enabled-Status;
- Mouse-/Tab-Status;
- Fokusstatus;
- Text beziehungsweise MovieClip-Frame;
- dynamischen Kindern.

Die Dynamic-State-Revisionsnummer ist Teil des Render-Cache-Schlüssels. Transform-, Text-, Child- oder Fokusänderungen verwenden deshalb keinen veralteten gecachten Frame.

## Eingabe im UI Browser

Die neue Leiste `Input Events` aktiviert oder deaktiviert die Weiterleitung der Browser-Eingabe.

Bedienung:

- Mausbewegung erzeugt `mouseOver` und `mouseOut`;
- Drücken erzeugt `mouseDown`;
- Loslassen erzeugt `mouseUp`;
- Drücken und Loslassen auf demselben Ziel erzeugt `click`;
- Anklicken setzt den Fokus und erzeugt `focusOut` beziehungsweise `focusIn`;
- `Tab` und `Shift+Tab` wechseln zwischen `tabEnabled`-Zielen, ersatzweise zwischen allen aktivierten Hit-Regionen;
- `Enter` oder Leertaste aktiviert das fokussierte Ziel;
- Tasten werden als `keyDown` und `keyUp` an das fokussierte Ziel weitergereicht.

Maus- und Tastaturereignisse können entlang der stabilen Parent-Pfade bis `root` weitergegeben werden. Eventdaten enthalten unter anderem Stage-Koordinaten, Keycode, Zeichencode und Tastennamen.

Hit-Testing verwendet die transformierten rechteckigen Bounds vorhandener Shapes, Textfelder und externer Bilder sowie die Bounds dynamischer Objekte. Das ist eine sichere Analysegrundlage, aber noch kein pixelgenauer Flash-HitTest.

## Analyseanzeige

Im normalen Analysefeld erscheinen zusätzlich:

```text
Dynamische Display-List / Input:
- Dynamische Objekte
- Angehängte Objekte
- Gezeichnete dynamische Objekte
- Hit-Regionen
- Fokuspfad
- Ausgeführte Input-Listener
```

## Tests

Neun fokussierte Modelltests prüfen:

- Konstruktion, `addChild`, Suche und Entfernen;
- Transform-, Text- und Tab-Properties;
- Transform-Anwendung auf statischen Placements ohne Änderung des Originals;
- Child-Reihenfolge;
- verknüpfte Symbolklassen;
- Ablehnung unbekannter Nicht-Display-Klassen;
- EventDispatcher-Pfade;
- Fokuswechsel;
- Timeline-Fortschritt dynamischer MovieClips.

Zwei zusätzliche Tests prüfen, dass verknüpfte AVM2-Konstruktoren beim `new` genau einmal laufen und eingebaute Klassen ohne ABC-Definition keinen erfundenen Initializer erhalten.

Die elf Tests liefen gegen ein minimales lokales Runtime-Modell erfolgreich. Die neuen Dateien wurden außerdem syntaktisch kompiliert. Eine vollständige visuelle Tk-End-to-End-Prüfung mit allen Filmen ist in der headless Entwicklungsumgebung nicht möglich.

## Grenzen

Noch nicht enthalten sind:

- pixelgenaue Shape-HitTests und Flash-`hitTestPoint`-/`hitTestObject`-Semantik;
- vollständige `mouseChildren`, Masken- und ScrollRect-HitTest-Regeln;
- automatische SimpleButton-Zustände `up`, `over`, `down` und `hitTest`;
- Richtungsnavigation für Controller;
- echte Gamepad-Geräteingabe;
- TextField-Eingabecursor und editierbarer Text;
- vollständiges Event-Capture und Flash-konformes Bubbling;
- beliebige dynamische Vektorzeichenbefehle;
- native DKCTF-Callbacks, Audio sowie MSBT- und Sprachlogik.

## Nächster Schritt

Als nächster Arbeitsblock folgen Button- und Navigationszustände:

1. automatische `up`-/`over`-/`down`-Zustände für SimpleButton- und MovieClip-Buttons;
2. Richtungsfokus und Controller-Mapping;
3. präzisere Hit-Test-Regeln einschließlich `mouseChildren`;
4. Inventar und sichere Implementierung realer DKCTF-Callbacks;
5. anschließend CAUD/CSMP-UI-Audio und MSBT-Sprachtexte.
