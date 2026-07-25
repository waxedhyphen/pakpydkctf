# Hard Mode P2 selector – Testlog

Arbeitsstand: 2026-07-25

Ziel: `chooseKongP2` soll nicht nur visuell rotieren, sondern die tatsächliche Figur von Spieler 2 beim Start des Hard Mode bestimmen.

## Test 1 – hochgeladene ExeFS und aktueller PAK-Stand

Eingaben:

```text
UIPak(21).pak
exefs(11).zip
```

### ExeFS-Prüfung

`exefs(11).zip` enthält eine unveränderte `main`. Das ist beim PAKPY-Workflow korrekt: Die `main` dient ausschließlich als validierte Quelle; exportiert wird eine IPS32-Datei.

Verifiziert:

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

NSO-VA 0x1E6FEC:
7F 6A 28 38

NSO-VA 0x1E700C:
68 9E 26 B9

NSO-VA 0x1E7018:
29 15 1E 12
```

Damit passt die hochgeladene `main` exakt zum Profil `dkctf_hardmode_real_p2_selector.json`. Ein IPS32-Export ist gegen Build ID und Originalbytes möglich.

### Native Callback-Prüfung

Die Callback-Registrierung wurde direkt aus `main` verifiziert:

```text
Name: UpdateCharacterTypes
Callback: 0x3457A8
Argumentzahl: 0
```

`UpdateCharacterTypes()` liest die beiden Runtime-Werte über die internen IDs `0x65` und `0x66`, wandelt sie in Kong-IDs um und schreibt sie nach `+0x2698` und `+0x269C`. Der korrigierte AVM2-Aufruf mit null Argumenten entspricht damit der realen nativen Signatur.

`InitLevelTransition` erhält keine separate P2-Auswahl aus einem dritten UI-Argument. Im Hard-Mode-Pfad überschreibt es P2 später automatisch. Deshalb bleiben die drei ExeFS-Einträge erforderlich:

```text
0x1E6FEC: Initialisierungsbyte nicht löschen
0x1E700C: P2-Feld +0x269C nicht automatisch überschreiben
0x1E7018: aktives P2-Slot-Bit erhalten
```

### PAK-Prüfung

`UIPak(21).pak` enthält zwar `chooseKongP2`, aber Methode 488 besitzt einen eigenen Zwischenstand:

```text
Methode 488 Länge: 219 Bytes
Dispatch bei 0x0C: 8E 00 00
PLAY-Einfügepunkt bei 0x2E: 60 F4 08
PLAY-lookupswitch-Fall bei 0xD1: 43 FF FF
```

Dieser Stand unterscheidet sich um 11 Bytes von den Ausgangsbytes des generischen Repo-Profils. Das Profil darf deshalb nicht unverändert auf `UIPak(21).pak` angewendet werden. Es braucht einen exakt angepassten Patch mit neu berechneten Sprungzielen.

### Ergebnis

Ausgeschlossen:

- Die unveränderte `main` ist kein Fehler; sie ist die korrekte IPS-Quelle.
- `UpdateCharacterTypes()` erwartet keine P1/P2-Argumente.
- Ein Hook in `InitLevelTransition`, der UI-Args lesen soll, ist der falsche Ansatz.
- Das generische AVM2-Profil passt bytegenau nicht auf `UIPak(21).pak`.

Noch nicht im Spiel bestätigt:

- angepasster AVM2-Patch für Methode 488;
- erzeugte IPS32-Datei;
- tatsächliche Übernahme der P2-Auswahl im Level.

## Test 2 – angepasster PAK-Patch und IPS32-Export

### AVM2-Patch für `UIPak(21).pak`

Neues Profil:

```text
PAKPY/avm2_profiles/dkctf_hardmode_real_p2_selector_uipak21.json
```

Änderungen an Methode 488:

```text
0x0C: 8E 00 00 -> E7 00 00
0x2E: 60 F4 08 -> 92-Byte-Block
0xD1: 43 FF FF -> EA FE FF
```

Der eingefügte Block:

1. liest `chooseKongP2.currentState`;
2. mappt den Zustand über `kongMapping` auf den Kong-String;
3. schreibt den String nach `mRuntimeData.Char_P2`;
4. ruft `UpdateCharacterTypes()` ohne Figurenargumente auf;
5. setzt anschließend den ursprünglichen `initLevelTransition`-Ablauf fort.

Strukturell verifiziert:

```text
Methode 488 vorher: 219 Bytes
Methode 488 nachher: 308 Bytes
Einfügung:            +89 Bytes

anfängliches Sprungziel:
0x9D -> 0xF6

finaler lookupswitch:
Position 0xCC -> 0x125
PLAY-Ziel bleibt 0x0F
neuer relativer Offset: -278
```

Das gepatchte `MapHUD.swf` wurde nach dem Umbau erneut vollständig geparst. Methode 488, DoABC-Länge, SWF-Dateilänge, eingebettetes `MasterShell`-Asset und PAK-Offsets wurden erneut validiert.

### IPS32

Die unveränderte `main` wurde nur zur Prüfung verwendet. Exportiert wurde eine 39 Byte große IPS32-Datei mit exakt drei Records:

```text
IPS32 0x1E70EC -> 1F 20 03 D5
IPS32 0x1E710C -> 1F 20 03 D5
IPS32 0x1E7118 -> 29 19 1F 12
```

Diese IPS32-Offets entsprechen jeweils:

```text
NSO-VA + 0x100 NSO-Header
```

Die IPS-Datei wurde anschließend erneut geparst; Header, drei Recordlängen, Offsets, Ersatzbytes und `EEOF`-Footer stimmen.

### Erzeugte Testdateien

```text
UIPak21_hardmode_p2_fixed.pak
exefs/F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips
```

### Ergebnis

Bestätigt außerhalb des Spiels:

- PAK passt exakt auf den hochgeladenen `UIPak(21)`-Zwischenstand;
- `Char_P2` wird vor dem Levelstart geschrieben;
- der native Null-Argument-Callback wird danach aufgerufen;
- die IPS verhindert anschließend die automatische P2-Ersetzung;
- die Original-`main` wird nicht verändert oder ausgeliefert.

Noch offen und nur im Spiel prüfbar:

- ob der Emulator die IPS aus dem verwendeten Modordner lädt;
- ob die gewählte P2-Figur im Level erscheint;
- Verhalten aller fünf P2-Auswahlen und doppelter Kong-Kombinationen.
