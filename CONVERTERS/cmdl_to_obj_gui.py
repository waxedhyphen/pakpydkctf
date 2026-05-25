import os
import queue
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import sys
from windows_compat import configure_root, is_macos_metadata_path, setup_windows_process
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
from cmdl_to_obj_core import convert_cmdl_to_obj


class App:
    def __init__(self, root):
        self.root = root
        self.root.title('CMDL -> OBJ')
        self.root.geometry('860x520')
        self.root.resizable(True, True)
        self.source_paths = []
        self.target_dir = ''
        self.worker_thread = None
        self.progress_queue = queue.Queue()
        self.status_text = tk.StringVar(value='1. CMDL/SMDL/WMDL auswählen. 2. Zielordner wählen. 3. Auf Umwandeln klicken.')
        self.source_text = tk.StringVar(value='Keine Quelldateien ausgewählt.')
        self.target_text = tk.StringVar(value='Kein Zielordner ausgewählt.')
        self.info_text = tk.StringVar(value='Es werden OBJ + MTL geschrieben. Mehrfachauswahl ist möglich.')
        self.progress_text = tk.StringVar(value='Bereit.')
        self.progress_value = tk.DoubleVar(value=0.0)
        outer = tk.Frame(root, padx=18, pady=18)
        outer.pack(fill='both', expand=True)
        tk.Label(outer, text='CMDL -> OBJ Konverter', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        tk.Label(outer, textvariable=self.status_text, justify='left', wraplength=800, pady=10, font=('Segoe UI', 10)).pack(anchor='w')
        tk.Label(outer, textvariable=self.info_text, justify='left', wraplength=800, pady=6, font=('Segoe UI', 9)).pack(anchor='w')
        box1 = tk.LabelFrame(outer, text='Quelle', padx=10, pady=10)
        box1.pack(fill='x', pady=(12, 8))
        row1 = tk.Frame(box1)
        row1.pack(fill='x')
        self.source_button = tk.Button(row1, text='Dateien auswählen', width=24, command=self.choose_sources)
        self.source_button.pack(side='left')
        self.source_folder_button = tk.Button(row1, text='Ordner auswählen', width=24, command=self.choose_source_folder)
        self.source_folder_button.pack(side='left', padx=10)
        tk.Label(box1, textvariable=self.source_text, justify='left', wraplength=780, pady=8).pack(anchor='w')
        self.source_list = tk.Listbox(box1, height=7)
        self.source_list.pack(fill='x', pady=(0, 4))
        box2 = tk.LabelFrame(outer, text='Ziel', padx=10, pady=10)
        box2.pack(fill='x', pady=8)
        self.target_button = tk.Button(box2, text='Zielordner auswählen', width=24, command=self.choose_target)
        self.target_button.pack(anchor='w')
        tk.Label(box2, textvariable=self.target_text, justify='left', wraplength=780, pady=8).pack(anchor='w')
        box3 = tk.LabelFrame(outer, text='Fortschritt', padx=10, pady=10)
        box3.pack(fill='x', pady=8)
        self.progress_bar = ttk.Progressbar(box3, variable=self.progress_value, maximum=100, mode='determinate')
        self.progress_bar.pack(fill='x')
        tk.Label(box3, textvariable=self.progress_text, justify='left', wraplength=780, pady=8).pack(anchor='w')
        button_row = tk.Frame(outer)
        button_row.pack(fill='x', pady=(16, 0))
        self.convert_button = tk.Button(button_row, text='Umwandeln und speichern', width=24, command=self.convert)
        self.convert_button.pack(side='left')
        tk.Button(button_row, text='Beenden', width=14, command=self.root.destroy).pack(side='left', padx=10)

    def refresh_source_list(self):
        self.source_list.delete(0, 'end')
        for path in self.source_paths:
            self.source_list.insert('end', path)
        if self.source_paths:
            self.source_text.set(f'{len(self.source_paths)} Datei(en) ausgewählt.')
        else:
            self.source_text.set('Keine Quelldateien ausgewählt.')

    def choose_sources(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        paths = filedialog.askopenfilenames(title='CMDL/SMDL/WMDL auswählen', filetypes=[('Retro-Modelle', '*.cmdl *.smdl *.wmdl'), ('Alle Dateien', '*.*')])
        if not paths:
            return
        self.source_paths = [path for path in paths if not is_macos_metadata_path(path)]
        if not self.source_paths:
            messagebox.showerror('Fehler', 'Es wurden nur macOS-Metadaten-Dateien ausgewaehlt.')
            return
        self.refresh_source_list()
        if not self.target_dir:
            self.target_dir = os.path.dirname(self.source_paths[0])
            self.target_text.set(self.target_dir)
        self.progress_value.set(0.0)
        self.progress_text.set('Bereit.')
        self.status_text.set('Quelldateien gesetzt. Jetzt Zielordner wählen oder direkt auf Umwandeln klicken.')

    def choose_source_folder(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        folder = filedialog.askdirectory(title='Quellordner auswählen')
        if not folder:
            return
        files = []
        for name in os.listdir(folder):
            if is_macos_metadata_path(name):
                continue
            if name.lower().endswith(('.cmdl', '.smdl', '.wmdl')):
                files.append(os.path.join(folder, name))
        files.sort()
        if not files:
            messagebox.showerror('Fehler', 'Im ausgewählten Ordner wurden keine CMDL/SMDL/WMDL-Dateien gefunden.')
            return
        self.source_paths = files
        self.refresh_source_list()
        if not self.target_dir:
            self.target_dir = folder
            self.target_text.set(folder)
        self.progress_value.set(0.0)
        self.progress_text.set('Bereit.')
        self.status_text.set('Quellordner gesetzt. Jetzt Zielordner wählen oder direkt auf Umwandeln klicken.')

    def choose_target(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        folder = filedialog.askdirectory(title='Zielordner auswählen')
        if not folder:
            return
        self.target_dir = folder
        self.target_text.set(folder)
        self.status_text.set('Ziel gesetzt. Jetzt auf Umwandeln und speichern klicken.')

    def set_busy(self, busy):
        state = 'disabled' if busy else 'normal'
        self.convert_button.config(state=state)
        self.source_button.config(state=state)
        self.source_folder_button.config(state=state)
        self.target_button.config(state=state)

    def update_progress(self, percent, text):
        self.progress_queue.put(('progress', float(percent), text))

    def convert_worker(self, source_paths, target_dir):
        try:
            results = []
            total = len(source_paths)
            for index, source_path in enumerate(source_paths, start=1):
                start = 100.0 * ((index - 1) / total)
                end = 100.0 * (index / total)
                self.update_progress(start, f'Verarbeite {index} / {total}: {os.path.basename(source_path)}')
                result = convert_cmdl_to_obj(source_path, target_dir)
                results.append(result)
                self.update_progress(end, f'Fertig: {os.path.basename(result["output_obj_path"])}')
            lines = []
            for result in results:
                lines.append(f'{os.path.basename(result["source_path"])} -> {os.path.basename(result["output_obj_path"])} | Vertices: {result["vertex_count"]} | Meshes: {result["mesh_count"]} | Indices: {result["index_count_total"]}')
            self.progress_queue.put(('done', 'CMDL zu OBJ abgeschlossen.', 'Die OBJ-Dateien wurden erstellt.\n\n' + '\n'.join(lines)))
        except Exception as exc:
            self.progress_queue.put(('error', f'{exc}\n\n{traceback.format_exc()}'))

    def poll_progress(self):
        try:
            while True:
                item = self.progress_queue.get_nowait()
                if item[0] == 'progress':
                    _, percent, text = item
                    self.progress_value.set(max(0.0, min(100.0, percent)))
                    self.progress_text.set(text)
                elif item[0] == 'done':
                    _, status, message = item
                    self.progress_value.set(100.0)
                    self.progress_text.set('Fertig.')
                    self.status_text.set(status)
                    self.set_busy(False)
                    self.worker_thread = None
                    messagebox.showinfo('Erfolg', message)
                elif item[0] == 'error':
                    _, message = item
                    self.status_text.set('Umwandlung fehlgeschlagen.')
                    self.progress_text.set('Fehler.')
                    self.set_busy(False)
                    self.worker_thread = None
                    messagebox.showerror('Fehler', message)
        except queue.Empty:
            pass
        if self.worker_thread and self.worker_thread.is_alive():
            self.root.after(100, self.poll_progress)
        elif self.worker_thread is not None:
            self.root.after(100, self.poll_progress)

    def convert(self):
        if self.worker_thread and self.worker_thread.is_alive():
            return
        if not self.source_paths:
            messagebox.showerror('Fehler', 'Es wurden noch keine Quelldateien ausgewählt.')
            return
        if not self.target_dir:
            messagebox.showerror('Fehler', 'Es wurde noch kein Zielordner ausgewählt.')
            return
        self.set_busy(True)
        self.progress_value.set(0.0)
        self.progress_text.set('Startet...')
        self.status_text.set('Umwandlung läuft...')
        self.worker_thread = threading.Thread(target=self.convert_worker, args=(list(self.source_paths), self.target_dir), daemon=True)
        self.worker_thread.start()
        self.root.after(100, self.poll_progress)


def main():
    setup_windows_process()
    root = tk.Tk()
    configure_root(root, min_size=(720, 480))
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
