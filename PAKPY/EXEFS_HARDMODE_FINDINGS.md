# DKCTF Hard Mode Multiplayer – native ExeFS findings

Diese Datei dokumentiert nur binär nachgewiesene Fakten aus der bereitgestellten DKCTF-`main`. Vermutete Feldnamen werden ausdrücklich nicht als bewiesen dargestellt.

## Referenz-Build

```text
main SHA-256:
018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21

Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Alle Offsets in dieser Datei sind **NSO-VA / module-relative Adressen**, nicht rohe Offsets innerhalb der komprimierten `main`-Datei.

---

# 1. UI-Aufrufe

## Normaler Levelstart

`MasterShell -> MapHUD.swf`, Klasse `map.MapDialog`, Methode `onPlayLevelSelect`:

```actionscript
ExternalInterface.call("initLevelTransition", "STANDARD");
```

Der normale Start übergibt nur den Modus. Die bereits gespeicherten Charakter- und Spielerzustände werden nativ verwendet.

## Hard-Mode-Start

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

---

# 2. Native Callback-Auflösung

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

Im Helfer liegt der Modus in `w23`. Der Hard-Mode-Zweig ist dadurch eindeutig:

```text
w23 == 2
0x352C18 -> 0x1E6FC0
```

`0x1E6FC0` ist somit die nachgewiesene native Hard-Mode-Initialisierung.

---

# 3. Native Charakterfelder und Aktivmaske

Der registrierte native Callback:

```text
UpdateCharacterTypes
Callback-Record: 0x193B638
Funktion:        0x3457A8
```

beweist die Bedeutung der relevanten Felder durch seinen Schreibpfad:

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

Der Callback setzt außerdem im Byte bei:

```text
+0x26A0
```

die aktiven Slots:

```text
Bit 0 = P1 aktiv
Bit 1 = P2 aktiv
```

Nach einer P1-Aktualisierung wird Bit 0 gesetzt. Nach einer P2-Aktualisierung wird Bit 1 gesetzt. Damit bedeutet der relevante Low-Bit-Zustand:

```text
01 = nur P1 aktiv
11 = P1 und P2 aktiv
```

---

# 4. Nachgewiesene Hard-Mode-Solosperre

Die Hard-Mode-Funktion bei `0x1E6FC0` macht drei getrennte Dinge:

1. Sie setzt die ausgewählte Hard-Mode-Figur nach `+0x2698`.
2. Sie überschreibt `+0x269C` mit einer automatisch bestimmten Ersatzfigur.
3. Sie erzwingt in `+0x26A0` den Zustand `01`.

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

Dadurch werden Bit 0 und Bit 1 zunächst gelöscht und anschließend nur Bit 0 wieder gesetzt. Ein bereits aktiver P2-Zustand wird also ausdrücklich entfernt. Das ist der konkrete native Grund, warum nach einem Hard-Mode-Start nur Spieler 1 aktiv bleibt.

---

# 5. Minimaler Testpatch 1 – nur P2-Aktivierung erhalten

Für den ersten Spieltest wird ausschließlich die Maske geändert:

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

Das Verhalten ist absichtlich konservativ:

```text
vorher 01 -> nachher 01
vorher 11 -> nachher 11
```

Damit bleibt Einzelspieler unverändert, während ein bereits gesetztes P2-Bit erhalten bleibt.

## Noch nicht Teil von Testpatch 1

Die Hard-Mode-Funktion überschreibt weiterhin bei:

```text
0x1E700C
```

das P2-Charakterfeld `+0x269C` mit einer automatisch bestimmten Figur.

Das bedeutet für Testpatch 1:

- Ziel des Tests ist ausschließlich, ob Spieler 2 im Hard Mode wieder aktiv/spawnbar wird.
- Die zuvor im KONG-Select gewählte P2-Figur muss in diesem ersten Test noch nicht erhalten bleiben.
- Ein separater zweiter Patch wird erst nach erfolgreichem Aktivierungstest gebaut, damit Aktivierung und Charakterübernahme nicht gleichzeitig verändert werden.

---

# 6. PAKPY-Patchprofil

PAKPY enthält jetzt das eingebaute Profil:

```text
Hard Mode: P2 aktiv halten – Test 1
```

GUI:

```text
Werkzeuge -> ExeFS Patchvorschau / IPS32
Ctrl+Shift+P
```

Das Profil:

- validiert die vollständige Build ID,
- prüft die erwarteten Originalbytes,
- zeigt NSO-VA und Atmosphère-IPS32-Offset,
- verändert niemals die geladene `main`,
- exportiert eine fertige Atmosphère-Verzeichnisstruktur,
- erzeugt zusätzlich `manifest.json` und `README.md`.

Für diesen Eintrag gilt:

```text
NSO-VA:      0x1E7018
IPS32-Offset: 0x1E7118
```

Atmosphère wendet ExeFS-Patches auf das dekomprimierte gemappte NSO an und zieht für NSO-Patches den geschützten Headeroffset `0x100` ab. Deshalb muss der IPS-Eintrag bei `NSO-VA + 0x100` liegen.

Offizielle Implementierung:

- `stratosphere/loader/source/ldr_patcher.cpp`
- `libraries/libstratosphere/source/patcher/patcher_api.cpp`

---

# 7. Aktueller Bestätigungsstatus

## Binär bestätigt

- `initLevelTransition("HARD", currentKong)` wird zu Modusenum 2.
- Modus 2 ruft die Hard-Initialisierung bei `0x1E6FC0` auf.
- `UpdateCharacterTypes` schreibt P1/P2 nach `+0x2698/+0x269C`.
- Bit 0/1 bei `+0x26A0` aktivieren P1/P2.
- Hard Mode löscht Bit 1 und erzwingt nur P1.
- Der Patch `29 15 1E 12 -> 29 19 1F 12` ist gegen den bereitgestellten Build exakt validiert.
- Der erzeugte IPS32-Eintrag ist strukturell validiert.

## Noch nicht im Spiel bestätigt

- Ob Testpatch 1 P2 im Hard Mode tatsächlich spawnen lässt.
- Welche automatisch gesetzte P2-Figur mit Testpatch 1 erscheint.
- Ob weitere Hard-Mode-Systeme P2 später erneut deaktivieren.
- Der spätere Erhalt der im KONG-Select ausgewählten P2-Figur.
