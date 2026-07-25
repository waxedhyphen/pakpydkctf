# Hard Mode P2 selector – Testlog

Arbeitsstand: 2026-07-25

Ziel: `chooseKongP2` soll die tatsächlich geladene und gespawnte Figur von Spieler 2 im Hard Mode bestimmen.

## Arbeitsgrundlage

```text
UI:    UIPak(21).pak
ExeFS: exefs(11).zip / main
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Die `main` bleibt unverändert. PAKPY validiert die Originalbytes und exportiert ausschließlich IPS32.

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
- ohne funktionierende Selector-Übergabe bestimmt die native Hard-Mode-Logik P2 automatisch.

## Bestätigte ursprüngliche Auto-Paarung

```text
P1 = DK      -> P2 = normaler/default P2-Charakter
P1 != DK     -> P2 = DK
```

Für Funky, Diddy, Dixie und Cranky als P1 wurde P2 immer DK.

Der Ladebildschirm zeigte dabei den Charakter aus der normalen 2-Spieler-Auswahl, obwohl der endgültige Spawn abweichen konnte.

Die Auto-Paarung stammt aus:

```text
0x1E6FF4  P1-Wert konvertieren
0x1E6FFC  P1 mit interner DK-ID vergleichen
0x1E7000  automatischen P2-Wert 1 erzeugen
0x1E7004  bei P1=DK auf Wert 2 erhöhen
0x1E7008  P1 nach +0x2698 schreiben
0x1E700C  automatischen P2 nach +0x269C schreiben
```

## UI-Ausgangsstand

`UIPak(21).pak` übergibt den zweiten Slider bereits als drittes natives Argument:

```actionscript
ExternalInterface.call(
    "initLevelTransition",
    "HARD",
    currentKong,
    int(getChildAt(2).currentState)
);
```

Das Problem lag daher nicht in einer fehlenden UI-Übergabe, sondern darin, dass der native Callback das dritte Argument nicht als P2-Kong auswertete.

## Fehlgeschlagene Versuche

### Test 2 – `mRuntimeData.Char_P2` plus `UpdateCharacterTypes()`

```text
FEHLGESCHLAGEN
```

Ausgeschlossen:

- zusätzlicher Aufruf von `UpdateCharacterTypes()`;
- bloßes Schreiben eines Kong-Strings nach `mRuntimeData.Char_P2`;
- der zugehörige 92-Byte-AVM2-Block.

### Test 3 – ausschließlich `mRuntimeData.Char_P2`

```text
FEHLGESCHLAGEN
```

Ladebildschirm und Spawn benutzten weiterhin den normalen beziehungsweise automatisch ermittelten P2-Wert.

### Test 4 – stockmäßigen `Char_P2`-Reload erzwingen

Zusätzlicher Patch:

```text
0x352C60
20 02 00 36 -> 1F 20 03 D5
```

```text
FEHLGESCHLAGEN
```

Damit ist der gesamte `mRuntimeData.Char_P2`-Umweg ausgeschlossen.

### Test 5 – `UpdateCharacterTypes` als eigenen Callback verwenden

```text
FEHLGESCHLAGEN: GAME-CRASH
```

Zusätzliche Beobachtung:

```text
Beim Hinzufügen von P2 fehlte die Join-Animation.
```

Ryujinx-Log:

```text
CProductionLoadingScreen::TimerTick(float)
CTransitionScene::CheckObjectsLoaded()
Invalid memory access at virtual address 0x0
```

Ursachen:

1. `0x3457A8` ist keine freie Code-Cave, sondern die aktive Originalroutine `UpdateCharacterTypes()`.
2. Try 5 behandelte `[x2+0x08]` fälschlich als Sliderwert; dort liegt nur der Zeiger auf die 16-Byte-Argumenteinträge.
3. Das dritte Argument liegt korrekt bei `entries+0x20`.

Vollständig gestrichen:

- zusätzlicher AVM2-Aufruf `Char_P2`;
- Umbenennung der Callback-Registrierung;
- Überschreiben von `UpdateCharacterTypes()`;
- Stash bei `+0x26C0`;
- Try-5-Patches bei `0x352B18`, `0x1E7000` und `0x1E7004`.

## Test 6 – funktionierender direkter Pfad

### PAK / AVM2

```text
UIPak21_hardmode_p2_try6.pak ist byteidentisch zu UIPak(21).pak.
Keine zusätzliche AVM2-Änderung.
```

Der bereits vorhandene dritte Parameter wird direkt im originalen nativen `initLevelTransition`-Callback verarbeitet.

### Ablauf

```text
1. P1-String wie bisher in die interne P1-ID umwandeln.
2. Argumentanzahl auf mindestens 3 prüfen.
3. Argumenteinträge über [x22+0x08] laden.
4. Drittes Argument über entries+0x20 lesen.
5. Sliderwert als Integer auswerten.
6. Slider 0..4 mit der nativen Kong-Tabelle mappen.
7. Interne P2-ID direkt nach state+0x269C schreiben.
8. Originalen initLevelTransition-Aufruf fortsetzen.
```

Zuordnung:

```text
Slider 0 -> DK     -> interne ID 1
Slider 1 -> Diddy  -> interne ID 2
Slider 2 -> Dixie  -> interne ID 6
Slider 3 -> Cranky -> interne ID 7
Slider 4 -> Funky  -> interne ID 8
```

### ExeFS-Records

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5

0x1E700C
68 9E 26 B9 -> 1F 20 03 D5

0x1E7018
29 15 1E 12 -> 29 19 1F 12

0x3526EC
8B 0A 00 54 -> 8B 05 00 54

0x3527A0
164-Byte-P1-Vergleichsblock -> 164-Byte-Kompaktparser
```

