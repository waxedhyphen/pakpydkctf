# Duplicate primary character – Try 11 slot registry

Arbeitsstand: 2026-07-25

## Status

```text
EXPERIMENTELL
NUR STRUKTURELL BESTÄTIGT
NOCH NICHT IM SPIEL BESTÄTIGT
```

Try 11 ist ein kombinierter ExeFS-Patch auf Basis des bestätigten Try-9+10-Stands. Alle acht vorhandenen Try-9+10-Records bleiben byteidentisch enthalten. Der Patch ersetzt keine UI- oder PAK-Datei.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

Try-9+10-Records: 8
Try-11-Records: 85
Gesamt: 93 IPS32-Records
IPS-Größe: 2719 Bytes
IPS SHA-256:
936da990d9465f60ff1116e9808a47783d53db297348861d39bc9894bd80860d
```

Der IPS32-Export verwendet den für Ryujinx bestätigten Record-Bias `Runtime-Offset + 0x100`.

## Unverändert übernommene Try-9+10-Belegung

```text
0x1E6FEC   Try 9
0x1E7000   Try 9
0x1E7004   Try 9
0x1E7018   Try 9
0x1E7520   Try 10
0x3526EC   Try 9
0x3527A0   Try 9 Parser + Try 10 Helper-Tail
0x352B18   Try 9
```

`0x1E700C` bleibt der originale P2-Store. `0x3527A0..0x352840` wurde nicht als neue Code-Cave verwendet.

## Neue Try-11-Architektur

Try 11 erhält die vorhandene CharacterType-Registry und ergänzt daneben eine unabhängige Registry:

```text
PlayerBySlot[0] = P1 CPlayer*
PlayerBySlot[1] = P2 CPlayer*
```

Damit bleibt:

```text
CharacterType = echter Kong für Modell, Animation und Fähigkeiten
PlayerSlot    = unabhängige P1/P2-Identität
```

### Helper

```text
Code:     0xA7A708..0xA7AC2C
Größe:    1316 Bytes
Registry: 0x19E7220..0x19E7240
```

Helper-Einstiege:

```text
0xA7A708 register actor
0xA7A7B4 clear actor
0xA7A844 get player index
0xA7A898 get player by slot
0xA7A908 first alive player
0xA7A944 first alive ID
0xA7A970 is primary player ID
0xA7A9FC player from index
0xA7AA74 should pickup item
0xA7AA88 alive player count
0xA7AB20 has any alive players
0xA7AB3C closest primary player
```

## Eingebaute Umbaugruppen

- Actor-Registrierung und -Entfernung im `CPlayer`-Lifecycle;
- slotbasierter `CPlayer::GetPlayerIndex` mit CharacterType-Fallback;
- slotbasierte Lebendspieler-Zählung;
- First-/Closest-Alive-Player;
- `PlayerFromIndex`;
- HP-, Schaden-, Schild- und Inventarslotpfade mit konkretem Actorpointer;
- P1/P2-Lookups in Multiplayerstatus, BarrelCannon, Heilung und NthAlive;
- Checkpoint-Spawn und FinishRespawn;
- RespawnBalloon Think, Grab und Toggle;
- Todesbenachrichtigungs-Lookups.

Typbasierte Gameplay-Lookups wurden nicht global ersetzt. Modelle, Animationen, Kongfähigkeiten, Effekte und bewusst CharacterType-basierte Systeme benutzen weiterhin den echten Kongtyp.

## Strukturelle Validierung

Bestätigt:

- alle Expected-Bytes stimmen gegen die bestätigte Try-9+10-Baseline;
- keine Try-11-Überlappung mit Try 9 oder Try 10;
- alle absoluten AArch64-`B`-/`BL`-Ziele wurden aus der gepatchten Ausgabe verifiziert;
- der Helper passt vollständig in die gewählte Region;
- keine direkten externen `B`-/`BL`-Referenzen in die ursprüngliche Helper-Region gefunden;
- Registry-Speicher ist in Stock `.data` null;
- IPS32-Parse-/Write-Roundtrip bestanden;
- simulierte Anwendung auf `.text` und `.data` stimmt mit allen 85 Try-11-Replacements überein.

## Offene Laufzeitgrenze

Try 11 trennt zwei bereits existierende unterschiedliche `CPlayer*`-Objekte nach P1/P2-Slot. Die statische Analyse beweist nicht, dass der Stock-Spawnpfad tatsächlich ein zweites Actor-Objekt desselben CharacterType erzeugt.

Falls `DK + DK` weiterhin nur einen Actor erzeugt, bleibt ein echter zweiter Actor/Clone als nächster Blocker. Dieser Build darf daher vor dem In-Game-Test nicht als funktionierender Duplicate-Kong-Fix bezeichnet werden.

Die Helper-Region gehört ursprünglich zu einem NEX-DataStore-Protokollhandler. Es existieren keine direkten Code-Xrefs in die Region; indirekte Vtable-/Funktionspointer-Nutzung ist statisch nicht vollständig ausgeschlossen.

## Ersttest

```text
1. normaler 2P-Modus: DK + DK
2. Hard-Mode-2P: DK + DK
3. unterschiedliche Kongs als Regression
4. P1-Tod und P2-Tod
5. Checkpoint und Rejoin
6. Levelstart und Levelwechsel
```
