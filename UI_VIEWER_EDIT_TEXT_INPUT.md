# UI Viewer – EditText-Eingabe, Cursor und Auswahl

Stand: 2026-07-22

## Zweck

Diese Stufe macht echte `DefineEditText`-Eingabefelder und zur Laufzeit erzeugte
`TextField`-Instanzen innerhalb der isolierten UI-Vorschau editierbar. Eingaben ändern
nur den filmbezogenen Runtime-Zustand. SWF/GFX-, GFXL-, TXTR-, MSBT- und PAK-Daten
werden nicht verändert.

## Erkennung editierbarer Felder

Ein statisches `DefineEditText` gilt als Eingabefeld, wenn:

- das SWF-Flag `ReadOnly` nicht gesetzt ist;
- `NoSelect` nicht gesetzt ist;
- kein manueller Inspector-Textoverride den Pfad besitzt.

Dynamische `TextField`-Objekte werden editierbar, sobald ActionScript
`type = "input"` setzt. Verknüpfte SymbolClass-Textfelder übernehmen die
`DefineEditText`-Flags ihrer Definition.

Manuelle Textoverrides bleiben absichtlich maßgeblich. Ein Feld mit einem solchen
Override wird nicht durch die Eingabelaufzeit überschrieben.

## Unterstützte DefineEditText-Flags

Der vorhandene Parser liefert bereits:

- `wordWrap`;
- `multiline`;
- `readOnly`;
- `noSelect`;
- `maxLength`;
- `html`;
- Layout, Fontklasse und Textfarbe.

Diese Stufe ergänzt die Auswertung von `Password` und verwendet die Flags direkt für
Eingabe, Auswahl und Darstellung.

## Bedienung

Im UI Browser gibt es:

- `EditText-Eingabe`: aktiviert oder deaktiviert die Vorschau-Eingabe;
- `Textfelder…`: öffnet den Eingabeinspektor;
- `Ctrl+E`: öffnet denselben Inspector.

Ein editierbares Feld wird durch einen Mausklick fokussiert. Der Klick setzt den Caret
anhand der präzisen transformierten Hit-Geometrie und der lokalen Textposition.

### Tastatur

| Eingabe | Wirkung |
|---|---|
| normale Zeichen | an Caret oder Auswahl einfügen |
| Pfeil links/rechts | Caret bewegen |
| Ctrl+links/rechts | wortweise bewegen |
| Pfeil hoch/runter | gleiche Textspalte in benachbarter Zeile |
| Home/End | Zeilenanfang oder -ende |
| Ctrl+Home/End | Textanfang oder -ende |
| Shift + Bewegung | Auswahl erweitern |
| Backspace/Delete | Zeichen oder Auswahl löschen |
| Ctrl+Backspace/Delete | Wort löschen |
| Ctrl+A | alles auswählen |
| Ctrl+C/X/V | kopieren, ausschneiden, einfügen |
| Ctrl+Z/Y | Undo/Redo |
| Enter | einzeiliges Feld abschließen |
| Enter in `multiline` | Zeilenumbruch einfügen |
| Ctrl+Enter | mehrzeiliges Feld abschließen |
| Tab/Shift+Tab | Eingabe abschließen und Fokus wechseln |
| Escape | Inhalt auf den Wert beim Eingabebeginn zurücksetzen |

Die vorhandene Button-Navigation bleibt aktiv, wird aber während einer Textsession
nicht für Pfeile, Leertaste oder Enter ausgeführt.

## Auswahl und Darstellung

Der Viewer speichert pro aktiver Session:

- Rohtext;
- Ausgangstext;
- Anchor;
- Caret;
- normalisierten Auswahlbereich;
- Drag-Status;
- bis zu 100 Undo- und Redo-Schritte.

Auswahl und Caret werden als lokale Overlay-Geometrie gezeichnet und anschließend mit
derselben Placement-Matrix wie das Textfeld transformiert. Rotation, Skalierung,
Scherung und verschachtelte MovieClips bleiben dadurch deckungsgleich.

Bei `displayAsPassword` oder dem SWF-Password-Flag wird nur eine Folge von
Aufzählungspunkten gerendert. Die tatsächliche Textlänge und Caretposition bleiben
erhalten. Kopieren und Ausschneiden aus einem Passwortfeld sind gesperrt.

## AVM2-TextField-API

Unterstützte Properties:

```text
type
selectable
maxChars
restrict
displayAsPassword
multiline
wordWrap
selectionBeginIndex
selectionEndIndex
caretIndex
selectedText
```

Unterstützte Methoden:

```text
setSelection(begin, end)
replaceSelectedText(value)
replaceText(begin, end, value)
appendText(value)
```

Die Properties werden nur für echte statische oder dynamische TextField-Empfänger
behandelt. Gleichnamige Properties an anderen DisplayObjects werden an die vorherige
Runtime-Schicht weitergereicht.

## Ereignisse

Benutzereingaben erzeugen weiterhin `keyDown` und `keyUp`. Vor einer Einfügung wird
ein cancelbares `textInput`-Ereignis am stabilen Feldpfad ausgelöst. Ruft ein Handler
`preventDefault()` auf, wird die Einfügung verworfen.

