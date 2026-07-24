# UI KONG Select: Teil 1 und Teil 2 abgeschlossen

Diese Datei dokumentiert den finalen, **im Spiel bestätigten** Stand des KONG-Select-Umbaus in `UIPak(10).pak`.

Abgeschlossen sind:

- **Teil 1:** Spieler 1 kann DK, Funky, Diddy, Dixie und Cranky auswählen.
- **Teil 2:** Spieler 2 kann ebenfalls DK, Funky, Diddy, Dixie und Cranky auswählen.
- Beide Spieler besitzen einen eigenen vollständigen Auswahlring.
- Namen und Porträts werden während der Rotation korrekt aktualisiert.
- Namen und Porträts werden nach Schließen und erneutem Öffnen des Menüs korrekt wiederhergestellt.

Bestätigter gemeinsamer Zyklus:

```text
Rechts: DK -> FUNKY -> DIDDY -> DIXIE -> CRANKY -> DK
Links:  DK -> CRANKY -> DIXIE -> DIDDY -> FUNKY -> DK
```

Die Dokumentation unterscheidet weiterhin:

- **binär bestätigt:** direkt aus PAK-, GFX-, SWF- und ABC-Daten gelesen
- **im Spiel bestätigt:** mit der vom Nutzer gebauten PAK getestet

---

# 1. Referenzdateien

| Rolle | Datei | Größe | SHA-256 |
|---|---:|---:|---|
| früher Ausgangsstand | `UIPak(7).pak` | 72.653.504 Bytes | `f007a0aeeef648a0a188bec8ba33b88a6d37d5c0316f7c753380136e88540850` |
| DK/Funky/Diddy-Zwischenstand | `UIPak(8).pak` | 72.653.980 Bytes | `995a8066c9858a8910e0613a2e1e34f4cdaf733e117e8435a32ec18b85be7c9f` |
| finaler Spieler-1-Stand | `UIPak(9).pak` | 72.654.140 Bytes | `11e4d12e63b3ad5b11c80f558fb817d1e3588f85e312b7758843480b24670101` |
| finaler Spieler-1-und-Spieler-2-Stand | `UIPak(10).pak` | 72.654.307 Bytes | `7e1d57c986b59ef89fce1efe0510457f035486de79f26b9ece648afc380d8648` |

`UIPak(10).pak` enthält weiterhin 1659 PAK-Einträge.

## Änderungen von `UIPak(9).pak` zu `UIPak(10).pak`

Es wurden genau zwei PAK-Assets verändert:

| Asset | `UIPak(9)` | `UIPak(10)` | Delta |
|---|---:|---:|---:|
| `PauseMenu` (`GFX`) | 350.567 | 350.728 | +161 Bytes |
| `MasterShell` (`GFX`) | 432.203 | 432.209 | +6 Bytes |

Innerhalb dieser GFX-Assets änderten sich genau vier Filme:

| Film | `UIPak(9)` | `UIPak(10)` | Delta |
|---|---:|---:|---:|
| `PauseMenu -> MenuCharacter.swf` | 30.896 | 30.898 | +2 Bytes |
| `PauseMenu -> Source` | 85.416 | 85.575 | +159 Bytes komprimiert |
| `MasterShell -> MenuCharacter.swf` | 30.892 | 30.893 | +1 Byte |
| `MasterShell -> Source` | 62.438 | 62.443 | +5 Bytes komprimiert |

Alle übrigen PAK-Einträge sind zwischen `UIPak(9)` und `UIPak(10)` unverändert.

---

# 2. Architektur

Die funktionierende Lösung besteht weiterhin aus getrennten Ebenen.

## `PauseMenu -> Source`

Diese Ebene steuert für beide Spieler:

- `P1Selection` und `P2Selection`
- Rotation nach rechts und links
- lokalisierte Charakternamen
- Wiederherstellung beim erneuten Öffnen
- Sichtbarkeit der Porträts während der Rotation
- `resetPortraitP1` und `resetPortraitP2`

Relevanter Codepfad:

```text
PauseMenu -> Source
DoABC: erstes unbenanntes Root-Modul
Klasse: shell.MenuCharacter
```

## `PauseMenu/MasterShell -> MenuCharacter.swf`

Diese Filme enthalten die tatsächlichen Timeline-Instanzen:

```text
Sprite 15 = Spieler-1-Porträts
Sprite 12 = Spieler-2-Porträts
```

