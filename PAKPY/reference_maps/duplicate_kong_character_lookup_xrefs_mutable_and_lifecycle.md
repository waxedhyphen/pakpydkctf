# Duplicate Kong – mutable CharacterType-Lookups und Lifecycle

### `002CDCA8` – CStateManagerGameData::PrimaryPlayerByCharacterType(dkcPas::ECharacterType, NPlayerState::EPlayerFlags)

Direkte Referenzen: **44**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x001FA5B0` | `BL` | `0x001FA49C+0x114` – CPlayer::RespawnToLocation(CStateManager&, CTransform4f const&, NPlayerState::EResetContext, CPlayer::EPlayRespawnEffects) |
| `0x0021E8E8` | `BL` | `0x0021E824+0xC4` – CPlayerModuleBarrelCannon::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00241078` | `BL` | `0x00240F0C+0x16C` – CPlayerModuleHealth::CheckAndSpawnHUDBarrelMinorKong(CStateManager&, float) |
| `0x00242708` | `BL` | `0x00242614+0xF4` – CPlayerModuleHealth::ApplyPrimaryPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&) |
| `0x00256994` | `BL` | `0x00256954+0x40` – CPlayerModuleSlave::PreOwnerAreaLoaded(CStateManager&) |
| `0x0026949C` | `BL` | `0x00269444+0x58` – CPlayerModuleSwimmingPropeller::SetPropellerState(CStateManager&, CPlayerModuleSwimmingPropeller::EPropellerState) |
| `0x00269810` | `BL` | `0x002697EC+0x24` – CPlayerModuleSwimmingPropeller::StopPropellerAnimation(CStateManager&) |
| `0x0026987C` | `BL` | `0x0026984C+0x30` – CPlayerModuleSwimmingPropeller::StartPropellerAnimation(CStateManager&) |
| `0x002699C8` | `B` | `0x002699B4+0x14` – CPlayerModuleSwimmingPropeller::PropellerOwnerPlayer(CStateManager&) const |
| `0x0027C974` | `BL` | `0x0027C910+0x64` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x0027C9B0` | `BL` | `0x0027C910+0xA0` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x0027CC00` | `BL` | `0x0027CB6C+0x94` – NPlayerUtils::HealAlivePlayers(CStateManager&) |
| `0x0027CC30` | `BL` | `0x0027CB6C+0xC4` – NPlayerUtils::HealAlivePlayers(CStateManager&) |
| `0x0027D0C8` | `BL` | `0x0027D050+0x78` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0027D178` | `BL` | `0x0027D050+0x128` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0027D1C4` | `BL` | `0x0027D050+0x174` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0027D21C` | `BL` | `0x0027D050+0x1CC` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x002932A8` | `BL` | `0x002931E0+0xC8` – CBonusRoomGOC::OnAction_ExitBonusRoom(CStateManager&, CScriptMsg const&) |
| `0x00293380` | `BL` | `0x002931E0+0x1A0` – CBonusRoomGOC::OnAction_ExitBonusRoom(CStateManager&, CScriptMsg const&) |
| `0x00294708` | `BL` | `0x002946C4+0x44` – CBonusRoomGOC::MountPlayers(CStateManager&) |
| `0x00294734` | `BL` | `0x002946C4+0x70` – CBonusRoomGOC::MountPlayers(CStateManager&) |
| `0x00294754` | `BL` | `0x002946C4+0x90` – CBonusRoomGOC::MountPlayers(CStateManager&) |
| `0x0035EE34` | `BL` | `0x0035EBF8+0x23C` – CSCAIOWin::TimerTick(float) |
| `0x0035EF4C` | `BL` | `0x0035EBF8+0x354` – CSCAIOWin::TimerTick(float) |
| `0x0035FFC8` | `BL` | `0x0035FADC+0x4EC` – CSCAIOWin::SetupSCAObject(IObjectStore&, CPlayer const&, dkcPas::ECharacterType) const |
| `0x003AD928` | `BL` | `0x003AD8A4+0x84` – CBarrelBalloonGOC::PopBalloon(CStateManager&) |
| `0x003BD0E8` | `BL` | `0x003BD010+0xD8` – CCheckpointGOC::SpawnPlayer(CStateManager&) |
| `0x003BD18C` | `BL` | `0x003BD010+0x17C` – CCheckpointGOC::SpawnPlayer(CStateManager&) |
| `0x003BD390` | `BL` | `0x003BD31C+0x74` – CCheckpointGOC::FinishRespawn(CStateManager&) |
| `0x003BD3CC` | `BL` | `0x003BD31C+0xB0` – CCheckpointGOC::FinishRespawn(CStateManager&) |
| `0x0041FA48` | `BL` | `0x0041F9AC+0x9C` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FA84` | `BL` | `0x0041F9AC+0xD8` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FAC8` | `BL` | `0x0041F9AC+0x11C` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FB18` | `BL` | `0x0041F9AC+0x16C` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FC88` | `B` | `0x0041FC64+0x24` – CPlayerKeyframeGOC::PlayerFromIndex(CStateManager&, NPlayerState::EPlayerIndex) |
| `0x00440DF0` | `BL` | `0x00440C9C+0x154` – CRespawnBalloonGOC::Think(CStateManager&, float) |
| `0x00440E30` | `BL` | `0x00440C9C+0x194` – CRespawnBalloonGOC::Think(CStateManager&, float) |
| `0x004410C0` | `BL` | `0x00440EC8+0x1F8` – CRespawnBalloonGOC::GrabPlayersAndStart(CStateManager&, float) |
| `0x00441130` | `BL` | `0x00440EC8+0x268` – CRespawnBalloonGOC::GrabPlayersAndStart(CStateManager&, float) |
| `0x00441688` | `BL` | `0x00441644+0x44` – CRespawnBalloonGOC::ToggleControls(CStateManager&, bool) |
| `0x004416C0` | `BL` | `0x00441644+0x7C` – CRespawnBalloonGOC::ToggleControls(CStateManager&, bool) |
| `0x0044174C` | `BL` | `0x00441644+0x108` – CRespawnBalloonGOC::ToggleControls(CStateManager&, bool) |
| `0x0045B850` | `BL` | `0x0045B74C+0x104` – CSpawnPointGOC::DoSpawn(CStateManager&) |
| `0x004F0E54` | `BL` | `0x004F0774+0x6E0` – CImpostorManager::AddPlayerImpostor(CStateManager&, CImpostorGOC&) |

