#========================
#FILE main.py
#========================

import tkinter as tk
from gui import App
from dcln_gui_patch import install as install_dcln_gui
from room_gui_patch import install as install_room_gui
from char_gui_patch import install as install_char_gui
from char_skeletal_package_patch import install as install_char_skeletal_package
from uuid_gui_patch import install as install_uuid_gui
from missing_txtr_export_error_patch import install as install_missing_txtr_export_error
from skeletal_tail_patch import install as install_skeletal_tail_patch
from tree_ctrl_select_patch import install as install_tree_ctrl_select_patch
from model_animation_refs_patch import install as install_model_animation_refs_patch
from char_anim_selector_patch import install as install_char_anim_selector_patch
from anim_raw_probe_patch import install as install_anim_raw_probe_patch
from anim_track_skel_map_patch import install as install_anim_track_skel_map_patch
from windows_compat import configure_root, setup_windows_process

install_skeletal_tail_patch()
install_dcln_gui(App)
install_room_gui(App)
install_char_gui(App)
install_char_skeletal_package(App)
install_uuid_gui(App)
install_missing_txtr_export_error(App)
install_tree_ctrl_select_patch(App)
install_model_animation_refs_patch(App)
install_char_anim_selector_patch(App)
install_anim_raw_probe_patch(App)
install_anim_track_skel_map_patch(App)

def main():
    setup_windows_process()
    root = tk.Tk()
    configure_root(root, min_size=(980, 700))
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()