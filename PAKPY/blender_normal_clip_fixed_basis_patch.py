"""Upgrade the generated Blender normal_clip importer to the exact glTF basis.

The old importer estimated a similarity transform from Blender bone heads. That
fit is invalid because Blender's glTF importer prettifies edit-bone directions,
and the earlier connected-rig path also moved heads. The fitted scale/translation
therefore distorted large animation deltas while rest-like frames still looked
reasonable.
"""
from __future__ import annotations

import blender_normal_clip_action_script_patch as base_patch


README = '''Blender normal_clip Actions

Datei: blender_import_normal_clip_actions.py

Voraussetzungen:
- Character-/Model-Paket wurde mit dem aktuellen PAKPY exportiert.
- debug/anim_normal_clip_bind/*.normal_clip_bind.json ist vorhanden.
- Die automatisch erzeugte experimental_skeletal.blend ist geöffnet.

Blender Scripting:
1. blender_import_normal_clip_actions.py öffnen.
2. Script ausführen.
3. Die erzeugten Actions im Dope Sheet / Action Editor auswählen.

Kommandozeile:
blender character.blend --python blender_import_normal_clip_actions.py -- --package PFAD --filter a_pompy_idle_ws --fps 30 --save character_animated.blend

Der Importer verwendet exakt dieselbe Koordinatenumrechnung wie Blenders glTF-Importer: X,Y,Z -> X,-Z,Y. Er schätzt keinen Maßstab aus Bone-Heads. Für jeden Bone wird die globale Spiel-Animation als Delta relativ zur Spiel-Restpose auf die Blender-Restmatrix angewandt. Dadurch bleiben Root-Motion und große Translationen zusammenhängend.

Auch Rigs mit nur einem oder zwei passenden Bones werden unterstützt; die frühere Mindestgrenze von drei Bones entfällt.

Wichtig: Die Action stellt den isolierten normal_clip dar. Ein Live-Spiel-Capture kann zusätzliche Posegraph-, Blend-, Look-at-, Physik-, Actor- oder Procedural-Layer enthalten.
'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"normal_clip fixed-basis patch expected one {label}, found {source.count(old)}")
    return source.replace(old, new, 1)


def upgrade_script(source: str) -> str:
    result = str(source)
    result = _replace_once(
        result,
        "The importer calibrates game-space to the imported armature from matching rest\n"
        "joint positions. Bone roll is handled by a per-bone rest correction, so no fixed\n"
        "axis-swizzle or hand-authored roll table is required.",
        "The importer uses Blender glTF's exact Y-up to Z-up conversion and applies each\n"
        "game-space global animation delta to the matching Blender rest bone. Bone roll\n"
        "and Blender's bone-prettification are preserved by the per-bone rest matrix.",
        "module description",
    )
    result = _replace_once(result, "import json\nimport sys", "import json\nimport math\nimport sys", "math import")
    result = _replace_once(result, "\nimport numpy as np", "", "numpy import")

    start = result.index("def estimate_similarity(")
    end = result.index("\n\ndef action_name(", start)
    result = result[:start] + '''def gltf_to_blender_conversion():
    """Match Blender's official glTF import conversion: X,Y,Z -> X,-Z,Y."""
    scale_length = float(getattr(bpy.context.scene.unit_settings, "scale_length", 1.0) or 1.0)
    if not math.isfinite(scale_length) or scale_length <= 0.0:
        scale_length = 1.0
    units_per_meter = 1.0 / scale_length
    conversion = Matrix((
        (units_per_meter, 0.0, 0.0, 0.0),
        (0.0, 0.0, -units_per_meter, 0.0),
        (0.0, units_per_meter, 0.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return conversion, units_per_meter


def fixed_basis_residual_stats(entries, conversion):
    """Diagnostic only; Blender may prettify bone heads without changing skinning."""
    residuals = []
    for _palette, _node_index, _name, _pose_bone, game_rest, blender_rest in entries:
        delta = (conversion @ game_rest).translation - blender_rest.translation
        residuals.append(float(delta.length))
    if not residuals:
        return 0.0, 0.0
    residuals.sort()
    middle = len(residuals) // 2
    median = residuals[middle] if len(residuals) % 2 else 0.5 * (residuals[middle - 1] + residuals[middle])
    return float(median), float(residuals[-1])
''' + result[end:]

    result = _replace_once(result, "    source_points = []\n    target_points = []\n", "", "point arrays")
    result = _replace_once(
        result,
        '''        entries.append((palette_index, node_index, name, pose_bone, game_rest, blender_rest))
        source_points.append(tuple(game_rest.translation))
        target_points.append(tuple(blender_rest.translation))
    if len(entries) < 3:
        raise RuntimeError("Zu wenige passende Armature-Bones für " + str(path))

    conversion, scale, residual_median, residual_max = estimate_similarity(source_points, target_points)
    corrections = {}
    for _palette, node_index, _name, pose_bone, game_rest, blender_rest in entries:
        corrections[pose_bone.name] = (conversion @ game_rest).inverted_safe() @ blender_rest
''',
        '''        entries.append((palette_index, node_index, name, pose_bone, game_rest, blender_rest))
    if not entries:
        raise RuntimeError("Keine passenden Armature-Bones für " + str(path))

    conversion, scale = gltf_to_blender_conversion()
    conversion_inverse = conversion.inverted_safe()
    residual_median, residual_max = fixed_basis_residual_stats(entries, conversion)
    game_rest_inverse = {
        pose_bone.name: game_rest.inverted_safe()
        for _palette, _node_index, _name, pose_bone, game_rest, _blender_rest in entries
    }
    blender_rest_by_bone = {
        pose_bone.name: blender_rest.copy()
        for _palette, _node_index, _name, pose_bone, _game_rest, blender_rest in entries
    }
''',
        "basis setup",
    )
    result = _replace_once(
        result,
        '''    armature["pak_normal_clip_rest_calibrated"] = True
    armature["pak_normal_clip_basis_scale"] = scale
''',
        '''    armature["pak_normal_clip_rest_calibrated"] = True
    armature["pak_normal_clip_basis_mode"] = "gltf_yup_to_blender"
    armature["pak_normal_clip_basis_scale"] = scale
''',
        "armature basis metadata",
    )
    result = _replace_once(
        result,
        '''            target = conversion @ matrix4(absolute[node_index]) @ corrections[pose_bone.name]
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix = target
''',
        '''            game_current = matrix4(absolute[node_index])
            game_delta = game_current @ game_rest_inverse[pose_bone.name]
            target = conversion @ game_delta @ conversion_inverse @ blender_rest_by_bone[pose_bone.name]
            pose_bone.rotation_mode = "QUATERNION"
            pose_bone.matrix = target
''',
        "frame target formula",
    )
    result = _replace_once(
        result,
        '''        "basis_scale": scale,
        "rest_position_residual_median": residual_median,
        "rest_position_residual_max": residual_max,
''',
        '''        "basis_mode": "gltf_yup_to_blender",
        "basis_scale": scale,
        "rest_position_residual_median_diagnostic": residual_median,
        "rest_position_residual_max_diagnostic": residual_max,
''',
        "action report basis fields",
    )
    compile(result, "blender_import_normal_clip_actions.py", "exec")
    return result


def install() -> None:
    if getattr(base_patch, "_fixed_gltf_basis_installed", False):
        return
    base_patch.NORMAL_CLIP_ACTION_SCRIPT = upgrade_script(base_patch.NORMAL_CLIP_ACTION_SCRIPT)
    base_patch.NORMAL_CLIP_ACTION_README = README
    base_patch._fixed_gltf_basis_installed = True
