# DKCTF Hard Mode Multiplayer – In-Game Test Log

This file records observed in-game behavior separately from static binary findings.

## Reference build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

## Test 1 – active P2 slot only

External project:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test1.json
```

Patch:

```text
0x1E7018
29 15 1E 12 -> 29 19 1F 12
```

Purpose: preserve bit 1 in the active-slot byte at `+0x26A0` while Hard Mode initializes.

### In-game result

Status: **partially successful**

Observed:

- Both characters were visible in the level-loading preview.
- With DK and Diddy, Diddy appeared on DK's back.
- Only one independently controllable player existed after the level started.
- The result was the normal one-player companion/piggyback state, not multiplayer.

Conclusion:

- The IPS32 patch was loaded.
- Preserving the active-slot bit kept the second Kong represented as a partner.
- The active-slot bit alone did not enable the independent P2 controller/spawn path.

## Additional blocker found after Test 1

Hard Mode initializes the byte at `game state + 0x26AF` to zero:

```asm
0x1E6FE4  MOV  W8, #0x26AF
0x1E6FEC  STRB WZR, [X19, X8]
```

Original bytes:

```text
7F 6A 28 38
```

The function at `0x33557C`, used by `UpdateCharacterTypes` and the common level-transition helper, reads this byte first:

```text
+0x26AF == 0 -> false
```

When false, the independent P2 path is skipped. The source-level name of `+0x26AF` is not yet proven, so the documentation keeps the address-based description.

## Test 2 – independent P2 path plus active slot

External project:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test2.json
```

Validated entries:

```text
0x1E6FEC
7F 6A 28 38 -> 1F 20 03 D5
STRB WZR, [X19, X8] -> NOP

0x1E7018
29 15 1E 12 -> 29 19 1F 12
AND #0xFC -> AND #0xFE
```

Purpose:

1. do not clear the separate `+0x26AF` state byte during Hard Mode initialization;
2. preserve the P2 active-slot bit.

### In-game result

Status: **confirmed**

Observed:

- Hard Mode starts with two real players.
- P2 exists independently instead of only as a piggyback companion.
- P2 is controllable by the second controller.
- The multiplayer activation problem is therefore solved for the reference build.

Remaining character-selection behavior:

- Hard Mode still chooses the pair automatically.
- When P1 is DK, P2 becomes Diddy.
- When P1 is Diddy, Dixie or another buddy Kong, P2 becomes DK.
- Funky is not currently available through the stock Hard-Mode selector in normal mode.
- The exact P2 character selected in the earlier KONG-select UI is not preserved by the Hard-Mode initialization.

This remaining limitation is a separate character-selection problem, not a failure of the multiplayer-enabling ExeFS patch.

## Current next phase – Hard-Mode UI

Main UI objective:

- duplicate the existing Hard-Mode Kong selector;
- show one selector for P1 and one for P2;
- eventually expose the full list `DK, Funky, Diddy, Dixie, Cranky` for each player;
- first verify the second selector visually before adding AVM2 state and input logic.

The structural UI findings and the exact visual-copy test are documented in:

```text
PAKPY/UI_HARDMODE_KONG_SELECT.md
```

## Status meanings

```text
Binary validated  = original bytes and control flow verified in the provided main
In-game partial   = patch is loaded and changes behavior, but target behavior is incomplete
In-game confirmed = independent P2 is present and controllable in Hard Mode
```
