"""Resizable mesh panel and per-mesh visibility controls for the GPU viewer."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import mesh_viewer as mv


_INSTALLED = False
_VISIBLE_MARK = "[x]"
_HIDDEN_MARK = "[ ]"


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    BaseViewer = mv.MeshViewer

    class VisibilityMeshViewer(BaseViewer):
        def __init__(self, parent, parsed, entry, require_store=None):
            self._mesh_visibility = {}
            self._mesh_panel_paned = None
            self._mesh_visibility_label = None
            super().__init__(parent, parsed, entry, require_store=require_store)

        def _install_mesh_panel(self):
            # The original viewport is created before the OpenGL context is
            # initialised. Recreate it as a child of a PanedWindow so the list
            # width can be changed with a draggable sash.
            old_viewport = self.viewport
            try:
                old_viewport.pack_forget()
                old_viewport.destroy()
            except Exception:
                pass

            paned = tk.PanedWindow(
                self,
                orient="horizontal",
                sashwidth=9,
                sashrelief="raised",
                showhandle=False,
                opaqueresize=True,
                borderwidth=0,
                highlightthickness=0,
            )
            paned.pack(fill="both", expand=True, padx=8, pady=(4, 8))
            self._mesh_panel_paned = paned

            panel = ttk.Frame(paned, padding=(6, 4, 6, 4))
            paned.add(panel, minsize=220, width=360)

            title_row = ttk.Frame(panel)
            title_row.pack(fill="x", pady=(0, 5))
            mesh_count = len(self.scene.get("meshes") or [])
            ttk.Label(title_row, text=f"Meshes ({mesh_count})").pack(side="left")
            self._mesh_visibility_label = ttk.Label(title_row, text=f"{mesh_count} sichtbar")
            self._mesh_visibility_label.pack(side="right")

            action_row = ttk.Frame(panel)
            action_row.pack(fill="x", pady=(0, 5))
            ttk.Button(action_row, text="Alle an", command=lambda: self._set_all_mesh_visibility(True)).pack(side="left")
            ttk.Button(action_row, text="Alle aus", command=lambda: self._set_all_mesh_visibility(False)).pack(side="left", padx=(5, 0))
            ttk.Button(action_row, text="Nur Auswahl", command=self._show_only_selected_mesh).pack(side="left", padx=(5, 0))
            ttk.Button(action_row, text="Auswahl aufheben", command=self.clear_mesh_selection).pack(side="right")

            tree_wrap = ttk.Frame(panel)
            tree_wrap.pack(fill="both", expand=True)

            columns = ("visible", "material", "triangles", "texture")
            self.mesh_tree = ttk.Treeview(
                tree_wrap,
                columns=columns,
                show="tree headings",
                selectmode="browse",
                height=30,
            )
            self.mesh_tree.heading("#0", text="Mesh")
            self.mesh_tree.heading("visible", text="An")
            self.mesh_tree.heading("material", text="Material")
            self.mesh_tree.heading("triangles", text="Tris")
            self.mesh_tree.heading("texture", text="Textur")
            self.mesh_tree.column("#0", width=94, minwidth=70, stretch=False)
            self.mesh_tree.column("visible", width=42, minwidth=38, anchor="center", stretch=False)
            self.mesh_tree.column("material", width=165, minwidth=90, stretch=True)
            self.mesh_tree.column("triangles", width=62, minwidth=50, anchor="e", stretch=False)
            self.mesh_tree.column("texture", width=180, minwidth=90, stretch=True)
            self.mesh_tree.tag_configure("hidden", foreground="#808080")

            scrollbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.mesh_tree.yview)
            self.mesh_tree.configure(yscrollcommand=scrollbar.set)
            self.mesh_tree.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="left", fill="y")

            self.mesh_tree.bind("<<TreeviewSelect>>", self._on_mesh_list_select)
            self.mesh_tree.bind("<Button-1>", self._on_mesh_tree_click, add="+")
            self.mesh_tree.bind("<space>", self._toggle_selected_mesh_visibility)

            materials = self.scene.get("materials") or []
            texture_names = self.scene.get("texture_names") or {}
            self._mesh_iids.clear()
            self._iid_meshes.clear()
            self._mesh_visibility.clear()

            for draw_index, mesh in enumerate(self.scene.get("meshes") or []):
                mesh_index = int(mesh.get("mesh_index", draw_index))
                material_index = int(mesh.get("material_index", 0))
                material_name = (
                    str(materials[material_index])
                    if 0 <= material_index < len(materials)
                    else f"material_{material_index}"
                )
                triangle_count = int(mesh.get("index_count", len(mesh.get("indices") or []))) // 3
                texture_name = str(texture_names.get(material_index, "—"))
                self._mesh_visibility[mesh_index] = True
                iid = self.mesh_tree.insert(
                    "",
                    "end",
                    text=f"Mesh {mesh_index}",
                    values=(_VISIBLE_MARK, material_name, triangle_count, texture_name),
                )
                self._mesh_iids[mesh_index] = iid
                self._iid_meshes[iid] = mesh_index

            ttk.Label(
                panel,
                text="Klick auf [x]/[ ] oder Leertaste: Mesh ein-/ausblenden",
            ).pack(anchor="w", pady=(5, 0))

            self.viewport = tk.Frame(paned, background="#20242a", takefocus=True)
            paned.add(self.viewport, minsize=320)
            self._bind_recreated_viewport()

            def place_initial_sash():
                try:
                    paned.sash_place(0, 360, 0)
                except Exception:
                    pass

            self.after_idle(place_initial_sash)

        def _bind_recreated_viewport(self):
            self.viewport.bind("<Configure>", self.request_render)
            self.viewport.bind("<Expose>", self.request_render)
            self.viewport.bind("<ButtonPress-1>", self._start_orbit)
            self.viewport.bind("<B1-Motion>", self._drag)
            self.viewport.bind("<ButtonPress-2>", self._start_pan)
            self.viewport.bind("<B2-Motion>", self._drag)
            self.viewport.bind("<ButtonPress-3>", self._start_pan)
            self.viewport.bind("<B3-Motion>", self._drag)
            self.viewport.bind("<MouseWheel>", self._wheel)
            self.viewport.bind("<Button-4>", lambda _event: self._zoom_by(0.88))
            self.viewport.bind("<Button-5>", lambda _event: self._zoom_by(1.0 / 0.88))

        def _is_mesh_visible(self, mesh_index):
            return bool(self._mesh_visibility.get(int(mesh_index), True))

        def _visible_gpu_meshes(self):
            return [
                mesh
                for mesh in self._gpu_meshes
                if self._is_mesh_visible(mesh.get("mesh_index", -1))
            ]

        def _update_mesh_visibility_label(self):
            if self._mesh_visibility_label is None:
                return
            visible_count = sum(1 for visible in self._mesh_visibility.values() if visible)
            self._mesh_visibility_label.configure(
                text=f"{visible_count}/{len(self._mesh_visibility)} sichtbar"
            )

        def _set_mesh_visible(self, mesh_index, visible):
            mesh_index = int(mesh_index)
            if mesh_index not in self._mesh_visibility:
                return
            visible = bool(visible)
            self._mesh_visibility[mesh_index] = visible
            iid = self._mesh_iids.get(mesh_index)
            if iid:
                values = list(self.mesh_tree.item(iid, "values"))
                if values:
                    values[0] = _VISIBLE_MARK if visible else _HIDDEN_MARK
                self.mesh_tree.item(
                    iid,
                    values=values,
                    tags=() if visible else ("hidden",),
                )
            self._update_mesh_visibility_label()
            self.request_render()

        def _toggle_mesh_visibility(self, mesh_index):
            self._set_mesh_visible(mesh_index, not self._is_mesh_visible(mesh_index))

        def _set_all_mesh_visibility(self, visible):
            visible = bool(visible)
            for mesh_index in list(self._mesh_visibility):
                self._mesh_visibility[mesh_index] = visible
                iid = self._mesh_iids.get(mesh_index)
                if iid:
                    values = list(self.mesh_tree.item(iid, "values"))
                    if values:
                        values[0] = _VISIBLE_MARK if visible else _HIDDEN_MARK
                    self.mesh_tree.item(
                        iid,
                        values=values,
                        tags=() if visible else ("hidden",),
                    )
            self._update_mesh_visibility_label()
            self.request_render()

        def _show_only_selected_mesh(self):
            selection = self.mesh_tree.selection()
            if not selection:
                return
            selected_mesh = self._iid_meshes.get(selection[0])
            if selected_mesh is None:
                return
            for mesh_index in list(self._mesh_visibility):
                visible = mesh_index == selected_mesh
                self._mesh_visibility[mesh_index] = visible
                iid = self._mesh_iids.get(mesh_index)
                if iid:
                    values = list(self.mesh_tree.item(iid, "values"))
                    if values:
                        values[0] = _VISIBLE_MARK if visible else _HIDDEN_MARK
                    self.mesh_tree.item(
                        iid,
                        values=values,
                        tags=() if visible else ("hidden",),
                    )
            self._update_mesh_visibility_label()
            self.request_render()

        def _on_mesh_tree_click(self, event):
            if self.mesh_tree.identify_region(event.x, event.y) != "cell":
                return None
            if self.mesh_tree.identify_column(event.x) != "#1":
                return None
            iid = self.mesh_tree.identify_row(event.y)
            mesh_index = self._iid_meshes.get(iid)
            if mesh_index is None:
                return None
            self._toggle_mesh_visibility(mesh_index)
            return "break"

        def _toggle_selected_mesh_visibility(self, _event=None):
            selection = self.mesh_tree.selection()
            if not selection:
                return "break"
            mesh_index = self._iid_meshes.get(selection[0])
            if mesh_index is not None:
                self._toggle_mesh_visibility(mesh_index)
            return "break"

        def _render(self):
            original_meshes = self._gpu_meshes
            self._gpu_meshes = self._visible_gpu_meshes()
            try:
                return super()._render()
            finally:
                self._gpu_meshes = original_meshes

        def _pick_mesh_at(self, x, y):
            original_meshes = self._gpu_meshes
            self._gpu_meshes = self._visible_gpu_meshes()
            try:
                return super()._pick_mesh_at(x, y)
            finally:
                self._gpu_meshes = original_meshes

    VisibilityMeshViewer.__name__ = "VisibilityMeshViewer"
    mv.MeshViewer = VisibilityMeshViewer
