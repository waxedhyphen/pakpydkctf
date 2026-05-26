from collections import defaultdict
import struct
from pak_core import PakError
from room_scene_codec import parse_room_asset
from room_clone_codec import clean_hex, collect_clone_plans, collect_bundle, clone_uuid_map, insert_clone_blocks
from room_clone_linked import inbound_dependency_bundle


def clone_label(clone_id):
    digits = ''.join(ch for ch in clone_id if ch.isdigit())[-4:]
    return digits.rjust(4, '0')


def same_len_name(name, clone_id):
    code = clone_label(clone_id)
    out = name
    if 'Choose' in out:
        out = out.replace('Choose', 'Cl' + code, 1)
    elif 'Rambi' in out:
        out = out.replace('Rambi', 'R' + code, 1)
    elif 'DKBarrel' in out:
        out = out.replace('DKBarrel', 'DKB' + code + 'x', 1)
    elif len(out) >= 5:
        out = out[:-5] + 'C' + code
    return out if len(out) == len(name) else name


def write_same_len_name(block, name):
    name_len = int.from_bytes(block[44:48], 'big')
    start = 48
    end = start + name_len
    old = bytes(block[start:end])
    new = name.encode('utf-8')
    if len(new) == len(old):
        block[start:end] = new


def clone_component_block_named(asset, component, uuid_map, transform, clone_id):
    block = bytearray(asset[component['off']:component['end']])
    for old_uuid, new_uuid in uuid_map.items():
        block = bytearray(bytes(block).replace(bytes.fromhex(old_uuid), bytes.fromhex(new_uuid)))
    write_same_len_name(block, same_len_name(component.get('name') or '', clone_id))
    if transform is not None and component.get('actor_refs') and component['actor_refs'].get('transform'):
        if len(block) < 37:
            raise PakError(f'Clone-Transform kann nicht geschrieben werden: {component.get("name") or component["uuid_hex"]}')
        flag = block[-37]
        block[-37:] = bytes([flag]) + struct.pack('>9f', *(transform['position'] + transform['rotation'] + transform['scale']))
    return bytes(block)


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
            block = clone_component_block_named(asset, component, uuid_map, transform, clone_id)
            blocks_by_layer[component['layer_index']].append(block)
        clone_count += len(source_uuids)
    if not blocks_by_layer:
        return None, 0, changed, unsupported
    cloned = insert_clone_blocks(asset, info, blocks_by_layer)
    parsed_again = parse_room_asset(cloned)
    if len(parsed_again['components']) <= len(info['components']):
        raise PakError('ROOM-Clone hat keine neuen Komponenten erzeugt')
    return cloned, clone_count, changed, unsupported
