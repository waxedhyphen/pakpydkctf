# Duplicate Kong – PlayerIndex und Slot-API Xrefs

### `001FA6AC` – CPlayer::GetPlayerIndex(CGameState const&) const

Direkte Referenzen: **17**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x0021E8BC` | `BL` | `0x0021E824+0x98` – CPlayerModuleBarrelCannon::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00220BE8` | `BL` | `0x00220B54+0x94` – CPlayerModuleBarrelCannon::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x0023FC50` | `BL` | `0x0023FBF8+0x58` – CPlayerModuleGroundPound::AddWindWakerImpulse(CStateManager&) |
| `0x00240E40` | `BL` | `0x00240DD8+0x68` – CPlayerModuleHealth::GetRemainingHP(CStateManager const&) const |
| `0x0024265C` | `BL` | `0x00242614+0x48` – CPlayerModuleHealth::ApplyPrimaryPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&) |
| `0x00264594` | `BL` | `0x002644D4+0xC0` – CPlayerModuleSwimming::CheckAndConsumeBlueBalloon(CStateManager&, CPlayer&) |
| `0x0027C6E8` | `BL` | `0x0027C678+0x70` – NPlayerUtils::CanSpawnPlayer(CStateManager const&, dkcPas::ECharacterType) |
| `0x0027C98C` | `BL` | `0x0027C910+0x7C` – NPlayerUtils::SpawnOtherPlayer(CStateManager&, dkcPas::ECharacterType, TUniqueId, dkcPas::ECharacterType) |
| `0x002A63CC` | `BL` | `0x002A6390+0x3C` – CPlayerGOC::SetInitialState(CStateManager&) |
| `0x0033BE18` | `BL` | `0x0033BDE4+0x34` – CHUDIOWin::PlayerMounting(CStateManager&, CPlayer&, CPlayerModuleSlave::ESlaveMountTypes) |
| `0x0038270C` | `BL` | `0x003826D4+0x38` – CPlayerController::Reset(CStateManager&) |
| `0x003AF0F4` | `BL` | `0x003AF074+0x80` – CBeatUpHandlerGOC::OnAction_SetupDetectionForOriginator(CStateManager&, CScriptMsg const&) |
| `0x003BD3A8` | `BL` | `0x003BD31C+0x8C` – CCheckpointGOC::FinishRespawn(CStateManager&) |
| `0x003BDAC8` | `BL` | `0x003BD954+0x174` – CCinematicCameraShotGOC::OnAction_PlayShot(CStateManager&, CScriptMsg const&) |
| `0x0041DB4C` | `BL` | `0x0041D81C+0x330` – CPlayerActorGOC::SetupPlayer(CStateManager&, CPlayer const*) |
| `0x0041FA00` | `BL` | `0x0041F9AC+0x54` – CPlayerKeyframeGOC::StartAnimation(CStateManager&, CScriptMsg const&) |
| `0x00427430` | `BL` | `0x004273E0+0x50` – CPlayerSoundGOC::GetTargetSoundCharactersForScriptAction(CStateManager&, CScriptMsg const&, rstl::reserved_vector<CPlayerSoundGOC::ESoundCharacter, 2>&) const |

### `003376BC` – CGameState::GetPlayerIndexByCharacterType(dkcPas::ECharacterType) const

Direkte Referenzen: **19**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x001FA3E4` | `BL` | `0x001FA3A4+0x40` – CPlayer::AddPlayerHitPoints(CStateManager&, CPlayer::EForceResetHP) const |
| `0x001FA6B8` | `B` | `0x001FA6AC+0xC` – CPlayer::GetPlayerIndex(CGameState const&) const |
| `0x001FA6F4` | `BL` | `0x001FA6BC+0x38` – CPlayer::RemovePlayerHitPoints(CStateManager&) |
| `0x001FB134` | `BL` | `0x001FB0C8+0x6C` – CPlayer::GetHealthItemForCurrentState(CStateManager const&, NPlayerState::EItemType) const |
| `0x001FB520` | `BL` | `0x001FB354+0x1CC` – CPlayer::ShouldPickupItem(CStateManager const&, NPlayerState::EItemType) const |
| `0x00240FBC` | `BL` | `0x00240F0C+0xB0` – CPlayerModuleHealth::CheckAndSpawnHUDBarrelMinorKong(CStateManager&, float) |
| `0x00241020` | `BL` | `0x00240F0C+0x114` – CPlayerModuleHealth::CheckAndSpawnHUDBarrelMinorKong(CStateManager&, float) |
| `0x0024237C` | `BL` | `0x00242198+0x1E4` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x00243448` | `BL` | `0x00243230+0x218` – CPlayerModuleHealth::ApplySoloPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&, NPlayerState::EItemType, CPlayerModuleHealth::EDamageAbsorbedByOther) |
| `0x002557A4` | `BL` | `0x00255754+0x50` – CPlayerModuleShield::PostOwnerThink(CStateManager&, float) |
| `0x002562FC` | `BL` | `0x002562C4+0x38` – CPlayerModuleShield::GetShieldModuleTarget(CStateManager const&) const |
| `0x0028FB14` | `BL` | `0x0028F9D8+0x13C` – CBarrelCannonGOC::UpdatePlayerLaunchLogic(CStateManager&, float) |
| `0x0028FB34` | `BL` | `0x0028F9D8+0x15C` – CBarrelCannonGOC::UpdatePlayerLaunchLogic(CStateManager&, float) |
| `0x003D1790` | `BL` | `0x003D1764+0x2C` – CDialogPanelGOC::HandleSwimmingDisplay(CStateManager&, float) |
| `0x00452BB4` | `BL` | `0x00452B70+0x44` – CShopInstanceGOC::ChooseMessageFilters(CStateManager&) |
| `0x00452BC4` | `BL` | `0x00452B70+0x54` – CShopInstanceGOC::ChooseMessageFilters(CStateManager&) |
| `0x00452BD4` | `BL` | `0x00452B70+0x64` – CShopInstanceGOC::ChooseMessageFilters(CStateManager&) |
| `0x00452BE4` | `BL` | `0x00452B70+0x74` – CShopInstanceGOC::ChooseMessageFilters(CStateManager&) |
| `0x00452BF4` | `BL` | `0x00452B70+0x84` – CShopInstanceGOC::ChooseMessageFilters(CStateManager&) |

### `002CDB1C` – CStateManagerGameData::GetPrimaryPlayer(NPlayerState::EPrimaryPlayer, NPlayerState::EPlayerFlags) const

Direkte Referenzen: **16**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x0021E784` | `BL` | `0x0021E738+0x4C` – CPlayerModuleBarrelCannon::GetOverrideTouchBounds(CStateManager const&) const |
| `0x0026E060` | `BL` | `0x0026DF8C+0xD4` – CPlayerModuleTeleport::ShouldTeleport(CStateManager const&) const |
| `0x0027C47C` | `BL` | `0x0027C44C+0x30` – NPlayerUtils::GetPlayerToTeleportTo(CPlayer const&, CStateManager const&) |
| `0x0027C4B0` | `BL` | `0x0027C44C+0x64` – NPlayerUtils::GetPlayerToTeleportTo(CPlayer const&, CStateManager const&) |
| `0x0027C4E4` | `BL` | `0x0027C44C+0x98` – NPlayerUtils::GetPlayerToTeleportTo(CPlayer const&, CStateManager const&) |
| `0x0027C518` | `BL` | `0x0027C44C+0xCC` – NPlayerUtils::GetPlayerToTeleportTo(CPlayer const&, CStateManager const&) |
| `0x0027C54C` | `BL` | `0x0027C44C+0x100` – NPlayerUtils::GetPlayerToTeleportTo(CPlayer const&, CStateManager const&) |
| `0x003BDA50` | `BL` | `0x003BD954+0xFC` – CCinematicCameraShotGOC::OnAction_PlayShot(CStateManager&, CScriptMsg const&) |
| `0x003BDB50` | `BL` | `0x003BD954+0x1FC` – CCinematicCameraShotGOC::OnAction_PlayShot(CStateManager&, CScriptMsg const&) |
| `0x0043862C` | `BL` | `0x004385C0+0x6C` – CRambiCrateGOC::PlayersOverlapCrateBounds(CStateManager const&) const |
| `0x0046CFE4` | `BL` | `0x0046CF58+0x8C` – CTriggerLogicGOC::UpdateInhabitantState(CStateManager&, TUniqueId const&, CTouchableTriggerGOC&) |
| `0x004BE920` | `BL` | `0x004BE8C4+0x5C` – CBopJumpOnPlayerJumpedJumpTypeData::CanJump(CStateManager const&, CEntityGOC const&) const |
| `0x004E74D8` | `BL` | — – UNAUFGELÖST |
| `0x004EDAE4` | `BL` | `0x004EDA88+0x5C` – CTargetSelector::FindBestTarget(CStateManager const&, CEntityGOC const&, ITargetSelector::EDirection) const |
| `0x004EE5F4` | `BL` | `0x004EE598+0x5C` – CTargetSelectorOffScreen::FindBestTarget(CStateManager const&, CEntityGOC const&, ITargetSelector::EDirection) const |
| `0x004EEEC8` | `BL` | `0x004EEDBC+0x10C` – CTargetSelectorRaycast::CalculateFirstPlayerHitId(CStateManager const&, CEntityGOC const&) const |

