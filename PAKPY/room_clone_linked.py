from collections import defaultdict
from pak_core import PakError
from room_scene_codec import parse_room_asset
from room_clone_codec import clean_hex, collect_clone_plans, collect_bundle, clone_uuid_map, clone_component_block, insert_clone_blocks


def parent_roots(by_uuid, component_uuid):
    roots = []
    seen = set()
    stack = [clean_hex(component_uuid)]
    while stack:
        current = clean_hex(stack.pop(0))
        if current in seen:
            continue
        seen.add(current)
        component = by_uuid.get(current)
        if component is None:
            continue
        parents = component.get('parents') or []
        if not parents:
            roots.append(current)
            continue
        for parent in parents:
            parent_uuid = clean_hex(parent.get('uuid_hex'))
            if parent_uuid:
                stack.append(parent_uuid)
    return roots


def inbound_dependency_bundle(by_uuid, source_uuids, bundle):
    targets = [clean_hex(item) for item in source_uuids if clean_hex(item)]
    source_layers = set()
    for item in targets:
        component = by_uuid.get(item)
        if component is not None:
            source_layers.add(component.get('layer_index'))
    bundle_set = set(bundle)
    extra = []
    for component in by_uuid.values():
        component_uuid = clean_hex(component.get('uuid_hex'))
        if component_uuid in bundle_set:
            continue
        if source_layers and component.get('layer_index') not in source_layers:
            continue
        body_hex = (component.get('body_hex') or '').lower()
        if not any(target in body_hex for target in targets):
            continue
        for root in parent_roots(by_uuid, component_uuid) or [component_uuid]:
            for item in collect_bundle(by_uuid, root):
                if item not in bundle_set:
                    bundle_set.add(item)
                    extra.append(item)
    return extra


def ordered_bundle(by_uuid, bundle):
    return sorted(bundle, key=lambda item: by_uuid[item]['off'])


def apply_room_clones(parsed, folder, manifest, room_asset):
    plans, changed, unsupported = collect_clone_plans(folder, manifest)
    if not plans:
        return None, 0, [], unsupported
    asset = bytes(room_asset)
    info = parse_room_asset(asset)
    by_uuid = {item['uuid_hex']: item for item in info['components']}
    groups = defaultdict(list)
    for plan in plans:
        groups[plan['clone_id']].append(plan)
    blocks_by_layer = defaultdict(list)
    clone_count = 0
    for clone_id, group_plans in groups.items():
        source_uuids = []
        source_transforms = {}
        for plan in group_plans:
            actor_uuid = clean_hex(plan['source_actor_uuid'])
            if actor_uuid not in by_uuid:
                unsupported.append(f'CLONE Source-Actor fehlt in ROOM: {plan["path"]}')
                continue
            source_uuids.append(actor_uuid)
            source_transforms[actor_uuid] = plan['transform']
        bundle = []
        for actor_uuid in source_uuids:
            for component_uuid in collect_bundle(by_uuid, actor_uuid):
                if component_uuid not in bundle:
                    bundle.append(component_uuid)
        for component_uuid in inbound_dependency_bundle(by_uuid, source_uuids, bundle):
            if component_uuid not in bundle:
                bundle.append(component_uuid)
        if not bundle:
            continue
        bundle = ordered_bundle(by_uuid, bundle)
        uuid_map = clone_uuid_map(bundle)
        for component_uuid in bundle:
            component = by_uuid[component_uuid]
            transform = source_transforms.get(component_uuid)
            block = clone_component_block(asset, component, uuid_map, transform)
            blocks_by_layer[component['layer_index']].append(block)
        clone_count += len(source_uuids)
    if not blocks_by_layer:
        return None, 0, changed, unsupported
    cloned = insert_clone_blocks(asset, info, blocks_by_layer)
    parsed_again = parse_room_asset(cloned)
    if len(parsed_again['components']) <= len(info['components']):
        raise PakError('ROOM-Clone hat keine neuen Komponenten erzeugt')
    return cloned, clone_count, changed, unsupported
