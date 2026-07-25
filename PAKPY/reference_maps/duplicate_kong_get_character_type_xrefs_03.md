# CPlayer::GetCharacterType direct Xrefs – Teil 3

| `0x0042004C` | `BL` | `0x0041FF50+0xFC` – CPlayerKeyframeGOC::GetPlayerKeyframeAnimInfo(CStateManager const&, CPlayer const&) const |
| `0x004203E4` | `BL` | `0x004203D0+0x14` – CPlayerKeyframeGOC::IsSlavedToDK(CStateManager const&, CPlayer const&) const |
| `0x004220A4` | `BL` | `0x00422068+0x3C` – CPlayerProxyGOC::NotifyPlayerDamaged(CStateManager&, TUniqueId) |
| `0x004222C4` | `BL` | `0x00422218+0xAC` – CPlayerProxyGOC::ForEachProxyPlayer(CStateManager&, void (CPlayerProxyGOC::*)(CStateManager&, CPlayer*), TUniqueId) |
| `0x00422304` | `BL` | `0x00422218+0xEC` – CPlayerProxyGOC::ForEachProxyPlayer(CStateManager&, void (CPlayerProxyGOC::*)(CStateManager&, CPlayer*), TUniqueId) |
| `0x004223D4` | `BL` | `0x004223AC+0x28` – CPlayerProxyGOC::CacheIsOnGroundPlayerStatusImpl(CStateManager&, CPlayer*) |
| `0x00422758` | `BL` | `0x004226F4+0x64` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x00422784` | `BL` | `0x004226F4+0x90` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x0042279C` | `BL` | `0x004226F4+0xA8` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x004227A8` | `BL` | `0x004226F4+0xB4` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x004227EC` | `BL` | `0x004226F4+0xF8` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x00422818` | `BL` | `0x004226F4+0x124` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x00422830` | `BL` | `0x004226F4+0x13C` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x0042283C` | `BL` | `0x004226F4+0x148` – CPlayerProxyGOC::ForEachProxyPlayerVsRiderValidCombination(CStateManager&, bool (CPlayerProxyGOC::*)(CStateManager&, CPlayer*, CPlayer*)) |
| `0x00422F40` | `BL` | `0x00422F14+0x2C` – CPlayerProxyGOC::CheckAndSendPlayerOnGroundMessagesImpl(CStateManager&, CPlayer*) |
| `0x00422FFC` | `BL` | `0x00422FB8+0x44` – CPlayerProxyGOC::CacheInWaterPlayerStatusImpl(CStateManager&, CPlayer*) |
| `0x0042301C` | `BL` | `0x00422FB8+0x64` – CPlayerProxyGOC::CacheInWaterPlayerStatusImpl(CStateManager&, CPlayer*) |
| `0x00423064` | `BL` | `0x00423044+0x20` – CPlayerProxyGOC::CheckAndSendPlayerWaterStatusMessagesImpl(CStateManager&, CPlayer*) |
| `0x00423114` | `BL` | `0x00423100+0x14` – CPlayerProxyGOC::CheckPlayerVsRiderDuplicatesImpl(CStateManager&, CPlayer*, CPlayer*) |
| `0x00423120` | `BL` | `0x00423100+0x20` – CPlayerProxyGOC::CheckPlayerVsRiderDuplicatesImpl(CStateManager&, CPlayer*, CPlayer*) |
| `0x00427480` | `BL` | `0x004273E0+0xA0` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |
| `0x004274EC` | `BL` | `0x004273E0+0x10C` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |
| `0x004275C8` | `BL` | `0x00427594+0x34` – CPlayerSoundGOC::GetSoundCharacter(CStateManager const&, NPlayerState::EPlayerIndex) const |
| `0x00441E74` | `BL` | `0x00441DC0+0xB4` – CRespawnBalloonGOC::GetSpecialRider(CStateManager const&, CPlayer const&) const |
| `0x00441E80` | `BL` | `0x00441DC0+0xC0` – CRespawnBalloonGOC::GetSpecialRider(CStateManager const&, CPlayer const&) const |
| `0x00441E90` | `BL` | `0x00441DC0+0xD0` – CRespawnBalloonGOC::GetSpecialRider(CStateManager const&, CPlayer const&) const |
| `0x00448154` | `BL` | `0x004480BC+0x98` – CRocketBarrelProxyGOC::OnAction_SetHorizontalSpeedLimit(CStateManager&, CScriptMsg const&) |
| `0x00448284` | `BL` | `0x004481EC+0x98` – CRocketBarrelProxyGOC::OnAction_ResetHorizontalSpeedLimit(CStateManager&, CScriptMsg const&) |
| `0x004483B4` | `BL` | `0x0044831C+0x98` – CRocketBarrelProxyGOC::OnAction_SetVerticalAccelerationValues(CStateManager&, CScriptMsg const&) |
| `0x004484E8` | `BL` | `0x00448450+0x98` – CRocketBarrelProxyGOC::OnAction_ResetVerticalAccelerationValues(CStateManager&, CScriptMsg const&) |
| `0x004486AC` | `BL` | `0x00448614+0x98` – CRocketBarrelProxyGOC::OnAction_FlightPause(CStateManager&, CScriptMsg const&) |
| `0x004487E4` | `BL` | `0x0044874C+0x98` – CRocketBarrelProxyGOC::OnAction_FlightResume(CStateManager&, CScriptMsg const&) |
| `0x00448E68` | `BL` | `0x00448DD0+0x98` – CRocketBarrelProxyGOC::ForEachRocketBarrel(CStateManager&, void (CRocketBarrelProxyGOC::*)(CStateManager&, CRocketBarrel&)) |
| `0x00448F18` | `BL` | `0x00448DD0+0x148` – CRocketBarrelProxyGOC::ForEachRocketBarrel(CStateManager&, void (CRocketBarrelProxyGOC::*)(CStateManager&, CRocketBarrel&)) |
| `0x0045B89C` | `BL` | `0x0045B74C+0x150` – CSpawnPointGOC::DoSpawn(CStateManager&) |
| `0x0045BA10` | `BL` | `0x0045B74C+0x2C4` – CSpawnPointGOC::DoSpawn(CStateManager&) |
| `0x0045BA28` | `BL` | `0x0045B74C+0x2DC` – CSpawnPointGOC::DoSpawn(CStateManager&) |
| `0x0046515C` | `BL` | `0x00465018+0x144` – CTippyGOC::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |
| `0x004651B8` | `BL` | `0x00465018+0x1A0` – CTippyGOC::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |
| `0x00465430` | `BL` | `0x0046540C+0x24` – CTippyGOC::OnAction_ApplyWeightLeft(CStateManager&, CScriptMsg const&) |
| `0x004654C4` | `BL` | `0x004654A0+0x24` – CTippyGOC::OnAction_ApplyWeightRight(CStateManager&, CScriptMsg const&) |
| `0x004668DC` | `BL` | `0x0046689C+0x40` – CTippyGOC::AddWeight(CStateManager const&, TUniqueId, CTippyGOC::ESide) |
| `0x00466990` | `BL` | `0x00466950+0x40` – CTippyGOC::RemoveWeight(CStateManager const&, TUniqueId, CTippyGOC::ESide) |
| `0x0046C7C8` | `BL` | `0x0046C628+0x1A0` – CTriggerLogicGOC::PassesObjectTypeLogic(CStateManager const&, CEntityGOC const&, ITouchableGOC const&) const |
| `0x0046D050` | `BL` | `0x0046CF58+0xF8` – CTriggerLogicGOC::UpdateInhabitantState(CStateManager&, TUniqueId const&, CTouchableTriggerGOC&) |
| `0x004F0034` | `BL` | `0x004EFFD8+0x5C` – CImpostorManager::GetAdjustedRenderSortLayer(CPlayer const&, CImpostorGOC const&, CStateManager const&) const |
| `0x004F00C8` | `BL` | `0x004EFFD8+0xF0` – CImpostorManager::GetAdjustedRenderSortLayer(CPlayer const&, CImpostorGOC const&, CStateManager const&) const |
| `0x004F08E0` | `BL` | `0x004F0774+0x16C` – CImpostorManager::AddPlayerImpostor(CStateManager&, CImpostorGOC&) |
| `0x004F093C` | `BL` | `0x004F0774+0x1C8` – CImpostorManager::AddPlayerImpostor(CStateManager&, CImpostorGOC&) |
| `0x004F0B58` | `BL` | `0x004F0774+0x3E4` – CImpostorManager::AddPlayerImpostor(CStateManager&, CImpostorGOC&) |
| `0x004F0DE8` | `BL` | `0x004F0774+0x674` – CImpostorManager::AddPlayerImpostor(CStateManager&, CImpostorGOC&) |
| `0x004F0DF8` | `BL` | `0x004F0774+0x684` – CImpostorManager::AddPlayerImpostor(CStateManager&, CImpostorGOC&) |
| `0x005347B4` | `BL` | `0x00534460+0x354` – CActorModuleHealth::ApplyDamage(CStateManager&, TUniqueId, CDamageInfo const&) |
| `0x0056E7D8` | `BL` | `0x0056E688+0x150` – CPlayerModuleFlutterJump::PreOwnerThink(CStateManager&, float) |
| `0x0056E8B4` | `BL` | `0x0056E688+0x22C` – CPlayerModuleFlutterJump::PreOwnerThink(CStateManager&, float) |
| `0x0056F138` | `BL` | `0x0056F00C+0x12C` – CPlayerModuleFlutterJump::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x0056F1A4` | `BL` | `0x0056F00C+0x198` – CPlayerModuleFlutterJump::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x0056F580` | `BL` | `0x0056F530+0x50` – CPlayerModuleFlutterJump::SetHairSpinState(CStateManager&, CPlayerModuleFlutterJump::EHairSpinState) |
| `0x0056F5C8` | `BL` | `0x0056F530+0x98` – CPlayerModuleFlutterJump::SetHairSpinState(CStateManager&, CPlayerModuleFlutterJump::EHairSpinState) |
| `0x0056F63C` | `BL` | `0x0056F530+0x10C` – CPlayerModuleFlutterJump::SetHairSpinState(CStateManager&, CPlayerModuleFlutterJump::EHairSpinState) |
| `0x0056F698` | `BL` | `0x0056F530+0x168` – CPlayerModuleFlutterJump::SetHairSpinState(CStateManager&, CPlayerModuleFlutterJump::EHairSpinState) |
| `0x0056FC68` | `BL` | `0x0056FC50+0x18` – CPlayerModuleFlutterJump::JumpHeldByFlutterJumpController(CStateManager const&, CPlayer const&) const |
| `0x0056FCC8` | `BL` | `0x0056FC50+0x78` – CPlayerModuleFlutterJump::JumpHeldByFlutterJumpController(CStateManager const&, CPlayer const&) const |
| `0x0056FEF4` | `BL` | `0x0056FED0+0x24` – CPlayerModuleFlutterJump::CanFlutterJump(CStateManager&, CPlayer const&) const |
| `0x0056FF80` | `BL` | `0x0056FF68+0x18` – CPlayerModuleFlutterJump::IsFlutterJumpPlayerAlive(CStateManager const&, CPlayer const&) const |
| `0x005701BC` | `BL` | `0x005701A4+0x18` – CPlayerModuleFlutterJump::FlutterJumpOwnerPlayer(CStateManager&) const |
| `0x005702D4` | `BL` | `0x0057024C+0x88` – CPlayerModuleFlutterJump::UpdateHairSpinState(CStateManager&, CPlayer&, float) |
| `0x0057049C` | `BL` | `0x0057047C+0x20` – CPlayerModuleFlutterJump::StopSecondaryAnimation(CStateManager&, int) |
| `0x00570524` | `BL` | `0x00570500+0x24` – CPlayerModuleFlutterJump::StartHairSpinAnimation(CStateManager&) |
| `0x0057069C` | `BL` | `0x00570678+0x24` – CPlayerModuleFlutterJump::StartInactiveSpinAnimation(CStateManager&) |
| `0x00571738` | `BL` | `0x005716C8+0x70` – CPlayerModuleHeadTracking::UpdateSecondaryAnimation(CStateManager&, CPlayer&, CHeadTrackingAnimationBlendValues&, bool, float) |
| `0x005735B0` | `BL` | `0x005733B4+0x1FC` – CPlayerModuleKnockback::DamageKnockback(CStateManager&, CVector3f const&, float, rstl::optional_object<CContactResult, false> const&, NPlayerModules::EDamageKnockbackType) |
| `0x0057374C` | `BL` | `0x005733B4+0x398` – CPlayerModuleKnockback::DamageKnockback(CStateManager&, CVector3f const&, float, rstl::optional_object<CContactResult, false> const&, NPlayerModules::EDamageKnockbackType) |
| `0x0057559C` | `BL` | `0x00575514+0x88` – CPlayerModuleSpecialContactDamage::GetCollisionResolutionResponse(CStateManager const&, TUniqueId const&) const |
| `0x00575678` | `BL` | `0x00575514+0x164` – CPlayerModuleSpecialContactDamage::GetCollisionResolutionResponse(CStateManager const&, TUniqueId const&) const |
| `0x00575A94` | `BL` | `0x00575A3C+0x58` – CPlayerModuleSpecialContactDamage::CheckStateToApplyDamage(CStateManager&, CEntityGOC&) |
| `0x00575B68` | `BL` | `0x00575A3C+0x12C` – CPlayerModuleSpecialContactDamage::CheckStateToApplyDamage(CStateManager&, CEntityGOC&) |
| `0x00576580` | `BL` | `0x0057650C+0x74` – CPlayerModuleStalledDescent::PostOwnerThink(CStateManager&, float) |
| `0x00576750` | `BL` | `0x0057650C+0x244` – CPlayerModuleStalledDescent::PostOwnerThink(CStateManager&, float) |
| `0x00576C28` | `BL` | `0x00576B18+0x110` – CPlayerModuleStalledDescent::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00577DD4` | `BL` | `0x00577DB0+0x24` – CPlayerModuleStalledDescent::CanStallDescent(CStateManager&, CPlayer const&) const |
| `0x00577E60` | `BL` | `0x00577E48+0x18` – CPlayerModuleStalledDescent::IsStallDescentPlayerAlive(CStateManager&, CPlayer const&) const |
| `0x00577ED0` | `BL` | `0x00577EB8+0x18` – CPlayerModuleStalledDescent::JumpHeldByRocketController(CStateManager&, CPlayer const&) const |
| `0x00577F44` | `BL` | `0x00577EB8+0x8C` – CPlayerModuleStalledDescent::JumpHeldByRocketController(CStateManager&, CPlayer const&) const |
| `0x00578924` | `BL` | `0x00578908+0x1C` – CPlayerModuleSuperCombinedAbility::PostOwnerThink(CStateManager&, float) |
| `0x00578A8C` | `BL` | `0x00578A58+0x34` – CPlayerModuleSuperCombinedAbility::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x0057A684` | `BL` | `0x0057A594+0xF0` – CPlayerModuleSwimmingSpin::SwimSpinCycle(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x0057C8C4` | `BL` | `0x0057C818+0xAC` – CPlayerModuleTireInteraction::PostOwnerThink(CStateManager&, float) |
| `0x0057D084` | `BL` | `0x0057D038+0x4C` – CPlayerModuleTireInteraction::IssueJumpFromTire(CStateManager&, CFSMProperties const&, float) |
| `0x0057D540` | `BL` | `0x0057D52C+0x14` – CPlayerModuleTireInteraction::GetCurrentJumpTypeFromPlayerInput(CStateManager const&) const |
| `0x0057D5A4` | `BL` | `0x0057D588+0x1C` – CPlayerModuleTireInteraction::ShouldHighBounceFromPlayerInput(CPlayer const&, float) const |
| `0x0057D650` | `BL` | `0x0057D620+0x30` – CPlayerModuleTireInteraction::GetCurrentBounceType(CStateManager const&) const |
