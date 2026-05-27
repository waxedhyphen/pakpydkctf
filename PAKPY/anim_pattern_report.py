from pathlib import Path
import argparse,csv,hashlib,json

def read_json(path): return json.loads(Path(path).read_text(encoding='utf-8'))
def write_json(path,data): Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
def write_csv(path,rows):
    if not rows: return
    keys=[]
    for row in rows:
        for k in row:
            if k not in keys: keys.append(k)
    with Path(path).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(rows)
def tag4(d,o): return d[o:o+4].decode('ascii','replace') if o+4<=len(d) else ''
def sha_data(d): return hashlib.sha1(d).hexdigest() if d else ''
def body_from_raw(root,anim_file):
    p=Path(root)/'raw'/anim_file
    if not p.exists(): return b''
    d=p.read_bytes()
    if len(d)<84 or d[:4]!=b'RFRM' or tag4(d,20)!='ANIM': return b''
    body=d[84:]
    while body and body[-1]==0: body=body[:-1]
    return body
def body_from_decode(dec):
    out=b''
    for w in dec.get('body_prefix_words') or []:
        try: out+=bytes.fromhex(w.get('hex',''))
        except Exception: pass
    return out[:int(dec.get('body_used_size') or 0)]
def get_body(root,anim_file,dec):
    b=body_from_raw(root,anim_file)
    return b if b else body_from_decode(dec)
def compact_21(body):
    if len(body)!=21 or not body.startswith(bytes.fromhex('40800400')): return None
    return {'compact_header_hex':body[:4].hex(),'compact_payload_hex':body[4:].hex(),'compact_a_hex':body[4:12].hex(),'compact_b_hex':body[12:20].hex(),'compact_tail_hex':body[20:21].hex()}
def s16(x): return x-65536 if x>=32768 else x
def u16(b): return int.from_bytes(b,'big')
def split_key(b):
    return {'hex':b.hex(),'u16_0':u16(b[0:2]),'u16_1':u16(b[2:4]),'u16_2':u16(b[4:6]),'u16_3':u16(b[6:8]),'s16_0':s16(u16(b[0:2])),'s16_1':s16(u16(b[2:4])),'s16_2':s16(u16(b[4:6])),'s16_3':s16(u16(b[6:8])),'u32_0':int.from_bytes(b[0:4],'big'),'u32_1':int.from_bytes(b[4:8],'big')}
def compact_key_row(row):
    if not row.get('compact_a_hex') or not row.get('compact_b_hex'): return None
    a=bytes.fromhex(row['compact_a_hex']); b=bytes.fromhex(row['compact_b_hex']); k0=split_key(a); k1=split_key(b); bd=[b[i]-a[i] for i in range(8)]; bd_wrap=[(b[i]-a[i])&255 for i in range(8)]; out=dict(row)
    out.update({'track_count_guess':1,'key_count_guess':2,'key_size_bytes':8,'key0_hex':a.hex(),'key1_hex':b.hex(),'key_delta_hex':bytes(bd_wrap).hex(),'key_delta_signed_csv':','.join(str(x) for x in bd),'key0_u64':int.from_bytes(a,'big'),'key1_u64':int.from_bytes(b,'big'),'key_delta_u64':int.from_bytes(b,'big')-int.from_bytes(a,'big'),'key0_u32a':k0['u32_0'],'key0_u32b':k0['u32_1'],'key1_u32a':k1['u32_0'],'key1_u32b':k1['u32_1'],'key_delta_u32a':k1['u32_0']-k0['u32_0'],'key_delta_u32b':k1['u32_1']-k0['u32_1'],'key0_u16_csv':f"{k0['u16_0']},{k0['u16_1']},{k0['u16_2']},{k0['u16_3']}",'key1_u16_csv':f"{k1['u16_0']},{k1['u16_1']},{k1['u16_2']},{k1['u16_3']}",'key_delta_u16_csv':f"{k1['u16_0']-k0['u16_0']},{k1['u16_1']-k0['u16_1']},{k1['u16_2']-k0['u16_2']},{k1['u16_3']-k0['u16_3']}"})
    for i in range(4):
        out[f'key0_s16_{i}']=k0[f's16_{i}']; out[f'key1_s16_{i}']=k1[f's16_{i}']; out[f'delta_s16_{i}']=k1[f's16_{i}']-k0[f's16_{i}']
        out[f'key0_u16_{i}']=k0[f'u16_{i}']; out[f'key1_u16_{i}']=k1[f'u16_{i}']; out[f'delta_u16_{i}']=k1[f'u16_{i}']-k0[f'u16_{i}']
    return out
def row_for_decode(root,anim,dec):
    body=get_body(root,anim.get('anim_file','') or anim.get('file',''),dec); comp=compact_21(body) or {}; pre=dec.get('pre_data_hex','')
    row={'anim_file':anim.get('anim_file','') or anim.get('file',''),'anim_name':anim.get('anim_name','') or anim.get('name',''),'char_name':anim.get('char_name',''),'skel_file':anim.get('skel_file',''),'size':anim.get('size',0),'control_u32':anim.get('control_u32',''),'frame_count_guess':anim.get('frame_count_guess',0),'descriptor_hex':anim.get('descriptor_hex',''),'pre_data_hex':pre,'pre_data_last_u32':(dec.get('pre_data_words') or [{}])[-1].get('u32be',''),'body_used_size':len(body),'body_tail_zero_bytes':dec.get('body_tail_zero_bytes',0),'bytes_per_frame_guess':round(len(body)/int(anim.get('frame_count_guess') or 0),3) if str(anim.get('frame_count_guess') or '').isdigit() and int(anim.get('frame_count_guess') or 0) else 0,'body_sha1':sha_data(body),'body_head_4':body[:4].hex(),'body_head_8':body[:8].hex(),'body_head_16':body[:16].hex(),'body_footer_1':body[-1:].hex() if body else '','body_footer_4':body[-4:].hex() if len(body)>=4 else body.hex(),'body_full_hex':body.hex() if len(body)<=256 else body[:256].hex()}
    row.update(comp)
    return row
