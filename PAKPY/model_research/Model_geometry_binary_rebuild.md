# Model geometry binary rebuild

## Scope

The geometry encoder rebuilds the binary model resource while preserving all
unmodified chunks and the original source partition layout. It currently targets
CMDL, SMDL and WMDL resources whose existing `MESH` part count is unchanged.

## Input path

The edited `.blend` is opened by the installed Blender executable in background
mode. PAKPY selects the armature and all objects carrying
`pakpy_source_mesh_index`, forces rest-pose export, and writes a temporary GLB.

The GLB stage is used instead of reading Blender's internal mesh structures from
normal Python because Blender then handles:

- evaluated non-armature modifiers;
- triangulation;
- split vertices caused by per-loop UVs and normals;
- coordinate conversion back to glTF/model axes;
- skin joint and weight export.

PAKPY reads the temporary GLB accessors and resolves its joint names back to the
original SKEL skin-bone order.

## Resource chunks

### HEAD

The original 96-byte (or larger) payload is preserved. Only bounding-box minimum
and maximum values are recalculated from the rebuilt geometry.

The five existing mesh-bucket counts remain unchanged because the source `MESH`
record count and flags remain unchanged.

### MESH

Every original 21-byte record is retained as a template. The encoder preserves:

- material index;
- vertex-buffer index;
- index-buffer index;
- unknown fields and flags.

It rewrites:

- primitive mode to triangle list (`3`);
- index-buffer offset;
- index count.

### VBUF

The number of vertex buffers and each component descriptor remain unchanged.
Meshes that originally shared a VBUF are concatenated into that same rebuilt
VBUF. Their indices receive the appropriate local vertex-base offset.

Known layouts written by the encoder:

- format `37`, semantic `0`: float32 position XYZ;
- format `34`, semantic `1`: float16 normal XYZW;
- format `34`, semantic `2/3`: float16 tangent XYZW;
- format `20/21`, UV semantics: float16 UV;
- format `22`, semantic `9`: four unsigned-byte joint indices;
- format `34`, semantic `10`: four float16 weights.

Unknown bytes start from a template copy of the first original vertex in that
VBUF.

### IBUF

The number of index buffers remains unchanged. Mesh index lists are concatenated
per original IBUF and the corresponding MESH offsets are updated.

The original 16-bit type is retained while all indices fit in `0..65535`.
The encoder upgrades the IBUF to type `2` (32-bit) when necessary.

### GPU

The number and ordering of GPU segments remain equal to
`VBUF count + IBUF count`.

All rebuilt segments use marker `0x0D000000` followed by zlib-compressed data.
This avoids needing an encoder for the older LZSS/arithmetic variants while
remaining readable by the existing model decoder.

### PAK model META

The existing META layout variant (A/B/C/D), grouping markers and segment count
are preserved. Offsets, compressed sizes and decompressed sizes are recalculated
for the new zlib segments.

The normal META builder previously rejected a changed GPU codec marker. The
geometry-repack patch relaxes only that codec-equality check while keeping the
segment-count and layout checks.

## Validation

Before the model asset is accepted, PAKPY decodes the newly generated resource
again with `load_model_with_skin` and verifies the source `MESH` count.

The normal PAK rebuild then recalculates ADIR offsets, model META and the outer
RFRM sizes, reparses the complete output PAK and rejects structural errors before
writing the final file.

## Tested paths

Automated tests cover:

- replacing a three-vertex source model with arbitrary five-vertex/four-triangle
  topology;
- zlib VBUF/IBUF output and re-decoding;
- GLB accessor extraction and joint-name remapping;
- transformed source-part nodes;
- CHAR-root discovery of nested model packages;
- armature rest-pose/hierarchy validation in the Blender script.

A local real-resource probe also rebuilt SMDL entry 661 from
`b00_mangrove_seaLion(4).pak`, increased the horn partition from 856 to 857
vertices and added one triangle. The resulting resource decoded with 5,255 total
vertices and 8,057 faces.
