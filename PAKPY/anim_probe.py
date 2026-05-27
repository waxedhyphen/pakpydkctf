from pathlib import Path
import argparse,csv,hashlib,json,math,statistics,struct

def be16(d,o): return int.from_bytes(d[o:o+2],'big') if o+2<=len(d) else 0
def be32(d,o): return int.from_bytes(d[o:o+4],'big') if o+4<=len(d) else 0
def be64(d,o): return int.from_bytes(d[o:o+8],'big') if o+8<=len(d) else 0
def tag4(d,o): return d[o:o+4].decode('ascii','replace') if o+4<=len(d) else ''
def sha1(d): return hashlib.sha1(d).hexdigest()
def uuid_text(b):
    h=b.hex()
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}' if len(h)==32 else ''
def uuid_key(s): return str(s or '').replace('-','').lower()
def entropy(d):
    if not d: return 0.0
    c=[0]*256
    for b in d: c[b]+=1
    n=len(d)
    return -sum((x/n)*math.log2(x/n) for x in c if x)
def rfrm(d):
    return {'ok':len(d)>=32 and d[:4]==b'RFRM','size_field':be64(d,4),'zero_field':be64(d,12),'type':tag4(d,20),'version_a':be32(d,24),'version_b':be32(d,28),'payload_offset':32,'payload_size':max(0,len(d)-32)}
def read_name(d,p):
    if p+4>len(d): return None,p
    n=be32(d,p)
    if n<=0 or n>4096 or p+4+n>len(d): return None,p
    raw=d[p+4:p+4+n]
    return raw.split(b'\x00',1)[0].decode('utf-8','replace'),p+4+n
def scan_names(d,start,end):
    out=[]
    for p in range(start,min(end,len(d))):
        name,q=read_name(d,p)
        if name is not None: out.append({'offset':p,'name':name,'end':q})
    return out
def build_uuid_map(files):
    out={}
    for p in files:
        k=uuid_key(p.stem)
        if len(k)==32 and all(x in '0123456789abcdef' for x in k): out[k]=p
    return out
def parse_skel(path):
    d=path.read_bytes(); h=rfrm(d); out={'file':path.name,'uuid':path.stem,'size':len(d),'sha1':sha1(d),**h}
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
def find_uuid_refs(d,uuid_map):
    out=[]
    for k,path in uuid_map.items():
        b=bytes.fromhex(k); p=d.find(b)
        while p!=-1:
            out.append({'offset':p,'uuid':uuid_text(b),'file':path.name,'ext':path.suffix.lower()}); p=d.find(b,p+1)
    out.sort(key=lambda x:(x['offset'],x['ext'],x['file']))
    return out
def name_before(d,offset,window=160):
    best=''; best_off=-1
    for p in range(max(0,offset-window),offset):
        name,end=read_name(d,p)
        if name is not None and end<=offset and end>best_off: best=name; best_off=end
    return best
def parse_char(path,uuid_map):
    d=path.read_bytes(); h=rfrm(d); refs=find_uuid_refs(d,uuid_map)
    out={'file':path.name,'uuid':path.stem,'size':len(d),'sha1':sha1(d),**h,'name':'','skeleton_uuid':'','skeleton_file':'','models':[],'animations':[],'uuid_refs':refs}
    if not h['ok'] or h['type']!='CHAR': return out
    skels=[x for x in refs if x['ext']=='.skel']
    if skels:
        sk=skels[0]; out['skeleton_uuid']=sk['uuid']; out['skeleton_file']=sk['file']; out['name']=name_before(d,sk['offset'])
    else:
        names=scan_names(d,32,128); out['name']=names[0]['name'] if names else ''
    for i,x in enumerate([x for x in refs if x['ext'] in ('.cmdl','.smdl','.wmdl','.genp')]):
        out['models'].append({'index':i,'name':name_before(d,x['offset']),'uuid':x['uuid'],'file':x['file'],'type':x['ext'][1:].upper(),'offset':x['offset']})
    anims=[x for x in refs if x['ext']=='.anim']; out['animation_count']=len(anims)
    for i,x in enumerate(anims):
        out['animations'].append({'index':i,'name':name_before(d,x['offset']),'uuid':x['uuid'],'type':'ANIM','file':x['file'],'offset':x['offset']})
    return out
def unpack_floats(d,o,n,endian):
    if o+4*n>len(d): return None
    try: return list(struct.unpack_from(('>' if endian=='be' else '<')+'f'*n,d,o))
    except Exception: return None