def group_rows(rows,key,min_count=2):
    groups={}
    for row in rows:
        v=row.get(key,'')
        groups.setdefault(v,[]).append(row)
    out=[]
    for k,items in groups.items():
        if not k or len(items)<min_count: continue
        out.append({'key':k,'count':len(items),'sizes':sorted(set(str(x.get('size','')) for x in items)),'controls':sorted(set(str(x.get('control_u32','')) for x in items)),'frames':sorted(set(str(x.get('frame_count_guess','')) for x in items)),'names':[x.get('anim_name','') for x in items[:24]],'files':[x.get('anim_file','') for x in items[:24]]})
    out.sort(key=lambda x:(-x['count'],x['key']))
    return out
def compact_groups(rows):
    groups={}
    for row in rows:
        key='|'.join([str(row.get('control_u32','')),str(row.get('compact_header_hex','')),str(row.get('compact_tail_hex','')),str(row.get('track_count_guess','')),str(row.get('key_count_guess','')),str(row.get('key_size_bytes',''))])
        groups.setdefault(key,[]).append(row)
    out=[]
    for k,items in groups.items():
        out.append({'group_key':k,'count':len(items),'names':[x.get('anim_name','') for x in items],'delta_u32a_values':sorted(set(str(x.get('key_delta_u32a','')) for x in items)),'delta_u32b_values':sorted(set(str(x.get('key_delta_u32b','')) for x in items)),'delta_s16_1_values':sorted(set(str(x.get('delta_s16_1','')) for x in items)),'delta_s16_2_values':sorted(set(str(x.get('delta_s16_2','')) for x in items)),'delta_s16_3_values':sorted(set(str(x.get('delta_s16_3','')) for x in items))})
    out.sort(key=lambda x:(-x['count'],x['group_key']))
    return out
def load_links(root):
    p=Path(root)/'char_anim_links.csv'
    if not p.exists(): return {}
    with p.open(newline='',encoding='utf-8') as f:
        return {r.get('anim_file',''):r for r in csv.DictReader(f)}
def build_report(root):
    root=Path(root); anims=read_json(root/'anims.json'); links=load_links(root); rows=[]
    for anim in anims:
        p=root/'anim_decode'/(anim.get('uuid_hex','')+'.json')
        if not p.exists(): continue
        dec=read_json(p); merged=dict(anim); merged.update(links.get(anim.get('file',''),{})); rows.append(row_for_decode(root,merged,dec))
    compact=[r for r in rows if r.get('compact_payload_hex')]; compact_keys=[x for x in (compact_key_row(r) for r in compact) if x]
    class_rows=[]
    for r in rows:
        class_rows.append({'class_key':'|'.join([str(r.get('control_u32','')),str(r.get('frame_count_guess','')),str(r.get('body_used_size','')),str(r.get('body_head_4',''))]),**r})
    summary={'anim_count':len(rows),'compact_21_count':len(compact),'compact_key_rows':len(compact_keys),'duplicate_full_body_groups':len(group_rows(rows,'body_sha1')),'duplicate_head_16_groups':len(group_rows(rows,'body_head_16')),'duplicate_head_8_groups':len(group_rows(rows,'body_head_8')),'body_head_4_groups':len(group_rows(rows,'body_head_4')),'class_groups':len(group_rows(class_rows,'class_key')),'compact_groups':len(compact_groups(compact_keys))}
    return {'summary':summary,'rows':rows,'class_rows':class_rows,'compact_21':compact,'compact_21_keys':compact_keys,'compact_21_groups':compact_groups(compact_keys),'duplicate_full_bodies':group_rows(rows,'body_sha1'),'duplicate_head_16':group_rows(rows,'body_head_16'),'duplicate_head_8':group_rows(rows,'body_head_8'),'body_head_4_groups':group_rows(rows,'body_head_4'),'class_groups':group_rows(class_rows,'class_key')}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('probe_out'); args=ap.parse_args(); root=Path(args.probe_out)
    rep=build_report(root); out=root/'anim_pattern_report'; out.mkdir(parents=True,exist_ok=True)
    write_json(out/'summary.json',rep['summary']); write_json(out/'compact_21.json',rep['compact_21']); write_json(out/'compact_21_keys.json',rep['compact_21_keys']); write_json(out/'compact_21_groups.json',rep['compact_21_groups']); write_json(out/'duplicate_full_bodies.json',rep['duplicate_full_bodies']); write_json(out/'duplicate_head_16.json',rep['duplicate_head_16']); write_json(out/'duplicate_head_8.json',rep['duplicate_head_8']); write_json(out/'body_head_4_groups.json',rep['body_head_4_groups']); write_json(out/'class_groups.json',rep['class_groups'])
    write_csv(out/'anim_pattern_rows.csv',rep['rows']); write_csv(out/'compact_21.csv',rep['compact_21']); write_csv(out/'compact_21_keys.csv',rep['compact_21_keys']); write_csv(out/'compact_21_groups.csv',rep['compact_21_groups']); write_csv(out/'class_rows.csv',rep['class_rows'])
    print(json.dumps(rep['summary'],indent=2,ensure_ascii=False))
if __name__=='__main__': main()
