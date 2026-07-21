# Fur rendering notes from EXEFS

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

## Texture-property mapping

The FURM samples use:

| Material property | Viewer slot | Evidence |
|---|---|---|
| `DIFTTXTR` | base color | common material slot and `uc_diffuseMap` |
| `NMAPTXTR` | tangent-space normal | `uc_normalMap` |
| `SPCTTXTR` | specular texture | `uc_specularMap` |
| `SPCFTXTR` | 1D specular falloff curve | 128x1 texture and `uc_specularFalloffMap` |
| `FURTTXTR` | strand/shell mask | binary-looking 32x32 texture and `uc_furMap` |
| `FURLTXTR` | length map | grayscale body-region mask and `uc_furLengthMap` |
| `FURFTXTR` | flow map | signed-looking RG direction texture and `uc_furFlowMap` |

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

`LCNTCOLR` must not be interpreted as a generic RGB color. In the supplied Cranky model its first component is `5` for the main fur material, `8` for the beard material and `0` for the explicitly named `NO_fur` base material. The viewer therefore uses `LCNTCOLR.x` as the static shell count. This is a strong sample-based inference, not a recovered source-level type declaration. The remaining components appear to be render/LOD controls and are currently preserved only for diagnostics.

## Current viewer approximation

Implemented:

- opaque/base material pass;
- repeated shell displacement along vertex normals;
- strand mask, length map and flow map;
- EXEFS material shell count, thickness, density and root occlusion;
- tangent/flow-oriented specular response using the 1D falloff texture;
- rim lighting parameters;
- exact `DIFCCOLR` lookup, avoiding the previous `LCNTCOLR` neon-tint bug.

Not yet reconstructed:

- the separate `FurFins` silhouette pass;
- runtime `FurDynamics`, external forces, drag and constraints;
- the exact original alpha/depth blend state and all LOD rules;
- exact interpretation of the remaining `LCNTCOLR` components and `FROSSCLR`.
