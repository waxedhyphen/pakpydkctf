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

Die Spawn-Paarung stammt aus:

```text
0x1E6FF4  P1-Wert konvertieren
0x1E6FFC  P1 mit interner DK-ID vergleichen
0x1E7000  automatischen P2-Wert 1 erzeugen
0x1E7004  bei P1=DK auf Wert 2 erhöhen
0x1E7008  P1 nach +0x2698 schreiben
0x1E700C  automatischen P2 nach +0x269C schreiben
```

## AVM2-Ausgangsstand

`UIPak(21).pak` enthält `chooseKongP2` und getrennte visuelle Eingabe.

Methode 488:

```text
Länge:                         219 Bytes
Dispatch bei 0x0C:             8E 00 00
PLAY-Einfügepunkt bei 0x2E:    60 F4 08
PLAY-lookupswitch bei 0xD1:    43 FF FF
max_stack:                      5
locals:                         4
```

Der Ausgangsstand übergibt bereits einen dritten Wert:

```actionscript
ExternalInterface.call(
    "initLevelTransition",
    "HARD",
    currentKong,
    int(getChildAt(2).currentState)
);
```

Der stockmäßige native Callback `0x35267C` verwendet diesen dritten Wert jedoch nicht als P2-Auswahl.

## Test 2 – Runtime-String, zusätzlicher Callback und NOP bei 0x1E700C

Ansatz:

1. Sliderzustand über `kongMapping` in einen String umwandeln;
2. String nach `mRuntimeData.Char_P2` schreiben;
3. `UpdateCharacterTypes()` zusätzlich aufrufen;
4. automatische Zuweisung bei `0x1E700C` entfernen.

```text
Methode 488: 219 -> 308 Bytes
IPS32-Records: 3
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Ausgeschlossen:

- zusätzlicher `UpdateCharacterTypes()`-Aufruf;
- bloßes NOP bei `0x1E700C`;
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

Damit wurde der Branch entfernt, der den vorhandenen Block übersprang:

```text
0x352C74  Runtime-ID 0x66 lesen
0x352C88  Char_P2-String lesen
0x352C90  String in interne Kong-ID umwandeln
0x352CA0  Ergebnis nach +0x269C schreiben
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Der Nutzer hat bestätigt, dass auch Try 4 die Sliderauswahl nicht übernimmt.

Damit ist ausgeschlossen:

- der vom Hard-Mode-Menü gesetzte `mRuntimeData.Char_P2`-Wert erreicht diesen Pfad nicht; oder
- Runtime-ID `0x66` enthält dort weiterhin den normalen P2-Auswahlwert.

Der gesamte `mRuntimeData.Char_P2`-Ansatz wird ab Test 5 nicht mehr verwendet.

## Test 5 – direkter nativer Sliderpfad

Test 5 umgeht vollständig:

- `mRuntimeData.Char_P2`;
- den normalen 2-Spieler-Charakterwert;
- den Ladebildschirm-P2-Zustand;
- den stockmäßigen `Char_P2`-Reload;
- die automatische DK/default-Paarung als endgültige Quelle.

### 1. AVM2

Unmittelbar vor dem originalen `initLevelTransition`-Aufruf wird ausgeführt:

```actionscript
ExternalInterface.call(
    "Char_P2",
    int(getChildAt(2).currentState)
);
```

Danach folgt unverändert der originale `initLevelTransition`-Aufruf.

Byteänderungen in Methode 488:

```text
0x0C: 8E 00 00 -> A3 00 00

0x2E:
60 F4 08
->
60 F4 08 2C DA 09 D0 24 02 46 F3 07 01
66 81 04 73 4F F5 08 02 60 F4 08

0xD1: 43 FF FF -> 2E FF FF
```

Strukturell:

```text
Methode 488 vorher: 219 Bytes
Methode 488 nachher: 240 Bytes
Nettoeinfügung:      +21 Bytes
max_stack:            5
locals:               4
anfängliches Ziel:    0x9D -> 0xB2
lookupswitch:         0xCC -> 0xE1
PLAY-Ziel:            weiterhin 0x0F
neuer Offset:         -210
```

### 2. Native Callback-Registrierung

Der vorhandene, von den analysierten SWFs nicht verwendete Callback-Slot `UpdateCharacterTypes` wird umgewidmet.

