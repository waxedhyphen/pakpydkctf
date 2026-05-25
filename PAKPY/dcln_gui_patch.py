from tkinter import filedialog, messagebox
from pak_core import PakError, get_entry_asset, get_entry_payload, format_meta_lines
from dcln_codec import parse_dcln_asset, export_dcln_as_obj, export_dcln_package, format_dcln_info_lines

def install(App):
    original_convert_selected_to_obj = App.convert_selected_to_obj
    original_export_model_package_dialog = App.export_model_package_dialog
    original_show_selected = App.show_selected

    def is_dcln_entry(self, entry):
        return entry.get('type') == 'DCLN'

    def show_context_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            iid = self.tree.focus()
        if not iid:
            return
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.last_clicked_iid = iid
        self.root.after_idle(self.show_selected)
        item = self.tree_items.get(iid)
        if item is None:
            return
        self.context_menu.delete(0, 'end')
        self.context_menu.add_command(label='Roh exportieren', command=self.export_selected_whole)
        if item['kind'] == 'entry' and self.is_model_entry(item['entry']):
            self.context_menu.add_separator()
            self.context_menu.add_command(label='Convert -> OBJ', command=self.convert_selected_to_obj)
            self.context_menu.add_command(label='Export with...', command=self.export_selected_with_dialog)
        elif item['kind'] == 'entry' and self.is_dcln_entry(item['entry']):
            self.context_menu.add_separator()
            self.context_menu.add_command(label='Convert -> OBJ', command=self.convert_selected_to_obj)
            self.context_menu.add_command(label='Collisionpaket exportieren', command=self.export_model_package_dialog)
        elif self.is_txtr_item(item):
            self.context_menu.add_separator()
            self.context_menu.add_command(label='Convert -> PNG', command=self.convert_selected_to_png)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def convert_selected_to_obj(self):
        try:
            item = self.get_selected_item()
            if item['kind'] == 'entry' and self.is_dcln_entry(item['entry']):
                out_dir = filedialog.askdirectory(title='Zielordner für DCLN-OBJ auswählen')
                if not out_dir:
                    return
                result = export_dcln_as_obj(self.parsed, item['entry'], out_dir)
                lines = [
                    'DCLN-OBJ exportiert:',
                    result['obj_path'],
                    '',
                    'MTL exportiert:',
                    result['mtl_path'],
                    '',
                    'TREE-OBJ exportiert:',
                    result['tree_obj_path'],
                    '',
                    f'Vertices: {result["vertex_count"]}',
                    f'Triangles: {result["triangle_count"]}',
                    f'Materialien: {result["material_count"]}',
                    f'TREE-Nodes: {result["tree_node_count"]}'
                ]
                self.output.delete('1.0', 'end')
                self.output.insert('1.0', '\n'.join(lines))
                messagebox.showinfo('Fertig', result['obj_path'])
                return
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))
            return
        return original_convert_selected_to_obj(self)

    def export_model_package_dialog(self):
        try:
            item = self.get_selected_item()
            if item['kind'] == 'entry' and self.is_dcln_entry(item['entry']):
                out_dir = filedialog.askdirectory(title='Zielordner für Collisionpaket auswählen')
                if not out_dir:
                    return
                result = export_dcln_package(self.parsed, item['entry'], out_dir)
                lines = [
                    'Collisionpaket exportiert:',
                    result['package_dir'],
                    '',
                    f'OBJ: {result["obj_path"]}',
                    f'MTL: {result["mtl_path"]}',
                    f'TREE-OBJ: {result["tree_obj_path"]}',
                    f'Manifest: {result["manifest_path"]}',
                    '',
                    f'Vertices: {result["vertex_count"]}',
                    f'Triangles: {result["triangle_count"]}',
                    f'Materialien: {result["material_count"]}',
                    f'TREE-Nodes: {result["tree_node_count"]}'
                ]
                self.output.delete('1.0', 'end')
                self.output.insert('1.0', '\n'.join(lines))
                messagebox.showinfo('Fertig', result['package_dir'])
                return
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))
            return
        return original_export_model_package_dialog(self)

    def show_selected(self, event=None):
        if self.parsed is None:
            return
        display_iid = self.get_display_iid()
        if not display_iid:
            self.preview.clear()
            self.txtr_preview.clear()
            return
        item = self.tree_items.get(display_iid)
        if item is None:
            self.preview.clear()
            self.txtr_preview.clear()
            return
        if item['kind'] == 'entry' and self.is_dcln_entry(item['entry']):
            entry = item['entry']
            asset = get_entry_asset(self.parsed, entry)
            payload = get_entry_payload(asset)
            lines = []
            lines.append(f'Index: {entry["index"]}')
            lines.append(f'Typ: {entry["type"]}')
            lines.append(f'Name: {self.entry_display_name(entry)}')
            lines.append(f'UUID: {entry["uuid_hex"]}')
            lines.append(f'Offset: {entry["offset"]}')
            lines.append(f'Größe: {entry["size"]}')
            lines.append(f'Payload-Größe: {len(payload)}')
            lines.append(f'Payload-Kennung: {entry["payload_kind"] or "unbekannt"}')
            lines.extend(format_meta_lines(entry))
            lines.append(f'Asset-SHA1: {entry["asset_sha1"]}')
            lines.append(f'Payload-SHA1: {entry["payload_sha1"]}')
            try:
                info = parse_dcln_asset(asset)
                lines.append('')
                lines.extend(format_dcln_info_lines(info))
            except Exception as e:
                lines.append('')
                lines.append(f'DCLN-Analyse fehlgeschlagen: {e}')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            self.preview.clear()
            self.txtr_preview.clear()
            return
        return original_show_selected(self, event)

    App.is_dcln_entry = is_dcln_entry
    App.show_context_menu = show_context_menu
    App.convert_selected_to_obj = convert_selected_to_obj
    App.export_model_package_dialog = export_model_package_dialog
    App.show_selected = show_selected