## `MasterShell -> Source`

MasterShell besitzt eigene Reset-Methoden:

```text
Methode 359 = resetPortraitP1
Methode 360 = resetPortraitP2
```

Source-Logik und Timeline-Instanzen müssen weiterhin getrennt behandelt werden.

---

# 3. Relevante PauseMenu-Konstanten und Felder

## Charakterkonstanten

| Konstante | Multiname-Index |
|---|---:|
| `k_sDK` | 915 |
| `k_sDiddy` | 916 |
| `k_sDixie` | 917 |
| `k_sCranky` | 918 |
| `k_sFunky` | 919 |

## Auswahl- und UI-Felder

| Feld | Multiname-Index |
|---|---:|
| `P1_Character` | 503 |
| `P2_Character` | 504 |
| `portrait_p1` | 505 |
| `portrait_p2` | 506 |
| `P1Selection` | 507 |
| `P2Selection` | 508 |
| `visible` | 1293 |
| `dk` | 1297 |
| `fk` | 1298 |
| `diddy` | 1299 |
| `dixie` | 1300 |
| `cranky` | 1301 |
| `toggleNext` | 1304 |
| `togglePrev` | 1305 |

## Lokalisierungsstrings

| Text | String-Index |
|---|---:|
| `$_P1_Title` | 2103 |
| `$_Character_DK` | 2104 |
| `$_Character_FK` | 2106 |
| `$_P2_Title` | 2110 |
| `$_Character_Diddy` | 2111 |
| `$_Character_Dixie` | 2113 |
| `$_Character_Cranky` | 2115 |

---

# 4. Finale Source-Methodengrößen

| Bereich | Methode | Stock | `UIPak(9)` | final `UIPak(10)` |
|---|---|---:|---:|---:|
| PauseMenu | `initMenu` 490 | 1018 | 1219 | 1391 |
| PauseMenu | `toggleRight` 492 | 668 | 853 | 1011 |
| PauseMenu | `toggleLeft` 493 | 668 | 846 | 1004 |
| PauseMenu | `resetPortraitP1` 500 | 25 | 58 | 58 |
| PauseMenu | `resetPortraitP2` 501 | 36 | 36 | 58 |
| MasterShell | `resetPortraitP1` 359 | 25 | 58 | 58 |
| MasterShell | `resetPortraitP2` 360 | 36 | 36 | 58 |

Alle finalen Methodenbodies lassen sich vollständig disassemblieren. Sämtliche relativen Sprünge und `lookupswitch`-Ziele landen auf gültigen Instruktionsgrenzen.

---

# 5. Spieler 1: finaler Stand

## Rotation

```text
Rechts: DK -> Funky -> Diddy -> Dixie -> Cranky -> DK
Links:  DK -> Cranky -> Dixie -> Diddy -> Funky -> DK
```

`initMenu`, Methode 490, erkennt alle fünf Werte von `P1Selection` und setzt den passenden Namen sowie das passende P1-Porträt.

`PauseMenu -> Source`, Methode 500, blendet alle fünf P1-Porträts aus:

```actionscript
portrait_p1.dk.visible = false;
portrait_p1.fk.visible = false;
portrait_p1.diddy.visible = false;
portrait_p1.dixie.visible = false;
portrait_p1.cranky.visible = false;
```

`MasterShell -> Source`, Methode 359, enthält dieselbe vollständige Fünferliste mit den MasterShell-Multiname-Indizes.

Der bestätigte P1-Funky-zu-Diddy-Pfad springt zu einem eigenen Diddy-Abschlussblock. Er darf nicht wieder in den angehängten Dispatcher umgeleitet werden, da der frühere falsche Stackzustand einen Absturz beim Rechtsdrücken verursachte.

---

# 6. Spieler 2: finaler Stand

## 6.1 Rotation nach rechts

```text
Diddy -> Dixie -> Cranky -> DK -> Funky -> Diddy
```

Der P2-Dispatcher in `toggleRight`, Methode 492, beginnt bei `0x355`:

| Aktuelle Auswahl | Zielpfad |
|---|---:|
| Diddy | vorhandener Dixie-Pfad bei `0x14E` |
| Dixie | vorhandener Cranky-Pfad bei `0x17B` |
| Cranky | neuer DK-Pfad bei `0x391` |
| DK | neuer Funky-Pfad bei `0x3B0` |
| Funky | vorhandener Diddy-Pfad bei `0x1DC` |

