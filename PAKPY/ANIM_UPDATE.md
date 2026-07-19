# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 2  
**Authoritative rule:** Replace or extend this file when new findings are confirmed. Historical notes under `anim_research/` remain evidence, but conflicts are resolved in favor of this file and tested runtime code.

## Update protocol

1. Mark each finding as **verified**, **strongly supported**, **hypothesis**, or **rejected**.
2. Record the binary address and sample set.
3. Change runtime code only for verified behavior.
4. Add or update a regression test.
5. Keep unsupported decoding in a `pending:*` state.

## Runtime integration

| File | Purpose |
|---|---|
| `anim_normal_clip_indices.py` | Exact `LoadIdxData` parser |
| `anim_normal_clip_indices_patch.py` | Exports exact base/animated/constant node lists |
| `anim_normal_clip_setup.py` | Exact setup-stage parser through `LoadPairData`, range tables and frame-stream start |
| `anim_normal_clip_setup_patch.py` | Exports constants, ranges and `frame_data_file_offset` into probe JSON |
| `test_anim_normal_clip_indices.py` | Index bitmap regression tests |
| `test_anim_normal_clip_setup.py` | Setup decoder regression tests |
| `anim_research/LoadIdxData.md` | Address-level `LoadIdxData` notes |
| `anim_research/LoadPairData_and_ranges.md` | Address-level setup-stage notes |

Every resolved `normal_clip` probe with a skeleton now receives:

```text
normal_clip_indices.rotation.*
normal_clip_indices.translation.*
normal_clip_indices.scale.*
normal_clip_setup.constant_rotations
normal_clip_setup.constant_translations
normal_clip_setup.rotation_ranges
normal_clip_setup.translation_ranges
normal_clip_setup.scale_ranges
normal_clip_setup.frame_data_file_offset
```

No fabricated animation timeline is emitted. Current track status remains:

```text
pending:normal_clip_frame_decode
```

## Verified binary identity

```text
Nintendo Switch NSO main SHA-256:
018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21

Decompressed .text SHA-256:
1b93d59da91ecda15a048840787d22bcb52c99815acd0c2b32767da3615af252
```

## Function map

| Address | Function | Current state |
|---:|---|---|
| `0x1823FC` | `CAnimBitStream::DecodeValue32` | verified LSB reader for packed variants |
| `0x194B98` | `RemapIndex` | verified |
| `0x194C00` | `CountBoneBits` | verified |
| `0x194CD0` | `BuildBoneMap` | verified |
| `0x194D44` | `BuildActiveBoneSet` | verified |
| `0x195BA8` | `LoadIdxData` | fully ported and validated |
| `0x1969A4` | `LoadPairData` | fully ported and validated |
| `0x196D88` | `LoadRotRange` | fully ported and validated |
| `0x196E98` | translation/scale range loader | fully ported and validated |
| `0x197BE0` | `LoadSetupFrames` | next target |
| `0x198B64` | normal-clip value reader | partial notes; exact port pending |
| `0x199058` | Slerp step | interpolation type verified |
| `0x199360` | `GenerateFrame` | pending |

## Verified serialized setup order

Starting after `LoadIdxData`:

```text
constant rotation records
constant translation records
rotation range nibble table
translation range records
scale range records
frame-processing stream
```

No alignment is inserted between these blocks.

## `LoadIdxData`

- Reads node-space base bitmaps for rotation, translation and scale.
- Reads selector bitmaps over the base lists.
- Selector `1` means animated; selector `0` means constant.
- `RemapIndex` maps selector-local positions to real skeleton node indices.
- Does not read key times or a separate serialized permutation table.

For `016__b_idle_1_ws`:

```text
81 nodes
flags: 0x79
rotation: 53 base / 37 animated / 16 constant
translation: 10 base / 8 animated / 2 constant
scale: 13 base / 13 animated / 0 constant
LoadPairData start: 0x81
```

## `LoadPairData`: verified

### Constant rotation

- One record per constant rotation node.
- Original routine performs a 12-byte lookahead.
- Stream advances by 8 or 12 bytes according to bit 31 of the first big-endian word.
- Quantized `X/Y/Z` use multiplier `2^-27` and offset `-1`.
- `W = ±sqrt(1 - X² - Y² - Z²)` when the vector length is below one.
- Bit 30 selects the sign of `W`.
- Stored order is `(W, X, Y, Z)`.

### Constant translation

- One record per constant translation node.
- Same 8/12-byte advance rule and 12-byte lookahead.
- Bits 25..29 encode a power-of-two range exponent.
- Bit 30 selects direct or reciprocal range.
- Components use `value = integer * (2 * R * 2^-29) - R`.

## Range loaders: verified

### Rotation ranges

One nibble per animated rotation channel, **low nibble first**:

```text
R = reinterpret_float(0x3F800000 - (nibble << 22))
base = -R
scale = R * 2^-23
```

The earlier `R * 2 * 2^-23` claim is rejected.

### Translation and scale ranges

- One 8-byte range record per animated channel.
- Produces base `xyz` and span `xyz`.
- Compact floats are reconstructed exactly from the binary instruction sequence.
- Translation span multiplier: flag bit 2 set -> `2^-30`, otherwise `2^-20`.
- Scale span multiplier: encoded mode `3` -> `2^-30`, otherwise `2^-20`.

## Validation

Strict parsing against all 30 supplied Warus clips and the full 81-node skeleton:

```text
30 / 30 index blocks parsed
30 / 30 setup blocks parsed
0 bitmap padding violations
all constant quaternion norms ~= 1
all constant vectors finite
all range values finite
frame-data offsets: 0x122 .. 0x1ED
```

For `016__b_idle_1_ws`:

```text
LoadPairData start:       0x081
LoadPairData end:         0x111
rotation ranges end:      0x124
translation ranges end:   0x164
frame-data start:         0x1CC
```

## Remaining path to Blender playback

1. Port `LoadSetupFrames @ 0x197BE0`.
2. Identify frame-block traversal and key timing.
3. Port the value readers, including `0x198B64`, instruction-for-instruction.
4. Produce local node rotation/translation/scale keys.
5. Apply Slerp for rotations and verify vector interpolation.
6. Validate fixed node mapping against the 41 RenderDoc captures.
7. Emit real Blender quaternion/location/scale F-curves.

## Rejected earlier assumptions

- `0x54` is the rotation bitmap — rejected; it is the flags byte.
- `LoadIdxData` reads keyframe times — rejected.
- `LoadIdxData` reads a separate permutation table — rejected.
- normal-clip rotation ranges use `R * 2 * 2^-23` — rejected; the binary uses `R * 2^-23`.
- marker-spaced six-byte vectors are the normal-clip codec — rejected.
