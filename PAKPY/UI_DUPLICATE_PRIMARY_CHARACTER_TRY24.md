# Duplicate DK Try 24

## Runtime result

Try 24 is discarded as a complete patch.

Confirmed working:

- normal singleplayer starts without a second player.

Confirmed broken:

- normal 2P no longer enters the duplicate-DK path;
- hard-mode 2P no longer enters the duplicate-DK path;
- consequently the functional Try 22 multiplayer baseline was regressed.

## Confirmed cause

Try 24 read `RuntimeData_PlayerCount` (`0x75`) and passed it to `NFlashData::get_player_index_from_flash_value()` (`0x1F53BC`). That was the wrong parser for this value.

Stock `NFlashData::init_player_info` writes `RuntimeData_PlayerCount` as a literal count:

- `1` = one player;
- `2` = two players.

The parser used by Try 24 only accepts index-style values `0` and `1`; literal `2` becomes invalid. Therefore every real 2P transition was routed into the 1P branch.

## Useful retained finding

The 1P clear must happen before loading-screen state is finalized. However, the complete Try 24 transition hook cannot be retained.

The next approach must:

- return to Try 22 as the functional 2P baseline;
- read the actual current menu setting `mMenuStates@shell_playerCount` instead of the derived runtime value;
- interpret that menu value through `CFlashValue::GetInt()`;
- preserve ordinary stock Kong-partner retention;
- explicitly remove only the replay-created duplicate DK when leaving 2P.

## Build

- Base IPS SHA-256: `b52d3e37fcf4ffe4d14c4cc341461c404943ce1b17e6afe76301a23ba2e4346f`
- Try 24 IPS SHA-256: `4d19b3b1a5405ef621e667650251f21778e65039ebd1045d1a96736109177612`
- Status: discarded after runtime test
