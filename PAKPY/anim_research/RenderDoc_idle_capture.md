# Warus `b_idle_1_ws` RenderDoc capture analysis

Status: the uploaded RDC and all 41 chronological CSV exports were analyzed. The
RDC confirms the GPU matrix palette contained in `1.csv`, but the 41 captures do
not constitute a timestamped export of the isolated `b_idle_1_ws` resource.

## Supplied ordering

The user confirmed:

- `frame1.rdc` corresponds to CSV capture 1;
- `1.csv` through `41.csv` are ordered by capture time;
- Warus continuously had `b_idle_1_ws` active;
- it is unknown whether capture 1 is animation frame 0, whether capture 41 is the
  last clip frame, or how much animation time elapsed between captures.

The numbering is therefore a chronological sequence, not an ANIM frame index.

## RDC container

The uploaded capture is a RenderDoc 1.45 Vulkan capture:

```text
RDC SHA-256:              3cf3aa474cfc203dae4dd354797bb4d8685cf8d5d3dac20084d24bc7f1a2c6fc
container version:        0x102
program version:          1.45 2fc0bc
driver:                   Vulkan
frame-capture version:    32
compressed section size:  452,493,232 bytes
uncompressed size:        1,004,863,296 bytes
compression flag:         LZ4
```

The frame-capture section was decompressed with RenderDoc's one-megabyte
continuing LZ4 block format:

```text
compressed blocks: 959
result bytes:      1,004,863,296
size match:        exact
```

Metadata is stored in `renderdoc_frame1_metadata.json`.

## Exact matrix palette in the RDC

The first CSV contains 60 matrices with three float4 rows:

```text
60 * 3 * 4 * sizeof(float32) = 2,880 bytes = 0xB40
```

The same 2,880-byte palette occurs five times in the decompressed RDC stream:

```text
0x3B08AE80
0x3B0A3480
0x3B0A5500
0x3B0B3880
0x3B0B5900
```

All five copies have identical first 2,880 bytes. Four copies first differ from
the first copy exactly at byte `0xB40`, proving that the exported CSV values are
the first matrix block in a larger 8-KiB GPU resource/copy region. Details and
hashes are in `renderdoc_frame1_matrix_copies.csv`.

## Capture sequence

Consecutive CSV palettes change smoothly, so their numbering is consistent with
the stated chronological ordering. The sequence contains no timestamp, ANIM
frame number, playback rate, event ID or actor transform. Per-pair palette-change
statistics are in `renderdoc_capture_sequence.csv`.

The following interpretations are rejected:

- CSV 1 is automatically ANIM frame 0;
- CSV 41 is automatically ANIM frame 40 or the last `b_idle_1_ws` frame;
- each capture advanced by exactly one integer ANIM frame;
- the 41 palettes are the unmodified output of one isolated normal clip.

## Why the final game palette is not a pure normal clip

The reconstructed isolated clip was fitted against the capture sequence using:

- the exact 61-frame `b_idle_1_ws` decoder;
- both optional SKEL remap states;
- subframe interpolation;
- common actor/model transforms;
- temporal matrix invariants;
- direct-parent local rotation extraction;
- both plausible interpretations of the ambiguous 60-entry SKEL skin table.

No single offset and capture-step produces a consistent match across the full
palette. Some bones follow the isolated idle motion closely, while other chains
show large, bone-specific differences. The strongest disagreements occur in
shield, hip, hand/wrist, helper and mustache-base chains.

This is consistent with the idle clip being permanently active as a base layer
while the live character output also includes other posegraph, helper,
scale-compensation or procedural transforms. It does not invalidate the normal
clip decoder.

## Correct local-delta extraction order

A previous diagnostic attempted to isolate animation rotation as:

```text
inverse(bindLocal) * currentLocal
```

The verified runtime composition is:

```text
currentLocal = animationLocal * bindLocal
```

Therefore the correct diagnostic extraction order is:

```text
animationLocal = currentLocal * inverse(bindLocal)
```

This correction applies to the old capture diagnostic only. The production ANIM
value, interpolation and bind/hierarchy decoders already use the verified
runtime order.

## Blender consequence

A strict reproduction of the complete live actor requires the missing live
posegraph inputs and capture timestamps. An isolated `normal_clip` Blender Action
does not require them.

`blender_import_normal_clip_actions.py` uses the decoded 81-node absolute poses
and calibrates them to the opened Blender armature from its rest pose:

```text
C            = best-fit game-rest to Blender-rest similarity transform
O_b          = inverse(C * gameRestGlobal_b) * blenderRestGlobal_b
blender_b(f) = C * gameCurrentGlobal_b(f) * O_b
```

At the rest pose this maps exactly to the existing Blender rest matrix. The
per-bone correction absorbs Blender bone roll, while `C` absorbs global axis,
scale and origin differences. The generated Action therefore represents the
isolated `b_idle_1_ws` clip, not every additional live-game pose layer.
