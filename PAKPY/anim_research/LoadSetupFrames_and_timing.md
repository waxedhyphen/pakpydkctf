# DKCTF `normal_clip`: `LoadSetupFrames`, timing and frame traversal

Status: **verified and ported** on 2026-07-19.

Binary: Nintendo Switch NSO `main`, SHA-256
`018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21`.

Validation set: 30 Warus Shield `normal_clip` resources, all using the full
81-node skeleton.

## Functions covered

| Address | Role |
|---:|---|
| `0x197BE0` | `CAnimStreamProcess::LoadSetupFrames` |
| `0x198A38` | build duration descriptors or apply implicit duration `1` |
| `0x198E4C` | decode packed channel durations |
| `0x198F40` | build lists of channels whose next key is due |
| `0x199058` | process the next frame-stream block |

`0x198B64` and `0x198D48` are used to determine record boundaries here. Their
payload values are deliberately left for the next decoder layer.

## Complete serialized frame-stream layout

`normal_clip_setup.frame_data_file_offset` points to the setup-frame stream.
The first value block begins at:

```text
align_up(frame_data_file_offset, 4)
```

The serialized order is:

```text
initial value records for every animated rotation channel
initial value records for every animated translation channel
initial value records for every animated scale channel

initial timing header byte
optional packed duration words, aligned to 2 bytes

second value block, aligned to 4 bytes

for scan_frame = 1 .. frame_count-2:
    timing header byte
    optional packed durations, aligned to 2 bytes
    value records for channels due at scan_frame, aligned to 4 bytes

8 zero bytes at the end of every supplied resource
```

The first value block stores keys at frame `0`.

The initial timing header assigns the distance from frame `0` to each channel's
second key. The second value block stores those second keys; channels therefore
do not necessarily share the same second key frame.

Each later frame block updates only channels whose previously scheduled key is
at the block's `scan_frame`. The block first schedules their next key and then
stores the corresponding value records.

## Timing entry state

The process owns one 8-byte timing entry per animated channel. The fields used
by these functions are:

```text
+0x00 u16 previous/current key frame
+0x02 u16 duration to next key
+0x04 f32 interpolation value/reciprocal, prepared elsewhere
```

A channel is due when:

```text
key_frame + duration == scan_frame
```

When a due channel receives a new duration:

```text
key_frame = key_frame + old_duration
next_duration = decoded_duration
next_key_frame = key_frame + next_duration
```

After the final processed block, every channel in all 30 samples has
`next_key_frame == frame_count - 1`.

## Header byte

```text
bits 0..1  explicit-duration payload width minus 3
bit  2     scale durations are all implicitly 1
bit  3     translation durations are all implicitly 1
bit  4     rotation durations are all implicitly 1
bits 5..7  zero in all supplied samples
```

Thus:

```text
payload_width = (header & 3) + 3   # 3..6 bits
```

If a type's implicit bit is set, every active channel of that type receives
duration `1` and consumes no duration bits. If it is clear, that type is added
to the explicit duration descriptor list.

Descriptor order is always:

```text
rotation channels in active-list order
translation channels in active-list order
scale channels in active-list order
```

## Packed duration codec @ `0x198E4C`

The stream consists of **big-endian 16-bit words**, but bits are consumed
**LSB-first inside each word**.

Each duration uses a one-bit prefix:

```text
prefix 0:
    duration = 1
    bits consumed = 1

prefix 1:
    payload = next payload_width bits, LSB-first
    duration = payload + 1
    bits consumed = payload_width + 1
```

The function peeks and refills 16-bit words exactly as needed. Its resulting
byte position is equivalent to:

```text
start + ceil(bits_consumed / 16) * 2
```

No byte is consumed from a prefetched word if no bit from that word was used.

## Value-record advances

These rules are sufficient to traverse the complete stream without yet
interpreting payload values.

### Rotation reader @ `0x198B64`

```text
first = BE16 @ record+0
size = 12 if first.bit15 else 8
```

### Compact vector path

Used for translation unless `(flags & 0x0C) == 0x0C`, and for scale unless
`(flags & 0x30) == 0x30`:

```text
first = BE32 @ record+0
size = 8 if first.bit31 else 4
```

### Extended vector helper @ `0x198D48`

```text
first  = BE32 @ record+0
second = BE32 @ record+4
size = 4 + 4 * (first.bit31 + (first & second).bit31)
```

Possible sizes are `4`, `8`, and `12` bytes.

## `LoadSetupFrames` versus subsequent processing

`LoadSetupFrames` performs:

1. align frame data to 4 bytes;
2. decode/advance initial values for every animated channel;
3. initialize timing entries to zero;
4. read the initial timing header and channel durations;
5. align to 4 bytes;
6. decode/advance the second key value for every animated channel;
7. set the process frame cursor to `1`.

`ProcessFrame @ 0x199058` performs:

1. read the next header byte;
2. build active lists for channels due at the current scan frame;
3. advance the process frame cursor;
4. update durations, using implicit `1` or the packed codec;
5. align to 4 bytes;
6. read one new value record for each due channel.

To prepare the final resource frame, processing is needed for scan frames:

```text
1 .. frame_count - 2
```

There is no frame block for `frame_count - 1`; attempting to process one reads
into the final zero padding.

## Validation

Strict traversal over all 30 supplied clips produced:

```text
30 / 30 complete frame streams parsed
30 / 30 end exactly 8 zero bytes before file end
all channels begin with a key at frame 0
all channel key lists are strictly increasing
all channels end with a key at frame_count - 1
no frame-header bits 5..7 were set
```

Record counts range from 335 to 3354 per clip. The complete per-resource report
is in `load_setup_frames_validation.csv`.

For `016__b_idle_1_ws`:

```text
frame count:                  61
setup frame-data offset:      0x1CC
initial values end/header:    0x364
initial duration stream end:  0x38C
second value block end:       0x524
last processed scan frame:    59
frame stream end:             0x2E30
file size:                    0x2E38
trailing zeros:               8 bytes
resolved value records:       1444
```

## Runtime output

`anim_normal_clip_frames.py` exports:

```text
initial_records[]
blocks[].header and bit width
blocks[].duration_updates[]
blocks[].records[] with exact node, key frame, offset, size and codec
rotation_key_frames[][]
translation_key_frames[][]
scale_key_frames[][]
stream_end_file_offset
```

The runtime status is now:

```text
pending:normal_clip_value_decode
```

Timing and boundaries are no longer pending. The next task is to port the
payload math of `0x198B64`, the compact vector path and `0x198D48`, then feed
the resulting quaternion/vector keys into Blender.
