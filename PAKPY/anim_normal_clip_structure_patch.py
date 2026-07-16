def _skeleton_names(skel):
    source=skel.get('names') or skel.get('nodes') or []
    out=[]
    for index,item in enumerate(source):
        if isinstance(item,dict):
            out.append(str(item.get('name','') or f'name_{index}'))
        else:
            out.append(str(item or f'name_{index}'))
    return out


def _prefix_bytes(probe):
    body=probe.get('body') or {}
    value=body.get('prefix_hex','') if isinstance(body,dict) else ''
    if not value:
        value=probe.get('body_used_hex_prefix_160','') or ''
    try:
        return bytes.fromhex(value)
    except Exception:
        return b''


def _mask_candidate(mask,names,lsb_first):
    indices=[]
    padding=[]
    total_bits=len(mask)*8
    for index in range(total_bits):
        bit=(1<<(index&7)) if lsb_first else (0x80>>(index&7))
        if not mask[index>>3]&bit:
            continue
        if index<len(names):
            indices.append(index)
        else:
            padding.append(index)
    return {
        'set_count':len(indices),
        'set_name_indices':indices,
        'set_names':[names[index] for index in indices],
        'padding_set_bits':padding,
    }


def _normal_clip_layout(probe,skel):
    names=_skeleton_names(skel)
    name_count=len(names)
    mask_byte_count=(name_count+7)//8 if name_count else 0
    total=mask_byte_count*4
    prefix=_prefix_bytes(probe)
    body_size=int(probe.get('body_used_size') or probe.get('body_size') or 0)
    if not mask_byte_count:
        return {'version':1,'status':'pending:missing_skeleton_names','name_count':0}
    if len(prefix)<total:
        return {
            'version':1,
            'status':'pending:short_body_prefix',
            'name_count':name_count,
            'mask_byte_count':mask_byte_count,
            'required_prefix_bytes':total,
            'available_prefix_bytes':len(prefix),
        }
    masks=[prefix[index*mask_byte_count:(index+1)*mask_byte_count] for index in range(4)]
    return {
        'version':1,
        'status':'ok:four_channel_masks',
        'semantics_status':'pending:mask_roles_and_bit_order',
        'name_count':name_count,
        'names':names,
        'mask_count':4,
        'mask_byte_count':mask_byte_count,
        'mask_total_bytes':total,
        'mask_hex':[mask.hex() for mask in masks],
        'bit_order_candidates':{
            'msb_first':[_mask_candidate(mask,names,False) for mask in masks],
            'lsb_first':[_mask_candidate(mask,names,True) for mask in masks],
        },
        'compressed_payload_offset':total,
        'compressed_payload_size':max(0,body_size-total),
        'compressed_payload_prefix_hex':prefix[total:total+64].hex(),
    }


def install_into():
    m=__import__('anim_track_skel_map_patch')
    if getattr(m,'_normal_clip_structure_installed',False):
        return
    old_apply=m._apply_mapping
    def apply_mapping(probe,skel,skel_file):
        is_normal=probe.get('raw_family')=='normal_clip'
        layout=_normal_clip_layout(probe,skel) if is_normal else None
        if layout is not None:
            probe['normal_clip_layout']=layout
            track_decode=probe.get('track_decode') or {}
            track_decode['normal_clip_layout']=layout
            probe['track_decode']=track_decode
        result=old_apply(probe,skel,skel_file)
        if layout is not None:
            mapping=result.get('track_skeleton_map') or {}
            mapping['normal_clip_layout']=layout
            if layout.get('status','').startswith('ok') and mapping.get('status')!='ok':
                mapping['status']='pending:normal_clip_quantized_stream'
                mapping['note']='four_channel_masks_parsed; mask_roles_and_quantized_stream_pending'
            result['track_skeleton_map']=mapping
        return result
    m._apply_mapping=apply_mapping
    m._normal_clip_structure_installed=True
