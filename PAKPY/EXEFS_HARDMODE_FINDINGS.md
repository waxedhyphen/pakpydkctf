# DKCTF Hard Mode Multiplayer – native ExeFS findings

Diese Datei dokumentiert nur binär nachgewiesene Fakten aus der bereitgestellten DKCTF-`main`. Vermutete Feldnamen werden nicht als bewiesen dargestellt.

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

Der Hard-Mode-Start übergibt zusätzlich genau einen Kong und schreibt vor dem Übergang nur `Char_P1`.

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

Im Helfer liegt der Modus in `w23`. Der Hard-Mode-Zweig ist eindeutig:

```text
w23 == 2
0x352C18 -> 0x1E6FC0
```

`0x1E6FC0` ist damit die nachgewiesene native Hard-Mode-Initialisierung.

## 3. Native Charakterfelder und Aktivmaske

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

## 4. Nachgewiesene Hard-Mode-Solosperre

Die Hard-Mode-Funktion bei `0x1E6FC0`:

1. setzt die ausgewählte Hard-Mode-Figur nach `+0x2698`,
2. überschreibt `+0x269C` mit einer automatisch bestimmten Ersatzfigur,
3. erzwingt in `+0x26A0` den Zustand `01`.

Der entscheidende Block:

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

Dadurch werden Bit 0 und Bit 1 gelöscht und anschließend nur Bit 0 wieder gesetzt. Das ist der konkrete native Grund, warum Hard Mode P2 deaktiviert.

## 5. Minimaler Testpatch 1

Nur die Maske wird geändert:

```asm
Original:
0x1E7018  AND W9, W9, #0xFC
Bytes:    29 15 1E 12

Neu:
0x1E7018  AND W9, W9, #0xFE
Bytes:    29 19 1F 12
```

Neue Semantik:

```c
flags = (flags & 0xFE) | 1;
```

```text
vorher 01 -> nachher 01
vorher 11 -> nachher 11
```

Einzelspieler bleibt unverändert; ein bereits aktiver P2-Slot bleibt erhalten.

Noch nicht Teil dieses Tests: Bei `0x1E700C` wird das P2-Charakterfeld `+0x269C` weiterhin mit einer automatisch bestimmten Figur überschrieben. Der erste Test prüft ausschließlich, ob P2 aktiv/spawnbar bleibt.

## 6. Datengetriebenes PAKPY-Projekt

Der DKCTF-Testpatch ist **nicht** im Python-Code hardcodiert. Er liegt ausschließlich als externe Projektdatei vor:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test1.json
```

Die universelle Engine und GUI enthalten keine DKCTF-Adresse, Build ID oder Gameplay-Patchliste.

GUI:

```text
Werkzeuge -> ExeFS Patchprojekt / IPS32
Ctrl+Shift+P
```

Ablauf:

1. beliebige `main` laden,
2. beliebiges JSON-Projekt laden oder Einträge manuell erstellen,
3. Build ID und Originalbytes validieren,
4. IPS32 in einen Emulator-Modordner oder eine Atmosphère-Struktur exportieren.

Für dieses externe Projekt gilt:

```text
NSO-VA:       0x1E7018
IPS32-Offset: 0x1E7118
```

Die vollständige universelle Projektarchitektur und das JSON-Schema stehen in `EXEFS_PATCH_PROJECTS.md`.

## 7. Bestätigungsstatus

### Binär bestätigt

- `initLevelTransition("HARD", currentKong)` wird zu Modusenum 2.
- Modus 2 ruft die Hard-Initialisierung bei `0x1E6FC0` auf.
- `UpdateCharacterTypes` schreibt P1/P2 nach `+0x2698/+0x269C`.
- Bit 0/1 bei `+0x26A0` aktivieren P1/P2.
- Hard Mode löscht Bit 1 und erzwingt nur P1.
- `29 15 1E 12 -> 29 19 1F 12` ist gegen den Referenz-Build exakt validiert.
- Der erzeugte IPS32-Eintrag ist strukturell validiert.

### Noch nicht im Spiel bestätigt

- ob Testpatch 1 P2 im Hard Mode tatsächlich spawnen lässt,
- welche automatisch gesetzte P2-Figur erscheint,
- ob spätere Hard-Mode-Systeme P2 erneut deaktivieren,
- der spätere Erhalt der im KONG-Select ausgewählten P2-Figur.
