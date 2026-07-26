# Duplicate DK Try 24

## Confirmed Try 23 failure

Try 23 did not change the reported 1P behavior. The loading screen already entered as a two-player transition, so the error occurred before the serialized actor replay.

The previous transition gates used `CGameState::IsMultiplayerActive()` or interpreted `RuntimeData_PlayerCount` as the literal value `2`. Both were wrong for this purpose:

- `IsMultiplayerActive()` can remain true from hard mode or a Kong-partner state;
- `RuntimeData_PlayerCount` stores a player index, not a literal count.

The stock parser `NFlashData::get_player_index_from_flash_value()` at `0x1F53BC` defines the relevant values:

- `0` = one human player;
- `1` = two human players.

## Transition fix

Try 24 replaces the `IsMultiplayerActive()+TBZ` pair at `0x352320` inside `CProductionFrontEnd::InitGameTransition`.

The helper reads `RuntimeData_PlayerCount` (`0x75`) from the current frontend `CFlashDataModel` and parses it with the stock player-index parser.

For true 1P, before the loading-screen state is finalized, it clears:

- `CGameState+0x26AF` multiplayer-active byte;
- bit 1 of `CGameState+0x26A0`;
- Base18's `CGameState+0x26C0` physical-P2 handoff;
- all duplicate-replay registry state.

For true 2P it enters the original stock P2-character path.

## Mode-independent DK+DK activation

Try 24 no longer activates duplicate mode from the hard-mode argument parser.

At `0x35236C`, after stock has actually read and stored a real P2 character, the helper checks:

- `CGameState+0x2698` = P1 character;
- `CGameState+0x269C` = P2 character.

Only a real two-player DK+DK transition arms the serialized replay. The physical P2 component is changed to Diddy in `+0x269C` and `+0x26C0`, while the visible and logical actor remains DK through the existing pointer-specific override.

The later hard-mode argument parser only preserves this already-armed physical Diddy carrier. It cannot activate duplicate mode by itself.

## Retained behavior

- independent serialized DK replay from Try 19;
- separate raw primary-player registry entries;
- pointer-aware player indexes;
- raw death bookkeeping;
- Try 22 raw target/survivor types in `CBarrelBalloonGOC::StartPlayerRejoin`;
- checkpoint slot dispatch;
- no `SLdrPlayer` copy or finished-GOC mutation.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 24 IPS SHA-256: `4d19b3b1a5405ef621e667650251f21778e65039ebd1045d1a96736109177612`
- Helper range: `0xA7A708..0xA7AB3C`
- Scope: DK+DK in normal and hard mode while preserving real 1P

## Runtime status

Not yet confirmed. Required checks:

1. normal 1P loading screen and level start;
2. hard-mode 1P loading screen and level start;
3. obtaining a Kong partner in 1P;
4. normal-mode 2P DK+DK;
5. hard-mode 2P DK+DK;
6. P2 revives P1;
7. P1 revives P2.