Neue Abschlussblöcke:

| Zielauswahl | Abschlussblock | sichtbares Icon |
|---|---:|---|
| DK | `0x3CF` | `portrait_p2.dk` |
| Funky | `0x3E1` | `portrait_p2.fk` |

Beide Blöcke rufen `toggleNext` auf, setzen das richtige Icon sichtbar und beenden die Methode.

## 6.2 Rotation nach links

```text
Diddy -> Funky -> DK -> Cranky -> Dixie -> Diddy
```

Der P2-Dispatcher in `toggleLeft`, Methode 493, beginnt bei `0x34E`:

| Aktuelle Auswahl | Zielpfad |
|---|---:|
| Diddy | neuer Funky-Pfad bei `0x38A` |
| Dixie | vorhandener Diddy-Pfad bei `0x1AF` |
| Cranky | vorhandener Dixie-Pfad bei `0x1DC` |
| DK | vorhandener Cranky-Pfad bei `0x14E` |
| Funky | neuer DK-Pfad bei `0x3A9` |

Neue Abschlussblöcke:

| Zielauswahl | Abschlussblock | sichtbares Icon |
|---|---:|---|
| Funky | `0x3C8` | `portrait_p2.fk` |
| DK | `0x3DA` | `portrait_p2.dk` |

Beide Blöcke rufen `togglePrev` auf, setzen das richtige Icon sichtbar und beenden die Methode.

## 6.3 Wiederherstellung beim Öffnen

Der finale P2-Zusatz in `initMenu`, Methode 490, beginnt bei `0x4C3`.

```text
P2Selection == Diddy  -> vorhandener Diddy-Block bei 0x2B6
P2Selection == Dixie  -> vorhandener Dixie-Block bei 0x2E9
P2Selection == Cranky -> vorhandener Cranky-Block bei 0x31C
P2Selection == DK     -> neuer DK-Textblock bei 0x4FF
P2Selection == Funky  -> neuer Funky-Textblock bei 0x527
sonst                 -> vorhandener Fehlerpfad bei 0x357
```

Neue Iconblöcke:

| Auswahl | Iconblock | sichtbares Icon |
|---|---:|---|
| DK | `0x54F` | `portrait_p2.dk` |
| Funky | `0x55F` | `portrait_p2.fk` |

Damit werden DK und Funky nach Schließen und erneutem Öffnen sofort korrekt als P2-Auswahl dargestellt.

## 6.4 PauseMenu `resetPortraitP2`, Methode 501

Finale Codelänge: `58 Bytes`.

```actionscript
portrait_p2.diddy.visible = false;
portrait_p2.dixie.visible = false;
portrait_p2.cranky.visible = false;
portrait_p2.dk.visible = false;
portrait_p2.fk.visible = false;
```

Relevante Offsets:

```text
0x0003 diddy
0x000E dixie
0x0019 cranky
0x0024 dk
0x002F fk
0x0039 returnvoid
```

## 6.5 MasterShell `resetPortraitP2`, Methode 360

Finale Codelänge: `58 Bytes`.

| Feld | Multiname-Index |
|---|---:|
| `portrait_p2` | 302 |
| `visible` | 1485 |
| `dk` | 1489 |
| `fk` | 1490 |
| `diddy` | 1491 |
| `dixie` | 1492 |
| `cranky` | 1493 |

Die Methode blendet ebenfalls alle fünf P2-Porträts aus.

---

# 7. Finale Porträt-Timelines

In beiden Filmen sind nun beide Spielergruppen vollständig:

```text
PauseMenu  -> MenuCharacter.swf
MasterShell -> MenuCharacter.swf
```

## 7.1 Spieler 1: Sprite 15

| Tiefe | Instanz | Character-ID | Matrix |
|---:|---|---:|---|
| 1 | `dk` | 13 | `10 A0 00` |
| 3 | `fk` | 14 | `00` |
| 5 | `diddy` | 11 | `10 A0 00` |
| 7 | `dixie` | 10 | `10 A0 00` |
| 9 | `cranky` | 9 | `10 A0 00` |

Rohe hinzugefügte P1-`PlaceObject2`-Payloads:

```text
Diddy:  26 05 00 0B 00 10 A0 00 64 69 64 64 79 00
Dixie:  26 07 00 0A 00 10 A0 00 64 69 78 69 65 00
Cranky: 26 09 00 09 00 10 A0 00 63 72 61 6E 6B 79 00
```

