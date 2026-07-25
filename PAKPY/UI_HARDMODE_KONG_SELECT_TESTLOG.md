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

## Bereits im Spiel bestätigt

Das vorhandene Zwei-Spieler-Fundament verwendet:

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5

0x1E7018
29 15 1E 12 -> 29 19 1F 12
```

Bestätigtes Ergebnis:

- zwei echte Spieler starten im Hard Mode;
- P2 ist separat steuerbar;
- ohne funktionierende Selector-Übergabe bestimmt die native Hard-Mode-Logik P2 automatisch.

## Bestätigte automatische Paarungslogik

Der Nutzer hat Try 3 mit mehreren P1-Figuren geprüft. Das Verhalten ist eindeutig:

```text
P1 = DK      -> P2 = normaler/default P2-Charakter
P1 != DK     -> P2 = DK
```

Dies gilt für Funky, Diddy, Dixie und Cranky als P1: P2 wird jeweils DK.

Zusätzlich:

```text
Ladebildschirm-P2-Icon = Charakter aus der normalen 2-Spieler-Auswahl
```

Damit benutzen Ladebildschirm und endgültiger Spawn nicht zuverlässig denselben Zustand.

Die Spawn-Paarung entspricht exakt dem nativen Block:

```text
0x1E6FF4  P1-Wert konvertieren
0x1E6FFC  P1 mit interner DK-ID vergleichen
0x1E7000  temporären P2-Wert 1 setzen
0x1E7004  bei DK auf Wert 2 erhöhen
0x1E7008  P1 nach +0x2698 schreiben
0x1E700C  automatischen P2 nach +0x269C schreiben
```

## AVM2-Ausgangsstand

`UIPak(21).pak` enthält `chooseKongP2` und getrennte visuelle Eingabe.

Relevanter Stand von Methode 488:

```text
Methode 488: 219 Bytes
Dispatch bei 0x0C: 8E 00 00
PLAY-Einfügepunkt bei 0x2E: 60 F4 08
PLAY-lookupswitch-Fall bei 0xD1: 43 FF FF
```

Der originale PLAY-Aufruf übergibt bereits:

```actionscript
ExternalInterface.call(
    "initLevelTransition",
    "HARD",
    currentKong,
    int(getChildAt(2).currentState)
);
```

Der native Callback bei `0x35267C` liest nur `HARD` und den P1-Kong. Das dritte UI-Argument wird stockmäßig nicht als P2-Auswahl verarbeitet.

## Test 2 – zusätzlicher Callback und NOP bei 0x1E700C

Verwendeter Ansatz:

1. `chooseKongP2.currentState` über `kongMapping` in einen Kong-String umwandeln;
2. nach `mRuntimeData.Char_P2` schreiben;
3. `UpdateCharacterTypes()` zusätzlich aufrufen;
4. die automatische P2-Zuweisung bei `0x1E700C` entfernen.

```text
Methode 488: 219 -> 308 Bytes
IPS32-Records: 3
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Ausgeschlossen:

- der zusätzliche `UpdateCharacterTypes()`-Aufruf löst die Übergabe nicht;
- das bloße Entfernen des Stores bei `0x1E700C` löst die Übergabe nicht;
- der 92-Byte-AVM2-Block wird nicht weiterverwendet.

## Test 3 – nur Char_P2 schreiben

AVM2 schrieb unmittelbar vor `initLevelTransition`:

```actionscript
mRuntimeData.Char_P2 = kongMapping[int(chooseKongP2.currentState)];
```

Kein zusätzlicher nativer Callback.

ExeFS enthielt nur die zwei bestätigten Multiplayer-Patches:

```text
0x1E6FEC -> NOP
0x1E7018 -> AND #0xFE
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Beobachtung:

- Ladebildschirm zeigt weiterhin den normalen P2-Auswahlcharakter;
- Spawn benutzt weiterhin die automatische DK/default-Paarung;
- bei P1 außer DK ist P2 immer DK;
- bei P1 DK ist P2 der normale/default P2-Charakter.

Damit ist ausgeschlossen:

```text
Das bloße Schreiben von mRuntimeData.Char_P2 reicht nicht,
wenn der spätere native Reload nicht ausgeführt wird.
```

## Nachanalyse von Test 3

Nach der automatischen Paarung existiert bereits ein stockmäßiger Reload:

```text
0x352C58  Status über 0x33557C prüfen
0x352C60  bei false direkt zu 0x352CA4 springen
0x352C74  Runtime-Datenquelle laden
0x352C80  Runtime-Daten-ID 0x66 = Char_P2
0x352C88  Char_P2-String lesen
0x352C90  String in interne Kong-ID umwandeln
0x352CA0  Ergebnis nach +0x269C schreiben
```

Der beobachtete automatische Spawn beweist, dass dieser Reload in Try 3 nicht wirksam wurde. Der Branch bei `0x352C60` überspringt den Block.

Wichtig:

- `0x1E6FEC -> NOP` verhindert nur das Löschen von `+0x26AF`;
- ein NOP setzt den Wert nicht aktiv auf true;
- außerdem kann die Statusfunktion `0x33557C` über ihr Objekt/VTable-Ergebnis weiterhin false liefern;
- daher ist das bloße NOP bei `0x1E6FEC` keine Garantie, dass `0x352C74` ausgeführt wird.

## Test 4 – vorhandenen Char_P2-Reload erzwingen

### AVM2

Der minimale AVM2-Patch aus Test 3 bleibt bestehen:

```actionscript
mRuntimeData.Char_P2 = kongMapping[int(chooseKongP2.currentState)];
```

Methode 488:

```text
vorher: 219 Bytes
nachher: 254 Bytes
Einfügung: +35 Bytes
max_stack: 5
locals: 4
```

### ExeFS

Test 4 enthält:

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5

0x1E7018
29 15 1E 12 -> 29 19 1F 12

0x352C60
20 02 00 36 -> 1F 20 03 D5
```

Der dritte Eintrag entfernt ausschließlich den bedingten Sprung, der den vorhandenen `Char_P2`-Reload überspringt.

Ablauf von Test 4:

```text
1. AVM2 schreibt die Hard-Mode-P2-Auswahl nach Char_P2.
2. 0x1E700C setzt vorübergehend die automatische DK/default-Paarung.
3. 0x352C60 darf den Reload nicht mehr überspringen.
4. 0x352C74 liest Char_P2.
5. 0x352CA0 ersetzt die automatische P2-ID mit der Selector-Auswahl.
```

Nicht enthalten:

- kein `UpdateCharacterTypes()`-Zusatzaufruf;
- kein NOP bei `0x1E700C`;
- kein Hook, der Argumente aus `InitLevelTransition` liest;
- keine freie globale Variable oder Code-Cave.

### Erzeugte Testdateien

```text
UIPak21_hardmode_p2_try4.pak
exefs/F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips
```

Validierung außerhalb des Spiels:

```text
PAK/SWF/DoABC erneut vollständig geparst
Methode 488 erneut geparst
IPS32: 39 Bytes, drei Records, EEOF korrekt
Originalbytes aller drei IPS-Einträge stimmen mit der hochgeladenen main überein
```

### Status

```text
Noch nicht im Spiel bestätigt.
```

Bei einem Fehlschlag von Test 4 ist eindeutig ausgeschlossen, dass der stockmäßige Reload von Runtime-ID `0x66` die per AVM2 gesetzte P2-Auswahl enthält. Dann muss der dritte ExternalInterface-Wert direkt im Callback `0x35267C` abgegriffen und ohne Umweg über `mRuntimeData.Char_P2` in die endgültige P2-ID überführt werden.
