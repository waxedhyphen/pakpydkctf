# Duplicate DK Try 19

## Confirmed Try 18 regression

Try 18 read offset `0x26A0` from `CProductionFrontEnd`. That offset belongs to `CGameState`.

This explains both runtime failures:

- real 2P did not arm serialized replay, so no visible second DK was created;
- 1P could arm replay from unrelated frontend memory and spawn an unwanted second DK.

## Fix

Try 19 resolves the real game state through `CFlashIOWin::GameState()` (`0x32F66C`) inside the existing capture helper. It then reads `CGameState+0x26A0` and tests bit 1 for P2 presence.

The stock frontend writes this P2-present bit to `CGameState+0x26A0`. Base18 preserves this bit in `NGameModeSetup::setup_bonus_gamemode` while setting the P1-present bit.

## Retained functionality

Try 19 keeps the existing serialized replay construction and integration patches:

- independent second DK load through a fresh `CMemoryInStream` and stock `LoadPlayerGOC`;
- physical P2 slot stored as Diddy before primary-player registration;
- P1 raw DK and P2 raw Diddy stored in separate primary-player registry entries;
- pointer-aware `CPlayer::GetPlayerIndex()`;
- raw-slot death bookkeeping;
- slot-specific checkpoint and respawn lookup.

No `SLdrPlayer` copy or loader replacement is used.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 19 IPS SHA-256: `02ff5d3ca885d6b57a5f0e5ef595017ef3afbbff74450cd9d170cf20cf363190`
- Helper range: `0xA7A708..0xA7AACC`
- Scope: DK + DK

## Runtime status

Not yet confirmed. Required checks:

1. 1P hard-mode level entry produces exactly one DK.
2. 2P DK+DK produces two visible DK actors.
3. P1 and P2 can interact with barrels and world objects.
4. P2 contributes to camera movement.
5. P1 and P2 death/rejoin and checkpoint respawn work independently.
