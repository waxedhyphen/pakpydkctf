#========================
#FILE main.py
#========================

import tkinter as tk
from gui import App
from windows_compat import configure_root, setup_windows_process

def main():
    setup_windows_process()
    root = tk.Tk()
    configure_root(root, min_size=(980, 700))
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
