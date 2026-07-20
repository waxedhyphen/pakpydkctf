# Automatic normal_clip Actions in generated BLEND files

**Status:** implemented with a character-level final pass

## Export order

A Character export has two relevant phases:

1. each nested model package creates its exact skeletal GLB and BLEND;
2. after all models are complete, the character-level animation pipeline writes
   `debug/anim_normal_clip_bind/*.normal_clip_bind.json`.

The original automatic embed hook ran during phase 1. That is sufficient for
standalone model exports and model packages that already have local bind files,
but it can run too early when the authoritative bind files are produced only at
the Character root.

`blender_embed_character_actions_patch.py` now wraps the completed Character
export. It runs after phase 2 and:

1. locates every `models/*/model/*.experimental_skeletal.blend`;
2. opens each BLEND through Blender background mode;
3. points `blender_import_normal_clip_actions.py` at the Character package root;
4. imports all decoded Character-root and model-local normal clips;
5. saves the same BLEND with persistent Actions;
6. copies an individual Blender report into each model package.

The earlier model-level hook remains active for standalone model exports. Running
the Character final pass again is safe because Actions with matching names are
replaced before being recreated.

## Blender discovery

Blender is located through `PAKPY_BLENDER_EXE`, `BLENDER_EXE`, `PATH`, or the
normal Windows installation directories.

## Reports and manifests

Each model `repack_manifest.json` records:

```text
experimental_skeletal_blend_actions_status
experimental_skeletal_blend_action_count
experimental_skeletal_blend_action_error_count
experimental_skeletal_blend_action_error
experimental_skeletal_blend_action_report
```

The Character `manifest.json` records the aggregate values plus
`experimental_skeletal_blend_action_models`. The complete final-pass report is:

```text
blender_normal_clip_character_embed_report.json
```

The BLEND SHA-1 is recalculated after the final save.

## Failure handling

Unsupported ANIM classes do not abort model or Character export. Only available
`normal_clip_bind` documents are embedded. A missing Blender executable or an
individual Action conversion failure is recorded in the model and Character
manifests.

The subprocess timeout defaults to 900 seconds and can be changed with
`PAKPY_BLENDER_ACTION_TIMEOUT`. The Action frame rate defaults to 30 fps and can
be changed with `PAKPY_ANIM_FPS`.

Sea Lion class-`0x82`/`0xC2` resources remain outside this path until their
binary codecs are decoded.
