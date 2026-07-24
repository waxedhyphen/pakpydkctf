# DKCTF Hard Mode – zwei unabhängige Kong-Selectoren

Diese Datei dokumentiert den aktuellen Stand des Hard-Mode-Multiplayer-Umbaus. ExeFS, SWF-Timeline, AVM2-Anzeige, Eingabe und tatsächliche Spiellogik werden getrennt bewertet.

## Gesamtziel

Der Hard-Mode-Auswahlbildschirm soll zwei getrennte Kong-Selectoren besitzen:

```text
Selector P1: DK, Funky, Diddy, Dixie, Cranky
Selector P2: DK, Funky, Diddy, Dixie, Cranky
```

Beide Spieler sollen unabhängig wählen können. Auch zweimal derselbe Kong soll möglich sein.

## Aktuelle Arbeitsgrundlage

```text
UIPak(15).pak
```

Dieser Stand wurde im Spiel getestet und enthält den derzeit bestätigten UI-Fortschritt.

## Bestätigungsstufen

1. **ExeFS:** echter zweiter Spieler ist im Hard Mode aktiv;
2. **Timeline:** zweite Selector-Grafik existiert;
3. **Sichtbarkeit:** zweite Zeile erscheint nur bei zwei Spielern;
4. **Layout:** P1-Selector und Titel werden im 2P-Modus verschoben und in 1P zurückgesetzt;
5. **Textinitialisierung:** P2 zeigt einen echten Kong-Namen statt Designer-Platzhaltern;
6. **Eingabe:** P1 und P2 rotieren ihre eigenen UI-Texte;
7. **Spiellogik:** gewählte Texte werden als echte Figuren übernommen.

Stufe 1 bis 6 sind derzeit umgesetzt. Stufe 7 ist noch nicht umgesetzt.

## 1. ExeFS-Multiplayer – im Spiel bestätigt

Externes Projekt:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test2.json
```

Enthaltene Änderungen:

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5
STRB WZR, [X19, X8] -> NOP

0x1E7018
29 15 1E 12 -> 29 19 1F 12
AND #0xFC -> AND #0xFE
```

Im Spiel bestätigt:

- zwei echte Spieler starten im Hard Mode;
- P2 ist unabhängig steuerbar;
- der zweite Kong ist nicht nur ein 1P-Begleiter.

Noch offen:

- Hard Mode bestimmt die Figurenpaarung weiterhin automatisch;
- die beiden UI-Auswahlen werden noch nicht an den nativen Hard-Mode-Start übergeben.

## 2. Relevantes UI-Asset

```text
MasterShell -> MapHUD.swf
```

SymbolClass-Zuordnung:

```text
Character ID 80 = map.menu_hardmode
```

Relevante Klasse und Methoden:

```text
map.menu_hardmode
Konstruktor: 483
setMenu:     484
toggleLeft:  492
toggleRight: 493
```

Relevante Eingaberoutine:

```text
map.MapHUD
keyDownProcess: Methode 421
```

Vorhandene P1-Felder:

```text
chooseKong          : utilities.BaseToggle
selectedKongIndex   : int
currentKong         : String
isFunkyMode         : Boolean
maxNumberOfKongs    : int
```

Für P2 wurde kein neuer ABC-Trait angelegt. Der zweite Selector wird aktuell über seine feste Timeline-Position angesprochen:

```text
getChildAt(2)
```

Das vermeidet einen Umbau des ABC-Konstantenpools und der Klassentraits.

## 3. Funky im vorhandenen P1-Selector – im Spiel bestätigt

Funky war bereits in den vorhandenen Mappings enthalten. Außerhalb des Funky-Modus wurde ursprünglich nur die Zykluslänge begrenzt.

Der Patch setzt:

```text
maxNumberOfKongs = 5
```

Der vorhandene P1-Selector kann dadurch alle fünf Kongs anzeigen.

## 4. Timeline von Sprite 80

Ursprünglicher erster Frame:

| Tiefe | Character ID | Instanzname | Position |
|---:|---:|---|---|
| 1 | 60 | `playHM` | x=8,65 px, y=202,40 px |
| 21 | 72 | `chooseKong` | x=3,15 px, y=69,25 px |
| 32 | 60 | `rules` | x=8,65 px, y=315,05 px |

Der vorhandene P1-Selector ist:

```text
Character ID 72
Tiefe 21
Instanz chooseKong
```

Die zweite Instanz wurde aus Character 72 erzeugt und anschließend benannt:

```text
Character ID 72
Tiefe 22
Instanz chooseKongP2
```

Aktuelle Reihenfolge in Sprite 80:

```text
Tiefe 1   Character 60  playHM
Tiefe 21  Character 72  chooseKong
Tiefe 22  Character 72  chooseKongP2
Tiefe 32  Character 60  rules
```

Die P2-Zeile wurde zusätzlich per Timeline-Transform nach unten positioniert. Die endgültige Feinposition wurde im Spiel bestätigt.

## 5. Sichtbarkeit von `chooseKongP2` – im Spiel bestätigt

Der Runtime-Wert ist eindeutig bestätigt:

```text
mRuntimeData.PlayerCount
1 = ein Spieler
2 = zwei Spieler
```

`setMenu` setzt die Sichtbarkeit sinngemäß so:

```actionscript
getChildAt(2).visible =
    Controller.GetDataValue(
        "menu_hardmode::setMenu",
        "mRuntimeData",
        "PlayerCount"
    ) != 1;
```

Ergebnis:

```text
1P -> chooseKongP2 unsichtbar
2P -> chooseKongP2 sichtbar
```

