# DKCTF Hard Mode Multiplayer – native ExeFS findings

Diese Datei dokumentiert binär nachgewiesene Fakten aus der bereitgestellten DKCTF-`main`. In-Game-Beobachtungen stehen zusätzlich in `EXEFS_HARDMODE_TEST_LOG.md`.

## Referenz-Build

```text
main SHA-256:
018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21

Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Alle Offsets sind **NSO-VA / module-relative Adressen**, nicht rohe Offsets innerhalb der komprimierten `main`-Datei.

## 1. UI-Aufrufe

### Normaler Levelstart

`MasterShell -> MapHUD.swf`, Klasse `map.MapDialog`, Methode `onPlayLevelSelect`:

```actionscript
ExternalInterface.call("initLevelTransition", "STANDARD");
```

Der normale Start übergibt nur den Modus. Bereits gespeicherte Charakter- und Spielerzustände werden nativ verwendet.

### Hard-Mode-Start

`MasterShell -> MapHUD.swf`, Klasse `map.menu_hardmode`, Methode `inputSelect`:

```actionscript
Controller.SetDataValue(
    "menu_hardmode::toggleRight",
    "mRuntimeData",
    "Char_P1",
    currentKong
);

ExternalInterface.call(
    "initLevelTransition",
    "HARD",
    currentKong
);
```

Der Stock-Hard-Mode-Start schreibt nur `Char_P1` und übergibt nur einen Kong an die native Transition.

## 2. Native Callback-Auflösung

```text
Callbackname-String: 0x1520A98
rodata-Pointer:      0xBEFBE0
Callback-Record:     0x193BB40
Native Funktion:     0x35267C
```

Der Stringparser bei `0x1F50EC` bildet die Modi exakt ab:

| String | Enum |
|---|---:|
| `STANDARD` | 0 |
| `TIME` | 1 |
| `HARD` | 2 |
| `GAUNTLET` | 3 |

Der Callback bei `0x35267C` liest den Modus aus dem ersten Argument. Ein optionales zweites Argument wird als Kong ausgewertet. Danach wird der gemeinsame Übergangshelfer bei `0x352AA0` aufgerufen.

Der Hard-Mode-Zweig ist eindeutig:

```text
w23 == 2
0x352C18 -> 0x1E6FC0
```

`0x1E6FC0` ist die nachgewiesene native Hard-Mode-Initialisierung.

## 3. Charakterfelder und Aktivmaske

Der registrierte Callback `UpdateCharacterTypes` liegt bei:

```text
Callback-Record: 0x193B638
Funktion:        0x3457A8
```

Sein Schreibpfad beweist:

```text
+0x2698 = Player-1-Charakter-ID
+0x269C = Player-2-Charakter-ID
```

Die Kong-Auswahl wird über die Tabelle bei `0x151E320` in interne IDs umgesetzt:

| UI-Kongindex | interne ID |
|---:|---:|
| 0 | 1 |
| 1 | 2 |
| 2 | 6 |
| 3 | 7 |
| 4 | 8 |

Das Byte bei `+0x26A0` enthält die aktiven Slots:

```text
Bit 0 = P1 aktiv
Bit 1 = P2 aktiv

01 = nur P1 aktiv
11 = P1 und P2 aktiv
```

## 4. Erster Hard-Mode-Soloblocker: Aktivmaske

Die Hard-Mode-Funktion bei `0x1E6FC0`:

1. setzt die ausgewählte Hard-Mode-Figur nach `+0x2698`,
2. überschreibt `+0x269C` mit einer automatisch bestimmten Partnerfigur,
3. erzwingt in `+0x26A0` den Zustand `01`.

Der Block:

```asm
0x1E7010  MOV  W8, #0x26A0
0x1E7014  LDRB W9, [X19, X8]
0x1E7018  AND  W9, W9, #0xFC
0x1E701C  ORR  W9, W9, #1
0x1E7028  STRB W9, [X19, X8]
```

Sinngemäß:

```c
flags = (flags & 0xFC) | 1;
```

Dadurch werden Bit 0 und Bit 1 gelöscht und nur Bit 0 wieder gesetzt.

### Testpatch 1

```asm
0x1E7018
29 15 1E 12  AND W9, W9, #0xFC
29 19 1F 12  AND W9, W9, #0xFE
```

Neue Semantik:

```c
flags = (flags & 0xFE) | 1;
```

In-Game-Ergebnis: P2 blieb als Piggyback-/Begleiter-Kong vorhanden, war aber noch kein unabhängiger Spieler. Der Patch war damit nur teilweise erfolgreich.

## 5. Zweiter Hard-Mode-Soloblocker: Zustand `+0x26AF`

Hard Mode setzt ein separates Statusbyte auf null:

```asm
0x1E6FE4  MOV  W8, #0x26AF
0x1E6FEC  STRB WZR, [X19, X8]
```

Originalbytes:

```text
7F 6A 28 38
```

Die Funktion bei `0x33557C`, die sowohl von `UpdateCharacterTypes` als auch vom Transition-Helfer verwendet wird, liest dieses Byte zuerst:

```text
+0x26AF == 0 -> false
```

Bei `false` wird der unabhängige P2-Pfad nicht aktiviert. Der Quellname dieses Feldes ist noch nicht bewiesen; deshalb bleibt die Dokumentation adressbasiert.

### Testpatch 2

```asm
0x1E6FEC
7F 6A 28 38  STRB WZR, [X19, X8]
1F 20 03 D5  NOP

