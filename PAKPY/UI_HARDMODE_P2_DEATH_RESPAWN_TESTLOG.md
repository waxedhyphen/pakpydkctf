# Hard Mode P2 death/respawn – Testlog

Arbeitsstand: 2026-07-25

Ziel: Den mit Try 9 erzeugten echten Hard-Mode-P2 vollständig in die normale Zwei-Spieler-Todes- und Respawnlogik integrieren, ohne den bestätigten Try-9-Selector oder dessen Quit-Restore zu überschreiben.

## Arbeitsgrundlage

```text
UI: UIPak(21).pak, unverändert
ExeFS-Analyse: hochgeladene exefs(13).zip / main
main SHA-256:
018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

Die Stock-Bytes aller sieben Try-9-Records und des neuen Try-10-Hooks wurden vor dem Patchbau exakt gegen diese `main` validiert.

## Unverändert übernommene Try-9-Regeln

- alle sieben Try-9-Records bleiben aktiv;
- kein Try-7- oder Try-8-Restore-Hook wird wieder eingeführt;
- `0x1E700C` bleibt der originale P2-Store im Hard-Mode-Initializer;
- kein AVM2-Patch;
- kein UI-PAK-Patch;
- der aktive Try-9-Parser von `0x3527A0` bis einschließlich `0x352800` bleibt byteidentisch;
- Try 9 bleibt der im Spiel bestätigte Stand für Spawn, Steuerung und manuellen Quit-Restore.

## Normale Nicht-Hardmode-2P-Initialisierung

`NGameModeSetup::setup_playerstate_for_level` verwendet im normalen Zweispielerpfad die Aktivmaske bei `GameState+0x26A0`.

```text
P1 aktiv: Bit 0
P2 aktiv: Bit 1
```

P1 erhält Gesundheitsinventar Item 2, P2 erhält Item 3. Für beide wird die Kapazität auf die normale Start-HP gesetzt. Der Count wird nur dann positiv gesetzt, wenn das jeweilige Aktivbit vorhanden ist.

Relevanter normaler P2-Block:

```text
0x1E7638  LDRB Aktivmaske
0x1E764C  TST Bit 1
0x1E7650  Item 3
0x1E7660  SetInventoryCapacity(Item 3, Start-HP)
0x1E7674  SetInventoryCount(Item 3, Start-HP oder 0)
```

## Normaler Schadens- und Todespfad

`CPlayerModuleHealth::ApplyPrimaryPlayerDamage` ermittelt den PlayerIndex:

```text
0x24265C  GetPlayerIndex
0x24266C  CMP PlayerIndex,0
0x242670  Basis-Item 2
0x24267C  CINC -> P1 Item 2, P2 Item 3
0x242770 / 0x2427A0  ApplySoloPlayerDamage
```

`CPlayerModuleHealth::ApplySoloPlayerDamage` zieht Schaden vom gewählten Item ab:

```text
0x2434B8 / 0x2434CC  RemoveFromInventory
0x2434E8              GetInventoryCount
0x2434EC              CBZ -> Todesblock 0x243598
0x2435F0              CPlayerModuleHealth::Death
```

## Exakter globale-Tod-Branch

`CPlayerRespawnGOC::OnAction_NotifyOfPlayerDeath` prüft nach einer Todesmeldung beide Gesundheitsitems:

```text
0x423710  Item 2 auswählen
0x423718  HasInventoryItem(Item 2)
0x42371C  TBNZ -> Return, solange P1 lebt

