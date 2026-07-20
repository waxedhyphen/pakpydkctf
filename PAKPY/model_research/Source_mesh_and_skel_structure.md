# PAK model/rig structure analysis

Source: `b00_mangrove_seaLion(4).pak` (73,928,768 bytes)

## Implementation status

Implemented by `mesh_partition_export_patch.py`:

- every source MESH record is exported as one compact glTF mesh and one scene node;
- Blender therefore receives one separately selectable object per source MESH record;
- deterministic names include model name, zero-padded source MESH index, material name, and a non-generic dominant SKEL joint when the weight evidence is strong;
- glTF node/mesh extras and Blender custom properties retain source indices, buffer references, offsets, counts, flags, material data, and used joint names;
- `_PAKPY_SOURCE_VERTEX_INDEX` preserves the original vertex-buffer index for every compacted exported vertex;
- non-skin SKEL nodes are added to glTF as named helper nodes and converted in Blender to `use_deform = False` helper bones while their helper objects are retained for exact transform inspection;
- model manifests record `source_mesh_objects`, `source_mesh_object_count`, `skel_helpers`, and `skel_helper_count`.

The split is deliberately performed at source MESH-record level. Connected geometry islands remain inside their source partition because island splitting would incorrectly fragment valid body meshes.

## Inventory

- 963 resources
- 22 CHAR
- 21 CMDL
- 14 SMDL
- 3 WMDL
- 10 SKEL
- 38 total model resources

Source MESH record distribution across the 38 models:

- 19 models: 1 MESH record
- 14 models: 2 MESH records
- 3 models: 5 MESH records
- 1 model: 6 MESH records
- 1 WMDL: 186 MESH records

Therefore 19 of 38 models already contain more than one source-level MESH record.

## Character/model/skeleton examples

### sea_lion

CHAR `sea_lion` references five SMDL skins and SKEL entry 40.

The main SMDL entry 396 contains two source MESH records:

| Source MESH | Material | Vertex buffer | Main joint evidence | Meaning |
|---|---|---:|---|---|
| 0 | `P2_pompy_helmet` | 1 | all 802 used vertices weighted to joint 31, `helmet_skin` | helmet |
| 1 | `pompy_fur3` | 0 | distributed over the character rig | body/fur |

The source distinction is strong and deterministic, but the former GLB/DAE representation turned both records into one Blender mesh object.

### emperor_painguin

SMDL entry 661 contains two source MESH records:

| Source MESH | Material | Main joint evidence | Meaning |
|---|---|---|---|
| 0 | `EmperorPainguin_Texture` | broad body rig | main body |
| 1 | `EmperorPainguin_Horn_Texture` | joint 0 `horn_root_skin`, joint 6 `horn_elbow_skin`, joint 10 `horn_hole_skin` | horn/weapon assembly |

The full SKEL node-name table also contains `projectile_attach_skin`. It is not in the 69-entry skin-bone table, so a skin-only armature export did not preserve it as a joint/bone.

### Warus_Shield

SMDL entry 241 contains five source MESH records:

- main character/shield geometry
- shield handle, fully weighted to `shield_skin`
- left pupil, weighted to `head_skin`
- right pupil, weighted to `head_skin`
- pupil locator geometry, weighted to `pupil_L_skin` and `pupil_R_skin`

Again, the source records are recoverable and semantically distinguishable.

## Important distinction

A source MESH record is primarily a draw/material/skin partition, not always a complete semantic object. Individual records may contain many disconnected geometry islands. For example, the sea-lion body record contains 70 connected components. Therefore automatic splitting should use two levels:

1. preserve every source MESH record as a distinct object/node;
2. optionally split connected components, rather than doing so unconditionally.

## Export representation

For each source MESH record, the exporter creates a separate glTF mesh and scene node that references the same skin. These fields are preserved in glTF extras and Blender custom properties:

- source MESH index
- material index and material name
- vertex-buffer index
- index-buffer index
- index offset and index count
- primitive mode
- MESH flags and unknown fields
- used joint indices and resolved SKEL names
- dominant joint evidence

Names are deterministic, for example:

`sea_lion__mesh_000__P2_pompy_helmet__helmet_skin`

The name is only a readable label. Source indices, offsets and the `_PAKPY_SOURCE_VERTEX_INDEX` attribute remain authoritative for future replacement/repacking.

## SKEL representation

The exporter preserves both:

- skin bones in their original skin-table order;
- non-skin helper/control/attachment nodes.

Non-skin nodes are represented as named glTF helpers. During BLEND creation they are also added to the armature as `use_deform = False` bones and retain their source node index, parent, flags and names as custom properties.

## Repacking status

The current package rebuild path only detects changed texture files. Modified OBJ, DAE, GLB, or BLEND geometry is not currently converted back into CMDL/SMDL/WMDL. Preserving exact source metadata now is therefore essential for implementing model-part replacement later.
