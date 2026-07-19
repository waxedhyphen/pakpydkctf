# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 8

This is the authoritative current-state document. Runtime changes require a
regression test. Isolated resource playback, Blender conversion and strict
live-game pose reproduction are tracked separately.

## Current runtime pipeline

| File | Purpose |
|---|---|
| `anim_normal_clip_indices.py` | exact two-level node/channel bitmap parser |
| `anim_normal_clip_setup.py` | constants, quantization ranges and frame-stream start |
| `anim_normal_clip_frames.py` | exact key timing and record boundaries |
| `anim_normal_clip_values.py` | rotation/compact-vector/extended-vector payload decode |
| `anim_normal_clip_pose.py` | local-pose interpolation and optional SKEL remap |
| `anim_normal_clip_bind.py` | bind, root-anchor, hierarchy and render-matrix composition |
| `blender_normal_clip_action_script_patch.py` | base Blender Action script generator |
| `blender_normal_clip_action_v2_patch.py` | guarded basis, split FPS, loop and capture-fit upgrade |
| `anim_capture_fit.py` | cyclic/subframe RenderDoc palette-to-clip matcher |
| `test_anim_capture_fit.py` | capture parser and cyclic subframe regression tests |
| `test_blender_normal_clip_action_generator.py` | generated-script, timing, basis-guard and loop tests |
| `anim_research/RenderDoc_idle_capture.md` | corrected Pompy capture analysis |
| `anim_research/Warus_level_posegraph.md` | level actor and clip-selection evidence |
| `anim_research/warus_pompy_capture_fit.*` | machine-readable 30-clip ranking |

Exported normal clips receive:

```text
normal_clip_indices.*
normal_clip_setup.*
normal_clip_frames.*
normal_clip_values_file
normal_clip_pose_file
normal_clip_bind_file
```

Generated package tools include:

```text
blender_import_normal_clip_actions.py
BLENDER_NORMAL_CLIP_ACTIONS.txt
anim_capture_fit.py
ANIM_CAPTURE_FIT.txt
```

## Current readiness

```text
normal_clip binary decode and integer game poses: ready
isolated Blender Action generation: ready with guarded basis validation
Warus capture base clip and timing: identified
strict complete live actor pose: pending additional actor/posegraph inputs
```

No marker-derived or prefix-mapped heuristic animation is accepted as a real
`normal_clip` timeline.

## Verified binary stages

| Address | Function | State |
|---:|---|---|
| `0x195BA8` | `LoadIdxData` | fully ported/validated |
| `0x1969A4` | `LoadPairData` | fully ported/validated |
| `0x196D88` | `LoadRotRange` | fully ported/validated |
| `0x196E98` | vector range loader | fully ported/validated |
| `0x197BE0` | `LoadSetupFrames` | structural traversal fully ported |
| `0x198A38` | duration descriptor helper | fully ported |
| `0x198B64` | rotation value reader | payload fully ported |
| `0x198D48` | extended vector value reader | payload fully ported |
| `0x198E4C` | packed duration decoder | fully ported |
| `0x198F40` | due-channel list builder | structurally ported |
| `0x199058` | `ProcessFrame` | traversal plus compact vector payload ported |
| `0x1973BC` | local TRS interpolation/output | fully ported/validated |
| `0x197900` | output/base-pose initialization | structurally ported |
| `0x12D57C` | optional quaternion SKEL remap | fully ported |
| `0x12D610` | optional translation SKEL remap | fully ported |
| `0x199360` | frame generation control | control flow understood |
| `0x11A490` | `CCoords::x_y_ss` | fully ported |
| `0x12C558` | layout start/anchor discovery | relevant fields fully ported |
| `0x12C930` | base absolute construction | fully ported |
| `0x12CA44` | inverse base absolute construction | fully ported |
| `0x12E830` | animation/bind relative CCoords | fully ported |
| `0x12E358` | 81-node absolute hierarchy | fully ported |
| `0x18AA40` | scale propagation | fully ported |
| `0x18AB48` | no-scale propagation | fully ported |
| `0x12E9A0` | 60-bone render transforms | normal path fully ported |

