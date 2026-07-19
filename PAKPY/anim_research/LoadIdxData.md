# `CAnimStreamData::LoadIdxData` reverse engineering

## Scope

```text
CAnimStreamData::LoadIdxData(SAnimStreamStart const&, int&)
text start: 0x195BA8
text end:   0x1969A4
size:       0xDFC / 3580 bytes
```

Relevant helpers:

```text
0x194B98 NAnimStream::RemapIndex
0x194C00 NAnimStream::CountBoneBits
0x194CD0 NAnimStream::BuildBoneMap
0x194D44 NAnimStream::BuildActiveBoneSet
0x195BA8 CAnimStreamData::LoadIdxData
0x1969A4 CAnimStreamData::LoadPairData
```

Binary hashes and the current status are maintained in `../ANIM_UPDATE.md`.

## Final result

`LoadIdxData` does not parse keyframe times, sample records, or a separately serialized permutation table.

It reads a two-level hierarchy of LSB-first bitmaps:

1. A node-space base bitmap creates an ordered node list for each transform class.
2. A selector bitmap addresses positions inside that list.
3. Selector bit `1` becomes an animated channel.
4. Selector bit `0` becomes a constant channel.
5. `RemapIndex` replaces selector-local positions with real skeleton node indices using the base list.

Transform classes are processed in this order:

```text
rotation -> translation -> scale
```

## Flags

The second byte of `SAnimStreamStart` contains the flags consumed here:

| Flag | Meaning |
|---:|---|
| `0x40` | rotation maps present |
| `0x20` | translation maps present |
| `0x10` | scale maps present |

Other bits are not interpreted by `LoadIdxData`.

## Locating `SAnimStreamStart`

For this RFRM form, the stream base is file offset `0x28`. The game computes the structure offset as:

```cpp
uint32_t ComputeStartOffset(const uint8_t* stream) {
    uint16_t h = ReadU16LE(stream);
    uint32_t off = 8;
    off = (off & ~1u) | ((h >> 6) & 1u);
    off += (h >> 2) & 1u;
    if (h & 0x80)
        off = off + stream[off] * 4 + 7;
    return off;
}
```

For all 30 supplied Warus clips:

```text
stream base:                    file 0x28
SAnimStreamStart:               file 0x53
SAnimStreamStart flags:         file 0x54
LoadIdxData serialized payload: file 0x55
```

The former assumption that the first rotation bitmap starts at `0x54` was a one-byte misalignment. `0x54` is the flag byte.

## Serialized layout

Let:

```text
N = full skeleton node count
B = ceil(N / 8)
```

`N` is the complete node count, not the skin-bone count.

The function consumes:

```text
if flags & 0x40: rotation base bitmap      B bytes
if flags & 0x20: translation base bitmap   B bytes
if flags & 0x10: scale base bitmap         B bytes

if flags & 0x40: rotation selector   ceil(rotationBaseCount / 8) bytes
if flags & 0x20: translation selector ceil(translationBaseCount / 8) bytes
if flags & 0x10: scale selector       ceil(scaleBaseCount / 8) bytes
```

There is no alignment between the six map blocks. The updated stream offset points directly at `LoadPairData`.

## Bit order

All maps are LSB-first inside each byte. Byte `EC` therefore yields:

```text
set positions: 2, 3, 5, 6, 7
```

For byte index `i`, bits are visited in this order:

```text
i*8+0, i*8+1, ... i*8+7
```

## Base maps

Each base map is `ceil(nodeCount / 8)` bytes. Every set bit appends the corresponding skeleton node index. Because bytes and bits are traversed in ascending order, the list is node-index ordered.

Equivalent code:

```python
base_nodes = [
    node
    for node in range(round_up_to_8(node_count))
    if bitmap[node // 8] & (1 << (node & 7))
]
```

Padding bits above `nodeCount - 1` must be clear.

## Selector maps

A selector is indexed by position in `base_nodes`, not by skeleton node number.

```python
animated_local = selector_set_positions
constant_local = selector_clear_positions_within_base_count
animated_nodes = [base_nodes[i] for i in animated_local]
constant_nodes = [base_nodes[i] for i in constant_local]
```

The so-called remap table used by `RemapIndex` is the expanded base-node list. No additional permutation table is serialized in this section.

## Helpers

### `CountBoneBits @ 0x194C00`

```cpp
int CountBoneBits(int logicalCount, const uint8_t* map) {
    return popcount(map[0 : (logicalCount + 7) / 8]);
}
```

### `BuildBoneMap @ 0x194CD0`

