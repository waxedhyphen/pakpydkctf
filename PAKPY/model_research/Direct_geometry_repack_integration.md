# Direct geometry-repack integration

## Problem

The BLEND geometry rebuilder was originally installed only by `main.py` through
`blend_model_repack_patch.install(App)`. Other entrypoints could import
`gui.py` and `model_package.py` without installing that patch. In that state the
button **Modellpaket zurückbauen** still called the legacy texture-only function
and reported only `Geänderte PNGs`, even when the `.blend` file had changed.

## Current integration

`model_package.py` now installs the complete model export/repack stack whenever
the module is imported:

1. skeletal GLB/BLEND support;
2. exact SKEL bind matrices;
3. source `MESH` partition export;
4. minimal Outliner cleanup;
5. BLEND geometry extraction and binary model rebuilding.

The public `rebuild_model_package_from_folder` function is also a permanent
dispatcher to `blend_model_repack_patch.rebuild_from_blend_package`. It no
longer contains the legacy PNG-only implementation.

This makes the behavior independent of whether the application was started
through `main.py`, imported through `gui.py`, or called directly from another
Python entrypoint.

## Backward-compatible GUI result

Older GUI code still formats the field `changed_count` as `Geänderte PNGs`.
Until that presentation code is removed, the returned integer keeps numeric
compatibility but renders the additional lines:

```text
Geänderte PNGs: 3
Geänderte Modellressourcen: 1
Modellpakete geprüft: 1
```

The authoritative structured fields remain:

- `texture_changed_count`;
- `geometry_changed_count`;
- `model_package_count`;
- `geometry_summaries`.

## Regression test

`test_model_package_direct_geometry_rebuild.py` verifies that the public model
package entrypoint delegates to the BLEND-aware rebuild function, restores its
stable dispatcher after patch installation, and exposes texture, geometry and
package counts to older GUI output.
