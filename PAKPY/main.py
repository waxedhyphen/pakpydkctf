#========================
#FILE main.py
#========================

import tkinter as tk
from gui import App
from dcln_gui_patch import install as install_dcln_gui
from room_gui_patch import install as install_room_gui
from uuid_gui_patch import install as install_uuid_gui
from missing_txtr_export_error_patch import install as install_missing_txtr_export_error
from windows_compat import configure_root, setup_windows_process

install_dcln_gui(App)
install_room_gui(App)
install_uuid_gui(App)
install_missing_txtr_export_error(App)

def main():
    setup_windows_process()
    root = tk.Tk()
    configure_root(root, min_size=(980, 700))
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()
