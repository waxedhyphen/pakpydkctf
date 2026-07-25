# Duplicate primary character – CharacterType/PrimaryPlayer-Symbolinventar

| Adresse | Größe | Symbol |
|---:|---:|---|
| `0x001E6E5C` | `0x164` | NGameModeSetup::setup_timeattack_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer*) |
| `0x001E6FC0` | `0x118` | NGameModeSetup::setup_bonus_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer) |
| `0x001E7BA4` | `0xC` | NTimeAttack::get_valid_minor_kong(NPlayerState::EPrimaryPlayer) |
| `0x001E7BB0` | `0x10` | NTimeAttack::get_primary_kong(NPlayerState::EPrimaryPlayer) |
| `0x001E7BC0` | `0x28` | NTimeAttack::get_secondary_kong(NPlayerState::EPrimaryPlayer) |
| `0x001E7D88` | `0x10` | NTimeAttack::get_filter1_value(NPlayerState::EPrimaryPlayer) |
| `0x001F3AEC` | `0x38` | NFlashData::get_character_name(dkcPas::ECharacterType) |
| `0x001F48B4` | `0x28` | NFlashData::get_timeattack_kong(NPlayerState::EPrimaryPlayer) |
| `0x001F9DF0` | `0x2C` | CPlayer::IsPrimaryPlayer() const |
| `0x001FA354` | `0x8` | CPlayer::GetCharacterType() const |
| `0x0020067C` | `0x14` | CPlayer::GetCharacterType(CPlayer const*) |
| `0x00241534` | `0x208` | CPlayerModuleHealth::CanSpawnHUDBarrelMinorKong(CStateManager&, dkcPas::ECharacterType&, NPlayerState::EItemType&, int&) const |
| `0x00242614` | `0x1B4` | CPlayerModuleHealth::ApplyPrimaryPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&) |
| `0x0024F4AC` | `0x78` | CPlayerModuleMount::HasOpenSlotForCharacterType(dkcPas::ECharacterType) const |
| `0x00250FF8` | `0x54` | CPlayerModuleMount::HasRider(dkcPas::ECharacterType) const |
| `0x00251108` | `0x1C` | CPlayerModuleMount::HasRiderInChain(CStateManager const&, dkcPas::ECharacterType) const |
| `0x00251124` | `0xC0` | CPlayerModuleMount::GetRiderInChain(CStateManager const&, dkcPas::ECharacterType) const |
| `0x002511E4` | `0x4` | CPlayerModuleMount::RiderInChain(CStateManager const&, dkcPas::ECharacterType) |
| `0x00251618` | `0x34` | CPlayerModuleMount::GetRiderControllerByCharType(dkcPas::ECharacterType) const |
| `0x00252224` | `0x88` | CPlayerModuleMount::GetDesiredTranslationForCharacter(CStateManager const&, dkcPas::ECharacterType) const |
| `0x00256488` | `0x48` | CPlayerModuleShield::GetPlayerSpecificShieldVisual(CStateManager const&, dkcPas::ECharacterType) |
| `0x0027BDC0` | `0x70` | NPlayerState::character_type_in_bit_field(SLdrPlayerCharactersBitField const&, dkcPas::ECharacterType) |
| `0x0027BE30` | `0x14` | NPlayerState::is_a_primary_kong(NPlayerState::EPrimaryPlayer) |
| `0x0027BE44` | `0x20` | NPlayerState::charType_for_primary_player(NPlayerState::EPrimaryPlayer) |
| `0x0027BE64` | `0x24` | NPlayerState::primary_player_for_charType(dkcPas::ECharacterType) |
| `0x0027C678` | `0x1BC` | NPlayerUtils::CanSpawnPlayer(CStateManager const&, dkcPas::ECharacterType) |
| `0x0027C910` | `0x234` | NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x0027D050` | `0x234` | NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0027D3E4` | `0x4` | NPlayerUtils::NthAlivePrimaryPlayer(CStateManager const&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x00280328` | `0x30` | CAreaState::SetBestTime(float, NPlayerState::EPrimaryPlayer, bool) |
| `0x00280368` | `0x1C` | CAreaState::GetCompletedSuperHardModeWithPrimaryPlayer(NPlayerState::EPrimaryPlayer) const |
| `0x0028038C` | `0x1C` | CAreaState::SetCompletedSuperHardMode(NPlayerState::EPrimaryPlayer) |
| `0x002CDADC` | `0x40` | CStateManagerGameData::GetPrimaryPlayerId(NPlayerState::EPrimaryPlayer) const |
| `0x002CDB1C` | `0x58` | CStateManagerGameData::GetPrimaryPlayer(NPlayerState::EPrimaryPlayer, NPlayerState::EPlayerFlags) const |
| `0x002CDB74` | `0x64` | CStateManagerGameData::IsPrimaryPlayerId(TUniqueId) const |
| `0x002CDBD8` | `0x58` | CStateManagerGameData::PrimaryPlayer(NPlayerState::EPrimaryPlayer, NPlayerState::EPlayerFlags) |
| `0x002CDC30` | `0x78` | CStateManagerGameData::GetPrimaryPlayerByCharacterType(dkcPas::ECharacterType, NPlayerState::EPlayerFlags) const |
| `0x002CDCA8` | `0x78` | CStateManagerGameData::PrimaryPlayerByCharacterType(dkcPas::ECharacterType, NPlayerState::EPlayerFlags) |
| `0x002CDD20` | `0xA0` | CStateManagerGameData::GetFirstAlivePrimaryPlayer() const |
| `0x002CDDC0` | `0xA0` | CStateManagerGameData::FirstAlivePrimaryPlayer() |
| `0x002CDE60` | `0xB4` | CStateManagerGameData::GetFirstAlivePrimaryPlayerId() const |
| `0x002CDF14` | `0x228` | CStateManagerGameData::GetClosestPrimaryPlayer(CStateManager const&, NPlayerState::EPlayerFlags, CVector3f const&) const |
| `0x002CE13C` | `0x50` | CStateManagerGameData::SetPrimaryPlayer(CPlayer&) |
| `0x002CE18C` | `0x2C` | CStateManagerGameData::ClearPrimaryPlayer(dkcPas::ECharacterType) |
| `0x002CE1B8` | `0x8` | CStateManagerGameData::SetLastDeadPrimaryPlayer(dkcPas::ECharacterType) |
| `0x002CE1C0` | `0x8` | CStateManagerGameData::GetLastDeadPrimaryPlayer() const |
| `0x003376BC` | `0x28` | CGameState::GetPlayerIndexByCharacterType(dkcPas::ECharacterType) const |
| `0x0033841C` | `0xBC` | CGlobalAreaState::SetBestUploadedInformationIfBetter(float, NPlayerState::EPrimaryPlayer, bool, bool, unsigned char, bool) |
| `0x003409D8` | `0x138` | CMapManager::SendAddedOrChangedPlayerMessage(CStateManager&, dkcPas::ECharacterType, dkcPas::ECharacterType) |
| `0x00340B10` | `0xA4` | CMapManager::SendDroppedPlayerMessage(CStateManager&, dkcPas::ECharacterType) |
| `0x00341ABC` | `0x88` | CMapManager::PlayStartLevelSounds(CStateManager const&, NFlashData::EGameModeTypes, NPlayerState::EPrimaryPlayer, NPlayerState::EPrimaryPlayer) const |
| `0x00344DB4` | `0xB8` | CMenuIOWin::PostTimeAttackPrompt(CMenuIOWin::ETimeAttackPrompt, int, rstl::basic_string<char, rstl::char_traits<char>, rstl::rmemory_allocator> const&, NPlayerState::EPrimaryPlayer, bool, bool) |
| `0x00345210` | `0x198` | CMenuIOWin::PostBestTimeWithoutQuery(int, NPlayerState::EPrimaryPlayer, bool, bool) |
| `0x003457A8` | `0x2A0` | CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00352AA0` | `0x288` | CProductionFrontEnd::InitLevelTransition(CObjectId const&, NFlashData::EGameModeTypes, NPlayerState::EPrimaryPlayer) |
| `0x00353158` | `0x94` | CProductionFrontEnd::PlayStartLevelSounds(NFlashData::EGameModeTypes, NPlayerState::EPrimaryPlayer) |
| `0x003590B8` | `0x80` | CProductionFrontEnd::CompleteHard(NPlayerState::EPrimaryPlayer) |
| `0x0035ABB0` | `0x3A4` | CProductionLoadingScreen::BuildRollingScene(CUniverseInfo::ELoadDirection, IObjectStore&, dkcPas::ECharacterType, dkcPas::ECharacterType, CProductionLoadingScreen::EShieldState, CProductionLoadingScreen::EShieldState) |
| `0x0035AF54` | `0x3A8` | CProductionLoadingScreen::BuildRunningScene(CUniverseInfo::ELoadDirection, IObjectStore&, dkcPas::ECharacterType, dkcPas::ECharacterType, CProductionLoadingScreen::EShieldState, CProductionLoadingScreen::EShieldState) |
| `0x0035FADC` | `0x6F8` | CSCAIOWin::SetupSCAObject(IObjectStore&, CPlayer const&, dkcPas::ECharacterType) const |
| `0x0036B3C0` | `0x48` | CTimeAttackGameMode::CTimeAttackGameMode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer) |
| `0x0036B3C0` | `0x48` | CTimeAttackGameMode::CTimeAttackGameMode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer) |
| `0x0036B454` | `0x68` | CTimeAttackGameMode::CTimeAttackGameMode(CGameState&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer&) |
| `0x0036B454` | `0x68` | CTimeAttackGameMode::CTimeAttackGameMode(CGameState&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer&) |
| `0x003A1020` | `0x2C` | CBaboonGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x003CB0FC` | `0x20` | CCreatureGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x003D1114` | `0x84` | CDialogPanelGOC::SetPortrait(CStateManager const&, dkcPas::ECharacterType) |
| `0x003F1BA0` | `0x10` | CHUDAnchorGOC::SetPortrait(CStateManager&, dkcPas::ECharacterType) |
| `0x003F1D34` | `0x1C` | CHUDAnchorGOC::AllocatePortrait(CHUDIOWin*, dkcPas::ECharacterType) |
| `0x003FD864` | `0xCC` | CMapManagerProxyGOC::SendAddedPlayerMessage(CStateManager&, CTransform4f const&, dkcPas::ECharacterType, dkcPas::ECharacterType) |
| `0x003FD930` | `0x80` | CMapManagerProxyGOC::SendDroppedPlayerMessage(CStateManager&, CTransform4f const&, dkcPas::ECharacterType) |
| `0x003FD9B0` | `0xCC` | CMapManagerProxyGOC::SendChangedPrimaryPlayerMessage(CStateManager&, CTransform4f const&, dkcPas::ECharacterType, dkcPas::ECharacterType) |
| `0x00400FA4` | `0x64` | CMapNodeGOC::CompleteHard(CStateManager&, NPlayerState::EPrimaryPlayer) |
| `0x004097D8` | `0x24` | CMapPlayerGOC::GetCharacterType() const |
| `0x00414D28` | `0x2C` | COwlGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x0042C508` | `0x2C` | CPolarBearGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x00436BE0` | `0x2C` | CPufferFishGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x0044EB68` | `0x20` | CSeaLionGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x0047297C` | `0x2C` | CWarusKingGOC::NotifyScriptEventKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x005341EC` | `0x1B4` | CActorModuleHealth::ConnectKilledByPlayerType(TFunctor2<CStateManager&, dkcPas::ECharacterType const> const&) |
| `0x00534B54` | `0x74` | CActorModuleHealth::NotifyKilledByPlayerType(CStateManager&, dkcPas::ECharacterType) |
| `0x00582EDC` | `0x7C` | CActorModuleBehaviorFollowSurface::UpdateCharacterTypes(CCollisionMaterial const&) |