Nach einer tatsächlichen Textänderung folgt `change`. Änderungen der Auswahl erzeugen
`select`. Die Events tragen unter anderem:

```text
text
data
caretIndex
selectionBeginIndex
selectionEndIndex
keyCode
charCode
shiftKey
ctrlKey
altKey
```

Die Eventweitergabe verwendet dieselben stabilen DisplayObject-Pfade und dieselbe
begrenzte AVM2-Runtime wie die übrige Eingabeschicht.

## `restrict` und `maxChars`

`maxChars` ist auf höchstens 1.000.000 Zeichen begrenzt. Ein Wert von null bedeutet
innerhalb dieses globalen Limits unbegrenzt.

Der sichere `restrict`-Teilumfang unterstützt:

```text
A-Z
a-z
0-9
\-
\\
^0-9
```

Damit funktionieren literale Zeichen, Bereiche, Escape-Zeichen und ein führendes `^`
als Negation. Komplexe wiederholte Include-/Exclude-Gruppen der vollständigen
Flash-Syntax werden nicht erraten.

## Zwischenablage

Die Zwischenablage wird ausschließlich als direkte Reaktion auf `Ctrl+C`, `Ctrl+X`
oder `Ctrl+V` verwendet.

Sicherheitsgrenzen:

- maximal 65.536 Zeichen pro Lese- oder Schreibvorgang;
- nur Klartext;
- Nullzeichen werden entfernt;
- Zeilenumbrüche werden normalisiert;
- einzeilige Felder wandeln eingefügte Zeilenumbrüche in Leerzeichen um;
- keine Hintergrundüberwachung;
- keine Zwischenablagehistorie;
- kein Kopieren aus Passwortfeldern.

## Textquellen und Priorität

Die bestehende Priorität bleibt erhalten:

```text
manueller Inspector-Textoverride
→ direkter AVM2-/Benutzereingabewert
→ Game-State-Mock
→ MSBT-Auflösung
→ ursprünglicher DefineEditText-Inhalt
```

Sobald ein Benutzer ein Feld bearbeitet, wird dessen Text als direkter Runtime-Wert
gespeichert. Eine eventuell zuvor gespeicherte MSBT-Roh-ID für diesen Pfad wird entfernt,
damit ein späterer Sprachwechsel keinen frei eingegebenen Text überschreibt.

## Eingabeinspektor

Der Inspector zeigt:

- stabilen Feldpfad;
- editierbar oder nur dynamisch;
- `multiline`, `selectable` und Passwortstatus;
- `maxChars` und `restrict`;
- aktuell sichtbaren Text beziehungsweise Maskierung;
- aktive Session, Caret und Auswahl;
- Änderungs-, Commit-, Abbruch- und Clipboard-Zähler.

Der State Inspector ergänzt dieselben Informationen direkt am jeweiligen
`EditText`- oder `DynamicTextField`-Knoten.

## Reproduzierbarer Scanner

```bash
python PAKPY/scan_ui_edit_texts.py UIPak.pak \
  --require PreLoadPak.pak \
  --require MiscData.pak \
  --json ui_edit_texts.json
```

Der Scanner durchsucht eingebettete `FWS`-, `CWS`- und `GFX`-Filme rekursiv nach
`DefineEditText`. Er zählt editierbare, schreibgeschützte, nicht selektierbare,
mehrzeilige, passwortgeschützte, HTML- und `maxLength`-Felder. AVM1 und AVM2 werden
nicht ausgeführt.

Die großen PAK-Dateien liegen nicht im Repository. Deshalb enthält diese Änderung
keine neu erfundenen Corpus-Zahlen; der Scanner ist für den lokalen DKCTF-PAK-Satz
reproduzierbar ausgelegt.

## Tests

Die fokussierte Modellsuite prüft:

- Einfügen und Auswahlersetzung;
- `maxChars`;
- ein- und mehrzeilige Normalisierung;
- positive, negative und escaped `restrict`-Muster;
- Zeichen-, Wort-, Zeilen- und Vertikalnavigation;
- Löschen, Undo und Redo;
- Passwortdarstellung;
- Clipboard-Limit und Klartextnormalisierung;
- richtungsabhängiges Zusammenklappen einer Auswahl.

## Grenzen und nächste Schritte

Noch offen sind:

- IME-Komposition und Plattform-Preedit-Unterstreichung;
- bidirektionaler Text und komplexe Graphemcluster;
- pixelgenaue Wortumbruchidentität mit Scaleform;
- horizontales und vertikales internes TextField-Scrolling;
- vollständige Flash-`restrict`-Gruppensemantik;
- echte Gamepad-Hardware;
- Morph-Shapes und seltene Fill-/Scale9-Sonderfälle.

Der nächste visuelle Arbeitsblock sollte die verbleibenden Shape-, Morph-, Bitmap-Fill-
und Scale9-Sonderfälle inventarisieren und anschließend mit Rendervergleichsbildern
absichern.
