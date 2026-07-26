# Duplicate DK Try 23

## Baseline

Try 23 is Try 22 with one isolated transition-gate correction. The serialized second-DK load, raw P1/P2 slots, player-index handling, checkpoint dispatch and `CBarrelBalloonGOC::StartPlayerRejoin` changes are unchanged.

## Confirmed Try 22 result

- ordinary two-player/rejoin behavior improved;
- duplicate DK remained limited to hard mode;
- singleplayer still entered a two-player/partner-present state in both normal and hard mode.

## Cause

Try 22 captured the preliminary `IsMultiplayerActive()` result at `0x352284/0x352288`. That is not the final decision used to enter the P2 character-data path.

The decisive stock sequence is:

```text
0x352320  bl CGameState::IsMultiplayerActive
0x352324  tbz w0, #0, 0x352418
0x352328  RuntimeData_Char_P2 path
0x352418  singleplayer path
```

## Try 23 change

- remove the Try 22 hook at `0x352288` and restore the original `and w8, w0, #1`;
- replace only the decisive `tbz` at `0x352324`;
- record the exact stock P2-read decision;
- branch to the original P2 target `0x352328` or original 1P target `0x352418`;
- transfer the decision once to the explicit-character parser and clear it after consumption.

This is intended to produce the same duplicate-DK activation in normal and hard-mode 2P while leaving both 1P modes unarmed.

## Binary delta from Try 22

Only these areas differ:

1. `0x352288` is no longer patched.
2. `0x352324` branches to `try23_capture_transition_multiplayer`.
3. The first helper routine now records and reproduces the decisive branch instead of the preliminary `and` instruction.

The rest of the helper and all revive changes are retained.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 23 IPS SHA-256: `315c67a3f5d3b107ec241a13fcf19402c1bad35248838137f837a21cf0c8699c`
- ZIP SHA-256: `6832e2458fb5a5af7980ed61c33621393e3da024fac8dafc4c06623d8e235571`
- Helper range: `0xA7A708..0xA7AAE0`
- Scope: DK + DK

## Runtime status

Not yet confirmed. Required checks:

1. normal 1P start;
2. hard-mode 1P start;
3. obtaining a Kong partner in both 1P modes;
4. normal 2P DK + DK;
5. hard-mode 2P DK + DK;
6. both revive directions.