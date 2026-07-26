# Duplicate DK Try 28 – native level P2 decision

## Runtime baseline

Try 22 remains the last partially confirmed integration baseline:

- the serialized replay can create an independent second DK actor;
- the raw-slot revive correction uses `CBarrelBalloonGOC::StartPlayerRejoin`;
- normal two-player behavior improved;
- duplicate DK was still limited to Hard Mode and single-player remained broken.

Try 23 through Try 27 are discarded. Their menu-value and early frontend gates either disabled valid modes or armed state at a point that did not survive the complete transition lifecycle.

## Why Try 27 could not activate replay

Try 27 armed duplicate state in `CProductionFrontEnd::InitGameTransition` near `0x352358/0x35236C`. That is not the final native level-player setup. The later callback parser and native `InitLevelTransition` path still run before player components are loaded, so the early state did not reliably reach the replay factory.

Try 28 does not patch the guessed menu-player-count values and does not arm from the callback parser.

## Exact native P2 path

The relevant function is:

```text
CProductionFrontEnd::InitLevelTransition(
    CObjectId const&,
    EGameModeTypes,
    EPrimaryPlayer)
```

The stock path is:

```text
0x352C4C  read transition state
0x352C50  compare with 2
0x352C5C  CGameState::IsMultiplayerActive()
0x352C60  branch past P2 setup when false
0x352C74  read RuntimeData_Char_P2
0x352CA0  store P2 CharacterType at CGameState+0x269C
0x352CA4  continue level initialization
```

Try 28 hooks only:

- `0x352C5C`: calls the original `IsMultiplayerActive()` and records that exact current-level result;
- `0x352CA4`: after stock has completed the P2 store, arms duplicate replay only when:
  - the recorded result is multiplayer;
  - `CGameState+0x2698 == 1` (P1 DK);
  - `CGameState+0x269C == 1` (P2 DK).

Only then is the physical P2 carrier changed to Diddy (`2`) in `+0x269C` and Base18 handoff `+0x26C0`. The visible actor, DK resources, animation set, FSM and logical type continue to come from the serialized DK replay.

The complete Base18 parser record at `0x3527A0` is byte-identical to the known-good base and cannot arm the duplicate registry. A partner barrel collected during gameplay does not execute this frontend level-transition path.

## Intro spawn correction

`CPlayerActorGOC::OnAction_SyncPlayer` loops over nine actor slots. Its stock table at `0x1523EA0` is:

```text
[DK, Diddy, Dixie, Cranky, Funky, DK, Diddy, Dixie, Cranky]
```

Slots `5..8` are the P2 half. Stock slot `5` resolves DK through the ordinary primary-player table and therefore returns P1.

The hook at `0x41CA5C` returns the exact replay-created P2 pointer for active duplicate mode and actor slots `5..8`. Other slots and non-duplicate modes tail-call the original lookup unchanged.

## Level-exit cleanup

Cleanup is attached only to the real level unloader:

```text
CGameUnloaderIOWin::OnMessage + 0x2C
0x55F154
```

On the first unload state, active duplicate mode clears:

- the duplicate P2-present bit in `CGameState+0x26A0`;
- `CGameState+0x269C`;
- Base18 handoff `CGameState+0x26C0`;
- the replay registry.

The patch does not delete anything when P2 disconnects. Stock level unloading remains responsible for destroying the actor.

## Retained Try 22 integration

- fresh `CMemoryInStream` serialized DK replay in `NScriptLoader::LoadComponent`;
- separate physical DK/Diddy primary-player slots;
- pointer-aware `CPlayer::GetPlayerIndex()`;
- raw death bookkeeping;
- raw target and survivor types in the actual revive-barrel path;
- slot-specific checkpoint player lookup;
- no loader copy and no mutation of an already completed GOC.

## Excluded failed hooks

Try 28 contains no hooks at the guessed menu/player-count or disconnect locations used by Try 23–27, including:

```text
0x352288  0x352320  0x352324  0x352334  0x35236C  0x32B50C
```

It also contains none of the discarded `CRespawnBalloonGOC` hooks from Try 21.

## Build and validation

- Build ID: `F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000`
- Base18 SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 28 IPS SHA-256: `14c455d1cc0e5329d26a13cf4a287914fcd5fac81f1569ad8b03b11d4399282b`
- Records: `25`
- Helper: `0xA7A708..0xA7AB5C` (`1108` bytes)

Two independent static checks passed:

- IPS32 parse/write and simulated application;
- all eight Base18 records byte-identical;
- exact stock-byte guards at every new hook;
- all AArch64 branch destinations decoded to their declared helper symbols;
- sorted, non-overlapping records;
- helper fits inside the validated code cave.

## Runtime status

Not yet confirmed in game. Required tests:

1. cold normal 1P;
2. cold Hard Mode 1P;
3. collect a normal Kong partner in 1P;
4. normal DK + DK 2P;
5. Hard Mode DK + DK 2P;
6. intro spawn positions;
7. P2 revives P1;
8. P1 revives P2;
9. finish or exit the level, then enter 1P and verify no duplicate DK carries over.
