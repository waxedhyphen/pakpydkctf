from pathlib import Path
import json
import math
import struct
import gui as gui_module
import model_package
from pak_core import PakError,get_entry_asset,safe_name,kind_to_ext,sha1_bytes,format_uuid_hex

ZERO_UUID='00000000000000000000000000000000'
MODEL_TYPES={'CMDL','SMDL','WMDL'}

def be32(data,off):
    return int.from_bytes(data[off:off+4],'big')

def tag4(data,off):
    return data[off:off+4].decode('ascii','replace')

def _signed16(value):
    return value-0x10000 if value>=0x8000 else value

def _signed32(value):
    return value-0x100000000 if value>=0x80000000 else value

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
    return entry.get('display_name') or entry.get('name') or entry.get('uuid_hex','')

def _known_anim_entries(parsed,require_store=None):
    out={}
    for entry in parsed.get('entries',[]):
        if entry.get('type')=='ANIM' and entry.get('uuid_hex')!=ZERO_UUID:
            out[entry['uuid_hex']]=(entry,'pak',parsed.get('path',''))
    if require_store is not None:
        for uuid_hex,item in getattr(require_store,'required_entries_by_uuid',{}).items():
            entry=item.get('entry') or {}
            if entry.get('type')=='ANIM' and uuid_hex!=ZERO_UUID:
                out[uuid_hex]=(entry,'require',item.get('parsed_path',''))
    return out

def _collect_model_animation_refs(parsed,entry,require_store=None,extra_refs=None):
    refs=[]
    seen=set()
    if extra_refs:
        for index,ref in enumerate(extra_refs):
            uuid_hex=ref.get('uuid_hex') or ref.get('uuid') or ''
            uuid_hex=uuid_hex.replace('-','').lower()
            if len(uuid_hex)!=32 or uuid_hex==ZERO_UUID or uuid_hex in seen:
                continue
            anim_entry,source,source_path=_known_anim_entries(parsed,require_store).get(uuid_hex,({},ref.get('source_kind',''),ref.get('source_path','')))
            refs.append({'index':len(refs),'uuid_hex':uuid_hex,'name':ref.get('name') or _entry_name(anim_entry),'type':'ANIM','offset':ref.get('offset',-1),'source_kind':source,'source_path':source_path})
            seen.add(uuid_hex)
    if entry is None or entry.get('type') not in MODEL_TYPES:
        return refs
    try:
        asset=get_entry_asset(parsed,entry)
    except Exception:
        return refs
    for uuid_hex,(anim_entry,source,source_path) in _known_anim_entries(parsed,require_store).items():
        if uuid_hex in seen:
            continue
        try:
            needle=bytes.fromhex(uuid_hex)
        except Exception:
            continue
        pos=asset.find(needle)
        if pos==-1:
            continue
        offsets=[]
        while pos!=-1:
            offsets.append(pos)
            pos=asset.find(needle,pos+1)
        refs.append({'index':len(refs),'uuid_hex':uuid_hex,'name':_entry_name(anim_entry),'type':'ANIM','offset':offsets[0],'offsets':offsets,'source_kind':source,'source_path':source_path})
        seen.add(uuid_hex)
    refs.sort(key=lambda ref:((ref.get('name') or '').upper(),ref.get('uuid_hex','')))
    for index,ref in enumerate(refs):
        ref['index']=index
    return refs

def _resolve_anim_asset(parsed,uuid_hex,require_store=None):
    entry=parsed.get('uuid_to_entry',{}).get(uuid_hex)
    if entry is not None:
        return get_entry_asset(parsed,entry),entry,'pak',parsed.get('path','')
    if require_store is not None:
        asset,entry,source=require_store.resolve_asset(parsed,uuid_hex)
        if entry is not None and asset is not None:
            source_path=require_store.get_required_source(uuid_hex) if source=='require' else parsed.get('path','')
            return asset,entry,source,source_path
    return None,None,'',''

