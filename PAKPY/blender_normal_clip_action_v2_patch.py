"""Upgrade the generated normal_clip Blender importer without duplicating it.

Installed after ``blender_normal_clip_action_script_patch``. The existing writer
reads its module constants at export time, so this patch replaces the generated
script/readme and then adds the standalone RenderDoc capture fitter.
"""
from __future__ import annotations

from pathlib import Path

import blender_named_timeline_patch as blender_patch
import blender_normal_clip_action_script_patch as base_patch


README = '''Blender normal_clip Actions

Datei: blender_import_normal_clip_actions.py

Voraussetzungen:
- Character-/Model-Paket wurde mit dem aktuellen PAKPY exportiert.
- debug/anim_normal_clip_bind/*.normal_clip_bind.json ist vorhanden.
- Die unveränderte Armature aus dem experimental_skeletal DAE/BLEND ist geöffnet.

30-fps-Wiedergabe:
blender character.blend --python blender_import_normal_clip_actions.py -- --package PFAD --filter a_pompy_idle_ws --scene-fps 30 --clip-fps 30 --save character_animated.blend

Vergleich mit 60-Hz-RenderDoc-Captures:
blender character.blend --python blender_import_normal_clip_actions.py -- --package PFAD --filter a_pompy_idle_ws --scene-fps 60 --clip-fps 30 --save character_animated_60hz.blend

Der Importer verwendet standardmäßig stabile Rumpf-/Bein-Anker für die
Spiel-zu-Blender-Basis. Er bricht ab, wenn diese Restbasis die konfigurierte
Fehlergrenze überschreitet, statt eine sichtbar falsche Action zu erzeugen.
--basis-mode all reproduziert den alten All-Bone-Fit; --basis-mode identity ist
nur für nachweislich identische Koordinatensysteme gedacht.

Loop-Clips werden anhand ihrer Endpunkte erkannt und mit Cycles-F-Curves
versehen. --cycles off deaktiviert dies.

Wichtig: Die Action stellt den isolierten normal_clip dar. Ein Live-Spiel-Capture
kann zusätzliche Posegraph-, Blend-, Look-at-, Physik- oder Procedural-Layer
enthalten.
'''

CAPTURE_README = '''RenderDoc normal_clip Capture-Fit

Datei: anim_capture_fit.py

Beispiel:
python anim_capture_fit.py --captures PFAD_ZU_CSVS --package PFAD_ZUM_CHARACTER_PAKET --json anim_capture_fit.json --csv anim_capture_fit.csv

Das Werkzeug behandelt 1.csv, 2.csv usw. als chronologische Render-Samples. Es
testet alle normal_clip_bind-Exporte, zyklische Offsets und Subframe-Schritte.
motion_rmse dient zur Clip-/Zeit-Erkennung trotz annähernd konstanter
zusätzlicher Live-Pose-Offsets. absolute_rmse bleibt die maßgebliche Größe für
eine echte 1:1-Posevalidierung.
'''


def _replace_once(script: str, old: str, new: str, label: str) -> str:
    if script.count(old) != 1:
        raise RuntimeError(f"Blender importer upgrade marker {label!r} occurs {script.count(old)} times")
    return script.replace(old, new, 1)


