# Hard Mode P2 selector – Testlog

Arbeitsstand: 2026-07-25

Ziel: `chooseKongP2` soll im Hard Mode den echten P2-Kong bestimmen, ohne den normalen P2-Kong nach der Rückkehr dauerhaft zu verändern.

## Arbeitsgrundlage

```text
UI: UIPak(21).pak
ExeFS: exefs(11).zip / main
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

PAKPY validiert die unveränderte `main` und exportiert ausschließlich IPS32.

## Im Spiel bestätigtes Zwei-Spieler-Fundament

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5

0x1E7018
29 15 1E 12 -> 29 19 1F 12
```

Bestätigt:

- zwei echte Spieler starten im Hard Mode;
- P2 ist separat steuerbar;
- die P2-Slot-Aktivierung bleibt erhalten.

## Ursprüngliche automatische Paarung

Vor dem funktionierenden Selector-Patch galt:

```text
P1 = DK      -> P2 = normaler/default P2-Kong
P1 != DK     -> P2 = DK
```

Die Paarung wurde hier erzeugt:

```text
0x1E6FF4  P1 konvertieren
0x1E6FFC  P1 mit DK vergleichen
0x1E7000  automatischen P2-Wert 1 erzeugen
0x1E7004  bei P1=DK auf Wert 2 erhöhen
0x1E7008  P1 nach state+0x2698 schreiben
0x1E700C  P2 nach state+0x269C schreiben
```

## UI-Ausgangsstand

`UIPak(21).pak` übergibt den P2-Slider bereits als drittes Argument:

```actionscript
ExternalInterface.call(
    "initLevelTransition",
    "HARD",
    currentKong,
    int(getChildAt(2).currentState)
);
```

Das Problem lag in der nativen Auswertung, nicht in der UI.

## Fehlgeschlagene Versuche

### Test 2 – `mRuntimeData.Char_P2` plus `UpdateCharacterTypes()`

```text
FEHLGESCHLAGEN
```

Ausgeschlossen:

- zusätzlicher `UpdateCharacterTypes()`-Aufruf vor dem Start;
- bloßes Schreiben nach `mRuntimeData.Char_P2`;
- zugehöriger 92-Byte-AVM2-Block.

### Test 3 – ausschließlich `mRuntimeData.Char_P2`

```text
FEHLGESCHLAGEN
```

Ladebildschirm und Spawn verwendeten weiterhin den normalen beziehungsweise automatisch ermittelten P2-Wert.

### Test 4 – stockmäßigen `Char_P2`-Reload erzwingen

```text
0x352C60
20 02 00 36 -> 1F 20 03 D5
```

```text
FEHLGESCHLAGEN
```

Der gesamte `mRuntimeData.Char_P2`-Umweg ist ausgeschlossen.

### Test 5 – `UpdateCharacterTypes` als eigenen Callback verwenden

```text
FEHLGESCHLAGEN: GAME-CRASH
```

Beobachtungen:

- Join-Animation fehlte;
- Crash in `CTransitionScene::CheckObjectsLoaded()`;
- Nullzugriff auf Adresse `0x0`.

Ursachen:

1. `0x3457A8` ist die aktive Originalroutine `UpdateCharacterTypes()`, keine freie Code-Cave.
2. Try 5 interpretierte `[x2+0x08]` falsch; dort liegt der Zeiger auf die Argumenteinträge.
3. Das dritte Argument liegt bei `entries+0x20`.

Try 5 wurde vollständig entfernt.

## Test 6 – funktionierender direkter P2-Selector

### PAK / AVM2

```text
UIPak21_hardmode_p2_try6.pak ist byteidentisch zu UIPak(21).pak.
Keine zusätzliche AVM2-Änderung.
```

### Nativer Ablauf

```text
1. P1 wie stock auswerten.
2. Drittes initLevelTransition-Argument über entries+0x20 lesen.
3. Slider 0..4 in die interne Kong-ID umwandeln.
4. P2-ID direkt nach state+0x269C schreiben.
5. Originalen initLevelTransition-Aufruf fortsetzen.
```

Zuordnung:

```text
0 -> DK     -> ID 1
1 -> Diddy  -> ID 2
2 -> Dixie  -> ID 6
3 -> Cranky -> ID 7
4 -> Funky  -> ID 8
```

ExeFS:

```text
0x1E6FEC -> NOP
0x1E700C -> NOP
0x1E7018 -> AND #0xFE
0x3526EC -> korrigierter Parser-Branch
0x3527A0 -> 164-Byte-Kompaktparser
```

### In-Game-Ergebnis

```text
BESTÄTIGT: FUNKTIONIERT
```

Bestätigt:

- kein Crash;
- ausgewählter Hard-Mode-P2-Kong wird gespawnt;
- automatische DK/Default-Paarung überschreibt ihn nicht mehr.

