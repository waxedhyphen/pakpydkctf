# Duplicate primary character – Try 11 Fix 2

Arbeitsstand: 2026-07-26

## Status

```text
TRY 11 FIX 1: LEVEL-EINSTIEG FUNKTIONIERT
TRY 11 FIX 1: DUPLIKAT-P2 NICHT SICHTBAR / NICHT VORHANDEN
TRY 11 FIX 1: P1-TOD FÜHRT ZU KAMERA-FREEZE OHNE REJOIN
TRY 11 FIX 2: STRUKTURELL BESTÄTIGT, IN-GAME-TEST OFFEN
```

## In-Game-Befund aus Fix 1

Fix 1 beseitigt den doppelten `SetPrimaryPlayer`-Aufruf und ermöglicht den Level-Einstieg. Der anschließende Laufzeittest zeigt jedoch:

```text
- das Spawnverhalten wirkt, als würde ein zweiter Slot erwartet;
- es erscheint kein zweiter sichtbarer Spieler;
- beim Tod von P1 bleibt die Kamera stehen;
- kein Rejoin ist möglich;
- P2 bleibt unsichtbar/abwesend.
```

Damit ist die zuvor dokumentierte Laufzeitgrenze bestätigt: Die Slotregistry kann nur vorhandene `CPlayer*` trennen. Der Stock-Pfad erzeugt für eine doppelte CharacterType-Auswahl keinen zweiten Actor desselben Typs.

## Bestätigter Stock-Spawnpfad

`NPlayerUtils::SpawnOtherPlayer` arbeitet mit vorhandenen PrimaryPlayer-Actors:

```text
0x27C94C  GetPrimaryPlayerByCharacterType(source type)
0x27C960  CanSpawnPlayer(target type)
0x27C974  PrimaryPlayerByCharacterType(target type)
```

Bei identischer Auswahl liefert der Target-Lookup denselben Actor wie der Source-Lookup. Zusätzlich kann `CanSpawnPlayer` den bereits aktiven Zieltyp ablehnen. Es wird an dieser Stelle kein neuer `CPlayerGOC`-Graph geklont.

## Fix-2-Architektur

Fix 2 verwendet bei einer CharacterType-Kollision einen bereits vorhandenen, aktuell inaktiven PrimaryPlayer-Actor als getrennten physischen Actor.

```text
P1/P2 logical slot = eigene Try-11-Registry
sichtbarer/spawnbarer Actor = vorhandener inaktiver PrimaryPlayer-Actor
CPlayer CharacterType = ausgewählter Duplikat-Kong
Stock CharacterType registry slot = ursprünglicher Carrier-Typ
```

Damit existieren zwei unterschiedliche Actorpointer, ohne während des Levelstarts einen kompletten `CPlayerGOC`-Komponentenbaum neu zu allozieren.

## Neue Fix-2-Hooks

### Duplicate-CanSpawn

```text
0x27C960 -> try11_can_spawn_duplicate (0xA7AD14)
```

- normale Stock-`CanSpawnPlayer`-Erfolge bleiben unverändert;
- nur wenn Stock ablehnt, P1/P2 denselben Typ gewählt haben und P2 aktiv ist, wird nach einem inaktiven Carrier gesucht;
- ohne freien Carrier bleibt das Stock-Nein bestehen.

### Spawnziel

```text
0x27C968..0x27C978 -> try11_select_spawn_actor (0xA7ADD0)
```

- normales unterschiedliches Ziel: Stock-Actor bleibt erhalten;
- identisches Ziel zeigt auf Source: erster inaktiver anderer PrimaryPlayer-Actor wird gewählt;
- der Actor wird in den logischen Slot gegenüber dem Source-Actor eingetragen;
- sein ursprünglicher Typ wird für Restore gespeichert;
- `CPlayer+0x14` erhält den ausgewählten Duplikat-CharacterType.

### Alias-Clear

```text
0x1F8BC0 -> try11_clear_entity_fix2 (0xA7AC3C)
```

- Carrier wird vor dem Stock-Clear auf seinen ursprünglichen Typ zurückgestellt;
- Stock-Registry wird über den ursprünglichen Carrier-Typ bereinigt;
- nur der exakt passende logische Slot wird entfernt;
- ein überlebender Spieler desselben gewünschten Typs wird bei Bedarf wieder in der Stock-Typregistry eingetragen.

### Fehlender-P2-Todesguard

```text
0x42372C -> try11_death_item3_guard (0xA7AEEC)
```

Item 3 verhindert globalen Tod nur noch dann, wenn Slot 1 tatsächlich einen aktiven und lebenden Actor enthält. Dadurch darf ein positives P2-HP-Inventar bei fehlendem P2-Actor nicht mehr zu einem Kamera-Freeze ohne kontrollierbaren Spieler führen.

## Registry

```text
0x19E7220 owner GameData*
0x19E7228 PlayerBySlot[0]
0x19E7230 PlayerBySlot[1]
0x19E7238 AliasCarrier CPlayer*
0x19E7240 AliasCarrierOriginalType
0x19E7244 AliasDesiredType
```

Reservierte/validierte Nullregion: 48 Bytes.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

Try-9+10-Records: 8
Try-11/Fix-2-Records: 88
Gesamt: 96 IPS32-Records
Helper: 0xA7A708..0xA7AF20, 2072 Bytes
IPS-Größe: 3537 Bytes
IPS SHA-256:
c9f89ee032b977b584b69938b5634cd245fac295668505980672e1c6ff7e0f67
```

Try 9 und Try 10 bleiben byteidentisch enthalten. Der IPS32-Export verwendet weiterhin `Runtime-Offset + 0x100`.

## Offene Laufzeitfrage

Fix 2 erzeugt einen getrennten echten Actor, ändert aber nicht den ursprünglich für den Carrier geladenen vollständigen `CPlayerGOC`-/Modulgraphen. Der In-Game-Test muss deshalb zeigen:

```text
- erscheint der zweite Actor;
- welches Modell/Animationsset wird verwendet;
- greifen Fähigkeiten über den geänderten CPlayer-CharacterType;
- funktionieren Controller, Tod, Rejoin und Checkpoint;
- funktioniert der Wechsel zurück auf unterschiedliche Kongs.
```

Bis diese Punkte bestätigt sind, ist Fix 2 experimentell.