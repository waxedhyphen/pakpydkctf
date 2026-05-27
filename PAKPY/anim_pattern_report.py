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
def sha_hex(h): return hashlib.sha1(bytes.fromhex(h)).hexdigest() if h else ''
def body_hex_from_decode(dec):
    words=dec.get('body_prefix_words') or []
    out=''
    for w in words: out+=w.get('hex','')
    used=int(dec.get('body_used_size') or 0)*2
    return out[:used]
def compact_two_frame(dec):
    body=body_hex_from_decode(dec)
    if len(body)!=42: return None
    if not body.startswith('40800400') or not body.endswith('1c'): return None
    return {'header_hex':body[:8],'key0_hex':body[8:24],'key1_hex':body[24:40],'footer_hex':body[40:42]}
def row_for_decode(anim,dec):
    body=body_hex_from_decode(dec); compact=compact_two_frame(dec) or {}
    return {'anim_file':anim.get('file',''),'anim_name':anim.get('name',''),'char_name':anim.get('char_name',''),'skel_file':anim.get('skel_file',''),'size':anim.get('size',0),'control_u32':anim.get('control_u32',''),'frame_count_guess':anim.get('frame_count_guess',0),'descriptor_hex':anim.get('descriptor_hex',''),'pre_data_hex':dec.get('pre_data_hex',''),'pre_data_last_u32':(dec.get('pre_data_words') or [{}])[-1].get('u32be',''),'body_used_size':dec.get('body_used_size',0),'body_tail_zero_bytes':dec.get('body_tail_zero_bytes',0),'bytes_per_frame_guess':dec.get('bytes_per_frame_guess',0),'body_sha1':sha_hex(body),'body_head_4':body[:8],'body_head_8':body[:16],'body_footer_1':body[-2:] if body else '','compact_header_hex':compact.get('header_hex',''),'compact_key0_hex':compact.get('key0_hex',''),'compact_key1_hex':compact.get('key1_hex',''),'compact_footer_hex':compact.get('footer_hex','')}
def group_rows(rows,key):
    groups={}
    for row in rows:
        v=row.get(key,'')
        groups.setdefault(v,[]).append(row)
    out=[]
    for k,items in groups.items():
        if not k or len(items)<2: continue
        out.append({'key':k,'count':len(items),'sizes':sorted(set(str(x.get('size','')) for x in items)),'controls':sorted(set(str(x.get('control_u32','')) for x in items)),'names':[x.get('anim_name','') for x in items[:24]],'files':[x.get('anim_file','') for x in items[:24]]})
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
        dec=read_json(p); merged=dict(anim); merged.update(links.get(anim.get('file',''),{})); rows.append(row_for_decode(merged,dec))
    compact=[r for r in rows if r.get('compact_key0_hex')]
    summary={'anim_count':len(rows),'compact_two_frame_count':len(compact),'duplicate_body_groups':len(group_rows(rows,'body_sha1')),'duplicate_prefix_groups':len(group_rows(rows,'body_head_8')),'body_head_4_groups':len(group_rows(rows,'body_head_4'))}
    return {'summary':summary,'rows':rows,'compact_two_frame':compact,'duplicate_bodies':group_rows(rows,'body_sha1'),'duplicate_prefixes':group_rows(rows,'body_head_8'),'body_head_4_groups':group_rows(rows,'body_head_4')}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('probe_out'); args=ap.parse_args(); root=Path(args.probe_out)
    rep=build_report(root); out=root/'anim_pattern_report'; out.mkdir(parents=True,exist_ok=True)
    write_json(out/'summary.json',rep['summary']); write_json(out/'compact_two_frame.json',rep['compact_two_frame']); write_json(out/'duplicate_bodies.json',rep['duplicate_bodies']); write_json(out/'duplicate_prefixes.json',rep['duplicate_prefixes']); write_json(out/'body_head_4_groups.json',rep['body_head_4_groups'])
    write_csv(out/'anim_pattern_rows.csv',rep['rows']); write_csv(out/'compact_two_frame.csv',rep['compact_two_frame'])
    print(json.dumps(rep['summary'],indent=2,ensure_ascii=False))
if __name__=='__main__': main()