def _anim_ref_label(ref,anim_entry=None):
    name=''
    size=''
    if anim_entry is not None:
        name=_entry_name(anim_entry)
        size=f' | Größe {anim_entry.get("size",0)}'
    elif ref.get('name'):
        name=ref.get('name','')
    offset=ref.get('offset',-1)
    offset_text=f' | Offset 0x{offset:X}' if isinstance(offset,int) and offset>=0 else ''
    if name:
        return f'  ANIM | {name} | {format_uuid_hex(ref["uuid_hex"])}{size}{offset_text}'
    return f'  ANIM | {format_uuid_hex(ref["uuid_hex"])}{offset_text}'

def _anim_summary_lines(ref,anim_entry,asset,source,source_path):
    lines=[]
    lines.append(f'ANIM-UUID: {format_uuid_hex(ref["uuid_hex"])}')
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

def _safe_rel(root,path):
    return str(Path(path).relative_to(root)).replace('\\','/')

def _unique_path(path):
    path=Path(path)
    if not path.exists():
        return path
    suffix=''.join(path.suffixes)
    stem=path.name[:-len(suffix)] if suffix else path.name
    n=2
    while True:
        candidate=path.with_name(f'{stem}_{n}{suffix}')
        if not candidate.exists():
            return candidate
        n+=1