0x1E7018
29 15 1E 12  AND W9, W9, #0xFC
29 19 1F 12  AND W9, W9, #0xFE
```

In-Game-Ergebnis: **bestätigt**.

- Hard Mode startet mit zwei echten Spielern.
- P2 ist unabhängig vorhanden.
- Der zweite Controller kann P2 steuern.
- Die Multiplayer-Aktivierung ist für den Referenz-Build gelöst.

Externes Projekt:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test2.json
```

## 6. Verbleibende automatische Figurenpaarung

Der Multiplayer-Pfad funktioniert, aber Hard Mode bestimmt die Figuren weiterhin automatisch:

```text
P1 = DK      -> P2 = Diddy
P1 = Diddy   -> P2 = DK
P1 = Dixie   -> P2 = DK
andere Buddy-Kongs -> P2 = DK
```

Funky ist im Stock-Hard-Mode-Selector im normalen Modus nicht auswählbar. Die Hard-Mode-Initialisierung überschreibt weiterhin das P2-Charakterfeld bei `+0x269C`.

Das ist jetzt ein getrenntes Auswahlproblem. Der nächste Hauptschritt ist daher UI-seitig:

- zwei Selector-Instanzen im Hard-Mode-Menü,
- eine für P1 und eine für P2,
- später jeweils vollständiger Fünferzyklus,
- danach Übergabe beider gewählten Werte an die bereits funktionierende native Multiplayer-Initialisierung.

UI-Dokumentation:

```text
PAKPY/UI_HARDMODE_KONG_SELECT.md
```

## 7. Datengetriebenes PAKPY-System

Die DKCTF-Patches sind nicht in der universellen Python-Engine hardcodiert. Sie liegen als externe JSON-Projekte vor:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test1.json
PAKPY/exefs_profiles/dkctf_hardmode_p2_test2.json
```

GUI:

```text
Werkzeuge -> ExeFS Patchprojekt / IPS32
Ctrl+Shift+P
```

Die Engine validiert Build ID, Originalbytes, Segmentgrenzen und Überschneidungen und kann direkt in einen Emulator-Modordner exportieren.

## 8. Bestätigungsstatus

### Binär bestätigt

- `initLevelTransition("HARD", currentKong)` wird zu Modusenum 2.
- Modus 2 ruft `0x1E6FC0` auf.
- `UpdateCharacterTypes` schreibt P1/P2 nach `+0x2698/+0x269C`.
- Bit 0/1 bei `+0x26A0` aktivieren P1/P2.
- Hard Mode löscht Bit 1 an `0x1E7018`.
- Hard Mode löscht den separaten Zustand bei `+0x26AF` an `0x1E6FEC`.
- Beide Test-2-Einträge sind gegen den Referenz-Build exakt validiert.

### Im Spiel bestätigt

- Test 1 erzeugt Partner-/Piggyback-Verhalten, aber keinen echten P2.
- Test 2 aktiviert einen unabhängigen, steuerbaren P2 im Hard Mode.

### Noch offen

- freie Auswahl des P1-Kongs im neuen Hard-Mode-UI,
- freie Auswahl des P2-Kongs im neuen Hard-Mode-UI,
- Funky im vollständigen Fünferzyklus,
- Übergabe und Erhalt beider gewählten Charaktere.