## Verified codec and pose rules

- Node/channel maps are two-level LSB-first base and selector bitmaps.
- Selector `1` is animated; selector `0` is constant.
- Node indices address the complete skeleton, not a skin-bone prefix.
- Rotation records use unsigned 24-bit XYZ and reconstructed W.
- Compact vectors are unsigned 20-bit; extended vectors are unsigned 30-bit.
- Rotation uses shortest-path normalized linear interpolation.
- Translation and scale interpolate component-wise linearly.
- Animation and bind compose as quaternion `animation * bind`, scale product and
  translation sum.
- Warus uses `relative_start=2`, `hierarchy_start=3`, `active_anchor=2`.
- Node flag bit zero selects parent-scale cancellation.
- Render matrices are `currentAbsolute[node] * inverseBaseAbsolute[node]` in SKEL
  skin order.
- For the supplied Warus capture the optional SKEL remap must remain disabled.

## Decoder validation

Across the 30 supplied Warus clips:

```text
complete clips:                 30 / 30
decoded animated records:       42,681
absolute 81-node frames:         65,286
render 60-bone frames:           48,360
all quaternion/TRS/matrix values finite: yes
rest-pose identity test:         passed
```

## Corrected RenderDoc result

The one-gigabyte RDC FrameCapture section was decompressed and the 60×3×4 CSV
palette was found five times byte-identically.

The previous comparison used the wrong clip. The uploaded level PAK shows that
the Ledge Guardian render component selects `a_pompy_idle_ws`. A package-wide
fit of all 30 normal clips gives:

```text
best clip:                    a_pompy_idle_ws
integer samples:              31
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

The very low motion error shows that the decoded Pompy motion is close to the
capture. Remaining errors are dominated by nearly constant offsets in selected
shoulder, wrist/hand/finger, helper and mustache chains. These are tracked as
additional live actor/posegraph inputs, not as evidence that the normal-clip
payload decoder is half-functional.

## Blender Action mapping

The importer still uses per-bone rest correction:

```text
O_b = inverse(C * gameRestGlobal_b) * blenderRestGlobal_b
M_b(frame) = C * gameCurrentGlobal_b(frame) * O_b
```

The generated script now improves the unsafe parts around `C` and timing:

- default basis fit uses stable torso/leg anchors rather than every Blender bone
  head;
- the basis fit has a configurable maximum residual and aborts on failure;
- anchor-fit and all-bone residuals are reported separately;
- scene/render FPS and source clip FPS are separate;
- `--scene-fps 60 --clip-fps 30` reproduces the capture sampling cadence;
- duplicate-endpoint loops receive Cycles modifiers automatically.

The previous Warus Blender report used a high-residual all-bone fit:

```text
basis scale:                    0.854199
all-bone residual median:       0.297898
all-bone residual maximum:      0.911374
```

That fit is no longer silently accepted as proof of a correct basis. The
experimental skeletal DAE joint globals match the decoded SKEL rest positions to
approximately `1e-8`.

## Remaining work for strict live 1:1 reproduction

1. recover or capture the input/base pose supplied to missing/masked clip channels;
2. identify the active ActorKeyframe, helper, constraint and procedural outputs;
3. apply the external actor/model transform when comparing absolute world poses;
4. rerun the updated Blender importer on the untouched experimental skeletal
   Armature and inspect its guarded basis report;
5. compare the complete layered result against the GPU palette.

## Rejected assumptions

- marker-spaced six-byte vectors are the `normal_clip` codec;
- channel order is the first N skin bones;
- `LoadIdxData` contains key times or a serialized permutation table;
- vector span mode is selected from unrelated low flag bits;
- nominal record advance limits decoder lookahead;
- CSV number equals ANIM frame number;
- the supplied captures are `b_idle_1_ws`;
- each capture advances one integer ANIM frame;
- a high-residual all-bone Blender similarity fit is valid;
- the old diagnostic order `inverse(bind) * current` isolates animation delta.
