from pathlib import Path
import csv,hashlib,json,math,statistics,struct
from pak_core import get_entry_asset,safe_name,kind_to_ext

def be16(d,o): return int.from_bytes(d[o:o+2],'big') if o+2<=len(d) else 0
def be32(d,o): return int.from_bytes(d[o:o+4],'big') if o+4<=len(d) else 0
def be64(d,o): return int.from_bytes(d[o:o+8],'big') if o+8<=len(d) else 0
def tag4(d,o): return d[o:o+4].decode('ascii','replace') if o+4<=len(d) else ''
def sha1(d): return hashlib.sha1(d).hexdigest()
def uuid_text(h):
    h=str(h or '').replace('-','').lower()
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}' if len(h)==32 else h
def uuid_key(s): return str(s or '').replace('-','').lower()
def entry_name(e): return str(e.get('display_name') or e.get('name') or uuid_text(e.get('uuid_hex','')))
def entry_file_name(e): return safe_name(uuid_text(e.get('uuid_hex','')))+kind_to_ext(e.get('type',''))
def entropy(d):
    if not d: return 0.0
    c=[0]*256
    for b in d: c[b]+=1
    n=len(d)
    return -sum((x/n)*math.log2(x/n) for x in c if x)
def rfrm(d): return {'ok':len(d)>=32 and d[:4]==b'RFRM','size_field':be64(d,4),'type':tag4(d,20),'version_a':be32(d,24),'version_b':be32(d,28),'payload_offset':32,'payload_size':max(0,len(d)-32)}
def read_name(d,p):
    if p+4>len(d): return None,p
    n=be32(d,p)
    if n<=0 or n>4096 or p+4+n>len(d): return None,p
    raw=d[p+4:p+4+n]
    return raw.split(b'\x00',1)[0].decode('utf-8','replace'),p+4+n
def name_before(d,offset,window=160):
    best=''; best_off=-1
    for p in range(max(0,offset-window),offset):
        name,end=read_name(d,p)
        if name is not None and end<=offset and end>best_off: best=name; best_off=end
    return best
def collect_assets(parsed,require_store=None):
    primary=[]
    for entry in parsed.get('entries',[]):
        primary.append({'entry':entry,'asset':get_entry_asset(parsed,entry),'source':'pak','source_path':str(parsed.get('path',''))})
    required=[]
    if require_store is not None:
        for uuid_hex,item in getattr(require_store,'required_entries_by_uuid',{}).items():
            entry=item.get('entry') or {}
            required.append({'entry':entry,'asset':item.get('asset',b''),'source':'require','source_path':str(item.get('parsed_path',''))})
    all_assets=primary+required
    by_uuid={uuid_key(x['entry'].get('uuid_hex','')):x for x in all_assets if uuid_key(x['entry'].get('uuid_hex',''))}
    return primary,required,by_uuid
def find_uuid_refs(d,by_uuid):
    out=[]
    for k,item in by_uuid.items():
        if len(k)!=32: continue
        b=bytes.fromhex(k); p=d.find(b)
        while p!=-1:
            e=item['entry']
            out.append({'offset':p,'uuid':uuid_text(k),'uuid_hex':k,'file':entry_file_name(e),'name':entry_name(e),'type':e.get('type',''),'source':item.get('source',''),'source_path':item.get('source_path','')})
            p=d.find(b,p+1)
    out.sort(key=lambda x:(x['offset'],x['type'],x['file']))
    return out
def parse_skel(item):
    e=item['entry']; d=item['asset']; h=rfrm(d); out={'file':entry_file_name(e),'uuid':uuid_text(e.get('uuid_hex','')),'uuid_hex':uuid_key(e.get('uuid_hex','')),'name':entry_name(e),'source':item.get('source',''),'source_path':item.get('source_path',''),'size':len(d),'sha1':sha1(d),**h}
    if not h['ok'] or h['type']!='SKEL': return out
    p=32; out['marker']=f'0x{be32(d,p):08X}'; out['unknown_a']=be32(d,p+4); count=be32(d,p+8); p+=12; names=[]
    if 0<count<=4096:
        for i in range(count):
            name,p2=read_name(d,p)
            if name is None: break
            names.append({'index':i,'name':name,'offset':p}); p=p2
    out['name_count']=len(names); out['names']=names
    if p+15<=len(d):
        out['fields_offset']=p; out['node_count']=be16(d,p+6); out['skin_bone_count']=be16(d,p+8); out['has_skeleton_map']=bool(d[p+14])
    return out
