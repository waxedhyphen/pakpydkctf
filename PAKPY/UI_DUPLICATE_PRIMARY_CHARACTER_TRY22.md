# Duplicate DK Try 22

## Baseline

Try 19 remains the runtime baseline. It is the first approach that creates two actual Donkey Kong actors through an independent serialized replay without the earlier `CAnimSet` crash.

Try 20 and Try 21 are discarded because their runtime behavior did not fix the reported bugs. Try 21 also patched the wrong balloon subsystem.

## Confirmed Try 19 runtime state

Working:

- normal and hard-mode 2P can reach gameplay with two visible DK actors;
- the replay actor has its own DK model, animation set, FSM and gameplay modules;
- P2 can interact with normal barrels and world objects;
- this is the best duplicate-character baseline so far.

Broken:

- 1P still enters with a two-player/partner-present state;
- obtaining a Kong partner in that 1P state kills the player;
- P2 cannot successfully release P1 from P1's revive barrel;
- P1 can consume P2's revive barrel, but P2 is not restored.

## 1P / 2P gate correction

Try 22 hooks `CProductionFrontEnd::InitGameTransition` at `0x352288`, directly after the stock `CGameState::IsMultiplayerActive()` call at `0x352284`.

This is the exact stock result that:

- is stored in `CGameState+0x26AF`;
- controls whether the frontend reads `RuntimeData_Char_P2` moments later.

The result is transferred into the later explicit-character parser as a one-shot value. It is consumed and cleared at `0x3527EC`.

This avoids all previously unreliable gates:

- `CGameState+0x26A0 bit 1`, which also represents a 1P Kong partner;
- a delayed second call to `IsMultiplayerActive()`;
- `RuntimeData_PlayerCount` read from the Flash data model at the wrong phase.

## Actual revive barrel path

The individual multiplayer revive path is not `CRespawnBalloonGOC`.

The relevant stock path is:

```text
CPlayerModuleRiseFromTheGrave::PostOwnerOrInactiveThink
    -> CBarrelBalloonGOC::StartPlayerRejoin
```

`StartPlayerRejoin` stores two CharacterTypes:

- dead target at `0x3ADEBC`;
- living player at `0x3ADEC8`.

Try 19's targeted logical override makes both duplicate actors report DK at these two calls. That collapses the target and survivor onto the same CharacterType.

Try 22 replaces only these calls with the stock-equivalent raw `CPlayer+0x14` getter:

- P1 uses raw DK slot;
- P2 uses raw Diddy slot;
- both visible actors and gameplay modules remain DK.

The ineffective Try 21 `CRespawnBalloonGOC` hooks are not included.

## Retained Try 19 behavior

- independent `CMemoryInStream -> LoadPlayerGOC` replay;
- separate raw primary-player registry entries;
- pointer-aware `CPlayer::GetPlayerIndex()`;
- raw death bookkeeping;
- slot-specific checkpoint lookups;
- no `SLdrPlayer` copy or finished-GOC mutation.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 22 IPS SHA-256: `0be9e5636a43b1ddf7ac9976ca1e61616ca9344d1130ba8de449797774aa0f88`
- Helper range: `0xA7A708..0xA7AAE0`
- Scope: DK + DK

## Runtime status

Not yet confirmed. Required checks:

1. normal 1P start;
2. obtaining a Kong partner in 1P;
3. normal 2P DK + DK;
4. hard-mode 2P DK + DK;
5. P2 revives P1;
6. P1 revives P2.
