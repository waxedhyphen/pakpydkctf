# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 7

This is the authoritative current-state document. Replace or extend it when new
findings are confirmed. Runtime changes require a regression test. Isolated
resource playback and strict live-game pose reproduction are tracked separately.

## Current runtime pipeline

| File | Purpose |
|---|---|
| `anim_normal_clip_indices.py` | exact two-level node/channel bitmap parser |
| `anim_normal_clip_setup.py` | constants, quantization ranges and frame-stream start |
| `anim_normal_clip_frames.py` | exact key timing and record boundaries |
| `anim_normal_clip_values.py` | exact rotation/compact-vector/extended-vector payload decode |
| `anim_normal_clip_values_patch.py` | writes sparse node-indexed key documents |
| `anim_normal_clip_pose.py` | exact local-pose interpolation and optional SKEL remap |
| `anim_normal_clip_pose_patch.py` | writes complete identity-base local pose frames |
| `anim_normal_clip_bind.py` | exact bind, root-anchor, hierarchy and render-matrix composition |
| `anim_normal_clip_bind_patch.py` | writes 81-node absolute and 60-bone render matrices |
| `blender_normal_clip_action_script_patch.py` | generates rest-calibrated Blender Action importer |
| `test_blender_normal_clip_action_math.py` | verifies rest calibration and motion preservation |
| `anim_research/NormalClip_value_payloads.md` | value-reader documentation |
| `anim_research/NormalClip_pose_interpolation.md` | local interpolation documentation |
| `anim_research/NormalClip_bind_hierarchy.md` | CSkelPose bind/hierarchy documentation |
| `anim_research/RenderDoc_idle_capture.md` | RDC/CSV analysis and live-pose limitations |
| `anim_research/renderdoc_frame1_metadata.json` | parsed RDC metadata |
| `anim_research/renderdoc_frame1_matrix_copies.csv` | exact GPU palette locations |
| `anim_research/renderdoc_capture_sequence.csv` | chronological palette-change report |

Exported normal clips receive:

```text
normal_clip_indices.*
normal_clip_setup.*
normal_clip_frames.*
normal_clip_values_file
normal_clip_values_summary
normal_clip_pose_file
normal_clip_pose_summary
normal_clip_bind_file
normal_clip_bind_summary
```

Generated analysis and Blender files include:

```text
debug/anim_normal_clip_values/*.normal_clip_values.json
debug/anim_normal_clip_pose/*.normal_clip_pose.json
debug/anim_normal_clip_bind/*.normal_clip_bind.json
blender_import_normal_clip_actions.py
BLENDER_NORMAL_CLIP_ACTIONS.txt
```

## Current readiness

```text
isolated normal_clip Blender Action: ready
strict live-game layered pose match: pending posegraph/timestamp inputs
```

The existing generic probe status remains:

```text
pending:normal_clip_external_root_and_blender_basis
```

That status refers to strict live-game actor reproduction. The generated isolated
`normal_clip` Blender Action path is ready and is reported separately by the
Blender importer.

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

## Validation

Across the 30 supplied Warus clips:

```text
complete clips:                 30 / 30
decoded animated records:       42,681
absolute 81-node frames:         65,286
render 60-bone frames:           48,360
all quaternion/TRS/matrix values finite: yes
rest-pose identity test:         passed
```

Blender Action calibration tests:

```text
rest matrix maps exactly:        passed
current motion preserved:        passed
```

## RenderDoc result

The uploaded capture 1 was parsed and its one-gigabyte FrameCapture section was
successfully decompressed. The 60×3×4 matrix palette exported in `1.csv` occurs
five times byte-identically in the RDC. CSV files 1–41 are chronological, but no
capture contains an ANIM frame number or a common fixed frame step.

The live palette is not treated as the output of one pure normal clip. Bone-wise
comparison shows additional live posegraph/helper/procedural influences. The
isolated clip importer is therefore marked ready, while exact reproduction of
the complete live actor remains a separate task.

## Blender Action mapping

The generated importer estimates a similarity transform `C` between game and
Blender rest-joint positions, then uses a per-bone rest correction:

```text
O_b = inverse(C * gameRestGlobal_b) * blenderRestGlobal_b
M_b(frame) = C * gameCurrentGlobal_b(frame) * O_b
```

This maps the decoded rest pose exactly onto the opened armature and absorbs
Blender bone roll without a fixed manual axis table. It writes location,
quaternion and scale keys for every integer clip frame and sets linear
interpolation.

## Remaining work

For isolated `normal_clip` playback in Blender: none beyond executing the
generated importer on the exported armature.

For strict live-game 1:1 reproduction:

1. recover animation time for every original RDC, not only CSV order;
2. capture or decode all active posegraph/blend/procedural inputs;
3. identify the external actor/model transform and optional SKEL-remap caller state;
4. compare the complete layered pose against the GPU palette.

## Rejected assumptions

- marker-spaced six-byte vectors are the `normal_clip` codec;
- channel order is the first N skin bones;
- `LoadIdxData` contains key times or a serialized permutation table;
- vector span mode is selected from unrelated low flag bits;
- nominal record advance limits decoder lookahead;
- CSV number equals ANIM frame number;
- the 41 chronological palettes are a pure isolated `b_idle_1_ws` export;
- the old diagnostic order `inverse(bind) * current` isolates the animation delta.