## 7.2 Spieler 2: Sprite 12

| Tiefe | Instanz | Character-ID | Matrix |
|---:|---|---:|---|
| 1 | `cranky` | 9 | `00` |
| 3 | `dixie` | 10 | `00` |
| 5 | `diddy` | 11 | `00` |
| 7 | `dk` | 13 | `00` |
| 9 | `fk` | 14 | `00` |

Rohe hinzugefügte P2-`PlaceObject2`-Payloads:

```text
DK:    26 07 00 0D 00 00 64 6B 00
Funky: 26 09 00 0E 00 00 66 6B 00
```

## 7.3 Reproduzierbare P2-Timeline-Einstellungen

Die folgenden Kopien wurden in beiden `MenuCharacter.swf` ausgeführt.

### DK

```text
Quell-Sprite:       15
Quellinstanz:       dk
Ziel-Sprite:        12
Neuer Instanzname:  dk
Positionsanker:     diddy
Zieltiefe:          7
Ersetzen:           AUS
```

### Funky

```text
Quell-Sprite:       15
Quellinstanz:       fk
Ziel-Sprite:        12
Neuer Instanzname:  fk
Positionsanker:     diddy
Zieltiefe:          9
Ersetzen:           AUS
```

Die Tiefen `7` und `9` sowie die finalen Matrixwerte sind binär und im Spiel bestätigt.

---

# 8. Bestätigungsstatus

## Im Spiel bestätigt

- Spieler 1 kann alle fünf Kongs auswählen.
- Spieler 2 kann alle fünf Kongs auswählen.
- Beide Spieler besitzen ihren eigenen vollständigen Auswahlring.
- Beide Rechtsrotationen funktionieren.
- Beide Linksrotationen funktionieren.
- Alle Namen werden korrekt angezeigt.
- Alle P1- und P2-Porträts werden korrekt angezeigt.
- Beim Weiterrotieren verschwindet das vorherige Porträt.
- Beim erneuten Öffnen werden Name und Porträt der aktuellen P1- und P2-Auswahl korrekt wiederhergestellt.
- Der korrigierte P1-Rechtsweg verursacht keinen Absturz.

## Binär bestätigt

- `UIPak(10).pak` enthält 1659 PAK-Einträge.
- Gegenüber `UIPak(9).pak` wurden nur `PauseMenu` und `MasterShell` verändert.
- Beide `MenuCharacter.swf` enthalten in Sprite 15 alle fünf P1-Instanzen.
- Beide `MenuCharacter.swf` enthalten in Sprite 12 alle fünf P2-Instanzen.
- PauseMenu-Methoden 490, 492 und 493 enthalten die vollständige P1- und P2-Fünferlogik.
- PauseMenu-Methoden 500 und 501 blenden jeweils alle fünf Porträts aus.
- MasterShell-Methoden 359 und 360 blenden jeweils alle fünf Porträts aus.
- Alle finalen Methodenbodies, DoABC-Blöcke und SWF-Strukturen lassen sich fehlerfrei parsen.
- Sämtliche geprüften Sprungziele liegen auf gültigen Instruktionsgrenzen.

## Teil 1 abgeschlossen

```text
P1-UI-Rotation + P1-Text + P1-Porträts für alle fünf Kongs
```

## Teil 2 abgeschlossen

```text
P2-UI-Rotation + P2-Text + P2-Porträts für alle fünf Kongs
```

Damit ist die vollständige KONG-Select-UI für beide Spieler abgeschlossen.

---

# 9. Regeln für weitere Arbeit

1. Immer von `UIPak(10).pak` oder einem daraus nachweislich funktionierenden Nachfolger ausgehen.
2. Source und Timeline getrennt bearbeiten.
3. PauseMenu und MasterShell nicht als identische Codekopien behandeln.
4. Originalbytes vor jedem AVM2-Patch exakt validieren.
5. Bei variabler Länge alle relativen Sprünge und `lookupswitch`-Ziele manuell prüfen.
6. Jeder neue Sprung muss auf einer gültigen Instruktionsgrenze landen.
7. Vorschau-Bestätigung, binäre Bestätigung und Spiel-Bestätigung getrennt dokumentieren.
8. Den funktionierenden P1-Diddy-Abschlussblock der Rechtsrotation nicht wieder in den Dispatcher hineinleiten.
9. Keine PAK blind erzeugen oder verändern; der Nutzer baut und testet die PAK selbst.
