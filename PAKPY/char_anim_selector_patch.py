from pak_core import PakError,get_entry_asset,format_uuid_hex
import char_codec

ZERO_UUID='00000000000000000000000000000000'

def _u32be(data,off):
    if off+4>len(data):
        return None
    return int.from_bytes(data[off:off+4],'big')

def _u16be_list(data):
    return [int.from_bytes(data[i:i+2],'big') for i in range(0,len(data)//2*2,2)]

def _collect_selectors(parsed,entry):
    if entry is None or entry.get('type')!='CHAR':
        return []
    try:
        info=char_codec.parse_char_asset(get_entry_asset(parsed,entry))
    except Exception:
        return []
    out=[]
    for anim in info.get('animations',[]):
        if (anim.get('uuid_hex') or '').replace('-','').lower()!=ZERO_UUID:
            continue
        extra=bytes.fromhex(anim.get('extra_hex','')) if anim.get('extra_hex') else b''
        item=dict(anim)
        item['selector_kind_u32']=_u32be(extra,0)
        item['selector_arg_u32']=_u32be(extra,4)
        item['selector_u16']=_u16be_list(extra)
        out.append(item)
    return out

def _selector_label(item):
    name=item.get('name') or 'selector'
    idx=item.get('index')
    idx_text=f'#{idx} ' if isinstance(idx,int) else ''
    k=item.get('selector_kind_u32')
    a=item.get('selector_arg_u32')
    suffix=''
    if k is not None:
        suffix+=f' | kind {k}'
    if a is not None:
        suffix+=f' | arg 0x{a:08X}'
    return f'  ANIM-SEL | {idx_text}{name} | Null-UUID{suffix}'

def _sort_children(self,parent_iid):
    children=list(self.tree.get_children(parent_iid))
    if not children:
        return
    def key(iid):
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
            elif kind in ('char_anim_child','char_anim_selector_child'):
                typ='ANIM'
            elif kind=='model_mtrl_child':
                typ='MTRL'
            elif kind=='model_txtr_child':
                typ='TXTR'
        return (typ.upper(),text.upper(),iid)
    ordered=sorted(children,key=key)
    if ordered!=children:
        for index,iid in enumerate(ordered):
            self.tree.move(iid,parent_iid,index)
    for iid in ordered:
        _sort_children(self,iid)

def install(App):
    original_refresh=App.refresh_list
    original_show=App.show_selected
    original_payload=App.build_payload_export
    original_whole=App.build_whole_export
    def refresh_list(self):
        original_refresh(self)
        if self.parsed is None:
            return
        query=self.filter_var.get().strip().upper()
        mode=self.filter_mode_var.get()
        for entry in self.parsed.get('entries',[]):
            if entry.get('type')!='CHAR':
                continue
            selectors=_collect_selectors(self.parsed,entry)
            if not selectors:
                continue
            entry_iid=f'entry_{entry["index"]}'
            if not self.tree.exists(entry_iid):
                if not query:
                    continue
                matching=[]
                for selector in selectors:
                    text=' '.join(str(x or '') for x in (selector.get('name',''),selector.get('extra_hex',''),'ANIM','SEL','NULL')).upper()
                    if mode=='type':
                        ok=query in 'ANIM'
                    elif mode=='missing':
                        ok=False
                    elif mode=='size':
                        ok=False
                    else:
                        ok=query in text
                    if ok:
                        matching.append(selector)
                if not matching:
                    continue
                parent=''
                if mode=='type':
                    parent='group_CHAR'
                    if not self.tree.exists(parent):
                        self.tree.insert('', 'end', iid=parent, text=f'{self.type_group_label("CHAR")} (1)', open=True)
                self.tree.insert(parent,'end',iid=entry_iid,text=self.tree.item(entry_iid,'text') if self.tree.exists(entry_iid) else f'{entry["type"]} | {self.entry_display_name(entry)} | Größe {entry["size"]}',open=True)
                self.tree_items[entry_iid]={'kind':'entry','entry':entry}
                selectors_to_show=matching
            else:
                selectors_to_show=selectors
            for selector in selectors_to_show:
                iid=f'entry_{entry["index"]}_char_anim_selector_{selector.get("index",0)}'
                if self.tree.exists(iid):
                    continue
                self.tree.insert(entry_iid,'end',iid=iid,text=_selector_label(selector))
                self.tree_items[iid]={'kind':'char_anim_selector_child','entry':entry,'selector':selector}
        _sort_children(self,'')
    def show_selected(self,event=None):
        iid=self.get_display_iid()
        item=self.tree_items.get(iid) if iid else None
        if item is None or item.get('kind')!='char_anim_selector_child':
            return original_show(self,event)
        self.preview.clear()
        self.txtr_preview.clear()
        entry=item['entry']
        selector=item['selector']
        lines=[]
        lines.append(f'Übergeordneter CHAR: #{entry["index"]} CHAR')
        lines.append(f'CHAR-Name: {self.entry_display_name(entry)}')
        lines.append(f'CHAR-UUID: {entry["uuid_hex"]}')
        lines.append('')
        lines.append(f'CHAR-Animationsslot: #{selector.get("index","")}')
        lines.append(f'Name: {selector.get("name","")}')
        lines.append(f'UUID: {format_uuid_hex(selector.get("uuid_hex",ZERO_UUID))}')
        lines.append('Status: Selector/Gruppe, keine eigene ANIM-Datei')
        if selector.get('selector_kind_u32') is not None:
            lines.append(f'Selector-Kind-u32: {selector["selector_kind_u32"]}')
        if selector.get('selector_arg_u32') is not None:
            lines.append(f'Selector-Arg-u32: 0x{selector["selector_arg_u32"]:08X}')
        lines.append(f'Extra: {selector.get("extra_hex","")}')
        lines.append(f'Extra-u16: {selector.get("selector_u16",[])}')
        self.output.delete('1.0','end')
        self.output.insert('1.0','\n'.join(lines))
    def build_payload_export(self,item):
        if item.get('kind')=='char_anim_selector_child':
            raise PakError('Dieser CHAR-Animationspunkt ist ein Selector mit Null-UUID und hat keine eigene ANIM-Datei')
        return original_payload(self,item)
    def build_whole_export(self,item):
        if item.get('kind')=='char_anim_selector_child':
            raise PakError('Dieser CHAR-Animationspunkt ist ein Selector mit Null-UUID und hat keine eigene ANIM-Datei')
        return original_whole(self,item)
    App.refresh_list=refresh_list
    App.show_selected=show_selected
    App.build_payload_export=build_payload_export
    App.build_whole_export=build_whole_export
