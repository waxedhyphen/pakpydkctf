# Duplicate DK Try 22

## Baseline

Try 19 remains the serialized-replay baseline. It is the first approach that creates two actual Donkey Kong actors through an independent load without the earlier `CAnimSet` crash.

Try 20 and Try 21 are discarded. Try 21 also patched the wrong balloon subsystem.

## Retained construction

- independent `CMemoryInStream -> LoadPlayerGOC` replay;
- separate raw primary-player registry entries;
- pointer-aware `CPlayer::GetPlayerIndex()`;
- raw death bookkeeping;
- slot-specific checkpoint lookups;
- no `SLdrPlayer` copy or finished-GOC mutation.

## Revive correction

The relevant path is:

```text
CPlayerModuleRiseFromTheGrave::PostOwnerOrInactiveThink
    -> CBarrelBalloonGOC::StartPlayerRejoin
```

`StartPlayerRejoin` stores the dead target at `0x3ADEBC` and the surviving player at `0x3ADEC8`. Try 22 replaces those two logical CharacterType calls with raw `CPlayer+0x14` reads so P1 remains raw DK and P2 remains raw Diddy while both visible actors remain DK.

## Transition gate used by Try 22

Try 22 hooks `CProductionFrontEnd::InitGameTransition` at `0x352288`, after the preliminary `CGameState::IsMultiplayerActive()` call at `0x352284`. The captured value is transferred once to the explicit-character parser and consumed at `0x3527EC`.

## Confirmed runtime result

Reported working:

- the ordinary two-player/rejoin path is improved compared with Try 19;
- duplicate DK still works in hard mode.

Reported broken:

- duplicate DK is not activated in normal mode;
- singleplayer is still treated as a two-player/partner-present start in both normal and hard mode;
- therefore Try 22 does not solve the transition-mode detection.

## Root cause after runtime test

The call at `0x352284` is preliminary and is not the final branch that decides whether P2 character data is read. Capturing it can arm 1P and reject normal-mode 2P.

The decisive stock check occurs later:

```text
0x352320  CGameState::IsMultiplayerActive(real transition GameState)
0x352324  tbz w0, #0, 0x352418
0x352328  begin RuntimeData_Char_P2 path
```

Try 22 is superseded by Try 23, which leaves `0x352288` stock and hooks only the decisive `0x352324` branch.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 22 IPS SHA-256: `0be9e5636a43b1ddf7ac9976ca1e61616ca9344d1130ba8de449797774aa0f88`
- Helper range: `0xA7A708..0xA7AAE0`
- Scope: DK + DK

## Status

Superseded. Keep only as the confirmed baseline for the corrected revive path.