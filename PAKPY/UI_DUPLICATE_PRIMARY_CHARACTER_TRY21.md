# Duplicate DK Try 21

## Confirmed runtime baseline

Try 19 remains the best confirmed runtime approach.

Confirmed in game:

- normal level entry no longer crashes;
- 2P can create two real Donkey Kong actors;
- both actors have DK model, animations, FSM and gameplay modules;
- Player 2 can interact with ordinary barrels and world objects.

Confirmed Try 19 bugs:

- 1P still starts through a two-player-like setup even though only one visible player appears;
- obtaining a Kong partner in 1P kills the player;
- Player 2 cannot use Player 1's revive balloon;
- when Player 1 uses Player 2's revive balloon, the balloon is consumed but Player 2 does not return;
- Player 1 cannot be revived normally in duplicate-DK 2P.

Try 20 did not fix these bugs and additionally made duplicate-character loading work only in Hardmode. Try 20 is discarded.

## 1P/2P gate diagnosis

The previous gates did not represent the number of human players:

- `CGameState+0x26A0 bit 1` also represents a 1P Kong partner;
- `CGameState::IsMultiplayerActive()` is mode/timing-dependent at the transition hook and caused the Hardmode-only Try 20 regression.

The stock Flash data model has a dedicated value for the human player count:

- name: `mRuntimeData@PlayerCount`;
- enum: `NFlashData::RuntimeData_PlayerCount = 0x75`;
- representation: integer `CFlashValue`, type tag `3`, value `1` or `2`.

Try 21 reads this value directly from `CProductionFrontEnd+0x38` through `CFlashDataModel::GetDataValue` at `0x64DA34`. Duplicate replay is armed only when the value is exactly `2`.

This is intended to keep the serialized replay disabled in genuine 1P and prevent a later Kong-partner load from being mistaken for the second human player.

## Revive-balloon diagnosis

The previous fixes patched `CCheckpointGOC`, but the reported revive barrel is controlled by `CRespawnBalloonGOC`.

The balloon performs seven separate calls to `CStateManagerGameData::PrimaryPlayerByCharacterType`:

- `0x440DF0` — P1 think lookup;
- `0x440E30` — P2 think lookup;
- `0x4410C0` — P1 grab/start lookup;
- `0x441130` — P2 grab/start lookup;
- `0x441688` — P1 control lookup;
- `0x4416C0` — P2 control lookup;
- `0x44174C` — second P2 control lookup.

Stock code supplies `GameState+0x2698` and `GameState+0x269C`. In duplicate mode those logical selections can both be DK, while the live primary registry intentionally stores:

- P1 under raw DK type `1`;
- P2 under raw Diddy type `2`.

Try 21 dispatches the seven balloon call sites to those exact raw registry keys while duplicate mode is active. The original `x0` GameData pointer and `w2` active/alive flags are preserved. Non-duplicate modes tail-call the stock lookup with the original character type.

## Retained duplicate construction

Try 21 keeps the successful Try 19 architecture:

- independent second DK loaded from the captured serialized DK bytes;
- fresh `CMemoryInStream`;
- stock `LoadPlayerGOC` for the second actor;
- no `SLdrPlayer` copy;
- no finished-GOC loader mutation;
- P1 raw DK and P2 raw Diddy primary-registry separation;
- logical DK identity for the visible P2 actor;
- pointer-aware player index;
- raw death bookkeeping;
- exact checkpoint slot dispatch.

## Build and static validation

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 21 IPS SHA-256: `77fdee70ed99cc49a850404c9654dac9a1c106d8e052a7f5f5461662f79e2bbf`
- Helper range: `0xA7A708..0xA7AB80`
- Records: 26 non-overlapping IPS32 records
- Scope: DK + DK

Independent checks completed:

- IPS32 parse/write roundtrip;
- simulated application to the original `main`;
- expected stock bytes at every new hook;
- decoded branch targets for all factory, player, checkpoint and balloon hooks;
- only two instructions changed inside the 164-byte Base18 frontend parser block;
- failed loader-copy and late-loader hooks absent;
- helper remains below the established cave end `0xA7B1B8`.

## Runtime status

Not yet confirmed in game.

Required tests:

1. normal 1P start;
2. obtaining a Kong partner in 1P;
3. normal-mode DK + DK;
4. Hardmode DK + DK;
5. Player 2 reviving Player 1;
6. Player 1 reviving Player 2.
