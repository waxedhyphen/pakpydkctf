# Try 17 runtime result

Date: 2026-07-26

## Confirmed working

- Level entry no longer crashes.
- A real second Donkey Kong actor is present.
- The replayed actor uses Donkey Kong's model, animations, FSM and gameplay modules.
- This is the first duplicate-character attempt that reaches gameplay with two actual DK actors instead of a Diddy actor relabeled as DK.
- In two-player mode, player 2 can interact with barrels and other world objects.

## Confirmed broken

### Single-player regression

- Starting a one-player level incorrectly creates a second DK.
- The Try 17 replay path is therefore not guarded by a reliable explicit two-player condition.

### Two-player duplicate DK

- Player 1 is the actor with broken barrel and world-object interaction.
- Player 2 can interact with those objects normally.
- Player 2 does not contribute correctly to forward camera movement.
- If either player dies, the normal multiplayer respawn/rejoin flow does not work.

## Corrected interpretation

Try 17 solves independent actor/resource construction but corrupts or replaces ownership used by the original player 1 actor.

The important correction is that player 2 is not the actor rejected by barrel and world-object interactions. Player 2 works there; player 1 does not.

This suggests that the independently replayed DK load overwrites a DK-keyed registration or ownership entry that originally belonged to player 1. Likely candidates include:

- the single `PrimaryPlayer[DK]` entry;
- CharacterType-to-player registration;
- DK-keyed interaction ownership or entity lookup.

This is an inference from the runtime behavior and is not yet isolated to one exact write site.

The remaining camera and respawn failures still show that two same-type actors are not represented correctly by stock CharacterType-based systems.

## Next target

Keep the serialized replay construction that produces a real second DK. Do not return to `SLdrPlayer` copying or CharacterType-only relabeling.

Priority order:

1. add a reliable explicit two-player guard so one-player mode remains byte-semantically equivalent to the uploaded `(18).ips` base;
2. prevent the replayed second DK from overwriting player 1's DK registration/ownership;
3. repair camera participant/player-boundary lookup;
4. repair death, respawn and checkpoint lookup;
5. audit remaining CharacterType-keyed consumers.

The next patch must preserve player 1's stock DK ownership while maintaining player 2 through its separate physical P2 slot.

## Status

Try 17 is a partial runtime success, not a complete duplicate-Kong implementation.
