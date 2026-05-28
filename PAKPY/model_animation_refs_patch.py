from pathlib import Path
import json
import math
import struct
import gui as gui_module
import model_package
import char_codec
import char_gui_patch
import char_skeletal_package_patch
from pak_core import PakError,get_entry_asset,safe_name,kind_to_ext,sha1_bytes,format_uuid_hex

ZERO_UUID='00000000000000000000000000000000'

def be32(data,off):
    return int.from_bytes(data[off:off+4],'big')

def tag4(data,off):
    return data[off:off+4].decode('ascii','replace')

def _signed16(value):
    return value-0x10000 if value>=0x8000 else value

def _float_or_none(data,off,endian):
    if off+4>len(data):
        return None
    try:
        value=struct.unpack_from(('>' if endian=='be' else '<')+'f',data,off)[0]
    except Exception:
        return None
    if not math.isfinite(value) or abs(value)>1000000:
        return None
    return value

def _format_float(value):
    if value is None:
        return None
    if abs(float(value))<0.00000001:
        value=0.0
    return round(float(value),6)

def _word_probe(data,base_off,file_base_off,limit=8):
    out=[]
    count=min(limit,max(0,(len(data)-base_off)//4))
    for index in range(count):
        off=base_off+index*4
        raw=data[off:off+4]
        item={'offset':off,'file_offset':file_base_off+off,'hex':raw.hex(),'u32be':int.from_bytes(raw,'big'),'u32le':int.from_bytes(raw,'little')}
        fbe=_float_or_none(data,off,'be')
        fle=_float_or_none(data,off,'le')
        if fbe is not None:
            item['f32be']=_format_float(fbe)
        if fle is not None:
            item['f32le']=_format_float(fle)
        out.append(item)
    return out

def parse_anim_probe21(asset):
    if len(asset)<40 or asset[:4]!=b'RFRM' or tag4(asset,20)!='ANIM':
        raise PakError('Keine ANIM-Ressource')
    payload=asset[32:]
    if len(payload)<32:
        raise PakError('ANIM-Payload ist zu klein')
    magic=payload[:4].hex()
    inner_size=be32(payload,4)
    control=be32(payload,8)
    descriptor=payload[16:32]
    data_offset=52 if len(payload)>=52 else len(payload)
    body=payload[data_offset:]
    body_used=body.rstrip(b'\x00')
    probe={'type':'ANIM','size':len(asset),'sha1':sha1_bytes(asset),'format_magic':magic,'inner_size':inner_size,'inner_size_ok':inner_size+8==len(payload),'control_u32':f'0x{control:08X}','control_class':(control>>24)&255,'control_flags':(control>>16)&255,'control_mid':(control>>8)&255,'control_low8':control&255,'control_low16':control&65535,'frame_count_guess':control&255,'group_hash':payload[12:16].hex(),'descriptor_hex':descriptor.hex(),'descriptor_head':list(descriptor[:8]),'descriptor_tail':descriptor[8:].hex(),'pre_data_hex':payload[32:data_offset].hex(),'pre_data_words':_word_probe(payload,32,32),'data_offset':data_offset,'file_data_offset':32+data_offset,'body_size':len(body),'body_used_size':len(body_used),'body_tail_zero_bytes':len(body)-len(body_used),'body_prefix_words':_word_probe(payload,data_offset,32,12)}
    if len(body_used)==21:
        keys=[]
        key_blob=body_used[4:20]
        for index in range(2):
            raw=key_blob[index*8:index*8+8]
            vals=[int.from_bytes(raw[i:i+2],'big') for i in range(0,8,2)]
            keys.append({'index':index,'raw_hex':raw.hex(),'u16':vals,'s16':[_signed16(v) for v in vals]})
        delta_u16=[]
        delta_s16=[]
        if len(keys)==2:
            delta_u16=[keys[1]['u16'][i]-keys[0]['u16'][i] for i in range(4)]
            delta_s16=[keys[1]['s16'][i]-keys[0]['s16'][i] for i in range(4)]
        probe['body']={'kind':'compact21','header_hex':body_used[:4].hex(),'tail_hex':body_used[20:].hex(),'track_count_guess':1,'key_count_guess':2,'key_size_bytes':8,'keys':keys,'delta_u16':delta_u16,'delta_s16':delta_s16}
    else:
        probe['body']={'kind':'raw','prefix_hex':body_used[:96].hex(),'tail_hex':body_used[-32:].hex() if body_used else ''}
    return probe

def _entry_name(entry):
    if not entry:
        return ''
    return entry.get('display_name') or entry.get('name') or entry.get('uuid_hex','')

def _rel(root,path):
    return str(Path(path).relative_to(root)).replace('\\','/')

def _unique_path(path):
    path=Path(path)
    if not path.exists():
        return path
    suffix=''.join(path.suffixes)
    stem=path.name[:-len(suffix)] if suffix else path.name
    number=2
    while True:
        candidate=path.with_name(f'{stem}_{number}{suffix}')
        if not candidate.exists():
            return candidate
        number+=1

def _resolve_anim_asset(parsed,uuid_hex,require_store=None):
    return char_codec._resolve_ref(parsed,uuid_hex,require_store)

def _collect_char_animation_refs(parsed,entry,require_store=None):
    refs=[]
    if entry is None or entry.get('type')!='CHAR':
        return refs
    try:
        info=char_codec.parse_char_asset(get_entry_asset(parsed,entry))
    except Exception:
        return refs
    for anim in info.get('animations',[]):
        uuid_hex=(anim.get('uuid_hex') or '').replace('-','').lower()
        if not uuid_hex or uuid_hex==ZERO_UUID:
            continue
        asset,anim_entry,source,source_path=_resolve_anim_asset(parsed,uuid_hex,require_store)
        item=dict(anim)
        item.update({'uuid_hex':uuid_hex,'type':'ANIM','resolved':asset is not None and anim_entry is not None,'entry_type':anim_entry.get('type') if anim_entry else '', 'entry_name':_entry_name(anim_entry),'source_kind':source,'source_path':source_path})
        refs.append(item)
    refs.sort(key=lambda ref:((ref.get('name') or '').upper(),ref.get('uuid_hex','')))
    for index,ref in enumerate(refs):
        ref['tree_index']=index
    return refs

def _anim_ref_label(ref,anim_entry=None):
    name=ref.get('name') or _entry_name(anim_entry)
    size=f' | Größe {anim_entry.get("size",0)}' if anim_entry is not None else ''
    index=ref.get('index')
    index_text=f'#{index} ' if isinstance(index,int) else ''
    if name:
        return f'  ANIM | {index_text}{name} | {format_uuid_hex(ref["uuid_hex"])}{size}'
    return f'  ANIM | {index_text}{format_uuid_hex(ref["uuid_hex"])}{size}'

def _anim_summary_lines(ref,anim_entry,asset,source,source_path):
    lines=[]
    lines.append(f'CHAR-Animationsslot: #{ref.get("index","")}')
    if ref.get('name'):
        lines.append(f'CHAR-Animationsname: {ref["name"]}')
    lines.append(f'ANIM-UUID: {format_uuid_hex(ref["uuid_hex"])}')
    if ref.get('extra_hex'):
        lines.append(f'CHAR-Extra: {ref["extra_hex"]}')
    if anim_entry is not None:
        lines.append(f'ANIM-Eintrag: #{anim_entry.get("index",-1)}')
        lines.append(f'ANIM-Name: {_entry_name(anim_entry)}')
        lines.append(f'ANIM-Größe: {anim_entry.get("size",len(asset) if asset else 0)}')
    if source:
        lines.append(f'Quelle: {"Aktuelles PAK" if source=="pak" else "Require"}')
    if source_path:
        lines.append(f'Quellpfad: {source_path}')
    if asset is not None:
        try:
            probe=parse_anim_probe21(asset)
            lines.append(f'Format-Magic: {probe["format_magic"]}')
            lines.append(f'Control: {probe["control_u32"]}')
            lines.append(f'Frame-Guess: {probe["frame_count_guess"]}')
            lines.append(f'Descriptor: {probe["descriptor_hex"]}')
            lines.append(f'Body-Typ: {probe["body"].get("kind","")}')
            if probe['body'].get('kind')=='compact21':
                lines.append(f'Compact21 Keys: {probe["body"].get("key_count_guess",0)}')
                for key in probe['body'].get('keys',[]):
                    lines.append(f'- Key {key["index"]}: {key["raw_hex"]} | s16 {key["s16"]}')
                lines.append(f'Delta s16: {probe["body"].get("delta_s16",[])}')
            lines.append(f'Asset-SHA1: {probe["sha1"]}')
        except Exception as e:
            lines.append(f'ANIM-Probe Fehler: {e}')
    return lines

def _write_animation_probe_set(parsed,entry,package_dir,refs,require_store=None,root_name='char'):
    package_dir=Path(package_dir)
    probe_dir=package_dir/'debug'/'anim_probe21'
    probe_dir.mkdir(parents=True,exist_ok=True)
    out=[]
    compact21_count=0
    resolved_count=0
    for ref in refs:
        uuid_hex=ref.get('uuid_hex','')
        asset,anim_entry,source,source_path=_resolve_anim_asset(parsed,uuid_hex,require_store)
        item=dict(ref)
        item.update({'resolved':asset is not None and anim_entry is not None,'entry_type':anim_entry.get('type') if anim_entry else '', 'entry_name':_entry_name(anim_entry) if anim_entry else '', 'source_kind':source,'source_path':source_path,'probe21_file':'','probe21_kind':'','probe21_error':''})
        if asset is not None and anim_entry is not None:
            resolved_count+=1
            base=safe_name(f'{item.get("index",len(out)):03d}__{item.get("name") or item["entry_name"] or "anim"}__{uuid_hex}')
            probe_path=_unique_path(probe_dir/(base+'.probe21.json'))
            try:
                probe=parse_anim_probe21(asset)
                probe.update({'uuid_hex':uuid_hex,'entry_name':item['entry_name'],'char_animation_name':item.get('name',''),'char_animation_index':item.get('index',-1),'source_kind':source,'source_path':source_path})
                item['probe21_kind']=probe.get('body',{}).get('kind','')
                if item['probe21_kind']=='compact21':
                    compact21_count+=1
                probe_path.write_text(json.dumps(probe,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
            except Exception as e:
                item['probe21_error']=str(e)
                probe_path.write_text(json.dumps({'error':str(e),'uuid_hex':uuid_hex,'char_animation_name':item.get('name',''),'char_animation_index':item.get('index',-1)},indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
            item['probe21_file']=_rel(package_dir,probe_path)
        out.append(item)
    summary={'source_kind':root_name,'char_uuid_hex':entry.get('uuid_hex',''),'char_name':_entry_name(entry),'animation_count':len(out),'resolved_animation_count':resolved_count,'compact21_count':compact21_count,'animations':out}
    summary_path=package_dir/'debug'/'anim_probe21_summary.json'
    summary_path.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
    return {'summary':summary,'summary_file':_rel(package_dir,summary_path),'animations':out,'animation_count':len(out),'resolved_animation_count':resolved_count,'compact21_count':compact21_count}

def _install_gui_patch(App):
    original_refresh=App.refresh_list
    original_payload=App.build_payload_export
    original_whole=App.build_whole_export
    original_show=App.show_selected
    def get_char_animation_refs(self,entry):
        cache_key='_char_animation_refs'
        cache_req_key='_char_animation_refs_require_id'
        req_id=id(self.require_store)
        if entry.get(cache_key) is None or entry.get(cache_req_key)!=req_id:
            entry[cache_key]=_collect_char_animation_refs(self.parsed,entry,self.require_store)
            entry[cache_req_key]=req_id
        return list(entry.get(cache_key) or [])
    def anim_ref_matches(self,ref,query,mode):
        if mode=='missing':
            asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,ref['uuid_hex'],self.require_store)
            return anim_entry is None or asset is None
        if not query:
            return True
        if mode=='size':
            asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,ref['uuid_hex'],self.require_store)
            if anim_entry is None:
                return False
            return self.size_matches(query,anim_entry.get('size',0))
        if mode=='type':
            return query in 'ANIM'
        text=' '.join(str(x or '') for x in (ref.get('name',''),ref.get('uuid_hex',''),ref.get('source_kind',''),'ANIM')).upper()
        return query in text
    def sort_tree_children_by_type(self,parent_iid):
        children=list(self.tree.get_children(parent_iid))
        if not children:
            return
        def item_key(iid):
            item=self.tree_items.get(iid)
            text=self.tree.item(iid,'text') or ''
            typ=''
            if item is not None:
                kind=item.get('kind')
                if kind=='entry':
                    typ=item['entry'].get('type','')
                elif kind=='bundle_child':
                    typ=item['child'].get('inner_kind','')
                elif kind=='caud_child':
                    typ='CAUD'
                elif kind=='char_anim_child':
                    typ='ANIM'
                elif kind=='model_mtrl_child':
                    typ='MTRL'
                elif kind=='model_txtr_child':
                    typ='TXTR'
            return (typ.upper(),text.upper(),iid)
        ordered=sorted(children,key=item_key)
        if ordered!=children:
            for index,iid in enumerate(ordered):
                self.tree.move(iid,parent_iid,index)
        for iid in ordered:
            sort_tree_children_by_type(self,iid)
    def add_char_animation_children(self):
        query=self.filter_var.get().strip().upper()
        mode=self.filter_mode_var.get()
        for entry in self.parsed.get('entries',[]):
            if entry.get('type')!='CHAR':
                continue
            refs=get_char_animation_refs(self,entry)
            if not refs:
                continue
            entry_iid=f'entry_{entry["index"]}'
            if not self.tree.exists(entry_iid):
                if not query:
                    continue
                refs_match=[ref for ref in refs if anim_ref_matches(self,ref,query,mode)]
                if not refs_match:
                    continue
                parent=''
                if mode=='type':
                    group_iid='group_CHAR'
                    if not self.tree.exists(group_iid):
                        self.tree.insert('', 'end', iid=group_iid, text=f'{self.type_group_label("CHAR")} (1)', open=True)
                    parent=group_iid
                self.tree.insert(parent,'end',iid=entry_iid,text=gui_module.make_entry_label(entry),open=True)
                self.tree_items[entry_iid]={'kind':'entry','entry':entry}
                refs_to_show=refs_match
            else:
                if query:
                    entry_match=self.entry_matches(entry,query,mode)
                    refs_to_show=refs if entry_match and mode!='missing' else [ref for ref in refs if anim_ref_matches(self,ref,query,mode)]
                else:
                    refs_to_show=refs
            for ref in refs_to_show:
                iid=f'entry_{entry["index"]}_char_anim_{ref.get("index",ref.get("tree_index",0))}_{ref["uuid_hex"]}'
                if self.tree.exists(iid):
                    continue
                asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,ref['uuid_hex'],self.require_store)
                tags=()
                if anim_entry is None or asset is None:
                    tags=('missing_ref',)
                elif source=='require':
                    tags=('required_ref',)
                self.tree.insert(entry_iid,'end',iid=iid,text=_anim_ref_label(ref,anim_entry),tags=tags)
                self.tree_items[iid]={'kind':'char_anim_child','entry':entry,'ref':ref,'anim_entry':anim_entry}
    def patched_refresh_list(self):
        original_refresh(self)
        if self.parsed is None:
            return
        add_char_animation_children(self)
        sort_tree_children_by_type(self,'')
    def patched_payload(self,item):
        if item.get('kind')=='char_anim_child':
            asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,item['ref']['uuid_hex'],self.require_store)
            if anim_entry is None or asset is None:
                raise PakError('Verlinktes ANIM ist weder im aktuellen PAK noch in den requireten Dateien vorhanden')
            base=safe_name(item['ref'].get('name') or _entry_name(anim_entry) or item['ref']['uuid_hex'])
            return base+kind_to_ext(anim_entry.get('type') or 'ANIM'),asset
        return original_payload(self,item)
    def patched_whole(self,item):
        if item.get('kind')=='char_anim_child':
            asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,item['ref']['uuid_hex'],self.require_store)
            if anim_entry is None or asset is None:
                raise PakError('Verlinktes ANIM ist weder im aktuellen PAK noch in den requireten Dateien vorhanden')
            base=safe_name(item['ref'].get('name') or _entry_name(anim_entry) or item['ref']['uuid_hex'])
            return base+'.anim.bin',asset
        return original_whole(self,item)
    def patched_show(self,event=None):
        iid=self.get_display_iid()
        item=self.tree_items.get(iid) if iid else None
        if item is None or item.get('kind')!='char_anim_child':
            return original_show(self,event)
        self.preview.clear()
        self.txtr_preview.clear()
        entry=item['entry']
        ref=item['ref']
        asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,ref['uuid_hex'],self.require_store)
        lines=[]
        lines.append(f'Übergeordneter CHAR: #{entry["index"]} CHAR')
        lines.append(f'CHAR-Name: {self.entry_display_name(entry)}')
        lines.append(f'CHAR-UUID: {entry["uuid_hex"]}')
        lines.append('')
        if asset is None or anim_entry is None:
            lines.append('Status: Missing')
            lines.append(f'ANIM-UUID: {format_uuid_hex(ref["uuid_hex"])}')
        else:
            lines.extend(_anim_summary_lines(ref,anim_entry,asset,source,source_path))
        self.output.delete('1.0','end')
        self.output.insert('1.0','\n'.join(lines))
    App.get_char_animation_refs=get_char_animation_refs
    App.anim_ref_matches=anim_ref_matches
    App.refresh_list=patched_refresh_list
    App.build_payload_export=patched_payload
    App.build_whole_export=patched_whole
    App.show_selected=patched_show