def _write_animation_package(parsed,entry,package_dir,refs,require_store=None):
    package_dir=Path(package_dir)
    raw_dir=package_dir/'animations'/'raw_anim'
    probe_dir=package_dir/'animations'/'probe21'
    raw_dir.mkdir(parents=True,exist_ok=True)
    probe_dir.mkdir(parents=True,exist_ok=True)
    out=[]
    compact21_count=0
    resolved_count=0
    for ref in refs:
        uuid_hex=ref.get('uuid_hex','')
        asset,anim_entry,source,source_path=_resolve_anim_asset(parsed,uuid_hex,require_store)
        item=dict(ref)
        item.update({'resolved':asset is not None and anim_entry is not None,'entry_type':anim_entry.get('type') if anim_entry else '','entry_name':_entry_name(anim_entry) if anim_entry else ref.get('name',''),'source_kind':source,'source_path':source_path,'raw_file':'','probe21_file':'','probe21_kind':'','probe21_error':''})
        if asset is None or anim_entry is None:
            out.append(item)
            continue
        resolved_count+=1
        base=safe_name(f'{item["index"]:03d}__{item["entry_name"] or "anim"}__{uuid_hex}')
        raw_path=_unique_path(raw_dir/(base+kind_to_ext(anim_entry.get('type') or 'ANIM')))
        raw_path.write_bytes(asset)
        item['raw_file']=_safe_rel(package_dir,raw_path)
        probe_path=_unique_path(probe_dir/(base+'.probe21.json'))
        try:
            probe=parse_anim_probe21(asset)
            probe.update({'uuid_hex':uuid_hex,'entry_name':item['entry_name'],'source_kind':source,'source_path':source_path})
            item['probe21_kind']=probe.get('body',{}).get('kind','')
            if item['probe21_kind']=='compact21':
                compact21_count+=1
            probe_path.write_text(json.dumps(probe,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
        except Exception as e:
            item['probe21_error']=str(e)
            probe_path.write_text(json.dumps({'error':str(e),'uuid_hex':uuid_hex},indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
        item['probe21_file']=_safe_rel(package_dir,probe_path)
        out.append(item)
    summary={'model_uuid_hex':entry.get('uuid_hex',''),'model_name':_entry_name(entry),'animation_count':len(out),'resolved_animation_count':resolved_count,'compact21_count':compact21_count,'animations':out}
    summary_path=package_dir/'animations'/'anim_probe21_summary.json'
    summary_path.parent.mkdir(parents=True,exist_ok=True)
    summary_path.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
    return {'summary':summary,'summary_file':_safe_rel(package_dir,summary_path),'animations':out,'animation_count':len(out),'resolved_animation_count':resolved_count,'compact21_count':compact21_count}

def _install_gui_patch(App):
    original_refresh=App.refresh_list
    original_get_tags=App.get_tree_tags_for_item
    original_payload=App.build_payload_export
    original_whole=App.build_whole_export
    original_show=App.show_selected
    def get_model_animation_refs(self,entry):
        cache_key='_model_animation_refs'
        cache_req_key='_model_animation_refs_require_id'
        req_id=id(self.require_store)
        if entry.get(cache_key) is None or entry.get(cache_req_key)!=req_id:
            entry[cache_key]=_collect_model_animation_refs(self.parsed,entry,self.require_store)
            entry[cache_req_key]=req_id
        return list(entry.get(cache_key) or [])
    def anim_ref_matches(self,ref,query,mode):
        if mode=='missing':
            asset,anim_entry,source=self.require_store.resolve_asset(self.parsed,ref['uuid_hex'])
            return anim_entry is None or asset is None
        if not query:
            return True
        if mode=='size':
            asset,anim_entry,source=self.require_store.resolve_asset(self.parsed,ref['uuid_hex'])
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
                elif kind=='model_anim_child':
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
    def add_model_animation_children(self):
        query=self.filter_var.get().strip().upper()
        mode=self.filter_mode_var.get()
        for entry_iid,item in list(self.tree_items.items()):
            if item.get('kind')!='entry':
                continue
            entry=item['entry']
            if entry.get('type') not in MODEL_TYPES or not self.tree.exists(entry_iid):
                continue
            refs=get_model_animation_refs(self,entry)
            if not refs:
                continue
            if query:
                entry_match=self.entry_matches(entry,query,mode)
                refs_to_show=refs if entry_match and mode!='missing' else [ref for ref in refs if anim_ref_matches(self,ref,query,mode)]
            else:
                refs_to_show=refs
            for ref in refs_to_show:
                iid=f'entry_{entry["index"]}_anim_{ref["uuid_hex"]}_{ref.get("offset",-1)}'
                if self.tree.exists(iid):
                    continue
                asset,anim_entry,source=self.require_store.resolve_asset(self.parsed,ref['uuid_hex'])
                tags=()
                if anim_entry is None or asset is None:
                    tags=('missing_ref',)
                elif source=='require':
                    tags=('required_ref',)
                self.tree.insert(entry_iid,'end',iid=iid,text=_anim_ref_label(ref,anim_entry),tags=tags)
                self.tree_items[iid]={'kind':'model_anim_child','entry':entry,'ref':ref,'anim_entry':anim_entry}
    def patched_refresh_list(self):
        original_refresh(self)
        if self.parsed is None:
            return
        add_model_animation_children(self)
        sort_tree_children_by_type(self,'')
    def patched_get_tags(self,item):
        if item.get('kind')=='model_anim_child':
            asset,anim_entry,source=self.require_store.resolve_asset(self.parsed,item['ref']['uuid_hex'])
            if anim_entry is None or asset is None:
                return ('missing_ref',)
            if source=='require':
                return ('required_ref',)
            return ()
        return original_get_tags(self,item)
    def patched_payload(self,item):
        if item.get('kind')=='model_anim_child':
            asset,anim_entry,source=self.require_store.resolve_asset(self.parsed,item['ref']['uuid_hex'])
            if anim_entry is None or asset is None:
                raise PakError('Verlinktes ANIM ist weder im aktuellen PAK noch in den requireten Dateien vorhanden')
            base=safe_name(_entry_name(anim_entry) or item['ref']['uuid_hex'])
            return base+kind_to_ext(anim_entry.get('type') or 'ANIM'),asset
        return original_payload(self,item)
    def patched_whole(self,item):
        if item.get('kind')=='model_anim_child':
            asset,anim_entry,source=self.require_store.resolve_asset(self.parsed,item['ref']['uuid_hex'])
            if anim_entry is None or asset is None:
                raise PakError('Verlinktes ANIM ist weder im aktuellen PAK noch in den requireten Dateien vorhanden')
            base=safe_name(_entry_name(anim_entry) or item['ref']['uuid_hex'])
            return base+'.anim.bin',asset
        return original_whole(self,item)
    def patched_show(self):
        iid=self.get_display_iid()
        item=self.tree_items.get(iid) if iid else None
        if item is None or item.get('kind')!='model_anim_child':
            return original_show(self)
        self.preview.clear()
        self.txtr_preview.clear()
        entry=item['entry']
        ref=item['ref']
        asset,anim_entry,source,source_path=_resolve_anim_asset(self.parsed,ref['uuid_hex'],self.require_store)
        lines=[]
        lines.append(f'Übergeordnetes Modell: #{entry["index"]} {entry["type"]}')
        lines.append(f'Modell-Name: {self.entry_display_name(entry)}')
        lines.append(f'Modell-UUID: {entry["uuid_hex"]}')
        if isinstance(ref.get('offset'),int) and ref.get('offset')>=0:
            lines.append(f'Referenz-Offset im Modell: 0x{ref["offset"]:X}')
        lines.append('')
        if asset is None or anim_entry is None:
            lines.append('Status: Missing')
            lines.append(f'ANIM-UUID: {format_uuid_hex(ref["uuid_hex"])}')
        else:
            lines.extend(_anim_summary_lines(ref,anim_entry,asset,source,source_path))
        self.output.delete('1.0','end')
        self.output.insert('1.0','\n'.join(lines))
    App.get_model_animation_refs=get_model_animation_refs
    App.anim_ref_matches=anim_ref_matches
    App.refresh_list=patched_refresh_list
    App.get_tree_tags_for_item=patched_get_tags
    App.build_payload_export=patched_payload
    App.build_whole_export=patched_whole
    App.show_selected=patched_show

def _install_model_package_patch():
    original=model_package.export_model_package
    def patched_export_model_package(parsed,entry,out_dir,require_store=None,animation_refs=None):
        refs=_collect_model_animation_refs(parsed,entry,require_store,animation_refs)
        result=original(parsed,entry,out_dir,require_store=require_store,animation_refs=animation_refs)
        if 'obj_path' not in result and 'obj' in result:
            result['obj_path']=result['obj']
        if 'mtl_path' not in result and 'mtl' in result:
            result['mtl_path']=result['mtl']
        try:
            package_dir=Path(result['package_dir'])
            anim_result=_write_animation_package(parsed,entry,package_dir,refs,require_store)
            result['model_animation_count']=anim_result['animation_count']
            result['model_animation_resolved_count']=anim_result['resolved_animation_count']
            result['model_animation_compact21_count']=anim_result['compact21_count']
            result['model_animation_probe21_summary']=str(package_dir/anim_result['summary_file'])
            manifest_path=Path(result.get('manifest_path') or package_dir/'repack_manifest.json')
            if manifest_path.is_file():
                manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
                manifest['model_animation_count']=anim_result['animation_count']
                manifest['model_animation_resolved_count']=anim_result['resolved_animation_count']
                manifest['model_animation_compact21_count']=anim_result['compact21_count']
                manifest['model_animation_probe21_summary']=anim_result['summary_file']
                manifest['model_animation_refs']=anim_result['animations']
                if not manifest.get('animations'):
                    manifest['animations']=anim_result['animations']
                manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8',newline='\n')
        except Exception as e:
            result['model_animation_error']=str(e)
        return result
    model_package.export_model_package=patched_export_model_package
    gui_module.export_model_package=patched_export_model_package

def install(App):
    _install_model_package_patch()
    _install_gui_patch(App)
