import inspect
import json
from pathlib import Path
from tkinter import filedialog

def _load_store(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str) and Path(v).is_dir()}
    except Exception:
        pass
    return {}

def _save_store(path, store):
    try:
        path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding='utf-8', newline='\n')
    except Exception:
        pass

def _folder_from_path(path, directory=False):
    if not path:
        return ''
    folder = Path(path)
    if not directory:
        folder = folder.parent
    if folder.is_dir():
        return str(folder)
    return ''

def install():
    if getattr(filedialog, '_pakpy_dialog_dir_memory_installed', False):
        return
    store_path = Path.home() / '.pakpy_dialog_dirs.json'
    store = _load_store(store_path)
    base_dir = Path(__file__).resolve().parent
    originals = {
        'askopenfilename': filedialog.askopenfilename,
        'askopenfilenames': filedialog.askopenfilenames,
        'asksaveasfilename': filedialog.asksaveasfilename,
        'askdirectory': filedialog.askdirectory
    }
    def make_key(kind, options):
        title = str(options.get('title') or '')
        for frame in inspect.stack()[2:]:
            filename = Path(frame.filename)
            lower = str(filename).lower()
            if 'tkinter' in lower:
                continue
            try:
                rel = str(filename.resolve().relative_to(base_dir))
            except Exception:
                rel = filename.name
            return '|'.join((kind, rel.replace('\\', '/'), frame.function, title))
        return '|'.join((kind, title))
    def apply_initialdir(key, options):
        folder = store.get(key)
        if folder and Path(folder).is_dir() and 'initialdir' not in options:
            options['initialdir'] = folder
        return options
    def remember(key, folder):
        if folder:
            store[key] = folder
            _save_store(store_path, store)
    def askopenfilename(*args, **kwargs):
        key = make_key('askopenfilename', kwargs)
        path = originals['askopenfilename'](*args, **apply_initialdir(key, kwargs))
        remember(key, _folder_from_path(path))
        return path
    def askopenfilenames(*args, **kwargs):
        key = make_key('askopenfilenames', kwargs)
        paths = originals['askopenfilenames'](*args, **apply_initialdir(key, kwargs))
        if paths:
            remember(key, _folder_from_path(paths[0]))
        return paths
    def asksaveasfilename(*args, **kwargs):
        key = make_key('asksaveasfilename', kwargs)
        path = originals['asksaveasfilename'](*args, **apply_initialdir(key, kwargs))
        remember(key, _folder_from_path(path))
        return path
    def askdirectory(*args, **kwargs):
        key = make_key('askdirectory', kwargs)
        path = originals['askdirectory'](*args, **apply_initialdir(key, kwargs))
        remember(key, _folder_from_path(path, directory=True))
        return path
    filedialog.askopenfilename = askopenfilename
    filedialog.askopenfilenames = askopenfilenames
    filedialog.asksaveasfilename = asksaveasfilename
    filedialog.askdirectory = askdirectory
    filedialog._pakpy_dialog_dir_memory_installed = True
