#!/usr/bin/env python3
"""Exact sparse value decoder for DKCTF ANIM normal_clip.

Ports rotation @0x198B64, extended vectors @0x198D48, and the compact vector
path in ProcessFrame. Output values are node-indexed sparse keys; bind-pose and
Blender composition are intentionally left to the next layer.
"""
from __future__ import annotations
import math
from dataclasses import asdict, dataclass
from typing import Any

from anim_normal_clip_frames import parse_frame_schedule_from_setup
from anim_normal_clip_setup import parse_normal_clip_setup

class NormalClipValueError(ValueError): pass

def _u32(v): return v & 0xffffffff
def _rev32(v): return int.from_bytes(_u32(v).to_bytes(4,'little'),'big')
def _bfi(dst,src,lsb,width):
    mask=((1<<width)-1)<<lsb
    return _u32((dst&~mask)|((src&((1<<width)-1))<<lsb))
def _bfxil(dst,src,lsb,width):
    mask=(1<<width)-1
    return _u32((dst&~mask)|((src>>lsb)&mask))
def _need(raw,off,size,label):
    if off<0 or off+size>len(raw):
        raise NormalClipValueError(f'{label} outside file at 0x{off:X}')
    return raw[off:off+size]

@dataclass
class NormalClipValueResult:
    type:str
    frame_count:int
    rotation_tracks:list[dict[str,Any]]
    translation_tracks:list[dict[str,Any]]
    scale_tracks:list[dict[str,Any]]
    constant_rotations:list[dict[str,Any]]
    constant_translations:list[dict[str,Any]]
    decoded_record_count:int
    rotation_record_count:int
    compact_vector_record_count:int
    extended_vector_record_count:int
    special_rotation_count:int
    extended_rotation_count:int
    notes:list[str]
    def to_dict(self,node_names=None):
        out=asdict(self)
        if node_names is not None:
            for key in ('rotation_tracks','translation_tracks','scale_tracks','constant_rotations','constant_translations'):
                for item in out[key]:
                    i=item['node_index']
                    item['node_name']=node_names[i] if 0<=i<len(node_names) else f'<node_{i}>'
        return out

def decode_rotation_payload(raw,off,base,scale):
    """12-byte lookahead, 8/12-byte caller advance."""
    b=_need(raw,off,12,'rotation record/lookahead')
    h0,h1,h2,h3=(int.from_bytes(b[i:i+2],'big') for i in (0,2,4,6))
    extended=bool(h0&0x8000); special=bool(h0&0x4000)
    sign=-1.0 if h0&1 else 1.0
    code=(((h0>>2)&0xfff)<<7)|(b[8]&0x7f)
    sign_bit=(h0>>1)&1
    if special and not extended:
        if {h1,h2,h3}!={1,2,3}:
            raise NormalClipValueError(f'bad special quaternion slots at 0x{off:X}')
        q=[0.0]*4; q[h1]=sign
        return {'quaternion_wxyz':tuple(q),'quantized_xyz':None,'extended':False,
                'special':True,'normalized_vector_path':False,
                'interpolation_code':code,'interpolation_sign_bit':sign_bit}
    qi=((h1<<8)|b[9],(h2<<8)|b[10],(h3<<8)|b[11])
    x,y,z=(base+scale*v for v in qi); length2=x*x+y*y+z*z
    normalized=special or length2>=1.0
    if normalized:
        if length2>0:
            inv=1.0/math.sqrt(length2); x*=inv; y*=inv; z*=inv
        w=0.0
    else:
        w=sign*math.sqrt(max(0.0,1.0-length2))
    return {'quaternion_wxyz':(w,x,y,z),'quantized_xyz':qi,'extended':extended,
            'special':special,'normalized_vector_path':normalized,
            'interpolation_code':code,'interpolation_sign_bit':sign_bit}

def decode_compact_vector_payload(raw,off,base,span):
    """Unsigned 20-bit XYZ, 8-byte lookahead, 4/8-byte advance."""
    b=_need(raw,off,8,'compact vector record/lookahead')
    r0=int.from_bytes(b[:4],'little'); r1=int.from_bytes(b[4:8],'little')
    a=_rev32(r0); c=_rev32(r1)
    qi=(((a>>10)&0xffc00)|((c>>20)&0x3ff),
        ((c>>10)&0x3ff)|_rev32(r0&0x00fc0f00),
        ((a&0x3ff)<<10)|_rev32(r1&0xff030000))
    if any(v>=(1<<20) for v in qi): raise NormalClipValueError('compact value exceeds 20 bits')
    return {'value_xyz':tuple(base[i]+span[i]*qi[i] for i in range(3)),
            'quantized_xyz':qi,'codec':'vector_compact_4_8'}

