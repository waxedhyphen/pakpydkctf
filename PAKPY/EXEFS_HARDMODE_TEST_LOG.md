# DKCTF Hard Mode Multiplayer – In-Game Test Log

This file records only observed in-game behavior and the native facts used to define the next isolated test.

## Reference build

```text
Build ID:
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

## Test 1

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

- Both characters are visible in the level-loading preview.
- When P1 is DK and the other selected Kong is Diddy, Diddy appears on DK's back.
- Only one independently controllable player exists after the level starts.
- This is companion/piggyback behavior, not normal two-player behavior.

Conclusion:

- The IPS32 patch is being loaded.
- Preserving the active-slot bit is sufficient to keep the second Kong represented as a partner.
- The active-slot bit alone does not enable the independent P2 controller/spawn path.

## Additional native blocker identified after Test 1

Hard Mode initializes the byte at `game state + 0x26AF` to zero:

```asm
0x1E6FE4  MOV  W8, #0x26AF
0x1E6FEC  STRB WZR, [X19, X8]
```

Original bytes at `0x1E6FEC`:

```text
7F 6A 28 38
```

The function at `0x33557C`, used both by `UpdateCharacterTypes` and the `initLevelTransition` helper, first reads this byte:

```text
+0x26AF == 0 -> returns false
```

When that check returns false, the independent P2 path is skipped. This matches the observed result: the second Kong remains available as a one-player companion but is not activated as a separate player.

The source-level name of `+0x26AF` is not yet proven; the documentation therefore keeps the address-based description.

## Test 2

External project:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test2.json
```

It contains two independently validated entries:

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
2. continue preserving the P2 active-slot bit.

Still deliberately not addressed:

- preserving the exact P2 character selected in the KONG-select UI;
- any later Hard-Mode-specific restrictions after spawning.

## Test status meanings

```text
Binary validated       = original bytes and control flow verified in the provided main
In-game partial        = patch is loaded and changes behavior, but target behavior is incomplete
In-game confirmed      = independent P2 is present and controllable in Hard Mode
```
