# Fur rendering notes from EXEFS and RenderDoc

These notes describe the evidence used by the mesh viewer's static fur pass. They are not a claim that the original runtime shader has been reconstructed bit-for-bit.

## EXEFS strings and shader permutations

The decompressed `main` NSO contains the following adjacent strings in its read-only segment:

- `Fur`
- `FurFins`
- `FurDynamics`
- `uc_normalMap`
- `uc_specularMap`
- `uc_specularFalloffMap`
- `uc_specularPower`
- `uc_drag`
- `uc_stiffnessCoefficient`
- `uc_constraintHeight`
- `uc_constraintEllipseRatioSqr`
- `uc_diffuseMap`
- `uc_furMap`
- `uc_rimFresnelMin`
- `uc_rimFresnelMax`
- `uc_rimBrightness`
- `uc_furDensity`
- `uc_furOcclusionStartLength`
- `uc_furLengthMap`
- `uc_furFlowMap`
- `uc_furThickness`
- `uc_furFlowStrength`
- `uc_furBendPower`

The same region contains these compile/permutation names:

- `FUR_FINS`
- `INITIALIZE_FUR_DYNAMICS`
- `APPLY_FUR_DYNAMICS`
- `OPAQUE_PASS`
- `GBuffer`

The function at text offset `0xE09F8` conditionally adds those defines from a flag word. This confirms that the original renderer has separate fin, dynamics, opaque and deferred/G-buffer paths rather than treating fur as an ordinary Phong/PBR material.

## Recovered pass and depth behaviour

`CMaterial_Fur::ApplyMaterial` and `ApplyIdentifiedMaterial` construct a depth state with depth testing and depth writing enabled for the normal Fur draw. `SetupInstanceInfo` also constructs at least two separate paths:

- a depth-enabled path with `NoColorWrite`, associated with Fur initialization/stream-out work;
- a full-color path with its own depth mode.

The executable also exposes alpha-to-coverage state and NVN alpha-reference controls. A direct source-level link between every one of those calls and the Fur color pass has not been recovered, but the `OPAQUE_PASS`/`GBuffer` permutations and enabled depth writing show that ordinary back-to-front alpha blending is not the primary Fur path.

The viewer therefore keeps opaque depth-writing shells and uses deterministic UV-bound cutouts. The earlier screen-space dither was removed after the capture showed stable instanced layers; it produced temporal pepper noise that is not present in the game.

## RenderDoc capture evidence

The supplied Vulkan capture contains the Fur-area draws at EIDs 263, 270, 275, 281, 286, 292 and 297. The relevant `vkCmdDrawIndexed` instance counts include:

- EID 275: 8 instances;
- EID 286: 8 instances;
- EID 297: 3 instances.

The mesh viewer output for an individual instance shows a displaced copy of the same Fur surface topology. This establishes that the visible volume is formed by instanced shell geometry rather than by applying `FURTTXTR` as a single colour overlay.

The capture also shows that actual draw instance count can be selected by runtime/LOD logic. `LCNTCOLR.x` remains useful as a material-side layer-control value, but it must not be assumed to equal every submitted draw's instance count without the original CPU selection logic.

## Texture-property mapping

The FURM samples use:

| Material property | Viewer slot | Evidence |
|---|---|---|
| `DIFTTXTR` | base color | common material slot and `uc_diffuseMap` |
| `NMAPTXTR` | tangent-space normal | `uc_normalMap` |
| `SPCTTXTR` | specular texture | `uc_specularMap` |
| `SPCFTXTR` | 1D specular falloff curve | 128x1 texture and `uc_specularFalloffMap` |
| `FURTTXTR` | strand/shell coverage | binary-looking 32x32 texture and `uc_furMap` |
| `FURLTXTR` | length map | grayscale body-region mask and `uc_furLengthMap` |
| `FURFTXTR` | flow map | signed-looking RG direction texture and `uc_furFlowMap` |

`FURTTXTR` is not a color texture. The supplied sample is effectively a binary 32x32 coverage pattern. It must control which shell fragments survive; the final Fur RGB still comes from `DIFTTXTR` multiplied by `DIFCCOLR`.

The pattern must remain at a stable UV position between instances so surviving pixels form coherent strand columns. Random screen-space coverage or unrelated per-layer UV offsets break those columns and create noise.

## Scalar and color properties

The names line up with the EXEFS uniforms as follows:

| Property | Meaning used by viewer |
|---|---|
| `SPCPSCLR` | specular power |
| `RFMNSCLR` | rim Fresnel minimum |
| `RFMXSCLR` | rim Fresnel maximum |
| `RBRTCOLR` | rim RGB plus strength in W |
| `FRDNSCLR` | fur mask density/repetition |
| `FRTHSCLR` | fur thickness/maximum shell displacement |
| `FROCSCLR` | fur root-occlusion start |
| `FRFSSCLR` | flow strength |
| `FRBPSCLR` | shell/bend curve power |
| `DRAGSCLR` | dynamics drag; recorded but not simulated |
| `SCOFSCLR` | dynamics stiffness coefficient; recorded but not simulated |
| `CONHSCLR` | dynamics constraint height; recorded but not simulated |
| `CONESCLR` | dynamics constraint ellipse ratio; recorded but not simulated |
| `DIFCCOLR` | diffuse/base tint |
| `ICMCCOLR` / `ICNCCOLR` | incandescence/emission colors depending material family |

`LCNTCOLR` must not be interpreted as a generic RGB color. In the supplied Cranky model its first component is `5` for the main fur material, `8` for the beard material and `0` for the explicitly named `NO_fur` base material. The viewer currently uses it as the maximum static shell count when the game's runtime LOD decision is unavailable. The remaining components appear to be render/LOD controls and are preserved for diagnostics.

## Current viewer approximation

Implemented:

- opaque base-material pass;
- depth-writing cutout shells rather than a Fur-map colour overlay;
- stable UV-bound strand coverage across shell instances;
- progressively narrower outer-shell cutout edges without screen-space noise;
- length-map-scaled displacement;
- flow-map bending in the tangent/bitangent plane;
- EXEFS material thickness, density and root occlusion;
- tangent/flow-oriented specular response using the 1D falloff texture;
- bounded, albedo-aware rim lighting;
- Fur RGB from `DIFTTXTR * DIFCCOLR` only;
- exact `DIFCCOLR` lookup, avoiding the previous `LCNTCOLR` neon-tint bug.

Not yet reconstructed:

- the exact shader formula that maps `InstanceIndex` to shell height;
- the CPU/LOD rule that selects 8, 3 or another submitted instance count;
- the separate view-dependent `FurFins` silhouette pass;
- runtime `FurDynamics`, external forces, drag and constraints;
- the exact original multisample alpha-to-coverage state;
- exact interpretation of the remaining `LCNTCOLR` components and `FROSSCLR`;
- the final platform shader's exact equations and constants.
