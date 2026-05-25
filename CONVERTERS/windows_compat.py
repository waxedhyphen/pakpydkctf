from pathlib import Path
import ctypes
import hashlib
import re
import sys
from tkinter import ttk


WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}


def setup_windows_process(app_id='PAKPY.Converters.Windows'):
    if sys.platform != 'win32':
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def configure_root(root, min_size=None):
    if sys.platform == 'win32':
        try:
            style = ttk.Style(root)
            if 'vista' in style.theme_names():
                style.theme_use('vista')
        except Exception:
            pass
    if min_size:
        try:
            root.minsize(*min_size)
        except Exception:
            pass


def is_macos_metadata_path(path):
    for part in Path(path).parts:
        if part == '__MACOSX' or part == '.DS_Store' or part.startswith('._'):
            return True
    return False


def safe_path_component(text, fallback='asset', max_len=120):
    raw = str(text or '').strip()
    if not raw:
        raw = fallback
    clean = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', '_', raw)
    clean = re.sub(r'[^A-Za-z0-9._ -]+', '_', clean)
    clean = re.sub(r'\s+', '_', clean).strip(' .')
    if not clean:
        clean = fallback
    stem = clean.split('.', 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        clean = '_' + clean
    if len(clean) > max_len:
        digest = hashlib.sha1(clean.encode('utf-8', 'replace')).hexdigest()[:10]
        clean = f'{clean[:max_len - 11]}_{digest}'.rstrip(' .')
    return clean or fallback
