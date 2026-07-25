# Hard Mode P2 selector – Testlog

Arbeitsstand: 2026-07-25

Ziel: `chooseKongP2` soll die tatsächlich geladene und gespawnte Figur von Spieler 2 im Hard Mode bestimmen.

## Feste Arbeitsgrundlage

```text
UI:    UIPak(21).pak
ExeFS: exefs(11).zip / main
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Die `main` bleibt unverändert. PAKPY validiert daran die Originalbytes und exportiert ausschließlich IPS32.

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

## Bestätigte automatische Paarungslogik

```text
P1 = DK      -> P2 = normaler/default P2-Charakter
P1 != DK     -> P2 = DK
```

Für Funky, Diddy, Dixie und Cranky als P1 wird P2 immer DK.

Zusätzlich bestätigt:

```text
Ladebildschirm-P2-Icon = Charakter aus der normalen 2-Spieler-Auswahl
```

Ladebildschirm und endgültiger Spawn benutzen daher nicht zuverlässig denselben Zustand.

Die automatische Spawn-Paarung stammt aus:

```text
0x1E6FF4  P1-Wert konvertieren
0x1E6FFC  P1 mit interner DK-ID vergleichen
0x1E7000  automatischen P2-Wert 1 erzeugen
0x1E7004  bei P1=DK auf Wert 2 erhöhen
0x1E7008  P1 nach +0x2698 schreiben
0x1E700C  automatischen P2 nach +0x269C schreiben
```

## AVM2-Ausgangsstand

`UIPak(21).pak` enthält `chooseKongP2` und übergibt dessen Zustand bereits an den nativen Übergang:

```actionscript
ExternalInterface.call(
    "initLevelTransition",
    "HARD",
    currentKong,
    int(getChildAt(2).currentState)
);
```

Der Slider ist damit bereits das dritte Callback-Argument. Das Problem liegt in der nativen Auswertung, nicht in einer fehlenden UI-Übergabe.

## Test 2 – Runtime-String und zusätzlicher UpdateCharacterTypes-Aufruf

Ansatz:

1. Sliderzustand über `kongMapping` in einen String umwandeln;
2. String nach `mRuntimeData.Char_P2` schreiben;
3. `UpdateCharacterTypes()` zusätzlich aufrufen;
4. automatische Zuweisung bei `0x1E700C` entfernen.

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Ausgeschlossen:

- zusätzlicher `UpdateCharacterTypes()`-Aufruf;
- bloßes Schreiben nach `mRuntimeData.Char_P2` in diesem Ablauf;
- der 92-Byte-AVM2-Block.

## Test 3 – ausschließlich mRuntimeData.Char_P2 schreiben

AVM2:

```actionscript
mRuntimeData.Char_P2 = kongMapping[int(chooseKongP2.currentState)];
```

ExeFS enthielt ausschließlich das bestätigte Zwei-Spieler-Fundament.

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Beobachtung:

- Ladebildschirm zeigt weiterhin den normalen P2-Charakter;
- Spawn benutzt weiterhin die automatische DK/default-Paarung.

Ausgeschlossen:

```text
Ein AVM2-Write nach mRuntimeData.Char_P2 allein erreicht den endgültigen Spawn nicht.
```

## Test 4 – stockmäßigen Char_P2-Reload erzwingen

Zusätzlicher ExeFS-Eintrag:

```text
0x352C60
20 02 00 36 -> 1F 20 03 D5
```

Dadurch wurde der Branch entfernt, der den stockmäßigen `Char_P2`-Reload übersprang.

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Der vom Hard-Mode-Menü gesetzte Wert erreicht diesen Pfad nicht, oder Runtime-ID `0x66` enthält dort weiterhin den normalen P2-Auswahlwert. Der gesamte `mRuntimeData.Char_P2`-Ansatz ist damit ausgeschlossen.

## Test 5 – umgewidmeter UpdateCharacterTypes-Callback

Ansatz:

- zusätzlichen AVM2-Aufruf `Char_P2(slider)` einfügen;
- Callback-Registrierung `UpdateCharacterTypes` in `Char_P2` umbenennen;
- Originalroutine bei `0x3457A8` durch eigenen 100-Byte-Handler ersetzen;
- Slider-ID in `state+0x26C0` zwischenspeichern;
- automatische Paarung aus diesem Feld laden.

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN: GAME-CRASH
```

Zusätzlich beobachtet:

```text
Beim Hinzufügen von Spieler 2 erscheint keine Join-Animation mehr.
```

Ryujinx lädt alle sieben Try-5-IPS-Records. Der Absturz erfolgt später auf dem MainThread während des Ladeübergangs:

```text
CProductionLoadingScreen::TimerTick(float)
CTransitionScene::CheckObjectsLoaded()
Invalid memory access at virtual address 0x0
```

### Nachanalyse von Test 5

Try 5 hatte zwei konkrete Fehler.

#### Fehler 1: aktive Originalroutine überschrieben

`0x3457A8` ist keine freie Code-Cave. Dort liegt die echte, aktive Routine `UpdateCharacterTypes()`.

Die Originalroutine:

