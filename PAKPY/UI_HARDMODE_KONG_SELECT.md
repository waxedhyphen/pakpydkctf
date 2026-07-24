# DKCTF Hard Mode – zwei unabhängige Kong-Selectoren

Diese Datei dokumentiert den aktuellen Gesamtstand des Hard-Mode-Multiplayer-Umbaus und trennt klar zwischen ExeFS, UI-Timeline, AVM2-Logik und In-Game-Bestätigung.

## Gesamtziel

Der Hard-Mode-Auswahlbildschirm soll zwei getrennte Kong-Selectoren besitzen:

```text
Selector P1: DK, Funky, Diddy, Dixie, Cranky
Selector P2: DK, Funky, Diddy, Dixie, Cranky
```

Beide Spieler sollen später unabhängig wählen können. Auch zweimal derselbe Kong soll möglich sein.

Die Umsetzung wird getrennt bestätigt:

1. **ExeFS bestätigt:** echter zweiter Spieler ist aktiv und steuerbar;
2. **visuell bestätigt:** eine zweite Selector-Grafik existiert;
3. **Sichtbarkeit bestätigt:** die zweite Zeile erscheint nur im 2-Spieler-Modus;
4. **AVM2 bestätigt:** P2 besitzt einen eigenen Trait und Auswahlzustand;
5. **Eingabe bestätigt:** P1 und P2 steuern getrennte Selectoren;
6. **im Spiel bestätigt:** beide gewählten Figuren werden beim Hard-Mode-Start übernommen.

## Aktueller Arbeitsstand

Vom Nutzer bereitgestellter aktueller PAK-Stand:

```text
UIPak(11).pak
```

Dieser Stand enthält laut Nutzer:

- die zweite Selector-Zeile;
- den Funky-Patch für den vorhandenen Hard-Mode-Selector.

Die Datei wurde als aktuelle Arbeitsgrundlage hochgeladen. Nach dem letzten Upload wurde noch keine weitere Änderung vorgenommen.

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
- der Patch wird vom Emulator geladen;
- der zweite Kong ist nicht mehr nur ein 1P-Begleiter.

Noch offen:

- Hard Mode bestimmt die Figurenpaarung weiterhin automatisch;
- bei DK als P1 wird P2 beispielsweise Diddy;
- bei Diddy, Dixie oder Cranky als P1 wird P2 weiterhin automatisch auf DK gesetzt;
- die exakte Auswahl von P1 und P2 wird noch nicht aus zwei UI-Selectoren übernommen.

Damit ist das Aktivieren des echten zweiten Spielers gelöst. Die aktuelle Hauptarbeit liegt in `MapHUD.swf`.

## 2. Relevantes UI-Asset

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
setMenu: 484
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

Aktuell existieren in AVM2 weiterhin nur ein Selector-Feld und ein Auswahlzustand.

## 3. Funky immer auswählbar – im Spiel bestätigt

Funky war bereits in den vorhandenen Mappings enthalten. Außerhalb des Funky-Modus wurde nur die Zykluslänge auf vier begrenzt.

Minimaler Patch:

```text
map.menu_hardmode.setMenu
Methode 484
Code-Offset 0xA7

04 -> 05
```

Dadurch setzen beide Zweige:

```text
maxNumberOfKongs = 5
```

Im Spiel bestätigt:

```text
DK -> Funky -> Diddy -> Dixie -> Cranky -> DK
```

Der globale Wert `isFunkyMode` selbst wurde nicht verändert.

## 4. Timeline von Sprite 80

Ursprünglicher erster Frame:

| Tiefe | Character ID | Instanzname | Position |
|---:|---:|---|---|
| 1 | 60 | `playHM` | x=8,65 px, y=202,40 px |
| 21 | 72 | `chooseKong` | x=3,15 px, y=69,25 px |
| 32 | 60 | `rules` | x=8,65 px, y=315,05 px |

Der vorhandene Selector ist:

```text
Character ID 72
Tiefe 21
Instanz chooseKong
```

Character 72 wird auch in anderen Menüs wiederverwendet und ist kein speziell für Hard Mode gebautes Symbol.

