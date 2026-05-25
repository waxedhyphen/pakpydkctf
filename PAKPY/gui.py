from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from pak_core import PakError, parse_pak, analyze_text, make_entry_label, make_child_label, safe_name, kind_to_ext, get_entry_asset, get_entry_payload, build_segment_blob, build_bundle_replaced_asset, rebuild_pak, format_meta_lines, format_mtrl_info_lines, format_model_material_lines, make_mtrl_ref_label, make_txtr_ref_label, format_txtr_ref_lines, ASSET_TYPE_LABELS
from pak_folder import export_all, collect_folder_replacements
from soundpreview import SoundPreview
from txtrpreview import TxtrPreview
from caud_codec import format_caud_lines, is_caud_asset
from pak_extract import export_model_entry_as_obj, export_model_with_options, export_txtr_item_as_png, export_txtr_bytes_as_png
from model_package import export_model_package, rebuild_model_package_from_folder
from require_store import RequireStore
from windows_compat import is_macos_metadata_path

class App:
    def __init__(self, root):
        self.root = root
        self.root.title('PAK Rebuilder mit META-Neuaufbau')
        self.root.geometry('1220x860')
        self.parsed = None
        self.visible_items = []
        self.pak_var = tk.StringVar()
        self.repl_var = tk.StringVar()
        self.mode_var = tk.StringVar(value='payload')
        self.filter_var = tk.StringVar()
        self.filter_mode_var = tk.StringVar(value='name')
        self.tree_items = {}
        self.last_clicked_iid = ''
        self.require_store = RequireStore()
        self.filter_mode_var.set('name')
        outer = tk.Frame(root, padx=14, pady=14)
        outer.pack(fill='both', expand=True)
        row1 = tk.Frame(outer)
        row1.pack(fill='x')
        tk.Label(row1, text='PAK-Datei').pack(side='left')
        tk.Entry(row1, textvariable=self.pak_var).pack(side='left', fill='x', expand=True, padx=(8, 8))
        tk.Button(row1, text='Auswählen', command=self.choose_pak, width=12).pack(side='left')
        tk.Button(row1, text='Einlesen', command=self.load_pak, width=12).pack(side='left', padx=(8, 0))
        row2 = tk.Frame(outer)
        row2.pack(fill='x', pady=(10, 0))
        tk.Label(row2, text='Ersatzdatei').pack(side='left')
        tk.Entry(row2, textvariable=self.repl_var).pack(side='left', fill='x', expand=True, padx=(8, 8))
        tk.Button(row2, text='Auswählen', command=self.choose_replacement, width=12).pack(side='left')
        row3 = tk.Frame(outer)
        row3.pack(fill='x', pady=(10, 0))
        tk.Label(row3, text='Modus').pack(side='left')
        tk.Radiobutton(row3, text='Nur Inhalt ersetzen', variable=self.mode_var, value='payload').pack(side='left', padx=(10, 0))
        tk.Radiobutton(row3, text='Ganze Ressource ersetzen', variable=self.mode_var, value='whole').pack(side='left', padx=(10, 0))
        tk.Radiobutton(row3, text='Automatisch', variable=self.mode_var, value='auto').pack(side='left', padx=(10, 0))
        middle = tk.PanedWindow(outer, orient='horizontal', sashwidth=10, sashrelief='raised')
        middle.pack(fill='both', expand=True, pady=(12, 0))
        left = tk.Frame(middle, width=500)
        tk.Label(left, text='Einträge und Unterdateien').pack(anchor='w')
        search_row = tk.Frame(left)
        search_row.pack(fill='x', pady=(6, 2))
        tk.Label(search_row, text='Filter').pack(side='left')
        self.filter_entry = tk.Entry(search_row, textvariable=self.filter_var)
        self.filter_entry.pack(side='left', fill='x', expand=True, padx=(8, 0))
        filter_mode_row = tk.Frame(left)
        filter_mode_row.pack(fill='x', pady=(0, 6))
        tk.Label(filter_mode_row, text='Filtern nach').pack(side='left')
        tk.Radiobutton(filter_mode_row, text='Name', variable=self.filter_mode_var, value='name').pack(side='left', padx=(8, 0))
        tk.Radiobutton(filter_mode_row, text='Größe', variable=self.filter_mode_var, value='size').pack(side='left', padx=(8, 0))
        tk.Radiobutton(filter_mode_row, text='Dateityp', variable=self.filter_mode_var, value='type').pack(side='left', padx=(8, 0))
        tk.Radiobutton(filter_mode_row, text='Missing', variable=self.filter_mode_var, value='missing').pack(side='left', padx=(8, 0))
        self.filter_var.trace_add('write', self.on_filter_changed)
        self.filter_mode_var.trace_add('write', self.on_filter_changed)
        tree_wrap = tk.Frame(left)
        tree_wrap.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(tree_wrap, show='tree', selectmode='extended', height=36)
        self.tree.tag_configure('missing_ref', foreground='#d88f96')
        self.tree.tag_configure('required_ref', foreground='#7a6fd6')
        self.tree.bind('<<TreeviewSelect>>', self.show_selected)
        self.tree.bind('<ButtonRelease-1>', self.remember_tree_click, add='+')
        self.tree.bind('<Button-2>', self.show_context_menu, add='+')
        self.tree.bind('<ButtonPress-3>', self.show_context_menu, add='+')
        self.tree.bind('<ButtonPress-2>', self.show_context_menu, add='+')
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.tree.pack(side='left', fill='both', expand=True)
        tree_scroll = ttk.Scrollbar(tree_wrap, orient='vertical', command=self.tree.yview)
        tree_scroll.pack(side='left', fill='y')
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind('<ButtonRelease-1>', self.remember_tree_click, add='+')
        right = tk.Frame(middle, width=680)
        tk.Label(right, text='Analyse').pack(anchor='w')
        self.output = ScrolledText(right, wrap='word')
        self.output.pack(fill='both', expand=True)
        self.preview = SoundPreview(right)
        self.txtr_preview = TxtrPreview(right)
        middle.add(left, minsize=320)
        middle.add(right, minsize=420)
        self.root.after(50, lambda: middle.sash_place(0, 520, 0))
        bottom = tk.Frame(outer)
        bottom.pack(fill='x', pady=(10, 0))
        bottom_row_1 = tk.Frame(bottom)
        bottom_row_1.pack(fill='x')
        bottom_row_2 = tk.Frame(bottom)
        bottom_row_2.pack(fill='x', pady=(8, 0))
        tk.Button(bottom_row_1, text='Validieren', command=self.validate_current, width=15).pack(side='left')
        tk.Button(bottom_row_1, text='Inhalt exportieren', command=self.export_selected_payload, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_1, text='Ganz exportieren', command=self.export_selected_whole, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_1, text='Direkt ersetzen', command=self.replace_selected_direct, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_1, text='Backup importieren', command=self.import_required_paks, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_1, text='Datei requiren', command=self.import_required_paks, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_2, text='Alles exportieren', command=self.export_all_dialog, width=18).pack(side='left')
        tk.Button(bottom_row_2, text='Modellpaket exportieren', command=self.export_model_package_dialog, width=21).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_2, text='Modellpaket zurückbauen', command=self.rebuild_model_package_dialog, width=21).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_2, text='Aus Ordner neu bauen', command=self.rebuild_from_folder_dialog, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_2, text='Neues PAK bauen', command=self.build_new_pak, width=18).pack(side='left', padx=(8, 0))
        tk.Button(bottom_row_2, text='Leeren', command=self.clear_all, width=12).pack(side='left', padx=(8, 0))
    def is_model_entry(self, entry):
        return entry['type'] in ('CMDL', 'SMDL', 'WMDL')

    def is_txtr_item(self, item):
        if item['kind'] == 'entry':
            return item['entry']['type'] == 'TXTR'
        if item['kind'] == 'bundle_child':
            return item['child']['inner_kind'] == 'TXTR'
        if item['kind'] == 'model_txtr_child':
            return item.get('txtr_entry') is not None
        return False

    def get_txtr_entry_from_item(self, item):
        if item['kind'] == 'entry' and item['entry']['type'] == 'TXTR':
            return item['entry']
        if item['kind'] == 'model_txtr_child':
            asset, entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            return entry
        return None

    def get_txtr_asset_from_item(self, item):
        if item['kind'] == 'entry' and item['entry']['type'] == 'TXTR':
            return get_entry_asset(self.parsed, item['entry'])
        if item['kind'] == 'model_txtr_child':
            asset, entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            return asset
        return None

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
            if item['kind'] != 'entry' or not self.is_model_entry(item['entry']):
                raise PakError('OBJ-Umwandlung geht nur bei CMDL, SMDL oder WMDL')
            out_dir = filedialog.askdirectory(title='Zielordner für OBJ auswählen')
            if not out_dir:
                return
            result = export_model_entry_as_obj(self.parsed, item['entry'], out_dir, write_mtl=True)
            lines = [
                'OBJ exportiert:',
                result['obj_path']
            ]
            if result['mtl_path']:
                lines.extend(['', 'MTL exportiert:', result['mtl_path']])
            lines.extend([
                '',
                f'Vertices: {result["vertex_count"]}',
                f'Meshes: {result["mesh_count"]}',
                f'Materialien: {result["material_count"]}',
                f'Faces: {result["face_count"]}'
            ])
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', result['obj_path'])
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def convert_selected_to_png(self):
        try:
            item = self.get_selected_item()
            txtr_entry = self.get_txtr_entry_from_item(item)
            txtr_asset = self.get_txtr_asset_from_item(item)
            if txtr_entry is None or txtr_asset is None:
                raise PakError('PNG-Umwandlung geht hier nur bei echten TXTR-Einträgen oder verlinkten TXTRs')
            base = self.selected_base_name(txtr_entry) + '.png'
            out_path = filedialog.asksaveasfilename(title='PNG speichern', initialfile=base, defaultextension='.png', filetypes=[('PNG', '*.png'), ('Alle Dateien', '*.*')])
            if not out_path:
                return
            try:
                export_txtr_bytes_as_png(txtr_asset, out_path)
            except Exception as inner:
                raise PakError(f'PNG-Umwandlung fehlgeschlagen: {inner}')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'PNG exportiert:\n{out_path}')
            messagebox.showinfo('Fertig', out_path)
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def export_selected_with_dialog(self):
        try:
            item = self.get_selected_item()
            if item['kind'] != 'entry' or not self.is_model_entry(item['entry']):
                raise PakError('Export with... geht nur bei CMDL, SMDL oder WMDL')
            entry = item['entry']
            win = tk.Toplevel(self.root)
            win.title('Export with...')
            win.transient(self.root)
            win.grab_set()
            frame = tk.Frame(win, padx=14, pady=14)
            frame.pack(fill='both', expand=True)
            mesh_var = tk.BooleanVar(value=True)
            mtl_var = tk.BooleanVar(value=True)
            txtr_var = tk.BooleanVar(value=True)
            tk.Label(frame, text=f'{entry["type"]} | {self.entry_display_name(entry)}').pack(anchor='w')
            tk.Checkbutton(frame, text='Mesh als OBJ', variable=mesh_var).pack(anchor='w', pady=(10, 0))
            tk.Checkbutton(frame, text='MTL-Datei erzeugen', variable=mtl_var).pack(anchor='w')
            tk.Checkbutton(frame, text='Verlinkte TXTRs mit exportieren', variable=txtr_var).pack(anchor='w')
            button_row = tk.Frame(frame)
            button_row.pack(fill='x', pady=(14, 0))
            def run_export():
                try:
                    out_dir = filedialog.askdirectory(title='Zielordner auswählen')
                    if not out_dir:
                        return
                    if txtr_var.get():
                        result = export_model_package(self.parsed, entry, out_dir, require_store=self.require_store)
                        lines = [
                            'Modellpaket exportiert:',
                            result['package_dir'],
                            '',
                            f'OBJ: {result["obj_path"]}',
                            f'MTL: {result["mtl_path"]}',
                            f'Texturen gesamt: {result["texture_count"]}',
                            f'Als PNG bearbeitbar: {result["editable_png_count"]}',
                            f'Nur Roh-Sicherung: {result["raw_only_count"]}',
                            f'Manifest: {result["manifest_path"]}'
                        ]
                        self.output.delete('1.0', 'end')
                        self.output.insert('1.0', '\n'.join(lines))
                        win.destroy()
                        messagebox.showinfo('Fertig', result['package_dir'])
                        return
                    written = []
                    if mesh_var.get():
                        result = export_model_with_options(self.parsed, entry, out_dir, write_mtl=mtl_var.get(), export_textures=False)
                        if result.get('obj_path'):
                            written.append(result['obj_path'])
                        if result.get('mtl_path'):
                            written.append(result['mtl_path'])
                    if not written:
                        raise PakError('Export with... hat keine Dateien erzeugt')
                    lines = ['Export abgeschlossen:', '']
                    lines.extend(written[:120])
                    if len(written) > 120:
                        lines.append(f'... {len(written) - 120} weitere')
                    self.output.delete('1.0', 'end')
                    self.output.insert('1.0', '\n'.join(lines))
                    win.destroy()
                    messagebox.showinfo('Fertig', f'{len(written)} Datei(en) exportiert')
                except Exception as e:
                    self.output.delete('1.0', 'end')
                    self.output.insert('1.0', f'Fehler: {e}')
                    messagebox.showerror('Fehler', str(e))
            tk.Button(button_row, text='Exportieren', command=run_export, width=16).pack(side='left')
            tk.Button(button_row, text='Abbrechen', command=win.destroy, width=16).pack(side='left', padx=(8, 0))
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def export_model_package_dialog(self):
        try:
            item = self.get_selected_item()
            if item['kind'] != 'entry' or not self.is_model_entry(item['entry']):
                raise PakError('Modellpaket geht nur bei CMDL, SMDL oder WMDL')
            out_dir = filedialog.askdirectory(title='Zielordner für Modellpaket auswählen')
            if not out_dir:
                return
            result = export_model_package(self.parsed, item['entry'], out_dir, require_store=self.require_store)
            lines = [
                'Modellpaket exportiert:',
                result['package_dir'],
                '',
                f'OBJ: {result["obj_path"]}',
                f'MTL: {result["mtl_path"]}',
                f'Texturen gesamt: {result["texture_count"]}',
                f'Als PNG bearbeitbar: {result["editable_png_count"]}',
                f'Nur Roh-Sicherung: {result["raw_only_count"]}',
                f'Manifest: {result["manifest_path"]}'
            ]
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', result['package_dir'])
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def rebuild_model_package_dialog(self):
        if self.parsed is None:
            messagebox.showerror('Fehler', 'Noch keine PAK-Datei eingelesen')
            return
        folder = filedialog.askdirectory(title='Modellpaket-Ordner auswählen')
        if not folder:
            return
        try:
            out_path = filedialog.asksaveasfilename(title='Neues PAK speichern', defaultextension='.pak', initialfile=Path(self.parsed['path']).stem + '_model_repacked.pak', filetypes=[('PAK-Dateien', '*.pak'), ('Alle Dateien', '*.*')])
            if not out_path:
                return
            result = rebuild_model_package_from_folder(self.parsed, folder, out_path)
            self.pak_var.set(result['out_path'])
            self.load_pak()
            lines = [
                'Neue Datei:',
                result['out_path'],
                '',
                f'Geänderte PNGs: {result["changed_count"]}'
            ]
            if result['changed_files']:
                lines.append('')
                lines.extend(result['changed_files'][:60])
                if len(result['changed_files']) > 60:
                    lines.append(f'... {len(result["changed_files"]) - 60} weitere')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', result['out_path'])
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def choose_pak(self):
        path = filedialog.askopenfilename(title='PAK-Datei auswählen', filetypes=[('PAK-Dateien', '*.pak'), ('Alle Dateien', '*.*')])
        if path:
            if is_macos_metadata_path(path):
                messagebox.showerror('Fehler', 'Das ist nur eine macOS-Metadaten-Datei, keine echte PAK-Datei.')
                return
            self.pak_var.set(path)

    def choose_replacement(self):
        path = filedialog.askopenfilename(title='Ersatzdatei auswählen', filetypes=[('Alle Dateien', '*.*')])
        if path:
            if is_macos_metadata_path(path):
                messagebox.showerror('Fehler', 'Das ist nur eine macOS-Metadaten-Datei, keine echte Ersatzdatei.')
                return
            self.repl_var.set(path)

    def import_required_paks(self):
        paths = filedialog.askopenfilenames(title='PAK-Dateien zum Requiren auswählen', filetypes=[('PAK-Dateien', '*.pak'), ('Alle Dateien', '*.*')])
        if not paths:
            return
        paths = [path for path in paths if not is_macos_metadata_path(path)]
        if not paths:
            messagebox.showerror('Fehler', 'Es wurden nur macOS-Metadaten-Dateien ausgewaehlt.')
            return
        try:
            results = self.require_store.add_many(paths)
            self.refresh_list()
            lines = ['Require importiert:', '']
            total_added = 0
            total_replaced = 0
            for item in results:
                total_added += item['added']
                total_replaced += item['replaced']
                lines.append(f'{Path(item["path"]).name} | Einträge {item["entry_count"]} | neu {item["added"]} | überschrieben {item["replaced"]}')
            lines.append('')
            lines.append(f'Gesamt neu: {total_added}')
            lines.append(f'Gesamt überschrieben: {total_replaced}')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', f'{len(results)} Require-Datei(en) importiert')
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def clear_all(self):
        self.parsed = None
        self.visible_items = []
        self.tree_items = {}
        self.last_clicked_iid = ''
        self.tree.delete(*self.tree.get_children())
        self.output.delete('1.0', 'end')
        self.preview.clear()
        self.txtr_preview.clear()
        self.repl_var.set('')
        self.filter_var.set('')
        self.require_store.clear()

    def entry_display_name(self, entry):
        return entry.get('display_name') or entry['name'] or entry['uuid_hex']

    def child_display_name(self, entry, child):
        return f'{self.entry_display_name(entry)} {child["segment_tag"]}'.strip()

    def caud_display_name(self, caud_entry):
        return caud_entry.get('caud_info', {}).get('name', caud_entry['uuid_hex'])
    def type_sort_key(self, kind):
        return (kind or '').strip().upper()

    def size_matches(self, query, size):
        text = query.strip()
        if not text:
            return True
        for op in ('>=', '<=', '>', '<', '='):
            if text.startswith(op):
                value_text = text[len(op):].strip()
                if not value_text.isdigit():
                    return False
                value = int(value_text)
                if op == '>=':
                    return size >= value
                if op == '<=':
                    return size <= value
                if op == '>':
                    return size > value
                if op == '<':
                    return size < value
                return size == value
        return text in str(size)

    def entry_matches(self, entry, query, mode):
        if not query:
            return True
        if mode == 'size':
            return self.size_matches(query, entry['size'])
        if mode == 'type':
            if query in entry['type'].upper():
                return True
            if entry['type'] == 'MTRL':
                shader_kind = (entry.get('mtrl_info') or {}).get('shader_kind', '')
                return query in shader_kind.upper()
            return False
        return query in self.entry_display_name(entry).upper() or query in entry['uuid_hex'].upper() or query in entry['type'].upper()

    def child_matches(self, entry, child, query, mode):
        if not query:
            return True
        if mode == 'size':
            return self.size_matches(query, len(child['inner']))
        if mode == 'type':
            return query in child['inner_kind'].upper() or query in child['segment_tag'].upper()
        return query in self.child_display_name(entry, child).upper() or query in child['inner_kind'].upper()

    def caud_matches(self, caud_entry, query, mode):
        if not query:
            return True
        name = self.caud_display_name(caud_entry)
        if mode == 'size':
            return self.size_matches(query, caud_entry['size'])
        if mode == 'type':
            return query in 'CAUD'
        return query in name.upper() or query in caud_entry['uuid_hex'].upper()

    def model_mtrl_matches(self, material, query, mode):
        if not query:
            return True
        if mode == 'size':
            return False
        if mode == 'type':
            return query in 'MTRL' or query in material['mat_type'].upper()
        return query in material['name'].upper() or query in material['uuid_hex'].upper() or query in material['mat_type'].upper()

    def model_txtr_matches(self, ref, query, mode):
        if not query:
            return True
        if mode == 'size':
            return False
        if mode == 'type':
            return query in 'TXTR' or query in ref['tag'].upper()
        return query in ref['uuid_hex'].upper() or query in ref['tag'].upper()

    def get_txtr_entry_for_ref(self, ref):
        entry, _ = self.get_resolved_txtr_entry_for_ref(ref)
        return entry
    
    def get_resolved_txtr_entry_for_ref(self, ref):
        entry, source = self.require_store.resolve_entry(self.parsed, ref['uuid_hex'])
        return entry, source

    def is_missing_model_txtr_ref(self, ref):
        entry, _ = self.get_resolved_txtr_entry_for_ref(ref)
        return entry is None

    def model_txtr_matches(self, ref, query, mode):
        if mode == 'missing':
            return self.is_missing_model_txtr_ref(ref)
        if not query:
            return True
        if mode == 'size':
            return False
        if mode == 'type':
            return query in 'TXTR' or query in ref['tag'].upper()
        entry, source = self.get_resolved_txtr_entry_for_ref(ref)
        source_text = source.upper() if source else ''
        entry_name = ''
        if entry is not None:
            entry_name = (entry.get('display_name') or entry.get('name') or entry['uuid_hex']).upper()
        return query in ref['uuid_hex'].upper() or query in ref['tag'].upper() or query in entry_name or query in source_text

    def entry_matches(self, entry, query, mode):
        if mode == 'missing':
            return False
        if not query:
            return True
        if mode == 'size':
            return self.size_matches(query, entry['size'])
        if mode == 'type':
            if query in entry['type'].upper():
                return True
            if entry['type'] == 'MTRL':
                shader_kind = (entry.get('mtrl_info') or {}).get('shader_kind', '')
                return query in shader_kind.upper()
            return False
        return query in self.entry_display_name(entry).upper() or query in entry['uuid_hex'].upper() or query in entry['type'].upper()

    def child_matches(self, entry, child, query, mode):
        if mode == 'missing':
            return False
        if not query:
            return True
        if mode == 'size':
            return self.size_matches(query, len(child['inner']))
        if mode == 'type':
            return query in child['inner_kind'].upper() or query in child['segment_tag'].upper()
        return query in self.child_display_name(entry, child).upper() or query in child['inner_kind'].upper()

    def caud_matches(self, caud_entry, query, mode):
        if mode == 'missing':
            return False
        if not query:
            return True
        name = self.caud_display_name(caud_entry)
        if mode == 'size':
            return self.size_matches(query, caud_entry['size'])
        if mode == 'type':
            return query in 'CAUD'
        return query in name.upper() or query in caud_entry['uuid_hex'].upper()

    def model_mtrl_matches(self, material, query, mode):
        if mode == 'missing':
            return any(self.is_missing_model_txtr_ref(ref) for ref in material.get('txtr_refs', []))
        if not query:
            return True
        if mode == 'size':
            return False
        if mode == 'type':
            return query in 'MTRL' or query in material['mat_type'].upper()
        return query in material['name'].upper() or query in material['uuid_hex'].upper() or query in material['mat_type'].upper()

    def get_tree_tags_for_item(self, item):
        if item['kind'] == 'model_txtr_child':
            entry, source = self.get_resolved_txtr_entry_for_ref(item['ref'])
            if entry is None:
                return ('missing_ref',)
            if source == 'require':
                return ('required_ref',)
        return ()

    def type_group_label(self, kind):
        label = ASSET_TYPE_LABELS.get(kind, '')
        if label:
            return f'{kind} — {label}'
        return kind

    def build_grouped_type_items(self, query):
        grouped_entries = {}
        children_by_entry = {}
        for entry in self.parsed['entries']:
            entry_match = self.entry_matches(entry, query, 'type')
            matching_children = []
            if entry['is_bundle']:
                for child in entry['bundle']['children']:
                    if self.child_matches(entry, child, query, 'type'):
                        matching_children.append({'kind': 'bundle_child', 'child': child})
            matching_cauds = []
            if entry['type'] == 'CSMP' and self.parsed.get('csmp_to_cauds'):
                for caud_entry in self.parsed['csmp_to_cauds'].get(entry['uuid_hex'], []):
                    if self.caud_matches(caud_entry, query, 'type'):
                        matching_cauds.append({'kind': 'caud_child', 'caud_entry': caud_entry})
            matching_mtrls = []
            if entry['type'] in ('WMDL', 'CMDL', 'SMDL', 'CHAR'):
                for material in entry.get('model_materials', []):
                    txtr_children = []
                    for ref in material.get('txtr_refs', []):
                        if self.model_txtr_matches(ref, query, 'type'):
                            txtr_children.append({'kind': 'model_txtr_child', 'ref': ref})
                    if self.model_mtrl_matches(material, query, 'type') or txtr_children:
                        matching_mtrls.append({'kind': 'model_mtrl_child', 'material': material, 'txtr_children': txtr_children})
            if not entry_match and not matching_children and not matching_cauds and not matching_mtrls:
                continue
            grouped_entries.setdefault(entry['type'], []).append(entry)
            children_by_entry[entry['index']] = {
                'entry_match': entry_match,
                'bundle_children': matching_children,
                'caud_children': matching_cauds,
                'mtrl_children': matching_mtrls
            }
        return grouped_entries, children_by_entry
    
    def refresh_list(self):
        self.tree_items = {}
        self.last_clicked_iid = ''
        self.tree.delete(*self.tree.get_children())
        if self.parsed is None:
            return
        query = self.filter_var.get().strip().upper()
        mode = self.filter_mode_var.get()
        if mode == 'type':
            groups, children_by_entry = self.build_grouped_type_items(query)
            for kind in sorted(groups, key=lambda k: k.upper()):
                group_iid = f'group_{kind}'
                entries = groups[kind]
                self.tree.insert('', 'end', iid=group_iid, text=f'{self.type_group_label(kind)} ({len(entries)})', open=bool(query))
                for entry in sorted(entries, key=lambda e: (self.entry_display_name(e).upper(), e['index'])):
                    entry_iid = f'entry_{entry["index"]}'
                    self.tree.insert(group_iid, 'end', iid=entry_iid, text=make_entry_label(entry), open=False)
                    self.tree_items[entry_iid] = {'kind': 'entry', 'entry': entry}
                    child_info = children_by_entry.get(entry['index'], {})
                    bundle_children = entry['bundle']['children'] if child_info.get('entry_match') and not query and entry['is_bundle'] else [item['child'] for item in child_info.get('bundle_children', [])]
                    for child in bundle_children:
                        child_iid = f'entry_{entry["index"]}_child_{child["index"]}'
                        self.tree.insert(entry_iid, 'end', iid=child_iid, text=make_child_label(entry, child))
                        self.tree_items[child_iid] = {'kind': 'bundle_child', 'entry': entry, 'child': child}
                    caud_children = self.parsed['csmp_to_cauds'].get(entry['uuid_hex'], []) if child_info.get('entry_match') and not query and entry['type'] == 'CSMP' and self.parsed.get('csmp_to_cauds') else [item['caud_entry'] for item in child_info.get('caud_children', [])]
                    for caud_entry in caud_children:
                        caud_iid = f'entry_{entry["index"]}_caud_{caud_entry["index"]}'
                        caud_label = f'  CAUD | {self.caud_display_name(caud_entry)} | Größe {caud_entry["size"]}'
                        self.tree.insert(entry_iid, 'end', iid=caud_iid, text=caud_label)
                        self.tree_items[caud_iid] = {'kind': 'caud_child', 'entry': entry, 'caud_entry': caud_entry}
                    mtrl_children = child_info.get('mtrl_children', [])
                    if child_info.get('entry_match') and not query and entry['type'] in ('WMDL', 'CMDL', 'SMDL', 'CHAR'):
                        mtrl_children = [{'kind': 'model_mtrl_child', 'material': material, 'txtr_children': [{'kind': 'model_txtr_child', 'ref': ref} for ref in material.get('txtr_refs', [])]} for material in entry.get('model_materials', [])]
                    for material_item in mtrl_children:
                        material = material_item['material']
                        child_iid = f'entry_{entry["index"]}_mtrl_{material["index"]}'
                        self.tree.insert(entry_iid, 'end', iid=child_iid, text=make_mtrl_ref_label(material))
                        self.tree_items[child_iid] = {'kind': 'model_mtrl_child', 'entry': entry, 'material': material}
                        txtr_children = material_item.get('txtr_children', [])
                        if query == '':
                            txtr_children = [{'kind': 'model_txtr_child', 'ref': ref} for ref in material.get('txtr_refs', [])]
                        for ref_item in txtr_children:
                            ref = ref_item['ref']
                            txtr_entry = self.get_txtr_entry_for_ref(ref)
                            txtr_iid = f'entry_{entry["index"]}_mtrl_{material["index"]}_txtr_{ref["tag"]}_{ref["uuid_hex"]}'
                            self.tree.insert(child_iid, 'end', iid=txtr_iid, text=make_txtr_ref_label(ref, txtr_entry), tags=self.get_tree_tags_for_item({'kind': 'model_txtr_child', 'ref': ref}))
                            self.tree_items[txtr_iid] = {'kind': 'model_txtr_child', 'entry': entry, 'material': material, 'ref': ref, 'txtr_entry': txtr_entry}
            return
        entries = list(self.parsed['entries'])
        if mode == 'size':
            entries.sort(key=lambda entry: (-entry['size'], self.entry_display_name(entry).upper(), entry['index']))
        else:
            entries.sort(key=lambda entry: (self.entry_display_name(entry).upper(), entry['type'], entry['index']))
        for entry in entries:
            entry_match = self.entry_matches(entry, query, mode)
            matching_children = []
            if entry['is_bundle']:
                for child in entry['bundle']['children']:
                    if self.child_matches(entry, child, query, mode):
                        matching_children.append(child)
            matching_cauds = []
            if entry['type'] == 'CSMP' and self.parsed.get('csmp_to_cauds'):
                for caud_entry in self.parsed['csmp_to_cauds'].get(entry['uuid_hex'], []):
                    if self.caud_matches(caud_entry, query, mode):
                        matching_cauds.append(caud_entry)
            matching_mtrls = []
            if entry['type'] in ('WMDL', 'CMDL', 'SMDL', 'CHAR'):
                for material in entry.get('model_materials', []):
                    if self.model_mtrl_matches(material, query, mode):
                        matching_mtrls.append(material)
            if not entry_match and not matching_children and not matching_cauds and not matching_mtrls:
                continue
            entry_iid = f'entry_{entry["index"]}'
            self.tree.insert('', 'end', iid=entry_iid, text=make_entry_label(entry), open=bool(query))
            self.tree_items[entry_iid] = {'kind': 'entry', 'entry': entry}
            if entry['is_bundle']:
                children = list(entry['bundle']['children'])
                if mode == 'size':
                    children.sort(key=lambda child: (-len(child['inner']), self.child_display_name(entry, child).upper(), child['index']))
                else:
                    children.sort(key=lambda child: (self.child_display_name(entry, child).upper(), child['segment_tag'], child['index']))
                children_to_show = children if entry_match and not query else matching_children
                for child in children_to_show:
                    child_iid = f'entry_{entry["index"]}_child_{child["index"]}'
                    self.tree.insert(entry_iid, 'end', iid=child_iid, text=make_child_label(entry, child))
                    self.tree_items[child_iid] = {'kind': 'bundle_child', 'entry': entry, 'child': child}
            if entry['type'] == 'CSMP' and self.parsed.get('csmp_to_cauds'):
                caud_entries = list(self.parsed['csmp_to_cauds'].get(entry['uuid_hex'], []))
                if mode == 'size':
                    caud_entries.sort(key=lambda ce: (-ce['size'], self.caud_display_name(ce).upper(), ce['index']))
                else:
                    caud_entries.sort(key=lambda ce: (self.caud_display_name(ce).upper(), ce['index']))
                cauds_to_show = caud_entries if entry_match and not query else matching_cauds
                for caud_entry in cauds_to_show:
                    caud_iid = f'entry_{entry["index"]}_caud_{caud_entry["index"]}'
                    caud_label = f'  CAUD | {self.caud_display_name(caud_entry)} | Größe {caud_entry["size"]}'
                    self.tree.insert(entry_iid, 'end', iid=caud_iid, text=caud_label)
                    self.tree_items[caud_iid] = {'kind': 'caud_child', 'entry': entry, 'caud_entry': caud_entry}
            if entry['type'] in ('WMDL', 'CMDL', 'SMDL', 'CHAR'):
                materials = list(entry.get('model_materials', []))
                if mode == 'size':
                    materials.sort(key=lambda material: (material['name'].upper(), material['index']))
                else:
                    materials.sort(key=lambda material: (material['name'].upper(), material['mat_type'].upper(), material['index']))
                mats_to_show = materials if entry_match and not query else matching_mtrls
                for material in mats_to_show:
                    child_iid = f'entry_{entry["index"]}_mtrl_{material["index"]}'
                    self.tree.insert(entry_iid, 'end', iid=child_iid, text=make_mtrl_ref_label(material))
                    self.tree_items[child_iid] = {'kind': 'model_mtrl_child', 'entry': entry, 'material': material}
                    txtr_refs = material.get('txtr_refs', []) if entry_match and not query else [ref for ref in material.get('txtr_refs', []) if self.model_txtr_matches(ref, query, mode)]
                    for ref in txtr_refs:
                        txtr_entry = self.get_txtr_entry_for_ref(ref)
                        txtr_iid = f'entry_{entry["index"]}_mtrl_{material["index"]}_txtr_{ref["tag"]}_{ref["uuid_hex"]}'
                        self.tree.insert(child_iid, 'end', iid=txtr_iid, text=make_txtr_ref_label(ref, txtr_entry))
                        self.tree_items[txtr_iid] = {'kind': 'model_txtr_child', 'entry': entry, 'material': material, 'ref': ref, 'txtr_entry': txtr_entry}

    def remember_tree_click(self, event=None):
        iid = self.tree.identify_row(event.y) if event is not None else self.tree.focus()
        if iid:
            self.last_clicked_iid = iid
        self.root.after_idle(self.show_selected)

    def get_display_iid(self):
        focus = self.tree.focus()
        if focus and self.tree.exists(focus):
            return focus
        if self.last_clicked_iid and self.tree.exists(self.last_clicked_iid):
            return self.last_clicked_iid
        sel = self.tree.selection()
        for iid in reversed(sel):
            if self.tree.exists(iid):
                return iid
        return ''

    def get_selected_items(self):
        if self.parsed is None:
            raise PakError('Noch keine PAK-Datei eingelesen')
        items = []
        for iid in self.tree.selection():
            item = self.tree_items.get(iid)
            if item is not None:
                items.append(item)
        if items:
            return items
        display_iid = self.get_display_iid()
        item = self.tree_items.get(display_iid) if display_iid else None
        if item is None:
            raise PakError('Bitte einen Eintrag oder eine Unterdatei auswählen')
        return [item]

    def make_unique_output_path(self, folder, filename):
        folder = Path(folder)
        target = folder / filename
        if not target.exists():
            return target
        suffix = ''.join(Path(filename).suffixes)
        stem = filename[:-len(suffix)] if suffix else filename
        number = 2
        while True:
            candidate = folder / f'{stem}_{number}{suffix}'
            if not candidate.exists():
                return candidate
            number += 1

    def build_payload_export(self, item):
        if item['kind'] == 'entry':
            entry = item['entry']
            asset = get_entry_asset(self.parsed, entry)
            base = self.selected_base_name(entry)
            if entry['is_bundle']:
                payload = get_entry_payload(asset)
                default_name = base + '.__bundle__.bin'
            else:
                payload = asset
                default_name = base + kind_to_ext(entry['type'])
            return default_name, payload
        if item['kind'] == 'bundle_child':
            entry = item['entry']
            child = item['child']
            payload = child['inner']
            base = self.selected_base_name(entry) + '__' + child['segment_tag']
            default_name = base + kind_to_ext(child['inner_kind'])
            return default_name, payload
        if item['kind'] == 'caud_child':
            caud_entry = item['caud_entry']
            asset = get_entry_asset(self.parsed, caud_entry)
            base = self.selected_base_name(caud_entry)
            default_name = base + kind_to_ext(caud_entry['type'])
            return default_name, asset
        if item['kind'] == 'model_mtrl_child':
            material = item['material']
            filename = safe_name(material['name']) + '_' + material['uuid_hex'] + '.mtrlref.txt'
            lines = format_model_material_lines(material)
            return filename, '\n'.join(lines).encode('utf-8')
        if item['kind'] == 'model_txtr_child':
            asset, txtr_entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            if txtr_entry is None or asset is None:
                raise PakError('Verlinktes TXTR ist weder im aktuellen PAK noch in den requireten Dateien vorhanden')
            base = self.selected_base_name(txtr_entry)
            default_name = base + kind_to_ext(txtr_entry['type'])
            return default_name, asset
        raise PakError('Auswahl konnte nicht exportiert werden')

    def build_whole_export(self, item):
        if item['kind'] == 'entry':
            entry = item['entry']
            data = get_entry_asset(self.parsed, entry)
            base = self.selected_base_name(entry)
            default_name = base + '.' + entry['type'].lower() + '.bin'
            return default_name, data
        if item['kind'] == 'bundle_child':
            entry = item['entry']
            child = item['child']
            data = build_segment_blob(child)
            base = self.selected_base_name(entry) + '__' + child['segment_tag']
            default_name = base + '.__wrapped__.bin'
            return default_name, data
        if item['kind'] == 'caud_child':
            caud_entry = item['caud_entry']
            data = get_entry_asset(self.parsed, caud_entry)
            base = self.selected_base_name(caud_entry)
            default_name = base + '.' + caud_entry['type'].lower() + '.bin'
            return default_name, data
        if item['kind'] == 'model_mtrl_child':
            material = item['material']
            filename = safe_name(material['name']) + '_' + material['uuid_hex'] + '.mtrlref.txt'
            lines = format_model_material_lines(material)
            return filename, '\n'.join(lines).encode('utf-8')
        if item['kind'] == 'model_txtr_child':
            data, txtr_entry, source = self.require_store.resolve_asset(self.parsed, item['ref']['uuid_hex'])
            if txtr_entry is None or data is None:
                raise PakError('Verlinktes TXTR ist weder im aktuellen PAK noch in den requireten Dateien vorhanden')
            base = self.selected_base_name(txtr_entry)
            default_name = base + '.' + txtr_entry['type'].lower() + '.bin'
            return default_name, data
        raise PakError('Auswahl konnte nicht exportiert werden')

    def on_filter_changed(self, *args):
        self.refresh_list()

    def load_pak(self):
        path = self.pak_var.get().strip()
        if not path:
            messagebox.showerror('Fehler', 'Bitte zuerst eine PAK-Datei auswählen')
            return
        try:
            self.parsed = parse_pak(path)
            self.refresh_list()
            self.preview.clear()
            self.txtr_preview.clear()
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', analyze_text(self.parsed))
        except Exception as e:
            self.parsed = None
            self.visible_items = []
            self.tree_items = {}
            self.last_clicked_iid = ''
            self.tree.delete(*self.tree.get_children())
            self.preview.clear()
            self.txtr_preview.clear()
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def validate_current(self):
        if self.parsed is None:
            messagebox.showerror('Fehler', 'Noch keine PAK-Datei eingelesen')
            return
        self.preview.clear()
        self.txtr_preview.clear()
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', analyze_text(self.parsed))
        errors = [x for x in self.parsed['issues'] if x['level'] == 'error']
        if errors:
            messagebox.showwarning('Validierung', f'{len(errors)} Fehler gefunden')
        else:
            messagebox.showinfo('Validierung', 'Keine harten Fehler gefunden')

    def get_selected_item(self):
        if self.parsed is None:
            raise PakError('Noch keine PAK-Datei eingelesen')
        iid = self.get_display_iid()
        if not iid:
            raise PakError('Bitte einen Eintrag oder eine Unterdatei auswählen')
        item = self.tree_items.get(iid)
        if item is None:
            raise PakError('Auswahl konnte nicht gelesen werden')
        return item

    def selected_base_name(self, entry):
        uid = entry['uuid_hex']
        formatted_uid = f'{uid[:8]}-{uid[8:12]}-{uid[12:16]}-{uid[16:20]}-{uid[20:]}'
        display_name = entry.get('display_name') or entry['name']
        if display_name:
            return f'{safe_name(display_name)}_{formatted_uid}'
        return formatted_uid

    def ask_output_pak_path(self, entry, child=None, suffix='rebuilt'):
        source = Path(self.parsed['path'])
        base = self.selected_base_name(entry)
        if child is not None:
            base = f'{base}_{child["segment_tag"]}'
        default_name = f'{source.stem}_{base}_{suffix}{source.suffix or ".pak"}'
        return filedialog.asksaveasfilename(title='Neues PAK speichern', defaultextension=source.suffix or '.pak', initialfile=default_name, filetypes=[('PAK-Dateien', '*.pak'), ('Alle Dateien', '*.*')])

    def export_selected_payload(self):
        try:
            items = self.get_selected_items()
            if len(items) == 1:
                default_name, payload = self.build_payload_export(items[0])
                out_path = filedialog.asksaveasfilename(title='Inhalt exportieren', initialfile=default_name, filetypes=[('Alle Dateien', '*.*')])
                if not out_path:
                    return
                Path(out_path).write_bytes(payload)
                self.output.delete('1.0', 'end')
                self.output.insert('1.0', f'Inhalt exportiert:\n{out_path}')
                messagebox.showinfo('Fertig', f'Inhalt exportiert:\n{out_path}')
                return
            out_dir = filedialog.askdirectory(title='Export-Ordner auswählen')
            if not out_dir:
                return
            written_paths = []
            for item in items:
                default_name, payload = self.build_payload_export(item)
                out_path = self.make_unique_output_path(out_dir, default_name)
                out_path.write_bytes(payload)
                written_paths.append(str(out_path))
            lines = [f'{len(written_paths)} Inhalte exportiert nach:', out_dir, '']
            lines.extend(written_paths[:30])
            if len(written_paths) > 30:
                lines.append(f'... {len(written_paths) - 30} weitere')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', f'{len(written_paths)} Inhalte exportiert nach:\n{out_dir}')
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def export_selected_whole(self):
        try:
            items = self.get_selected_items()
            if len(items) == 1:
                default_name, data = self.build_whole_export(items[0])
                out_path = filedialog.asksaveasfilename(title='Ganz exportieren', initialfile=default_name, filetypes=[('Alle Dateien', '*.*')])
                if not out_path:
                    return
                Path(out_path).write_bytes(data)
                self.output.delete('1.0', 'end')
                self.output.insert('1.0', f'Ganz exportiert:\n{out_path}')
                messagebox.showinfo('Fertig', f'Ganz exportiert:\n{out_path}')
                return
            out_dir = filedialog.askdirectory(title='Export-Ordner auswählen')
            if not out_dir:
                return
            written_paths = []
            for item in items:
                default_name, data = self.build_whole_export(item)
                out_path = self.make_unique_output_path(out_dir, default_name)
                out_path.write_bytes(data)
                written_paths.append(str(out_path))
            lines = [f'{len(written_paths)} Dateien ganz exportiert nach:', out_dir, '']
            lines.extend(written_paths[:30])
            if len(written_paths) > 30:
                lines.append(f'... {len(written_paths) - 30} weitere')
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', '\n'.join(lines))
            messagebox.showinfo('Fertig', f'{len(written_paths)} Dateien ganz exportiert nach:\n{out_dir}')
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def export_all_dialog(self):
        if self.parsed is None:
            messagebox.showerror('Fehler', 'Noch keine PAK-Datei eingelesen')
            return
        out_dir = filedialog.askdirectory(title='Export-Ordner auswählen')
        if not out_dir:
            return
        try:
            manifest = export_all(self.parsed, out_dir)
            bundle_entries = sum(1 for item in manifest['entries'] if item.get('is_bundle'))
            bundle_children = sum(len(item.get('bundle_children', [])) for item in manifest['entries'])
            meta_entries = sum(1 for item in manifest['entries'] if item.get('has_meta'))
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Alles exportiert nach:\n{out_dir}\n\nmanifest.json wurde erstellt.\nBundle-Einträge: {bundle_entries}\nUnterdateien: {bundle_children}\nMETA-Einträge: {meta_entries}')
            messagebox.showinfo('Fertig', f'Alles exportiert nach:\n{out_dir}')
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
        lines = []
        preview_data = None
        preview_label = ''
        txtr_preview_data = None
        txtr_preview_label = ''
        if item['kind'] == 'entry':
            entry = item['entry']
            asset = get_entry_asset(self.parsed, entry)
            payload = get_entry_payload(asset)
            name = self.entry_display_name(entry)
            lines.append(f'Index: {entry["index"]}')
            lines.append(f'Typ: {entry["type"]}')
            lines.append(f'Name: {name}')
            lines.append(f'UUID: {entry["uuid_hex"]}')
            lines.append(f'Offset: {entry["offset"]}')
            lines.append(f'Größe: {entry["size"]}')
            lines.append(f'Payload-Größe: {len(payload)}')
            lines.append(f'Payload-Kennung: {entry["payload_kind"] or "unbekannt"}')
            lines.extend(format_meta_lines(entry))
            if entry['type'] == 'MTRL':
                lines.append('')
                lines.extend(format_mtrl_info_lines(entry, self.parsed))
            lines.append(f'Asset-SHA1: {entry["asset_sha1"]}')
            lines.append(f'Payload-SHA1: {entry["payload_sha1"]}')
            if entry['type'] == 'CSMP':
                preview_data = asset
                preview_label = name
                try:
                    from soundpreview import parse_csmp_info
                    csmp_info = parse_csmp_info(asset)
                    duration = csmp_info['duration']
                    lines.append(f'Dauer: {duration:.2f}s')
                    lines.append(f'Samplerate: {csmp_info["sample_rate"]} Hz')
                    lines.append(f'Kanäle: {csmp_info["channels"]}')
                    if csmp_info.get('loop_flag') and csmp_info['sample_rate'] > 0:
                        sr = csmp_info['sample_rate']
                        ls = csmp_info['loop_start_sample']
                        le = csmp_info['loop_end_sample']
                        lines.append(f'Loop: ja')
                        lines.append(f'Loop-Start: {ls/sr:.4f}s (Sample {ls})')
                        lines.append(f'Loop-Ende: {le/sr:.4f}s (Sample {le})')
                        lines.append(f'Loop-Länge: {(le-ls)/sr:.4f}s (Samples {le-ls})')
                    else:
                        lines.append(f'Loop: nein')
                except Exception:
                    pass
            if entry['type'] == 'TXTR':
                txtr_preview_data = asset
                txtr_preview_label = name
            if entry['type'] == 'CAUD':
                caud_info = entry.get('caud_info')
                if caud_info:
                    lines.append('')
                    lines.extend(format_caud_lines(caud_info))
                else:
                    lines.append('')
                    lines.append('CAUD konnte nicht gelesen werden.')
            if entry['is_bundle']:
                lines.append('')
                lines.append(f'Bundle erkannt: {entry["bundle_count"]} Unterdateien')
                for child in entry['bundle']['children']:
                    lines.append(f'- {child["segment_tag"]} | {child["inner_kind"]} | Größe {len(child["inner"])}')
                lines.append('')
                lines.append('Bei "Inhalt exportieren" wird hier das komplette Asset exportiert.')
                lines.append('Die einzelnen Unterdateien können darunter separat ausgewählt werden.')
        elif item['kind'] == 'caud_child':
            entry = item['entry']
            caud_entry = item['caud_entry']
            caud_info = caud_entry.get('caud_info')
            lines.append(f'Übergeordnete CSMP: #{entry["index"]}')
            lines.append(f'CSMP-Name: {self.entry_display_name(entry)}')
            lines.append(f'CSMP-UUID: {entry["uuid_hex"]}')
            lines.append('')
            lines.append(f'CAUD-Eintrag: #{caud_entry["index"]}')
            lines.append(f'CAUD-UUID: {caud_entry["uuid_hex"]}')
            lines.append(f'CAUD-Größe: {caud_entry["size"]}')
            if caud_info:
                lines.append('')
                lines.extend(format_caud_lines(caud_info))
            else:
                lines.append('')
                lines.append('CAUD konnte nicht gelesen werden.')
        elif item['kind'] == 'model_mtrl_child':
            entry = item['entry']
            material = item['material']
            lines.append(f'Übergeordnetes Modell: #{entry["index"]} {entry["type"]}')
            lines.append(f'Modell-Name: {self.entry_display_name(entry)}')
            lines.append(f'Modell-UUID: {entry["uuid_hex"]}')
            lines.append('')
            lines.extend(format_model_material_lines(material))
            linked_mtrl = next((candidate for candidate in self.parsed['entries'] if candidate['type'] == 'MTRL' and candidate['uuid_hex'] == material['uuid_hex']), None)
            if linked_mtrl is not None:
                lines.append('')
                lines.append(f'Verlinktes MTRL: #{linked_mtrl["index"]}')
                lines.append(f'MTRL-Name: {self.entry_display_name(linked_mtrl)}')
                lines.append(f'MTRL-UUID: {linked_mtrl["uuid_hex"]}')
                lines.append(f'MTRL-Größe: {linked_mtrl["size"]}')
                lines.append('')
                lines.extend(format_meta_lines(linked_mtrl))
                lines.append('')
                lines.extend(format_mtrl_info_lines(linked_mtrl, self.parsed))
            else:
                lines.append('')
                lines.append(f'Verlinktes MTRL im aktuellen PAK nicht gefunden: {material["uuid_hex"]}')
        elif item['kind'] == 'model_txtr_child':
            entry = item['entry']
            material = item['material']
            ref = item['ref']
            txtr_entry, txtr_source = self.get_resolved_txtr_entry_for_ref(ref)
            lines.append(f'Übergeordnetes Modell: #{entry["index"]} {entry["type"]}')
            lines.append(f'Modell-Name: {self.entry_display_name(entry)}')
            lines.append(f'Modell-UUID: {entry["uuid_hex"]}')
            lines.append('')
            lines.append(f'Material-Slot: #{material["index"]} {material["name"]}')
            lines.append(f'Slot-UUID: {material["uuid_hex"]}')
            lines.append('')
            lines.extend(format_txtr_ref_lines(ref, txtr_entry))
            if txtr_entry is None:
                lines.append('')
                lines.append('Status: Missing')
            else:
                lines.append('')
                lines.append(f'Quelle: {"Aktuelles PAK" if txtr_source == "pak" else "Require"}')
                if txtr_source == 'pak':
                    asset = get_entry_asset(self.parsed, txtr_entry)
                    txtr_preview_data = asset
                    txtr_preview_label = self.entry_display_name(txtr_entry)
                    lines.append(f'Asset-SHA1: {txtr_entry["asset_sha1"]}')
                    lines.append(f'Payload-SHA1: {txtr_entry["payload_sha1"]}')
                else:
                    asset = self.require_store.get_required_asset(ref['uuid_hex'])
                    txtr_preview_data = asset
                    txtr_preview_label = self.entry_display_name(txtr_entry)
                    lines.append(f'Require-Pfad: {self.require_store.get_required_source(ref["uuid_hex"])}')
        else:
            entry = item['entry']
            child = item['child']
            name = self.entry_display_name(entry)
            lines.append(f'Übergeordneter Eintrag: #{entry["index"]} {entry["type"]}')
            lines.append(f'Name: {name}')
            lines.append(f'Sprachblock: {child["segment_tag"]}')
            lines.append(f'Inhaltstyp: {child["inner_kind"]}')
            lines.append(f'Block-Offset im Bundle: 0x{child["off"]:X}')
            lines.append(f'Wrapper-Größe: {24 + len(child["inner"])}')
            lines.append(f'Inhalt-Größe: {len(child["inner"])}')
            lines.append(f'Inhalt-SHA1: {child["inner_sha1"]}')
            lines.append(f'Wrapper-SHA1: {child["whole_sha1"]}')
            lines.append('')
            lines.append('Bei "Inhalt exportieren" wird hier die echte Unterdatei gespeichert.')
            lines.append('Bei "Ganz exportieren" wird der einzelne umhüllte Block gespeichert.')
            lines.append('Direktes Ersetzen baut danach das Bundle, META und das PAK neu auf.')
            if child['inner_kind'] == 'CSMP':
                preview_data = child['inner']
                preview_label = f'{name} {child["segment_tag"]}'
                try:
                    from soundpreview import parse_csmp_info
                    csmp_info = parse_csmp_info(child['inner'])
                    duration = csmp_info['duration']
                    lines.append(f'Dauer: {duration:.2f}s')
                    lines.append(f'Samplerate: {csmp_info["sample_rate"]} Hz')
                    lines.append(f'Kanäle: {csmp_info["channels"]}')
                    if csmp_info.get('loop_flag') and csmp_info['sample_rate'] > 0:
                        sr = csmp_info['sample_rate']
                        ls = csmp_info['loop_start_sample']
                        le = csmp_info['loop_end_sample']
                        lines.append(f'Loop: ja')
                        lines.append(f'Loop-Start: {ls/sr:.4f}s (Sample {ls})')
                        lines.append(f'Loop-Ende: {le/sr:.4f}s (Sample {le})')
                        lines.append(f'Loop-Länge: {(le-ls)/sr:.4f}s (Samples {le-ls})')
                    else:
                        lines.append(f'Loop: nein')
                except Exception:
                    pass
            if child['inner_kind'] == 'TXTR':
                txtr_preview_data = child['inner']
                txtr_preview_label = f'{name} {child["segment_tag"]}'
        self.output.delete('1.0', 'end')
        self.output.insert('1.0', '\n'.join(lines))
        if preview_data is not None:
            try:
                self.preview.load_csmp(preview_data, preview_label)
            except Exception as e:
                self.preview.clear()
                self.output.insert('end', f'\n\nCSMP-Vorschau konnte nicht geladen werden:\n{e}')
        else:
            self.preview.clear()
        if txtr_preview_data is not None:
            try:
                self.txtr_preview.load_txtr(txtr_preview_data, txtr_preview_label)
            except Exception as e:
                self.txtr_preview.clear()
                self.output.insert('end', f'\n\nTXTR-Vorschau konnte nicht geladen werden:\n{e}')
        else:
            self.txtr_preview.clear()

    def run_replace(self, replacement_path):
        item = self.get_selected_item()
        if item['kind'] not in ('entry', 'bundle_child', 'model_txtr_child'):
            raise PakError('Nur echte Einträge, Bundle-Unterdateien oder verlinkte TXTRs können direkt ersetzt werden')
        if item['kind'] == 'entry':
            entry = item['entry']
            out_path = self.ask_output_pak_path(entry)
            if not out_path:
                return None
            replacements = {entry['index']: {'path': replacement_path, 'mode': self.mode_var.get()}}
        elif item['kind'] == 'bundle_child':
            entry = item['entry']
            child = item['child']
            out_path = self.ask_output_pak_path(entry, child=child)
            if not out_path:
                return None
            rebuilt_asset = build_bundle_replaced_asset(self.parsed, entry, {child['index']: {'path': replacement_path, 'mode': self.mode_var.get()}})
            replacements = {entry['index']: {'asset_bytes': rebuilt_asset}}
        else:
            txtr_entry = item.get('txtr_entry')
            if txtr_entry is None:
                raise PakError('Verlinktes TXTR ist im aktuellen PAK nicht vorhanden')
            out_path = self.ask_output_pak_path(txtr_entry)
            if not out_path:
                return None
            replacements = {txtr_entry['index']: {'path': replacement_path, 'mode': self.mode_var.get()}}
        out_path = rebuild_pak(self.parsed, replacements, out_path)
        self.pak_var.set(out_path)
        self.load_pak()
        self.output.delete('1.0', 'end')
        if item['kind'] == 'entry':
            self.output.insert('1.0', f'Neue Datei:\n{out_path}\n\nErsetzter Eintrag:\n{entry["type"]} | {entry["name"] if entry["name"] else entry["uuid_hex"]}')
        elif item['kind'] == 'bundle_child':
            self.output.insert('1.0', f'Neue Datei:\n{out_path}\n\nErsetzter Untereintrag:\n{entry["type"]} | {child["segment_tag"]} | {child["inner_kind"]}')
        else:
            self.output.insert('1.0', f'Neue Datei:\n{out_path}\n\nErsetztes verlinktes TXTR:\n{txtr_entry["type"]} | {self.entry_display_name(txtr_entry)}')
        messagebox.showinfo('Fertig', f'Neue Datei geschrieben:\n{out_path}')
        return out_path

    def replace_selected_direct(self):
        try:
            item = self.get_selected_item()
            if item['kind'] not in ('entry', 'bundle_child', 'model_txtr_child'):
                raise PakError('Nur echte Einträge, Bundle-Unterdateien oder verlinkte TXTRs können direkt ersetzt werden')
            filetypes = [('Alle Dateien', '*.*')]
            if item['kind'] == 'entry':
                if item['entry']['type'] == 'TXTR':
                    filetypes = [('PNG oder TXTR', '*.png *.txtr *.bin'), ('PNG-Dateien', '*.png'), ('Alle Dateien', '*.*')]
                title = f'Ersatzdatei für {item["entry"]["type"]} auswählen'
            elif item['kind'] == 'bundle_child':
                if item['child']['inner_kind'] == 'TXTR':
                    filetypes = [('PNG oder TXTR', '*.png *.txtr *.bin'), ('PNG-Dateien', '*.png'), ('Alle Dateien', '*.*')]
                title = f'Ersatzdatei für {item["child"]["segment_tag"]} {item["child"]["inner_kind"]} auswählen'
            else:
                txtr_entry = item.get('txtr_entry')
                if txtr_entry is None:
                    raise PakError('Verlinktes TXTR ist im aktuellen PAK nicht vorhanden')
                filetypes = [('PNG oder TXTR', '*.png *.txtr *.bin'), ('PNG-Dateien', '*.png'), ('Alle Dateien', '*.*')]
                title = f'Ersatzdatei für verlinktes TXTR {self.entry_display_name(txtr_entry)} auswählen'
            replacement = filedialog.askopenfilename(title=title, filetypes=filetypes)
            if not replacement:
                return
            self.repl_var.set(replacement)
            self.run_replace(replacement)
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def rebuild_from_folder_dialog(self):
        if self.parsed is None:
            messagebox.showerror('Fehler', 'Noch keine PAK-Datei eingelesen')
            return
        folder = filedialog.askdirectory(title='Ordner mit manifest.json auswählen')
        if not folder:
            return
        try:
            replacements = collect_folder_replacements(self.parsed, folder)
            if not replacements:
                raise PakError('Im Ordner wurden keine Änderungen gefunden')
            first_entry = self.parsed['entries'][sorted(replacements)[0]]
            out_path = self.ask_output_pak_path(first_entry, suffix='folder_rebuilt')
            if not out_path:
                return
            out_path = rebuild_pak(self.parsed, replacements, out_path)
            self.pak_var.set(out_path)
            self.load_pak()
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Neue Datei:\n{out_path}\n\nGeänderte Einträge: {len(replacements)}')
            messagebox.showinfo('Fertig', f'Neue Datei geschrieben:\n{out_path}')
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))

    def build_new_pak(self):
        try:
            replacement = self.repl_var.get().strip()
            if not replacement:
                raise PakError('Bitte eine Ersatzdatei auswählen')
            self.run_replace(replacement)
        except Exception as e:
            self.output.delete('1.0', 'end')
            self.output.insert('1.0', f'Fehler: {e}')
            messagebox.showerror('Fehler', str(e))