def scan_quats(d,start,limit=24):
    out=[]; counts={'be':0,'le':0}; stop=max(start,min(len(d)-16,start+262144))
    for o in range(start,stop,4):
        for e in ('be','le'):
            v=unpack_floats(d,o,4,e)
            if not v or not all(math.isfinite(x) and abs(x)<=4 for x in v): continue
            l=math.sqrt(sum(x*x for x in v))
            if 0.985<=l<=1.015:
                counts[e]+=1
                if len(out)<limit: out.append({'offset':o,'endian':e,'values':[round(x,6) for x in v],'length':round(l,6)})
    return {'counts':counts,'examples':out}
def scan_vec3(d,start,limit=24):
    out=[]; counts={'be':0,'le':0}; stop=max(start,min(len(d)-12,start+262144))
    for o in range(start,stop,4):
        for e in ('be','le'):
            v=unpack_floats(d,o,3,e)
            if not v or not all(math.isfinite(x) and abs(x)<1000 for x in v): continue
            s=sum(abs(x) for x in v)
            if 0.00001<s<250:
                counts[e]+=1
                if len(out)<limit: out.append({'offset':o,'endian':e,'values':[round(x,6) for x in v]})
    return {'counts':counts,'examples':out}
def zero_runs(d):
    out=[]; i=0
    while i<len(d):
        if d[i]!=0: i+=1; continue
        j=i
        while j<len(d) and d[j]==0: j+=1
        if j-i>=4: out.append((i,j-i))
        i=j
    return out
def scan_full_transforms(d,start,node_count):
    out=[]
    if node_count<=0 or node_count>512: return out
    span=node_count*40; stop=max(start,min(len(d)-span,start+65536))
    for o in range(start,stop,4):
        score=0; valid=True
        for i in range(min(node_count,64)):
            vals=unpack_floats(d,o+i*40,10,'be')
            if not vals or not all(math.isfinite(x) and abs(x)<100000 for x in vals): valid=False; break
            q=vals[:4]; s=vals[4:7]; t=vals[7:10]; ql=math.sqrt(sum(x*x for x in q))
            score+=8 if 0.9<=ql<=1.1 else -12; score+=4 if all(0.001<=abs(x)<=100 for x in s) else -8; score+=3 if sum(abs(x) for x in t)<500 else -4
        if valid and score>node_count*6:
            out.append({'offset':o,'score':score})
            if len(out)>=16: break
    return out
def parse_anim(path,skel=None):
    d=path.read_bytes(); h=rfrm(d); p=d[32:]; out={'file':path.name,'uuid':path.stem,'size':len(d),'sha1':sha1(d),**h}
    if not h['ok'] or h['type']!='ANIM': return out
    inner=be32(p,4); ctrl=be32(p,8); desc=p[16:32]
    out.update({'inner_magic':p[:4].hex(),'inner_size':inner,'inner_size_ok':inner==len(d)-40,'control_u32':f'0x{ctrl:08X}','control_b0':p[8] if len(p)>8 else 0,'control_b1':p[9] if len(p)>9 else 0,'control_low16':be16(p,10),'group_hash':p[12:16].hex(),'descriptor_hex':desc.hex(),'descriptor_bytes':list(desc),'data_offset':64,'payload_entropy':round(entropy(p),4),'payload_nonzero_ratio':round(sum(1 for x in p if x)/max(1,len(p)),4)})
    out['f32_one_offsets_be']=[i for i in range(min(len(p)-3,256)) if p[i:i+4]==b'\x3f\x80\x00\x00'][:32]
    out['f32_one_offsets_le']=[i for i in range(min(len(p)-3,256)) if p[i:i+4]==b'\x00\x00\x80\x3f'][:32]
    out['leading_zero_runs']=[{'offset':o,'size':n} for o,n in zero_runs(p[:256])[:16]]
    out['quat_probe']=scan_quats(p,32); out['vec3_probe']=scan_vec3(p,32)
    node_count=int((skel or {}).get('node_count') or 0); skin_count=int((skel or {}).get('skin_bone_count') or 0)
    out['skel_node_count']=node_count; out['skel_skin_bone_count']=skin_count; out['full_transform_candidates']=scan_full_transforms(p,32,node_count)
    out['ratio_to_nodes']=round((len(p)-64)/node_count,3) if node_count else 0; out['ratio_to_skin_bones']=round((len(p)-64)/skin_count,3) if skin_count else 0; out['status']='probe_only'
    return out
