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

PAKPY validiert die unveränderte `main` und exportiert IPS32.

## Bestätigtes Zwei-Spieler-Fundament

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5

0x1E7018
29 15 1E 12 -> 29 19 1F 12
```

Im Spiel bestätigt:

- zwei echte Spieler starten im Hard Mode;
- P2 ist separat steuerbar;
- die P2-Slot-Aktivierung bleibt erhalten.

## Ursprüngliche automatische Paarung

```text
P1 = DK      -> P2 = normaler/default P2-Kong
P1 != DK     -> P2 = DK
```

Die automatische P2-ID wurde bei `0x1E700C` nach `state+0x269C` geschrieben.

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

Das Problem lag in der nativen Auswertung.

## Fehlgeschlagene Tests 2 bis 5

### Test 2

`mRuntimeData.Char_P2` schreiben und zusätzlich `UpdateCharacterTypes()` aufrufen.

```text
FEHLGESCHLAGEN
```

### Test 3

Nur `mRuntimeData.Char_P2` schreiben.

```text
FEHLGESCHLAGEN
```

### Test 4

Stockmäßigen `Char_P2`-Reload bei `0x352C60` erzwingen.

```text
FEHLGESCHLAGEN
```

Damit ist der gesamte indirekte Runtime-String-Umweg ausgeschlossen.

### Test 5

`UpdateCharacterTypes()` bei `0x3457A8` als eigenen Callback überschreiben.

```text
FEHLGESCHLAGEN: GAME-CRASH
```

Zusätzlich fehlte die Join-Animation. `0x3457A8` ist die aktive Originalroutine und keine freie Code-Cave. Außerdem wurde der ExternalInterface-Argumentzeiger falsch als Wert interpretiert. Test 5 wurde vollständig entfernt.

## Test 6 – funktionierender direkter Selector

Der vorhandene native Callback liest das dritte Argument korrekt über `entries+0x20`, mappt Slider `0..4` auf die internen IDs und schreibt die ausgewählte P2-ID nach `state+0x269C`.

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

```text
BESTÄTIGT: FUNKTIONIERT
```

Bestätigt:

- kein Crash;
- ausgewählter Hard-Mode-P2-Kong wird gespawnt;
- automatische DK/Default-Paarung überschreibt ihn nicht.

Bestätigter Nebeneffekt: Nach dem Verlassen des Hard Mode blieb der Hard-Mode-Kong als aktueller P2 gesetzt.

## P1- und P2-Reload in UpdateCharacterTypes

P1 wird beim normalen Character-Refresh immer aus `Char_P1` zurückgeladen:

```text
0x3457E0  Runtime-Datenquelle
0x3457EC  Runtime-ID 0x65 = Char_P1
0x3457FC  String -> Kong-ID
0x345814  Store state+0x2698
```

P2 besitzt bereits denselben Reload:

```text
0x345850  Runtime-Datenquelle
0x34585C  Runtime-ID 0x66 = Char_P2
0x34586C  String -> Kong-ID
0x34588C  Store state+0x269C
```

Stock liegt davor jedoch ein Skip:

```text
0x345848  BL 0x33557C
0x34584C  TBZ W0,#0,0x3458F4
```

## Test 7 – Reload über state+0x26AF gaten

Test 7 ersetzte die Stockprüfung durch:

```text
0x345848  LDRB W0,[X24,#0xF]   ; state+0x26AF
0x34584C  CBZ  W0,0x3458F4
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN FÜR MANUELLEN LEVEL-QUIT
```

Beobachtung:

- Hard-Mode-Selector funktioniert weiterhin;
- beim manuellen Verlassen des Levels bleibt der Hard-Mode-P2-Kong aktiv;
- regulärer Levelabschluss wurde mit diesem Test nicht geprüft.

Schlussfolgerung:

```text
Beim manuellen Quit ist state+0x26AF bereits 0,
bevor der Character-Refresh den normalen P2-Wert laden könnte.
```

Try 7 ersetzte damit nur eine false liefernde Prüfung durch eine andere false liefernde Prüfung. Die acht Byte bei `0x345848` werden nicht weiterverwendet.

## Test 8 – vorhandenen Char_P2-Reload unbedingt ausführen

Try 8 behielt den im Spiel bestätigten Try-6-Selector unverändert und entfernte ausschließlich den Skip vor dem bereits vorhandenen `Char_P2`-Reload:

```text
0x34584C
40 05 00 36
->
1F 20 03 D5
```

Der Aufruf bei `0x345848` blieb stock. Nur sein false-Ergebnis durfte den P2-Block nicht mehr überspringen.

Erwarteter Ablauf bei einem Character-Refresh:

```text
Char_P1 -> interne ID -> state+0x2698
Char_P2 -> interne ID -> state+0x269C
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN FÜR MANUELLEN LEVEL-QUIT
```

Auch der ungefilterte `Char_P2`-Reload stellte P2 beim manuellen Quit nicht wieder her. Daraus folgt, dass `UpdateCharacterTypes()` im relevanten Quit-Rückkehrpfad nicht als Restore-Mechanismus verwendet werden kann. Der Try-8-Patch bei `0x34584C` wurde aus dem aktiven Profil entfernt.

## Test 9 – P2 über denselben Hard-Mode-Initializer wie P1

Try 9 behält die bestätigte Auswertung des dritten `initLevelTransition`-Arguments, schreibt die gewählte P2-ID aber nicht mehr vorzeitig direkt nach `state+0x269C`.

Neuer Ablauf:

```text
chooseKongP2.currentState
-> drittes ExternalInterface-Argument bei entries+0x20
-> Slider 0..4 auf interne Kong-ID mappen
-> temporärer Store state+0x26C0
-> Hard-Mode-Initializer lädt state+0x26C0 bei 0x1E7000
-> originaler P2-Store bei 0x1E700C schreibt state+0x269C
```

ExeFS:

```text
0x1E6FEC -> P2-Zustand erhalten
0x1E7000 -> P2-ID aus state+0x26C0 laden
0x1E7004 -> DK-spezifisches Inkrement entfernen
0x1E7018 -> P2-Slot-Bit erhalten
0x3526EC -> Parser-Kontrollfluss
0x3527A0 -> P2-Slider parsen und nach state+0x26C0 schreiben
0x352B18 -> temporäre P2-ID bis zum Initializer erhalten
```

Wichtig:

- `0x1E700C` bleibt original und schreibt P2 innerhalb des normalen Hard-Mode-Initializers;
- kein `UpdateCharacterTypes()`-Restore-Patch;
- kein AVM2-Patch;
- `UIPak(21).pak` bleibt unverändert.

### In-Game-Ergebnis

```text
BESTÄTIGT: FUNKTIONIERT
```

Bestätigt:

- der in `chooseKongP2` ausgewählte Kong wird als echter, separat steuerbarer P2 gespawnt;
- kein Crash beim Start oder manuellen Verlassen des Levels;
- nach manuellem Quit bleibt der Hard-Mode-P2-Kong nicht persistent;
- der vor dem Hard Mode ausgewählte normale P2-Kong wird wiederhergestellt.

Damit ist das ursprüngliche Ziel für den getesteten manuellen Quit-Pfad erreicht. Ein regulärer Levelabschluss wurde weiterhin nicht separat bestätigt.
