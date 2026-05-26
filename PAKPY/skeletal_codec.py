from pathlib import Path
import json,math,struct
from pak_core import PakError,get_entry_asset,safe_name,sha1_bytes,kind_to_ext
ZERO_UUID='00000000000000000000000000000000'
SKELETAL_REF_TYPES={'SKEL','ANIM'}
def be16(d,o): return int.from_bytes(d[o:o+2],'big')
def be32(d,o): return int.from_bytes(d[o:o+4],'big')
def be64(d,o): return int.from_bytes(d[o:o+8],'big')
def tag4(d,o): return d[o:o+4].decode('ascii','replace')
def is_rfrm_type(a,t): return len(a)>=32 and a[:4]==b'RFRM' and tag4(a,20)==t
def format_uuid(h): return h if not h or len(h)!=32 else f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'
def read_name(a,p):
    if p+4>len(a): raise PakError('Name ist abgeschnitten')
    s=be32(a,p);p+=4
    if s<=0 or s>4096 or p+s>len(a): raise PakError('Name hat ungültige Länge')
    return a[p:p+s].split(b'\x00',1)[0].decode('utf-8','replace'),s,p+s
def _sf(v):
    v=float(v)
    return 0.0 if not math.isfinite(v) or abs(v)<1e-8 else v
def _id(): return [1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0]
def _mm(a,b):
    return [sum(a[y*4+k]*b[k*4+x] for k in range(4)) for y in range(4) for x in range(4)]
def _m3i(m):
    a,b,c,d,e,f,g,h,i=m;det=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
    if abs(det)<=1e-8: return [1.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,1.0]
    q=1.0/det
    return [(e*i-f*h)*q,(c*h-b*i)*q,(b*f-c*e)*q,(f*g-d*i)*q,(a*i-c*g)*q,(c*d-a*f)*q,(d*h-e*g)*q,(b*g-a*h)*q,(a*e-b*d)*q]
def _inv(m):
    r=[m[0],m[1],m[2],m[4],m[5],m[6],m[8],m[9],m[10]];i=_m3i(r);t=[m[3],m[7],m[11]]
    it=[-(i[0]*t[0]+i[1]*t[1]+i[2]*t[2]),-(i[3]*t[0]+i[4]*t[1]+i[5]*t[2]),-(i[6]*t[0]+i[7]*t[1]+i[8]*t[2])]
    return [i[0],i[1],i[2],it[0],i[3],i[4],i[5],it[1],i[6],i[7],i[8],it[2],0.0,0.0,0.0,1.0]
def _qmat(t,q,s):
    w,x,y,z=[float(v) for v in q];l=math.sqrt(w*w+x*x+y*y+z*z)
    if l>1e-8: w,x,y,z=w/l,x/l,y/l,z/l
    sx,sy,sz=[float(v) for v in s];tx,ty,tz=[float(v) for v in t]
    xx,yy,zz=x*x,y*y,z*z;xy,xz,yz=x*y,x*z,y*z;wx,wy,wz=w*x,w*y,w*z
    return [(1-2*(yy+zz))*sx,2*(xy-wz)*sy,2*(xz+wy)*sz,tx,2*(xy+wz)*sx,(1-2*(xx+zz))*sy,2*(yz-wx)*sz,ty,2*(xz-wy)*sx,2*(yz+wx)*sy,(1-2*(xx+yy))*sz,tz,0,0,0,1]
def _tr(m): return [_sf(m[3]),_sf(m[7]),_sf(m[11])]
def _read_name_array(a,p):
    if p+8>len(a): raise PakError('Name-Array ist abgeschnitten')
    unknown=be32(a,p);count=be32(a,p+4);p+=8;names=[]
    if count<0 or count>4096: raise PakError('Name-Array-Zähler ist ungültig')
    for i in range(count):
        name,size,p=read_name(a,p);names.append({'index':i,'name':name,'size':size})
    trailing=be32(a,p) if p+4<=len(a) else 0
    p+=4 if p+4<=len(a) else 0
    return {'unknown':unknown,'count':count,'names':names,'trailing_unknown':trailing},p
