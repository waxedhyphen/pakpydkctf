from pathlib import Path
import csv
import html
import json
import math
import os
import re
import struct
from pak_core import PakError, get_entry_asset, safe_name, sha1_bytes
from rigged_gltf import load_model_with_skin
from skeletal_codec import resolve_ref, format_uuid

ZERO_UUID = '00000000000000000000000000000000'

def be16(data, off):
    return int.from_bytes(data[off:off+2], 'big')

def be32(data, off):
    return int.from_bytes(data[off:off+4], 'big')

def tag4(data, off):
    return data[off:off+4].decode('ascii', 'replace')

def _finite(value):
    return math.isfinite(float(value)) and abs(float(value)) < 1000000.0

def _f(value):
    value = float(value)
    if not math.isfinite(value) or abs(value) < 0.00000001:
        value = 0.0
    return f'{value:.9g}'

def _sid(text, fallback='node'):
    text = re.sub(r'[^A-Za-z0-9_\-]+', '_', str(text or fallback)).strip('_')
    if not text:
        text = fallback
    if text[0].isdigit():
        text = '_' + text
    return text

def _xml(text):
    return html.escape(str(text or ''), quote=True)

def _indent(lines, level, text):
    lines.append('  ' * level + text)

def _read_name(asset, p):
    size = be32(asset, p)
    p += 4
    if size <= 0 or size > 4096 or p + size > len(asset):
        raise PakError(f'Ungültige SKEL-Namenslänge bei 0x{p - 4:X}')
    name = asset[p:p+size].split(b'\x00', 1)[0].decode('utf-8', 'replace')
    return name, size, p + size

def parse_skel_layout(asset):
    if len(asset) < 48 or asset[:4] != b'RFRM' or tag4(asset, 20) != 'SKEL':
        raise PakError('Keine SKEL-Ressource')
    p = 32
    marker = be32(asset, p)
    unknown_a = be32(asset, p + 4)
    name_count = be32(asset, p + 8)
    if name_count <= 0 or name_count > 4096:
        raise PakError(f'Ungültiger SKEL name_count: {name_count}')
    p += 12
    names = []
    for index in range(name_count):
        name, size, p = _read_name(asset, p)
        names.append({'index': index, 'name': name, 'size': size})
    fields_offset = p
    fields = {}
    if p + 16 <= len(asset):
        fields = {'zero_or_flags': be32(asset, p), 'name_count_repeat': be16(asset, p + 4), 'node_count': be16(asset, p + 6), 'skin_bone_count': be16(asset, p + 8), 'group_count_a': be16(asset, p + 10), 'group_count_b': be16(asset, p + 12), 'flags': be16(asset, p + 14)}
    data_start = p + 16
    return {'type': 'SKEL', 'size': len(asset), 'sha1': sha1_bytes(asset), 'version_a': be32(asset, 24), 'version_b': be32(asset, 28), 'marker': f'0x{marker:08X}', 'unknown_a': unknown_a, 'name_count': name_count, 'names': names, 'fields_offset': fields_offset, 'fields': fields, 'data_start': data_start, 'data_start_hex': f'0x{data_start:X}', 'data_head_hex': asset[data_start:data_start+512].hex()}

def collect_model_skin_usage(parsed, model_entry):
    asset = get_entry_asset(parsed, model_entry)
    model = load_model_with_skin(asset)
    unique_joints = set()
    weighted_vertices = 0
    vertex_count = 0
    max_joint = -1
    for vertex_set in model.get('vertex_sets', {}).values():
        joints = vertex_set.get('joints', [])
        weights = vertex_set.get('weights', [])
        vertex_count += len(vertex_set.get('positions', []))
        for joint_list, weight_list in zip(joints, weights):
            has_weight = False
            for joint, weight in zip(joint_list, weight_list):
                if float(weight) > 0.000001:
                    unique_joints.add(int(joint))
                    max_joint = max(max_joint, int(joint))
                    has_weight = True
            if has_weight:
                weighted_vertices += 1
    return {'entry_uuid_hex': model_entry.get('uuid_hex', ''), 'entry_name': model_entry.get('display_name') or model_entry.get('name') or model_entry.get('uuid_hex', ''), 'entry_type': model_entry.get('type', ''), 'model_bone_count': int(model.get('bone_count') or 0), 'vertex_count': vertex_count, 'weighted_vertices': weighted_vertices, 'unique_joint_count': len(unique_joints), 'max_joint_index': max_joint, 'unique_joints': sorted(unique_joints)}

