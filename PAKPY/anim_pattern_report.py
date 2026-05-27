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
def be32(d,o): return int.from_bytes(d[o:o+4],'big') if o+4<=len(d) else 0
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
    used=int(dec.get('body_used_size') or 0)
    return out[:used]
def get_body(root,anim_file,dec):
    b=body_from_raw(root,anim_file)
    return b if b else body_from_decode(dec)
def hexs(d): return d.hex()
def compact_21(body):
    if len(body)!=21 or not body.startswith(bytes.fromhex('40800400')): return None
    return {'compact_header_hex':body[:4].hex(),'compact_payload_hex':body[4:].hex(),'compact_a_hex':body[4:12].hex(),'compact_b_hex':body[12:20].hex(),'compact_tail_hex':body[20:21].hex()}
def row_for_decode(root,anim,dec):
    body=get_body(root,anim.get('anim_file','') or anim.get('file',''),dec); comp=compact_21(body) or {}; head4=body[:4].hex(); head8=body[:8].hex(); head16=body[:16].hex(); pre=dec.get('pre_data_hex','')
    row={'anim_file':anim.get('anim_file','') or anim.get('file',''),'anim_name':anim.get('anim_name','') or anim.get('name',''),'char_name':anim.get('char_name',''),'skel_file':anim.get('skel_file',''),'size':anim.get('size',0),'control_u32':anim.get('control_u32',''),'frame_count_guess':anim.get('frame_count_guess',0),'descriptor_hex':anim.get('descriptor_hex',''),'pre_data_hex':pre,'pre_data_last_u32':(dec.get('pre_data_words') or [{}])[-1].get('u32be',''),'body_used_size':len(body),'body_tail_zero_bytes':dec.get('body_tail_zero_bytes',0),'bytes_per_frame_guess':round(len(body)/int(anim.get('frame_count_guess') or 0),3) if str(anim.get('frame_count_guess') or '').isdigit() and int(anim.get('frame_count_guess') or 0) else 0,'body_sha1':sha_data(body),'body_head_4':head4,'body_head_8':head8,'body_head_16':head16,'body_footer_1':body[-1:].hex() if body else '','body_footer_4':body[-4:].hex() if len(body)>=4 else body.hex(),'body_full_hex':body.hex() if len(body)<=256 else body[:256].hex()}
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
    compact=[r for r in rows if r.get('compact_payload_hex')]
    class_rows=[]
    for r in rows:
        class_rows.append({'class_key':'|'.join([str(r.get('control_u32','')),str(r.get('frame_count_guess','')),str(r.get('body_used_size','')),str(r.get('body_head_4',''))]),**r})
    summary={'anim_count':len(rows),'compact_21_count':len(compact),'duplicate_full_body_groups':len(group_rows(rows,'body_sha1')),'duplicate_head_16_groups':len(group_rows(rows,'body_head_16')),'duplicate_head_8_groups':len(group_rows(rows,'body_head_8')),'body_head_4_groups':len(group_rows(rows,'body_head_4')),'class_groups':len(group_rows(class_rows,'class_key'))}
    return {'summary':summary,'rows':rows,'class_rows':class_rows,'compact_21':compact,'duplicate_full_bodies':group_rows(rows,'body_sha1'),'duplicate_head_16':group_rows(rows,'body_head_16'),'duplicate_head_8':group_rows(rows,'body_head_8'),'body_head_4_groups':group_rows(rows,'body_head_4'),'class_groups':group_rows(class_rows,'class_key')}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('probe_out'); args=ap.parse_args(); root=Path(args.probe_out)
    rep=build_report(root); out=root/'anim_pattern_report'; out.mkdir(parents=True,exist_ok=True)
    write_json(out/'summary.json',rep['summary']); write_json(out/'compact_21.json',rep['compact_21']); write_json(out/'duplicate_full_bodies.json',rep['duplicate_full_bodies']); write_json(out/'duplicate_head_16.json',rep['duplicate_head_16']); write_json(out/'duplicate_head_8.json',rep['duplicate_head_8']); write_json(out/'body_head_4_groups.json',rep['body_head_4_groups']); write_json(out/'class_groups.json',rep['class_groups'])
    write_csv(out/'anim_pattern_rows.csv',rep['rows']); write_csv(out/'compact_21.csv',rep['compact_21']); write_csv(out/'class_rows.csv',rep['class_rows'])
    print(json.dumps(rep['summary'],indent=2,ensure_ascii=False))
if __name__=='__main__': main()