def _parse_skeleton_map(a,p):
    if p+4>len(a): return {},p
    count_a=be16(a,p);count_b=a[p+2];count_c=a[p+3];start=p;p+=4
    values=list(a[p:p+count_a]);p+=count_a
    u16_values=[]
    for _ in range(count_a*2):
        if p+2>len(a): break
        u16_values.append(be16(a,p));p+=2
    u32_values=[]
    for _ in range(count_b):
        if p+4>len(a): break
        u32_values.append(be32(a,p));p+=4
    tail_u16=[]
    for _ in range(count_c):
        if p+2>len(a): break
        tail_u16.append(be16(a,p));p+=2
    unknown=be32(a,p) if p+4<=len(a) else 0
    p+=4 if p+4<=len(a) else 0
    return {'offset':start,'count_a':count_a,'count_b':count_b,'count_c':count_c,'values':values,'u16_values':u16_values,'u32_values':u32_values,'tail_u16':tail_u16,'unknown':unknown,'size':p-start},p
def _parse_animation_attributes(a,p):
    start=p
    if p>=len(a): return {'present':False,'offset':start,'size':0},p
    present=bool(a[p]);p+=1
    out={'present':present,'offset':start,'size':1}
    if not present:
        return out,p
    has_visibility=bool(a[p]) if p<len(a) else False;p+=1
    out['has_visibility_group_names']=has_visibility
    if has_visibility:
        names,p=_read_name_array(a,p);out['visibility_group_names']=names
    has_info=bool(a[p]) if p<len(a) else False;p+=1
    out['has_info_data']=has_info
    if has_info:
        info_names,p=_read_name_array(a,p)
        count=be32(a,p) if p+4<=len(a) else 0;p+=4 if p+4<=len(a) else 0
        infos=[]
        for _ in range(count):
            if p+12>len(a): break
            flag=be32(a,p);x,y=struct.unpack_from('>ff',a,p+4);p+=12;infos.append({'flag':flag,'x':x,'y':y})
        out['info_names']=info_names;out['info_count']=count;out['infos']=infos
    out['size']=p-start
    return out,p
def _coord_score(a,o,n,endian):
    if n<=0 or o+n*40>len(a): return None
    fmt=('>' if endian=='be' else '<')+'f'*10;score=0;ts=[];qs=[];ss=[]
    for i in range(n):
        try: vals=list(struct.unpack_from(fmt,a,o+i*40))
        except Exception: return None
        if not all(math.isfinite(x) and abs(x)<1000000 for x in vals): return None
        q=vals[:4];s=vals[4:7];t=vals[7:10];ql=math.sqrt(sum(x*x for x in q))
        score+=12 if 0.98<=ql<=1.02 else 4 if 0.75<=ql<=1.25 else -25
        score+=12 if all(abs(abs(x)-1)<=0.02 for x in s) else 3 if all(0.001<=abs(x)<=100 for x in s) else -25
        score+=6 if sum(abs(x) for x in t)<100 else -10
        qs.append(q);ss.append(s);ts.append(t)
    spread=max((sum(abs(x) for x in t) for t in ts),default=0.0)
    if spread<100: score+=60
    return {'offset':o,'endian':endian,'score':score,'translations':ts,'rotations':qs,'scales':ss,'spread':spread}
def _coords(a,start,stop,n):
    best=None
    for o in range(start,max(start,min(stop,len(a)-n*40)+1)):
        for e in ('be','le'):
            c=_coord_score(a,o,n,e)
            if c is not None and (best is None or c['score']>best['score']): best=c
    return best or {'offset':start,'endian':'be','score':0,'translations':[[0,0,0] for _ in range(n)],'rotations':[[1,0,0,0] for _ in range(n)],'scales':[[1,1,1] for _ in range(n)],'spread':0.0}
def _nearest(node,parent,lookup):
    p=parent[node] if 0<=node<len(parent) else 255;seen={node}
    while p!=255 and p not in seen:
        if p in lookup: return lookup[p]
        seen.add(p);p=parent[p] if 0<=p<len(parent) else 255
    return -1