### `002CE13C` – CStateManagerGameData::SetPrimaryPlayer(CPlayer&)

Direkte Referenzen: **1**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x001F8430` | `B` | `0x001F8388+0xA8` – CPlayer::EntityLoaded(CStateManager&) |

### `002CE18C` – CStateManagerGameData::ClearPrimaryPlayer(dkcPas::ECharacterType)

Direkte Referenzen: **1**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x001F8BC0` | `BL` | `0x001F8B60+0x60` – CPlayer::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |

### `0027BDC0` – NPlayerState::character_type_in_bit_field(SLdrPlayerCharactersBitField const&, dkcPas::ECharacterType)

Direkte Referenzen: **17**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x0024F378` | `BL` | `0x0024F29C+0xDC` – CPlayerModuleMount::CanGrabRider(CStateManager const&, CPlayer const&) const |
| `0x0024F620` | `B` | `0x0024F524+0xFC` – CPlayerModuleMount::CanBeGrabbedByRider(CStateManager const&, CPlayer const&) const |
| `0x0024F660` | `B` | `0x0024F638+0x28` – CPlayerModuleMount::CanGrabMount(CPlayer const&) const |
| `0x0025109C` | `BL` | `0x0025104C+0x50` – CPlayerModuleMount::HasRiderInChain_BitField(CStateManager const&, SLdrPlayerCharactersBitField const&) const |
| `0x00257B0C` | `B` | `0x00257A88+0x84` – CPlayerModuleSlave::HasTransitionAnimations(CStateManager&, CFSMProperties const&) const |
| `0x00258AB0` | `BL` | `0x002587C0+0x2F0` – CPlayerModuleSlave::EnterSlaveMode(CStateManager&, CMasterSlaveGOC&, unsigned int) |
| `0x00417358` | `BL` | `0x004172DC+0x7C` – CPlayerActionDetectorGOC::CheckBoundsAndQueueMessages(CStateManager&, TUniqueId, NScriptMsg::EScriptEvent, NScriptMsg::EScriptEvent) |
| `0x004174F8` | `BL` | `0x004174D8+0x20` – CPlayerActionDetectorGOC::CheckPlayerType(CPlayer const*) const |
| `0x00420998` | `BL` | `0x00420568+0x430` – CPlayerProxyGOC::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |
| `0x00421484` | `BL` | `0x00421450+0x34` – CPlayerProxyGOC::OnAction_QueryIsP1(CStateManager&, CScriptMsg const&) |
| `0x004220B0` | `BL` | `0x00422068+0x48` – CPlayerProxyGOC::NotifyPlayerDamaged(CStateManager&, TUniqueId) |
| `0x004222D0` | `BL` | `0x00422218+0xB8` – CPlayerProxyGOC::ForEachProxyPlayer(CStateManager&, void (CPlayerProxyGOC::*)(CStateManager&, CPlayer*), TUniqueId) |
| `0x00422310` | `BL` | `0x00422218+0xF8` – CPlayerProxyGOC::ForEachProxyPlayer(CStateManager&, void (CPlayerProxyGOC::*)(CStateManager&, CPlayer*), TUniqueId) |
| `0x00422764` | `BL` | `0x004226F4+0x70` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x00422790` | `BL` | `0x004226F4+0x9C` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x004227F8` | `BL` | `0x004226F4+0x104` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x00422824` | `BL` | `0x004226F4+0x130` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |

