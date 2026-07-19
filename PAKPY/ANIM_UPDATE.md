# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 9

This is the authoritative current-state document. Runtime changes require a
regression test. Binary decoding, rig export, Blender conversion and complete
live-game pose reproduction are tracked separately.

## Current runtime pipeline

| File | Purpose |
|---|---|
| `anim_normal_clip_indices.py` | two-level node/channel bitmap parser |
| `anim_normal_clip_setup.py` | constants, quantization ranges and frame-stream start |
| `anim_normal_clip_frames.py` | key timing and record boundaries |
| `anim_normal_clip_values.py` | rotation/compact-vector/extended-vector payload decode |
| `anim_normal_clip_pose.py` | local-pose interpolation and optional SKEL remap |
| `anim_normal_clip_bind.py` | bind, root-anchor, hierarchy and render-matrix composition |
| `exact_skeletal_rig_patch.py` | preserves full SKEL matrices in GLB/BLEND rigs |
| `blender_normal_clip_action_script_patch.py` | Blender Action importer generator |
| `anim_capture_fit.py` | cyclic/subframe RenderDoc palette-to-clip matcher |
| `test_exact_skeletal_rig_patch.py` | exact rig and no-edit-bone regression tests |
| `test_anim_capture_fit.py` | capture parser and cyclic subframe tests |
| `anim_research/RenderDoc_idle_capture.md` | Pompy capture/timing analysis |
| `anim_research/Warus_level_posegraph.md` | level actor and clip-selection evidence |

`blender_normal_clip_action_v2_patch.py` remains in the repository as inactive
research code. It is not installed by `main.py` because its default residual
check rejected every Warus clip and silently produced zero Actions.

Exported normal clips receive:

```text
normal_clip_indices.*
normal_clip_setup.*
normal_clip_frames.*
normal_clip_values_file
normal_clip_pose_file
normal_clip_bind_file
```

Generated package files include:

```text
blender_import_normal_clip_actions.py
BLENDER_NORMAL_CLIP_ACTIONS.txt
```

## Current readiness

```text
ExeFS-derived normal_clip stream traversal: implemented and structurally tested
integer game-space matrix generation: implemented; visual accuracy still under validation
exact SKEL GLB/BLEND rest rig: fixed and matrix-tested
Blender Action playback: not yet end-to-end validated after the rig fix
Warus capture base clip and timing: identified as a_pompy_idle_ws, approximately 30 fps
strict complete live actor pose: pending posegraph/base-pose/procedural inputs
```

No marker-derived or prefix-mapped heuristic animation is accepted as a real
`normal_clip` timeline.

## Verified binary stages

| Address | Function | State |
|---:|---|---|
| `0x195BA8` | `LoadIdxData` | ported and structurally validated |
| `0x1969A4` | `LoadPairData` | ported and structurally validated |
| `0x196D88` | `LoadRotRange` | ported and structurally validated |
| `0x196E98` | vector range loader | ported and structurally validated |
| `0x197BE0` | `LoadSetupFrames` | structural traversal ported |
| `0x198A38` | duration descriptor helper | ported |
| `0x198B64` | rotation value reader | ported from the supplied ExeFS build |
| `0x198D48` | extended vector value reader | ported from the supplied ExeFS build |
| `0x198E4C` | packed duration decoder | ported |
| `0x198F40` | due-channel list builder | structurally ported |
| `0x199058` | `ProcessFrame` | traversal and compact-vector path ported |
| `0x1973BC` | local TRS interpolation/output | ported |
| `0x197900` | output/base-pose initialization | control flow understood; caller input still external |
| `0x12D57C` | optional quaternion SKEL remap | ported |
| `0x12D610` | optional translation SKEL remap | ported |
| `0x199360` | frame generation control | control flow understood |
| `0x12C930` | base absolute construction | ported |
| `0x12CA44` | inverse base absolute construction | ported |
| `0x12E830` | animation/bind relative CCoords | ported |
| `0x12E358` | 81-node absolute hierarchy | ported |
| `0x18AA40` | scale propagation | ported |
| `0x18AB48` | no-scale propagation | ported |
| `0x12E9A0` | 60-bone render transforms | normal path ported |

The re-uploaded ExeFS `main` has SHA-256
`018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21`,
matching the previously analyzed build. The address map therefore remains valid.

## Codec and pose rules supported by the ExeFS analysis

