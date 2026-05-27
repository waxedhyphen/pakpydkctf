import json
import tkinter as tk
from tkinter import messagebox,ttk
from probe_core import list_anim_options,run_anim_probe

def install(App):
    original_init=App.__init__
    def patched_init(self,root):
        original_init(self,root)
        self.probe_window=None
        self.probe_anim_vars={}
        add_probe_button(self)
    def add_probe_button(self):
        try:
            outer=self.root.winfo_children()[0]
            bottom=outer.winfo_children()[-1]
            rows=[x for x in bottom.winfo_children() if isinstance(x,tk.Frame)]
            row=rows[-1] if rows else bottom
            tk.Button(row,text='Probe',command=self.open_probe_menu,width=12).pack(side='left',padx=(8,0))
        except Exception:
            tk.Button(self.root,text='Probe',command=self.open_probe_menu,width=12).pack(side='bottom',anchor='w',padx=14,pady=(0,14))
    def open_probe_menu(self):
        if self.parsed is None:
            messagebox.showerror('Probe','Erst eine PAK einlesen')
            return
        if self.probe_window is not None and self.probe_window.winfo_exists():
            self.probe_window.lift()
            return
        win=tk.Toplevel(self.root)
        self.probe_window=win
        win.title('Probe')
        win.geometry('860x640')
        top=tk.Frame(win,padx=12,pady=12)
        top.pack(fill='both',expand=True)
        mode_row=tk.Frame(top)
        mode_row.pack(fill='x')
        tk.Label(mode_row,text='Probe-Art').pack(side='left')
        self.probe_mode_var=tk.StringVar(value='anim')
        ttk.Combobox(mode_row,textvariable=self.probe_mode_var,values=['anim'],state='readonly',width=18).pack(side='left',padx=(8,0))
        out_row=tk.Frame(top)
        out_row.pack(fill='x',pady=(10,0))
        tk.Label(out_row,text='Output').pack(side='left')
        self.probe_out_var=tk.StringVar(value=self.dialog_dirs.get('probe_output_dir',''))
        tk.Entry(out_row,textvariable=self.probe_out_var).pack(side='left',fill='x',expand=True,padx=(8,8))
        tk.Button(out_row,text='Auswählen',command=self.choose_probe_output,width=12).pack(side='left')
        select_row=tk.Frame(top)
        select_row.pack(fill='x',pady=(10,0))
        tk.Button(select_row,text='Alle ANIM',command=lambda:self.set_probe_anim_selection(True),width=14).pack(side='left')
        tk.Button(select_row,text='Keine',command=lambda:self.set_probe_anim_selection(False),width=14).pack(side='left',padx=(8,0))
        tk.Button(select_row,text='Probe starten',command=self.run_probe_dialog,width=16).pack(side='right')
        list_wrap=tk.Frame(top)
        list_wrap.pack(fill='both',expand=True,pady=(10,0))
        canvas=tk.Canvas(list_wrap)
        scroll=ttk.Scrollbar(list_wrap,orient='vertical',command=canvas.yview)
        self.probe_anim_frame=tk.Frame(canvas)
        self.probe_anim_frame.bind('<Configure>',lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0,0),window=self.probe_anim_frame,anchor='nw')
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side='left',fill='both',expand=True)
        scroll.pack(side='left',fill='y')
        self.fill_probe_anim_list()
    def choose_probe_output(self):
        path=self.ask_directory('probe_output_dir',title='Probe-Output-Ordner auswählen')
        if path:
            self.probe_out_var.set(path)
    def fill_probe_anim_list(self):
        for child in self.probe_anim_frame.winfo_children(): child.destroy()
        self.probe_anim_vars={}
        rows=list_anim_options(self.parsed,self.require_store)
        head=tk.Frame(self.probe_anim_frame)
        head.pack(fill='x')
        tk.Label(head,text=f'ANIM-Dateien aus aktueller PAK: {len(rows)}').pack(side='left')
        for row in rows:
            var=tk.BooleanVar(value=True)
            self.probe_anim_vars[row['uuid_hex']]=var
            text=f"{row['name']} | {row['file']} | {row['size']} Bytes"
            tk.Checkbutton(self.probe_anim_frame,text=text,variable=var,anchor='w',justify='left').pack(fill='x',anchor='w')
    def set_probe_anim_selection(self,value):
        for var in self.probe_anim_vars.values(): var.set(bool(value))
    def run_probe_dialog(self):
        if self.parsed is None:
            messagebox.showerror('Probe','Erst eine PAK einlesen')
            return
        out=self.probe_out_var.get().strip()
        if not out:
            messagebox.showerror('Probe','Output-Ordner auswählen')
            return
        self.remember_dialog_dir('probe_output_dir',out)
        selected=[k for k,v in self.probe_anim_vars.items() if v.get()]
        try:
            result=run_anim_probe(self.parsed,self.require_store,out,selected)
        except Exception as e:
            messagebox.showerror('Probe',str(e))
            return
        self.output.delete('1.0','end')
        self.output.insert('end',json.dumps(result,indent=2,ensure_ascii=False))
        messagebox.showinfo('Probe',f'Probe fertig:\n{result.get("output_dir",out)}')
    App.__init__=patched_init
    App.add_probe_button=add_probe_button
    App.open_probe_menu=open_probe_menu
    App.choose_probe_output=choose_probe_output
    App.fill_probe_anim_list=fill_probe_anim_list
    App.set_probe_anim_selection=set_probe_anim_selection
    App.run_probe_dialog=run_probe_dialog