```cpp
int BuildBoneMap(int nodeCount, const uint8_t*& input, uint8_t* output) {
    int bytes = (nodeCount + 7) / 8;
    uint8_t* begin = output;
    for (int byteIndex = 0; byteIndex < bytes; ++byteIndex) {
        uint8_t bits = input[byteIndex];
        for (int bit = 0; bit < 8; ++bit)
            if (bits & (1u << bit))
                *output++ = uint8_t(byteIndex * 8 + bit);
    }
    input += bytes;
    return int(output - begin);
}
```

### `BuildActiveBoneSet @ 0x194D44`

```cpp
int BuildActiveBoneSet(
    int baseCount,
    const uint8_t* selector,
    uint8_t* animatedLocal,
    uint8_t* constantLocal
) {
    int bytes = (baseCount + 7) / 8;
    for (int byteIndex = 0; byteIndex < bytes; ++byteIndex) {
        uint8_t bits = selector[byteIndex];
        for (int bit = 0; bit < 8; ++bit) {
            uint8_t index = uint8_t(byteIndex * 8 + bit);
            if (bits & (1u << bit))
                *animatedLocal++ = index;
            else
                *constantLocal++ = index;
        }
    }
    return bytes;
}
```

The assembly looks like a byte containing many channel-type flags because all eight bit tests are unrolled. It is still a plain bitmap splitter.

### `RemapIndex @ 0x194B98`

```cpp
void RemapIndex(int count, uint8_t* indices, const uint8_t* baseNodes) {
    for (int i = 0; i < count; ++i)
        indices[i] = baseNodes[indices[i]];
}
```

## `CAnimStreamData` fields populated

The lists have a vector-like size/capacity/data layout. Confirmed consumers identify:

| Object offset | Meaning |
|---:|---|
| `+0x10/+0x14/+0x18` | animated rotation nodes |
| `+0x20/+0x24/+0x28` | animated translation nodes |
| `+0x30/+0x34/+0x38` | animated scale nodes |
| `+0x70/+0x74/+0x78` | constant rotation nodes |
| `+0x80/+0x84/+0x88` | constant translation nodes |
| `+0xB7` | full skeleton node count (`u8`) |

Constant scale nodes are split/remapped temporarily but not persisted. In the supplied samples all scale base entries are animated.

## Worked sample: `016__b_idle_1_ws`

```text
full nodes: 81
skin bones: 60
bitmap size: 11 bytes
```

| Offset | Size | Meaning | Result |
|---:|---:|---|---:|
| `0x53` | 2 | `SAnimStreamStart = 01 79` | flags `0x79` |
| `0x55` | 11 | rotation base | 53 nodes |
| `0x60` | 11 | translation base | 10 nodes |
| `0x6B` | 11 | scale base | 13 nodes |
| `0x76` | 7 | rotation selector | 37 animated / 16 constant |
| `0x7D` | 2 | translation selector | 8 animated / 2 constant |
| `0x7F` | 2 | scale selector | 13 animated / 0 constant |
| `0x81` | — | `LoadPairData` begins | — |

Raw maps:

```text
rotation base:     EC AF 8B D3 9E F9 C1 BD 7B FD 00
translation base:  0C 02 00 0D 00 06 80 01 00 00 00
scale base:        C0 2C 0A D2 04 20 00 00 00 00 00
rotation selector: FF BE FF FE 27 20 15
translation sel.:  3F 03
scale selector:    FF 1F
```

## Validation

The strict reference parser was run against all 30 supplied Warus `normal_clip` resources using the full 81-node skeleton:

```text
30 / 30 parsed
0 base-map padding violations
0 selector padding violations
0 partition failures
SAnimStreamStart = 0x53 for every sample
LoadPairData starts from 0x7F through 0x83
```

For every transform class:

```text
animated_count + constant_count == base_count
animated_nodes ∩ constant_nodes == empty
both lists preserve base-list ordering
```

## Corrections to previous notes

- `0x54` is not the rotation map; it is the flags byte.
- `b_idle_1` has 53 base rotation nodes, 37 animated and 16 constant, not 58 sequential rotation channels.
- `BuildActiveBoneSet` does not parse seven per-node channel flags.
- `LoadIdxData` does not parse key times.
- `LoadIdxData` does not parse a separate serialized remap/permutation table.

## Remaining work

The next decoder stages are outside this function:

1. `LoadPairData` for constant rotation/translation records.
2. Rotation/vector range loaders.
3. `LoadSetupFrames` for frame-block state and offsets.
4. Frame processing and key timing.
5. Exact value-record decoding.
6. `GenerateFrame`/Slerp and Blender TRS output.

`LoadIdxData` is no longer a blocker.
