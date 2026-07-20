# Automatic normal_clip Actions in generated BLEND files

**Status:** implemented

## Behaviour

Model-package export still creates the exact skeletal GLB and BLEND first. After
the complete animation pipeline has written
`debug/anim_normal_clip_bind/*.normal_clip_bind.json`, a final export wrapper:

1. locates the generated `*.experimental_skeletal.blend`;
2. locates Blender through `PAKPY_BLENDER_EXE`, `BLENDER_EXE`, `PATH`, or the
   normal Windows installation directories;
3. opens the existing BLEND in background mode;
4. runs `blender_import_normal_clip_actions.py` for every decoded bind document;
5. saves the same BLEND with persistent Blender Actions.

No manual Scripting-workspace import is required for newly exported packages.
The generated importer remains in the package as a diagnostic and manual
fallback.

## Manifest fields

`repack_manifest.json` records:

```text
experimental_skeletal_blend_actions_status
experimental_skeletal_blend_action_count
experimental_skeletal_blend_action_error_count
experimental_skeletal_blend_action_error
experimental_skeletal_blend_action_report
```

The BLEND SHA-1 is recalculated after the Actions have been embedded.

## Failure handling

Unsupported ANIM classes do not abort model export. Only available
`normal_clip_bind` documents are embedded. A missing Blender executable or an
individual Action conversion failure is recorded in the manifest and in
`blender_normal_clip_action_report.json`.

The subprocess timeout defaults to 900 seconds and can be changed with
`PAKPY_BLENDER_ACTION_TIMEOUT`. The Action frame rate defaults to 30 fps and can
be changed with `PAKPY_ANIM_FPS`.

Sea Lion class-`0x82`/`0xC2` resources remain outside this path until their
binary codecs are decoded.
