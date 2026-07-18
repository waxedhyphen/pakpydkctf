# DKCTF ANIM normal-clip research

## Status

The supplied version-20 `ANIM` files are not fully sample-decoded yet. The previous generic signed-16-bit interpretation is not supported for `normal_clip`; it should not be promoted as a correct decoder.

## Confirmed from the supplied files

- Wrapper magic: `RFRM`, nested form `ANIM`, version `20`.
- The control word's high byte `0x81` identifies the observed normal clips; its low byte matches the package's frame-count guess.
- File bytes `0x30..0x53` form one stable 36-byte structure:
  - 7-byte prefix `07 01 FF 01 00 00 00`
  - seven big-endian `float32` values
  - final flag byte `01`
- Those seven floats behave across all 30 clips like a 4+3 transform-shaped field. Idle is `[1,0,0,0, 0,0,0]`; turning and hurl clips contain meaningful nonzero values. The exact engine semantic still needs confirmation.
- The body begins at `0x54` in all supplied files.
- Its first 33 bytes are three fixed 11-byte fields. Each field is 88 bits while the matched skeleton has 81 nodes, leaving seven unresolved slots; therefore these must not yet be described as plain 81-bit masks.
- Byte 33 is zero in all 30 supplied clips.
- The remaining bytes are compressed/packed sample data.

## Strong hypotheses

The three 11-byte fields are candidate rotation, translation and scale channel maps. Their densities are consistent with that interpretation: the first is dense, the second and third are sparse. Their 88-to-81 slot relationship, bit order, node order and exact semantics are not yet proven. One plausible layout is seven special/control slots plus 81 skeleton-related slots, but this remains a hypothesis.

The seven pre-body floats are a candidate quaternion (`w,x,y,z`) plus vector (`x,y,z`) associated with root motion or a clip transform. This is strongly suggested by identity values in idle clips and mirrored/nonzero values in directional clips, but is not named as fact in the tooling.

## RenderDoc ground truth

The 41 CSV files contain 4096 `float4` rows each. The first 180 rows form 60 affine 3x4 skin matrices, exactly matching the 60 controller joints in the supplied skeletal DAE. With the DAE inverse-bind matrices:

```text
global_animated = skin_matrix @ inverse(inverse_bind)
local_animated  = inverse(parent_global_animated) @ global_animated
```

This produces 41 valid controller-joint poses. Joints whose parent is outside the 60-joint controller are retained in model space; other joints also receive parent-local transforms. They are exported by `tools/renderdoc_anim_reference.py` and can be imported into Blender with `tools/blender_import_renderdoc_reference.py`.

The captures are render poses and may contain interpolation. Capture index must not be assumed to equal a raw ANIM key index without timing evidence.

## Rejected / not proven

- Treating the normal body as a flat array of big-endian signed 16-bit vectors.
- The earlier seven-planes-by-eleven-bytes interpretation. Padding and cross-clip structure do not support it.
- A fixed per-channel bit width inferred only from file size. Clips with identical channel maps and frame counts can have different payload sizes, so clip-specific descriptors or variable coding are present.
- Treating the `b_idle_1_ws` payload as 61 independent 192-byte frame records merely because one alignment is divisible that way. Adjacent 192-byte blocks do not show frame-like correlation; the payload is more likely track-major or otherwise bit-packed.

## Next reverse-engineering target

Locate the channel quantization descriptors and establish the bit reader's order. A useful test is to decode one complete `b_idle_1_ws` pose and minimize matrix error against the exported RenderDoc local transforms. No candidate should be accepted merely because its values look numerically plausible.
