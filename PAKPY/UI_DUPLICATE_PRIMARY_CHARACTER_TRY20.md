# Duplicate DK Try 20

## Basis

Try 20 keeps Try 19's working serialized second-DK construction. It does not copy `SLdrPlayer` and does not rebuild an already constructed `CPlayerGOC`.

## Fix 1: real multiplayer gate

Try 19 used `CGameState+0x26A0 bit1`. That bit is also valid in 1P when a Kong partner is present.

Try 20 instead:

1. resolves the real `CGameState` through `CFlashIOWin::GameState()` (`0x32F66C`);
2. calls `CGameState::IsMultiplayerActive()` (`0x33557C`);
3. arms serialized replay only when that predicate is true and the requested pair is DK + DK.

This prevents the replay stage from remaining armed in 1P and intercepting a later Kong-partner load.

## Fix 2: stable duplicate identity

Constructor-time cached `CPlayer*` values are no longer the primary identity source.

While duplicate mode is active:

- raw DK carrier maps to P1/index 0;
- raw Diddy carrier maps to logical DK and P2/index 1.

This survives player reactivation or replacement better than exact pointer comparison.

## Fix 3: live primary-player lookup

The checkpoint/rejoin helper now maps slots through the stock live primary-player table on every call:

- slot 0 -> raw DK registry entry;
- slot 1 -> raw Diddy registry entry.

The caller's original active/alive flags remain intact.

## Fix 4: bidirectional revive role selection

The stock path at `0x3BD390` assumes P1/DK is the first available player.

Try 20:

- prefers P1 when P1 satisfies the stock flags;
- otherwise uses P2 as the surviving first actor;
- records the selected slot;
- resolves the opposite slot at the paired lookup `0x3BD3CC`.

This targets both P1 -> P2 and P2 -> P1 revive-barrel directions without globally swapping player identities.

## Patched consumers

- `0x1F70D0`: records source/replay player construction and sets the physical P2 carrier slot;
- `0x1FA354`: logical DK identity for the raw Diddy carrier;
- `0x1FA6AC`: stable raw-slot player index;
- `0x2435A4`: raw-slot death bookkeeping;
- `0x2CE150`: raw-slot primary-player registration;
- `0x38EE7C`: proven serialized replay dispatcher;
- `0x3BD0E8`, `0x3BD18C`, `0x3BD390`, `0x3BD3CC`: live checkpoint/rejoin/revive player resolution.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 20 IPS SHA-256: `00caf24e9cb03c74b3425b3cfe7819c42cf68d5a447f7ce1a61f48896caedd36`
- Helper: `0xA7A708..0xA7AB00`
- Scope: DK + DK

## Runtime status

Statically validated, not yet confirmed in game.

Required tests:

1. clean 1P level start;
2. collect a normal Kong partner in 1P;
3. DK + DK 2P start;
4. P2 camera contribution;
5. P1 revives P2;
6. P2 revives P1;
7. both death/rejoin directions.