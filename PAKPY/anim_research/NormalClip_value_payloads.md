# DKCTF `normal_clip` value payloads

Status: **instruction-level port complete** for the three animated value readers.
Validated against the 30 supplied Warus clips.

## Binary functions

| Address | Role | Status |
|---:|---|---|
| `0x198B64` | animated rotation reader | ported |
| `0x198D48` | extended 30-bit vector reader | ported |
| `0x199170` / `0x19926C` | inline compact 20-bit vector reader | ported |
| `0x195754` | translation span post-scale | ported/corrected |
| `0x1958A4` | scale span post-scale | ported/corrected |
| `0x1973BC` | pose interpolation/output | next composition target |

## Important correction: vector range span scaling

`LoadVecRange @ 0x196E98` reconstructs a base vector and an unscaled span.
Its caller subsequently multiplies the span according to the codec selected by
the stream flags.

```text
translation extended: (flags & 0x0C) == 0x0C
translation compact:  otherwise

scale extended:       (flags & 0x30) == 0x30
scale compact:        otherwise
```

Exact constants loaded by the binary:

```text
extended / 30-bit: float bits 0x30800000 = 0x1.0000000000000p-30
compact / 20-bit:  float bits 0x35800008 = 0x1.0000100000000p-20
```

The earlier implementation selected these constants from unrelated low flag
bits. That produced incorrect extended scale values and is rejected.

## Rotation record (`0x198B64`)

The routine performs a 12-byte lookahead but advances the stream by 8 or 12
bytes. Overlap with the following record is intentional.

```text
h0 = BE16 @ +0
h1 = BE16 @ +2
h2 = BE16 @ +4
h3 = BE16 @ +6
b8..b11 = bytes @ +8..+11

record size = 12 if h0.bit15 else 8
W sign      = -1 if h0.bit0 else +1
special     = h0.bit14
```

Normal quaternion payload:

```text
qx = (h1 << 8) | b9
qy = (h2 << 8) | b10
qz = (h3 << 8) | b11

X = channelBase + channelScale * qx
Y = channelBase + channelScale * qy
Z = channelBase + channelScale * qz
```

If `special` is clear and `X²+Y²+Z² < 1`:

```text
W = sign * sqrt(1 - X² - Y² - Z²)
```

Otherwise XYZ is normalized and `W=0`.

Compact exact-axis form occurs when `bit15=0` and `bit14=1`. `h1/h2/h3` are a
permutation of quaternion component slots `1,2,3`; one XYZ component becomes
`+1` or `-1`, the other components and W become zero.

The record also contains an interpolation correction code:

```text
code = (((h0 >> 2) & 0xFFF) << 7) | (b8 & 0x7F)
sign bit = h0.bit1
```

The sparse quaternion key itself is fully decoded. Applying this correction
exactly as the game does belongs to the later pose-interpolation layer.

## Compact vector record (inline `ProcessFrame` path)

The routine performs an 8-byte lookahead and advances by 4 or 8 bytes.
Components are unsigned 20-bit integers.

```text
record size = 8 if BE32@0.bit31 else 4
value[i] = rangeBase[i] + rangeSpan[i] * quantized[i]
```

The bitfields are ported instruction-for-instruction in
`anim_normal_clip_values.py`.

## Extended vector record (`0x198D48`)

The routine performs a 12-byte lookahead and advances by 4, 8 or 12 bytes.
Components are unsigned 30-bit integers.

```text
record size = 4 + 4 * (first.bit31 + (first.bit31 & second.bit31))
value[i] = rangeBase[i] + rangeSpan[i] * quantized[i]
```

As with rotations, lookahead overlap is part of the codec and must not be
replaced with isolated fixed-size records.

## Validation

Strict result over the 30 supplied clips and the 81-node skeleton:

```text
clips decoded:                 30 / 30
total animated value records: 42,681
rotation records:             31,172
compact vector records:        5,033
extended vector records:       6,476
special axis rotations:            6
quaternion norm range:         0.9999999999999999 .. 1.0
compact quantized range:       0 .. 2^20-1
extended quantized range:      0 .. 2^30-1
all vector outputs finite:     yes
all decoded key lists exactly match the verified schedule: yes
```

## Runtime output

Each normal clip now has a separate sparse value document under:

```text
debug/anim_normal_clip_values/*.normal_clip_values.json
```

It contains exact node-indexed rotation, translation and scale keys, plus
constant rotations/translations. The generic old timeline path remains blocked
until pose composition and coordinate conversion are implemented.

## Remaining work

1. Port/describe the interpolation and output composition around `0x1973BC`.
2. Determine how decoded local values combine with the SKEL bind transforms.
3. Apply the ANIM root transform and DKCTF-to-Blender coordinate conversion.
4. Validate composed matrices against the 41 RenderDoc captures.
5. Emit real Blender quaternion/location/scale F-curves.