def parse_char(item,by_uuid):
    e=item['entry']; d=item['asset']; h=rfrm(d); refs=find_uuid_refs(d,by_uuid)
    out={'file':entry_file_name(e),'uuid':uuid_text(e.get('uuid_hex','')),'uuid_hex':uuid_key(e.get('uuid_hex','')),'name':entry_name(e),'source':item.get('source',''),'source_path':item.get('source_path',''),'size':len(d),'sha1':sha1(d),**h,'skeleton_uuid':'','skeleton_file':'','skeleton_source':'','models':[],'animations':[],'uuid_refs':refs}
    if not h['ok'] or h['type']!='CHAR': return out
    skels=[x for x in refs if x['type']=='SKEL']
    if skels:
        sk=skels[0]; out['skeleton_uuid']=sk['uuid']; out['skeleton_file']=sk['file']; out['skeleton_source']=sk.get('source','')
    for i,x in enumerate([x for x in refs if x['type'] in ('CMDL','SMDL','WMDL','GENP')]):
        out['models'].append({'index':i,'name':name_before(d,x['offset']),'uuid':x['uuid'],'file':x['file'],'type':x['type'],'offset':x['offset'],'source':x.get('source','')})
    anims=[x for x in refs if x['type']=='ANIM']; out['animation_count']=len(anims)
    for i,x in enumerate(anims):
        out['animations'].append({'index':i,'name':name_before(d,x['offset']),'uuid':x['uuid'],'uuid_hex':x['uuid_hex'],'type':'ANIM','file':x['file'],'offset':x['offset'],'source':x.get('source','')})
    return out
def unpack_floats(d,o,n,endian):
    if o+4*n>len(d): return None
    try: return list(struct.unpack_from(('>' if endian=='be' else '<')+'f'*n,d,o))
    except Exception: return None
def scan_quats(d,start,limit=24):
    out=[]; counts={'be':0,'le':0}; stop=max(start,min(len(d)-16,start+262144))
    for o in range(start,stop,4):
        for endian in ('be','le'):
            v=unpack_floats(d,o,4,endian)
            if not v or not all(math.isfinite(x) and abs(x)<=4 for x in v): continue
            l=math.sqrt(sum(x*x for x in v))
            if 0.985<=l<=1.015:
                counts[endian]+=1
                if len(out)<limit: out.append({'offset':o,'file_offset':o+32,'endian':endian,'values':[round(x,6) for x in v],'length':round(l,6)})
    return {'counts':counts,'examples':out}
def scan_vec3(d,start,limit=24):
    out=[]; counts={'be':0,'le':0}; stop=max(start,min(len(d)-12,start+262144))
    for o in range(start,stop,4):
        for endian in ('be','le'):
            v=unpack_floats(d,o,3,endian)
            if not v or not all(math.isfinite(x) and abs(x)<1000 for x in v): continue
            s=sum(abs(x) for x in v)
            if 0.00001<s<250:
                counts[endian]+=1
                if len(out)<limit: out.append({'offset':o,'file_offset':o+32,'endian':endian,'values':[round(x,6) for x in v]})
    return {'counts':counts,'examples':out}
def parse_anim(item,skel=None):
    e=item['entry']; d=item['asset']; h=rfrm(d); p=d[32:]; out={'file':entry_file_name(e),'uuid':uuid_text(e.get('uuid_hex','')),'uuid_hex':uuid_key(e.get('uuid_hex','')),'name':entry_name(e),'source':item.get('source',''),'source_path':item.get('source_path',''),'size':len(d),'sha1':sha1(d),**h}
    if not h['ok'] or h['type']!='ANIM': return out
    inner=be32(p,4); ctrl=be32(p,8); desc=p[16:32]; data_start=52
    out.update({'inner_magic':p[:4].hex(),'inner_size':inner,'inner_size_ok':inner==len(d)-40,'control_u32':f'0x{ctrl:08X}','control_b0':p[8] if len(p)>8 else 0,'control_b1':p[9] if len(p)>9 else 0,'control_low16':be16(p,10),'group_hash':p[12:16].hex(),'descriptor_hex':desc.hex(),'descriptor_bytes':list(desc),'payload_data_offset':data_start,'file_data_offset':32+data_start,'data_header_hex':p[32:data_start].hex(),'data_prefix_hex':p[data_start:data_start+64].hex(),'payload_entropy':round(entropy(p),4),'data_entropy':round(entropy(p[data_start:]),4),'payload_nonzero_ratio':round(sum(1 for x in p if x)/max(1,len(p)),4),'data_nonzero_ratio':round(sum(1 for x in p[data_start:] if x)/max(1,len(p)-data_start),4)})
    out['quat_probe']=scan_quats(p,data_start); out['vec3_probe']=scan_vec3(p,data_start)
    node_count=int((skel or {}).get('node_count') or 0); skin_count=int((skel or {}).get('skin_bone_count') or 0)
    out['skel_node_count']=node_count; out['skel_skin_bone_count']=skin_count
    out['ratio_to_nodes']=round(max(0,len(p)-data_start)/node_count,3) if node_count else 0; out['ratio_to_skin_bones']=round(max(0,len(p)-data_start)/skin_count,3) if skin_count else 0; out['status']='probe_only'
    return out
