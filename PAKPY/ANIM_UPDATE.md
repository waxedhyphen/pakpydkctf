# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 6

This is the authoritative current-state document. Replace or extend it when
new findings are confirmed. Runtime code changes require a regression test and
unsupported stages must remain in a `pending:*` state.

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
| `test_anim_normal_clip_values.py` | value codec and corrected multiplier tests |
| `test_anim_normal_clip_pose.py` | interpolation, inheritance and SKEL-remap tests |
| `test_anim_normal_clip_bind.py` | bind/hierarchy, scale propagation and rest-pose tests |
| `anim_research/NormalClip_value_payloads.md` | address-level payload documentation |
| `anim_research/NormalClip_pose_interpolation.md` | `0x1973BC` and local-pose documentation |
| `anim_research/NormalClip_bind_hierarchy.md` | exact CSkelPose bind/hierarchy documentation |
| `anim_research/normal_clip_value_validation.csv` | 30-clip value validation report |
| `anim_research/normal_clip_pose_validation.csv` | 30-clip local-pose validation report |
| `anim_research/normal_clip_bind_validation.csv` | 30-clip hierarchy validation report |

Exported normal clips now receive:

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

Sparse decoded values are written to:

```text
debug/anim_normal_clip_values/*.normal_clip_values.json
debug/anim_normal_clip_pose/*.normal_clip_pose.json
debug/anim_normal_clip_bind/*.normal_clip_bind.json
```

The current generic track status is deliberately:

```text
pending:normal_clip_external_root_and_blender_basis
```

No old marker-derived or prefix-mapped animation is accepted as a real
`normal_clip` timeline.

## Function map

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
| `0x198F40` | due-channel list builder | fully ported structurally |
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

## Verified setup and timing

- `LoadIdxData` reads base bitmaps and selector bitmaps LSB-first.
- Selector `1` is animated; selector `0` is constant.
- Node indices are exact full-skeleton node indices, not skin-bone prefixes.
- Constant rotations and translations are decoded before range tables.
- Initial keys occur at frame 0.
- Explicit durations are BE16 words consumed LSB-first.
- Every supplied channel ends at `frame_count - 1`.
- Value blocks are aligned to four bytes; duration streams to two bytes.

## Corrected vector-range scaling

The previous setup implementation selected span multipliers from the wrong
flags. Correct behavior from the caller around `0x195754` and `0x1958A4`:

```text
translation extended when (flags & 0x0C) == 0x0C
scale extended when       (flags & 0x30) == 0x30
```

Exact span multipliers:

```text
extended 30-bit: float 0x30800000 = 2^-30
compact 20-bit:  float 0x35800008 = 0x1.00001p-20
```

The earlier low-bit multiplier selection is rejected.

## Verified value payloads

### Rotation

- 8/12-byte advance selected by bit 15 of the first BE16.
- The reader intentionally performs a 12-byte lookahead.
- XYZ are unsigned 24-bit values dequantized with the per-channel rotation range.
- W is reconstructed with a sign bit and `sqrt(1-|XYZ|²)`.
- Special paths produce normalized W=0 quaternions or compact exact-axis quaternions.
- Sparse key values are stored as WXYZ.

### Translation and scale

- Compact path: unsigned 20-bit XYZ; 4/8-byte advance.
- Extended path: unsigned 30-bit XYZ; 4/8/12-byte advance.
- Both paths intentionally read beyond the nominal advance and overlap following data.
- Values use `base + scaledSpan * quantized` per component.

## Verified local-pose interpolation

- Missing channels inherit an input pose; the standalone evaluator uses identity TRS.
- Rotation is shortest-path normalized linear interpolation.
- The right key's interpolation sign bit controls the segment ending at that key.
- The binary's correction coefficient multiplies both quaternion weights equally and cancels after normalization.
- Translation and scale are component-wise linear.
- Output layout is WXYZ at `+0x00`, scale XYZ at `+0x10`, translation XYZ at `+0x1C`.
- Optional SKEL sign/permutation helpers are ported but remain opt-in because their caller flag is external to the ANIM stream.

Local-pose validation across all clips:

```text
clips evaluated:               30 / 30
complete local node-frames:    65,286
maximum quaternion norm error: 2.22044604925e-16
all TRS values finite:         yes
```

## Verified bind and hierarchy composition

- `CCoords::x_y_ss` combines animation and bind as quaternion product, component-wise scale product and translation sum.
- Quaternion order is `animation * bind`.
- Warus layout starts are `relative_start=2`, `hierarchy_start=3`, `active_anchor=2` (`root`).
- The active anchor relative transform is also written to absolute slot zero and drives children serialized under node zero.
- Base hierarchical matrices omit local bind scale below the control-root zone.
- Runtime node flag bit zero selects no-scale propagation; clear selects scale propagation.
- No-scale propagation is `parentAbs * diag(1/parentRelativeScale) * childLocal`.
- Render matrices are `currentAbsolute[node] * inverseBaseAbsolute[node]` in exact SKEL skin-node order.

Hierarchy validation across all clips:

```text
clips composed:              30 / 30
absolute 81-node frames:     65,286
render 60-bone frames:       48,360
all matrix values finite:    yes
maximum absolute value:      9.33534035921
rest-pose identity test:     passed
```

The 41 RenderDoc CSVs do not contain animation timestamps or the external actor/model transform. A strict capture match is therefore still pending; treating them as 41 consecutive integer frames of the 61-frame idle clip is rejected.

## Validation

Across all 30 supplied Warus clips:

```text
complete clips:                 30 / 30
decoded animated records:       42,681
rotation records:               31,172
compact vector records:          5,033
extended vector records:         6,476
special exact-axis rotations:        6
quaternion norms:                0.9999999999999999 .. 1.0
20-bit values within range:      yes
30-bit values within range:      yes
all vector outputs finite:       yes
key schedules match exactly:     yes
```

## Remaining path to Blender

1. Recover RenderDoc capture time and the external actor/model-root transform.
2. Confirm the real caller state for the optional SKEL sign/permutation path.
3. Apply DKCTF-to-Blender basis conversion.
4. Convert decoded local animation deltas to Blender pose-bone channels relative to rest matrices.
5. Emit quaternion/location/scale F-curves and activate the Blender Action.

## Rejected assumptions

- marker-spaced six-byte vectors are the `normal_clip` codec;
- channel order can be inferred from the first N skin bones;
- `LoadIdxData` contains key times or a separate serialized permutation table;
- vector span mode is selected from unrelated low flag bits;
- nominal record advance means the decoder may not read into following bytes.