def _tail(i,m,children,globals):
    c=_tr(m)
    for ch in children.get(i,[]):
        if 0<=ch<len(globals):
            p=_tr(globals[ch])
            if sum(abs(p[j]-c[j]) for j in range(3))>1e-6: return p
    return [c[0],c[1]+0.035,c[2]]
def parse_skel_asset(a):
    if not is_rfrm_type(a,'SKEL'): raise PakError('Keine SKEL-Ressource')
    if len(a)<44: raise PakError('SKEL ist zu klein')
    p=32;marker=be32(a,p);va=be32(a,24);vb=be32(a,28);ua=be32(a,p+4);name_count=be32(a,p+8)
    if name_count<=0 or name_count>4096: raise PakError(f'SKEL-Namenszähler wirkt ungültig ({name_count})')
    p+=12;names=[]
    for i in range(name_count):
        name,size,p=read_name(a,p);names.append({'index':i,'name':name,'size':size})
    fields_offset=p
    fields={'zero_or_flags':be32(a,p),'name_count_repeat':be16(a,p+4),'node_count':be16(a,p+6),'skin_bone_count':be16(a,p+8),'aux_u32_count':be16(a,p+10),'aux_u8_count':be16(a,p+12),'has_skeleton_map':bool(a[p+14])} if p+15<=len(a) else {}
    node_count=int(fields.get('node_count') or 0);skin_count=int(fields.get('skin_bone_count') or 0);p+=15
    skeleton_map={};node_names=list(range(min(node_count,name_count)))
    if fields.get('has_skeleton_map'):
        skeleton_map,p=_parse_skeleton_map(a,p)
        node_names=list(skeleton_map.get('values') or node_names)
    animation_attributes,p=_parse_animation_attributes(a,p)
    runtime_offset=p
    runtime={'offset':runtime_offset,'unknown_count_b':a[p] if p<len(a) else 0,'unknown_count_c':a[p+1] if p+1<len(a) else 0,'unknown_count_a':a[p+2] if p+2<len(a) else 0,'unknown_count_e':a[p+3] if p+3<len(a) else 0,'unknown_count_d':be32(a,p+4) if p+8<=len(a) else 0}
    p+=8
    parent_offset=p;parent=list(a[p:p+node_count]) if node_count>0 and p+node_count<=len(a) else [255]*node_count;p+=len(parent)
    skin_offset=p;skin_names=list(a[p:p+skin_count]) if skin_count>0 and p+skin_count<=len(a) else [x for x in node_names if 0<=x<name_count][:skin_count];p+=len(skin_names)
    flags_offset=p;node_flags=list(a[p:p+node_count]) if node_count>0 and p+node_count<=len(a) else [];p+=len(node_flags)
    tr=_coords(a,p,min(len(a),p+256),node_count);coord_offset=tr.get('offset',p);aux_data=a[p:coord_offset]
    ts=tr.get('translations') or [[0,0,0] for _ in range(node_count)];qs=tr.get('rotations') or [[1,0,0,0] for _ in range(node_count)];ss=tr.get('scales') or [[1,1,1] for _ in range(node_count)]
    raw_local=[_qmat(ts[i] if i<len(ts) else [0,0,0],qs[i] if i<len(qs) else [1,0,0,0],ss[i] if i<len(ss) else [1,1,1]) for i in range(node_count)]
    raw_global=[]
    for i,m in enumerate(raw_local):
        pv=parent[i] if i<len(parent) else 255
        raw_global.append(_mm(raw_global[pv],m) if pv!=255 and 0<=pv<i and pv<len(raw_global) else m)
    name_to_node={}
    for ni,nam in enumerate(node_names):
        if 0<=nam<name_count and nam not in name_to_node: name_to_node[nam]=ni
    skin_nodes=[name_to_node[x] for x in skin_names if x in name_to_node];lookup={n:i for i,n in enumerate(skin_nodes)}
    children={i:[] for i in range(node_count)}
    for i,pv in enumerate(parent):
        if pv!=255 and 0<=pv<node_count and pv!=i: children.setdefault(pv,[]).append(i)
    bones=[]
    for bi,ni in enumerate(skin_nodes):
        name_index=node_names[ni] if ni<len(node_names) else ni;pi=_nearest(ni,parent,lookup);g=raw_global[ni]
        lm=_mm(_inv(raw_global[skin_nodes[pi]]),g) if pi>=0 else g;head=_tr(g)
        bones.append({'index':bi,'node_index':ni,'name_index':name_index,'name':names[name_index]['name'] if 0<=name_index<len(names) else f'bone_{bi:03d}','parent_index':pi,'parent_node_index':parent[ni] if ni<len(parent) else 255,'matrix':lm,'global_matrix':g,'inverse_bind_matrix':_inv(g),'translation':ts[ni] if ni<len(ts) else [0,0,0],'rotation':qs[ni] if ni<len(qs) else [1,0,0,0],'scale':ss[ni] if ni<len(ss) else [1,1,1],'head':head,'tail':_tail(ni,g,children,raw_global)})
    nodes=[]
    for ni,nam in enumerate(node_names):
        nodes.append({'index':ni,'name_index':nam,'name':names[nam]['name'] if 0<=nam<len(names) else f'node_{ni:03d}','parent_index':parent[ni] if ni<len(parent) else 255,'flags':node_flags[ni] if ni<len(node_flags) else 0,'matrix':raw_local[ni] if ni<len(raw_local) else _id(),'global_matrix':raw_global[ni] if ni<len(raw_global) else _id(),'translation':ts[ni] if ni<len(ts) else [0,0,0],'rotation':qs[ni] if ni<len(qs) else [1,0,0,0],'scale':ss[ni] if ni<len(ss) else [1,1,1]})
    return {'type':'SKEL','version_a':va,'version_b':vb,'marker':f'0x{marker:08X}','unknown_a':ua,'size':len(a),'sha1':sha1_bytes(a),'name_count':name_count,'names':names,'fields':fields,'fields_offset':fields_offset,'data_start':fields_offset+15,'skeleton_map_offset':skeleton_map.get('offset',0),'skeleton_map_count':skeleton_map.get('count_a',0),'skeleton_map':skeleton_map,'node_name_indices':node_names,'animation_attributes':animation_attributes,'has_info_data':bool(animation_attributes.get('has_info_data')),'runtime_header':runtime,'parent_table_offset':parent_offset,'parent_table':parent,'skin_table_offset':skin_offset,'skin_name_indices':skin_names,'skin_node_indices':skin_nodes,'flags_offset':flags_offset,'node_flags':node_flags,'aux_offset':flags_offset+len(node_flags),'aux_size':len(aux_data),'aux_data_hex':aux_data.hex(),'transform_offset':coord_offset,'transform_endian':tr.get('endian',''),'transform_format':'f32_quat_scale_pos','transform_stride':40,'transform_count':node_count,'transform_score':tr.get('score',0),'bind_matrix_mode':'skel_quat_scale_pos','coordinate_fix':'none','node_count':node_count,'skin_bone_count':skin_count,'nodes':nodes,'bones':bones,'status':'SKEL wird strukturell dekodiert: Skeleton-Map, Parent/Skin/Flags und Coord-Block im Format Quaternion + Scale + Position. SMDL-Joints werden ueber Skin-Namensindizes auf Coord-Nodes gemappt; keine SMDL-basierte Offset-Korrektur wird auf die Bind-Pose angewendet.'}
