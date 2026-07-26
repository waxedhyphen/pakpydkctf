# DKCTF – Duplicate DK in Normal Mode and Hard Mode

This file records the confirmed runtime state separately from static patch validation.

## Goal

Both players must be able to select DK independently in normal two-player mode and Hard Mode:

```text
P1 = DK
P2 = DK
```

The two actors must remain separate players with independent control, death, revive and checkpoint state.

## Current UI and ExeFS basis

Build ID:

```text
F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000
```

UI basis:

```text
UIPak SHA-256:
58ce2f8a1ee15f02ccd3edd5b3b3ea06126059da3ef1ac0f20d5538743783fe3
```

The UI passes separate P1 and P2 choices. The duplicate implementation uses a logical DK actor for P2 while keeping Diddy as the internal physical P2 carrier.

## Confirmed runtime state

### Normal two-player mode

Status: **confirmed in game**

The live normal-mode hook at:

```text
0x345898
CProductionFrontEnd::UpdateCharacterTypes path
```

runs after the native `Char_P2` store and before the P2 character-change event. When both stored character types are DK, it arms the duplicate replay state and changes only the internal P2 carrier to Diddy.

Confirmed result:

- normal two-player `DK + DK` starts correctly;
- two visible DK actors exist;
- both players are independently controllable;
- this is the best confirmed duplicate-character baseline so far.

### Hard Mode before the current fix

Status: **bug confirmed in game**

Observed behavior:

- selecting `DK + DK` in Hard Mode did not reliably create P2 DK;
- P2 DK existed only when the normal Kong Select had previously been set to `DK + DK`;
- a normal non-duplicate selection such as `DK + Diddy` followed by Hard-Mode `DK + DK` left P2 DK missing.

This cross-mode dependency was not intended behavior.

## Cause of the Hard-Mode dependency

The Hard-Mode P2 parser is reached at:

```text
0x3527EC -> helper 0xA7A798
```

The previous helper only replaced the Hard-Mode P2 value with the physical Diddy carrier when the global duplicate-state flag was already active.

That flag was armed by the confirmed normal-mode hook. The Hard-Mode argument parser itself did not arm duplicate state from its own selected P1 and P2 values.

Therefore:

```text
normal selector previously DK + DK
    -> duplicate flag already active
    -> Hard Mode P2 replay exists

normal selector previously not DK + DK
    -> duplicate flag inactive
    -> Hard Mode parser never requests the replay
    -> P2 DK missing
```

## Current fix

Artifact scope:

```text
customkong_dkdk_normal_hardmode_fix
```

IPS SHA-256:

```text
bc42c7aa1a2b3575d15c90ae1ead617119c170205f1dd427dca65e1ba3d324d9
```

The fix changes only the existing helper record. The IPS remains at 24 records.

### Hard-Mode parser change

The helper at `0xA7A798` now:

1. stores the selected Hard-Mode P1 type in `GameState+0x2698`;
2. stores the selected Hard-Mode P2 type in `GameState+0x269C`;
3. points the shared duplicate routine at this GameState;
4. tail-branches to the same `DK + DK` activation routine used by the working normal-mode path.

For `DK + DK`, the shared routine:

```text
logical P1 = DK
logical P2 = DK
physical P2 carrier = Diddy
```

It returns the physical P2 type in `W22` to the original Hard-Mode parser, which then writes the existing handoff field at `GameState+0x26C0`.

### Shared caller handling

The common helper is used by three paths:

```text
normal live UpdateCharacterTypes
Hard-Mode argument parser
existing transition/initializer path
```

The return path distinguishes these callers without changing the confirmed normal-mode value held in `W22`.

Unchanged:

- normal hook at `0x345898`;
- transition hook at `0x35236C`;
- serialized replay factory;
- player pointer and index hooks;
- death, checkpoint, barrel and revive hooks;
- modified UIPak selectors.

## Validation status

Static validation passed:

- IPS32 structure is valid;
- all 24 records are sorted and non-overlapping;
- only helper range `0xA7A778..0xA7A7B3` differs from the confirmed normal-mode baseline;
- `0x345898` still branches to `0xA7A734`;
- `0x35236C` still branches to `0xA7A734` and preserves the original `0x1B7EC0` tail path;
- `0x3527EC` still enters `0xA7A798`;
- the Hard-Mode parser now tail-branches from `0xA7A7A4` to `0xA7A734` while preserving its original return address;
- normal-mode `W22` is not overwritten by the new caller handling.

The new Hard-Mode-independent activation is **not yet confirmed in game**.

## Required next test

1. Fully restart the game.
2. Set the normal Kong Select to a non-duplicate pair such as `DK + Diddy`.
3. Enter Hard Mode.
4. Select `DK + DK`.
5. Verify that P2 DK exists and is independently controllable.
6. Test P2 death and P1 death.
7. Test both revive-barrel directions.
8. Exit the level and confirm that normal two-player `DK + DK` still works.

## Current status summary

```text
Normal 2P DK + DK                         confirmed in game
Old Hard-Mode cross-mode dependency       confirmed in game
Cause: Hard-Mode parser did not arm state confirmed statically
New independent Hard-Mode activation      statically validated, test pending
Other duplicate Kong combinations         not implemented
```