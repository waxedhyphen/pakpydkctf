# PAKPY ExeFS patch projects

## Architecture

The ExeFS patch engine is game-independent. It contains no DKCTF addresses, Build IDs, byte patterns or named gameplay fixes.

```text
exefs_patch.py
  generic project model
  JSON load/save
  Build-ID and original-byte validation
  IPS32 generation
  emulator and Atmosphère export

exefs_patch_gui_patch.py
  generic project editor
  arbitrary patch entries
  JSON import/export
  validation and export UI

exefs_profiles/*.json
  optional external game-specific projects
```

Deleting every file below `exefs_profiles/` does not remove any ExeFS editor or exporter functionality.

## Universal GUI

Open:

```text
Werkzeuge -> ExeFS Patchprojekt / IPS32
Ctrl+Shift+P
```

The editor can:

- load any NSO0 `main` file,
- create any number of patch entries,
- edit NSO-VA, expected bytes, replacement bytes and descriptions,
- bind a project to an exact 32-byte Build ID,
- save and load projects as JSON,
- validate every original byte before export,
- export directly into an emulator mod root as `exefs/<Build-ID>.ips`,
- export an Atmosphère directory structure,
- generate `manifest.json` and `README.md` alongside the patch.

The loaded `main` is never modified.

## JSON schema

```json
{
  "schema_version": 1,
  "name": "Example patch",
  "patch_group": "Example_Group",
  "expected_build_id": "64_HEX_CHARACTERS_OR_EMPTY",
  "notes": "Optional project notes",
  "entries": [
    {
      "memory_offset": "0x1234",
      "expected": "11 22 33 44",
      "replacement": "AA BB CC DD",
      "description": "Optional explanation"
    }
  ]
}
```

Rules:

- `memory_offset` is an NSO-VA/module-relative address, not a raw offset in the compressed NSO file.
- `expected` is mandatory and checked against the decompressed segment.
- `replacement` must currently have exactly the same length as `expected`.
- entries may not overlap.
- an optional `expected_build_id` must contain exactly 64 hexadecimal characters.
- export is blocked when the Build ID or any original byte does not match.

## DKCTF Hard Mode project

The current DKCTF test is data only:

```text
PAKPY/exefs_profiles/dkctf_hardmode_p2_test1.json
```

It is not imported by Python and is not listed by a hardcoded profile registry. Load it through `JSON laden` like any other project.

Its current purpose remains isolated:

```text
NSO-VA 0x1E7018
29 15 1E 12 -> 29 19 1F 12
```

This project only preserves an already active P2 bit during Hard Mode initialization. It does not yet preserve the previously selected P2 character.

## Export layouts

### Emulator mod root

Select the mod directory that already contains `romfs`:

```text
My DKCTF Mod/
├─ romfs/
└─ exefs/
   ├─ <Build-ID>.ips
   ├─ manifest.json
   └─ README.md
```

### Atmosphère

```text
atmosphere/
└─ exefs_patches/
   └─ <patch_group>/
      ├─ <Build-ID>.ips
      ├─ manifest.json
      └─ README.md
```

## Separation rule

Future discoveries must follow this split:

```text
universal behavior -> Python modules
specific game/build patch -> external JSON project
analysis evidence -> Markdown findings document
```

No future game-specific patch address is to be added to `exefs_patch.py` or `exefs_patch_gui_patch.py`.
