# Duplicate Kong – const CharacterType-Player-Lookups

### `002CDC30` – CStateManagerGameData::GetPrimaryPlayerByCharacterType(dkcPas::ECharacterType, NPlayerState::EPlayerFlags) const

Direkte Referenzen: **138**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x002005C0` | `BL` | `0x0020057C+0x44` – CPlayer::GetMultiplayerState(CStateManager const&) const |
| `0x0020061C` | `BL` | `0x0020057C+0xA0` – CPlayer::GetMultiplayerState(CStateManager const&) const |
| `0x00220C14` | `BL` | `0x00220B54+0xC0` – CPlayerModuleBarrelCannon::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x002422B8` | `BL` | `0x00242198+0x120` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x002422E4` | `BL` | `0x00242198+0x14C` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x00242F88` | `BL` | `0x00242ED8+0xB0` – CPlayerModuleHealth::SplitDamageBetweenPlayers(CStateManager const&, NDamageType::EDamageType, int, int&, int&) |
| `0x00242FB4` | `BL` | `0x00242ED8+0xDC` – CPlayerModuleHealth::SplitDamageBetweenPlayers(CStateManager const&, NDamageType::EDamageType, int, int&, int&) |
| `0x0024E8A8` | `BL` | `0x0024E788+0x120` – CPlayerModuleMount::PostOwnerThink(CStateManager&, float) |
| `0x0024FDBC` | `BL` | `0x0024FD34+0x88` – CPlayerModuleMount::FindRiders(CStateManager const&) |
| `0x0024FFBC` | `BL` | `0x0024FF4C+0x70` – CPlayerModuleMount::HasAllRidersInChain(CStateManager const&, CPlayerModuleMount::ECheckFullyMounted) const |
| `0x00250040` | `BL` | `0x0024FF4C+0xF4` – CPlayerModuleMount::HasAllRidersInChain(CStateManager const&, CPlayerModuleMount::ECheckFullyMounted) const |
| `0x00250B58` | `BL` | `0x00250A80+0xD8` – CPlayerModuleMount::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x002564A0` | `BL` | `0x00256488+0x18` – CPlayerModuleShield::GetPlayerSpecificShieldVisual(CStateManager const&, dkcPas::ECharacterType) |
| `0x0027C6D0` | `BL` | `0x0027C678+0x58` – NPlayerUtils::CanSpawnPlayer(CStateManager const&, dkcPas::ECharacterType) |
| `0x0027C94C` | `BL` | `0x0027C910+0x3C` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x002AF064` | `BL` | `0x002AF010+0x54` – CSquawksGOC::UpdateFade(CStateManager&) |
| `0x002AF108` | `BL` | `0x002AF010+0xF8` – CSquawksGOC::UpdateFade(CStateManager&) |
| `0x0033A9AC` | `BL` | `0x0033A92C+0x80` – CHUDIOWin::UpdateInventoryLock(NPlayerState::EPlayerIndex, int, NPlayerState::EItemType) |
| `0x0033BADC` | `BL` | `0x0033B464+0x678` – CHUDIOWin::AreaLoaded() |
| `0x0033BB2C` | `BL` | `0x0033B464+0x6C8` – CHUDIOWin::AreaLoaded() |
| `0x0033C134` | `BL` | `0x0033C104+0x30` – CHUDIOWin::PrimaryInWaterStateChange(CStateManager&, CWaterVolumeDataWrapper const&, bool) |
| `0x0033C194` | `BL` | `0x0033C164+0x30` – CHUDIOWin::SecondaryInWaterStateChange(CStateManager&, CWaterVolumeDataWrapper const&, bool) |
| `0x0033C234` | `BL` | — – UNAUFGELÖST |
| `0x0033C254` | `BL` | — – UNAUFGELÖST |
| `0x0033C418` | `BL` | `0x0033C3E4+0x34` – CHUDIOWin::GetPortraitTypeName(NPlayerState::EPlayerIndex) |
| `0x0033CC88` | `BL` | `0x0033CB1C+0x16C` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033CCB8` | `BL` | `0x0033CB1C+0x19C` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033CD34` | `BL` | `0x0033CB1C+0x218` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033CE60` | `BL` | `0x0033CB1C+0x344` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033CEB0` | `BL` | `0x0033CB1C+0x394` – CHUDIOWin::UpdatePlaying(float) |
| `0x0033E6E4` | `BL` | `0x0033E6B0+0x34` – CHUDIOWin::PlayerInWaterStateChange(NPlayerState::EPlayerIndex, CStateManager&, CWaterVolumeDataWrapper const&, bool) |
| `0x0035F380` | `BL` | `0x0035F310+0x70` – CSCAIOWin::SetupSCAObjects(IObjectStore&) |
| `0x0035F3E8` | `BL` | `0x0035F310+0xD8` – CSCAIOWin::SetupSCAObjects(IObjectStore&) |
| `0x0035FAD8` | `B` | `0x0035FA7C+0x5C` – CSCAIOWin::GetMinorKongPresent() const |
| `0x00360000` | `BL` | `0x0035FADC+0x524` – CSCAIOWin::SetupSCAObject(IObjectStore&, CPlayer const&, dkcPas::ECharacterType) const |
| `0x00391358` | `BL` | `0x0039131C+0x3C` – CActionDetectorGOC::AreaLoaded(CStateManager&) |
| `0x0039138C` | `BL` | `0x0039131C+0x70` – CActionDetectorGOC::AreaLoaded(CStateManager&) |
| `0x003A4124` | `BL` | `0x003A3F90+0x194` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4140` | `BL` | `0x003A3F90+0x1B0` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A41A0` | `BL` | `0x003A3F90+0x210` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A41BC` | `BL` | `0x003A3F90+0x22C` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A421C` | `BL` | `0x003A3F90+0x28C` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4238` | `BL` | `0x003A3F90+0x2A8` – CBaboonManagerGOC::PreThink(CStateManager&, float) |
| `0x003A4648` | `BL` | `0x003A4614+0x34` – CBaboonManagerGOC::TryGetTargetIndex(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x003A4664` | `BL` | `0x003A4614+0x50` – CBaboonManagerGOC::TryGetTargetIndex(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x003A566C` | `BL` | `0x003A55A8+0xC4` – CBaboonManagerGOC::VineSwingTryActivateSupportBaboon(CStateManager&, NBaboon::ESide&) |
| `0x003A5688` | `BL` | `0x003A55A8+0xE0` – CBaboonManagerGOC::VineSwingTryActivateSupportBaboon(CStateManager&, NBaboon::ESide&) |
| `0x003A57DC` | `BL` | `0x003A5738+0xA4` – CBaboonManagerGOC::VineSwingSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A57F8` | `BL` | `0x003A5738+0xC0` – CBaboonManagerGOC::VineSwingSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5A0C` | `BL` | `0x003A5948+0xC4` – CBaboonManagerGOC::MultiRollTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5A28` | `BL` | `0x003A5948+0xE0` – CBaboonManagerGOC::MultiRollTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5B90` | `BL` | `0x003A5AE8+0xA8` – CBaboonManagerGOC::MultiRollSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5BAC` | `BL` | `0x003A5AE8+0xC4` – CBaboonManagerGOC::MultiRollSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5DCC` | `BL` | `0x003A5D08+0xC4` – CBaboonManagerGOC::BombTossTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5DE8` | `BL` | `0x003A5D08+0xE0` – CBaboonManagerGOC::BombTossTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A5F10` | `BL` | `0x003A5E68+0xA8` – CBaboonManagerGOC::BombTossSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A5F2C` | `BL` | `0x003A5E68+0xC4` – CBaboonManagerGOC::BombTossSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A614C` | `BL` | `0x003A6088+0xC4` – CBaboonManagerGOC::DropJumpTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A6168` | `BL` | `0x003A6088+0xE0` – CBaboonManagerGOC::DropJumpTryActivateSupportBaboon(CStateManager&, NBaboon::ESide) |
| `0x003A6290` | `BL` | `0x003A61E8+0xA8` – CBaboonManagerGOC::DropJumpSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A62AC` | `BL` | `0x003A61E8+0xC4` – CBaboonManagerGOC::DropJumpSetupBaboon(CStateManager&, int, float, NBaboon::ERole) |
| `0x003A716C` | `B` | `0x003A7134+0x38` – CBaboonManagerGOC::GetTargetPlayer(CStateManager const&, int) const |
| `0x003A71E4` | `BL` | `0x003A7188+0x5C` – CBaboonManagerGOC::RefreshTarget(CStateManager const&, int) |
| `0x003A7200` | `BL` | `0x003A7188+0x78` – CBaboonManagerGOC::RefreshTarget(CStateManager const&, int) |
| `0x003A730C` | `BL` | `0x003A72D0+0x3C` – CBaboonManagerGOC::FindClosestPlayerIndex(CStateManager const&, CVector3f const&) const |
| `0x003A7370` | `BL` | `0x003A72D0+0xA0` – CBaboonManagerGOC::FindClosestPlayerIndex(CStateManager const&, CVector3f const&) const |
| `0x003A7428` | `BL` | `0x003A73CC+0x5C` – CBaboonManagerGOC::PredictTargetPlayerGroundPosition(CStateManager const&, int, float, NBaboon::EClampToArena, CVector3f&) const |
| `0x003A8034` | `BL` | `0x003A7F84+0xB0` – CBaboonManagerGOC::BombSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A8050` | `BL` | `0x003A7F84+0xCC` – CBaboonManagerGOC::BombSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A8200` | `BL` | `0x003A8140+0xC0` – CBaboonManagerGOC::MultiSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A821C` | `BL` | `0x003A8140+0xDC` – CBaboonManagerGOC::MultiSwingSetupNextClone(CStateManager&, CVector3f&) |
| `0x003A95A4` | `BL` | `0x003A9568+0x3C` – CBaboonManagerGOC::MultiSwingUpdateIsPlayerHiding(CStateManager&) |
| `0x003A961C` | `BL` | `0x003A9568+0xB4` – CBaboonManagerGOC::MultiSwingUpdateIsPlayerHiding(CStateManager&) |
| `0x003A9904` | `BL` | `0x003A97A4+0x160` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A994C` | `BL` | `0x003A97A4+0x1A8` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A9968` | `BL` | `0x003A97A4+0x1C4` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A99C8` | `BL` | `0x003A97A4+0x224` – CBaboonManagerGOC::MultiSwingGetNextTargetPosition(CStateManager&, int) |
| `0x003A9BB4` | `BL` | `0x003A9B04+0xB0` – CBaboonManagerGOC::MultiSwingSetupNinja(CStateManager&, CVector3f&) |
| `0x003A9BD0` | `BL` | `0x003A9B04+0xCC` – CBaboonManagerGOC::MultiSwingSetupNinja(CStateManager&, CVector3f&) |
| `0x003AA470` | `BL` | `0x003AA3BC+0xB4` – CBaboonManagerGOC::RollJumpSetupClone(CStateManager&, int) |
| `0x003AA48C` | `BL` | `0x003AA3BC+0xD0` – CBaboonManagerGOC::RollJumpSetupClone(CStateManager&, int) |
| `0x003AAF60` | `BL` | `0x003AAE68+0xF8` – CBaboonManagerGOC::BombSwingSetup(CStateManager&) |
| `0x003AAF7C` | `BL` | `0x003AAE68+0x114` – CBaboonManagerGOC::BombSwingSetup(CStateManager&) |
| `0x003AB64C` | `BL` | `0x003AB5B4+0x98` – CBaboonManagerGOC::MultiSwingSetupBaboon(CStateManager&, int, float, NBaboon::ESide, NBaboonPasDefs::EMultiSwingPosition) |
| `0x003AB668` | `BL` | `0x003AB5B4+0xB4` – CBaboonManagerGOC::MultiSwingSetupBaboon(CStateManager&, int, float, NBaboon::ESide, NBaboonPasDefs::EMultiSwingPosition) |
| `0x003AD118` | `BL` | `0x003AD0C4+0x54` – CBarrelBalloonGOC::Think(CStateManager&, float) |
| `0x003AD8EC` | `BL` | `0x003AD8A4+0x48` – CBarrelBalloonGOC::PopBalloon(CStateManager&) |
| `0x003ADD7C` | `BL` | `0x003ADC74+0x108` – CBarrelBalloonGOC::GetBalloonShouldDisappearOffscreen(CStateManager&) |
| `0x003AE194` | `BL` | `0x003AE164+0x30` – CBarrelBalloonGOC::PickMotionState(CStateManager&) |
| `0x003AE280` | `BL` | `0x003AE248+0x38` – CBarrelBalloonGOC::TeleportJustOffScreenAwayFromOtherPlayer(CStateManager&) |
| `0x003AE410` | `BL` | `0x003AE3DC+0x34` – CBarrelBalloonGOC::StartShakeInputMotion(CStateManager&, CBarrelBalloonGOC::EShakeMotion) |
| `0x003AE504` | `BL` | `0x003AE4D4+0x30` – CBarrelBalloonGOC::UpdateLockedMotionMovement(CStateManager&, float) |
| `0x003AF134` | `BL` | `0x003AF074+0xC0` – CBeatUpHandlerGOC::OnAction_SetupDetectionForOriginator(CStateManager&, CScriptMsg const&) |
| `0x003AF2B8` | `BL` | `0x003AF270+0x48` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003AF2E4` | `BL` | `0x003AF270+0x74` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003AF308` | `BL` | `0x003AF270+0x98` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003AF36C` | `BL` | `0x003AF270+0xFC` – CBeatUpHandlerGOC::OnAction_SetupDetectionForPlayers(CStateManager&, CScriptMsg const&) |
| `0x003B0954` | `BL` | `0x003B0908+0x4C` – CBeatUpHandlerGOC::SetupDetectionForPlayerIndex(CStateManager&, NPlayerState::EPlayerIndex) |
| `0x003B099C` | `BL` | `0x003B0970+0x2C` – CBeatUpHandlerGOC::GetPlayerIsAlive(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x003B3DE8` | `BL` | `0x003B3DAC+0x3C` – CBreathMonitorGOC::GetEventIndexForBreath(CStateManager&) |
| `0x003B3E28` | `BL` | `0x003B3DAC+0x7C` – CBreathMonitorGOC::GetEventIndexForBreath(CStateManager&) |
| `0x003BCEB8` | `BL` | `0x003BCE60+0x58` – CCheckpointGOC::Think(CStateManager&, float) |
| `0x003BCF10` | `BL` | `0x003BCE60+0xB0` – CCheckpointGOC::Think(CStateManager&, float) |
| `0x003BD9E8` | `BL` | `0x003BD954+0x94` – CCinematicCameraShotGOC::OnAction_PlayShot(CStateManager&, CScriptMsg const&) |
| `0x003D1714` | `BL` | `0x003D16C0+0x54` – CDialogPanelGOC::HandlePosition(CStateManager&) |
| `0x003D17AC` | `BL` | `0x003D1764+0x48` – CDialogPanelGOC::HandleSwimmingDisplay(CStateManager&, float) |
| `0x0040F3F4` | `BL` | `0x0040F37C+0x78` – CNearVisibleGOC::CheckForPlayerInBounds(CStateManager const&, CAABox const&) |
| `0x0040F454` | `BL` | `0x0040F37C+0xD8` – CNearVisibleGOC::CheckForPlayerInBounds(CStateManager const&, CAABox const&) |
| `0x0041AC30` | `BL` | `0x0041AAD8+0x158` – CPickupGOC::StartSpawnSequence(CStateManager&, TUniqueId, CPickupGOC::EIsForcePickup) |
| `0x0041AD70` | `BL` | `0x0041AAD8+0x298` – CPickupGOC::StartSpawnSequence(CStateManager&, TUniqueId, CPickupGOC::EIsForcePickup) |
| `0x0041DAB8` | `BL` | `0x0041D81C+0x29C` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041DB00` | `BL` | `0x0041D81C+0x2E4` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041DDCC` | `BL` | `0x0041DD84+0x48` – CPlayerActorGOC::GetRepresentPlayer(CStateManager const&) const |
| `0x0041DE00` | `BL` | `0x0041DD84+0x7C` – CPlayerActorGOC::GetRepresentPlayer(CStateManager const&) const |
| `0x0041DE5C` | `BL` | `0x0041DD84+0xD8` – CPlayerActorGOC::GetRepresentPlayer(CStateManager const&) const |
| `0x004256C0` | `BL` | `0x004255C0+0x100` – CPlayerRespawnGOC::Think(CStateManager&, float) |
| `0x00427478` | `BL` | `0x004273E0+0x98` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |
| `0x004274E4` | `BL` | `0x004273E0+0x104` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |
| `0x004275C0` | `BL` | `0x00427594+0x2C` – CPlayerSoundGOC::GetSoundCharacter(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x00438F78` | `BL` | `0x00438ED4+0xA4` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x00438FC8` | `BL` | `0x00438ED4+0xF4` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x00439004` | `BL` | `0x00438ED4+0x130` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x00439040` | `BL` | `0x00438ED4+0x16C` – CConditionalTest::GetInputValue(CStateManager const&, CRelayConditionalGOC const&, CConditionalTest::EInput, TUniqueId) const |
| `0x004390C8` | `BL` | `0x0043907C+0x4C` – CConditionalTest::IsPlayerItemIndeterminate(CStateManager const&) const |
| `0x004390FC` | `BL` | `0x0043907C+0x80` – CConditionalTest::IsPlayerItemIndeterminate(CStateManager const&) const |
| `0x00439180` | `BL` | `0x0043911C+0x64` – CConditionalTest::GetPlayerItemValue(CStateManager const&) const |
| `0x00439224` | `BL` | `0x004391C0+0x64` – CConditionalTest::GetPlayerItemMaxValue(CStateManager const&) const |
| `0x0044A168` | `BL` | `0x0044A0CC+0x9C` – CRumbleEffectGOC::OnAction_Rumble(CStateManager&, CScriptMsg const&) |
| `0x0044A200` | `BL` | `0x0044A0CC+0x134` – CRumbleEffectGOC::OnAction_Rumble(CStateManager&, CScriptMsg const&) |
| `0x0045C5EC` | `BL` | `0x0045C530+0xBC` – CSquawksProxyGOC::Think(CStateManager&, float) |
| `0x004D2E50` | `BL` | `0x004D2D88+0xC8` – CTargetOrientationSplineControl::Update(CStateManager&, CSplineMotionGOC const&, float) |
| `0x004E6C2C` | `BL` | `0x004E6B90+0x9C` – CProjectileMotionTargetedPhysics::Init(CProjectileGOC const&, CStateManager&) |
| `0x004E6C48` | `BL` | `0x004E6B90+0xB8` – CProjectileMotionTargetedPhysics::Init(CProjectileGOC const&, CStateManager&) |
| `0x00545660` | `BL` | `0x00545620+0x40` – CActorModulePolarBearController::AllTargetsBehind(CStateManager const&, float) const |
| `0x005456C0` | `BL` | `0x00545620+0xA0` – CActorModulePolarBearController::AllTargetsBehind(CStateManager const&, float) const |
| `0x00545790` | `BL` | `0x00545758+0x38` – CActorModulePolarBearController::CalculateForwardDisplacementToPlayer(CStateManager const&, NPlayerState::EPlayerIndex, float&) const |
| `0x00562610` | `BL` | `0x005625A8+0x68` – CRumbleManager::Rumble(CStateManager&, float, CVector3f const&, CRumbleManager::SLRAData const&, CRumbleManager::SLRAData const&) |
| `0x005643B4` | `BL` | `0x00564334+0x80` – CRumbleManager::Rumble(CStateManager&, float, CVector3f const&, ERumbleEffect, ERumblePriority) |
