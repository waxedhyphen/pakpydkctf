# Hard Mode P2 selector – Testlog

Arbeitsstand: 2026-07-25

Ziel: `chooseKongP2` soll nicht nur visuell rotieren, sondern die tatsächliche Figur von Spieler 2 beim Start des Hard Mode bestimmen.

## Feste Arbeitsgrundlage

```text
UI:    UIPak(21).pak
ExeFS: exefs(11).zip / main
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Die `main` bleibt unverändert. PAKPY validiert daran die Originalbytes und exportiert anschließend ausschließlich IPS32.

## Bereits im Spiel bestätigt

Das vorhandene Zwei-Spieler-Fundament benutzt diese beiden ExeFS-Änderungen:

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5

0x1E7018
29 15 1E 12 -> 29 19 1F 12
```

Bestätigtes Ergebnis dieses Fundaments:

- zwei echte Spieler starten im Hard Mode;
- P2 ist separat steuerbar;
- die Figur von P2 wird ohne weitere Auswahlübergabe noch automatisch bestimmt.

## Test 1 – statische Prüfung des Uploads

`UIPak(21).pak` enthält `chooseKongP2` und getrennte visuelle Eingabe. Methode 488 besitzt folgenden eigenen Zwischenstand:

```text
Methode 488: 219 Bytes
Dispatch bei 0x0C: 8E 00 00
PLAY-Einfügepunkt bei 0x2E: 60 F4 08
PLAY-lookupswitch-Fall bei 0xD1: 43 FF FF
```

Das generische AVM2-Profil passt deshalb nicht bytegenau auf diesen PAK.

Zusätzlich wurde verifiziert:

```text
UpdateCharacterTypes callback: 0x3457A8
registrierte Argumentzahl: 0
```

## Test 2 – 92-Byte-AVM2-Block und drei ExeFS-Records

Verwendete Idee:

1. `chooseKongP2.currentState` über `kongMapping` in einen Kong-String umwandeln;
2. den String nach `mRuntimeData.Char_P2` schreiben;
3. zusätzlich `UpdateCharacterTypes()` aufrufen;
4. anschließend `initLevelTransition` aufrufen;
5. bei `0x1E700C` die automatische temporäre P2-Zuweisung mit NOP entfernen.

Erzeugter Stand:

```text
Methode 488: 219 -> 308 Bytes
IPS32-Records: 3
```

### In-Game-Ergebnis

```text
FEHLGESCHLAGEN
```

Der Nutzer hat bestätigt, dass die P2-Auswahl nicht übernommen wird. Dieser kombinierte Ansatz ist damit ausgeschlossen.

### Nachanalyse des fehlgeschlagenen Tests

Der originale AVM2-Stand übergibt bereits vier Werte an ExternalInterface:

```text
initLevelTransition("HARD", currentKong, chooseKongP2.currentState)
```

Der native Callback bei `0x35267C` wertet den dritten UI-Wert jedoch nicht als P2-Figur aus. Er bestimmt aus dem P1-String nur den Parameter für `CProductionFrontEnd::InitLevelTransition`.

Entscheidend ist ein späterer bereits vorhandener nativer Pfad:

```text
0x352C74: Runtime-Daten-ID 0x66 lesen
0x352C90: String -> interne Kong-ID
0x352CA0: Ergebnis nach +0x269C schreiben
```

ID `0x66` ist `Char_P2`. Dieser Block läuft, wenn der unabhängige P2-Pfad über `+0x26AF` aktiv bleibt. Genau das stellt der bereits bestätigte Patch bei `0x1E6FEC` sicher.

Daraus folgen zwei Korrekturen:

- `UpdateCharacterTypes()` ist an dieser Stelle nicht erforderlich;
- der zusätzliche NOP bei `0x1E700C` ist nicht erforderlich und wird aus dem nächsten Versuch entfernt.

## Test 3 – minimaler vorhandener Runtime-Datenpfad

### AVM2

Methode 488 schreibt unmittelbar vor dem originalen `initLevelTransition`-Aufruf nur:

```text
mRuntimeData.Char_P2 = kongMapping[int(chooseKongP2.currentState)]
```

Kein zusätzlicher nativer Callback wird aufgerufen.

Byteänderungen für `UIPak(21).pak`:

```text
0x0C: 8E 00 00 -> B1 00 00
0x2E: 60 F4 08 -> 38-Byte-Block
0xD1: 43 FF FF -> 20 FF FF
```

Strukturell geprüft:

```text
Methode 488 vorher: 219 Bytes
Methode 488 nachher: 254 Bytes
Einfügung:            +35 Bytes
max_stack:            weiterhin 5
locals:               weiterhin 4

anfängliches Ziel:
0x9D -> 0xC0

lookupswitch:
Position 0xCC -> 0xEF
PLAY-Ziel bleibt 0x0F
neuer Offset: -224
```

### ExeFS

Try 3 benutzt ausschließlich die zwei bereits im Spiel bestätigten Multiplayer-Änderungen:

```text
0x1E6FEC -> NOP
0x1E7018 -> AND #0xFE
```

Nicht mehr enthalten:

```text
0x1E700C -> NOP
```

Die stockmäßige temporäre DK/Diddy-Zuweisung darf zunächst stattfinden. Danach liest der vorhandene Block bei `0x352C74` den zuvor gesetzten Wert `Char_P2` und ersetzt die temporäre Figur.

### Erzeugte Testdateien

```text
UIPak21_hardmode_p2_try3.pak
exefs/F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips
```

Validierung außerhalb des Spiels:

```text
PAK-Methode 488 vollständig erneut geparst
DoABC- und SWF-Längen erneut geparst
MasterShell-Asset und PAK-Offsets erneut geparst
IPS32: 29 Bytes, zwei Records, EEOF korrekt
IPS-Originalbytes stimmen mit der hochgeladenen main überein
```

### Status

```text
Noch nicht im Spiel bestätigt.
```

Bei einem weiteren Fehlschlag ist der nächste ausgeschlossene Punkt eindeutig: Das Schreiben von `mRuntimeData.Char_P2` vor `initLevelTransition` erreicht den späteren nativen Reload bei `0x352C74` nicht oder wird zwischen beiden Stellen ersetzt.