## 5. Zweite Selector-Zeile – sichtbar bestätigt

Es wurde eine zweite, zunächst unbenannte Instanz von Character 72 eingesetzt:

```text
Quell-Sprite:        80
Quellinstanz:        chooseKong
Ziel-Sprite:         80
Zieltiefe:           22
Instanzname:         keiner
X-Verschiebung:      0 px
Y-Verschiebung:      +66 px
```

Ergebnismatrix:

```text
1A 03 F5 48 80
x = 3,15 px
y = 135,25 px
```

Sprite 80 danach:

```text
Tiefe 1   Character 60  playHM
Tiefe 21  Character 72  chooseKong
Tiefe 22  Character 72  unbenannt
Tiefe 32  Character 60  rules
```

In der PAKPY-Vorschau bestätigt:

- die zweite vollständige Selector-Zeile wird dargestellt;
- sie befindet sich unterhalb des ursprünglichen Selectors;
- die Kopie zeigt aktuell die Designertexte `P1` und `Two Lines!`;
- diese Texte entstehen, weil die unbenannte Kopie noch nicht durch `map.menu_hardmode` initialisiert wird.

Noch nicht bestätigt:

- Darstellung der zweiten Zeile im Spiel;
- korrekte P2-Beschriftung;
- eigener P2-Zustand;
- eigene Eingabe.

## Aktuelles unmittelbares Ziel

Die zweite Selector-Zeile soll zunächst **nur abhängig vom Spielmodus sichtbar sein**.

Gewünschtes Verhalten:

```text
1-Spieler-Modus -> zweite Selector-Zeile unsichtbar
2-Spieler-Modus -> zweite Selector-Zeile sichtbar
```

Noch keine Auswahl- oder Controllerlogik. Dieser Schritt soll ausschließlich die Sichtbarkeit lösen.

Dafür sind voraussichtlich diese getrennten Änderungen nötig:

1. in `map.menu_hardmode` einen eigenen Slot-Trait ergänzen:

```text
chooseKongP2 : utilities.BaseToggle
```

2. die Timeline-Instanz auf Tiefe 22 kontrolliert von unbenannt zu `chooseKongP2` ändern;
3. den konkreten Runtime-Wert für 1P/2P in `MapHUD.swf` vor dem Patch eindeutig verifizieren;
4. in `setMenu` ausschließlich die Sichtbarkeit setzen:

```text
chooseKongP2.visible = Multiplayer aktiv
```

Wichtig:

- Der konkrete Feld- oder Datenname für den 1P/2P-Zustand ist vor der Umsetzung noch binär zu bestätigen.
- Es wird nicht geraten und nicht einfach ein angenommener Name wie `PlayerCount` eingebaut.
- Die Auswahlfunktion des zweiten Selectors bleibt in diesem Schritt unangetastet.

## Danach folgende Schritte

Erst nach bestätigter Sichtbarkeit:

1. P2-Beschriftung und Initialisierung korrigieren;
2. getrennte Felder wie `selectedKongIndexP2` und `currentKongP2` ergänzen;
3. `toggleLeft`, `toggleRight`, `nextItem` und `prevItem` für zwei Selectoren trennen;
4. Controller 1 und Controller 2 ihren jeweiligen Selector steuern lassen;
5. beide Selectorwerte als `Char_P1` und `Char_P2` speichern;
6. den nativen Hard-Mode-Start so ändern, dass die gewählte P2-Figur nicht wieder automatisch überschrieben wird;
7. doppelte Figurenkombinationen im Spiel testen.

## Aktueller Bestätigungsstatus

```text
ExeFS: echter P2                         im Spiel bestätigt
Funky im vorhandenen Selector            im Spiel bestätigt
Zweite Selector-Grafik                   PAKPY-Vorschau bestätigt
Zweite Zeile nur bei 2P sichtbar          noch nicht umgesetzt
Eigener AVM2-Trait chooseKongP2           noch nicht umgesetzt
Eigener P2-Auswahlzustand                 noch nicht umgesetzt
Getrennte Controller-Eingabe              noch nicht umgesetzt
Exakte P1/P2-Figuren im Level             noch nicht umgesetzt
```
