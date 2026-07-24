# DKCTF Hard Mode – zwei unabhängige Kong-Selectoren

Diese Datei dokumentiert die neue UI-Phase nach dem bestätigten ExeFS-Multiplayer-Fix.

## Ziel

Der Hard-Mode-Auswahlbildschirm soll zwei getrennte Kong-Selectoren besitzen:

```text
Selector P1: DK, Funky, Diddy, Dixie, Cranky
Selector P2: DK, Funky, Diddy, Dixie, Cranky
```

Beide Spieler sollen später unabhängig wählen können. Doppelte Figuren sollen nicht grundsätzlich ausgeschlossen werden.

Die Umsetzung wird getrennt bestätigt:

1. **visuell bestätigt:** zweite Selector-Instanz ist sichtbar und korrekt positioniert;
2. **AVM2 bestätigt:** eigener Trait und eigener Zustand für P2 existieren;
3. **Eingabe bestätigt:** P1 und P2 steuern getrennte Selectoren;
4. **im Spiel bestätigt:** beide Werte werden beim Hard-Mode-Start übernommen.

## Aktueller ExeFS-Stand

Das externe Projekt:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test2.json
```

ist im Spiel bestätigt:

- zwei echte Spieler starten im Hard Mode;
- P2 ist unabhängig steuerbar;
- die automatische Figurenpaarung ist noch aktiv.

Die UI-Arbeit beginnt deshalb erst nach einer funktionierenden Multiplayer-Basis.

## Relevantes Asset

```text
MasterShell -> MapHUD.swf
```

SymbolClass-Zuordnung:

```text
Character ID 80 = map.menu_hardmode
```

AVM2-Klasse:

```text
map.menu_hardmode
Klassenindex: 42
Konstruktor: 483
```

Vorhandene relevante Felder:

```text
chooseKong          : utilities.BaseToggle
playHM              : utilities.Button_square_anim
rules               : utilities.Button_square_anim
selectedKongIndex   : int
currentKong         : String
isFunkyMode         : Boolean
maxNumberOfKongs    : int
```

Es existiert bisher nur ein Selector-Feld und nur ein Auswahlzustand.

## Timeline von Sprite 80

Erster Frame:

| Tiefe | Character ID | Instanzname | Matrix | Position |
|---:|---:|---|---|---|
| 1 | 60 | `playHM` | `1A 0A D7 E8 00` | x=8,65 px, y=202,40 px |
| 21 | 72 | `chooseKong` | `18 07 EA D2` | x=3,15 px, y=69,25 px |
| 32 | 60 | `rules` | `1C 05 6B 13 A0` | x=8,65 px, y=315,05 px |

Der vorhandene Selector ist damit:

```text
Character ID 72
Tiefe 21
Instanz chooseKong
```

Character 72 ist kein Hard-Mode-Sonderobjekt. Derselbe Selector wird auch im Time-Attack-Menü wiederverwendet.

## Schritt UI-1 – reiner Sichttest

Der erste Test verändert noch keine AVM2-Klasse und keine Eingabelogik.

Es wird eine zweite, **unbenannte** Instanz von Character 72 in Sprite 80 eingefügt:

```text
Quell-Sprite:        80
Quellinstanz:        chooseKong
Ziel-Sprite:         80
Zieltiefe:           22
Instanzname:         keiner
X-Verschiebung:      0 px
Y-Verschiebung:      +66 px
```

Ausgangsmatrix:

```text
18 07 EA D2
x = 63 Twips  = 3,15 px
y = 1385 Twips = 69,25 px
```

Ergebnismatrix:

```text
1A 03 F5 48 80
x = 63 Twips  = 3,15 px
y = 2705 Twips = 135,25 px
```

Die Kopie bleibt absichtlich unbenannt. `map.menu_hardmode` besitzt noch keinen Trait `chooseKongP2`; ein verfrüht benanntes Timeline-Objekt könnte deshalb beim Setzen der nicht vorhandenen Eigenschaft scheitern.

## Lokal strukturell validierter Sichttest

Referenzfilm:

```text
u10_MasterShell_MapHUD.swf
```

Ergebnis der lokalen Strukturprüfung:

```text
Originalgröße CWS: 60716 Bytes
Testgröße CWS:     60677 Bytes
DoABC-Methoden:    702 -> 702
Methodenbodies:    702 -> 702
```

Sprite 80 nach dem Test:

```text
Tiefe 1   Character 60  playHM
Tiefe 21  Character 72  chooseKong
Tiefe 22  Character 72  unbenannt, Matrix 1A 03 F5 48 80
Tiefe 32  Character 60  rules
```

Status:

```text
binär/strukturell bestätigt
PAKPY-Vorschau noch zu bestätigen
im Spiel noch nicht bestätigt
```

## Bedienung in PAKPY

Nach dem aktuellen Pull:

1. `UIPak(10).pak` öffnen.
2. `MasterShell -> MapHUD.swf` auswählen.
3. `SWF-Timeline-Editor` öffnen.
4. Quelle suchen: Sprite `80`, Instanz `chooseKong`.
5. Ziel-Sprite `80` wählen.
6. Zieltiefe `22` eintragen.
7. X-Verschiebung `0` eintragen.
8. Y-Verschiebung `66` eintragen.
9. `Ohne Instanznamen einfügen` aktivieren.
10. `Plan prüfen`.
11. Erst danach `Vorschau anwenden`.

Der Prüfbericht muss enthalten:

```text
Character 72
Ziel-Sprite 80
Tiefe 22
Zielinstanz (unbenannt)
Verschiebung X 0 px / Y 66 px
Strukturprüfung passed
```

## Nächste Schritte nach bestätigter Sichtposition

Erst nach dem visuellen Test:

1. eigenen AVM2-Trait `chooseKongP2 : utilities.BaseToggle` einfügen;
2. die zweite Timeline-Instanz kontrolliert `chooseKongP2` nennen;
3. getrennte Felder ergänzen, beispielsweise `selectedKongIndexP2` und `currentKongP2`;
4. `setMenu`, `toggleLeft`, `toggleRight`, `nextItem`, `prevItem` und `inputSelect` auf zwei Selectoren erweitern;
5. für beide Selectoren den vollständigen Fünferzyklus verwenden;
6. beide Werte an `Char_P1` und `Char_P2` beziehungsweise an den nativen Übergang übergeben.

Keine dieser Funktionsänderungen ist Teil von UI-Schritt 1.
