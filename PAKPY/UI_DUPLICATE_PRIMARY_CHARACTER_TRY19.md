# Duplicate DK Try 19

## Status

Try 19 is the best runtime result so far, but it is not complete.

## Confirmed working in 2P

- DK + DK creates two visible DK actors.
- Both actors are independently constructed through the serialized replay path.
- Model, animations, FSM and DK gameplay modules are valid for both actors.
- The previous `CAnimSet::GetAnimationFromId` crash is gone.
- P2 can interact with ordinary barrels and other world objects.
- No `SLdrPlayer` copy or loader replacement is used.

## Confirmed 1P bugs

- Only one player is visible, but the level is initialized in a partner-present/two-player-like state.
- The replay registry remains armed after the initial P1 DK load.
- When a Kong partner is collected later, that partner `LoadPlayerGOC` is intercepted as the pending replay actor.
- The player then dies instead of receiving the normal 1P Kong partner.

### Cause

Try 19 uses `CGameState+0x26A0 bit1` as its multiplayer gate. Stock also sets this bit for a normal 1P Kong-partner state, so it does not prove that a second human player is active.

The required gate is `CGameState::IsMultiplayerActive()` on the real game-state object.

## Confirmed revive bugs in 2P

### P2 attempts to revive P1

- P2 cannot interact successfully with P1's revive barrel.
- P1 is not restored.

### P1 attempts to revive P2

- The revive barrel is consumed.
- P2 does not return.

### Current cause analysis

Try 19 resolves the four checkpoint/rejoin lookups from constructor-time cached `CPlayer*` pointers. These can stop representing the live primary-player entries after death, barrel capture or reactivation.

The stock revive path at `0x3BD390` also assumes that P1/DK is the available first player. Supporting P1 revival requires selecting P2 as the surviving first actor when P1 cannot satisfy the stock active/alive flags, then resolving the opposite slot at `0x3BD3CC`.

## Retained architecture

- independent second DK load through a fresh `CMemoryInStream` and stock `LoadPlayerGOC`;
- physical P2 carrier stored in the raw Diddy slot;
- logical public identity remains DK;
- P1 raw DK and P2 raw Diddy use separate primary-player registry entries;
- raw-slot death bookkeeping;
- duplicate scope remains DK + DK.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 19 IPS SHA-256: `02ff5d3ca885d6b57a5f0e5ef595017ef3afbbff74450cd9d170cf20cf363190`
- Helper range: `0xA7A708..0xA7AACC`

## Next patch requirements

1. Gate replay with the real `CGameState::IsMultiplayerActive()` result, not `+0x26A0 bit1`.
2. Resolve P1/P2 from the live stock primary-player table instead of cached construction pointers.
3. Keep the working serialized DK replay unchanged.
4. Allow the revive path to use P2 as the surviving first actor when P1 is unavailable.
5. Preserve normal 1P Kong-partner loading.