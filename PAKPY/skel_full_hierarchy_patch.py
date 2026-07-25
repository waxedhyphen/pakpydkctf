import copy
import sys
import skeletal_codec as sc

_ORIGINAL_PARSE = sc.parse_skel_asset


def _node_parent(nodes, node_index):
    if not 0 <= node_index < len(nodes):
        return -1
    try:
        parent = int(nodes[node_index].get('parent_index', 255))
    except Exception:
        return -1
    return parent if 0 <= parent < len(nodes) and parent != node_index else -1


def _required_helper_nodes(nodes, bones):
    deform_nodes = {int(bone.get('node_index', -1)) for bone in bones}
    required = set()
    for node_index in tuple(deform_nodes):
        seen = set()
        parent = _node_parent(nodes, node_index)
        while parent >= 0 and parent not in seen:
            seen.add(parent)
            if parent not in deform_nodes:
                required.add(parent)
            parent = _node_parent(nodes, parent)
    return required


def _tail_for_node(node_index, nodes):
    matrix = nodes[node_index].get('global_matrix') or sc._id()
    head = sc._tr(matrix)
    for child_index, child in enumerate(nodes):
        if _node_parent(nodes, child_index) != node_index:
            continue
        child_matrix = child.get('global_matrix') or sc._id()
        tail = sc._tr(child_matrix)
        if sum(abs(tail[i] - head[i]) for i in range(3)) > 1e-6:
            return tail
    return [head[0], head[1] + 0.035, head[2]]


def _helper_bone(node_index, bone_index, nodes):
    node = nodes[node_index]
    global_matrix = list(node.get('global_matrix') or sc._id())
    local_matrix = list(node.get('matrix') or global_matrix)
    return {
        'index': bone_index,
        'node_index': node_index,
        'name_index': int(node.get('name_index', node_index)),
        'name': str(node.get('name') or f'node_{node_index:03d}'),
        'parent_index': -1,
        'parent_node_index': _node_parent(nodes, node_index),
        'matrix': local_matrix,
        'global_matrix': global_matrix,
        'inverse_bind_matrix': sc._inv(global_matrix),
        'translation': list(node.get('translation') or [0.0, 0.0, 0.0]),
        'rotation': list(node.get('rotation') or [1.0, 0.0, 0.0, 0.0]),
        'scale': list(node.get('scale') or [1.0, 1.0, 1.0]),
        'head': sc._tr(global_matrix),
        'tail': _tail_for_node(node_index, nodes),
        'helper': True,
        'deform': False,
    }


def _restore_full_hierarchy(summary):
    nodes = summary.get('nodes') or []
    source_bones = summary.get('bones') or []
    if not nodes or not source_bones:
        return summary

    bones = [copy.deepcopy(bone) for bone in source_bones]
    node_to_bone = {}
    for index, bone in enumerate(bones):
        bone['index'] = index
        bone['helper'] = bool(bone.get('helper', False))
        bone['deform'] = not bone['helper']
        node_index = int(bone.get('node_index', -1))
        if node_index >= 0:
            node_to_bone[node_index] = index

    helper_nodes = _required_helper_nodes(nodes, bones)
    pending = set(helper_nodes)
    while pending:
        progressed = False
        for node_index in sorted(pending):
            parent_node = _node_parent(nodes, node_index)
            if parent_node in pending and parent_node not in node_to_bone:
                continue
            node_to_bone[node_index] = len(bones)
            bones.append(_helper_bone(node_index, len(bones), nodes))
            pending.remove(node_index)
            progressed = True
            break
        if not progressed:
            node_index = min(pending)
            node_to_bone[node_index] = len(bones)
            bones.append(_helper_bone(node_index, len(bones), nodes))
            pending.remove(node_index)

    for index, bone in enumerate(bones):
        node_index = int(bone.get('node_index', -1))
        parent_node = _node_parent(nodes, node_index)
        parent_index = node_to_bone.get(parent_node, -1)
        bone['index'] = index
        bone['parent_node_index'] = parent_node if parent_node >= 0 else 255
        bone['parent_index'] = parent_index
        if 0 <= node_index < len(nodes):
            global_matrix = list(nodes[node_index].get('global_matrix') or bone.get('global_matrix') or sc._id())
            bone['global_matrix'] = global_matrix
            if parent_index >= 0:
                parent_global = bones[parent_index].get('global_matrix') or sc._id()
                bone['matrix'] = sc._mm(sc._inv(parent_global), global_matrix)
            else:
                bone['matrix'] = global_matrix
            bone['inverse_bind_matrix'] = sc._inv(global_matrix)

    out = dict(summary)
    out['bones'] = bones
    out['helper_node_indices'] = sorted(helper_nodes)
    out['armature_bone_count'] = len(bones)
    out['deform_bone_count'] = sum(1 for bone in bones if bone.get('deform', True))
    out['hierarchy_mode'] = 'full_required_node_hierarchy'
    out['status'] = str(out.get('status') or '') + f' Die Armature behaelt die {out["deform_bone_count"]} Skin-Joint-Indizes und ergaenzt {len(helper_nodes)} ungewichtete SKEL-Zwischenknoten als Helper-Bones.'
    return out


def parse_skel_asset(asset):
    return _restore_full_hierarchy(_ORIGINAL_PARSE(asset))


def install_into():
    sc.parse_skel_asset = parse_skel_asset
    for module in tuple(sys.modules.values()):
        if module is None:
            continue
        if getattr(module, 'parse_skel_asset', None) is _ORIGINAL_PARSE:
            module.parse_skel_asset = parse_skel_asset
