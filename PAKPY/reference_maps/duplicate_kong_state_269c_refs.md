# Duplicate Kong – state+0x269C Referenzen

| Adresse | Operation | Funktion |
|---:|---|---|
| `0x001E6ED0` | `STR W` | `0x001E6E5C+0x74` – NGameModeSetup::setup_timeattack_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer*) |
| `0x001E700C` | `STR W` | `0x001E6FC0+0x4C` – NGameModeSetup::setup_bonus_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer) |
| `0x001F39E0` | `LDR W` | `0x001F3978+0x68` – NFlashData::init_player_info(CFlashMovieInstanceManager&, CGameState const&) |
| `0x001F3B8C` | `LDR W` | `0x001F3B24+0x68` – NFlashData::set_player_character_info(CFlashDataModel&, CGameState const&) |
| `0x001F4B50` | `LDR W` | `0x001F48DC+0x274` – NFlashData::init_slot_info(CFlashDataModel&, CGameState const*, int) |
| `0x001FB1C8` | `LDR W` | `0x001FB0C8+0x100` – CPlayer::GetHealthItemForCurrentState(CStateManager const&, NPlayerState::EItemType) const |
| `0x00200610` | `LDR W` | `0x0020057C+0x94` – CPlayer::GetMultiplayerState(CStateManager const&) const |
| `0x002410B8` | `STR W` | `0x00240F0C+0x1AC` – CPlayerModuleHealth::CheckAndSpawnHUDBarrelMinorKong(CStateManager&, float) |
| `0x002422D8` | `LDR W` | `0x00242198+0x140` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x00242590` | `LDR W` | `0x002424E4+0xAC` – CPlayerModuleHealth::StartDamageRumble(CStateManager&) const |
| `0x00242FA8` | `LDR W` | `0x00242ED8+0xD0` – CPlayerModuleHealth::SplitDamageBetweenPlayers(CStateManager const&, NDamageType::EDamageType, int, int&, int&) |
| `0x0024BF3C` | `LDR W` | `0x0024BD88+0x1B4` – CPlayerModuleMelee::SetMeleeApplied(CStateManager&, CEntityGOC const&) |
| `0x00251B9C` | `LDR W` | `0x00251B58+0x44` – CPlayerModuleMount::CheckAndConsumeCrashGuard(CStateManager&) |
| `0x0027CC24` | `LDR W` | `0x0027CB6C+0xB8` – NPlayerUtils::HealAlivePlayers(CStateManager&) |
| `0x0027D16C` | `LDR W` | `0x0027D050+0x11C` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0027D1B8` | `LDR W` | `0x0027D050+0x168` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0027D210` | `LDR W` | `0x0027D050+0x1C0` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x00293290` | `LDR W` | `0x002931E0+0xB0` – CBonusRoomGOC::OnAction_ExitBonusRoom(CStateManager&, CScriptMsg const&) |
| `0x002946E4` | `LDR W` | `0x002946C4+0x20` – CBonusRoomGOC::MountPlayers(CStateManager&) |
| `0x002AF0FC` | `LDR W` | `0x002AF010+0xEC` – CSquawksGOC::UpdateFade(CStateManager&) |
| `0x002CD29C` | `LDR W` | `0x002CD1B4+0xE8` – CStateManagerGameData::CStateManagerGameData(CStateManager&) |
| `0x00334838` | `STR W` | `0x00333FA4+0x894` – CGameState::CGameState(CInputBitStream&, rstl::rc_ptr<CUniverseInfo> const&) |
| `0x00335784` | `LDR W` | `0x0033562C+0x158` – CGameState::PutTo(COutputBitStream&) const |
| `0x003376D0` | `LDR W` | `0x003376BC+0x14` – CGameState::GetPlayerIndexByCharacterType(dkcPas::ECharacterType) const |
| `0x0033B660` | `LDR W` | `0x0033B464+0x1FC` – CHUDIOWin::AreaLoaded() |
| `0x0033BB20` | `LDR W` | `0x0033B464+0x6BC` – CHUDIOWin::AreaLoaded() |
| `0x0033BD88` | `LDR W` | `0x0033BD64+0x24` – CHUDIOWin::SpawnSecondPlayer(CStateManager&) |
| `0x0033C180` | `LDR W` | `0x0033C164+0x1C` – CHUDIOWin::SecondaryInWaterStateChange(CStateManager&, CWaterVolumeDataWrapper const&, bool) |
| `0x0033C248` | `LDR W` | UNAUFGELÖST |
| `0x0033CCAC` | `LDR W` | `0x0033CB1C+0x190` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033CEA4` | `LDR W` | `0x0033CB1C+0x388` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033E3B0` | `LDR W` | `0x0033DFF4+0x3BC` – CHUDIOWin::FillDataDictionary(char const*) |
| `0x00345870` | `LDR W` | `0x003457A8+0xC8` – CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0034588C` | `STR W` | `0x003457A8+0xE4` – CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0034591C` | `STR W` | `0x003457A8+0x174` – CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00345934` | `LDR W` | `0x003457A8+0x18C` – CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x003459FC` | `LDR W` | `0x003457A8+0x254` – CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0034D0E0` | `LDR W` | `0x0034CBCC+0x514` – CSuperGuide::CSuperGuide(CGameState&, CObjectId const&, CFourCC) |
| `0x0034E020` | `STR W` | `0x0034DCC4+0x35C` – CSuperGuide::ReadHeader(CGameState&, unsigned char) |
| `0x0034FBA8` | `STR W` | `0x0034FB64+0x44` – CProductionFrontEnd::SetupInitialGameState() |
| `0x00351408` | `LDR W` | `0x003512B8+0x150` – CProductionFrontEnd::FillDataDictionary(char const*) |
| `0x00352358` | `STR W` | `0x0035201C+0x33C` – CProductionFrontEnd::InitGameTransition(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00352410` | `STR W` | `0x0035201C+0x3F4` – CProductionFrontEnd::InitGameTransition(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00352CA0` | `STR W` | `0x00352AA0+0x200` – CProductionFrontEnd::InitLevelTransition(CObjectId const&, NFlashData::EGameModeTypes, NPlayerState::EPrimaryPlayer) |
| `0x00354A78` | `LDR W` | `0x003549C4+0xB4` – CProductionFrontEnd::PopulateSaveData(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00354DC8` | `LDR W` | `0x00354CF8+0xD0` – CProductionFrontEnd::InitSlotData(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0035A69C` | `LDR W` | `0x0035A178+0x524` – CProductionLoadingScreen::ShowLoadingScreen(CUniverseInfo::ELoadDirection, CGameStateManager* const&, CArchitectureQueue&, IObjectStore&, CResourceFactory*) |
| `0x0035EF38` | `LDR W` | `0x0035EBF8+0x340` – CSCAIOWin::TimerTick(float) |
| `0x0035F3B4` | `LDR W` | `0x0035F310+0xA4` – CSCAIOWin::SetupSCAObjects(IObjectStore&) |
| `0x0035FAA8` | `LDR W` | `0x0035FA7C+0x2C` – CSCAIOWin::GetMinorKongPresent() const |
| `0x0035FFB4` | `LDR W` | `0x0035FADC+0x4D8` – CSCAIOWin::SetupSCAObject(IObjectStore&, CPlayer const&, dkcPas::ECharacterType) const |
| `0x00391380` | `LDR W` | `0x0039131C+0x64` – CActionDetectorGOC::AreaLoaded(CStateManager&) |
| `0x003A4138` | `LDR W` | `0x003A3F90+0x1A8` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A41B4` | `LDR W` | `0x003A3F90+0x224` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4230` | `LDR W` | `0x003A3F90+0x2A0` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A465C` | `LDR W` | `0x003A4614+0x48` – CBaboonManagerGOC::TryGetTargetIndex(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x003A5680` | `LDR W` | `0x003A55A8+0xD8` – CBaboonManagerGOC::VineSwingTryActivateSupportBaboon(CStateManager&, NBaboon::ESide&) |
| `0x003A57F0` | `LDR W` | `0x003A5738+0xB8` – CBaboonManagerGOC::VineSwingSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5A20` | `LDR W` | `0x003A5948+0xD8` – CBaboonManagerGOC::MultiRollTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5BA4` | `LDR W` | `0x003A5AE8+0xBC` – CBaboonManagerGOC::MultiRollSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5DE0` | `LDR W` | `0x003A5D08+0xD8` – CBaboonManagerGOC::BombTossTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5F24` | `LDR W` | `0x003A5E68+0xBC` – CBaboonManagerGOC::BombTossSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A6160` | `LDR W` | `0x003A6088+0xD8` – CBaboonManagerGOC::DropJumpTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A62A4` | `LDR W` | `0x003A61E8+0xBC` – CBaboonManagerGOC::DropJumpSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A71F8` | `LDR W` | `0x003A7188+0x70` – CBaboonManagerGOC::RefreshTarget(CStateManager const&, int) |
| `0x003A7364` | `LDR W` | `0x003A72D0+0x94` – CBaboonManagerGOC::FindClosestPlayerIndex(CStateManager const&, CVector3f const&) const |
| `0x003A8048` | `LDR W` | `0x003A7F84+0xC4` – CBaboonManagerGOC::BombSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A8214` | `LDR W` | `0x003A8140+0xD4` – CBaboonManagerGOC::MultiSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A9610` | `LDR W` | `0x003A9568+0xA8` – CBaboonManagerGOC::MultiSwingUpdateIsPlayerHiding(CStateManager&) |
| `0x003A9960` | `LDR W` | `0x003A97A4+0x1BC` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A9BC8` | `LDR W` | `0x003A9B04+0xC4` – CBaboonManagerGOC::MultiSwingSetupNinja(CStateManager&, CVector3f&) |
| `0x003AA484` | `LDR W` | `0x003AA3BC+0xC8` – CBaboonManagerGOC::RollJumpSetupClone(CStateManager&, int) |
| `0x003AAF74` | `LDR W` | `0x003AAE68+0x10C` – CBaboonManagerGOC::BombSwingSetup(CStateManager&) |
| `0x003AB660` | `LDR W` | `0x003AB5B4+0xAC` – CBaboonManagerGOC::MultiSwingSetupBaboon(CStateManager&, int, float, NBaboon::ESide, NBaboonPasDefs::EMultiSwingPosition) |
| `0x003AF304` | `LDR W` | `0x003AF270+0x94` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003AF360` | `LDR W` | `0x003AF270+0xF0` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003B3E1C` | `LDR W` | `0x003B3DAC+0x70` – CBreathMonitorGOC::GetEventIndexForBreath(CStateManager&) |
| `0x003BCF04` | `LDR W` | `0x003BCE60+0xA4` – CCheckpointGOC::Think(CStateManager&, float) |
| `0x003BD180` | `LDR W` | `0x003BD010+0x170` – CCheckpointGOC::SpawnPlayer(CStateManager&) |
| `0x003D0FAC` | `LDR W` | `0x003D0E90+0x11C` – CDialogPanelGOC::FlashInitBubble(CStateManager const&) |
| `0x003E8C04` | `LDR W` | `0x003E8B68+0x9C` – CGrabThrowGOC::UpdateInhabitant(CStateManager&) |
| `0x003E9964` | `LDR W` | `0x003E98F0+0x74` – CGrabThrowGOC::UpdateDesiredInhabitant(CStateManager const&) |
| `0x003F1704` | `LDR W` | `0x003F16A0+0x64` – CHUDAnchorGOC::EntityLoaded(CStateManager&, CGameObjectComponent::SEntityLoadedInfo const&) |
| `0x003F1858` | `LDR W` | `0x003F1814+0x44` – CHUDAnchorGOC::PortraitFromType(CStateManager const&, NHUDAnchor::EHUDAnchor) |
| `0x003F19E4` | `LDR W` | `0x003F1860+0x184` – CHUDAnchorGOC::Think(CStateManager&, float) |
| `0x003F1CC8` | `LDR W` | `0x003F1C68+0x60` – CHUDAnchorGOC::AllocateVisual(CStateManager&) |
| `0x0040F448` | `LDR W` | `0x0040F37C+0xCC` – CNearVisibleGOC::CheckForPlayerInBounds(CStateManager const&, CAABox const&) |
| `0x0041AD64` | `LDR W` | `0x0041AAD8+0x28C` – CPickupGOC::StartSpawnSequence(CStateManager&, TUniqueId, CPickupGOC::EIsForcePickup) |
| `0x0041DAF4` | `LDR W` | `0x0041D81C+0x2D8` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041FA70` | `LDR W` | `0x0041F9AC+0xC4` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FB0C` | `LDR W` | `0x0041F9AC+0x160` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x004274D0` | `LDR W` | `0x004273E0+0xF0` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |
| `0x00438FF0` | `LDR W` | `0x00438ED4+0x11C` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x0043902C` | `LDR W` | `0x00438ED4+0x158` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x004390EC` | `LDR W` | `0x0043907C+0x70` – CConditionalTest::IsPlayerItemIndeterminate(CStateManager const&) const |
| `0x0043916C` | `LDR W` | `0x0043911C+0x50` – CConditionalTest::GetPlayerItemValue(CStateManager const&) const |
| `0x00439210` | `LDR W` | `0x004391C0+0x50` – CConditionalTest::GetPlayerItemMaxValue(CStateManager const&) const |
| `0x00440E24` | `LDR W` | `0x00440C9C+0x188` – CRespawnBalloonGOC::Think(CStateManager&, float) |
| `0x00441124` | `LDR W` | `0x00440EC8+0x25C` – CRespawnBalloonGOC::GrabPlayersAndStart(CStateManager&, float) |
| `0x004416B4` | `LDR W` | `0x00441644+0x70` – CRespawnBalloonGOC::ToggleControls(CStateManager&, bool) |
| `0x00441740` | `LDR W` | `0x00441644+0xFC` – CRespawnBalloonGOC::ToggleControls(CStateManager&, bool) |
| `0x0044A1EC` | `LDR W` | `0x0044A0CC+0x120` – CRumbleEffectGOC::OnAction_Rumble(CStateManager&, CScriptMsg const&) |
| `0x0044B558` | `LDR W` | `0x0044B4E4+0x74` – CRumbleEffectGOC::RumbleRiders(CStateManager&, CPlayer const&, TUniqueId) |
| `0x004D2E3C` | `LDR W` | `0x004D2D88+0xB4` – CTargetOrientationSplineControl::Update(CStateManager&, CSplineMotionGOC const&, float) |
| `0x004E6C40` | `LDR W` | `0x004E6B90+0xB0` – CProjectileMotionTargetedPhysics::Init(CProjectileGOC const&, CStateManager&) |
| `0x005456B4` | `LDR W` | `0x00545620+0x94` – CActorModulePolarBearController::AllTargetsBehind(CStateManager const&, float) const |