def _table_score_parent(values, node_count):
    if not values or node_count <= 0:
        return 0, []
    score = 0
    reasons = []
    valid = sum(1 for v in values if v == 255 or v < node_count)
    roots = sum(1 for v in values if v == 255)
    if valid == len(values):
        score += 35
        reasons.append('parent_indices_valid')
    elif valid >= int(len(values) * 0.85):
        score += 20
        reasons.append('parent_indices_mostly_valid')
    if 1 <= roots <= max(4, node_count // 8):
        score += 20
        reasons.append('root_count_plausible')
    if all(v == 255 or v != i for i, v in enumerate(values)):
        score += 10
        reasons.append('no_self_parent')
    return score, reasons

def _table_score_skin(values, name_count, skin_bone_count):
    if not values or skin_bone_count <= 0:
        return 0, []
    score = 0
    reasons = []
    if len(values) == skin_bone_count:
        score += 20
        reasons.append('skin_count_matches')
    if all(v < name_count for v in values):
        score += 35
        reasons.append('skin_name_indices_valid')
    if len(set(values)) == len(values):
        score += 15
        reasons.append('skin_indices_unique')
    return score, reasons

def probe_tables(asset, layout):
    fields = layout.get('fields') or {}
    node_count = int(fields.get('node_count') or 0)
    skin_bone_count = int(fields.get('skin_bone_count') or 0)
    name_count = int(layout.get('name_count') or 0)
    data_start = int(layout.get('data_start') or 0)
    out = []
    end = min(len(asset), data_start + 96)
    for off in range(data_start, end):
        parent_values = list(asset[off:off+node_count]) if node_count > 0 and off + node_count <= len(asset) else []
        parent_score, parent_reasons = _table_score_parent(parent_values, node_count)
        skin_off = off + node_count
        skin_values = list(asset[skin_off:skin_off+skin_bone_count]) if skin_bone_count > 0 and skin_off + skin_bone_count <= len(asset) else []
        skin_score, skin_reasons = _table_score_skin(skin_values, name_count, skin_bone_count)
        score = parent_score + skin_score
        if score > 0:
            out.append({'offset': off, 'offset_hex': f'0x{off:X}', 'parent_size': len(parent_values), 'skin_offset': skin_off, 'skin_offset_hex': f'0x{skin_off:X}', 'skin_size': len(skin_values), 'score': score, 'reasons': parent_reasons + skin_reasons, 'parent_values': parent_values, 'skin_values': skin_values})
    out.sort(key=lambda item: item['score'], reverse=True)
    return out[:24]

def _unpack_values(asset, off, count, endian):
    fmt = ('>' if endian == 'be' else '<') + 'f' * count
    return list(struct.unpack_from(fmt, asset, off))

def _translation_from_matrix(values):
    row = [values[3], values[7], values[11]]
    col = [values[12], values[13], values[14]]
    row_mag = sum(abs(x) for x in row)
    col_mag = sum(abs(x) for x in col)
    if row_mag <= col_mag or col_mag > 10000.0:
        return row, 'row_major_3_7_11'
    return col, 'column_major_12_13_14'

def _score_matrix(values, stride_name):
    if not all(_finite(v) for v in values):
        return 0, [], [0.0, 0.0, 0.0], 'invalid'
    score = 0
    reasons = []
    if stride_name == 'f32_4x4':
        t, mode = _translation_from_matrix(values)
        rot = [values[i] for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
        bottom = [values[12], values[13], values[14], values[15]]
        if abs(values[15] - 1.0) < 0.01 or all(abs(bottom[i] - [0.0, 0.0, 0.0, 1.0][i]) < 0.01 for i in range(4)):
            score += 18
            reasons.append('matrix_bottom_plausible')
    else:
        t = [values[3], values[7], values[11]]
        mode = '3x4_row_major'
        rot = [values[i] for i in (0, 1, 2, 4, 5, 6, 8, 9, 10)]
    near_axis = sum(1 for v in rot if abs(v) < 0.001 or abs(abs(v) - 1.0) < 0.05)
    if near_axis >= 4:
        score += 15
        reasons.append('rotation_values_plausible')
    mag = sum(abs(v) for v in t)
    if mag < 1000.0:
        score += 20
        reasons.append('translation_range_plausible')
    if mag > 0.000001:
        score += 5
        reasons.append('translation_not_all_zero')
    return score, reasons, t, mode

def _score_quat_trs(values):
    if not all(_finite(v) for v in values):
        return 0, [], [0.0, 0.0, 0.0], 'invalid'
    pos = values[:3]
    quat = values[3:7]
    scale = values[7:10]
    score = 0
    reasons = []
    qlen = math.sqrt(sum(v * v for v in quat))
    if 0.75 <= qlen <= 1.25:
        score += 30
        reasons.append('quat_length_plausible')
    if sum(abs(v) for v in pos) < 1000.0:
        score += 20
        reasons.append('translation_range_plausible')
    if all(0.001 <= abs(v) <= 100.0 for v in scale):
        score += 10
        reasons.append('scale_range_plausible')
    return score, reasons, pos, 'trs_quat_scale'

def _candidate_transforms(asset, off, count, fmt, endian):
    if count <= 0:
        return None
    if fmt == 'f32_4x4':
        floats = 16
        stride = 64
    elif fmt == 'f32_3x4':
        floats = 12
        stride = 48
    elif fmt == 'f32_trs_quat_scale':
        floats = 10
        stride = 40
    else:
        return None
    if off + stride * count > len(asset):
        return None
    scores = []
    translations = []
    modes = []
    for index in range(count):
        values = _unpack_values(asset, off + index * stride, floats, endian)
        if fmt == 'f32_trs_quat_scale':
            score, reasons, t, mode = _score_quat_trs(values)
        else:
            score, reasons, t, mode = _score_matrix(values, fmt)
        scores.append(score)
        translations.append(t)
        modes.append(mode)
    if not scores:
        return None
    good = sum(1 for s in scores if s >= 30)
    avg = sum(scores) / len(scores)
    spread = max(sum(abs(x) for x in t) for t in translations) if translations else 0.0
    total = int(avg + good * 2)
    reasons = []
    if good >= int(count * 0.7):
        total += 25
        reasons.append('most_bones_plausible')
    if spread < 1000.0:
        total += 10
        reasons.append('skeleton_bounds_plausible')
    return {'offset': off, 'offset_hex': f'0x{off:X}', 'format': fmt, 'endian': endian, 'stride': stride, 'count': count, 'score': total, 'avg_local_score': round(avg, 3), 'good_local_count': good, 'translation_mode': modes[0] if modes else '', 'bounds_sum_abs': round(spread, 6), 'reasons': reasons, 'translations': translations[:256]}

def probe_transforms(asset, layout, model_usage=None):
    fields = layout.get('fields') or {}
    skin_count = int(fields.get('skin_bone_count') or 0)
    model_count = int((model_usage or {}).get('model_bone_count') or 0)
    counts = []
    for value in (skin_count, model_count, int((model_usage or {}).get('max_joint_index', -1)) + 1):
        if value > 0 and value not in counts:
            counts.append(value)
    if not counts:
        counts = [skin_count or 1]
    data_start = int(layout.get('data_start') or 0)
    start = data_start
    end = min(len(asset), data_start + 4096)
    candidates = []
    for count in counts:
        for off in range(start, end, 4):
            for fmt in ('f32_4x4', 'f32_3x4', 'f32_trs_quat_scale'):
                for endian in ('be', 'le'):
                    item = _candidate_transforms(asset, off, count, fmt, endian)
                    if item is not None and item['score'] >= 45:
                        if model_usage:
                            max_joint = int(model_usage.get('max_joint_index', -1))
                            if max_joint >= 0 and max_joint < count:
                                item['score'] += 25
                                item['reasons'].append('model_joint_indices_fit')
                            if int(model_usage.get('unique_joint_count', 0)) <= count:
                                item['score'] += 10
                                item['reasons'].append('unique_joint_count_fits')
                        candidates.append(item)
    candidates.sort(key=lambda item: item['score'], reverse=True)
    return candidates[:32]

def _parent_map_from_table(table_candidate, skin_values):
    parent_values = table_candidate.get('parent_values') or []
    skin_values = skin_values or table_candidate.get('skin_values') or []
    if not skin_values:
        return {0: -1}
    name_to_skin = {name_index: idx for idx, name_index in enumerate(skin_values)}
    out = {}
    for idx, name_index in enumerate(skin_values):
        parent_raw = parent_values[name_index] if name_index < len(parent_values) else 255
        if parent_raw == 255:
            out[idx] = -1
        else:
            out[idx] = name_to_skin.get(parent_raw, -1)
    return out

def _fallback_bone_names(layout, count, skin_values=None):
    names = layout.get('names') or []
    out = []
    source = skin_values or list(range(count))
    for i in range(count):
        name_index = source[i] if i < len(source) else i
        if 0 <= name_index < len(names):
            out.append(names[name_index]['name'])
        else:
            out.append(f'bone_{i:03d}')
    return out

def write_candidate_armature_dae(path, layout, table_candidate, transform_candidate):
    count = int(transform_candidate.get('count') or 0)
    translations = transform_candidate.get('translations') or []
    skin_values = table_candidate.get('skin_values') if table_candidate else []
    names = _fallback_bone_names(layout, count, skin_values)
    parent_map = _parent_map_from_table(table_candidate or {}, skin_values) if table_candidate else {0: -1}
    children = {i: [] for i in range(count)}
    roots = []
    for i in range(count):
        parent = parent_map.get(i, -1)
        if parent >= 0 and parent < count and parent != i:
            children.setdefault(parent, []).append(i)
        else:
            roots.append(i)
    if not roots and count > 0:
        roots = [0]
    def matrix_for(index):
        t = translations[index] if index < len(translations) else [0.0, 0.0, index * 0.04]
        return [1.0, 0.0, 0.0, t[0], 0.0, 1.0, 0.0, t[1], 0.0, 0.0, 1.0, t[2], 0.0, 0.0, 0.0, 1.0]
    def node(lines, level, index):
        sid = _sid(names[index], f'bone_{index:03d}')
        _indent(lines, level, f'<node id="{sid}" sid="{sid}" name="{_xml(names[index])}" type="JOINT">')
        _indent(lines, level + 1, '<matrix>' + ' '.join(_f(v) for v in matrix_for(index)) + '</matrix>')
        for child in children.get(index, []):
            node(lines, level + 1, child)
        _indent(lines, level, '</node>')
    lines = []
    _indent(lines, 0, '<?xml version="1.0" encoding="utf-8"?>')
    _indent(lines, 0, '<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">')
    _indent(lines, 1, '<asset><contributor><authoring_tool>PAKPY SKEL probe</authoring_tool></contributor><unit name="meter" meter="1"/><up_axis>Y_UP</up_axis></asset>')
    _indent(lines, 1, '<library_visual_scenes>')
    _indent(lines, 2, '<visual_scene id="Scene" name="Scene">')
    for root in roots:
        node(lines, 3, root)
    _indent(lines, 2, '</visual_scene>')
    _indent(lines, 1, '</library_visual_scenes>')
    _indent(lines, 1, '<scene><instance_visual_scene url="#Scene"/></scene>')
    _indent(lines, 0, '</COLLADA>')
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    return str(path)

def write_probe_outputs(out_dir, skeleton_uuid, asset, layout, table_candidates, transform_candidates, model_usage=None):
    out_dir = Path(out_dir) / safe_name(skeleton_uuid)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'layout.json').write_text(json.dumps(layout, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    (out_dir / 'model_skin_usage.json').write_text(json.dumps(model_usage or {}, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    (out_dir / 'table_candidates.json').write_text(json.dumps(table_candidates, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    (out_dir / 'transform_candidates.json').write_text(json.dumps(transform_candidates, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    with (out_dir / 'candidate_scores.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['rank', 'score', 'offset_hex', 'format', 'endian', 'count', 'stride', 'avg_local_score', 'good_local_count', 'translation_mode', 'reasons'])
        for rank, item in enumerate(transform_candidates):
            writer.writerow([rank, item.get('score'), item.get('offset_hex'), item.get('format'), item.get('endian'), item.get('count'), item.get('stride'), item.get('avg_local_score'), item.get('good_local_count'), item.get('translation_mode'), ';'.join(item.get('reasons', []))])
    dae_files = []
    best_table = table_candidates[0] if table_candidates else {}
    for rank, candidate in enumerate(transform_candidates[:6]):
        dae_path = out_dir / f'candidate_{rank:02d}_armature.dae'
        write_candidate_armature_dae(dae_path, layout, best_table, candidate)
        small = dict(candidate)
        small['translations'] = candidate.get('translations', [])[:32]
        (out_dir / f'candidate_{rank:02d}.json').write_text(json.dumps(small, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
        dae_files.append(str(dae_path))
    summary = {'skeleton_uuid_hex': skeleton_uuid, 'skeleton_uuid': format_uuid(skeleton_uuid), 'layout_json': str(out_dir / 'layout.json'), 'table_candidates_json': str(out_dir / 'table_candidates.json'), 'transform_candidates_json': str(out_dir / 'transform_candidates.json'), 'candidate_scores_csv': str(out_dir / 'candidate_scores.csv'), 'candidate_armatures': dae_files, 'best_transform': transform_candidates[0] if transform_candidates else {}, 'best_table': table_candidates[0] if table_candidates else {}}
    (out_dir / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    return summary

def run_skel_probe_for_model(parsed, model_entry, skeleton_refs, out_dir, require_store=None):
    model_usage = collect_model_skin_usage(parsed, model_entry)
    summaries = []
    for ref in skeleton_refs or []:
        uuid_hex = ref.get('uuid_hex', '')
        if not uuid_hex or uuid_hex == ZERO_UUID:
            continue
        asset, entry, source, source_path = resolve_ref(parsed, uuid_hex, require_store)
        if asset is None or entry is None or entry.get('type') != 'SKEL':
            continue
        layout = parse_skel_layout(asset)
        layout['entry_uuid_hex'] = uuid_hex
        layout['entry_name'] = entry.get('display_name') or entry.get('name') or uuid_hex
        layout['source_kind'] = source
        layout['source_path'] = source_path
        table_candidates = probe_tables(asset, layout)
        transform_candidates = probe_transforms(asset, layout, model_usage=model_usage)
        summary = write_probe_outputs(out_dir, uuid_hex, asset, layout, table_candidates, transform_candidates, model_usage=model_usage)
        summaries.append(summary)
    return {'model_usage': model_usage, 'skeleton_count': len(summaries), 'skeletons': summaries}
