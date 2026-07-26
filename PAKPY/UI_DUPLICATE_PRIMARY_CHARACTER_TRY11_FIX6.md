# Duplicate primary character – Try 11 Fix 6

Arbeitsstand: 2026-07-26

## Laufzeitbefund aus Fix 5

Fix 5 erzeugt erstmals sichtbaren Fortschritt:

```text
während der Start-Cutscene: zwei Donkey Kongs sichtbar
nach Ende der Cutscene: P2-Carrier wird wieder Diddy
P2-Carrier: nicht steuerbar
P2-Carrier: kein normaler Respawn
```

Damit ist bestätigt, dass Fix 5 einen zweiten vorhandenen Actor auswählt und sichtbar macht. Nicht korrekt war jedoch die vollständige Aktivierung dieses Actors.

## Exakter Fix-5-Fehler

`CPlayer+0xF8` ist der `CPlayerGOC*`. Dieses Feld ist korrekt, wenn der kopierte `SLdrPlayerCommonData::CharacterType` bei `CPlayerGOC+0x8C` geändert wird.

Stock `CPlayerProxyGOC::ActivatePlayerImpl` und `DeactivatePlayerImpl` schicken `ACTV` bzw. `IACT` jedoch nicht an den `CPlayerGOC`, sondern an den Komponenten-/Entity-Identifier aus `CPlayer+0x100`, also den vollständigen `CEntityGOC*`.

Fix 5 tat nur Folgendes:

```text
ACTV an CPlayerGOC
CPlayer::SetActive(true)
```

Damit blieben andere Komponenten des Player-Entity – insbesondere controller- und respawnrelevante Komponenten – im ursprünglichen oder inaktiven Zustand. Ein späterer Stock-Aktivierungsschritt nach der Cutscene stellte deshalb die ursprüngliche Diddy-Darstellung wieder her.

## Fix 6

Fix 6 behält den funktionierenden AreaLoaded-Zeitpunkt aus Fix 5 bei und ändert ausschließlich die beiden Action-Zielpointer:

```text
CharacterType-Daten:
CPlayer+0xF8 -> CPlayerGOC+0x8C

ACTV/IACT-Ziel:
CPlayer+0x100 -> vollständiger CEntityGOC
```

Binärer Unterschied gegenüber Fix 5:

```text
Helpergröße unverändert: 2584 Bytes
Recordanzahl unverändert: 98 insgesamt / 90 Try-11
geänderte Helperbytes: 2
```

Die zwei geänderten Instruktionen sind:

```text
AreaLoaded ACTV:
ldr x2,[x26,#0xF8] -> ldr x2,[x26,#0x100]

Proxy-Deaktivierung IACT:
ldr x2,[x23,#0xF8] -> ldr x2,[x23,#0x100]
```

Alle CharacterType-Schreibzugriffe bleiben auf `CPlayerGOC+0x8C`. Alle bestätigten Try-9+10-Records bleiben byteidentisch.

## Build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000

IPS SHA-256:
c9ce12601d4d0d31539fc3a3ece578a23990c92bf95e7b52eae976baaab755be
```

## Status

```text
STRUKTURELL BESTÄTIGT
NOCH NICHT IM SPIEL BESTÄTIGT
```

Zu testen sind insbesondere:

```text
P2 bleibt nach der Cutscene DK
Controller 2 steuert P2
P2-Tod erlaubt Rejoin
P1-Tod bei lebendem P2
Checkpoint/Respawn
```