def _install_model_package_patch():
    original=model_package.export_model_package
    def patched_export_model_package(parsed,entry,out_dir,require_store=None,animation_refs=None,skeleton_refs=None):
        refs=[]
        if animation_refs:
            for ref in animation_refs:
                uuid_hex=(ref.get('uuid_hex') or '').replace('-','').lower()
                if len(uuid_hex)==32 and uuid_hex!=ZERO_UUID:
                    item=dict(ref)
                    item['uuid_hex']=uuid_hex
                    item['type']='ANIM'
                    refs.append(item)
        try:
            result=original(parsed,entry,out_dir,require_store=require_store,animation_refs=animation_refs,skeleton_refs=skeleton_refs)
        except TypeError:
            result=original(parsed,entry,out_dir,require_store=require_store,animation_refs=animation_refs)
        if 'obj_path' not in result and 'obj' in result:
            result['obj_path']=result['obj']
        if 'mtl_path' not in result and 'mtl' in result:
            result['mtl_path']=result['mtl']
        if refs:
            try:
                package_dir=Path(result['package_dir'])
                anim_result=_write_animation_probe_set(parsed,entry,package_dir,refs,require_store,root_name='model_from_char')
                result['model_animation_count']=anim_result['animation_count']
                result['model_animation_resolved_count']=anim_result['resolved_animation_count']
                result['model_animation_compact21_count']=anim_result['compact21_count']
                result['model_animation_probe21_summary']=str(package_dir/anim_result['summary_file'])
                manifest_path=Path(result.get('manifest_path') or package_dir/'repack_manifest.json')
                if manifest_path.is_file():
                    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                    manifest['char_animation_count']=anim_result['animation_count']
                    manifest['char_animation_resolved_count']=anim_result['resolved_animation_count']
                    manifest['char_animation_compact21_count']=anim_result['compact21_count']
                    manifest['char_animation_probe21_summary']=anim_result['summary_file']
                    manifest['char_animation_refs']=anim_result['animations']
                    manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
            except Exception as e:
                result['model_animation_error']=str(e)
        return result
    model_package.export_model_package=patched_export_model_package
    gui_module.export_model_package=patched_export_model_package

