# Mesh-part mapping and repack diagnostics

## Problem

The geometry rebuilder must map every Blender mesh object back to exactly one
original game `MESH` record. The authoritative Blender property is:

```text
pakpy_source_mesh_index = <integer>
```

Previously the Blender glTF exporter was expected to copy this custom property
into the temporary GLB node `extras`. Some Blender/exporter combinations can
place the property on the glTF mesh instead of the node, or omit it from the
node entirely. A replacement object renamed to a generic name such as `bake`
then had no name-based fallback. The resulting error only reported:

```text
fehlen=[1]
```

That did not explain that `1` was the one specific original source-part index,
nor which Blender objects were seen.

## Deterministic mapping

Before the background glTF export, every selected PAKPY mesh object is assigned
a temporary export-only name:

```text
__PAKPY_REPACK__mesh_001__bake
```

The original `.blend` is not saved with this temporary name. The name exists
only in the background Blender process. It provides a second deterministic
mapping channel in addition to custom properties.

The exporter also writes the source index to both:

- the Blender object;
- the Blender mesh data-block.

The GLB reader accepts the index from node extras, mesh extras, or the temporary
`__mesh_###__` name. User-facing object names therefore remain unrestricted.

## Detailed failures

When the source-part sets still do not match, the exception now reports:

- total number of original `MESH` parts;
- complete expected source-index list;
- complete recognized source-index list;
- number and identity of missing indices;
- number and identity of additional indices;
- original part name from the manifest where available;
- every exported mesh object name;
- object-level custom-property value;
- mesh-data-level custom-property value;
- final index resolved for each object;
- duplicate index assignments with all conflicting object names.

Example meaning:

```text
Fehlende Quellindizes (1): [1]
```

This means exactly one original part is missing: source `MESH` index `1`. It
does not mean one unspecified error, one error per object, or that every object
needs the value `1`.

## Debug files

The background export continues to write:

- `debug/repack_from_blend.glb`;
- `debug/repack_from_blend.log.txt`.

The log now includes one mapping line for each Blender object:

```text
PAKPY_REPACK_PART index=1 object=bake
```

This line verifies the value read directly from the `.blend` before glTF export.
