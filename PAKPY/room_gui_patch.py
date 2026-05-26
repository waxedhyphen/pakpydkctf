from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from pak_core import PakError, get_entry_asset, get_entry_payload, format_meta_lines
from room_deep_codec import format_room_info_lines, export_room_package
from room_full_repack import rebuild_room_package_from_folder
from room_clone_codec import create_room_clone_files

def install(App):
    original_init = App.__init__
    original_show_context_menu = App.show_context_menu
    original_export_model_package_dialog = App.export_model_package_dialog
    original_show_selected = App.show_selected

    def is_room_entry(self, entry):
        return entry.get('type') == 'ROOM'

    def find_button(widget, text):
        for child in widget.winfo_children():
            try:
                if isinstance(child, tk.Button) and child.cget('text') == text:
                    return child
            except Exception:
                pass
            found = find_button(child, text)
            if found is not None:
                return found
        return None

    def __init__(self, root):
        original_init(self, root)
        model_button = find_button(self.root, 'Modellpaket zurückbauen')
        if model_button is not None:
            parent = model_button.master
            button = tk.Button(parent, text='ROOM-Paket zurückbauen', command=self.rebuild_room_package_dialog, width=21)
            clone_button = tk.Button(parent, text='ROOM-Objekt clonen', command=self.clone_room_object_dialog, width=18)
            try:
                button.pack(side='left', padx=(8, 0), after=model_button)
                clone_button.pack(side='left', padx=(8, 0), after=button)
            except Exception:
                button.pack(side='left', padx=(8, 0))
                clone_button.pack(side='left', padx=(8, 0))

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
        if item['kind'] == 'entry' and self.is_room_entry(item['entry']):
            self.context_menu.delete(0, 'end')
            self.context_menu.add_command(label='Roh exportieren', command=self.export_selected_whole)
            self.context_menu.add_separator()
            self.context_menu.add_command(label='ROOM-Paket exportieren', command=self.export_model_package_dialog)
            try:
                self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()
            return
        return original_show_context_menu(self, event)

    def export_model_package_dialog(self):
        try:
            item = self.get_selected_item()
            if item['kind'] == 'entry' and self.is_room_entry(item['entry']):
                out_dir = filedialog.askdirectory(title='Zielordner für ROOM-Paket auswählen')
                if not out_dir:
                    return
                result = export_room_package(self.parsed, item['entry'], out_dir)
                lines = [
                    'ROOM-Paket exportiert:',
                    result['package_dir'],
                    '',
                    f'Manifest: {result["manifest_path"]}',
                    f'Komponenten: {result["components_path"]}',
                    f'DCLN-Referenzen: {result["dcln_refs_path"]}',
                    f'Asset-Referenzen: {result["asset_refs_path"]}',
                    f'HEAD-Referenzen: {result["head_refs_path"]}',
                    f'Report: {result["report_path"]}',
                    f'Collision-Debug-OBJ: {result["collision_obj_path"]}',
                    f'Scene-Preview-OBJ: {result["preview_obj_path"]}',
                    f'Scene-Preview-MTL: {result["preview_mtl_path"]}',
                    f'Scene-Preview-Tabelle: {result["preview_tsv_path"]}',
                    f'Scene-Objekte: {result["preview_split_dir"]}',
                    f'Scene-Repack-Manifest: {result["preview_repack_manifest_path"]}',
                    '',
                    f'Layer: {result["layer_count"]}',
                    f'Komponenten: {result["component_count"]}',
                    f'DCLN-Referenzen: {result["dcln_ref_count"]}',
                    f'Asset-Referenzen aus Komponenten: {result["component_asset_ref_count"]}',
                    f'Asset-Referenzen aus HEAD: {result["head_asset_ref_count"]}',
                    f'Scene-Preview-Referenzen: {result["preview_ref_count"]}',
                    f'Scene-Objekte: {result["preview_split_count"]}',
                    f'Scene-Preview-Zählung: {result["preview_counts"]}',
                    f'DCLN im aktuellen PAK auflösbar: {result["resolved_dcln_ref_count"]}',
                    f'Als Debug-OBJ exportiert: {result["exported_collision_count"]}'
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

    def clone_room_object_dialog(self):
        folder = filedialog.askdirectory(title='ROOM-Paket-Ordner auswählen')
        if not folder:
            return
        try:
            folder_path = Path(folder)
            source_path = filedialog.askopenfilename(title='ROOMCTRL-Original-OBJ auswählen', initialdir=str(folder_path / 'room_scene_objects' / 'ROOMCTRL'), filetypes=[('OBJ-Dateien', '*.obj'), ('Alle Dateien', '*.*')])
            if not source_path:
                return
            result = create_room_clone_files(folder_path, source_path)
            lines = [
                'ROOM-Clone-Dateien erstellt:',
                f'Clone-ID: {result["clone_id"]}',
                f'Dateien: {result["count"]}',
                ''
            ]
            lines.extend(result['files'])
            lines.append('')
            lines.append('Diese clone-Dateien jetzt im Editor verschieben/rotieren/scalen und danach ROOM-Paket zurückbauen.')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', f'{result["count"]} Clone-Datei(en) erstellt')
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def rebuild_room_package_dialog(self):
        if self.parsed is None:
            messagebox.showerror('Fehler', 'Noch keine PAK-Datei eingelesen')
            return
        folder = filedialog.askdirectory(title='ROOM-Paket-Ordner auswählen')
        if not folder:
            return
        try:
            folder_path = Path(folder)
            if not (folder_path / 'room_scene_repack_manifest.json').is_file():
                raise PakError('room_scene_repack_manifest.json fehlt')
            source = Path(self.parsed['path'])
            out_path = filedialog.asksaveasfilename(title='Neues PAK speichern', defaultextension='.pak', initialfile=source.stem + '_room_repacked.pak', filetypes=[('PAK-Dateien', '*.pak'), ('Alle Dateien', '*.*')])
            if not out_path:
                return
            result = rebuild_room_package_from_folder(self.parsed, folder_path, out_path)
            self.pak_var.set(result['out_path'])
            self.load_pak()
            lines = [
                'ROOM-Paket zurückgebaut:',
                result['out_path'],
                '',
                f'Geänderte PAK-Einträge: {result["changed_count"]}',
                f'ROOM-Transform-Patches/Clones: {result["transform_patch_count"]}',
                f'Geänderte OBJ-Assets/Clone-Dateien: {len(result["changed_objects"])}'
            ]
            if result['changed_objects']:
                lines.append('')
                lines.extend(result['changed_objects'][:80])
                if len(result['changed_objects']) > 80:
                    lines.append(f'... {len(result["changed_objects"]) - 80} weitere')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', result['out_path'])
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

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
        if item['kind'] == 'entry' and self.is_room_entry(item['entry']):
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
                lines.extend(format_room_info_lines(self.parsed, entry))
            except Exception as e:
                lines.append('')
                lines.append(f'ROOM-Analyse fehlgeschlagen: {e}')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            self.preview.clear()
            self.txtr_preview.clear()
            return
        return original_show_selected(self, event)

    App.__init__ = __init__
    App.is_room_entry = is_room_entry
    App.show_context_menu = show_context_menu
    App.export_model_package_dialog = export_model_package_dialog
    App.clone_room_object_dialog = clone_room_object_dialog
    App.rebuild_room_package_dialog = rebuild_room_package_dialog
    App.show_selected = show_selected
