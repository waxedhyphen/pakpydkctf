# UI KONG Select: Teil 1 abgeschlossen

Diese Datei dokumentiert den finalen, **im Spiel bestätigten** Stand von Teil 1 des
KONG-Select-Umbaus:

- Spieler 1 kann im Menü zwischen allen fünf Kongs rotieren.
- Die Namen werden korrekt angezeigt.
- Die Porträts werden korrekt ein- und ausgeblendet.
- Der ausgewählte Kong bleibt beim erneuten Öffnen des Menüs korrekt dargestellt.

Der bestätigte Zyklus lautet:

```text
Rechts: DK -> FUNKY -> DIDDY -> DIXIE -> CRANKY -> DK
Links:  DK -> CRANKY -> DIXIE -> DIDDY -> FUNKY -> DK
```

Diese Dokumentation trennt weiterhin zwischen:

- **binär bestätigt**: direkt aus den enthaltenen SWF-/ABC-Daten gelesen
- **im Spiel bestätigt**: mit der finalen PAK getestet
- **noch offen**: gehört nicht zu Teil 1

Teil 1 bezeichnet hier die vollständige **Spieler-1-UI-Auswahl**. Unabhängige
Spieler-2-Auswahl, doppelte Kongs und alle Gameplay-/Spawn-Pfade sind separate
Arbeitsschritte.

---

# 1. Referenzdateien

## Historische Stände

| Rolle | Datei | Größe | SHA-256 |
|---|---:|---:|---|
| früher Ausgangsstand | `UIPak(7).pak` | 72.653.504 Bytes | `f007a0aeeef648a0a188bec8ba33b88a6d37d5c0316f7c753380136e88540850` |
| funktionierender DK/Funky/Diddy-Stand | `UIPak(8).pak` | 72.653.980 Bytes | `995a8066c9858a8910e0613a2e1e34f4cdaf733e117e8435a32ec18b85be7c9f` |
| finaler Teil-1-Stand | `UIPak(9).pak` | 72.654.140 Bytes | `11e4d12e63b3ad5b11c80f558fb817d1e3588f85e312b7758843480b24670101` |

## Änderungen von `UIPak(8).pak` zu `UIPak(9).pak`

Es wurden genau zwei PAK-Assets verändert:

| Asset | vorher | final | Delta |
|---|---:|---:|---:|
| `PauseMenu` (`GFX`) | 350.438 | 350.567 | +129 Bytes |
| `MasterShell` (`GFX`) | 432.172 | 432.203 | +31 Bytes |

Innerhalb dieser GFX-Assets änderten sich:

| Film | vorher | final | Delta |
|---|---:|---:|---:|
| `PauseMenu -> MenuCharacter.swf` | 30.875 | 30.896 | +21 Bytes |
| `PauseMenu -> Source` | 85.308 | 85.416 | +108 Bytes komprimiert |
| `MasterShell -> MenuCharacter.swf` | 30.871 | 30.892 | +21 Bytes |
| `MasterShell -> Source` | 62.428 | 62.438 | +10 Bytes komprimiert |

Alle übrigen PAK-Einträge sind zwischen diesen beiden Ständen unverändert.

---

# 2. Architektur: Source und Timeline sind getrennt

Die funktionierende Lösung besteht aus zwei unterschiedlichen Ebenen.

## `PauseMenu -> Source`

Diese Ebene steuert:

- `P1Selection`
- Rotation nach rechts und links
- sichtbaren lokalisierten Namen
- Wiederherstellung beim Öffnen des Menüs
- Sichtbarkeit der P1-Porträts während der Rotation

Relevante Klasse:

```text
PauseMenu -> Source
DoABC: erstes unbenanntes Root-Modul
Klasse: shell.MenuCharacter
```

## `PauseMenu/MasterShell -> MenuCharacter.swf`

Diese Ebene enthält die tatsächlichen Timeline-Instanzen der Porträts.

## `MasterShell -> Source`

Diese Ebene enthält zusätzlich eine eigene `resetPortraitP1`-Methode. Sie muss dieselben
fünf Instanznamen kennen, obwohl die wirksame Rotationslogik in `PauseMenu -> Source`
liegt.