- liest P1/P2-Runtimewerte;
- schreibt die Charakter-IDs;
- aktualisiert Slot- und Spielerzustände;
- löst weitere Character- und Join-Abläufe aus.

Das Überschreiben dieser Routine erklärt die fehlende Join-Animation und kann einen unvollständigen Übergangszustand erzeugen. Ab Test 6 bleiben Routine und Callback-Registrierung vollständig stock.

#### Fehler 2: Callback-Argument falsch gelesen

Die ExternalInterface-Callback-Struktur ist:

```text
[x2 + 0x00] = Argumentanzahl
[x2 + 0x08] = Zeiger auf 16-Byte-Argumenteinträge
```

Try 5 behandelte `[x2+0x08]` fälschlich direkt als Sliderargument. Das war nur der Zeiger auf das Argument-Array.

Für `initLevelTransition("HARD", P1, P2Slider)` liegt der Slider korrekt bei:

```text
entries + 0x20
```

Damit konnte Try 5 einen falschen Wert als Kong-ID in den Übergang schreiben.

### Konsequenz

Vollständig gestrichen:

- AVM2-Aufruf `Char_P2`;
- Callback-Umbenennung bei `0x193B638`;
- Überschreiben von `UpdateCharacterTypes()` bei `0x3457A8`;
- Stash `+0x26C0`;
- Patch bei `0x352B18`;
- Try-5-Änderungen bei `0x1E7000` und `0x1E7004`.

## Test 6 – drittes initLevelTransition-Argument direkt auswerten

Test 6 verwendet den bereits in `UIPak(21)` vorhandenen Aufruf. Es wird kein neuer ExternalInterface-Callback eingeführt.

### PAK / AVM2

```text
UIPak21_hardmode_p2_try6.pak ist byteidentisch zu UIPak(21).pak.
Keine AVM2-Änderung.
```

PAK:

```text
Größe: 72.654.598 Bytes
SHA-256:
58ce2f8a1ee15f02ccd3edd5b3b3ea06126059da3ef1ac0f20d5538743783fe3
```

### Native Auswertung im vorhandenen Callback

Der vorhandene Callback `initLevelTransition` bei `0x35267C` wird nur innerhalb seines bisherigen P1-Vergleichsblocks erweitert.

Ablauf:

```text
1. P1-String wie bisher in die interne P1-ID umwandeln.
2. Argumentanzahl auf mindestens 3 prüfen.
3. Argumenteinträge über [x22+0x08] laden.
4. Dritten Eintrag über entries+0x20 adressieren.
5. Sliderwert als Integer lesen.
6. Slider 0..4 mit der stockmäßigen Tabelle mappen.
7. Interne P2-ID direkt nach state+0x269C schreiben.
8. Originalen initLevelTransition-Aufruf und Epilog unverändert fortsetzen.
```

Stockmäßige Zuordnung:

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

`0x1E700C` wird entfernt, weil der Callback die ausgewählte P2-ID bereits direkt nach `+0x269C` geschrieben hat. Die automatische DK/default-Paarung darf sie danach nicht ersetzen.

### Unverändert gegenüber Stock

```text
UpdateCharacterTypes-Routine 0x3457A8: vollständig unverändert
UpdateCharacterTypes-Registrierung: vollständig unverändert
Join-/Character-Update-Pfad: nicht gepatcht
initLevelTransition-Call und Epilog ab 0x352844: unverändert
```

### Erzeugte Dateien

```text
UIPak21_hardmode_p2_try6.pak
exefs/F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips
```

IPS32:

```text
Größe: 219 Bytes
Records: 5
SHA-256:
e7ccb0da541b88d61b5bd3cc6559d6ce08954aed8d320c4fd093e569cf77d9ee
```

Paket:

```text
SHA-256:
a012a66b85178f9ae32c1c010e44e90fbfc82ba48d1a1988c10753237b664e83
```

### Validierung außerhalb des Spiels

Geprüft:

- Try-6-PAK ist byteidentisch zum hochgeladenen `UIPak(21).pak`;
- IPS32 enthält genau fünf Records und einen korrekten `EEOF`-Footer;
- alle Originalbytes stimmen mit der hochgeladenen `main` überein;
- `UpdateCharacterTypes()` ist byteidentisch zu Stock;
- Callback-Registrierung ist byteidentisch zu Stock;
- der dritte GFX-Argumenteintrag wird über `entries+0x20` gelesen;
- der neue Inline-Block wurde als ARM64 assembliert und disassembliert;
- alle Branch-Ziele bleiben innerhalb des vorgesehenen Callback-Ablaufs;
- der originale `initLevelTransition`-Call und Epilog bleiben unverändert.

### Status

```text
Noch nicht im Spiel bestätigt.
```

Prüfpunkte für den In-Game-Test:

1. Beim Hinzufügen von P2 muss die Join-Animation wieder vorhanden sein.
2. Das Spiel darf beim Ladeübergang nicht abstürzen.
3. Der gespawnte P2 muss dem Hard-Mode-Slider entsprechen.
4. Testmatrix: P1=DK und P1!=DK jeweils mit mindestens zwei verschiedenen P2-Auswahlen.