### `002CDBD8` – CStateManagerGameData::PrimaryPlayer(NPlayerState::EPrimaryPlayer, NPlayerState::EPlayerFlags)

Direkte Referenzen: **19**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x00243968` | `BL` | `0x002436E8+0x280` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x0024398C` | `BL` | `0x002436E8+0x2A4` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x002439B0` | `BL` | `0x002436E8+0x2C8` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x002439D4` | `BL` | `0x002436E8+0x2EC` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x002439F8` | `BL` | `0x002436E8+0x310` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x00291B60` | `BL` | `0x002918B0+0x2B0` – CBarrelCannonGOC::GrabPlayer(CStateManager&, CPlayer*) |
| `0x00295584` | `BL` | `0x00295530+0x54` – CClingPathControlGOC::OnAction_Delete(CStateManager&, CScriptMsg const&) |
| `0x002955B4` | `BL` | `0x00295530+0x84` – CClingPathControlGOC::OnAction_Delete(CStateManager&, CScriptMsg const&) |
| `0x002955E4` | `BL` | `0x00295530+0xB4` – CClingPathControlGOC::OnAction_Delete(CStateManager&, CScriptMsg const&) |
| `0x00295614` | `BL` | `0x00295530+0xE4` – CClingPathControlGOC::OnAction_Delete(CStateManager&, CScriptMsg const&) |
| `0x00295644` | `BL` | `0x00295530+0x114` – CClingPathControlGOC::OnAction_Delete(CStateManager&, CScriptMsg const&) |
| `0x0033B6D8` | `BL` | `0x0033B464+0x274` – CHUDIOWin::AreaLoaded() |
| `0x0041C7CC` | `BL` | `0x0041C728+0xA4` – CPlayerActorGOC::AcceptScriptMsg(CStateManager&, CScriptMsg const&) |
| `0x0041CA5C` | `BL` | `0x0041C9F4+0x68` – CPlayerActorGOC::OnAction_SyncPlayer(CStateManager&, CScriptMsg const&) |
| `0x0041CC84` | `BL` | `0x0041CAB4+0x1D0` – CPlayerActorGOC::OnAction_Play(CStateManager&, CScriptMsg const&) |
| `0x0042593C` | `BL` | `0x004255C0+0x37C` – CPlayerRespawnGOC::Think(CStateManager&, float) |
| `0x00526208` | `BL` | `0x00526148+0xC0` – CActorModuleStack::SetStackIsFallingRules(CStateManager&, bool) |
| `0x00541B40` | `BL` | `0x00541AEC+0x54` – CActorModulePolarBearController::MegaLeapHurlPlayers(CStateManager&) const |
| `0x00541D90` | `BL` | `0x00541D3C+0x54` – CActorModulePolarBearController::MegaSlamHurlPlayers(CStateManager&) const |
