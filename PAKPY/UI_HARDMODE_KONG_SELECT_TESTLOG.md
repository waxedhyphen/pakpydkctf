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
