# Try 11 Fix 9 – persistent duplicate alias across IACT

Arbeitsstand: 2026-07-26

## Ausgangslage

Bestätigter Laufzeitstand von Fix 5/6:

- beim Levelstart sind während der Cutscene zwei Donkey Kongs vorhanden;
- nach der Cutscene wird der zweite Actor wieder zu Diddy;
- dieser Actor ist nicht durch Spieler 2 steuerbar;
- nach seinem Tod existiert kein funktionierender Respawn.

Fix 7 und Fix 8 werden verworfen. Der frühe vollständige `SLdrPlayer`-Klon führt nach dem Laden in einen ungültigen Animationszustand. Fix 8 beseitigte zwar den vorherigen Argumentregisterfehler in `CPlayerGOC::EntityLoaded`, stürzte danach aber in `CAnimSet::GetAnimationFromId` aus `CPlayerGOC::InitializeStateMachines` ab.

## Gefundene Ursache im Fix-5/6-Helper

Der Hook bei `0x1F8BC0` läuft beim `IACT`-Pfad von `CPlayer::AcceptScriptMsg`.

`try11_clear_entity_fix2` behandelte diese Deaktivierung fälschlich wie die endgültige Entfernung des Alias-Carriers. Für den zweiten DK-Carrier führte der Helper dabei ausdrücklich folgende Schritte aus:

1. ursprünglichen Carrier-Typ aus der Registry lesen;
2. `CPlayer+0x14` auf diesen Typ zurücksetzen;
3. `CPlayerGOC+0x8C` auf diesen Typ zurücksetzen;
4. den logischen P1/P2-Registrypointer entfernen;
5. Alias-Metadaten löschen.

Bei einem Diddy-Carrier für `DK + DK` erzeugt das exakt den beobachteten Übergang:

```text
zweiter DK während Cutscene
-> IACT
-> CharacterType wird auf Diddy zurückgesetzt
-> P2-Slot und Alias werden gelöscht
-> keine Controller- und Respawn-Zuordnung mehr
```

## Fix 9

Fix 9 basiert auf dem letzten nicht-crashenden Fix-6-Stand. Der vollständige Loader-Klon und der Hook bei `0x2A5358` aus Fix 7/8 sind nicht enthalten.

Geändert wird nur das Verhalten von `try11_clear_entity_fix2`:

- `IACT` gilt als vorübergehende Deaktivierung eines persistenten Player-Actors;
- der Alias-Carrier behält seinen ausgewählten CharacterType;
- `CPlayer+0x14` und `CPlayerGOC+0x8C` werden nicht auf Diddy zurückgesetzt;
- der logische P1/P2-Registrypointer bleibt erhalten;
- die Alias-Metadaten bleiben erhalten;
- nur der Stock-Primary-Pointer des ursprünglichen Carrier-Typs wird bereinigt;
- für normale Actors wird bei Bedarf der andere logische Actor erneut in der Stock-Type-Tabelle registriert.

## Binärer Stand

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
dc82b70c3850b2fca8eb8c900fa745f3aae325581cfc811d5cf41f8dedc889bc
```

Validierung:

- 98 IPS-Records insgesamt;
- alle acht bestätigten Try-9+10-Records byteidentisch;
- Recordkeys identisch zu Fix 6;
- einzige geänderte Payload ist der Helperblock bei `0xA7A708`;
- Helpergröße bleibt 2584 Bytes;
- `try11_clear_entity_fix2` bleibt bei `0xA7AC3C`;
- alle nachfolgenden Helper-Adressen bleiben unverändert;
- kein Record bei `0x2A5358`;
- Ryujinx-IPS32-Offsetbias `+0x100` beibehalten;
- erwartete Originalbytes, Overlap-Prüfung, Branchziele und simuliertes Anwenden bestanden.

## Status

Fix 9 ist strukturell validiert, aber noch nicht im Spiel bestätigt.

Priorisierte Laufzeittests:

1. `DK + DK`: bleibt P2 nach Ende der Cutscene DK?
2. reagiert P2 auf Controller 2?
3. kann P2 nach Tod respawnen/rejoinen?
4. bleibt Try 9 erhalten: P1-Tod bei lebendem P2 beendet den Lauf nicht global?
5. funktionieren verschiedene Kong-Kombinationen weiterhin unverändert?
