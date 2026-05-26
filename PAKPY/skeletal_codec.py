from pathlib import Path
import json,math,struct
from pak_core import PakError,get_entry_asset,safe_name,sha1_bytes,kind_to_ext
ZERO_UUID='00000000000000000000000000000000'
SKELETAL_REF_TYPES={'SKEL','ANIM'}
def be16(d,o): return int.from_bytes(d[o:o+2],'big')
def be32(d,o): return int.from_bytes(d[o:o+4],'big')
def be64(d,o): return int.from_bytes(d[o:o+8],'big')
def le32(d,o): return int.from_bytes(d[o:o+4],'little')
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
def _basis(): return [1.0,0.0,0.0,0.0,0.0,-1.0,0.0,0.0,0.0,0.0,-1.0,0.0,0.0,0.0,0.0,1.0]
def _mm(a,b):
    r=[0.0]*16
    for y in range(4):
        for x in range(4): r[y*4+x]=sum(a[y*4+k]*b[k*4+x] for k in range(4))
    return r
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
def _cb(m):
    b=_basis();return _mm(_mm(b,m),b)
def _tr(m): return [_sf(m[3]),_sf(m[7]),_sf(m[11])]
def _node_names(a,start,n,names):
    if n<=0 or start+4+n>len(a) or le32(a,start)!=n: return []
    v=list(a[start+4:start+4+n])
    return v if all(x==255 or x<names for x in v) else []