### `0027BE30` – NPlayerState::is_a_primary_kong(NPlayerState::EPrimaryPlayer)

Direkte Referenzen: **1**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x001E7BD0` | `BL` | `0x001E7BC0+0x10` – NTimeAttack::get_secondary_kong(NPlayerState::EPrimaryPlayer) |

### `0027BE44` – NPlayerState::charType_for_primary_player(NPlayerState::EPrimaryPlayer)

Direkte Referenzen: **3**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x001E6EA4` | `BL` | `0x001E6E5C+0x48` – NGameModeSetup::setup_timeattack_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer*) |
| `0x001E6EB8` | `BL` | `0x001E6E5C+0x5C` – NGameModeSetup::setup_timeattack_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer*) |
| `0x001E6FF8` | `BL` | `0x001E6FC0+0x38` – NGameModeSetup::setup_bonus_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer) |

### `0027BE64` – NPlayerState::primary_player_for_charType(dkcPas::ECharacterType)

Direkte Referenzen: **1**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x00367764` | `BL` | `0x003676E4+0x80` – CBonusGameMode::PrepareForEOLSave(CStateManager&) |

### `0027C678` – NPlayerUtils::CanSpawnPlayer(CStateManager const&, dkcPas::ECharacterType)

Direkte Referenzen: **5**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x00241638` | `BL` | `0x00241534+0x104` – CPlayerModuleHealth::CanSpawnHUDBarrelMinorKong(CStateManager&, dkcPas::ECharacterType&, NPlayerState::EItemType&, int&) const |
| `0x0027C960` | `BL` | `0x0027C910+0x50` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x003E8C10` | `BL` | `0x003E8B68+0xA8` – CGrabThrowGOC::UpdateInhabitant(CStateManager&) |
| `0x003E8C60` | `BL` | `0x003E8B68+0xF8` – CGrabThrowGOC::UpdateInhabitant(CStateManager&) |
| `0x003E9970` | `BL` | `0x003E98F0+0x80` – CGrabThrowGOC::UpdateDesiredInhabitant(CStateManager const&) |

### `0027C910` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType)

Direkte Referenzen: **1**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x003E9BD8` | `BL` | `0x003E9ADC+0xFC` – CGrabThrowGOC::HandlePreDeathEvents(CStateManager&, CGrabThrowGOC::ESpawnEffects, TUniqueId) |

### `003BD010` – CCheckpointGOC::SpawnPlayer(CStateManager&)

Direkte Referenzen: **1**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x00425AF8` | `BL` | `0x004255C0+0x538` – CPlayerRespawnGOC::Think(CStateManager&, float) |

### `003BD31C` – CCheckpointGOC::FinishRespawn(CStateManager&)

Direkte Referenzen: **0**

Keine direkten `B`/`BL`-Referenzen gefunden.

### `001F8388` – CPlayer::EntityLoaded(CStateManager&)

Direkte Referenzen: **0**

Keine direkten `B`/`BL`-Referenzen gefunden.

### `001F8B60` – CPlayer::AcceptScriptMsg(CStateManager&, CScriptMsg const&)

Direkte Referenzen: **0**

Keine direkten `B`/`BL`-Referenzen gefunden.