**Folgerung:** Rotation und Icon-Timeline dürfen nicht als ein einziger Patch behandelt
werden. Beide Bereiche müssen separat geändert und separat geprüft werden.

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

## Lokalisierungsstrings

| Text | String-Index |
|---|---:|
| `$_P1_Title` | 2103 |
| `$_Character_DK` | 2104 |
| `$_Character_FK` | 2106 |
| `$_Character_Diddy` | 2111 |
| `$_Character_Dixie` | 2113 |
| `$_Character_Cranky` | 2115 |

---

# 4. Finale Source-Methoden

## Methodengrößen

| Bereich | Methode | Stock | `UIPak(8)` | final `UIPak(9)` |
|---|---|---:|---:|---:|
| PauseMenu | `initMenu` 490 | 1018 | 1085 | 1219 |
| PauseMenu | `toggleRight` 492 | 668 | 732 | 853 |
| PauseMenu | `toggleLeft` 493 | 668 | 732 | 846 |
| PauseMenu | `resetPortraitP1` 500 | 25 | 36 | 58 |
| MasterShell | `resetPortraitP1` 359 | 25 | 36 | 58 |

Alle fünf finalen Methodenbodies lassen sich aus `UIPak(9).pak` vollständig und ohne
strukturellen ABC-Fehler disassemblieren.

## 4.1 `initMenu`, Methode 490

Der finale Zusatz beginnt bei `0x3FA` und behandelt alle drei zusätzlichen Kongs.

```text
P1Selection == Diddy  -> Diddy-Text, Diddy-Icon, gemeinsame Fortsetzung
P1Selection == Dixie  -> Dixie-Text, Dixie-Icon, gemeinsame Fortsetzung
P1Selection == Cranky -> Cranky-Text, Cranky-Icon, gemeinsame Fortsetzung
sonst                 -> ursprünglicher Pfad
```

Binär bestätigte Ziele:

| Auswahl | Textblock | Iconblock |
|---|---:|---:|
| Diddy | `0x420` | innerhalb desselben Blocks ab `0x444` |
| Dixie | `0x453` | `0x4B3` |
| Cranky | `0x47B` | `0x4A3` |

Sinngemäß:

```actionscript
if (P1Selection == k_sDiddy) {
    setToggleText("$_Character_Diddy");
    portrait_p1.diddy.visible = true;
} else if (P1Selection == k_sDixie) {
    setToggleText("$_Character_Dixie");
    portrait_p1.dixie.visible = true;
} else if (P1Selection == k_sCranky) {
    setToggleText("$_Character_Cranky");
    portrait_p1.cranky.visible = true;
}
```

Damit funktionieren Name und Icon auch nach Schließen und erneutem Öffnen des Menüs.

## 4.2 `toggleRight`, Methode 492

Finale Rechtsrotation:

```text
DK -> Funky -> Diddy -> Dixie -> Cranky -> DK
```

Der neue Dispatcher beginnt bei `0x2BB`:

```text
aktuell Diddy  -> Dixie-Zweig bei 0x2E1
aktuell Dixie  -> Cranky-Zweig bei 0x300
aktuell Cranky -> vorhandener DK-Zweig bei 0x65
sonst          -> vorhandener Pfad
```

Die drei dedizierten Abschlussblöcke sind:

| Zielauswahl | Abschlussblock | sichtbares Icon |
|---|---:|---|
| Diddy | `0x31F` | `portrait_p1.diddy` |
| Dixie | `0x331` | `portrait_p1.dixie` |
| Cranky | `0x343` | `portrait_p1.cranky` |

### Kritische, bestätigte Rechtskorrektur

Ein früher Zwischenpatch ließ den Funky-zu-Diddy-Zweig bei `0x2B5` in den neu
angehängten Dispatcher springen. Dadurch wurde der Block mit einem falschen Stackzustand
betreten und das Spiel stürzte beim Rechtsdrücken ab.

