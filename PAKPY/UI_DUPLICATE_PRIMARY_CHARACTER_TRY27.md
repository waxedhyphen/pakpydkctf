# Duplicate DK Try 27

## Baseline

Try 26 is fully discarded. Its player-count gate and `CPlayerActorGOC::OnAction_SyncPlayer` hook disabled or corrupted all tested modes.

Try 27 returns to the Try 22 multiplayer/revive baseline. No Try 24, Try 25 or Try 26 menu-count, controller-disconnect, spawn-sync or unloader hook is retained.

## Stock-controlled 1P / 2P transition

The original instructions at `0x352320` and `0x352324` remain byte-identical:

- stock calls `CGameState::IsMultiplayerActive()`;
- stock decides whether the real P2 path is entered;
- the mod does not replace that decision.

At `0x352288`, the helper only reproduces the displaced `and w8,w0,#1` and clears stale duplicate-replay registry state for a new transition.

## Duplicate activation

Duplicate DK is armed at `0x35236C` only after stock has already:

1. entered the real P2 branch;
2. read `RuntimeData_Char_P2`;
3. stored P2 in `CGameState+0x269C`;
4. set player-present bit 1 in `CGameState+0x26A0`.

The helper checks `CGameState+0x2698` and `+0x269C`. Only DK + DK activates serialized replay. P2 is then changed only at the physical layer to Diddy in `+0x269C` and Base18 handoff `+0x26C0`.

The Base18 hard-mode parser no longer activates duplicate mode. Its hook at `0x3527EC` only preserves physical Diddy when the actual frontend P2 path has already armed replay. A later 1P Kong-partner barrel therefore cannot arm duplicate-P2 state.

## Retained Try 22 integration

- independent serialized DK replay through a fresh `CMemoryInStream`;
- separate raw DK and Diddy registry slots;
- pointer-aware player indexes;
- raw death bookkeeping;
- raw target/survivor CharacterTypes in `CBarrelBalloonGOC::StartPlayerRejoin`;
- slot-specific checkpoint dispatch.

## Explicitly excluded

- no `shell_playerCount` query;
- no `RuntimeData_PlayerCount` query;
- no hook at `0x352320` or `0x352324`;
- no deletion when P2 disconnects;
- no intro-spawn hook;
- no level-unloader pointer-chain hook.

Stock retains a Kong when P2 disconnects. Actor destruction remains part of stock level unloading. Carry-over cleanup and intro spawn synchronization require separate proven paths and are not mixed into this recovery build.

## Build

- Base18 SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 27 IPS SHA-256: `7b1f86275ce963931bf493f8dbfefb391862e7a8354f613ca16cc3d4b79056ff`
- Helper range: `0xA7A708..0xA7AAD0`
- Records: `23`
- Scope: DK + DK

## Runtime status

Not yet confirmed in game. Recovery checks are cold normal 1P, cold hard-mode 1P, normal DK + DK 2P, hard-mode DK + DK 2P and both revive directions. Intro spawn synchronization and level-exit carry cleanup are intentionally isolated from this build.