def _parent(a,start,stop,n):
    best=(-1,0,[])
    for o in range(start,max(start,stop-n+1)):
        v=list(a[o:o+n])
        if len(v)!=n or not all(x==255 or x<n for x in v): continue
        roots=sum(1 for x in v if x==255);back=sum(1 for i,x in enumerate(v) if x==255 or x<i);score=back*4+roots*8+(60 if 1<=roots<=max(6,n//8) else 0)+(50 if v[:3]==[255,255,255] else 0)
        if score>best[0]: best=(score,o,v)
    return {'score':best[0],'offset':best[1],'values':best[2]}
def _skin(a,start,stop,names,count):
    best=(-1,0,[])
    for o in range(start,max(start,stop-count+1)):
        v=list(a[o:o+count])
        if len(v)!=count or not all(0<=x<names for x in v): continue
        u=len(set(v));asc=sum(1 for x,y in zip(v,v[1:]) if y>x);score=u*5+asc+(100 if u==count else 0)+(10 if v and v[0]>0 else 0)
        if score>best[0]: best=(score,o,v)
    return {'score':best[0],'offset':best[1],'values':best[2]}
def _trs_score(a,o,n,endian):
    if n<=0 or o+n*40>len(a): return None
    fmt=('>' if endian=='be' else '<')+'f'*10;score=0;ts=[];qs=[];ss=[]
    for i in range(n):
        try: vals=list(struct.unpack_from(fmt,a,o+i*40))
        except Exception: return None
        if not all(math.isfinite(x) and abs(x)<1000000 for x in vals): return None
        t=vals[:3];q=vals[3:7];s=vals[7:10];ql=math.sqrt(sum(x*x for x in q))
        score+=8 if 0.98<=ql<=1.02 else 3 if 0.75<=ql<=1.25 else -10
        score+=8 if all(abs(abs(x)-1)<=0.02 for x in s) else 2 if all(0.001<=abs(x)<=100 for x in s) else -10
        if sum(abs(x) for x in t)<100: score+=4
        ts.append(t);qs.append(q);ss.append(s)
    spread=max((sum(abs(x) for x in t) for t in ts),default=0.0)
    if spread<100: score+=40
    return {'offset':o,'endian':endian,'score':score,'translations':ts,'rotations':qs,'scales':ss,'spread':spread}
def _trs(a,start,stop,n):
    best=None
    for o in range(start,max(start,stop-n*40+1)):
        for e in ('be','le'):
            c=_trs_score(a,o,n,e)
            if c is not None and (best is None or c['score']>best['score']): best=c
    return best or {'offset':0,'endian':'be','score':0,'translations':[],'rotations':[],'scales':[],'spread':0.0}
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
def _correct(globals):
    if not globals: return []
    root_inv=_inv(globals[0])
    return [_cb(_mm(root_inv,m)) for m in globals]
def _locals(globals,parent):
    out=[]
    for i,g in enumerate(globals):
        p=parent[i] if i<len(parent) else 255
        out.append(_mm(_inv(globals[p]),g) if p!=255 and 0<=p<i and p<len(globals) else g)
    return out
def parse_skel_asset(a):
    if not is_rfrm_type(a,'SKEL'): raise PakError('Keine SKEL-Ressource')
    if len(a)<44: raise PakError('SKEL ist zu klein')
    p=32;marker=be32(a,p);va=be32(a,24);vb=be32(a,28);ua=be32(a,p+4);name_count=be32(a,p+8)
    if name_count<=0 or name_count>4096: raise PakError(f'SKEL-Namenszähler wirkt ungültig ({name_count})')
    p+=12;names=[]
    for i in range(name_count):
        name,size,p=read_name(a,p);names.append({'index':i,'name':name,'size':size})
    fields_offset=p;fields={}
    if p+16<=len(a): fields={'zero_or_flags':be32(a,p),'name_count_repeat':be16(a,p+4),'node_count':be16(a,p+6),'skin_bone_count':be16(a,p+8),'group_count_a':be16(a,p+10),'group_count_b':be16(a,p+12),'flags':be16(a,p+14)}
    node_count=int(fields.get('node_count') or 0);skin_count=int(fields.get('skin_bone_count') or 0);data_start=p+16
    node_names=_node_names(a,data_start,node_count,name_count) or list(range(min(node_count,name_count)))
    search_start=data_start+4+len(node_names);search_stop=min(len(a),data_start+4096)
    parent_info=_parent(a,search_start,search_stop,node_count);parent=parent_info.get('values') or [255]*node_count
    skin_info=_skin(a,parent_info.get('offset',search_start)+node_count,search_stop,name_count,skin_count);skin_names=skin_info.get('values') or [x for x in node_names if 0<=x<name_count][:skin_count]
    tr=_trs(a,data_start,len(a),node_count);ts=tr.get('translations') or [[0,0,0] for _ in range(node_count)];qs=tr.get('rotations') or [[1,0,0,0] for _ in range(node_count)];ss=tr.get('scales') or [[1,1,1] for _ in range(node_count)]
    raw_local=[_qmat(ts[i] if i<len(ts) else [0,0,0],qs[i] if i<len(qs) else [1,0,0,0],ss[i] if i<len(ss) else [1,1,1]) for i in range(node_count)]
    raw_global=[]
    for i,m in enumerate(raw_local):
        p=parent[i] if i<len(parent) else 255
        raw_global.append(_mm(raw_global[p],m) if p!=255 and 0<=p<i and p<len(raw_global) else m)
    globals=_correct(raw_global);locals_=_locals(globals,parent)
    name_to_node={}
    for ni,nam in enumerate(node_names):
        if 0<=nam<name_count and nam not in name_to_node: name_to_node[nam]=ni
    skin_nodes=[name_to_node[x] for x in skin_names if x in name_to_node];lookup={n:i for i,n in enumerate(skin_nodes)}
    children={i:[] for i in range(node_count)}
    for i,pv in enumerate(parent):
        if pv!=255 and 0<=pv<node_count and pv!=i: children.setdefault(pv,[]).append(i)
    bones=[]
    for bi,ni in enumerate(skin_nodes):
        name_index=node_names[ni] if ni<len(node_names) else ni;pi=_nearest(ni,parent,lookup);g=globals[ni]
        lm=_mm(_inv(globals[skin_nodes[pi]]),g) if pi>=0 else g;head=_tr(g)
        bones.append({'index':bi,'node_index':ni,'name_index':name_index,'name':names[name_index]['name'] if 0<=name_index<len(names) else f'bone_{bi:03d}','parent_index':pi,'parent_node_index':parent[ni] if ni<len(parent) else 255,'matrix':lm,'global_matrix':g,'inverse_bind_matrix':_inv(g),'translation':ts[ni] if ni<len(ts) else [0,0,0],'rotation':qs[ni] if ni<len(qs) else [1,0,0,0],'scale':ss[ni] if ni<len(ss) else [1,1,1],'head':head,'tail':_tail(ni,g,children,globals)})
    nodes=[]
    for ni,nam in enumerate(node_names):
        nodes.append({'index':ni,'name_index':nam,'name':names[nam]['name'] if 0<=nam<len(names) else f'node_{ni:03d}','parent_index':parent[ni] if ni<len(parent) else 255,'matrix':locals_[ni] if ni<len(locals_) else _id(),'global_matrix':globals[ni] if ni<len(globals) else _id(),'raw_global_matrix':raw_global[ni] if ni<len(raw_global) else _id(),'translation':ts[ni] if ni<len(ts) else [0,0,0],'rotation':qs[ni] if ni<len(qs) else [1,0,0,0],'scale':ss[ni] if ni<len(ss) else [1,1,1]})
    tail=a[fields_offset:]
    return {'type':'SKEL','version_a':va,'version_b':vb,'marker':f'0x{marker:08X}','unknown_a':ua,'size':len(a),'sha1':sha1_bytes(a),'name_count':name_count,'names':names,'fields':fields,'fields_offset':fields_offset,'data_start':data_start,'node_name_indices':node_names,'parent_table_offset':parent_info.get('offset',0),'parent_table':parent,'skin_table_offset':skin_info.get('offset',0),'skin_name_indices':skin_names,'skin_node_indices':skin_nodes,'transform_offset':tr.get('offset',0),'transform_endian':tr.get('endian',''),'transform_format':'f32_trs_quat_scale','transform_stride':40,'transform_count':node_count,'transform_score':tr.get('score',0),'coordinate_fix':'root_removed_x_yz_flipped','tail_size':len(tail),'tail_sha1':sha1_bytes(tail),'node_count':node_count,'skin_bone_count':skin_count,'nodes':nodes,'bones':bones,'status':'SKEL-Parent-Tabelle wird als Node-Tabelle gelesen; root.move wird entfernt und Y/Z werden für Modellraum gespiegelt.'}
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
