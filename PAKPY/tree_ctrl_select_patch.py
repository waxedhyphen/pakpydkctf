def install(App):
    original_init = App.__init__
    def patched_init(self, root):
        original_init(self, root)
        self._ctrl_drag_select_active = False
        self.tree.bind('<Control-ButtonPress-1>', self.ctrl_drag_select_press, add='+')
        self.tree.bind('<Control-B1-Motion>', self.ctrl_drag_select_motion, add='+')
        self.tree.bind('<Control-ButtonRelease-1>', self.ctrl_drag_select_release, add='+')
    def ctrl_drag_select_press(self, event):
        iid = self.tree.identify_row(event.y)
        self._ctrl_drag_select_active = True
        if iid:
            self.tree.selection_add(iid)
            self.tree.focus(iid)
            self.last_clicked_iid = iid
            self.root.after_idle(self.show_selected)
        return 'break'
    def ctrl_drag_select_motion(self, event):
        if not getattr(self, '_ctrl_drag_select_active', False):
            return None
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_add(iid)
            self.tree.focus(iid)
            self.last_clicked_iid = iid
            self.root.after_idle(self.show_selected)
        return 'break'
    def ctrl_drag_select_release(self, event):
        self._ctrl_drag_select_active = False
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_add(iid)
            self.tree.focus(iid)
            self.last_clicked_iid = iid
        self.root.after_idle(self.show_selected)
        return 'break'
    App.__init__ = patched_init
    App.ctrl_drag_select_press = ctrl_drag_select_press
    App.ctrl_drag_select_motion = ctrl_drag_select_motion
    App.ctrl_drag_select_release = ctrl_drag_select_release