0x423720  Item 3 auswählen
0x423728  HasInventoryItem(Item 3)
0x42372C  TBZ W0,#0,0x423740
```

`0x42372C` ist der entscheidende Branch:

- Item 3 positiv: Fallthrough zu `0x423730`, Routine kehrt zurück;
- Item 3 null: Sprung nach `0x423740`, globaler Todes-/Respawnpfad;
- `0x42378C` tail-brancht anschließend nach `CPlayerState::NotifyAllPlayersRespawningFromDeath`.

Damit ist strukturell exakt bestätigt, warum P1-Tod im bisherigen Hard-Mode-2P beide Spieler beendet.

## Normaler individueller 2P-Respawn

Solange kein globaler Respawn aktiv ist, verarbeitet `CPlayerModuleRiseFromTheGrave::PostOwnerOrInactiveThink` den einzelnen toten Spieler:

```text
0x5751B4  IsMultiplayerActive
0x57520C  GetHealthModule
0x575218  IsDeadAndOffscreen
0x5752A8  BarrelBalloon IsAvailable
0x5752D8  HasInventoryItem(Item 8 / Rejoin-Balloon)
0x5752E8  GetFirstAlivePrimaryPlayer
0x57531C  CBarrelBalloonGOC::StartPlayerRejoin
```

Dieser normale individuelle Rejoinpfad wird durch Try 10 nicht gepatcht.

## Stock-HP-Restore beim Rejoin

Beim erneuten Aktivieren eines Spielers ruft `CPlayer::OnActivationStateChanged` den vorhandenen HP-Restore auf:

```text
0x1F8838  CPlayer::AddPlayerHitPoints
```

Für PlayerIndex 1 verwendet `CPlayer::AddPlayerHitPoints` Item 3:

```text
0x1FA424  Item 3 auswählen
0x1FA42C  GetInventoryCount(Item 3)
0x1FA450  Item 3 auswählen
0x1FA458  GetInventoryCapacity(Item 3)
0x1FA47C  SetInventoryCount(Item 3, capacity)
```

Damit ist strukturell bestätigt, dass der vorhandene Rejoin P2 aus Item 3s Kapazität wiederbelebt. Try 10s Kapazität `1` wird vom Stock-Pfad zu genau einem Lebenspunkt zurückgeschrieben; hierfür ist kein weiterer Respawn-Hook erforderlich.

## Hard-Mode-Abweichung

Der `BONS`/Hard-Block bei `0x1E7510` initialisiert stock:

```text
Item 2 capacity/count = 1
Item 3 capacity       = 0
Item 3 count          = nicht positiv gesetzt
```

Try 9 erhält zwar das P2-Aktivbit, ändert aber diese HP-Initialisierung nicht. Deshalb bleibt Item 3 strukturell null. Sobald P1s Item 2 null wird, muss `0x42372C` in den globalen Pfad springen, auch wenn Try 9 einen echten steuerbaren P2 erzeugt hat.

Die In-Game-Beobachtung zeigte zusätzlich einen zweiten Effekt derselben Fehlinitialisierung: P2 starb beim Start des Hard-Mode-Levels automatisch. Auch hierfür fehlte P2 vor Try 10 ein positives Item-3-Gesundheitsinventar.

## Try 10 – P2-HP nur bei aktivem P2 initialisieren

Try 10 patcht keine Todes- oder Respawnroutine. Stattdessen stellt es die normale Multiplayer-Invariante bereits im Hard-Mode-Initializer her.

### Hook

```text
0x1E7520
E1 07 00 32
->
B9 AC 05 14    ; B 0x352804
```

### Helper-Platz

Try 9 endet im aktiven Parser bei:

```text
0x352800  B 0x352844
```

Dadurch waren die 16 folgenden Try-9-NOPs bei `0x352804..0x352840` bereits unerreichbar. Nur diese NOPs werden als Try-10-Helper verwendet. Der aktive Try-9-Code bleibt unverändert.

### Helper-Logik

```text
LDR  W22,[X20,#0x26A0]
TBZ  W22,#1,solo

P2 aktiv:
    SetInventoryCapacity(Item 3,1)
    SetInventoryCount(Item 3,1)
    B 0x1E7530

solo:
    SetInventoryCapacity(Item 3,0)
    B 0x1E7530
```

Damit bleibt stock Solo-Hard-Mode strukturell unverändert. Nur bei dem von Try 9 erhaltenen P2-Aktivbit erhält P2 sein eigenes 1-HP-Inventar.

## Kombiniertes Profil

```text
PAKPY/exefs_profiles/dkctf_hardmode_real_p2_death_respawn.json
```

Records:

```text
0x1E6FEC   4 Bytes   Try 9
0x1E7000   4 Bytes   Try 9
0x1E7004   4 Bytes   Try 9
0x1E7018   4 Bytes   Try 9
0x1E7520   4 Bytes   Try 10 Hook
0x3526EC   4 Bytes   Try 9
0x3527A0 164 Bytes   Try 9 Parser + Try 10 in ehemaligem NOP-Tail
0x352B18   4 Bytes   Try 9
```

## IPS32-Export

Der erste manuell erzeugte Try-10-IPS war ungültig: Die IPS32-Records enthielten nicht den für Ryujinx erforderlichen `+0x100`-Adressbias. Ryujinx wendete dadurch jeden Record exakt `0x100` zu niedrig an, beispielsweise `0x1E6EEC` statt `0x1E6FEC`. Dieser Export beschädigte ausführbaren Stock-Code und verursachte einen Game-Crash. Er ist verworfen und darf nicht verwendet werden.

Korrigierter kombinierter IPS32:

```text
Dateiname:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000.ips

Records: 8
Größe: 249 Bytes
Header: IPS32
Footer: EEOF
SHA-256:
b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f
```

Die im Ryujinx-Log bestätigten angewendeten Adressen entsprechen nach dem korrigierten Bias exakt den acht oben dokumentierten Memory-Offets.

## Status

### Strukturell bestätigt

- normale 2P-HP-Initialisierung disassembliert;
- normaler Schadens-/Todespfad disassembliert;
- normaler individueller Barrel-Rejoin disassembliert;
- Stock-HP-Restore beim Reaktivieren von P2 disassembliert;
- exakter globale-Tod-Branch `0x42372C` bestätigt;
- Hard-Mode-Abweichung Item 3 = 0 bestätigt;
- Try-9-Kompatibilität bytegenau geprüft;
- Solo-Hard-Mode-Pfad im Helper erhalten;
- korrigierte IPS32-Records und Branchziele validiert.

### Im Spiel bestätigt

```text
BESTÄTIGT: FUNKTIONIERT
```

Mit dem korrigierten kombinierten Try-9+10-IPS wurde bestätigt:

- der bisherige globale Tod bei P1-Tod im Hard-Mode-2P ist behoben;
- der getestete Zwei-Spieler-Todes-/Fortsetzungspfad funktioniert;
- P2 stirbt beim Start des Hard-Mode-Levels nicht mehr automatisch;
- Try 10 behebt damit neben dem ursprünglichen P1-Tod-Problem auch diesen vorher vorhandenen P2-Starttod-Bug.

Die zusätzliche Behebung des P2-Starttods bestätigt die strukturelle Analyse: P2 benötigte bereits beim Levelstart ein positives Item-3-Inventar und nicht erst während des späteren Respawnpfads.

### Weiterhin getrennt zu prüfen

- P2-Tod und P2-Rejoin über sämtliche Levelzustände;
- wenn beide Spieler gleichzeitig oder nacheinander tot sind, endet der Run weiterhin korrekt;
- Solo Hard Mode endet weiterhin bei P1-Tod;
- manueller Quit und Restore des normalen P2 bleiben mit dem kombinierten Try-9+10-IPS regressionsfrei.
