# Duplicate primary character – direkte Kern-Xrefs



### `001FA354` – CPlayer::GetCharacterType() const

Direkte Referenzen: **282**

| Callsite | Typ | Caller |
|---:|---|---|
| `0x0021F594` | `BL` | `0x0021F4F4+0xA0` – CPlayerModuleBarrelCannon::BarrelCannonIdle(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x0021F670` | `BL` | `0x0021F5F8+0x78` – CPlayerModuleBarrelCannon::BarrelCannonFidget(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x002286C4` | `BL` | `0x002284A4+0x220` – CPlayerModuleCling::ProcessClingStateNormal(CPlayer&, CStateManager&, float) |
| `0x00228A50` | `BL` | `0x002289F0+0x60` – CPlayerModuleCling::SetConfigForOrientation(CStateManager&, CPlayer&, float, bool) |
| `0x00229164` | `BL` | `0x00228EEC+0x278` – CPlayerModuleCling::ProcessClingStateToCling(CPlayer&, CStateManager&, float) |
| `0x0022A444` | `BL` | `0x0022A430+0x14` – CPlayerModuleCling::GetOctantConfig(CPlayer const&, dkcPas::ECling2SurfaceOctant) const |
| `0x0022B1BC` | `BL` | `0x0022AFC8+0x1F4` – CPlayerModuleCling::ShouldCling2Turn(CStateManager const&) const |
| `0x0022C388` | `BL` | `0x0022C25C+0x12C` – CPlayerModuleCling::CanPlayerWalkOffCling(CPlayer const&, CClingPathControlGOC const&, float) const |
| `0x0022DF90` | `BL` | `0x0022DDE8+0x1A8` – CPlayerModuleCling::TeleportToTransformOverride(CStateManager const&, CPlayer const&, CTransform4f&) const |
| `0x0022F608` | `BL` | `0x0022F578+0x90` – CPlayerModuleCling::ShouldCling2Transition(CStateManager&, CFSMProperties const&) const |
| `0x0022F87C` | `BL` | `0x0022F6D0+0x1AC` – CPlayerModuleCling::ShouldCling2SkidTurn(CStateManager&, CFSMProperties const&) const |
| `0x00230BA4` | `BL` | `0x002309A0+0x204` – CPlayerModuleCling::Cling2Transition(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x00232E04` | `BL` | `0x00232D64+0xA0` – CPlayerModuleCling::PredictTransitionEndPose(CPlayer const&, float, float) const |
| `0x00233C64` | `BL` | `0x00233C1C+0x48` – CPlayerModuleCrouch::GetCrouchType(CPlayer const&, CStateManager const&) const |
| `0x002343B4` | `BL` | `0x00234378+0x3C` – CPlayerModuleFunkyJump::AnimationThink(CStateManager&, float, float) |
| `0x00234A78` | `BL` | `0x00234A54+0x24` – CPlayerModuleFunkyJump::UpdateProceduralAnimation(CStateManager&, float) |
| `0x00234C2C` | `BL` | `0x00234B14+0x118` – CPlayerModuleFunkyJump::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00234FBC` | `BL` | `0x00234FA8+0x14` – CPlayerModuleFunkyJump::IsOnSpikesInShieldState(CStateManager&, CFSMProperties const&) const |
| `0x00235188` | `BL` | `0x00234FD8+0x1B0` – CPlayerModuleFunkyJump::SetupIntoFunkyJump(CStateManager&, CFSMProperties const&, float) |
| `0x00235394` | `BL` | `0x00235310+0x84` – CPlayerModuleFunkyJump::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x002354AC` | `BL` | `0x00235494+0x18` – CPlayerModuleFunkyJump::JumpHeldByFunkyJumpController(CStateManager const&, CPlayer const&) const |
| `0x002356C8` | `BL` | `0x00235634+0x94` – CPlayerModuleFunkyJump::UpdateFunkyJumpState(CStateManager&, CPlayer&) |
| `0x00235718` | `BL` | `0x00235634+0xE4` – CPlayerModuleFunkyJump::UpdateFunkyJumpState(CStateManager&, CPlayer&) |
| `0x002357F4` | `BL` | `0x00235634+0x1C0` – CPlayerModuleFunkyJump::UpdateFunkyJumpState(CStateManager&, CPlayer&) |
| `0x00235868` | `BL` | `0x00235634+0x234` – CPlayerModuleFunkyJump::UpdateFunkyJumpState(CStateManager&, CPlayer&) |
| `0x002358C8` | `BL` | `0x00235634+0x294` – CPlayerModuleFunkyJump::UpdateFunkyJumpState(CStateManager&, CPlayer&) |
| `0x0023595C` | `BL` | `0x00235934+0x28` – CPlayerModuleFunkyJump::UpdateFunkyGlow(CStateManager&, CPlayer&, float) |
| `0x002359E4` | `BL` | `0x00235934+0xB0` – CPlayerModuleFunkyJump::UpdateFunkyGlow(CStateManager&, CPlayer&, float) |
| `0x00235BDC` | `BL` | `0x00235BB8+0x24` – CPlayerModuleFunkyJump::UpdateHoverState(CPlayer const&, CPhysicsObject const&) |
| `0x00235D20` | `BL` | `0x00235D0C+0x14` – CPlayerModuleFunkyJump::IsOnSpikesInShieldState(CStateManager const&) const |
| `0x00236994` | `BL` | `0x00236980+0x14` – CPlayerModuleFunkyJump::IsHoverEnabled(CPlayer const&) const |
| `0x002379A8` | `BL` | `0x00237904+0xA4` – CPlayerModuleGrab::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x00237D5C` | `BL` | `0x00237D4C+0x10` – CPlayerModuleGrab::CPlayerGrabObjectInterface::GetGrabSource(CStateManager const&) const |
| `0x0023D4F0` | `BL` | `0x0023D458+0x98` – CPlayerModuleGreenBalloon::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x0023D524` | `BL` | `0x0023D458+0xCC` – CPlayerModuleGreenBalloon::AllowAction(CStateManager const&, NPlayerModules::EAction) const |
| `0x0023FD9C` | `BL` | — – UNAUFGELÖST |
| `0x00240920` | `BL` | `0x002408F4+0x2C` – CPlayerModuleHealth::AreaLoaded(CStateManager&) |
| `0x00240E10` | `BL` | `0x00240DD8+0x38` – CPlayerModuleHealth::GetRemainingHP(CStateManager const&) const |
| `0x00240FB0` | `BL` | `0x00240F0C+0xA4` – CPlayerModuleHealth::CheckAndSpawnHUDBarrelMinorKong(CStateManager&, float) |
| `0x00241014` | `BL` | `0x00240F0C+0x108` – CPlayerModuleHealth::CheckAndSpawnHUDBarrelMinorKong(CStateManager&, float) |
| `0x00241584` | `BL` | `0x00241534+0x50` – CPlayerModuleHealth::CanSpawnHUDBarrelMinorKong(CStateManager&, dkcPas::ECharacterType&, NPlayerState::EItemType&, int&) const |
| `0x002416FC` | `BL` | `0x00241534+0x1C8` – CPlayerModuleHealth::CanSpawnHUDBarrelMinorKong(CStateManager&, dkcPas::ECharacterType&, NPlayerState::EItemType&, int&) const |
| `0x0024170C` | `BL` | `0x00241534+0x1D8` – CPlayerModuleHealth::CanSpawnHUDBarrelMinorKong(CStateManager&, dkcPas::ECharacterType&, NPlayerState::EItemType&, int&) const |
| `0x002419A8` | `BL` | `0x00241918+0x90` – CPlayerModuleHealth::HandleDamageToPlayer(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&, NPlayerShared::EDamageFromMaster) |
| `0x00241CC4` | `BL` | `0x00241BAC+0x118` – CPlayerModuleHealth::CalculateAndApplyPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&, NPlayerShared::EDamageFromMaster) |
| `0x00242254` | `BL` | `0x00242198+0xBC` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x00242370` | `BL` | `0x00242198+0x1D8` – CPlayerModuleHealth::CheckShieldActivation(CStateManager&, CDamageInfo const&) |
| `0x0024252C` | `BL` | `0x002424E4+0x48` – CPlayerModuleHealth::StartDamageRumble(CStateManager&) const |
| `0x00242598` | `BL` | `0x002424E4+0xB4` – CPlayerModuleHealth::StartDamageRumble(CStateManager&) const |
| `0x00242868` | `BL` | `0x002427C8+0xA0` – CPlayerModuleHealth::ApplyMountDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&) |
| `0x0024343C` | `BL` | `0x00243230+0x20C` – CPlayerModuleHealth::ApplySoloPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&, NPlayerState::EItemType, CPlayerModuleHealth::EDamageAbsorbedByOther) |
| `0x002435A4` | `BL` | `0x00243230+0x374` – CPlayerModuleHealth::ApplySoloPlayerDamage(CStateManager&, CEntityGOC const&, CDamageInfo const&, rstl::optional_object<CContactResult, false> const&, NPlayerState::EItemType, CPlayerModuleHealth::EDamageAbsorbedByOther) |
| `0x00243750` | `BL` | `0x002436E8+0x68` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x002437DC` | `BL` | `0x002436E8+0xF4` – CPlayerModuleHealth::Death(CStateManager&, CVector3f const&, NPlayerShared::EPlayerScriptEvent) |
| `0x00244170` | `BL` | `0x00244130+0x40` – CPlayerModuleHealth::ShouldPlayPostDeathLoop(CStateManager&, CFSMProperties const&) const |
| `0x0024453C` | `BL` | `0x0024445C+0xE0` – CPlayerModuleHealth::Dead(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x00244D80` | `BL` | `0x00244D70+0x10` – CPlayerModuleJump::ShouldHighAttackBounce(CPlayer const&) |
| `0x002460E8` | `BL` | `0x00246054+0x94` – CPlayerModuleJump::DefaultAttackBounceHandler(CStateManager&, CContactResult const&, EBounceType, SLdrPlayerAttackBounceData const&, unsigned int) |
| `0x00247638` | `BL` | `0x002475C4+0x74` – CPlayerModuleJump::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x0024BED0` | `BL` | `0x0024BD88+0x148` – CPlayerModuleMelee::SetMeleeApplied(CStateManager&, CEntityGOC const&) |
| `0x0024F0F8` | `BL` | `0x0024EFFC+0xFC` – CPlayerModuleMount::DismountRider(CStateManager&, CPlayerModuleMount::CRiderController&, float) |
| `0x0024F30C` | `BL` | `0x0024F29C+0x70` – CPlayerModuleMount::CanGrabRider(CStateManager const&, CPlayer const&) const |
| `0x0024F36C` | `BL` | `0x0024F29C+0xD0` – CPlayerModuleMount::CanGrabRider(CStateManager const&, CPlayer const&) const |
| `0x0024F598` | `BL` | `0x0024F524+0x74` – CPlayerModuleMount::CanBeGrabbedByRider(CStateManager const&, CPlayer const&) const |
| `0x0024F608` | `BL` | `0x0024F524+0xE4` – CPlayerModuleMount::CanBeGrabbedByRider(CStateManager const&, CPlayer const&) const |
| `0x0024F64C` | `BL` | `0x0024F638+0x14` – CPlayerModuleMount::CanGrabMount(CPlayer const&) const |
| `0x0025058C` | `BL` | `0x0025051C+0x70` – CPlayerModuleMount::GridMountRider(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x00250664` | `BL` | `0x002505DC+0x88` – CPlayerModuleMount::DamageKnockback(CStateManager&, CVector3f const&, float, rstl::optional_object<CContactResult, false> const&, NPlayerModules::EDamageKnockbackType) |
| `0x00250890` | `BL` | `0x00250838+0x58` – CPlayerModuleMount::ShouldDamageDismountRiderOnDamageKnockback(CStateManager const&) const |
| `0x002516B4` | `BL` | `0x0025164C+0x68` – CPlayerModuleMount::MountRider(CStateManager&, CPlayer&, CPlayerModuleMount::ELerpRider, CPlayerModuleMount::EForceMount) |
| `0x00251700` | `BL` | `0x0025164C+0xB4` – CPlayerModuleMount::MountRider(CStateManager&, CPlayer&, CPlayerModuleMount::ELerpRider, CPlayerModuleMount::EForceMount) |
| `0x00251824` | `BL` | `0x0025164C+0x1D8` – CPlayerModuleMount::MountRider(CStateManager&, CPlayer&, CPlayerModuleMount::ELerpRider, CPlayerModuleMount::EForceMount) |
| `0x002550C4` | `BL` | `0x0025509C+0x28` – CPlayerModulePogoStick::CanPogoStickJump(CStateManager&, CPlayer const&) const |
| `0x00255178` | `BL` | `0x00255160+0x18` – CPlayerModulePogoStick::JumpHeldByPogoStickController(CStateManager const&, CPlayer const&) const |
| `0x002551D8` | `BL` | `0x00255160+0x78` – CPlayerModulePogoStick::JumpHeldByPogoStickController(CStateManager const&, CPlayer const&) const |
| `0x00255798` | `BL` | `0x00255754+0x44` – CPlayerModuleShield::PostOwnerThink(CStateManager&, float) |
| `0x002562F0` | `BL` | `0x002562C4+0x2C` – CPlayerModuleShield::GetShieldModuleTarget(CStateManager const&) const |
| `0x00256454` | `BL` | `0x002563E0+0x74` – CPlayerModuleShield::GetOtherShieldModuleInMountChain(CStateManager const&, CPlayer const&, NPlayerState::EPlayerIndex) const |
| `0x002569B0` | `BL` | `0x00256954+0x5C` – CPlayerModuleSlave::PreOwnerAreaLoaded(CStateManager&) |
| `0x00257AF4` | `BL` | `0x00257A88+0x6C` – CPlayerModuleSlave::HasTransitionAnimations(CStateManager&, CFSMProperties const&) const |
| `0x00257BB4` | `BL` | `0x00257B30+0x84` – CPlayerModuleSlave::CheckJumpFromSlave(CStateManager&, CFSMProperties const&, float) |
| `0x00257CA0` | `BL` | `0x00257B30+0x170` – CPlayerModuleSlave::CheckJumpFromSlave(CStateManager&, CFSMProperties const&, float) |
| `0x002581D4` | `BL` | `0x00258058+0x17C` – CPlayerModuleSlave::TransitionToMount(CStateManager&, EFSMStateMsg, CFSMProperties const&, float) |
| `0x00258AA4` | `BL` | `0x002587C0+0x2E4` – CPlayerModuleSlave::EnterSlaveMode(CStateManager&, CMasterSlaveGOC&, unsigned int) |
| `0x00259FB8` | `BL` | `0x00259FA4+0x14` – CPlayerModuleRoll::IsInWaterSkipRoll(CStateManager&, CFSMProperties const&) const |
| `0x0025A52C` | `BL` | `0x0025A518+0x14` – CPlayerModuleRoll::IsInWaterSkipRoll(CStateManager const&) const |
| `0x00261DC4` | `BL` | `0x00261CF4+0xD0` – CPlayerModuleSwimming::PreOwnerThink(CStateManager&, float) |
| `0x00261E1C` | `BL` | `0x00261CF4+0x128` – CPlayerModuleSwimming::PreOwnerThink(CStateManager&, float) |
| `0x002631DC` | `BL` | `0x00262CB0+0x52C` – CPlayerModuleSwimming::OnNotifyEvent(CStateManager&, NPlayerModules::ENotifyEvent) |
| `0x00264510` | `BL` | `0x002644D4+0x3C` – CPlayerModuleSwimming::CheckAndConsumeBlueBalloon(CStateManager&, CPlayer&) |
| `0x002645EC` | `BL` | `0x002645B8+0x34` – CPlayerModuleSwimming::SetBreathMeter(CStateManager&, CPlayer&, float, float) |
| `0x00264D08` | `BL` | `0x00264C30+0xD8` – CPlayerModuleSwimming::InitializeAnchorTransitionState(CPlayer&, CSwimMovementState::ESwimState, CSwimMovementState::ESwimWaterTransition) |
| `0x00264D20` | `BL` | `0x00264C30+0xF0` – CPlayerModuleSwimming::InitializeAnchorTransitionState(CPlayer&, CSwimMovementState::ESwimState, CSwimMovementState::ESwimWaterTransition) |
| `0x00264D38` | `BL` | `0x00264C30+0x108` – CPlayerModuleSwimming::InitializeAnchorTransitionState(CPlayer&, CSwimMovementState::ESwimState, CSwimMovementState::ESwimWaterTransition) |
| `0x00267EC8` | `BL` | `0x00267DA4+0x124` – CPlayerModuleSwimmingJetBoost::PreOwnerThink(CStateManager&, float) |
