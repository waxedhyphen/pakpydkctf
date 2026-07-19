# DKCTF `normal_clip` setup stage

This document covers the serialized bytes consumed after `LoadIdxData` and before frame processing.

## Binary identity

| Function | Address | Size | SHA-256 of decompressed `.text` bytes |
|---|---:|---:|---|
| `CAnimStreamData::LoadPairData(int&)` | `0x1969A4` | `0x3E4` | `631fe23372931e185023a58377384fadea90227cb80f057c21b5745a69b75f62` |
| `CAnimStreamData::LoadRotRange(int&)` | `0x196D88` | `0x110` | `acf47b03c98852a04780d72c12c1b9c13552d5b70ee6c9e0183c535759995852` |
| vector range loader | `0x196E98` | `0x198` | `a43c153606354c42130a2e80deb6a8bcc2aad906145750fc9884385ece7e6474` |

The calling order is visible in the stream constructor at `0x1955C8..0x1958A0`:

```text
LoadIdxData
LoadPairData
allocate animated rotation ranges
LoadRotRange
allocate animated translation ranges
vector range loader
apply translation precision multiplier
allocate animated scale ranges
vector range loader
apply scale precision multiplier
store final offset at CAnimStreamData+0x08
```

The final stored offset is the first byte consumed by later frame processing.

## Serialized order

Starting at `LoadIdxDataResult.load_pair_data_file_offset`:

```text
constant rotation records       one per constant rotation node
constant translation records    one per constant translation node
rotation range nibble table      ceil(animatedRotationCount / 2) bytes
translation range records        8 bytes per animated translation node
scale range records              8 bytes per animated scale node
frame-processing stream          begins here
```

No alignment is inserted between these blocks.

## `LoadPairData`: constant rotations

The decoder always performs a 12-byte lookahead but advances by either 8 or 12 bytes:

```text
recordSize = 8 + (BE32(record[0:4]).bit31 ? 4 : 0)
```

Let `raw0` and `raw1` be little-endian CPU loads from bytes `0..3` and `4..7`, and `be0/be1 = bswap32(raw0/raw1)`.

```text
qx = bswap32(raw0 & 0x00FFFF0F) | byte9
middle = BFI(be1 >> 20, be0, lsb=12, width=8)
qy = BFI(byte10, middle, lsb=8, width=20)
qz = BFI(byte11, be1, lsb=8, width=20)

X = qx * 2^-27 - 1
Y = qy * 2^-27 - 1
Z = qz * 2^-27 - 1
```

`W` is reconstructed from `X/Y/Z`; bit 30 selects its sign. Stored order is `(W, X, Y, Z)`.

Across the 30 supplied Warus clips, all observed constant-rotation records use the compact 8-byte advance. Decoded quaternions are finite and unit length within floating-point precision.

## `LoadPairData`: constant translations

It uses the same 8/12-byte advance rule and a 12-byte lookahead.

```text
exponent = bits25..29 of BE32(record[0:4])
R = 2^exponent
if bit30 is set: R = 1 / R
value = integer * (2 * R * 2^-29) - R
```

The three 29-bit integers are assembled by the exact `BFI/BFXIL/REV` sequence in the production parser.

## `LoadRotRange`

The table contains one 4-bit nibble per animated rotation channel, two channels per byte.

**Verified nibble order:** low nibble first, high nibble second.

```text
Rbits = 0x3F800000 - (n << 22)
R = reinterpret_float(Rbits)
base = -R
scale = R * 2^-23
```

The earlier `R * 2 * 2^-23` claim is rejected.

## Translation and scale range records

The vector range loader consumes one 8-byte record per animated channel and produces six floats:

```text
baseX, baseY, baseZ,
rawSpanX, rawSpanY, rawSpanZ
```

It reconstructs compact IEEE-754 values and multiplies differences by `1.0078740119934082`.

The constructor then scales only the span fields:

```text
translation: flags bit2 set -> 2^-30, otherwise 2^-20
scale: ((flags & 3) + 1) & 3 == 3 -> 2^-30, otherwise 2^-20
```

## Validation

Strict setup parsing was run against all 30 supplied Warus `normal_clip` files with the full 81-node skeleton.

```text
30 / 30 setup blocks parsed
all constant quaternions finite and norm ~= 1
all constant vectors finite
all ranges finite
frame-data offsets: 0x122 .. 0x1ED
```

For `016__b_idle_1_ws`:

```text
LoadPairData start:       0x081
constant rotations:       16
constant translations:    2
LoadPairData end:         0x111
rotation ranges end:      0x124
translation ranges end:   0x164
frame-data start:         0x1CC
```

## Runtime output

The probe integration writes:

```text
normal_clip_setup.constant_rotations
normal_clip_setup.constant_translations
normal_clip_setup.rotation_ranges
normal_clip_setup.translation_ranges
normal_clip_setup.scale_ranges
normal_clip_setup.frame_data_file_offset
```

Animated samples remain pending. The next target is `CAnimStreamProcess::LoadSetupFrames @ 0x197BE0` and its value readers.
