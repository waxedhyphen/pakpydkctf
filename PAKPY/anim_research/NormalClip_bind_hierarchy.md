# DKCTF `normal_clip` bind and hierarchy composition

Status: **instruction-level runtime hierarchy port complete** for the SKEL stage
between local ANIM CCoords and render/skinning matrices.

This stage consumes the local animation-delta pose from
`anim_normal_clip_pose.py`. It does not include the external actor/model transform
or Blender coordinate-basis conversion.

## Binary functions

| Address | Role | Status |
|---:|---|---|
| `0x11A490` | `CCoords::x_y_ss` | fully ported |
| `0x12C558` | `CSkelLayout::InitStartInfo` | relevant boundaries/anchor ported |
| `0x12C930` | `CSkelLayout::BuildBaseAbsFromRel` | fully ported |
| `0x12CA44` | `CSkelLayout::BuildBaseAbsInvFromAbs` | fully ported |
| `0x12E830` | `CSkelPose::BuildRelative` | fully ported |
| `0x12E358` | `CSkelPose::Transform` | fully ported |
| `0x18AA40` | `BuildAbsoluteScalePropagation` | fully ported |
| `0x18AB48` | `BuildAbsoluteNoScalePropagation` | fully ported |
| `0x12E9A0` | `CSkelPose::GetRenderTransforms` | normal render path fully ported |

## Layout start information

`CSkelLayout::InitStartInfo` derives three values from the SKEL parent/flag
tables:

```text
active_anchor  = first node whose flags contain mask 0x28
relative_start = first node >= 1 with flag bit 4 clear
hierarchy_start = relative_start advanced past parent=0xFF control roots
```

For the supplied 81-node Warus SKEL:

```text
active_anchor:   2  root
relative_start:  2
hierarchy_start: 3
```

Nodes 0 (`blendspace`) and 1 (`root.move`) are control slots. The relative CCoords
of node 2 (`root`) is selected as the active anchor and copied into absolute matrix
slot zero. It therefore drives the hierarchy whose serialized parents reference
node zero. Node 2 also receives its own direct absolute matrix.

## Animation plus bind CCoords

For every node from `relative_start` onward, `CSkelPose::BuildRelative` calls:

```text
CCoords::x_y_ss(out, animation, bind)
```

The exact operation is:

```text
out.rotation    = animation.rotation * bind.rotation
out.scale       = animation.scale * bind.scale       component-wise
out.translation = animation.translation + bind.translation
```

Translation is not rotated in this operation. Quaternion multiplication order is
animation first, bind second.

Nodes before `relative_start` remain identity/control CCoords unless another
runtime system explicitly writes them.

## Base absolute matrices

`CSkelLayout::BuildBaseAbsFromRel` does not use one uniform TRS rule:

1. Nodes before `hierarchy_start` use full `CCoords::BuildTransform`, including
   local scale.
2. Hierarchical nodes use `parentBaseAbsolute * QuaternionTranslationMatrix`.
   Their local bind scale is deliberately omitted.
3. `BuildBaseAbsInvFromAbs` stores the affine inverse of every base absolute
   matrix.

This is why a conventional GLTF-style bind hierarchy was not sufficient.

## Runtime absolute matrices

`CSkelPose::Transform` first clears the absolute 3x4 matrix buffer, then:

1. writes the active-anchor relative transform to absolute slot zero;
2. builds control roots in `[relative_start, hierarchy_start)` directly;
3. processes all remaining nodes in serialized order.

Per hierarchical node, node flag bit zero selects the path:

```text
flag bit 0 clear:
    absolute = parentAbsolute * childLocalTRS

flag bit 0 set:
    absolute = parentAbsolute
             * diag(1 / parentRelative.scale)
             * childLocalTRS
```

The second path is the scale-suppression/compensation path. The reciprocal is based
on the immediate parent's **relative CCoords scale**, not on a generic matrix
column normalization.

## Render/skinning matrices

The normal path in `CSkelPose::GetRenderTransforms` uses the SKEL skin-node table
without prefix guessing:

```text
render[skinIndex] = currentAbsolute[nodeIndex]
                  * inverseBaseAbsolute[nodeIndex]
```

For Warus this produces 60 render matrices from the complete 81-node hierarchy.
Helper and scale-compensation nodes participate in the global hierarchy even when
they are not themselves skin entries.

## Runtime output

`anim_normal_clip_bind_patch.py` writes compact 3x4 matrices to:

```text
debug/anim_normal_clip_bind/*.normal_clip_bind.json
```

Each document contains:

- exact layout start values;
- base absolute and inverse-base matrices;
- all 81 current absolute node matrices per frame;
- all 60 render matrices per frame;
- exact skin-node order and names.

## Validation

Strict evaluation over all 30 supplied Warus clips:

```text
clips composed:              30 / 30
absolute 81-node frames:     65,286
render 60-bone frames:       48,360
all matrix values finite:    yes
maximum absolute value:      9.33534035921
synthetic rest-pose check:   render matrices exactly identity
```

Five regression tests cover layout boundaries, quaternion multiplication order,
affine inversion, scale suppression and rest-pose render identity.

## Capture status

The hierarchy formulas are taken directly from the shipped NSO and are no longer
hypotheses. A strict numeric match to the 41 RenderDoc CSV files is not yet claimed
because those files contain no animation timestamps or external actor/model-root
matrix. Treating them as 41 consecutive integer frames of the 61-frame idle clip
is demonstrably incorrect.

The remaining capture task is to recover the requested animation time and the
common external transform for each capture, then compare the 60 render matrices
without fitting bone-local transforms.

## Remaining work

1. Recover capture timing and external actor/model transform.
2. Confirm whether the optional SKEL sign/permutation path is enabled by the real
   animation caller for this character.
3. Apply DKCTF-to-Blender basis conversion.
4. Convert local animation deltas into Blender pose-bone channels relative to rest
   matrices.
5. Emit and activate real Blender F-curves/Actions.
