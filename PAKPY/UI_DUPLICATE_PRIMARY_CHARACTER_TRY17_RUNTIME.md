# Try 17 runtime result

Date: 2026-07-26

## Confirmed working

- Level entry no longer crashes.
- A real second Donkey Kong actor is present.
- The second actor uses Donkey Kong's model, animations, FSM and gameplay modules.
- This is the first duplicate-character attempt that reaches gameplay with two actual DK actors instead of a Diddy actor relabeled as DK.

## Confirmed broken

The second DK is not fully registered as a normal second player:

- cannot interact correctly with barrels and other world objects;
- does not contribute to forward camera movement;
- if either player dies, the normal multiplayer respawn/rejoin flow does not work.

## Current interpretation

Try 17 solves independent actor/resource construction but not player-system integration.

The second actor currently has a split identity:

- DK model, animation set, FSM and gameplay modules;
- separate physical P2 slot based on the Diddy player slot;
- logical DK identity exposed by selected lookup paths.

Systems that still resolve players through CharacterType, PrimaryPlayer tables or CharacterType-to-index conversion can therefore select P1, reject P2 or fail to find an unambiguous player.

## Next target

Do not change or rebuild the second actor again. Keep the serialized replay construction from Try 17 and repair the remaining player consumers individually.

Priority order:

1. world-object and barrel interaction ownership;
2. camera participant/player-boundary lookup;
3. death, respawn and checkpoint lookup;
4. remaining CharacterType-based P1/P2 consumers.

Prefer exact actor-pointer or physical player-slot resolution for these systems. Do not globally force both actors through the same CharacterType-to-player lookup.

## Status

Try 17 is a partial runtime success, not a complete duplicate-Kong implementation.