def _install_char_package_patch():
    original=char_skeletal_package_patch.export_clean_char_package
    def patched_export_clean_char_package(parsed,entry,out_dir,require_store=None):
        result=original(parsed,entry,out_dir,require_store=require_store)
        try:
            package_dir=Path(result['package_dir'])
            refs=_collect_char_animation_refs(parsed,entry,require_store)
            anim_result=_write_animation_probe_set(parsed,entry,package_dir,refs,require_store,root_name='char')
            result['anim_probe21_summary_path']=str(package_dir/anim_result['summary_file'])
            result['anim_probe21_count']=anim_result['animation_count']
            result['anim_probe21_compact21_count']=anim_result['compact21_count']
            manifest_path=Path(result.get('manifest_path') or package_dir/'manifest.json')
            if manifest_path.is_file():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest['anim_probe21_summary']=anim_result['summary_file']
                manifest['anim_probe21_count']=anim_result['animation_count']
                manifest['anim_probe21_compact21_count']=anim_result['compact21_count']
                manifest['anim_probe21_refs']=anim_result['animations']
                manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
        except Exception as e:
            result['anim_probe21_error']=str(e)
        return result
    def export_char_package(parsed,entry,out_dir,require_store=None):
        return patched_export_clean_char_package(parsed,entry,out_dir,require_store=require_store)
    char_skeletal_package_patch.export_clean_char_package=patched_export_clean_char_package
    char_gui_patch.export_char_package=export_char_package

def install(App):
    _install_model_package_patch()
    _install_char_package_patch()
    _install_gui_patch(App)