def write_csv(path,rows):
    if not rows: return
    keys=[]
    for row in rows:
        for k in row:
            if k not in keys: keys.append(k)
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)
def counts(values,limit=50):
    c={}
    for v in values: c[v]=c.get(v,0)+1
    return dict(sorted(c.items(),key=lambda x:(-x[1],x[0]))[:limit])
def list_anim_options(parsed,require_store=None):
    primary,required,by_uuid=collect_assets(parsed,require_store); rows=[]
    for item in primary:
        e=item['entry']
        if e.get('type')=='ANIM': rows.append({'uuid_hex':uuid_key(e.get('uuid_hex','')),'uuid':uuid_text(e.get('uuid_hex','')),'name':entry_name(e),'file':entry_file_name(e),'source':item.get('source',''),'source_path':item.get('source_path',''),'size':len(item.get('asset',b''))})
    rows.sort(key=lambda x:(x['name'].lower(),x['file']))
    return rows
def summarise(data,out_dir):
    anims=data['anims']; links=data['links']; skels=data['skels']; chars=data['chars']; sizes=[x.get('size',0) for x in anims]
    return {'output_dir':str(out_dir),'files':data['asset_count'],'required_files_loaded':data.get('required_asset_count',0),'required_files_used':data.get('required_used_count',0),'skel_count':len(skels),'char_count':len(chars),'anim_count':len(anims),'char_anim_links':len(links),'resolved_anim_links':sum(1 for x in links if x.get('anim_file')),'resolved_skel_links':sum(1 for x in chars if x.get('skeleton_file')),'anim_inner_size_ok':sum(1 for x in anims if x.get('inner_size_ok')),'anim_magic_groups':counts(x.get('inner_magic','') for x in anims),'anim_descriptor_groups':counts((x.get('descriptor_hex','') for x in anims),20),'anim_control_groups':counts((x.get('control_u32','') for x in anims),20),'anim_size_min':min(sizes,default=0),'anim_size_max':max(sizes,default=0),'anim_size_avg':round(statistics.mean(sizes),2) if sizes else 0}
def run_tests(summary):
    failures=[]
    if summary['anim_count']<=0: failures.append('Keine ANIM-Dateien in aktueller PAK ausgewählt')
    if summary['char_count']<=0: failures.append('Keine CHAR-Dateien in aktueller PAK gefunden')
    if summary['skel_count']<=0: failures.append('Keine passenden SKEL-Dateien gefunden')
    if summary['anim_inner_size_ok']!=summary['anim_count']: failures.append('ANIM-Innenlängen passen nicht bei allen ausgewählten Dateien')
    return {'ok':not failures,'failures':failures,'summary':summary,'output_dir':summary['output_dir']}