```text
Callback-Tabelle bei NSO-VA 0x193B638

Name:
UpdateCharacterTypes -> Char_P2

Argumentzahl:
0 -> 1

Funktionsadresse:
bleibt 0x3457A8
```

Byteänderung:

```text
90 07 52 01 00 00 00 00 00 00 00 00 00 00 00 00
->
48 66 51 01 00 00 00 00 01 00 00 00 00 00 00 00
```

### 3. Neuer Callback bei 0x3457A8

Der neue Handler:

1. prüft, dass mindestens ein Argument vorhanden ist;
2. liest den Sliderwert als Integer;
3. mappt ihn mit der echten nativen Funktion `0x27BE44`;
4. erhält dadurch exakt diese internen IDs:

```text
Slider 0 -> 1  DK
Slider 1 -> 2  Diddy
Slider 2 -> 6  Dixie
Slider 3 -> 7  Cranky
Slider 4 -> 8  Funky
```

5. lädt den Frontend-State über `0x32F66C`;
6. schreibt die fertige interne P2-ID nach `state + 0x26C0`.

Der Callback schreibt keinen String und verwendet keine Runtime-Daten-ID.

### 4. Stash bis zur Hard-Mode-Initialisierung erhalten

Stock löscht `+0x26C0` vor der Transition:

```text
0x352B18
1F C0 26 B9 -> 1F 20 03 D5
```

Dadurch bleibt die vom Slider gesetzte ID erhalten.

### 5. Automatische Paarung durch die gestashte ID ersetzen

Stock:

```text
0x1E7000  automatische P2-ID 1 erzeugen
0x1E7004  bei P1=DK auf 2 erhöhen
```

Test 5:

```text
0x1E7000
E8 03 00 32 -> 68 C2 66 B9
```

Das lädt `W8 = [X19 + 0x26C0]`.

```text
0x1E7004
08 15 88 1A -> 1F 20 03 D5
```

Die DK-Sondererhöhung wird entfernt.

Der originale Store bleibt bestehen:

```text
0x1E700C
STR W8, [X19, #0x269C]
```

Damit schreibt der Hard-Mode-Start exakt die zuvor nativ gemappte Slider-ID als endgültigen P2.

### 6. Weiterhin enthaltenes Zwei-Spieler-Fundament

```text
0x1E6FEC -> NOP
0x1E7018 -> AND #0xFE
```

### Erzeugte Dateien

```text
UIPak21_hardmode_p2_try5.pak
exefs/F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips
```

### Validierung außerhalb des Spiels

```text
PAK-Größe: 72.654.302 Bytes
PAK SHA-256:
16dca8a8747130426b6788a4e5ec51791aaaa13a9266e44fb4e52670371cebc0

IPS32-Größe: 187 Bytes
IPS32-Records: 7
IPS SHA-256:
2c774e5164388d38670ded112a4513a3678a3ff96f2e0a14e1b09d26b41203f5
```

Geprüft:

- PAK, eingebettetes `MasterShell`, `MapHUD.swf` und DoABC erneut vollständig geparst;
- Methode 488 erneut geparst;
- alle Sprungziele und `lookupswitch`-Offsets geprüft;
- Callback-Code als ARM64 assembliert und disassembliert;
- Callback ruft `0x656814`, `0x27BE44` und `0x32F66C` mit den vorgesehenen Registern auf;
- alle sieben IPS-Originalbytes stimmen mit der hochgeladenen `main` überein;
- IPS32 erneut geparst, alle Records und `EEOF` stimmen;
- Callback-Tabelle zeigt nach Anwendung auf `Char_P2`, Argumentzahl 1, Funktion `0x3457A8`;
- die Hard-Mode-Initialisierung lädt nach Anwendung die ID aus `+0x26C0`.

### Status

```text
Noch nicht im Spiel bestätigt.
```

Bei einem Fehlschlag von Test 5 ist der nächste eindeutig ausgeschlossene Punkt nicht mehr `Char_P2`, sondern entweder:

- der AVM2-Callback `Char_P2` wird vor `initLevelTransition` nicht aufgerufen;
- der Frontend-State von `0x32F66C` ist nicht dasselbe Objekt, das später als `X19` in `0x1E6FC0` verwendet wird;
- oder `+0x26C0` wird an einer weiteren, bislang nicht erfassten Stelle überschrieben.
