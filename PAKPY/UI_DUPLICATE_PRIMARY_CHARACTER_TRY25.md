# Duplicate DK Try 25

## Baseline

Try 22 remains the functional multiplayer baseline:

- normal 2P works;
- the serialized replay creates a real second DK actor;
- the raw-slot revive correction is retained.

Try 25 attempted to restore 1P and remove the duplicate partner on controller leave.

## Confirmed runtime result

Working:

- same-character multiplayer can still create two actual DK actors.

Broken:

- singleplayer is still invalid;
- collecting a normal Kong partner barrel in 1P kills the player;
- after the intro sequence, P1 is reset to P2's spawn position;
- the duplicate partner-removal timing is wrong.

## Confirmed implementation errors

### Wrong player-count enum and parser

Try 25 reads enum `0x48`, but `mMenuStates@shell_playerCount` is enum `0x49`.

Enum `0x48` belongs to `shell_P1_ControllerMotionEnabled`.

Try 25 also interprets the value as literal `1` or `2`. The stock parser `NFlashData::get_player_index_from_flash_value()` returns:

- `0` for one human player;
- `1` for two human players.

This invalid gate can leave the duplicate replay active in 1P and causes a normal partner barrel to enter the duplicate-P2 path.

### Wrong duplicate-partner removal timing

Try 25 hooks controller departure at `0x32B50C` and queues Delete from `CPlayer::Think` at `0x1F88EC`.

That is incorrect. Stock keeps a Kong partner when P2 disconnects during a level. The mod-specific duplicate DK must remain during the level and be removed by normal actor teardown at level exit.

Both Try 25 hooks are discarded.

### Intro spawn collision

`CPlayerActorGOC::OnAction_SyncPlayer` resolves the player through CharacterType at `0x41CA5C`.

Because both duplicate actors report logical DK, both actor syncs resolve P1. P2's actor therefore resets P1 to P2's spawn after the intro sequence.

The required correction is actor-index-based lookup through `CPlayerActorGOC+0x78`.

## Retained functionality

- independent serialized DK replay through a fresh `CMemoryInStream`;
- separate raw DK/Diddy player registry entries;
- pointer-aware player indexes;
- raw death bookkeeping;
- raw target/survivor types in `CBarrelBalloonGOC::StartPlayerRejoin`;
- checkpoint slot dispatch;
- no loader copy or finished-GOC mutation.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 25 IPS SHA-256: `b47b921592ba09f21a8d725be5582c60b2ad6cd6eb690163b95cadb23ddbf483`
- Helper range: `0xA7A708..0xA7AC38`
- Records: `25`

## Status

Try 25 is discarded as a complete patch.