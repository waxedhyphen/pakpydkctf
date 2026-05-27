from pathlib import Path
import argparse,csv,json

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
def s8(x): return x-256 if x>=128 else x
def s16(x): return x-65536 if x>=32768 else x
def u16(b): return int.from_bytes(b,'big')
def split_key(b):
    return {'hex':b.hex(),'u16_0':u16(b[0:2]),'u16_1':u16(b[2:4]),'u16_2':u16(b[4:6]),'u16_3':u16(b[6:8]),'s16_0':s16(u16(b[0:2])),'s16_1':s16(u16(b[2:4])),'s16_2':s16(u16(b[4:6])),'s16_3':s16(u16(b[6:8])),'u32_0':int.from_bytes(b[0:4],'big'),'u32_1':int.from_bytes(b[4:8],'big')}
def row_to_decode(row):
    a=bytes.fromhex(row['compact_a_hex']); b=bytes.fromhex(row['compact_b_hex']); k0=split_key(a); k1=split_key(b); bd=[b[i]-a[i] for i in range(8)]; bd_wrap=[(b[i]-a[i])&255 for i in range(8)]
    out={'anim_name':row.get('anim_name',''),'anim_file':row.get('anim_file',''),'char_name':row.get('char_name',''),'skel_file':row.get('skel_file',''),'control_u32':row.get('control_u32',''),'frame_count_guess':row.get('frame_count_guess',0),'track_count_guess':1,'key_count_guess':2,'key_size_bytes':8,'body_header_hex':row.get('compact_header_hex',''),'tail_hex':row.get('compact_tail_hex',''),'key0_hex':k0['hex'],'key1_hex':k1['hex'],'byte_delta_signed':','.join(str(x) for x in bd),'byte_delta_wrapped_hex':bytes(bd_wrap).hex()}
    for i in range(4):
        out[f'key0_s16_{i}']=k0[f's16_{i}']; out[f'key1_s16_{i}']=k1[f's16_{i}']; out[f'delta_s16_{i}']=k1[f's16_{i}']-k0[f's16_{i}']
        out[f'key0_u16_{i}']=k0[f'u16_{i}']; out[f'key1_u16_{i}']=k1[f'u16_{i}']; out[f'delta_u16_{i}']=k1[f'u16_{i}']-k0[f'u16_{i}']
    out['key0_u32_0']=k0['u32_0']; out['key0_u32_1']=k0['u32_1']; out['key1_u32_0']=k1['u32_0']; out['key1_u32_1']=k1['u32_1']; out['delta_u32_0']=k1['u32_0']-k0['u32_0']; out['delta_u32_1']=k1['u32_1']-k0['u32_1']
    return out
def build(root):
    root=Path(root); src=root/'anim_pattern_report'/'compact_21_keys.json'
    rows=read_json(src)
    dec=[row_to_decode(r) for r in rows]
    groups={}
    for r in dec:
        key='|'.join([str(r['control_u32']),str(r['body_header_hex']),str(r['tail_hex']),str(r['track_count_guess']),str(r['key_count_guess']),str(r['key_size_bytes'])])
        groups.setdefault(key,[]).append(r)
    group_rows=[]
    for k,items in groups.items():
        group_rows.append({'group_key':k,'count':len(items),'names':[x['anim_name'] for x in items],'delta_u32_0_values':sorted(set(str(x['delta_u32_0']) for x in items)),'delta_u32_1_values':sorted(set(str(x['delta_u32_1']) for x in items)),'delta_s16_1_values':sorted(set(str(x['delta_s16_1']) for x in items)),'delta_s16_2_values':sorted(set(str(x['delta_s16_2']) for x in items)),'delta_s16_3_values':sorted(set(str(x['delta_s16_3']) for x in items))})
    return {'summary':{'compact_21_rows':len(dec),'groups':len(group_rows)},'rows':dec,'groups':group_rows}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('probe_out'); args=ap.parse_args(); root=Path(args.probe_out); rep=build(root); out=root/'anim_compact21_decode'; out.mkdir(parents=True,exist_ok=True)
    write_json(out/'summary.json',rep['summary']); write_json(out/'compact21_decode.json',rep['rows']); write_json(out/'compact21_groups.json',rep['groups']); write_csv(out/'compact21_decode.csv',rep['rows']); write_csv(out/'compact21_groups.csv',rep['groups'])
    print(json.dumps(rep['summary'],indent=2,ensure_ascii=False))
if __name__=='__main__': main()