### Bestätigter Nebeneffekt

Nach dem Verlassen des Hard Mode blieb der Hard-Mode-Kong als aktueller P2 gesetzt.

Grund:

```text
Try 6 schreibt die temporäre Hard-Mode-Auswahl direkt nach state+0x269C.
```

Dieses Feld ist der echte aktuelle P2-Zustand. Der normale P2-Wert wurde nach der Rückkehr nicht erneut geladen.

## Analyse des P1-Rückkehrverhaltens

P1 wird nicht über ein separates Spawn-Objekt zurückgetauscht. Der normale Frontend-Refresh `UpdateCharacterTypes()` lädt P1 erneut aus Runtime-ID `0x65` (`Char_P1`):

```text
0x3457E0  Runtime-Datenquelle laden
0x3457EC  ID 0x65 = Char_P1
0x3457FC  String in interne Kong-ID umwandeln
0x345814  nach state+0x2698 schreiben
```

Dadurch überschreibt der normale P1-Wert nach der Rückkehr die temporäre Hard-Mode-P1-ID.

P2 besitzt bereits denselben Reload:

```text
0x345850  Runtime-Datenquelle laden
0x34585C  ID 0x66 = Char_P2
0x34586C  String in interne Kong-ID umwandeln
0x34588C  nach state+0x269C schreiben
```

Stock wird dieser P2-Block jedoch nur ausgeführt, wenn `0x33557C` den temporären P2-Player-Status als aktiv meldet. Beim Rückkehr-Refresh kann diese zusätzliche Prüfung false sein, obwohl der echte Zwei-Spieler-Zustand weiterhin aktiv ist. Deshalb wurde P1 zurückgesetzt, P2 aber nicht.

## Test 7 – P2 beim Refresh wie P1 neu laden

Try 7 behält den bestätigten Try-6-Selector vollständig bei und ändert nur das Gate vor dem bereits vorhandenen P2-Reload.

### Änderung in `UpdateCharacterTypes()`

Stock:

```text
0x345848: BL 0x33557C
0x34584C: TBZ W0,#0,0x3458F4
```

Try 7:

```text
0x345848: LDRB W0,[X24,#0xF]   ; state+0x26AF
0x34584C: CBZ  W0,0x3458F4
```

Bytes:

```text
0x345848
4D BF FF 97 40 05 00 36
->
00 3F 40 39 40 05 00 34
```

`X24` zeigt in dieser Routine bereits auf `state+0x26A0`; `X24+0xF` ist daher exakt `state+0x26AF`.

Neues Verhalten:

```text
state+0x26AF = 0 -> stockmäßiger Inaktiv-P2-Pfad
state+0x26AF != 0 -> vorhandenen Char_P2-Reload ausführen
```

Damit wird bei verbundenem P2 nach der Rückkehr derselbe Mechanismus verwendet wie bei P1:

```text
normaler Runtime-Kong -> interne ID -> aktueller Frontend-Zustand
```

Es wird kein eigener Backup-Slot und kein zusätzlicher Exit-Hook eingeführt.

### Try-7-ExeFS-Records

```text
0x1E6FEC   4 Bytes
0x1E700C   4 Bytes
0x1E7018   4 Bytes
0x345848   8 Bytes
0x3526EC   4 Bytes
0x3527A0 164 Bytes
```

### Unverändert

- PAK ist byteidentisch zu `UIPak(21).pak` und Try 6;
- Try-6-Selectorparser bleibt unverändert;
- vorhandener `Char_P2`-Reload-Body bleibt unverändert;
- Join-/Character-Update-Code nach dem Gate bleibt unverändert;
- Callback-Registrierung bleibt unverändert;
- originaler Transition-Call und Epilog bleiben unverändert.

### Dateien

```text
UIPak21_hardmode_p2_try7.pak
exefs/F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips
```

```text
PAK SHA-256:
58ce2f8a1ee15f02ccd3edd5b3b3ea06126059da3ef1ac0f20d5538743783fe3

IPS-Größe: 233 Bytes
IPS SHA-256:
0d44f9ceae96db0d5a3282e0c09a358dfdde1f542f72870ebc1df6241bb25871

Paket SHA-256:
2e418551d40f82700bbf0c2ff4eeb8b4eb002be58c3cfa16a549f673ca746805
```

### Status

```text
Noch nicht im Spiel bestätigt.
```

Prüfung:

1. normalen P2-Kong auswählen;
2. im Hard Mode einen anderen P2-Kong wählen;
3. Hard Mode verlassen;
4. nach der Rückkehr muss wieder der vorherige normale P2-Kong aktiv sein;
5. Hard-Mode-Auswahl, Join-Animation und Übergang dürfen nicht regressieren.