def collect(root):
    files=sorted(p for p in Path(root).rglob('*') if p.is_file()); uuid_map=build_uuid_map(files)
    skels=[parse_skel(p) for p in files if p.suffix.lower()=='.skel']; skel_by_uuid={uuid_key(x.get('uuid')):x for x in skels}
    chars=[parse_char(p,uuid_map) for p in files if p.suffix.lower()=='.char']; anim_to_skel={}; links=[]
    for ch in chars:
        sk=ch.get('skeleton_uuid','')
        for a in ch.get('animations',[]):
            anim_to_skel[uuid_key(a.get('uuid'))]=sk; links.append({'char_file':ch.get('file',''),'char_name':ch.get('name',''),'skel_uuid':sk,'skel_file':ch.get('skeleton_file',''),'anim_index':a.get('index',0),'anim_name':a.get('name',''),'anim_uuid':a.get('uuid',''),'anim_file':a.get('file','')})
    anims=[]
    for p in files:
        if p.suffix.lower()=='.anim': anims.append(parse_anim(p,skel_by_uuid.get(uuid_key(anim_to_skel.get(uuid_key(p.stem),'')),{})))
    return {'root':str(root),'files':len(files),'skels':skels,'chars':chars,'anims':anims,'links':links}
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
def summarise(data):
    anims=data['anims']; links=data['links']; skels=data['skels']; chars=data['chars']; sizes=[x.get('size',0) for x in anims]
    return {'files':data['files'],'skel_count':len(skels),'char_count':len(chars),'anim_count':len(anims),'char_anim_links':len(links),'resolved_anim_links':sum(1 for x in links if x.get('anim_file')),'resolved_skel_links':sum(1 for x in chars if x.get('skeleton_file')),'anim_inner_size_ok':sum(1 for x in anims if x.get('inner_size_ok')),'anim_magic_groups':counts(x.get('inner_magic','') for x in anims),'anim_descriptor_groups':counts((x.get('descriptor_hex','') for x in anims),20),'anim_control_groups':counts((x.get('control_u32','') for x in anims),20),'anim_size_min':min(sizes,default=0),'anim_size_max':max(sizes,default=0),'anim_size_avg':round(statistics.mean(sizes),2) if sizes else 0}
def run_tests(data):
    s=summarise(data); failures=[]
    if s['anim_count']<=0: failures.append('Keine ANIM-Dateien gefunden')
    if s['char_count']<=0: failures.append('Keine CHAR-Dateien gefunden')
    if s['skel_count']<=0: failures.append('Keine SKEL-Dateien gefunden')
    if s['anim_inner_size_ok']!=s['anim_count']: failures.append('ANIM-Innenlängen passen nicht bei allen Dateien')
    if s['resolved_anim_links']!=s['char_anim_links']: failures.append('Nicht alle CHAR-Animationen zeigen auf vorhandene ANIM-Dateien')
    bad=[a['file'] for a in data['anims'] if a.get('inner_magic')!='49170014']
    if bad: failures.append('ANIM-Magic weicht ab: '+', '.join(bad[:8]))
    return {'ok':not failures,'failures':failures,'summary':s}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('root'); ap.add_argument('-o','--out',default='anim_probe_out'); ap.add_argument('--test',action='store_true'); args=ap.parse_args()
    data=collect(args.root); out=Path(args.out); out.mkdir(parents=True,exist_ok=True); summary=summarise(data); tests=run_tests(data)
    (out/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8'); (out/'tests.json').write_text(json.dumps(tests,indent=2,ensure_ascii=False),encoding='utf-8')
    (out/'anims.json').write_text(json.dumps(data['anims'],indent=2,ensure_ascii=False),encoding='utf-8'); (out/'chars.json').write_text(json.dumps(data['chars'],indent=2,ensure_ascii=False),encoding='utf-8'); (out/'skels.json').write_text(json.dumps(data['skels'],indent=2,ensure_ascii=False),encoding='utf-8')
    write_csv(out/'char_anim_links.csv',data['links']); write_csv(out/'anim_summary.csv',[{k:v for k,v in a.items() if not isinstance(v,(dict,list))} for a in data['anims']])
    print(json.dumps(tests if args.test else summary,indent=2,ensure_ascii=False))
    if args.test and not tests['ok']: raise SystemExit(1)
if __name__=='__main__': main()