Dies ist im Spiel bestätigt.

## 6. Bedingtes P1-Layout – im Spiel bestätigt

Wenn P2 angezeigt wird, werden der P1-Selector und sein Titel nach oben verschoben. Beim Zurückwechseln auf 1P werden feste Originalpositionen gesetzt; es findet keine kumulative relative Verschiebung statt.

Aktuelle feste Werte:

```text
1P:
chooseKong.y              = 69,25
chooseKong.toggle_Title.y = -141

2P:
chooseKong.y              = 14,25
chooseKong.toggle_Title.y = -121
```

Damit bewegt sich der gesamte P1-Selector im 2P-Modus 55 Pixel nach oben. Der Titel wird lokal um 20 Pixel nach unten korrigiert und steht dadurch insgesamt 35 Pixel höher als in 1P.

Beim erneuten Öffnen in 1P stehen beide Elemente wieder an ihren Originalpositionen.

## 7. Initialisierung und Bereinigung von `chooseKongP2` – im Spiel bestätigt

Der zweite Selector enthielt zunächst Designer-Platzhalter wie:

```text
P1
Two Lines!
NAME HERE
Choose your Kong.
```

Aktuelles Verhalten beim Öffnen des Menüs:

- P2 wird mit `DK` initialisiert;
- die Kong-Namensfelder werden über das vorhandene `BaseToggle.setToggle`/`setToggleText`-Verhalten befüllt;
- der zusätzliche P2-Titel wird explizit auf einen leeren String gesetzt;
- dadurch ist die Lösung unabhängig von der ausgewählten Sprache;
- es wird kein englischer Lokalisierungstext manipuliert.

Der zweite Titel bleibt leer:

```actionscript
chooseKongP2.toggle_Title.text = "";
```

Die Designer-Platzhalter sind im getesteten Spielstand nicht mehr sichtbar.

## 8. Getrennte Texteingabe für P1 und P2 – im Spiel bestätigt

Die Eingaberoutine musste den aktiven Hard-Mode-Bildschirm über das aktuelle Untermenü erkennen. `currentStateClip` selbst ist das `MapMenu`; der konkrete Hard-Mode-Bildschirm liegt in:

```text
currentStateClip.currentMenu
```

Nach der Korrektur gilt:

```text
Controller P1 links/rechts -> nur chooseKong
Controller P2 links/rechts -> nur chooseKongP2
```

P2 benutzt derzeit einen rein visuellen Auswahlzustand am zweiten `BaseToggle`.

Aktueller P2-Textzyklus:

```text
DK -> Diddy -> Dixie -> Cranky -> Funky -> DK
```

Die Rotation verändert ausschließlich die sichtbaren Texte. Sie startet beim Öffnen derzeit wieder bei `DK`.

Diagnostische Methodengrößen des bestätigten Standes:

```text
Methode 421: 575 Bytes
Methode 484: 344 Bytes
Methode 492: 212 Bytes
Methode 493: 210 Bytes
```

## 9. Was ausdrücklich noch nicht implementiert ist

Die aktuelle Auswahl ist nur UI-Verhalten.

Nicht vorhanden:

- kein Lesen von `mRuntimeData.Char_P1` oder `mRuntimeData.Char_P2` beim Öffnen;
- kein Logging der tatsächlich gespielten Figuren;
- keine automatische Initialisierung der Texte auf die aktuell gespielten Figuren;
- kein Schreiben der UI-Auswahl nach `Char_P1` oder `Char_P2`;
- keine Übergabe der P2-Auswahl an den nativen Hard-Mode-Start;
- keine bestätigte Unterstützung doppelter Figurenkombinationen im Level.

Der zuletzt vorgeschlagene Patch zum Auslesen, Loggen und Synchronisieren von `Char_P1`/`Char_P2` wurde vom Nutzer **nicht übernommen** und gehört nicht zum aktuellen Stand.

## 10. Aktueller Bestätigungsstatus

```text
ExeFS: echter P2                         im Spiel bestätigt
Funky im vorhandenen P1-Selector         im Spiel bestätigt
Zweite Selector-Grafik                   im Spiel bestätigt
Timeline-Name chooseKongP2               bestätigt
Zweite Zeile nur bei 2P sichtbar         im Spiel bestätigt
P1-Layout 1P/2P mit Rücksetzung          im Spiel bestätigt
P2-Platzhalter entfernt                  im Spiel bestätigt
P2-Titel sprachunabhängig geleert        im Spiel bestätigt
Getrennte P1/P2-Texteingabe              im Spiel bestätigt
P2-Auswahl nur visuell                   bestätigt
Aktuelle Figuren beim Öffnen einlesen    nicht umgesetzt
UI-Auswahl in Char_P1/Char_P2 schreiben  nicht umgesetzt
Exakte P1/P2-Figuren im Level            nicht umgesetzt
```

## Nächster funktionaler Schritt

Der nächste große Schritt ist nicht mehr die Darstellung, sondern die Verbindung mit der tatsächlichen Spiellogik:

1. die realen Werte und Schreibzeitpunkte von `Char_P1` und `Char_P2` sauber verifizieren;
2. festlegen, ob die UI beim Öffnen die aktuell gespielten Figuren übernehmen soll;
3. die beiden visuellen Auswahlzustände beim Bestätigen getrennt speichern;
4. verhindern, dass der native Hard-Mode-Start P2 anschließend wieder automatisch ersetzt;
5. alle 25 P1/P2-Kombinationen einschließlich doppelter Kongs testen.
