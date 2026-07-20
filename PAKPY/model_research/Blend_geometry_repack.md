# BLEND geometry repack workflow

This document describes the first geometry-repack implementation for exported
CMDL/SMDL/WMDL model packages and CHAR packages.

## What it does

A changed Blender file can now replace the geometry of the corresponding model
resource while the original armature and material partition structure remain
fixed.

Supported changes per existing source `MESH` part:

- arbitrary vertex count;
- arbitrary triangle count and topology;
- changed vertex positions;
- changed split normals and tangents;
- changed UV0 coordinates;
- changed skin weights using the original skin bones;
- 16-bit or 32-bit index buffers, selected automatically;
- evaluated non-armature Blender modifiers;
- changed PNG/TXTR files in the same package during the same rebuild.

The rebuild works both when selecting one model-package directory and when
selecting the root of a CHAR package. For a CHAR package, every nested model
package is checked and all changed models/textures are written into one new PAK.

## Required workflow

1. Export the CHAR or model package again with the current PAKPY version.
   Older `.blend` files do not contain the bind-pose safety snapshot.
2. Open the generated file referenced by
   `experimental_skeletal_blend` in `repack_manifest.json`.
3. Edit the objects in the `__MESH_PARTS` collection.
4. Save the same `.blend` file.
5. Optionally edit supported files in `textures/png` or
   `textures/raw_txtr`.
6. In PAKPY choose **Modellpaket zurückbauen**.
7. Select either the individual model-package folder or the CHAR-package root.
8. Select the destination for the rebuilt PAK.

A changed `.blend` file is detected through the SHA-1 stored in the model
manifest. Texture changes are detected independently using their own manifest
hashes.

## Armature rule

The model geometry may change freely, but the source skin definition must stay
unchanged. The rebuild validates all of the following before Blender exports the
edited mesh:

- armature object transform;
- number of skin bones;
- bone names;
- `pakpy_skin_bone_index` order;
- parent hierarchy;
- Edit Mode rest/bind matrices.

Pose Mode changes and active animations are ignored. Blender is forced to export
the armature in rest position.

Weight painting is allowed. Every exported vertex is reduced to the four
strongest valid original-bone influences and the weights are normalized. A
replacement mesh must keep or receive an Armature modifier and vertex groups for
the original bones; an unskinned replacement cannot be written into an SMDL.

## Source-part rule

The number of source `MESH` parts remains unchanged in this version. Each object
must retain a unique `pakpy_source_mesh_index` matching one original part.

Inside a part, topology is unrestricted. The implementation does not require the
old vertex count or old index count.

Material assignment is still taken from the original source `MESH` record.
Changing Blender material slots does not create new game material records.

## Blender modifiers

The temporary glTF export requests Blender's evaluated mesh and applies
non-armature modifiers. The armature modifier remains skin data rather than
being baked as a posed mesh.

Shape-key/morph-target export is disabled. Apply the desired shape to the base
mesh before rebuilding when it must become permanent geometry.

## Generated diagnostics

For every changed model, the package `debug` directory receives:

- `repack_from_blend.glb` — Blender's temporary exchange file;
- `repack_from_blend.log.txt` — Blender stdout/stderr;
- `repack_geometry_summary.json` — rebuilt mesh/vertex/face/buffer counts.

These files are diagnostics only and are not inserted into the PAK.

## Current limits

Not yet supported:

- adding or deleting source `MESH` parts;
- changing the source material index of a part;
- adding, deleting, renaming or repositioning bones;
- rebuilding SKEL or ANIM resources;
- morph targets;
- authoring additional game-specific vertex channels such as unknown secondary
  UV/color/custom data.

For unknown vertex-layout components, the encoder copies the first original
vertex record as a template and overwrites all understood fields. This preserves
constant/default bytes, but it does not expose every game-specific attribute in
Blender yet.

## Failure behavior

The rebuild stops before writing the output PAK when:

- Blender cannot be found;
- the bind snapshot is missing;
- the armature was structurally changed;
- a source `MESH` part is missing or duplicated;
- a vertex references an unknown bone;
- Blender does not produce triangles;
- the rebuilt model cannot be decoded again;
- two nested packages provide conflicting replacements for the same PAK entry.
