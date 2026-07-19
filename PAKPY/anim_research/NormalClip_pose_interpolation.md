# DKCTF `normal_clip` local-pose interpolation

Status: **instruction-level interpolation/output port complete** for the local
animation pose produced around `0x1973BC`.

This stage consumes the sparse key/value data already decoded by
`anim_normal_clip_values.py`. It does **not** yet produce final skinning matrices.

## Binary functions

| Address | Role | Status |
|---:|---|---|
| `0x1973BC` | interpolate active rotation/translation/scale channels into node transforms | ported |
| `0x197900` | allocate/initialize output node-transform pointers and optional input/base pose | structurally ported |
| `0x199438` | calculate per-channel interpolation factors and call `0x1973BC` | ported conceptually |
| `0x12D57C` | optional quaternion sign/permutation remap from SKEL table | ported |
| `0x12D610` | optional translation sign/permutation remap from SKEL table | ported |

## Output transform layout

The output node transform is 40 bytes:

```text
+0x00  quaternion WXYZ, four float32
+0x10  scale XYZ, three float32
+0x1C  translation XYZ, three float32
```

Rotation pair buffers use 32 bytes per channel: previous WXYZ followed by next
WXYZ. Translation and scale pair buffers use 24 bytes per channel: previous XYZ
followed by next XYZ.

Interpolation factors are stored as float32 arrays in rotation, translation,
scale order.

## Base/inherited pose behavior

`0x197900` creates an output pointer for every requested node.

- With no upstream/input pose, nodes point to or copy a global identity transform:
  rotation `(1,0,0,0)`, scale `(1,1,1)`, translation `(0,0,0)`.
- With an upstream pose, its local transform is copied first.
- `0x1973BC` overwrites only the components represented by this ANIM clip.

Therefore missing channels inherit the input pose. The standalone exported pose
uses identity TRS as its base and is an animation-delta/local-animation pose, not
a final bind-composed skeleton pose.

## Rotation interpolation

For each active rotation channel:

```text
t = per-channel interpolation factor in [0,1]
s = +1 or -1 from bit 0 of the stored interpolation float
c = stored interpolation correction coefficient
k = 1 + c*t*(1-t)

q = normalize(previous * ((1-t)*k) + next * (s*t*k))
```

`k` multiplies both quaternion weights equally and cancels from the normalized
quaternion direction. The stable mathematical result is therefore:

```text
q = normalize(previous*(1-t) + next*(s*t))
```

This is shortest-path normalized linear interpolation, not trigonometric Slerp.
The sign/correction metadata is written while decoding the new/right key, so the
right key controls the interval ending at that key.

The game normalizes the four-component result before writing WXYZ to `+0x00`.

## Translation and scale interpolation

Both vector channel types use component-wise linear interpolation:

```text
value = previous*(1-t) + next*t
```

Translation writes to `+0x1C`; scale writes to `+0x10`.

## Interpolation factor generation

The per-channel timing entry contains the left key frame and duration. Around
`0x199438`, the factor is calculated as:

```text
t = (requested_frame - left_key_frame) / duration
```

Short durations use a small reciprocal lookup table; longer durations cache
`1/duration`. Integer frame evaluation therefore reproduces every stored key
exactly and linearly fills the frames between keys.

## Optional SKEL sign/permutation maps

When an external caller flag is set, `0x1973BC` invokes two SKEL remap helpers.
The flag is not serialized as part of the ANIM payload, so the reference API
keeps this operation opt-in.

Each node has a two-byte map entry:

```text
byte 0: sign toggles in bits 0,2,4,6
byte 1: two-bit destination index for each source component
```

Quaternion remapping handles four WXYZ components. Translation remapping handles
three XYZ components. A first byte of `0xFF` means no remap.

The two tables are the first and second `node_count` entries of the SKEL
`skeleton_map.u16_values` array.

## Runtime output

`anim_normal_clip_pose_patch.py` writes evaluated local poses to:

```text
debug/anim_normal_clip_pose/*.normal_clip_pose.json
```

Each document contains all nodes for every integer frame and explicitly records
that the base pose is identity and no SKEL remap was automatically applied.

## Validation

Strict evaluation across all 30 supplied Warus clips and the full 81-node
skeleton:

```text
clips evaluated:                  30 / 30
complete local node-frames:       65,286
all quaternion norms valid:       yes
maximum quaternion norm error:    2.22044604925e-16
all TRS components finite:        yes
all stored sparse keys reproduced: yes
```

A preliminary comparison against the 41 RenderDoc captures shows that the decoded
local rotations track the capture-derived motion, but a strict matrix match is
not yet claimed. The capture buffer includes full hierarchy/helper-node effects
and an external model/root transform, while the old diagnostic extracted only
skin-bone-local deltas.

## Remaining work

1. Identify/port the bind-pose and hierarchy application after local pose output.
2. Resolve the three ANIM roots (`blendspace`, `root.move`, `root`) and external
   model/root transform behavior.
3. Reconstruct all 81 global node matrices, including non-skin helper and scale
   compensation nodes.
4. Compare predicted skinning matrices directly with the 41 RenderDoc buffers.
5. Apply the DKCTF-to-Blender basis conversion and emit Blender F-curves.