Der funktionierende Stand springt stattdessen von `0x2B5` direkt zu `0x31F`, einem
eigenen Diddy-Abschlussblock:

```actionscript
P1_Character.toggleNext(...);
portrait_p1.diddy.visible = true;
return;
```

Diese Korrektur ist im Spiel bestätigt und darf nicht wieder entfernt oder auf den
Dispatcher zurückgeführt werden.

## 4.3 `toggleLeft`, Methode 493

Finale Linksrotation:

```text
DK -> Cranky -> Dixie -> Diddy -> Funky -> DK
```

Der finale Zusatz arbeitet so:

```text
DK             -> Cranky-Initialblock bei 0x29C
aktuell Diddy  -> vorhandener Funky-Zweig bei 0x38
aktuell Dixie  -> Diddy-Zweig bei 0x2E1
aktuell Cranky -> Dixie-Zweig bei 0x30B
sonst          -> vorhandener Fehlerpfad
```

Sichtbarkeitsblöcke:

| Zielauswahl | Block | sichtbares Icon |
|---|---:|---|
| Diddy | ab `0x2FA` | `portrait_p1.diddy` |
| Dixie | `0x32A` | `portrait_p1.dixie` |
| Cranky | `0x33C` | `portrait_p1.cranky` |

Der funktionierende linke Pfad verwendet weiterhin die bereits vorhandene
`toggleNext`-Property. Diese Benennung darf nicht allein aufgrund des Methodennamens
`toggleLeft` als Fehler behandelt werden; das Verhalten ist im Spiel korrekt bestätigt.

## 4.4 PauseMenu `resetPortraitP1`, Methode 500

Finale Codelänge: `58 Bytes`.

```actionscript
portrait_p1.dk.visible = false;
portrait_p1.fk.visible = false;
portrait_p1.diddy.visible = false;
portrait_p1.dixie.visible = false;
portrait_p1.cranky.visible = false;
```

Relevante finale Offsets:

```text
0x0003 dk
0x000E fk
0x0019 diddy
0x0024 dixie
0x002F cranky
0x0039 returnvoid
```

## 4.5 MasterShell `resetPortraitP1`, Methode 359

Finale Codelänge: `58 Bytes`.

MasterShell verwendet andere Multiname-Indizes:

| Feld | Multiname-Index |
|---|---:|
| `portrait_p1` | 301 |
| `visible` | 1485 |
| `dk` | 1489 |
| `fk` | 1490 |
| `diddy` | 1491 |
| `dixie` | 1492 |
| `cranky` | 1493 |

Die finale Methode blendet ebenfalls alle fünf P1-Porträts aus.

---

# 5. Finale Porträt-Timeline

## Vorhandene P2-Quellen

In Sprite 12 liegen die drei Partner-Kong-Grafiken:

| Instanz | Character-ID | Tiefe | Matrix |
|---|---:|---:|---|
| `cranky` | 9 | 1 | `00` |
| `dixie` | 10 | 3 | `00` |
| `diddy` | 11 | 5 | `00` |

## P1-Zielgruppe

Spieler 1 verwendet Sprite 15.

In der finalen PAK enthalten **beide** Filme dieselbe vollständige P1-Gruppe:

```text
PauseMenu  -> MenuCharacter.swf -> Sprite 15
MasterShell -> MenuCharacter.swf -> Sprite 15
```

| Tiefe | Instanz | Character-ID | Matrix |
|---:|---|---:|---|
| 1 | `dk` | 13 | `10 A0 00` |
| 3 | `fk` | 14 | `00` |
| 5 | `diddy` | 11 | `10 A0 00` |
| 7 | `dixie` | 10 | `10 A0 00` |
| 9 | `cranky` | 9 | `10 A0 00` |

Damit verwenden Diddy, Dixie und Cranky die bereits vorhandenen P2-Grafiken, aber die
bestätigte P1-DK-Positionsmatrix.

## Rohe `PlaceObject2`-Payloads

### Diddy

```text
26 05 00 0B 00 10 A0 00 64 69 64 64 79 00
```

### Dixie

```text
26 07 00 0A 00 10 A0 00 64 69 78 69 65 00
```