def decode_extended_vector_payload(raw,off,base,span):
    """Unsigned 30-bit XYZ, 12-byte lookahead, 4/8/12-byte advance."""
    b=_need(raw,off,12,'extended vector record/lookahead')
    r0=int.from_bytes(b[:4],'little'); r1=int.from_bytes(b[4:8],'little'); r2=int.from_bytes(b[8:12],'little')
    a,c,d=_rev32(r0),_rev32(r1),_rev32(r2)
    qx=_bfxil(_bfxil(_rev32(r0&0x0000f03f),c,10,20),d,20,10)
    qy=_bfxil(_bfi(_rev32(r1&0x00fc0f00),a>>10,20,10),d,10,10)
    qz=((a&0x3ff)<<20)|((c&0x3ff)<<10)|_rev32(r2&0xff030000)
    qi=(qx,qy,qz)
    if any(v>=(1<<30) for v in qi): raise NormalClipValueError('extended value exceeds 30 bits')
    return {'value_xyz':tuple(base[i]+span[i]*qi[i] for i in range(3)),
            'quantized_xyz':qi,'codec':'vector_extended_4_8_12'}

def _records(schedule):
    yield from schedule.initial_records
    for block in schedule.blocks: yield from block.records

def parse_normal_clip_values(raw,node_count,*,strict=True):
    setup=parse_normal_clip_setup(raw,node_count,strict=strict)
    schedule=parse_frame_schedule_from_setup(raw,setup,strict=strict)
    rt=[{'channel_index':i,'node_index':r.node_index,'keys':[]} for i,r in enumerate(setup.rotation_ranges)]
    tt=[{'channel_type':'translation','channel_index':i,'node_index':r.node_index,'keys':[]} for i,r in enumerate(setup.translation_ranges)]
    st=[{'channel_type':'scale','channel_index':i,'node_index':r.node_index,'keys':[]} for i,r in enumerate(setup.scale_ranges)]
    counts={'all':0,'rot':0,'compact':0,'extended':0,'special':0,'rot_ext':0}
    for rec in _records(schedule):
        counts['all']+=1; i=rec.channel_index
        if rec.channel_type=='rotation':
            counts['rot']+=1; rr=setup.rotation_ranges[i]
            p=decode_rotation_payload(raw,rec.file_offset,rr.base,rr.scale)
            counts['special']+=int(p['special']); counts['rot_ext']+=int(p['extended'])
            rt[i]['keys'].append({'frame':rec.key_frame,'file_offset':rec.file_offset,
                'record_size':rec.record_size,**p})
            continue
        if rec.channel_type=='translation': rr=setup.translation_ranges[i]; target=tt[i]
        elif rec.channel_type=='scale': rr=setup.scale_ranges[i]; target=st[i]
        else: raise NormalClipValueError(f'unknown channel {rec.channel_type}')
        if rec.codec=='vector_extended_4_8_12':
            counts['extended']+=1; p=decode_extended_vector_payload(raw,rec.file_offset,rr.base_xyz,rr.span_xyz)
        elif rec.codec=='vector_compact_4_8':
            counts['compact']+=1; p=decode_compact_vector_payload(raw,rec.file_offset,rr.base_xyz,rr.span_xyz)
        else: raise NormalClipValueError(f'unknown codec {rec.codec}')
        target['keys'].append({'frame':rec.key_frame,'file_offset':rec.file_offset,
            'record_size':rec.record_size,**p})
    if strict:
        expected=(schedule.rotation_key_frames,schedule.translation_key_frames,schedule.scale_key_frames)
        for tracks,wanted,name in zip((rt,tt,st),expected,('rotation','translation','scale')):
            for i,track in enumerate(tracks):
                frames=[k['frame'] for k in track['keys']]
                if frames!=wanted[i]: raise NormalClipValueError(f'{name}[{i}] key schedule mismatch')
                for key in track['keys']:
                    values=key.get('quaternion_wxyz') or key.get('value_xyz')
                    if not all(math.isfinite(v) for v in values): raise NormalClipValueError(f'{name}[{i}] non-finite value')
                    if name=='rotation':
                        norm=math.sqrt(sum(v*v for v in values))
                        if abs(norm-1.0)>1e-5: raise NormalClipValueError(f'rotation[{i}] norm={norm}')
    constants_r=[{'node_index':x.node_index,'file_offset':x.file_offset,'record_size':x.record_size,
                  'quaternion_wxyz':x.quaternion_wxyz} for x in setup.constant_rotations]
    constants_t=[{'node_index':x.node_index,'file_offset':x.file_offset,'record_size':x.record_size,
                  'value_xyz':x.value_xyz} for x in setup.constant_translations]
    return NormalClipValueResult('ANIM_NORMAL_CLIP_VALUES',schedule.frame_count,rt,tt,st,constants_r,constants_t,
        counts['all'],counts['rot'],counts['compact'],counts['extended'],counts['special'],counts['rot_ext'],[
        'Rotations are WXYZ sparse keys.','Compact vectors are unsigned 20-bit.',
        'Extended vectors are unsigned 30-bit.','Lookahead overlap is intentional.',
        'Pose composition and Blender conversion remain pending.'])
