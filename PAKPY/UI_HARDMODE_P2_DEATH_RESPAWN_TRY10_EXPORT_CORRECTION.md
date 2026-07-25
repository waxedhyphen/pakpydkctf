# Hard Mode P2 death/respawn – Try 10 IPS32 export correction

Arbeitsstand: 2026-07-25

## Erster In-Game-Start

```text
FEHLGESCHLAGEN: GAME-CRASH
```

Dieser Start bewertet **nicht** die Try-10-HP-Logik. Die ausgelieferte IPS32-Datei war falsch serialisiert.

## Exakte Ursache

Ryujinx wendet IPS32-Recordadressen mit einem `-0x100`-Bias an. Der erste manuell erzeugte Try-10-Export schrieb die gewünschten Runtime-Offets direkt in die IPS32-Records, statt dort jeweils `Runtime-Offset + 0x100` abzulegen.

Dadurch wurden sämtliche Records exakt `0x100` zu früh angewendet.

Im Ryujinx-Log sichtbare Beispiele:

```text
gewollt:     0x1E6FEC
tatsächlich: 0x1E6EEC

gewollt:     0x1E7520
tatsächlich: 0x1E7420

gewollt:     0x3527A0
tatsächlich: 0x3526A0
```

Damit wurde ausführbarer Stock-Code außerhalb der vorgesehenen Patchstellen überschrieben. Der Crash ist für diesen Export vollständig erklärt.

## Ungültiger Export

```text
Datei: DKCTF_HardMode_P2_Try9_DeathRespawn_Try10.ips
SHA-256: aa267f17b0dbfc480d6495a05dc891ff0aa57cab4810ed58b7f8982d0c8c6206
Status: NICHT MEHR VERWENDEN
```

## Korrigierter Export

```text
Dateiname:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips

Records: 8
Größe: 249 Bytes
SHA-256:
b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f
```

Nach Anwendung des Ryujinx-Bias landen die Records jetzt exakt bei:

```text
0x1E6FEC
0x1E7000
0x1E7004
0x1E7018
0x1E7520
0x3526EC
0x3527A0
0x352B18
```

## Unverändert

- alle sieben Try-9-Runtime-Patches bleiben byteidentisch;
- die Try-10-Helperbytes bleiben byteidentisch;
- nur die IPS32-Recordadresskodierung wurde korrigiert;
- das bestehende Try-9-Profil wurde nicht geändert;
- kein UI- oder PAK-Patch wurde geändert.

## Bestätigungsstatus

### Bestätigt

- Ursache des ersten Crashs: fehlerhafte IPS32-Adresskodierung;
- alle falschen Runtime-Adressen lagen exakt `0x100` zu früh;
- korrigierter Export dekodiert auf die acht vorgesehenen Runtime-Offets.

### Noch nicht im Spiel bestätigt

- Try-10-HP-Logik;
- P1-Tod bei lebendem P2;
- P2-Rejoin;
- globaler Tod, wenn beide Spieler tot sind;
- Solo-Hard-Mode;
- manueller Quit und Try-9-Restore.