### Cranky

```text
26 09 00 09 00 10 A0 00 63 72 61 6E 6B 79 00
```

## Reproduzierbare Timeline-Editor-Einstellungen

Für beide Filme wurden die gleichen Kopien ausgeführt.

### Dixie

```text
Quell-Sprite:       12
Quellinstanz:       dixie
Ziel-Sprite:        15
Neuer Instanzname:  dixie
Positionsanker:     dk
Zieltiefe:          7
Ersetzen:           AUS
```

### Cranky

```text
Quell-Sprite:       12
Quellinstanz:       cranky
Ziel-Sprite:        15
Neuer Instanzname:  cranky
Positionsanker:     dk
Zieltiefe:          9
Ersetzen:           AUS
```

Die Tiefen `7` und `9` sind jetzt nicht mehr nur Vorschlagswerte, sondern binär und im
Spiel bestätigte Endwerte.

---

# 6. Bestätigungsstatus

## Im Spiel bestätigt

- Rechtsrotation: `DK -> Funky -> Diddy -> Dixie -> Cranky -> DK`.
- Linksrotation: `DK -> Cranky -> Dixie -> Diddy -> Funky -> DK`.
- Diddy-, Dixie- und Cranky-Texte werden korrekt angezeigt.
- Diddy-, Dixie- und Cranky-P1-Porträts werden korrekt angezeigt.
- Beim Weiterrotieren verschwindet das vorherige Porträt.
- Beim erneuten Öffnen des Menüs werden Name und Porträt der aktuellen Auswahl korrekt
  wiederhergestellt.
- Der korrigierte Rechtsweg verursacht keinen Crash mehr.

## Binär bestätigt

- `UIPak(9).pak` enthält 1659 PAK-Einträge.
- Gegenüber `UIPak(8).pak` wurden nur `PauseMenu` und `MasterShell` verändert.
- Beide `MenuCharacter.swf` enthalten in Sprite 15 alle fünf P1-Instanzen.
- PauseMenu-Methoden 490, 492, 493 und 500 enthalten die finale Fünferlogik.
- MasterShell-Methode 359 blendet alle fünf P1-Porträts aus.
- Alle finalen Methodenbodies und SWF-Strukturen lassen sich fehlerfrei parsen.

## Teil 1 abgeschlossen

Teil 1 ist abgeschlossen:

```text
P1-UI-Rotation + P1-Text + P1-Porträts für DK, Funky, Diddy, Dixie und Cranky
```

---

# 7. Noch offen / Teil 2 und später

Nicht durch Teil 1 abgedeckt:

- Spieler 2 unabhängig auf DK/Funky erweitern
- Spieler 1 und Spieler 2 unabhängig jeden Kong wählen lassen
- zweimal denselben Kong erlauben
- Gameplay-/Spawn-/Hard-Mode-/Frontend-Sonderpfade vollständig verifizieren
- Auswahlzustände außerhalb dieses konkreten Menüpfads prüfen

Diese Punkte dürfen nicht als durch `UIPak(9).pak` bestätigt bezeichnet werden.

---

# 8. Regeln für weitere Arbeit

1. Immer von `UIPak(9).pak` oder einem daraus nachweislich funktionierenden Nachfolger
   ausgehen.
2. Source und Timeline getrennt bearbeiten.
3. PauseMenu und MasterShell nicht als identische Codekopien behandeln.
4. Originalbytes vor jedem AVM2-Patch exakt validieren.
5. Bei variabler Länge alle relativen Sprünge und `lookupswitch`-Ziele manuell prüfen.
6. Jeder neue Sprung muss auf einer gültigen Instruktionsgrenze landen.
7. Vorschau-Bestätigung, binäre Bestätigung und Spiel-Bestätigung getrennt dokumentieren.
8. Den funktionierenden Diddy-Abschlussblock der Rechtsrotation bei `0x31F` nicht wieder
   in den Dispatcher hineinleiten.
9. Keine PAK blind erzeugen oder verändern; der Nutzer baut und testet die PAK selbst.