def upgrade_script(script: str) -> str:
    script = _replace_once(
        script,
        "DEFAULT_FPS = 30.0\nREPORT_NAME",
        "DEFAULT_CLIP_FPS = 30.0\nDEFAULT_SCENE_FPS = 30.0\n"
        "DEFAULT_MAX_BASIS_RESIDUAL = 0.05\nREPORT_NAME",
        "fps constants",
    )
    script = _replace_once(
        script,
        "def action_name(path):\n",
        '''PREFERRED_BASIS_BONES = (
    "skeletonroot",
    "hipl", "hipr",
    "kneel", "kneer",
    "anklel", "ankler",
    "belly", "spinetop",
    "shoulderl", "shoulderr",
)


def select_basis_entries(entries, mode):
    if mode == "all":
        return list(entries)
    if mode == "identity":
        return []
    preferred = set(PREFERRED_BASIS_BONES)
    anchors = [item for item in entries if norm_name(item[2]) in preferred]
    return anchors if len(anchors) >= 3 else list(entries)


def estimate_basis(entries, mode):
    if mode == "identity":
        return Matrix.Identity(4), 1.0, 0.0, 0.0, 0
    selected = select_basis_entries(entries, mode)
    source = [tuple(item[4].translation) for item in selected]
    target = [tuple(item[5].translation) for item in selected]
    conversion, scale, median, maximum = estimate_similarity(source, target)
    return conversion, scale, median, maximum, len(selected)


def residuals_for_entries(entries, conversion):
    values = [
        float(((conversion @ item[4]).translation - item[5].translation).length)
        for item in entries
    ]
    if not values:
        return 0.0, 0.0
    values.sort()
    middle = len(values) // 2
    median = values[middle] if len(values) % 2 else 0.5 * (values[middle - 1] + values[middle])
    return float(median), float(values[-1])


def document_is_cyclic(document, threshold=0.002):
    frames = document.get("frames") or []
    if len(frames) < 2:
        return False
    first = np.asarray(frames[0].get("render_matrices_3x4") or [], dtype=np.float64)
    last = np.asarray(frames[-1].get("render_matrices_3x4") or [], dtype=np.float64)
    if first.shape != last.shape or not first.size:
        return False
    return float(np.sqrt(np.mean((first - last) ** 2))) <= float(threshold)


def action_name(path):
''',
        "basis helpers",
    )
    script = _replace_once(
        script,
        "def create_action(armature, path, document, fps):",
        "def create_action(armature, path, document, scene_fps, clip_fps, basis_mode, max_basis_residual, cycles):",
        "create_action signature",
    )
    script = _replace_once(
        script,
        '''    entries = []
    source_points = []
    target_points = []
    for palette_index, (name, node_index) in enumerate(zip(names, skin_nodes)):
        pose_bone = match_bone(lookup, name)
        if pose_bone is None or not (0 <= node_index < len(base_rows)):
            continue
        game_rest = matrix4(base_rows[node_index])
        blender_rest = pose_bone.bone.matrix_local.copy()
        entries.append((palette_index, node_index, name, pose_bone, game_rest, blender_rest))
        source_points.append(tuple(game_rest.translation))
        target_points.append(tuple(blender_rest.translation))
    if len(entries) < 3:
        raise RuntimeError("Zu wenige passende Armature-Bones für " + str(path))

    conversion, scale, residual_median, residual_max = estimate_similarity(source_points, target_points)
''',
        '''    entries = []
    for palette_index, (name, node_index) in enumerate(zip(names, skin_nodes)):
        pose_bone = match_bone(lookup, name)
        if pose_bone is None or not (0 <= node_index < len(base_rows)):
            continue
        game_rest = matrix4(base_rows[node_index])
        blender_rest = pose_bone.bone.matrix_local.copy()
        entries.append((palette_index, node_index, name, pose_bone, game_rest, blender_rest))
    if len(entries) < 3:
        raise RuntimeError("Zu wenige passende Armature-Bones für " + str(path))

    conversion, scale, basis_residual_median, basis_residual_max, basis_bone_count = estimate_basis(entries, basis_mode)
    residual_median, residual_max = residuals_for_entries(entries, conversion)
    if basis_residual_max > float(max_basis_residual):
        raise RuntimeError(
            "Rest-Basis passt nicht zur Armature: "
            f"mode={basis_mode}, max={basis_residual_max:.6g}, Grenze={max_basis_residual:.6g}. "
            "Die unveränderte experimental_skeletal-Armature verwenden oder --basis-mode identity/all testen."
        )
''',
        "basis fit",
    )
    script = _replace_once(
        script,
        '''    scene = bpy.context.scene
    scene.render.fps = max(1, int(round(fps)))
    scene.render.fps_base = max(1e-8, float(round(fps)) / float(fps))
''',
        '''    scene = bpy.context.scene
    scene.render.fps = max(1, int(round(scene_fps)))
    scene.render.fps_base = max(1e-8, float(round(scene_fps)) / float(scene_fps))
    frame_scale = float(scene_fps) / float(clip_fps)
''',
        "scene fps",
    )
    script = _replace_once(
        script,
        '''        source_frame = int(frame_record.get("frame", 0))
        blender_frame = source_frame + 1
''',
        '''        source_frame = int(frame_record.get("frame", 0))
        blender_frame = 1.0 + source_frame * frame_scale
''',
        "frame mapping",
    )
    script = _replace_once(
        script,
        '''    action["pak_normal_clip_frame_count"] = len(frames)
    action["pak_normal_clip_fps"] = float(fps)
    scene.frame_start = 1
    scene.frame_end = max(scene.frame_end, len(frames))
''',
        '''    cyclic = document_is_cyclic(document) if cycles == "auto" else cycles == "on"
    if cyclic:
        for curve in curves:
            try:
                if not any(mod.type == "CYCLES" for mod in curve.modifiers):
                    curve.modifiers.new(type="CYCLES")
            except Exception:
                pass
        if hasattr(action, "use_cyclic"):
            action.use_cyclic = True
    action["pak_normal_clip_frame_count"] = len(frames)
    action["pak_normal_clip_clip_fps"] = float(clip_fps)
    action["pak_normal_clip_scene_fps"] = float(scene_fps)
    action["pak_normal_clip_frame_scale"] = frame_scale
    action["pak_normal_clip_cyclic"] = bool(cyclic)
    scene.frame_start = 1
    scene.frame_end = max(scene.frame_end, int(round(1.0 + (len(frames) - 1) * frame_scale)))
''',
        "loop and action metadata",
    )
    script = _replace_once(
        script,
        '''        "basis_scale": scale,
        "rest_position_residual_median": residual_median,
        "rest_position_residual_max": residual_max,
''',
        '''        "basis_mode": basis_mode,
        "basis_bone_count": basis_bone_count,
        "basis_scale": scale,
        "basis_residual_median": basis_residual_median,
        "basis_residual_max": basis_residual_max,
        "rest_position_residual_median_all_bones": residual_median,
        "rest_position_residual_max_all_bones": residual_max,
        "scene_fps": float(scene_fps),
        "clip_fps": float(clip_fps),
        "frame_scale": frame_scale,
        "cyclic": bool(cyclic),
''',
        "result fields",
    )
    script = _replace_once(
        script,
        '''    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--save", default="")
''',
        '''    parser.add_argument("--fps", type=float, default=None, help="Kompatibilitätsalias: setzt Scene- und Clip-FPS gemeinsam")
    parser.add_argument("--scene-fps", type=float, default=DEFAULT_SCENE_FPS)
    parser.add_argument("--clip-fps", type=float, default=DEFAULT_CLIP_FPS)
    parser.add_argument("--basis-mode", choices=("anchors", "all", "identity"), default="anchors")
    parser.add_argument("--max-basis-residual", type=float, default=DEFAULT_MAX_BASIS_RESIDUAL)
    parser.add_argument("--cycles", choices=("auto", "on", "off"), default="auto")
    parser.add_argument("--save", default="")
''',
        "arguments",
    )
    script = _replace_once(
        script,
        '''    root = find_package(args.package)
    armature = find_armature(args.armature)
''',
        '''    root = find_package(args.package)
    armature = find_armature(args.armature)
    scene_fps = float(args.fps if args.fps is not None else args.scene_fps)
    clip_fps = float(args.fps if args.fps is not None else args.clip_fps)
    if scene_fps <= 0.0 or clip_fps <= 0.0:
        raise RuntimeError("Scene- und Clip-FPS müssen positiv sein")
''',
        "resolved fps",
    )
    script = _replace_once(
        script,
        "            result = create_action(armature, path, load_json(path), args.fps)\n",
        '''            result = create_action(
                armature, path, load_json(path),
                scene_fps, clip_fps, args.basis_mode, args.max_basis_residual, args.cycles,
            )
''',
        "create_action call",
    )
    script = _replace_once(
        script,
        '        "fps": args.fps,\n',
        '''        "scene_fps": scene_fps,
        "clip_fps": clip_fps,
        "basis_mode": args.basis_mode,
        "max_basis_residual": args.max_basis_residual,
        "cycles": args.cycles,
''',
        "report settings",
    )
    script = _replace_once(
        script,
        '        "note": "Actions reproduce isolated normal_clip output. Live game captures may include additional posegraph/procedural layers.",\n',
        '        "note": "Actions reproduce isolated normal_clip output. Use --scene-fps 60 --clip-fps 30 for 60-Hz capture comparison. Live game captures may include additional posegraph/procedural layers.",\n',
        "report note",
    )
    compile(script, "blender_import_normal_clip_actions.py", "exec")
    return script


def install(App) -> None:
    base_patch.NORMAL_CLIP_ACTION_SCRIPT = upgrade_script(base_patch.NORMAL_CLIP_ACTION_SCRIPT)
    base_patch.NORMAL_CLIP_ACTION_README = README
    original = blender_patch._write_blender_files

    def write_blender_files(package_dir):
        result = original(package_dir)
        root = Path(package_dir)
        source = Path(__file__).with_name("anim_capture_fit.py")
        target = root / "anim_capture_fit.py"
        readme = root / "ANIM_CAPTURE_FIT.txt"
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
        readme.write_text(CAPTURE_README, encoding="utf-8", newline="\n")
        result["anim_capture_fit_script"] = target.name
        result["anim_capture_fit_readme"] = readme.name
        return result

    blender_patch._write_blender_files = write_blender_files