def parse_rfrm_chunks(a):
    if len(a)<32 or a[:4]!=b'RFRM': return []
    out=[];p=32
    while p<len(a):
        if p+24>len(a): out.append({'tag':'TRUNCATED','off':p,'size':len(a)-p,'version':0,'payload_off':p,'payload_end':len(a),'sha1':sha1_bytes(a[p:])});break
        tag=tag4(a,p);size=be64(a,p+4);ver=be32(a,p+12);po=p+24;pe=po+size
        if pe>len(a): out.append({'tag':tag,'off':p,'size':size,'version':ver,'payload_off':po,'payload_end':len(a),'sha1':sha1_bytes(a[po:])});break
        out.append({'tag':tag,'off':p,'size':size,'version':ver,'payload_off':po,'payload_end':pe,'sha1':sha1_bytes(a[po:pe])});p=pe
    return out
def parse_skeletal_asset_summary(a,fallback_type=''):
    typ=tag4(a,20) if len(a)>=24 and a[:4]==b'RFRM' else fallback_type
    return parse_skel_asset(a) if typ=='SKEL' else {'type':typ,'size':len(a),'sha1':sha1_bytes(a),'chunks':parse_rfrm_chunks(a)}
def resolve_ref(parsed,uuid_hex,require_store=None):
    if not uuid_hex or uuid_hex==ZERO_UUID: return None,None,'',''
    e=parsed.get('uuid_to_entry',{}).get(uuid_hex)
    if e is not None: return get_entry_asset(parsed,e),e,'pak',parsed.get('path','')
    if require_store is not None:
        a,e,s=require_store.resolve_asset(parsed,uuid_hex)
        if e is not None and a is not None: return a,e,s,require_store.get_required_source(uuid_hex) if s=='require' else parsed.get('path','')
    return None,None,'',''