- Node/channel maps use two LSB-first bitmaps.
- Selector `1` is animated; selector `0` is constant.
- Node indices address the complete skeleton.
- Rotation records store quantized XYZ and reconstruct W.
- Compact vectors use unsigned 20-bit values; extended vectors use unsigned
  30-bit values.
- Rotation interpolation follows the shortest quaternion path.
- Translation and scale interpolate component-wise.
- Missing channels can inherit an input/base pose in the game. Identity is only
  the no-input fallback.
- Animation and bind compose as quaternion `animation * bind`, scale product and
  translation sum.
- Render matrices are `currentAbsolute[node] * inverseBaseAbsolute[node]` in SKEL
  skin order.
- For the supplied Warus capture the optional SKEL remap must remain disabled.

## Decoder validation and its limitation

Across the 30 supplied Warus clips, the current parser consumes every expected
record, produces finite TRS/matrix values and covers every declared key timeline.
Those checks prove stream consistency; they do **not** by themselves prove that a
Blender Action is visually accurate.

The reported severe start distortion and back-and-forth movement remain valid
end-to-end failures until a newly exported exact rig is tested in Blender.

## RenderDoc result

The level PAK selects `a_pompy_idle_ws` for the captured Ledge Guardian. A fit of
all 30 Warus clips against the 41 chronological GPU palettes gives:

```text
best clip:                    a_pompy_idle_ws
interpreted loop length:      30 frames
capture 1 time:               approximately 27.5
capture step:                 approximately 0.5 ANIM frames
render/clip rate:             approximately 60 Hz / 30 fps
absolute RMSE:                0.13559
motion RMSE:                  0.00163
centered residual RMSE:       0.01191

b_idle_1_ws absolute RMSE:    0.60129
b_idle_1_ws motion RMSE:      0.00888
```

This identifies the most likely clip and timing. It does not establish that every
bone transform, initial pose or Blender rest conversion is correct.

## Confirmed rig-export defect and fix

The former GLB path discarded the rotation part of each SKEL joint matrix and
created translation-only joints. `skeletal_tail_patch.py` then reconstructed
orientations from parent/child directions. Its Blender generation script moved
every child head to the parent tail and enabled connected bones. Both operations
changed the rest armature.

Measured against the supplied Warus SKEL, the former generated GLB had:

```text
rest-joint position residual median:   0.32135
rest-joint position residual maximum:  1.07608
rotation-matrix RMSE median:            0.80214
rotation-matrix RMSE maximum:           0.94281
```

`exact_skeletal_rig_patch.py` now:

- writes each joint's full local matrix derived from the original SKEL global
  matrices;
- writes the original SKEL inverse-bind matrices;
- imports the GLB into Blender without entering armature Edit Mode;
- never moves bone heads, tails or connection flags.

On the same Warus data, reconstructed global rest matrices after the patch match
the SKEL matrices to about `1e-15`; inverse-bind differences are about `1e-7`,
which is the expected float32 storage error.

Existing exported GLB/BLEND files remain wrong and must be regenerated. The fix
only applies to newly extracted Character/Model packages.

## Blender Action mapping

The active importer estimates one game-to-Blender similarity transform and then
applies a per-bone rest correction:

```text
O_b = inverse(C * gameRestGlobal_b) * blenderRestGlobal_b
M_b(frame) = C * gameCurrentGlobal_b(frame) * O_b
```

With the former fabricated connected rig, this correction operated around wrong
rest matrices. The exact-rig patch removes that known source of distortion. A
real Blender run is still required before the Action path can be called accurate.

## Remaining validation

1. re-extract Warus using the current `main` branch;
2. verify that the newly generated GLB/BLEND contains the exact-rig marker;
3. import `a_pompy_idle_ws` and compare its first frames and loop against the GPU
   palettes;
4. if distortion remains, compare Blender pose matrices against the exported
   `normal_clip_bind` matrices per bone and frame;
5. then resolve any remaining base-pose, posegraph or procedural contributions.

## Rejected assumptions

- the supplied captures are `b_idle_1_ws`;
- CSV number equals an integer ANIM frame number;
- finite values and complete key coverage prove visual correctness;
- a low temporal/motion error proves every bone pose is correct;
- translation-only glTF joints preserve the SKEL rest rig;
- connecting Blender bones by moving child heads is animation-safe;
- a high-residual all-bone Blender similarity fit is valid;
- `inverse(bind) * current` extracts the animation delta.
