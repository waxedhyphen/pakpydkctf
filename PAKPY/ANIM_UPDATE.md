# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 1  
**Authoritative rule:** This is the central current-state document. Replace or extend this file when new binary findings are confirmed. Historical notes under `anim_research/` remain evidence, but any conflict is resolved in favor of this file and tested runtime code.

## Update protocol

For every new finding:

1. Mark it as **verified**, **strongly supported**, **hypothesis**, or **rejected**.
2. Record the binary function/address and sample set used.
3. Update the corresponding parser or patch only for verified behavior.
4. Add or update a regression test.
5. Keep unsupported decoding in a `pending:*` state; do not emit plausible-looking fake animation tracks.

## Runtime integration

| File | Purpose |
|---|---|
| `anim_normal_clip_indices.py` | Exact `LoadIdxData` parser and standalone CLI |
| `anim_normal_clip_indices_patch.py` | Adds exact channel lists to exported ANIM probes and disables the old false `normal_clip` marker decode |
| `test_anim_normal_clip_indices.py` | Synthetic regression tests for LSB map order and two-level remapping |
| `anim_research/LoadIdxData.md` | Full address-level reverse-engineering document |

When a CHAR/model package contains a skeleton JSON, every resolved `normal_clip` probe now receives:

```text
normal_clip_indices.rotation.base_nodes
normal_clip_indices.rotation.animated_nodes
normal_clip_indices.rotation.constant_nodes
normal_clip_indices.translation.*
normal_clip_indices.scale.*
normal_clip_indices.load_pair_data_file_offset
```

The old marker-derived `normal_clip` tracks are no longer accepted. Until the real frame processor is ported, the probe status is:

```text
pending:normal_clip_frame_decode
```

## Verified binary identity

```text
Nintendo Switch NSO main SHA-256:
018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21

Decompressed .text SHA-256:
1b93d59da91ecda15a048840787d22bcb52c99815acd0c2b32767da3615af252

LoadIdxData bytes SHA-256:
5d27ddb7e2c78e6fda7c124780e5b104d65b9c4b54fb8023800db0fda5b0f081
```

## Function map

| Address | Function | Current state |
|---:|---|---|
| `0x1823FC` | `CAnimBitStream::DecodeValue32` | LSB-first reader identified; belongs to packed variants, not normal rotation records |
| `0x194B98` | `NAnimStream::RemapIndex` | verified |
| `0x194C00` | `NAnimStream::CountBoneBits` | verified |
| `0x194CD0` | `NAnimStream::BuildBoneMap` | verified |
| `0x194D44` | `NAnimStream::BuildActiveBoneSet` | verified |
| `0x195BA8` | `CAnimStreamData::LoadIdxData` | fully ported and validated |
| `0x1969A4` | `CAnimStreamData::LoadPairData` | next reverse-engineering target |
| `0x196D88` | `CAnimStreamData::LoadRotRange` | range concept identified; production port pending |
| `0x197BE0` | `CAnimStreamProcess::LoadSetupFrames` | pending |
| `0x198B64` | normal-clip value reader | partial notes only; exact port pending |
| `0x199058` | Slerp step | interpolation type verified |
| `0x199360` | `GenerateFrame` | pending full port |

## `normal_clip` verified structure

### Container and stream start

- `RFRM` at file `0x00`
- `ANIM` at file `0x14`
- control word at file `0x28`; low byte is the observed frame-count field
- `CAnimStream` data pointer starts at file `0x28`
- `SAnimStreamStart` is calculated dynamically by `CAnimStream::CreateAnimData`
- for all 30 supplied Warus clips: start at file `0x53`, flags at `0x54`, index data at `0x55`

The earlier statement that the rotation bitmap starts at `0x54` is rejected. `0x54` is the flags byte.

### `LoadIdxData` result

`LoadIdxData` does **not** parse frame times, sample records, or a separate serialized permutation table.

It reads two bitmap levels, LSB-first:

1. Base node-space maps for rotation, translation and scale.
2. Selector maps over the resulting base lists.
   - selector bit `1`: animated channel
   - selector bit `0`: constant channel
3. `RemapIndex` converts selector-local positions through the base list to real skeleton node indices.

Flags used:

```text
0x40 rotation maps present
0x20 translation maps present
0x10 scale maps present
```

Serialized order:

```text
rotation base map
translation base map
scale base map
rotation selector
translation selector
scale selector
LoadPairData begins immediately after the final selector
```

There is no alignment between these bitmap blocks.

### Worked sample: `016__b_idle_1_ws`

```text
full nodes: 81
SAnimStreamStart: 0x53
flags: 0x79
rotation base: 0x55, 53 nodes
translation base: 0x60, 10 nodes
scale base: 0x6B, 13 nodes
rotation selector: 0x76, 37 animated / 16 constant
translation selector: 0x7D, 8 animated / 2 constant
scale selector: 0x7F, 13 animated / 0 constant
LoadPairData starts: 0x81
```

### Validation

Strict parser result over all supplied Warus clips:

```text
30 / 30 parsed
0 base-map padding violations
0 selector padding violations
0 partition failures
SAnimStreamStart = 0x53 in all samples
LoadPairData start = 0x7F..0x83
```

## Rotation codec: current truth

Verified or strongly supported:

- normal-clip rotation records are big-endian fixed records, not the old six-byte marker vectors
- record size is 8 or 12 bytes depending on a flag
- channel-specific ranges are loaded by `LoadRotRange`
- quaternion `W` is reconstructed from `X/Y/Z` and a sign flag
- playback uses quaternion Slerp

Not yet safe to implement as final:

- exact record flag positions
- exact 23/24-bit component assembly
- special-record path
- frame/key timing and record traversal

Consequently, no real `normal_clip` timeline is emitted yet.

## Packed variants

`packed_clip_82`, `packed_state_c1`, and `packed_state_c2` are separate codec families. The existing `anim_packed_sample_decode.py` remains experimental and must not be treated as verified. The LSB-first `DecodeValue32` route is relevant here, not as the main normal-clip rotation record path.

## Remaining path to Blender playback

1. Port `LoadPairData` for constant rotation and translation values.
2. Port rotation/vector range loaders.
3. Port `LoadSetupFrames` and the frame-processing routine.
4. Port `0x198B64` exactly.
5. Produce local node TRS keys with correct timing.
6. Apply Slerp for rotations and verify translation/scale interpolation.
7. Validate fixed node mapping against the 41 RenderDoc frames.
8. Export real quaternion/location/scale F-curves to Blender.

## Rejected earlier assumptions

- `0x54` is the rotation bitmap — rejected.
- `b_idle_1` has 58 rotation channels at this stage — rejected; the correct animated count is 37 and base count is 53.
- `BuildActiveBoneSet` reads one seven-channel flag byte per node — rejected; it is an unrolled bitmap splitter.
- `LoadIdxData` reads keyframe times — rejected.
- `LoadIdxData` reads a separate permutation table — rejected.
- marker-spaced six-byte vectors are the normal-clip codec — rejected.
