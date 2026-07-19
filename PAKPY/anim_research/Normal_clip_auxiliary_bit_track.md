# normal_clip auxiliary pre-index bit track

**Status:** implemented and regression-tested against the supplied Squawks corpus  
**ExeFS build:** SHA-256 `018d157673bfd932813555a5991e4257b57f52f89039a0b6685356767e62cd21`

## Root cause

Some class-`0x81` `normal_clip` resources set the sign bit in the first serialized
control halfword. The game then loads an auxiliary bit track between
`SAnimStreamStart` and `CAnimStreamData::LoadIdxData`.

The previous Python parser ignored that branch and treated the auxiliary bytes as
the first node bitmap. The resulting node-62/node-63 padding errors, invalid
selector counts, bogus frame headers and keyframes beyond the declared duration
were all downstream cursor-desynchronization symptoms.

This is not a model-name or Squawks-specific branch. Detection and length decoding
come entirely from serialized control and descriptor bits.

## ExeFS control flow

| Address | Operation |
|---:|---|
| `0x193708` | `CAnimStream::CreateAnimData` computes `SAnimStreamStart` |
| `0x1954DC` | signed control-halfword test enables the auxiliary track |
| `0x192F74` | decodes the 8/16-bit sample count from the control field |
| `0x1826DC` | loads the auxiliary descriptor and advances the stream cursor |
| `0x1825C4` | codec-0 setup value reader; consumes one byte for this layout |
| `0x195BA8` | `LoadIdxData` starts after the auxiliary track |

## Serialized length rule

The first auxiliary byte is a descriptor:

- descriptor bit 1 set: constant track, zero bits per sample;
- descriptor bit 1 clear: `descriptor >> 2` bits per sample.

For the current normal-clip layout, the stream first contains eight setup bits.
The cursor movement is therefore:

```text
payload_bits  = 8 + bits_per_sample * sample_count
payload_bytes = ceil(payload_bits / 8)
block_bytes   = 1 descriptor byte + payload_bytes
```

The decoder does not need the auxiliary values for skeletal pose reconstruction,
but it must consume the exact block length before parsing channel bitmaps.

The implementation deliberately accepts every descriptor covered by the ExeFS
calculation. It does not hardcode `0C 07`, `0E 07`, a character name, or a fixed
frame count.

## Corpus validation

All twelve supplied non-empty Squawks clips set the auxiliary-track control bit.
After applying the generic cursor rule:

- all base and selector bitmaps are valid for the 62-node skeleton;
- no node-62/node-63 padding bits remain;
- existing constant/range readers remain aligned;
- the existing frame/duration parser reaches `frame_count - 1` for every channel;
- the existing value decoder consumes the streams to their zero padding.

The five head-tracking clips do not set the control bit and remain on the original
path. The 30 supplied Warus clips also remain unchanged.

## Scope

This fixes class-`0x81` resources whose remaining data uses the already-supported
`normal_clip` index/setup/frame/value codecs. It does not add support for Sea
Lion's class-`0x82` packed clips or class-`0xC2` state resources.
