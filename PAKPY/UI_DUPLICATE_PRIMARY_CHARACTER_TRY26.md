# Duplicate DK Try 26

## Runtime baseline

Try 22/Try 25 remain the functional duplicate-actor baseline. Try 26 preserves the independent serialized DK replay and changes only the confirmed 1P, level-exit and spawn-integration faults.

## Correct singleplayer gate

Try 25 used the wrong Flash-data enum and parser.

Try 26 hooks `CProductionFrontEnd::InitGameTransition` at `0x352320` and reads:

- `mMenuStates@shell_playerCount` enum `0x49`;
- stock `NFlashData::get_player_index_from_flash_value()` at `0x1F53BC`.

Parsed values:

- `0` -> one human player and original 1P branch `0x352418`;
- `1` -> two human players and original P2 branch `0x352328`;
- invalid -> original `CGameState::IsMultiplayerActive()` fallback.

Duplicate DK is still armed only after stock has read an actual P2 selection at `0x35236C`. A 1P partner barrel therefore cannot activate the serialized P2 replay.

## Level-exit-only duplicate cleanup

Try 25's controller-leave and `CPlayer::Think` Delete hooks are removed.

Try 26 hooks `CGameUnloaderIOWin::OnMessage` at `0x55F154`:

- unload state `0`: clear the duplicate P2-present bit, physical P2 selection and Base18 handoff so the partner cannot carry into the next level;
- unload states `1..3`: preserve registry identity while stock actor teardown runs;
- unload state `4`: clear the replay registry in the final drain state.

The actor is not directly freed. Stock level unloading destroys it. Disconnecting P2 during a level retains the partner, matching stock behavior.

## Intro spawn correction

At `0x41CA5C`, `CPlayerActorGOC::OnAction_SyncPlayer` normally resolves a player through CharacterType.

Two logical DK actors both resolved P1, so P2's actor reset P1 to P2's spawn after the intro.

Try 26 dispatches duplicate actors through `CPlayerActorGOC+0x78`:

- player actor index `0` -> P1 registry pointer;
- player actor index `1` -> P2 registry pointer;
- non-duplicate or invalid index -> original CharacterType lookup.

## Retained functionality

- independent serialized DK replay;
- separate physical DK/Diddy slots;
- logical DK identity for both actors;
- pointer-aware player indexes;
- raw death bookkeeping;
- actual `CBarrelBalloonGOC::StartPlayerRejoin` target/survivor correction;
- checkpoint slot dispatch;
- no loader copy or finished-GOC mutation.

## Removed Try 25 hooks

- `0x32B50C` controller-leave cleanup;
- `0x1F88EC` queued actor deletion from `CPlayer::Think`.

## New hooks

- `0x55F154` level-unloader cleanup;
- `0x41CA5C` actor-index spawn synchronization.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 26 IPS SHA-256: `d269d1c5e4970cea7b0f32b0958e07be45915ccbd3f777c49f693831b0e433e3`
- ZIP SHA-256: `10e29716de89ddb555e83415e3fc7451c7ef49665bf5ba7755af7cde523b0736`
- Helper range: `0xA7A708..0xA7AC1C`
- Records: `25`
- Scope: DK+DK in normal and hard mode, valid 1P partner barrels, correct intro spawn, level-exit-only duplicate cleanup

## Runtime status

Not yet confirmed. Required checks:

1. normal 1P and partner barrel;
2. hard-mode 1P and partner barrel;
3. normal 2P DK+DK;
4. hard-mode 2P DK+DK;
5. intro completion without P1 moving to P2 spawn;
6. P2 disconnect during a level retains the partner;
7. level exit removes the duplicate partner before the next 1P level;
8. both revive directions.