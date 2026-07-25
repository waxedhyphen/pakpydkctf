# Duplicate primary character – direkte GameState-Feldzugriffe

| Adresse | Operation | Funktion |
|---:|---|---|
| `0x001C0AFC` | `LDR W` | `0x001C0A54+0xA8` – CGraphicalTransition::ActivateTransitionType(NGraphicalTransition::ETransitionType) |
| `0x001E6ECC` | `STR W` | `0x001E6E5C+0x70` – NGameModeSetup::setup_timeattack_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer, CTimeAttackReplayBuffer*) |
| `0x001E7008` | `STR W` | `0x001E6FC0+0x48` – NGameModeSetup::setup_bonus_gamemode(CGameState&, CObjectId const&, NPlayerState::EPrimaryPlayer) |
| `0x001E7104` | `STR W` | `0x001E70D8+0x2C` – NGameModeSetup::setup_gauntlet_gamemode(CGameState&, CObjectId const&) |
| `0x001F3990` | `LDR W` | `0x001F3978+0x18` – NFlashData::init_player_info(CFlashMovieInstanceManager&, CGameState const&) |
| `0x001F3B3C` | `LDR W` | `0x001F3B24+0x18` – NFlashData::set_player_character_info(CFlashDataModel&, CGameState const&) |
| `0x001F4B18` | `LDR W` | `0x001F48DC+0x23C` – NFlashData::init_slot_info(CFlashDataModel&, CGameState const*, int) |
| `0x001FB1C4` | `LDR W` | `0x001FB0C8+0xFC` – CPlayer::GetHealthItemForCurrentState(CStateManager const&, NPlayerState::EItemType) const |
| `0x001FB560` | `LDR W` | `0x001FB354+0x20C` – CPlayer::ShouldPickupItem(CStateManager const&, NPlayerState::EItemType) const |
| `0x002005B4` | `LDR W` | `0x0020057C+0x38` – CPlayer::GetMultiplayerState(CStateManager const&) const |
| `0x0021E8D4` | `LDR W` | `0x0021E824+0xB0` – CPlayerModuleBarrelCannon::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00220C00` | `LDR W` | `0x00220B54+0xAC` – CPlayerModuleBarrelCannon::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x002422AC` | `LDR W` | `0x00242198+0x114` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x00242528` | `LDR W` | `0x002424E4+0x44` – CPlayerModuleHealth::StartDamageRumble(CStateManager&) const |
| `0x002426F4` | `LDR W` | `0x00242614+0xE0` – CPlayerModuleHealth::ApplyPrimaryPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&) |
| `0x00242F70` | `LDR W` | `0x00242ED8+0x98` – CPlayerModuleHealth::SplitDamageBetweenPlayers(CStateManager const&, NDamageType::EDamageType, int, int&, int&) |
| `0x0024BEE8` | `LDR W` | `0x0024BD88+0x160` – CPlayerModuleMelee::SetMeleeApplied(CStateManager&, CEntityGOC const&) |
| `0x00251B84` | `LDR W` | `0x00251B58+0x2C` – CPlayerModuleMount::CheckAndConsumeCrashGuard(CStateManager&) |
| `0x00256400` | `LDR W` | `0x002563E0+0x20` – CPlayerModuleShield::GetOtherShieldModuleInMountChain(CStateManager const&, CPlayer const&, NPlayerState::EPlayerIndex) const |
| `0x0027BEE0` | `LDR W` | `0x0027BED0+0x10` – NPlayerState::get_default_starting_character_HP(CGameState const&, NPlayerState::EPlayerIndex) |
| `0x0027C9A4` | `LDR W` | `0x0027C910+0x94` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x0027C9EC` | `STR W` | `0x0027C910+0xDC` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x0027CBF4` | `LDR W` | `0x0027CB6C+0x88` – NPlayerUtils::HealAlivePlayers(CStateManager&) |
| `0x0027D0BC` | `LDR W` | `0x0027D050+0x6C` – NPlayerUtils::NthAlivePrimaryPlayer(CStateManager&, NPlayerState::EPlayerIndex, NPlayerUtils::ECheckBonusRoomState, NPlayerUtils::EAllowPotentiallyAlive) |
| `0x0029329C` | `LDR W` | `0x002931E0+0xBC` – CBonusRoomGOC::OnAction_ExitBonusRoom(CStateManager&, CScriptMsg const&) |
| `0x002946E0` | `LDR W` | `0x002946C4+0x1C` – CBonusRoomGOC::MountPlayers(CStateManager&) |
| `0x002AF058` | `LDR W` | `0x002AF010+0x48` – CSquawksGOC::UpdateFade(CStateManager&) |
| `0x00333E80` | `STR X` | `0x003338D0+0x5B0` – CGameState::CGameState(rstl::auto_ptr<IGameMode> const&, rstl::rc_ptr<CUniverseInfo> const&) |
| `0x003345BC` | `STR X` | `0x00333FA4+0x618` – CGameState::CGameState(CInputBitStream&, rstl::rc_ptr<CUniverseInfo> const&) |
| `0x003347C4` | `STR W` | `0x00333FA4+0x820` – CGameState::CGameState(CInputBitStream&, rstl::rc_ptr<CUniverseInfo> const&) |
| `0x00335758` | `LDR W` | `0x0033562C+0x12C` – CGameState::PutTo(COutputBitStream&) const |
| `0x003372B8` | `STR X` | `0x00336D20+0x598` – CGameState::ResetInPlace() |
| `0x003373B8` | `LDR X` | `0x00337384+0x34` – CGameState::SavePlayerSettingsBeforeAlternateMode() |
| `0x00337414` | `STR X` | `0x003373FC+0x18` – CGameState::RestorePlayerSettingsAfterAlternateMode() |
| `0x003376BC` | `LDR W` | `0x003376BC+0x0` – CGameState::GetPlayerIndexByCharacterType(dkcPas::ECharacterType) const |
| `0x0033A9A4` | `LDR W` | `0x0033A92C+0x78` – CHUDIOWin::UpdateInventoryLock(NPlayerState::EPlayerIndex, int, NPlayerState::EItemType) |
| `0x0033B654` | `LDR W` | `0x0033B464+0x1F0` – CHUDIOWin::AreaLoaded() |
| `0x0033BAD0` | `LDR W` | `0x0033B464+0x66C` – CHUDIOWin::AreaLoaded() |
| `0x0033BD84` | `LDR W` | `0x0033BD64+0x20` – CHUDIOWin::SpawnSecondPlayer(CStateManager&) |
| `0x0033C120` | `LDR W` | `0x0033C104+0x1C` – CHUDIOWin::PrimaryInWaterStateChange(CStateManager&, CWaterVolumeDataWrapper const&, bool) |
| `0x0033C228` | `LDR W` | UNAUFGELÖST |
| `0x0033C400` | `LDR W` | `0x0033C3E4+0x1C` – CHUDIOWin::GetPortraitTypeName(NPlayerState::EPlayerIndex) |
| `0x0033CC7C` | `LDR W` | `0x0033CB1C+0x160` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033CE54` | `LDR W` | `0x0033CB1C+0x338` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033E3A4` | `LDR W` | `0x0033DFF4+0x3B0` – CHUDIOWin::FillDataDictionary(char const*) |
| `0x0033E6CC` | `LDR W` | `0x0033E6B0+0x1C` – CHUDIOWin::PlayerInWaterStateChange(NPlayerState::EPlayerIndex, CStateManager&, CWaterVolumeDataWrapper const&, bool) |
| `0x003456EC` | `STR W` | `0x00345688+0x64` – CMenuIOWin::QuitToFrontEnd(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00345814` | `STR W` | `0x003457A8+0x6C` – CMenuIOWin::UpdateCharacterTypes(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0034D0B8` | `LDR W` | `0x0034CBCC+0x4EC` – CSuperGuide::CSuperGuide(CGameState&, CObjectId const&, CFourCC) |
| `0x0034DFBC` | `STR W` | `0x0034DCC4+0x2F8` – CSuperGuide::ReadHeader(CGameState&, unsigned char) |
| `0x0034FB48` | `STR W` | `0x0034F730+0x418` – CProductionFrontEnd::CProductionFrontEnd(CGameStateManager* const&, rstl::ncrc_ptr<CFlashMovieInstanceManager> const&, rstl::ncrc_ptr<CStateManager>&, rstl::ncrc_ptr<CFlashDataModel>&) |
| `0x0034FBB0` | `STR W` | `0x0034FB64+0x4C` – CProductionFrontEnd::SetupInitialGameState() |
| `0x0035139C` | `LDR W` | `0x003512B8+0xE4` – CProductionFrontEnd::FillDataDictionary(char const*) |
| `0x00352060` | `STR W` | `0x0035201C+0x44` – CProductionFrontEnd::InitGameTransition(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0035230C` | `STR W` | `0x0035201C+0x2F0` – CProductionFrontEnd::InitGameTransition(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0035240C` | `STR W` | `0x0035201C+0x3F0` – CProductionFrontEnd::InitGameTransition(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00354A54` | `LDR W` | `0x003549C4+0x90` – CProductionFrontEnd::PopulateSaveData(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x00354DA4` | `LDR W` | `0x00354CF8+0xAC` – CProductionFrontEnd::InitSlotData(IFlashMovieInstance const*, rstl::vector<CFlashValue, rstl::rmemory_allocator>&) |
| `0x0035A690` | `LDR W` | `0x0035A178+0x518` – CProductionLoadingScreen::ShowLoadingScreen(CUniverseInfo::ELoadDirection, CGameStateManager* const&, CArchitectureQueue&, IObjectStore&, CResourceFactory*) |
| `0x0035F398` | `LDR W` | `0x0035F310+0x88` – CSCAIOWin::SetupSCAObjects(IObjectStore&) |
| `0x0035FA88` | `LDR W` | `0x0035FA7C+0xC` – CSCAIOWin::GetMinorKongPresent() const |
| `0x00367760` | `LDR W` | `0x003676E4+0x7C` – CBonusGameMode::PrepareForEOLSave(CStateManager&) |
| `0x00391340` | `LDR W` | `0x0039131C+0x24` – CActionDetectorGOC::AreaLoaded(CStateManager&) |
| `0x003A4118` | `LDR W` | `0x003A3F90+0x188` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4194` | `LDR W` | `0x003A3F90+0x204` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4210` | `LDR W` | `0x003A3F90+0x280` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4638` | `LDR W` | `0x003A4614+0x24` – CBaboonManagerGOC::TryGetTargetIndex(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x003A5660` | `LDR W` | `0x003A55A8+0xB8` – CBaboonManagerGOC::VineSwingTryActivateSupportBaboon(CStateManager&, NBaboon::ESide&) |
| `0x003A57D0` | `LDR W` | `0x003A5738+0x98` – CBaboonManagerGOC::VineSwingSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5A00` | `LDR W` | `0x003A5948+0xB8` – CBaboonManagerGOC::MultiRollTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5B84` | `LDR W` | `0x003A5AE8+0x9C` – CBaboonManagerGOC::MultiRollSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5DC0` | `LDR W` | `0x003A5D08+0xB8` – CBaboonManagerGOC::BombTossTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5F04` | `LDR W` | `0x003A5E68+0x9C` – CBaboonManagerGOC::BombTossSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A6140` | `LDR W` | `0x003A6088+0xB8` – CBaboonManagerGOC::DropJumpTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A6284` | `LDR W` | `0x003A61E8+0x9C` – CBaboonManagerGOC::DropJumpSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A715C` | `LDR W` | `0x003A7134+0x28` – CBaboonManagerGOC::GetTargetPlayer(CStateManager const&, int) const |
| `0x003A71D8` | `LDR W` | `0x003A7188+0x50` – CBaboonManagerGOC::RefreshTarget(CStateManager const&, int) |
| `0x003A72F0` | `LDR W` | `0x003A72D0+0x20` – CBaboonManagerGOC::FindClosestPlayerIndex(CStateManager const&, CVector3f const&) const |
| `0x003A7414` | `LDR W` | `0x003A73CC+0x48` – CBaboonManagerGOC::PredictTargetPlayerGroundPosition(CStateManager const&, int, float, NBaboon::EClampToArena, CVector3f&) const |
| `0x003A8028` | `LDR W` | `0x003A7F84+0xA4` – CBaboonManagerGOC::BombSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A81F0` | `LDR W` | `0x003A8140+0xB0` – CBaboonManagerGOC::MultiSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A9590` | `LDR W` | `0x003A9568+0x28` – CBaboonManagerGOC::MultiSwingUpdateIsPlayerHiding(CStateManager&) |
| `0x003A98F0` | `LDR W` | `0x003A97A4+0x14C` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A9934` | `LDR W` | `0x003A97A4+0x190` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A99BC` | `LDR W` | `0x003A97A4+0x218` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A9BA4` | `LDR W` | `0x003A9B04+0xA0` – CBaboonManagerGOC::MultiSwingSetupNinja(CStateManager&, CVector3f&) |
| `0x003AA464` | `LDR W` | `0x003AA3BC+0xA8` – CBaboonManagerGOC::RollJumpSetupClone(CStateManager&, int) |
| `0x003AAF50` | `LDR W` | `0x003AAE68+0xE8` – CBaboonManagerGOC::BombSwingSetup(CStateManager&) |
| `0x003AB640` | `LDR W` | `0x003AB5B4+0x8C` – CBaboonManagerGOC::MultiSwingSetupBaboon(CStateManager&, int, float, NBaboon::ESide, NBaboonPasDefs::EMultiSwingPosition) |
| `0x003AD6B0` | `LDR W` | `0x003AD5B4+0xFC` – CBarrelBalloonGOC::OnActivationStateChange(CStateManager&, CScriptMsg const&) |
| `0x003AF120` | `LDR W` | `0x003AF074+0xAC` – CBeatUpHandlerGOC::OnAction_SetupDetectionForOriginator(CStateManager&, CScriptMsg const&) |
| `0x003AF2B0` | `LDR W` | `0x003AF270+0x40` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003AF2D8` | `LDR W` | `0x003AF270+0x68` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003B059C` | `LDR W` | `0x003B0250+0x34C` – CBeatUpHandlerGOC::Think(CStateManager&, float) |
| `0x003B0614` | `LDR W` | `0x003B0250+0x3C4` – CBeatUpHandlerGOC::Think(CStateManager&, float) |
| `0x003B0948` | `LDR W` | `0x003B0908+0x40` – CBeatUpHandlerGOC::SetupDetectionForPlayerIndex(CStateManager&, NPlayerState::EPlayerIndex) |
| `0x003B098C` | `LDR W` | `0x003B0970+0x1C` – CBeatUpHandlerGOC::GetPlayerIsAlive(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x003B0E2C` | `LDR W` | `0x003B0E18+0x14` – CBeatUpHandlerGOC::SendActionStateForPlayer(CStateManager&, NPlayerState::EPlayerIndex) |
| `0x003B3DDC` | `LDR W` | `0x003B3DAC+0x30` – CBreathMonitorGOC::GetEventIndexForBreath(CStateManager&) |
| `0x003BCEAC` | `LDR W` | `0x003BCE60+0x4C` – CCheckpointGOC::Think(CStateManager&, float) |
| `0x003BD0DC` | `LDR W` | `0x003BD010+0xCC` – CCheckpointGOC::SpawnPlayer(CStateManager&) |
| `0x003BD3C0` | `LDR W` | `0x003BD31C+0xA4` – CCheckpointGOC::FinishRespawn(CStateManager&) |
| `0x003BD9DC` | `LDR W` | `0x003BD954+0x88` – CCinematicCameraShotGOC::OnAction_PlayShot(CStateManager&, CScriptMsg const&) |
| `0x003D1798` | `LDR W` | `0x003D1764+0x34` – CDialogPanelGOC::HandleSwimmingDisplay(CStateManager&, float) |
| `0x003DFD4C` | `LDR W` | `0x003DFCD0+0x7C` – CGameQueryGOC::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |
| `0x003DFF7C` | `LDR W` | `0x003DFF60+0x1C` – CGameQueryGOC::OnAction_QueryIsPlayer1Funky(CStateManager&, CScriptMsg const&) |
| `0x003E8AB4` | `LDR W` | `0x003E8A4C+0x68` – CGrabThrowGOC::SetupInhabitantBehavior(CStateManager&) |
| `0x003E8B08` | `LDR W` | `0x003E8A4C+0xBC` – CGrabThrowGOC::SetupInhabitantBehavior(CStateManager&) |
| `0x003E8C00` | `LDR W` | `0x003E8B68+0x98` – CGrabThrowGOC::UpdateInhabitant(CStateManager&) |
| `0x003E8D10` | `LDR W` | `0x003E8CB8+0x58` – CGrabThrowGOC::SetupBarrelCharacter(CStateManager&) |
| `0x003E9960` | `LDR W` | `0x003E98F0+0x70` – CGrabThrowGOC::UpdateDesiredInhabitant(CStateManager const&) |
| `0x0040526C` | `LDR W` | `0x00405208+0x64` – CMapPlayerGOC::ResetCharacter(CStateManager&) |
| `0x0040F3E8` | `LDR W` | `0x0040F37C+0x6C` – CNearVisibleGOC::CheckForPlayerInBounds(CStateManager const&, CAABox const&) |
| `0x0041AC28` | `LDR W` | `0x0041AAD8+0x150` – CPickupGOC::StartSpawnSequence(CStateManager&, TUniqueId, CPickupGOC::EIsForcePickup) |
| `0x0041DAAC` | `LDR W` | `0x0041D81C+0x290` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041DDC4` | `LDR W` | `0x0041DD84+0x40` – CPlayerActorGOC::GetRepresentPlayer(CStateManager const&) const |
| `0x0041DDF4` | `LDR W` | `0x0041DD84+0x70` – CPlayerActorGOC::GetRepresentPlayer(CStateManager const&) const |
| `0x0041DE50` | `LDR W` | `0x0041DD84+0xCC` – CPlayerActorGOC::GetRepresentPlayer(CStateManager const&) const |
| `0x0041FA34` | `LDR W` | `0x0041F9AC+0x88` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FAB0` | `LDR W` | `0x0041F9AC+0x104` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x0041FC78` | `LDR W` | `0x0041FC64+0x14` – CPlayerKeyframeGOC::PlayerFromIndex(CStateManager&, NPlayerState::EPlayerIndex) |
| `0x00420990` | `LDR W` | `0x00420568+0x428` – CPlayerProxyGOC::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |
| `0x0042147C` | `LDR W` | `0x00421450+0x2C` – CPlayerProxyGOC::OnAction_QueryIsP1(CStateManager&, CScriptMsg const&) |
| `0x00427464` | `LDR W` | `0x004273E0+0x84` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |
| `0x004275B0` | `LDR W` | `0x00427594+0x1C` – CPlayerSoundGOC::GetSoundCharacter(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x00438F64` | `LDR W` | `0x00438ED4+0x90` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x00438FB4` | `LDR W` | `0x00438ED4+0xE0` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x004390B8` | `LDR W` | `0x0043907C+0x3C` – CConditionalTest::IsPlayerItemIndeterminate(CStateManager const&) const |
| `0x0043915C` | `LDR W` | `0x0043911C+0x40` – CConditionalTest::GetPlayerItemValue(CStateManager const&) const |
| `0x00439200` | `LDR W` | `0x004391C0+0x40` – CConditionalTest::GetPlayerItemMaxValue(CStateManager const&) const |
| `0x00440DE4` | `LDR W` | `0x00440C9C+0x148` – CRespawnBalloonGOC::Think(CStateManager&, float) |
| `0x004410B8` | `LDR W` | `0x00440EC8+0x1F0` – CRespawnBalloonGOC::GrabPlayersAndStart(CStateManager&, float) |
| `0x00441678` | `LDR W` | `0x00441644+0x34` – CRespawnBalloonGOC::ToggleControls(CStateManager&, bool) |
| `0x0044A154` | `LDR W` | `0x0044A0CC+0x88` – CRumbleEffectGOC::OnAction_Rumble(CStateManager&, CScriptMsg const&) |
| `0x0044B518` | `LDR W` | `0x0044B4E4+0x34` – CRumbleEffectGOC::RumbleRiders(CStateManager&, CPlayer const&, TUniqueId) |
| `0x004D2E2C` | `LDR W` | `0x004D2D88+0xA4` – CTargetOrientationSplineControl::Update(CStateManager&, CSplineMotionGOC const&, float) |
| `0x004E6C20` | `LDR W` | `0x004E6B90+0x90` – CProjectileMotionTargetedPhysics::Init(CProjectileGOC const&, CStateManager&) |
| `0x00545640` | `LDR W` | `0x00545620+0x20` – CActorModulePolarBearController::AllTargetsBehind(CStateManager const&, float) const |
| `0x00545778` | `LDR W` | `0x00545758+0x20` – CActorModulePolarBearController::CalculateForwardDisplacementToPlayer(CStateManager const&, NPlayerState::EPlayerIndex, float&) const |
| `0x00562600` | `LDR W` | `0x005625A8+0x58` – CRumbleManager::Rumble(CStateManager&, float, CVector3f const&, CRumbleManager::SLRAData const&, CRumbleManager::SLRAData const&) |
| `0x005643A8` | `LDR W` | `0x00564334+0x74` – CRumbleManager::Rumble(CStateManager&, float, CVector3f const&, ERumbleEffect, ERumblePriority) |
| `0x0068E568` | `LDR W` | `0x0068E434+0x134` – CPhysicsSteppedMoverCollider::MoveObject(CPhysicsWorld const&, CPhysicsSimulationObject&) const |
| `0x0068E8A4` | `LDR W` | `0x0068E69C+0x208` – CPhysicsSteppedMoverCollider::DoMovementStep(CPhysicsWorld const&, CPhysicsSimulationObject&, float, bool, bool, CCollisionInfoList&, CValueVersionId<unsigned int, unsigned short, unsigned short, 16u, 16u>&) const |
| `0x0068EA54` | `LDR W` | `0x0068E69C+0x3B8` – CPhysicsSteppedMoverCollider::DoMovementStep(CPhysicsWorld const&, CPhysicsSimulationObject&, float, bool, bool, CCollisionInfoList&, CValueVersionId<unsigned int, unsigned short, unsigned short, 16u, 16u>&) const |
| `0x0068F3C4` | `LDR W` | `0x0068E69C+0xD28` – CPhysicsSteppedMoverCollider::DoMovementStep(CPhysicsWorld const&, CPhysicsSimulationObject&, float, bool, bool, CCollisionInfoList&, CValueVersionId<unsigned int, unsigned short, unsigned short, 16u, 16u>&) const |
