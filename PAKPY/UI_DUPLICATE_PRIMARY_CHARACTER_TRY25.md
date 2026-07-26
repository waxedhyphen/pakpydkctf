# Duplicate DK Try 25

## Baseline

Try 22 remains the functional multiplayer baseline:

- normal 2P works;
- the serialized replay creates a real second DK actor;
- the raw-slot revive correction is retained.

Try 24 is discarded except for the finding that 1P must be corrected before loading-screen state is finalized.

## Correct player-count source

Try 25 reads `mMenuStates@shell_playerCount` through enum `0x48` from the current frontend `CFlashDataModel`.

The returned `CFlashValue` is parsed with `CFlashValue::GetInt()` (`0x656814`):

- literal `1` = one human player;
- literal `2` = two human players.

The hook replaces the stock `IsMultiplayerActive()+TBZ` decision at `0x352320`.

For missing or invalid menu data, the helper falls back to stock `CGameState::IsMultiplayerActive()` instead of forcing either mode.

## 1P behavior

For an actual 1P transition, `CGameState+0x26AF` is cleared before the loading screen is finalized.

Normal retained Kong partners are preserved. The P2-present bit and P2 selection are cleared only when the outgoing partner belongs to the active duplicate-DK replay.

## Normal- and hard-mode DK+DK

At `0x35236C`, after the frontend has read and stored a real P2 character, DK+DK arms the existing serialized replay.

Only the physical P2 carrier is changed to Diddy in:

- `CGameState+0x269C`;
- Base18 handoff `CGameState+0x26C0`.

The visible actor, animation set, FSM and logical character remain DK through the existing pointer-specific integration.

The hard-mode argument parser no longer activates duplicate mode. It only preserves the physical Diddy carrier if the frontend already armed DK+DK.

## Duplicate partner removal on 2P -> 1P

Stock normally keeps the P2 Kong as a 1P partner. That behavior remains unchanged for ordinary partners.

For the replay-created duplicate DK only:

1. the controller update hook at `0x32B50C` observes the freshly computed human-P2 value becoming zero;
2. it clears the duplicate P2-present bit, physical P2 selection and Base18 P2 handoff;
3. it marks the exact replay-created P2 actor for deletion;
4. the next `CPlayer::Think` for that exact actor calls stock `CStateManagerObject::QueueScriptMsgToSelf(Delete)`;
5. replay actor, loader and player registry pointers are then cleared.

No direct memory free is used.

## Retained Try 22 behavior

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
- Scope: DK+DK in normal and hard mode; preserve 1P and ordinary partner retention

## Runtime status

Not yet confirmed. Required checks:

1. cold normal 1P loading screen and start;
2. cold hard-mode 1P loading screen and start;
3. normal 2P DK+DK;
4. hard-mode 2P DK+DK;
5. leave duplicate-DK 2P and continue/re-enter as 1P;
6. ordinary 1P partner retention without duplicate mode;
7. P2 revives P1;
8. P1 revives P2.
