# Try 12 – Base18 physical P2 carrier

Arbeitsstand: 2026-07-26

## Verbindliche Basis

Try 12 wird ausschließlich aus der vom Nutzer erneut bereitgestellten, funktionierenden Basis gebaut:

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

Base18 IPS SHA-256:
b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f

Base18 Records:
8
```

Sieben der acht Records bleiben byteidentisch. Nur der bereits vorhandene Record bei Runtime `0x1E7000` wird ersetzt, weil dort P2s interner Actor gewählt werden muss.

## Warum Fix 5 bis Fix 10 verworfen sind

Die vorherige Architektur registrierte logische P1/P2-Pointer global und aktivierte einen zusätzlichen Actor über Proxy-/Spawn-Hooks. Dadurch griff sie auch in 1P-Ladevorgänge ein. Beobachtete Folgen waren unter anderem ein zweiter Actor im 1P-Ladebildschirm, 2P-Spawnpositionen im 1P-Modus, Cutscene-Resets, fehlende Controller-/Respawn-Zuordnung und Loader-/AnimSet-Crashes.

Try 12 enthält deshalb ausdrücklich keine Records bei:

```text
0x1F8420   globaler logischer Registry-Hook
0x27C960   SpawnOtherPlayer CanSpawn-Hook
0x27C968   SpawnOtherPlayer Carrier-Auswahl
0x4221E0   Proxy-Aktivierung
0x422C38   Proxy-Deaktivierung
0x2A5358   Loader-Klon
```

## Neue Architektur

Das Spiel erhält intern weiterhin zwei verschiedene physische Player-Actors, sodass die Stock-Pointertabelle, Controllerzuordnung, HP-Slots und Respawn-Lookups nicht kollidieren.

```text
P1 intern: gewünschter Kong
P2 intern: freier physischer Carrier
P2 sichtbar/logisch: gewünschter Kong
```

Für ein Duplikat verwendet P2 intern:

```text
Standard: Diddy (CharacterType 2)
Diddy + Diddy: Dixie (CharacterType 6)
```

## Single-player

Der Helper bei `0x1E7000` beginnt mit exakt der Operation aus Base18:

```asm
ldr w8, [x19, #0x26c0]
```

Ist der bereits vorhandene P2-Aktivitätsbit nicht gesetzt, wird dieser Wert unverändert zurückgegeben. Es wird kein Carrier markiert, kein Player-Alias geschrieben und kein Proxycode verändert. Alle pointerbasierten Index-Hooks verwenden dann den exakten Stock-Fallback.

## Duplicate-2P

Nur wenn P2 tatsächlich aktiv ist und P1/P2 denselben gewünschten CharacterType besitzen:

1. `state+0x269C` erhält einen anderen physischen Carrier-Typ.
2. Der Carrier durchläuft Stock-EntityLoaded, SetInitialState, Controller-, Modul-, FSM- und AnimSet-Initialisierung mit seinem eigenen gültigen Datensatz.
3. Erst nach `CPlayerGOC::InitializeStateMachines` werden `CPlayerGOC+0x8C` und `CPlayer+0x14` auf den gewünschten Duplikat-Kong gesetzt.
4. `CPlayer::GetPlayerIndex` erkennt den exakten Carrierpointer als P2.
5. Konkrete HP-, Inventar-, Shield-, HUD- und Barrel-Cannon-Pfade, die den Slot zuvor direkt aus CharacterType abgeleitet haben, verwenden denselben pointerbasierten Index.
6. Beim Entfernen des Carrier-Actors wird dessen physischer PrimaryPlayer-Slot bereinigt, nicht P1s logischer Kong-Slot.

## Hooks

```text
0x1E7000 -> 0xA7A708  choose physical carrier
0x2A6B1C -> 0xA7A760  alias after stock FSM initialization
0x1FA6AC -> 0xA7A7E4  pointer-aware GetPlayerIndex
0x1F8BC0 -> 0xA7A840  clear physical carrier slot
0x1FB518 -> 0xA7A864  pointer-aware ShouldPickupItem
```

Helperbereich:

```text
0xA7A708..0xA7A878
368 Bytes
```

## Output

```text
Try12 IPS SHA-256:
8740694b07b0e69e9130a77e72b0ed95e6a3bdb7f8509070f2a7f1c5a7dac0e8

Records gesamt:
24
```

## Validierung

Strukturell bestanden:

- Base18 aus Stock-Text rekonstruiert;
- sieben unangetastete Basisrecords byteidentisch;
- einziger ersetzter Basisrecord `0x1E7000`;
- erwartete Bytes gegen Base18 geprüft;
- IPS32 `+0x100`-Bias geprüft;
- Parse-/Write-Roundtrip geprüft;
- simuliertes Anwenden geprüft;
- alle Branchziele dekodiert und geprüft;
- Helper innerhalb des etablierten Cave-Bounds;
- Registry-Backing im Stock-Datensegment nullinitialisiert;
- reproduzierbarer IPS-Build mit identischem SHA-256.

## Laufzeitstatus

Noch nicht im Spiel bestätigt. Erforderliche Tests:

1. 1P: nur ein Player im Ladebildschirm und korrekte 1P-Spawnposition.
2. 2P DK+DK: zwei Player bleiben nach der Sequenz sichtbar.
3. Controller 2 steuert den zweiten Actor.
4. P2-Tod und Respawn/Rejoin.
5. P1-Tod bei lebendem P2 behält das bestätigte Try-9+10-Verhalten.
