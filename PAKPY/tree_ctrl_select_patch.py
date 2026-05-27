def install(App):
    original_init = App.__init__
    def patched_init(self, root):
        original_init(self, root)
        self._ctrl_drag_select_active = False
        self._ctrl_drag_select_mode = ''
        self._ctrl_drag_select_last_y = 0
        self.tree.bind('<Control-ButtonPress-1>', self.ctrl_drag_select_press, add='+')
        self.tree.bind('<Control-B1-Motion>', self.ctrl_drag_select_motion, add='+')
        self.tree.bind('<Control-ButtonRelease-1>', self.ctrl_drag_select_release, add='+')
    def ctrl_drag_visible_iids(self):
        out = []
        def walk(parent):
            for iid in self.tree.get_children(parent):
                out.append(iid)
                if self.tree.item(iid, 'open'):
                    walk(iid)
        walk('')
        return out
    def ctrl_drag_iids_between_y(self, y1, y2):
        top, bottom = sorted((y1, y2))
        found = []
        for iid in self.ctrl_drag_visible_iids():
            bbox = self.tree.bbox(iid)
            if not bbox:
                continue
            row_top = bbox[1]
            row_bottom = row_top + bbox[3]
            if row_bottom >= top and row_top <= bottom:
                found.append(iid)
        for y in (y1, y2):
            iid = self.tree.identify_row(y)
            if iid and iid not in found:
                found.append(iid)
        return found
    def ctrl_drag_apply_iids(self, iids):
        if not iids:
            return
        if self._ctrl_drag_select_mode == 'remove':
            for iid in iids:
                self.tree.selection_remove(iid)
        else:
            for iid in iids:
                self.tree.selection_add(iid)
        last = iids[-1]
        if last and self.tree.exists(last):
            self.tree.focus(last)
            self.last_clicked_iid = last
        self.root.after_idle(self.show_selected)
    def ctrl_drag_select_press(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            self._ctrl_drag_select_active = False
            self._ctrl_drag_select_mode = ''
            return 'break'
        self._ctrl_drag_select_active = True
        self._ctrl_drag_select_last_y = event.y
        self._ctrl_drag_select_mode = 'remove' if iid in self.tree.selection() else 'add'
        self.ctrl_drag_apply_iids([iid])
        return 'break'
    def ctrl_drag_select_motion(self, event):
        if not getattr(self, '_ctrl_drag_select_active', False):
            return 'break'
        iids = self.ctrl_drag_iids_between_y(self._ctrl_drag_select_last_y, event.y)
        self.ctrl_drag_apply_iids(iids)
        self._ctrl_drag_select_last_y = event.y
        return 'break'
    def ctrl_drag_select_release(self, event):
        if getattr(self, '_ctrl_drag_select_active', False):
            iids = self.ctrl_drag_iids_between_y(self._ctrl_drag_select_last_y, event.y)
            self.ctrl_drag_apply_iids(iids)
        self._ctrl_drag_select_active = False
        self._ctrl_drag_select_mode = ''
        self.root.after_idle(self.show_selected)
        return 'break'
    App.__init__ = patched_init
    App.ctrl_drag_visible_iids = ctrl_drag_visible_iids
    App.ctrl_drag_iids_between_y = ctrl_drag_iids_between_y
    App.ctrl_drag_apply_iids = ctrl_drag_apply_iids
    App.ctrl_drag_select_press = ctrl_drag_select_press
    App.ctrl_drag_select_motion = ctrl_drag_select_motion
    App.ctrl_drag_select_release = ctrl_drag_select_release
    try:
        from probe_gui_patch import install as install_probe_gui_patch
        install_probe_gui_patch(App)
    except Exception:
        pass
