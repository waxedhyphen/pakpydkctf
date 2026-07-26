# Duplicate DK – Try 18 integrated player-slot fix

Date: 2026-07-26

## Basis

Try 18 is built directly on the user-confirmed 249-byte Base18 IPS:

- Base SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Build ID: `F48BD40D89B529C114F17C7909FE6AA400000000000000000000000000000000`

Try 17's serialized replay is retained because it is the first path confirmed in game to create two actual DK actors with valid models, AnimSets, FSMs, and gameplay modules.

## Confirmed Try 17 runtime problems

- 1P incorrectly spawned a second DK.
- P2 could interact with barrels and world objects, but P1 could not.
- P2 did not contribute to forward camera movement.
- Death/rejoin and checkpoint respawn did not work correctly.

## Try 18 changes

### Exact 1P/2P gate

Duplicate replay is armed only when `CProductionFrontEnd+0x26A0 bit 1` is set. This is the exact field loaded by Base18 at `0x352804` and tested at `0x35280C` to choose its working 1P/2P transition path.

The registry is reset at every level transition. The factory cannot replay a second DK unless this exact Base18 branch armed it.

### Primary-player registration

Try 17 exposed logical DK through `CPlayer::GetCharacterType()` during `CStateManagerGameData::SetPrimaryPlayer`, causing P2 to overwrite the DK registry entry used by P1.

Try 18 patches `0x2CE150` so registration uses raw `CPlayer+0x14`:

- source P1: raw DK registry entry;
- replay P2: raw Diddy registry entry.

The replay actor still exposes logical DK to targeted gameplay paths.

### Player index / camera participation

`CPlayer::GetPlayerIndex()` at `0x1FA6AC` is pointer-aware:

- recorded source P1 pointer -> index 0;
- recorded replay P2 pointer -> index 1;
- all unrelated players -> exact stock CharacterType fallback.

### Death and respawn

- `0x2435A4` records the raw physical slot in `SetLastDeadPrimaryPlayer`, preventing P2 death from colliding with P1's DK entry.
- Checkpoint lookups at `0x3BD0E8`, `0x3BD18C`, `0x3BD390`, and `0x3BD3CC` dispatch to exact player slots while preserving stock active/alive filtering.

## Explicitly excluded

No loader-copy or post-construction loader mutation is used. Failed hooks at `0x2A5358`, `0x2A71B4`, `0x2A71B8`, and `0x2A7498` remain absent.

## Build

- IPS SHA-256: `338dd2b3dda5b5a46b8371a7ecc9562a6ff39d7cfcebd01a39d1c3db10c51270`
- Helper: `0xA7A708..0xA7AAC0`, 952 bytes
- Records: 19

## Status

Statically validated; runtime confirmation is pending.

Required runtime checks:

1. normal 1P level entry has exactly one DK;
2. DK+DK reaches gameplay;
3. both players interact with barrels/world objects;
4. P2 advances the camera;
5. P1 and P2 death/rejoin work;
6. checkpoint respawn works for both slots.
