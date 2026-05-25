import tkinter as tk
from tkinter import messagebox
from uuid_search import format_uuid_search_lines

def install(App):
    original_init = App.__init__

    def __init__(self, root):
        original_init(self, root)
        self.add_uuid_search_button()

    def add_uuid_search_button(self):
        target = None
        for child in self.root.winfo_children():
            for sub in child.winfo_children():
                try:
                    rows = sub.winfo_children()
                except Exception:
                    continue
                for row in rows:
                    try:
                        labels = [c.cget('text') for c in row.winfo_children() if isinstance(c, tk.Button)]
                    except Exception:
                        labels = []
                    if 'Neues PAK bauen' in labels and 'Leeren' in labels:
                        target = row
                        break
                if target is not None:
                    break
            if target is not None:
                break
        if target is None:
            return
        tk.Button(target, text='UUID suchen', command=self.open_uuid_search_dialog, width=14).pack(side='left', padx=(8, 0))

    def open_uuid_search_dialog(self):
        if self.parsed is None:
            messagebox.showerror('Fehler', 'Noch keine PAK-Datei eingelesen')
            return
        win = tk.Toplevel(self.root)
        win.title('UUID suchen')
        win.transient(self.root)
        win.grab_set()
        frame = tk.Frame(win, padx=14, pady=14)
        frame.pack(fill='both', expand=True)
        tk.Label(frame, text='UUID').pack(anchor='w')
        query_var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=query_var, width=48)
        entry.pack(fill='x', pady=(6, 0))
        entry.focus_set()
        button_row = tk.Frame(frame)
        button_row.pack(fill='x', pady=(12, 0))

        def run_search():
            try:
                query = query_var.get().strip()
                lines = format_uuid_search_lines(self.parsed, query)
                self.output.delete('1.0', 'end')
                self.output.insert('1.0', '\n'.join(lines))
                win.destroy()
            except Exception as e:
                messagebox.showerror('Fehler', str(e))

        tk.Button(button_row, text='Suchen', command=run_search, width=14).pack(side='left')
        tk.Button(button_row, text='Abbrechen', command=win.destroy, width=14).pack(side='left', padx=(8, 0))
        entry.bind('<Return>', lambda event: run_search())

    App.__init__ = __init__
    App.add_uuid_search_button = add_uuid_search_button
    App.open_uuid_search_dialog = open_uuid_search_dialog
