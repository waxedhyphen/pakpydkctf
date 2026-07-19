# DKCTF ANIM — central update file

**Status date:** 2026-07-19  
**Document schema:** 3  
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
| `anim_normal_clip_setup.py` | Parses constants, range tables and frame-stream start |
| `anim_normal_clip_setup_patch.py` | Exports setup data into probe JSON |
| `anim_normal_clip_frames.py` | Exact frame traversal, duration codec, key timing and record boundaries |
| `anim_normal_clip_frames_patch.py` | Exports frame blocks and exact per-channel key schedules |
| `test_anim_normal_clip_indices.py` | Index bitmap tests |
| `test_anim_normal_clip_setup.py` | Setup decoder tests |
| `test_anim_normal_clip_frames.py` | Timing codec, record-size and traversal tests |
| `anim_research/LoadIdxData.md` | Address-level index notes |
| `anim_research/LoadPairData_and_ranges.md` | Address-level setup notes |
| `anim_research/LoadSetupFrames_and_timing.md` | Complete frame/timing documentation |
| `anim_research/load_setup_frames_validation.csv` | 30-clip structural validation report |

Every resolved `normal_clip` probe with a skeleton now receives:

```text
normal_clip_indices.*
normal_clip_setup.*
normal_clip_frames.initial_records
normal_clip_frames.blocks
normal_clip_frames.rotation_key_frames
normal_clip_frames.translation_key_frames
normal_clip_frames.scale_key_frames
normal_clip_frames.stream_end_file_offset
```

No fabricated animation timeline is emitted. Current status:

```text
pending:normal_clip_value_decode
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
| `0x1823FC` | `DecodeValue32` | verified LSB reader for packed variants |
| `0x194B98` | `RemapIndex` | verified |
| `0x194C00` | `CountBoneBits` | verified |
| `0x194CD0` | `BuildBoneMap` | verified |
| `0x194D44` | `BuildActiveBoneSet` | verified |
| `0x195BA8` | `LoadIdxData` | fully ported and validated |
| `0x1969A4` | `LoadPairData` | fully ported and validated |
| `0x196D88` | `LoadRotRange` | fully ported and validated |
| `0x196E98` | translation/scale range loader | fully ported and validated |
| `0x197BE0` | `LoadSetupFrames` | structural traversal fully ported and validated |
| `0x198A38` | duration descriptor helper | fully ported |
| `0x198B64` | rotation value reader | boundaries ported; payload decode is next target |
| `0x198D48` | extended vector value reader | boundaries ported; payload decode pending |
| `0x198E4C` | packed duration decoder | fully ported and validated |
| `0x198F40` | due-channel list builder | fully ported structurally |
| `0x199058` | frame-stream processing | structural traversal fully ported and validated |
| `0x199360` | `GenerateFrame` | control flow understood; output composition pending |

## Verified setup structure

Starting after `LoadIdxData`:

```text
constant rotation records
constant translation records
rotation range nibble table
translation range records
scale range records
frame-processing stream
```

No alignment is inserted between setup blocks. The frame-processing stream itself aligns value blocks to four bytes.

## Verified frame stream and timing

1. Align `frame_data_file_offset` to 4.
2. Read initial value records for all animated rotation, translation and scale channels. These are keys at frame 0.
3. Read one timing header.
4. Explicit duration data is aligned to 2 and stored as BE16 words consumed LSB-first.
5. Align to 4 and read the second key value for every animated channel.
6. For scan frames `1 .. frame_count-2`, read a header, update durations and read records only for channels due at that scan frame.

Header:

```text
bits 0..1  explicit duration width = value + 3
bit 2      scale duration is implicitly 1
bit 3      translation duration is implicitly 1
bit 4      rotation duration is implicitly 1
bits 5..7  zero in all supplied clips
```

Explicit duration code:

```text
prefix 0 -> duration 1
prefix 1 -> next 3..6 LSB-first bits + 1
```

A channel is due when `key_frame + duration == scan_frame`. Every channel in all 30 validation clips begins at frame 0 and ends exactly at `frame_count - 1`.

## Verified record advances

```text
rotation:       8 or 12 bytes, selected by bit15 of BE16@0
compact vector: 4 or 8 bytes, selected by bit31 of BE32@0
extended vector: 4/8/12 bytes from bit31 of BE32@0 and BE32@4
```

Codec selection:

```text
translation extended when (flags & 0x0C) == 0x0C
scale extended when       (flags & 0x30) == 0x30
```

## Validation

Strict parsing against all 30 supplied Warus clips and the full 81-node skeleton:

```text
30 / 30 index blocks parsed
30 / 30 setup blocks parsed
30 / 30 complete frame streams traversed
all key lists strictly increasing
all channels end at frame_count - 1
all streams end exactly 8 zero bytes before file end
335 .. 3354 value records per clip
```

For `016__b_idle_1_ws`:

```text
frame count:              61
frame-data start:         0x1CC
first header:             0x364
second value block end:   0x524
stream end:               0x2E30
file size:                0x2E38
resolved value records:   1444
```

## Rotation and vector value payloads: current truth

Verified:

- record boundaries and key times are exact;
- rotation records are fixed 8/12-byte advances;
- quaternion `W` is reconstructed from `X/Y/Z` and a sign path;
- translation and scale use per-channel base/span ranges;
- playback uses quaternion Slerp.

Still pending before real animation output:

- instruction-exact payload decode for all `0x198B64` branches;
- compact vector payload decode;
- extended vector payload decode in `0x198D48`;
- interpolation/output composition and bind-pose convention;
- verification against the 41 RenderDoc frames;
- Blender quaternion/location/scale F-curves.

## Packed variants

`packed_clip_82`, `packed_state_c1`, and `packed_state_c2` are separate codec families. `anim_packed_sample_decode.py` remains experimental and is not verified.

## Rejected earlier assumptions

- `0x54` is the rotation bitmap — rejected; it is the flags byte.
- marker-spaced six-byte vectors are the normal-clip codec — rejected.
- `LoadIdxData` reads key times or a serialized permutation table — rejected.
- frame body is one fixed-stride value per channel per frame — rejected.
- timing remained an unknown blocker — rejected; timing and record traversal are now fully resolved.