def known_entries_by_uuid(parsed,require_store=None):
    out={e['uuid_hex']:(e,'pak',parsed.get('path','')) for e in parsed.get('entries',[])}
    if require_store is not None:
        for u,it in getattr(require_store,'required_entries_by_uuid',{}).items(): out[u]=(it['entry'],'require',it.get('parsed_path',''))
    return out
def find_known_uuid_refs(asset,parsed,require_store=None,wanted_types=None):
    wanted_types=set(wanted_types or []);refs=[]
    for u,it in known_entries_by_uuid(parsed,require_store).items():
        e,s,sp=it
        if u==ZERO_UUID or (wanted_types and e.get('type') not in wanted_types): continue
        try: needle=bytes.fromhex(u)
        except Exception: continue
        pos=asset.find(needle)
        while pos!=-1:
            refs.append({'uuid_hex':u,'offset':pos,'entry_type':e.get('type',''),'entry_name':e.get('display_name') or e.get('name') or '','source_kind':s,'source_path':sp});pos=asset.find(needle,pos+1)
    refs.sort(key=lambda x:(x['offset'],x['entry_type'],x['uuid_hex']))
    return refs
def unique_path(path):
    path=Path(path)
    if not path.exists(): return path
    suffix=''.join(path.suffixes);stem=path.name[:-len(suffix)] if suffix else path.name;n=2
    while True:
        c=path.with_name(f'{stem}_{n}{suffix}')
        if not c.exists(): return c
        n+=1
def rel(root,path): return str(Path(path).relative_to(root)).replace('\\','/')
def asset_file_name(prefix,entry,uuid_hex,fallback_type):
    typ=entry.get('type') if entry is not None else fallback_type;name=entry.get('display_name') or entry.get('name') or '' if entry is not None else ''
    return safe_name('__'.join(x for x in (prefix,typ,name,uuid_hex) if x))+kind_to_ext(typ)
def write_json(path,value): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n');return path
def write_bytes(path,data): path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
def export_skeletal_asset(folder,parsed,ref,require_store=None,prefix=''):
    uuid_hex=ref.get('uuid_hex','');asset,entry,source,source_path=resolve_ref(parsed,uuid_hex,require_store);rec=dict(ref)
    rec.update({'resolved':entry is not None and asset is not None,'entry_type':entry.get('type') if entry else '','entry_name':entry.get('display_name') or entry.get('name') or '' if entry else '','source_kind':source,'source_path':source_path,'raw_file':'','summary_file':'','summary':{}})
    if entry is None or asset is None: return rec
    typ=entry.get('type') or ref.get('type') or 'UNKNOWN';raw_path=unique_path(Path(folder)/typ/asset_file_name(prefix or ref.get('name') or typ,entry,uuid_hex,typ));write_bytes(raw_path,asset)
    summary_path=raw_path.with_suffix(raw_path.suffix+'.json');summary=parse_skeletal_asset_summary(asset,typ);summary.update({'uuid_hex':uuid_hex,'entry_name':rec['entry_name'],'source_kind':source,'source_path':source_path});write_json(summary_path,summary)
    rec['raw_file']=str(raw_path);rec['summary_file']=str(summary_path);rec['summary']=summary
    return rec
