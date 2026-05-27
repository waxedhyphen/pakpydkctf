from tkinter import filedialog, messagebox
from pak_core import get_entry_asset, get_entry_payload, format_meta_lines
from char_codec import export_char_package, format_char_info_lines

def install(App):
    original_show_context_menu = App.show_context_menu
    original_export_model_package_dialog = App.export_model_package_dialog
    original_show_selected = App.show_selected
    def is_char_entry(self, entry):
        return entry.get('type') == 'CHAR'
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
        if item['kind'] == 'entry' and self.is_char_entry(item['entry']):
            self.context_menu.delete(0, 'end')
            self.context_menu.add_command(label='Roh exportieren', command=self.export_selected_whole)
            self.context_menu.add_separator()
            self.context_menu.add_command(label='CHAR-Paket exportieren', command=self.export_model_package_dialog)
            try:
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()
            return
        return original_show_context_menu(self, event)
    def export_model_package_dialog(self):
        try:
            item = self.get_selected_item()
            if item['kind'] == 'entry' and self.is_char_entry(item['entry']):
                out_dir = self.ask_directory('char_package_export_dir', title='Zielordner für CHAR-Paket auswählen')
                if not out_dir:
                    return
                result = export_char_package(self.parsed, item['entry'], out_dir, require_store=self.require_store)
                lines = [
                    'CHAR-Paket exportiert:',
                    result['package_dir'],
                    '',
                    f'Manifest: {result["manifest_path"]}',
                    f'Report: {result["report_path"]}',
                    '',
                    f'Modelle: {result["resolved_model_count"]}/{result["model_count"]} aufgelöst',
                    f'Animationen: {result["resolved_animation_count"]}/{result["animation_count"]} aufgelöst',
                    f'Weitere Ressourcen: {result["resource_count"]}',
                    f'Fehlende Referenzen: {result["missing_count"]}'
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
        if item['kind'] == 'entry' and self.is_char_entry(item['entry']):
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
                lines.append('')
                lines.extend(format_char_info_lines(self.parsed, entry, require_store=self.require_store))
            except Exception as e:
                lines.append('')
                lines.append(f'CHAR-Analyse fehlgeschlagen: {e}')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            self.preview.clear()
            self.txtr_preview.clear()
            return
        return original_show_selected(self, event)
    App.is_char_entry = is_char_entry
    App.show_context_menu = show_context_menu
    App.export_model_package_dialog = export_model_package_dialog
    App.show_selected = show_selected
