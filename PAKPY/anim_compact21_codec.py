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
def sha1(d): return hashlib.sha1(d).hexdigest()
def s16(v): return v-65536 if v>=32768 else v
def key_to_values(raw): return [int.from_bytes(raw[i:i+2],'big') for i in range(0,8,2)]
def values_to_key(values): return b''.join(int(v&65535).to_bytes(2,'big') for v in values)
def decode_body(body):
    if len(body)!=21 or body[:4]!=bytes.fromhex('40800400') or body[-1:]!=bytes.fromhex('1c'): return None
    k0=body[4:12]; k1=body[12:20]; k0u=key_to_values(k0); k1u=key_to_values(k1); k0s=[s16(x) for x in k0u]; k1s=[s16(x) for x in k1u]
    return {'kind':'compact21','header_hex':body[:4].hex(),'tail_hex':body[-1:].hex(),'track_count_guess':1,'key_count_guess':2,'key_size_bytes':8,'keys':[{'index':0,'raw_hex':k0.hex(),'u16':k0u,'s16':k0s},{'index':1,'raw_hex':k1.hex(),'u16':k1u,'s16':k1s}],'delta_u16':[k1u[i]-k0u[i] for i in range(4)],'delta_s16':[k1s[i]-k0s[i] for i in range(4)]}
def rebuild_body(decoded):
    if not decoded or decoded.get('kind')!='compact21': return b''
    return bytes.fromhex(decoded['header_hex'])+b''.join(values_to_key(k['u16']) for k in decoded['keys'])+bytes.fromhex(decoded['tail_hex'])
def read_raw_anim(root,anim_file):
    p=Path(root)/'raw'/anim_file
    return p.read_bytes() if p.exists() else b''
def trim_body_tail(body):
    n=len(body)
    while n and body[n-1]==0: n-=1
    return body[:n],body[n:]
def decode_file(raw):
    if len(raw)<84 or raw[:4]!=b'RFRM' or tag4(raw,20)!='ANIM': return None
    head=raw[:84]; used,tail=trim_body_tail(raw[84:]); decoded=decode_body(used)
    if decoded is None: return None
    return {'head_hex':head.hex(),'tail_zero_hex':tail.hex(),'body':decoded}
def rebuild_file(decoded):
    if not decoded: return b''
    return bytes.fromhex(decoded['head_hex'])+rebuild_body(decoded['body'])+bytes.fromhex(decoded['tail_zero_hex'])
def row_from_pattern(root,row):
    anim_file=row.get('anim_file',''); raw=read_raw_anim(root,anim_file); body=bytes.fromhex(row.get('body_full_hex','')); decoded_body=decode_body(body); rebuilt_body=rebuild_body(decoded_body); decoded_file=decode_file(raw); rebuilt_file=rebuild_file(decoded_file); body_ok=body==rebuilt_body; file_ok=bool(raw) and raw==rebuilt_file
    out={'anim_name':row.get('anim_name',''),'anim_file':anim_file,'char_name':row.get('char_name',''),'skel_file':row.get('skel_file',''),'control_u32':row.get('control_u32',''),'body_hex':body.hex(),'rebuilt_body_hex':rebuilt_body.hex(),'body_lossless':body_ok,'raw_file_found':bool(raw),'raw_sha1':sha1(raw) if raw else '','rebuilt_sha1':sha1(rebuilt_file) if rebuilt_file else '','file_lossless':file_ok,'track_count_guess':decoded_body.get('track_count_guess',0) if decoded_body else 0,'key_count_guess':decoded_body.get('key_count_guess',0) if decoded_body else 0,'key_size_bytes':decoded_body.get('key_size_bytes',0) if decoded_body else 0}
    if decoded_body:
        for i,key in enumerate(decoded_body['keys']):
            out[f'key{i}_raw_hex']=key['raw_hex']; out[f'key{i}_u16_csv']=','.join(str(x) for x in key['u16']); out[f'key{i}_s16_csv']=','.join(str(x) for x in key['s16'])
        out['delta_u16_csv']=','.join(str(x) for x in decoded_body['delta_u16']); out['delta_s16_csv']=','.join(str(x) for x in decoded_body['delta_s16'])
    return out,{'anim_name':out['anim_name'],'anim_file':anim_file,'decoded':decoded_file}
def build(root):
    root=Path(root); rows=read_json(root/'anim_pattern_report'/'compact_21.json'); out_rows=[]; decoded=[]
    for row in rows:
        out,dec=row_from_pattern(root,row); out_rows.append(out); decoded.append(dec)
    summary={'compact21_count':len(out_rows),'body_lossless_count':sum(1 for x in out_rows if x.get('body_lossless')),'file_lossless_count':sum(1 for x in out_rows if x.get('file_lossless')),'raw_file_found_count':sum(1 for x in out_rows if x.get('raw_file_found')),'failed_count':sum(1 for x in out_rows if not x.get('file_lossless'))}
    return summary,out_rows,decoded
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('probe_out'); args=ap.parse_args(); root=Path(args.probe_out); summary,rows,decoded=build(root); out=root/'anim_compact21_codec'; out.mkdir(parents=True,exist_ok=True)
    write_json(out/'summary.json',summary); write_json(out/'decoded.json',decoded); write_csv(out/'lossless_check.csv',rows)
    print(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=='__main__': main()
