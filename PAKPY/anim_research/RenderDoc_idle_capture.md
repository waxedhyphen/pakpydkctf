# Warus `a_pompy_idle_ws` RenderDoc capture analysis

Status: the uploaded RDC, 41 chronological CSV palette exports, the Warus
Character package and `b00_mangrove_seaLion.pak` were analyzed together. The
captures follow `a_pompy_idle_ws`, not `b_idle_1_ws`.

## Corrected source clip

The previous analysis trusted the statement that `b_idle_1_ws` was continuously
active. The level PAK contradicts that assumption directly.

The `Ledge Guardians` ROOM data contains two copies of the Warus actor setup. In
both copies, the `T.Ledge Guardian - Render` component references CHAR entry UUID
`02603871c3ab4ccfb81b27a7929bc20a` (`Warus_Shield`) and names
`a_pompy_idle_ws` as the active/default clip:

```text
first render component:  0x433C9
first clip string:       0x43416
second render component: 0x44C11
second clip string:      0x44C5E
```

The corresponding ActorKeyframe components list:

```text
a_pompy_idle_ws
a_pompy_attack_forward_ws
a_pompy_jump_into_arena_ws
```

Therefore `b_idle_1_ws` was the wrong resource for capture validation.

## Capture ordering and timing

The supplied ordering remains:

- `frame1.rdc` corresponds to `1.csv`;
- `1.csv` through `41.csv` are chronological render captures;
- capture numbers are not serialized ANIM frame numbers.

A package-wide cyclic subframe fit ranks `a_pompy_idle_ws` first by a wide
margin:

| Clip | Absolute RMSE | Motion RMSE | Centered RMSE |
|---|---:|---:|---:|
| `a_pompy_idle_ws` | 0.13559 | 0.00163 | 0.01191 |
| `b_idle_1_ws` | 0.60129 | 0.00888 | 0.07762 |

The optimized diagnostic fit is approximately:

```text
offset = 27.6
step   = 0.49 ANIM frames per capture
loop   = 30 ANIM frames
```

Because the diagnostic fitter linearly interpolates already-composed render
matrices, the runtime-consistent interpretation is:

```text
capture 1        ~= a_pompy_idle_ws frame 27.5
capture interval ~= 0.5 ANIM frames
render rate      ~= 60 Hz
clip rate        = 30 fps
```

The sequence crosses frame 30 and loops to frame 0. This explains why treating
CSV 1–41 as integer frames 0–40 failed.

Machine-readable results are stored in:

```text
anim_research/warus_pompy_capture_fit.json
anim_research/warus_pompy_capture_fit.csv
```

The reproducible matcher is `anim_capture_fit.py`. It is also copied into newly
exported Character/Model packages.

## RDC container and matrix palette

The uploaded capture is a RenderDoc 1.45 Vulkan capture. Its one-gigabyte
FrameCapture section was decompressed successfully. The first CSV contains 60
matrices with three float4 rows:

```text
60 * 3 * 4 * sizeof(float32) = 2,880 bytes = 0xB40
```

That palette occurs five times byte-identically in the decompressed RDC at:

```text
0x3B08AE80
0x3B0A3480
0x3B0A5500
0x3B0B3880
0x3B0B5900
```

The RDC confirms the CSV palette bytes but does not contain a serialized ANIM
frame number for the actor.

## What the remaining error means

The corrected Pompy fit changes the diagnosis. The clip motion itself is very
close to the live capture. The strongest evidence is the temporal error:
`motion_rmse` is only about `0.00163`.

After removing one constant matrix offset per bone/component for diagnosis, the
remaining centered error is about `0.01191`. The largest discrepancies are
concentrated in shoulder, hand/wrist, finger and mustache/helper chains. Root,
shield and hip motion track Pompy Idle closely.

This pattern is consistent with `a_pompy_idle_ws` being the base normal clip plus
additional live inputs such as ActorKeyframe/posegraph state, partial bone masks,
an inherited input pose, helper/constraint transforms, procedural accessory
transforms or the external actor/model transform. It does not indicate a
wholesale failure of the ANIM value decoder.

## Correct local-delta extraction order

The verified runtime composition remains:

```text
currentLocal = animationLocal * bindLocal
animationLocal = currentLocal * inverse(bindLocal)
```

The production decoder already uses this order.

## Blender consequence

The Blender importer now separates clip rate from scene/render rate. For direct
comparison with these captures use:

```text
--scene-fps 60 --clip-fps 30
```

This writes successive 30-fps ANIM samples two Blender frames apart. It also:

- uses stable torso/leg anchors for the game-to-Blender basis by default;
- rejects a basis whose anchor residual exceeds the configured threshold;
- reports anchor and all-bone residuals separately;
- detects duplicate-endpoint loops and installs Cycles modifiers;
- retains `--basis-mode all` for the old all-bone fit and `identity` for an
  explicitly verified identical basis.

The old generated report had an all-bone best-fit scale of about `0.8542`, median
residual `0.2979` and maximum residual `0.9114`. Those values must not be treated
as a valid basis silently. The experimental skeletal DAE joint globals match the
decoded SKEL rest positions to roughly `1e-8`, so a large Blender fit residual is
an Armature/import calibration problem, not a SKEL decoder error.

## Rejected assumptions

- the captures are `b_idle_1_ws`;
- CSV number equals ANIM frame number;
- every capture advances one integer ANIM frame;
- the 41 palettes are a complete isolated live pose with no additional layers;
- a high-residual all-bone Blender similarity fit is acceptable;
- `inverse(bind) * current` extracts the animation delta.