`0x1E700C` wird entfernt, weil der Callback die ausgewählte P2-ID bereits direkt nach `state+0x269C` geschrieben hat. Die automatische DK/Default-Paarung darf diese ID danach nicht ersetzen.

### Unverändert gegenüber Stock

```text
UpdateCharacterTypes-Routine 0x3457A8: vollständig unverändert
UpdateCharacterTypes-Registrierung: vollständig unverändert
Join-/Character-Update-Pfad: nicht gepatcht
initLevelTransition-Call und Epilog: unverändert
```

### In-Game-Ergebnis

```text
BESTÄTIGT: FUNKTIONIERT
```

Bestätigt:

- kein Crash beim Übergang;
- der ausgewählte Hard-Mode-P2-Kong wird tatsächlich verwendet;
- die automatische DK/Default-Paarung überschreibt die Auswahl nicht mehr.

Die Wiederherstellung der Join-Animation wurde in dieser Rückmeldung nicht ausdrücklich separat bestätigt.

## Bestätigter Nebeneffekt: Auswahl bleibt nach Rückkehr erhalten

Beobachtung:

```text
Nach dem Verlassen des Hard Mode ist P2 nicht wieder der vorherige Standard-Kong,
sondern weiterhin der im Hard-Mode-Selector gewählte Kong.
```

Erklärung:

Try 6 tauscht nicht nur beim Spawn ein Character-Objekt aus. Der Patch schreibt die ausgewählte interne P2-Kong-ID direkt in den echten Frontend-/Transition-State:

```text
state + 0x269C
```

Dieses Feld ist der aktuelle native P2-Charakterzustand. Es wird nach dem Hard-Mode-Übergang nicht automatisch auf den vorherigen normalen P2-Wert zurückgesetzt. Wenn das Spiel später wieder auf denselben Zustand zugreift, ist dort weiterhin der Hard-Mode-Kong gespeichert.

Damit ist das aktuelle Verhalten:

```text
Hard-Mode-Auswahl -> tatsächlicher P2-Zustand wird geändert
Levelstart        -> P2 spawnt mit diesem Kong
Rückkehr          -> derselbe Kong bleibt als aktueller P2 gesetzt
```

Es handelt sich daher nicht um einen rein temporären visuellen oder Spawn-Swap, sondern um eine echte Änderung des aktuellen P2-Kong-Zustands.

Ein späterer Cleanup-Fix müsste vor dem Hard-Mode-Start den vorherigen P2-Wert sichern und ihn beim Verlassen beziehungsweise bei der Rückkehr gezielt wiederherstellen.
