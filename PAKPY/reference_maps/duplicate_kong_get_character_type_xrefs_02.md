# CPlayer::GetCharacterType direct Xrefs – Teil 2

| `0x00268728` | `BL` | `0x002686FC+0x2C` – CPlayerModuleSwimmingJetBoost::IsJetBoostControllerPlayer(CStateManager const&, CPlayer const&) const |
| `0x00268738` | `BL` | `0x002686FC+0x3C` – CPlayerModuleSwimmingJetBoost::IsJetBoostControllerPlayer(CStateManager const&, CPlayer const&) const |
| `0x002689C8` | `BL` | `0x002689B0+0x18` – CPlayerModuleSwimmingJetBoost::JetBoostOwnerPlayer(CStateManager&) const |
| `0x002689E0` | `BL` | `0x002689B0+0x30` – CPlayerModuleSwimmingJetBoost::JetBoostOwnerPlayer(CStateManager&) const |
| `0x00268E80` | `BL` | `0x00268E38+0x48` – CPlayerModuleSwimmingPropeller::PreOwnerThink(CStateManager&, float) |
| `0x002690BC` | `BL` | `0x00269068+0x54` – CPlayerModuleSwimmingPropeller::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00269100` | `BL` | `0x00269068+0x98` – CPlayerModuleSwimmingPropeller::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00269544` | `BL` | `0x00269518+0x2C` – CPlayerModuleSwimmingPropeller::IsPropellerControllerPlayer(CStateManager const&, CPlayer const&) const |
| `0x0026A328` | `BL` | `0x0026A260+0xC8` – CPlayerModuleSwing::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x0026E628` | `BL` | `0x0026E484+0x1A4` – CPlayerModuleTeleport::GetTeleportDestination(CStateManager const&) const |
| `0x0026EF7C` | `BL` | `0x0026EDD8+0x1A4` – CPlayerModuleTeleport::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x0027B928` | `BL` | `0x0027B910+0x18` – KongGroundPoundHelper::IsRunningSlapEnabled(CStateManager const&, CPlayer const&) |
| `0x0027B970` | `BL` | `0x0027B958+0x18` – KongGroundPoundHelper::IsRunningSlapToJumpLaunchEnabled(CStateManager const&, CPlayer const&) |
| `0x0027B9B8` | `BL` | `0x0027B9A0+0x18` – KongGroundPoundHelper::IsRunningSlapEnableInfiniteRoll(CStateManager const&, CPlayer const&) |
| `0x0027BA04` | `BL` | `0x0027B9E8+0x1C` – KongGroundPoundHelper::RunningSlapRollTimeout(CStateManager const&, CPlayer const&) |
| `0x0027BA64` | `BL` | `0x0027BA4C+0x18` – KongGroundPoundHelper::RunningSlapRollSpeedMultiplier(CStateManager const&, CPlayer const&) |
| `0x0027BAAC` | `BL` | `0x0027BA94+0x18` – KongGroundPoundHelper::IsRunningSlapOnlyOneRollAllowed(CStateManager const&, CPlayer const&) |
| `0x0027BB00` | `BL` | `0x0027BAE4+0x1C` – KongGroundPoundHelper::RunningSlapDelayBetweenSlaps(CStateManager const&, CPlayer const&) |
| `0x0027BB64` | `BL` | `0x0027BB4C+0x18` – KongGroundPoundHelper::RunningSlapRollFromJumpWithNoAnalogTimeout(CStateManager const&, CPlayer const&) |
| `0x0027BBAC` | `BL` | `0x0027BB94+0x18` – KongGroundPoundHelper::RunningSlapRollIntoCreaturesBehavior(CStateManager const&, CPlayer const&) |
| `0x0027D2E4` | `BL` | `0x0027D284+0x60` – NPlayerUtils::IsPlayerPotentiallyAlive(CStateManager const&, CPlayer const&) |
| `0x0027D338` | `BL` | `0x0027D284+0xB4` – NPlayerUtils::IsPlayerPotentiallyAlive(CStateManager const&, CPlayer const&) |
| `0x0028FB08` | `BL` | `0x0028F9D8+0x130` – CBarrelCannonGOC::UpdatePlayerLaunchLogic(CStateManager&, float) |
| `0x0028FB28` | `BL` | `0x0028F9D8+0x150` – CBarrelCannonGOC::UpdatePlayerLaunchLogic(CStateManager&, float) |
| `0x00290DB0` | `BL` | `0x00290C2C+0x184` – CBarrelCannonGOC::KillAllInhabitants(CStateManager&) |
| `0x002CE154` | `BL` | `0x002CE13C+0x18` – CStateManagerGameData::SetPrimaryPlayer(CPlayer&) |
| `0x002F0C34` | `BL` | `0x002F0BE4+0x50` – CPlayerInteractionAdapter::BuildConditionsForCreature(CStateManager const&, CEntityGOC const&, IRulesConditions&) const |
| `0x002F113C` | `BL` | `0x002F1110+0x2C` – CPlayerInteractionAdapter::BuildConditionsForSeaLion(CStateManager const&, CEntityGOC const&, IRulesConditions&) const |
| `0x0033A9E8` | `BL` | `0x0033A92C+0xBC` – CHUDIOWin::UpdateInventoryLock(NPlayerState::EPlayerIndex, int, NPlayerState::EItemType) |
| `0x0033A9FC` | `BL` | `0x0033A92C+0xD0` – CHUDIOWin::UpdateInventoryLock(NPlayerState::EPlayerIndex, int, NPlayerState::EItemType) |
| `0x0033B7D0` | `BL` | `0x0033B464+0x36C` – CHUDIOWin::AreaLoaded() |
| `0x0033B878` | `BL` | `0x0033B464+0x414` – CHUDIOWin::AreaLoaded() |
| `0x0033B98C` | `BL` | `0x0033B464+0x528` – CHUDIOWin::AreaLoaded() |
| `0x0033BE3C` | `BL` | `0x0033BDE4+0x58` – CHUDIOWin::PlayerMounting(CStateManager&, CPlayer&, CPlayerModuleSlave::ESlaveMountTypes) |
| `0x0033BEBC` | `BL` | `0x0033BDE4+0xD8` – CHUDIOWin::PlayerMounting(CStateManager&, CPlayer&, CPlayerModuleSlave::ESlaveMountTypes) |
| `0x0033C0C4` | `BL` | `0x0033C0A4+0x20` – CHUDIOWin::PlayerFullyMounted(CStateManager&, CPlayer&) |
| `0x0035F474` | `BL` | `0x0035F310+0x164` – CSCAIOWin::SetupSCAObjects(IObjectStore&) |
| `0x0035FB20` | `BL` | `0x0035FADC+0x44` – CSCAIOWin::SetupSCAObject(IObjectStore&, CPlayer const&, dkcPas::ECharacterType) const |
| `0x00383648` | `BL` | `0x003835C8+0x80` – CPlayerModuleOffscreenIndicator::PreOwnerThink(CStateManager&, float) |
| `0x00383918` | `BL` | `0x00383890+0x88` – CPlayerModuleOffscreenIndicator::PostOwnerThink(CStateManager&, float) |
| `0x003840CC` | `BL` | `0x0038406C+0x60` – CPlayerModuleOffscreenIndicator::GetPlayerAsRespawnBarrel(CStateManager const&, CPlayer const&) const |
| `0x00384258` | `BL` | `0x003841EC+0x6C` – CPlayerModuleOffscreenIndicator::GetPlayerBoundingBox(CStateManager const&) const |
| `0x00391EF4` | `BL` | `0x00391C28+0x2CC` – CActionDetectorGOC::CheckStartNewReaction(CStateManager&, int, rstl::optional_object<CAnimPlaybackParms, false>&) |
| `0x003A6CC8` | `BL` | `0x003A69B4+0x314` – CBaboonManagerGOC::BaboonHit(CStateManager&, int) |
| `0x003AD858` | `BL` | `0x003AD7B0+0xA8` – CBarrelBalloonGOC::ShouldAutoPop(CStateManager const&, CPlayer const&) const |
| `0x003AD868` | `BL` | `0x003AD7B0+0xB8` – CBarrelBalloonGOC::ShouldAutoPop(CStateManager const&, CPlayer const&) const |
| `0x003ADEBC` | `BL` | `0x003ADDDC+0xE0` – CBarrelBalloonGOC::StartPlayerRejoin(CStateManager&, CPlayer&, CPlayer const&) |
| `0x003ADEC8` | `BL` | `0x003ADDDC+0xEC` – CBarrelBalloonGOC::StartPlayerRejoin(CStateManager&, CPlayer&, CPlayer const&) |
| `0x003AE1D0` | `BL` | `0x003AE164+0x6C` – CBarrelBalloonGOC::PickMotionState(CStateManager&) |
| `0x003AE1E8` | `BL` | `0x003AE164+0x84` – CBarrelBalloonGOC::PickMotionState(CStateManager&) |
| `0x003AEB50` | `BL` | `0x003AEB20+0x30` – CBarrelBalloonGOC::HandleShakeInput(CPlayer&, CStateManager&) |
| `0x003E9BBC` | `BL` | `0x003E9ADC+0xE0` – CGrabThrowGOC::HandlePreDeathEvents(CStateManager&, CGrabThrowGOC::ESpawnEffects, TUniqueId) |
| `0x003F38B8` | `BL` | `0x003F3820+0x98` – CImpostorGOC::OnLoad(CStateManager&) |
| `0x003F487C` | `BL` | `0x003F4840+0x3C` – CImpostorGOC::SetDepthBias(CStateManager&, float) |
| `0x0040ADF0` | `BL` | `0x0040ADA8+0x48` – CMineCartProxyGOC::OnAction_EnableTravelAtMinimumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040AE90` | `BL` | `0x0040AE4C+0x44` – CMineCartProxyGOC::OnAction_DisableTravelAtMinimumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040AF34` | `BL` | `0x0040AEEC+0x48` – CMineCartProxyGOC::OnAction_EnableMaximumSpeedLimit(CStateManager&, CScriptMsg const&) |
| `0x0040AFD4` | `BL` | `0x0040AF90+0x44` – CMineCartProxyGOC::OnAction_DisableMaximumSpeedLimit(CStateManager&, CScriptMsg const&) |
| `0x0040B074` | `BL` | `0x0040B030+0x44` – CMineCartProxyGOC::OnAction_SetAcceleration(CStateManager&, CScriptMsg const&) |
| `0x0040B118` | `BL` | `0x0040B0D4+0x44` – CMineCartProxyGOC::OnAction_ResetAcceleration(CStateManager&, CScriptMsg const&) |
| `0x0040B1BC` | `BL` | `0x0040B178+0x44` – CMineCartProxyGOC::OnAction_SetDeceleration(CStateManager&, CScriptMsg const&) |
| `0x0040B260` | `BL` | `0x0040B21C+0x44` – CMineCartProxyGOC::OnAction_ResetDeceleration(CStateManager&, CScriptMsg const&) |
| `0x0040B304` | `BL` | `0x0040B2C0+0x44` – CMineCartProxyGOC::OnAction_SetDecelerationToMinimumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B3A8` | `BL` | `0x0040B364+0x44` – CMineCartProxyGOC::OnAction_ResetDecelerationToMinimumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B44C` | `BL` | `0x0040B408+0x44` – CMineCartProxyGOC::OnAction_SetInitialSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B4F0` | `BL` | `0x0040B4AC+0x44` – CMineCartProxyGOC::OnAction_ResetInitialSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B594` | `BL` | `0x0040B550+0x44` – CMineCartProxyGOC::OnAction_SetMinimumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B638` | `BL` | `0x0040B5F4+0x44` – CMineCartProxyGOC::OnAction_ResetMinimumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B6DC` | `BL` | `0x0040B698+0x44` – CMineCartProxyGOC::OnAction_SetMaximumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B780` | `BL` | `0x0040B73C+0x44` – CMineCartProxyGOC::OnAction_ResetMaximumSpeed(CStateManager&, CScriptMsg const&) |
| `0x0040B824` | `BL` | `0x0040B7E0+0x44` – CMineCartProxyGOC::OnAction_SetAllowPlatformAdvancement(CStateManager&, CScriptMsg const&) |
| `0x0040B8C8` | `BL` | `0x0040B884+0x44` – CMineCartProxyGOC::OnAction_ResetAllowPlatformAdvancement(CStateManager&, CScriptMsg const&) |
| `0x0040B98C` | `BL` | `0x0040B948+0x44` – CMineCartProxyGOC::OnAction_PrepareEOLSequence(CStateManager&, CScriptMsg const&) |
| `0x0040BA2C` | `BL` | `0x0040B9E8+0x44` – CMineCartProxyGOC::OnAction_StartEOLSequence(CStateManager&, CScriptMsg const&) |
| `0x0040BACC` | `BL` | `0x0040BA88+0x44` – CMineCartProxyGOC::OnAction_StopRolling(CStateManager&, CScriptMsg const&) |
| `0x0040BB6C` | `BL` | `0x0040BB28+0x44` – CMineCartProxyGOC::OnAction_Roll(CStateManager&, CScriptMsg const&) |
| `0x0040BC10` | `BL` | `0x0040BBCC+0x44` – CMineCartProxyGOC::OnAction_EnableJump(CStateManager&, CScriptMsg const&) |
| `0x0040BCB4` | `BL` | `0x0040BC70+0x44` – CMineCartProxyGOC::OnAction_DisableJump(CStateManager&, CScriptMsg const&) |
| `0x0040BD58` | `BL` | `0x0040BD14+0x44` – CMineCartProxyGOC::OnAction_EnableSound(CStateManager&, CScriptMsg const&) |
| `0x0040BDF8` | `BL` | `0x0040BDB4+0x44` – CMineCartProxyGOC::OnAction_DisableSound(CStateManager&, CScriptMsg const&) |
| `0x0040BE9C` | `BL` | `0x0040BE54+0x48` – CMineCartProxyGOC::OnAction_EnableLedgeAssist(CStateManager&, CScriptMsg const&) |
| `0x0040BF3C` | `BL` | `0x0040BEF8+0x44` – CMineCartProxyGOC::OnAction_DisableLedgeAssist(CStateManager&, CScriptMsg const&) |
| `0x0040BFE8` | `BL` | `0x0040BF98+0x50` – CMineCartProxyGOC::OnAction_QueryDamagedState(CStateManager&, CScriptMsg const&) |
| `0x0040C6E8` | `BL` | `0x0040C690+0x58` – CMineCartProxyGOC::ForEachMineCart(CStateManager&, void (CMineCartProxyGOC::*)(CStateManager&, CMineCart&)) |
| `0x0040C754` | `BL` | `0x0040C690+0xC4` – CMineCartProxyGOC::ForEachMineCart(CStateManager&, void (CMineCartProxyGOC::*)(CStateManager&, CMineCart&)) |
| `0x0041734C` | `BL` | `0x004172DC+0x70` – CPlayerActionDetectorGOC::CheckBoundsAndQueueMessages(CStateManager&, TUniqueId, NScriptMsg::EScriptEvent, NScriptMsg::EScriptEvent) |
| `0x004174EC` | `BL` | `0x004174D8+0x14` – CPlayerActionDetectorGOC::CheckPlayerType(CPlayer const*) const |
| `0x0041CB34` | `BL` | `0x0041CAB4+0x80` – CPlayerActorGOC::OnAction_Play(CStateManager&, CScriptMsg const&) |
| `0x0041D8E0` | `BL` | `0x0041D81C+0xC4` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041D9E0` | `BL` | `0x0041D81C+0x1C4` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041E1B8` | `BL` | `0x0041E178+0x40` – CPlayerActorGOC::GetAnimationData(CPlayer const&, CStateManager const&) const |
| `0x0041E2D4` | `BL` | `0x0041E294+0x40` – CPlayerActorGOC::RenderMethod(CPlayer const&, CStateManager&) |
| `0x0041FF70` | `BL` | `0x0041FF50+0x20` – CPlayerKeyframeGOC::GetPlayerKeyframeAnimInfo(CStateManager const&, CPlayer const&) const |
| `0x0041FFB4` | `BL` | `0x0041FF50+0x64` – CPlayerKeyframeGOC::GetPlayerKeyframeAnimInfo(CStateManager const&, CPlayer const&) const |
| `0x0042002C` | `BL` | `0x0041FF50+0xDC` – CPlayerKeyframeGOC::GetPlayerKeyframeAnimInfo(CStateManager const&, CPlayer const&) const |