def run_anim_probe(parsed,require_store,out_dir,selected_anim_uuids=None):
    out_dir=Path(out_dir).resolve(); raw_dir=out_dir/'raw'; out_dir.mkdir(parents=True,exist_ok=True); raw_dir.mkdir(parents=True,exist_ok=True)
    primary,required,by_uuid=collect_assets(parsed,require_store)
    primary_by_uuid={uuid_key(x['entry'].get('uuid_hex','')):x for x in primary if uuid_key(x['entry'].get('uuid_hex',''))}
    current_anim_uuids={uuid_key(x['entry'].get('uuid_hex','')) for x in primary if x['entry'].get('type')=='ANIM'}
    selected={uuid_key(x) for x in (selected_anim_uuids or []) if uuid_key(x)}
    selected=(selected&current_anim_uuids) if selected else set(current_anim_uuids)
    char_items=[x for x in primary if x['entry'].get('type')=='CHAR']
    chars=[parse_char(x,by_uuid) for x in char_items]
    anim_to_skel={}; links=[]; needed_skel_uuids=set(); needed_anim_uuids=set(selected)
    for ch in chars:
        sk=uuid_key(ch.get('skeleton_uuid',''))
        if sk: needed_skel_uuids.add(sk)
        for a in ch.get('animations',[]):
            au=uuid_key(a.get('uuid_hex',''))
            if au in current_anim_uuids: anim_to_skel[au]=sk
            if au in selected:
                needed_anim_uuids.add(au)
                links.append({'char_file':ch.get('file',''),'char_name':ch.get('name',''),'char_source':ch.get('source',''),'skel_uuid':ch.get('skeleton_uuid',''),'skel_file':ch.get('skeleton_file',''),'skel_source':ch.get('skeleton_source',''),'anim_index':a.get('index',0),'anim_name':a.get('name',''),'anim_uuid':a.get('uuid',''),'anim_file':a.get('file',''),'anim_source':a.get('source','')})
    primary_skel_uuids={uuid_key(x['entry'].get('uuid_hex','')) for x in primary if x['entry'].get('type')=='SKEL'}
    skel_uuids=primary_skel_uuids|needed_skel_uuids
    skel_items=[]
    for u in sorted(skel_uuids):
        item=primary_by_uuid.get(u) or by_uuid.get(u)
        if item is not None and item['entry'].get('type')=='SKEL': skel_items.append(item)
    skels=[parse_skel(x) for x in skel_items]; skel_by_uuid={x['uuid_hex']:x for x in skels}
    anims=[]
    for u in sorted(needed_anim_uuids):
        item=primary_by_uuid.get(u)
        if item is not None and item['entry'].get('type')=='ANIM': anims.append(parse_anim(item,skel_by_uuid.get(uuid_key(anim_to_skel.get(u,'')),{})))
    export_uuids={uuid_key(x['uuid_hex']) for x in skels}|{uuid_key(x['uuid_hex']) for x in chars}|{uuid_key(x['uuid_hex']) for x in anims}
    required_used_count=0
    for item in primary+required:
        u=uuid_key(item['entry'].get('uuid_hex',''))
        if u in export_uuids:
            if item.get('source')=='require': required_used_count+=1
            (raw_dir/entry_file_name(item['entry'])).write_bytes(item.get('asset',b''))
    data={'asset_count':len(primary),'required_asset_count':len(required),'required_used_count':required_used_count,'skels':skels,'chars':chars,'anims':anims,'links':links}
    summary=summarise(data,out_dir); tests=run_tests(summary)
    candidates=[]; anim_by_file={x.get('file',''):x for x in anims}; skel_by_file={x.get('file',''):x for x in skels}
    for link in links:
        anim=anim_by_file.get(link.get('anim_file',''),{}); skel=skel_by_file.get(link.get('skel_file',''),{}); q=anim.get('quat_probe',{}).get('counts',{}); v=anim.get('vec3_probe',{}).get('counts',{})
        candidates.append({'char_name':link.get('char_name',''),'char_file':link.get('char_file',''),'anim_index':link.get('anim_index',0),'anim_name':link.get('anim_name',''),'anim_file':link.get('anim_file',''),'skel_file':link.get('skel_file',''),'skel_source':link.get('skel_source',''),'size':anim.get('size',0),'control_u32':anim.get('control_u32',''),'descriptor_hex':anim.get('descriptor_hex',''),'node_count':skel.get('node_count',0),'skin_bone_count':skel.get('skin_bone_count',0),'ratio_to_nodes':anim.get('ratio_to_nodes',0),'ratio_to_skin_bones':anim.get('ratio_to_skin_bones',0),'vec3_be':v.get('be',0),'vec3_le':v.get('le',0),'quat_be':q.get('be',0),'quat_le':q.get('le',0)})
    candidates.sort(key=lambda x:(x['size'],x['char_name'],x['anim_index']))
    (out_dir/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    (out_dir/'tests.json').write_text(json.dumps(tests,indent=2,ensure_ascii=False),encoding='utf-8')
    (out_dir/'anims.json').write_text(json.dumps(anims,indent=2,ensure_ascii=False),encoding='utf-8')
    (out_dir/'chars.json').write_text(json.dumps(chars,indent=2,ensure_ascii=False),encoding='utf-8')
    (out_dir/'skels.json').write_text(json.dumps(skels,indent=2,ensure_ascii=False),encoding='utf-8')
    (out_dir/'anim_candidates.json').write_text(json.dumps(candidates[:80],indent=2,ensure_ascii=False),encoding='utf-8')
    write_csv(out_dir/'char_anim_links.csv',links); write_csv(out_dir/'anim_summary.csv',[{k:v for k,v in a.items() if not isinstance(v,(dict,list))} for a in anims]); write_csv(out_dir/'anim_candidates.csv',candidates)
    return tests
