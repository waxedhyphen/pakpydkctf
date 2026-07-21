"""Mesh list, viewport picking and synchronized selection for the GPU viewer."""
from __future__ import annotations

import ctypes
import math
import tkinter as tk
from tkinter import ttk

import mesh_viewer as mv


_INSTALLED = False

GL_RGB = 0x1907
GL_DITHER = 0x0BD0
GL_POLYGON_OFFSET_LINE = 0x2A02


def _pick_color(mesh_index: int) -> tuple[float, float, float]:
    value = int(mesh_index) + 1
    return (
        (value & 0xFF) / 255.0,
        ((value >> 8) & 0xFF) / 255.0,
        ((value >> 16) & 0xFF) / 255.0,
    )


def _decode_pick_color(pixel: bytes) -> int | None:
    if len(pixel) < 3:
        return None
    value = int(pixel[0]) | (int(pixel[1]) << 8) | (int(pixel[2]) << 16)
    return value - 1 if value > 0 else None


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    _patch_wgl_bindings()
    BaseViewer = mv.MeshViewer

    class SelectableMeshViewer(BaseViewer):
        def __init__(self, parent, parsed, entry, require_store=None):
            self.selected_mesh_index = None
            self._mesh_iids = {}
            self._iid_meshes = {}
            self._syncing_mesh_selection = False
            self._click_origin = None
            self._click_moved = False
            super().__init__(parent, parsed, entry, require_store=require_store)
            self._install_mesh_panel()
            self.viewport.bind("<ButtonRelease-1>", self._finish_left_click, add="+")
            self.bind("<Escape>", self._escape_or_close)

        def _install_mesh_panel(self):
            self.viewport.pack_forget()

            panel = ttk.Frame(self, padding=(8, 4, 4, 8))
            panel.pack(side="left", fill="y")

            title_row = ttk.Frame(panel)
            title_row.pack(fill="x", pady=(0, 5))
            ttk.Label(title_row, text=f"Meshes ({len(self.scene.get('meshes') or [])})").pack(side="left")
            ttk.Button(title_row, text="Auswahl aufheben", command=self.clear_mesh_selection).pack(side="right")

            tree_wrap = ttk.Frame(panel)
            tree_wrap.pack(fill="both", expand=True)

            columns = ("material", "triangles", "texture")
            self.mesh_tree = ttk.Treeview(
                tree_wrap,
                columns=columns,
                show="tree headings",
                selectmode="browse",
                height=30,
            )
            self.mesh_tree.heading("#0", text="Mesh")
            self.mesh_tree.heading("material", text="Material")
            self.mesh_tree.heading("triangles", text="Tris")
            self.mesh_tree.heading("texture", text="Textur")
            self.mesh_tree.column("#0", width=94, minwidth=70, stretch=False)
            self.mesh_tree.column("material", width=145, minwidth=90, stretch=True)
            self.mesh_tree.column("triangles", width=62, minwidth=50, anchor="e", stretch=False)
            self.mesh_tree.column("texture", width=150, minwidth=90, stretch=True)

            scrollbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.mesh_tree.yview)
            self.mesh_tree.configure(yscrollcommand=scrollbar.set)
            self.mesh_tree.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="left", fill="y")
            self.mesh_tree.bind("<<TreeviewSelect>>", self._on_mesh_list_select)

            materials = self.scene.get("materials") or []
            texture_names = self.scene.get("texture_names") or {}
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
                iid = self.mesh_tree.insert(
                    "",
                    "end",
                    text=f"Mesh {mesh_index}",
                    values=(material_name, triangle_count, texture_name),
                )
                self._mesh_iids[mesh_index] = iid
                self._iid_meshes[iid] = mesh_index

            self.viewport.pack(side="left", fill="both", expand=True, padx=(4, 8), pady=(4, 8))

        def _escape_or_close(self, _event=None):
            if self.selected_mesh_index is not None:
                self.clear_mesh_selection()
            else:
                self.close()

        def _start_orbit(self, event):
            self._click_origin = (event.x, event.y)
            self._click_moved = False
            return super()._start_orbit(event)

        def _drag(self, event):
            if self._click_origin is not None:
                dx = event.x - self._click_origin[0]
                dy = event.y - self._click_origin[1]
                if dx * dx + dy * dy > 16:
                    self._click_moved = True
            return super()._drag(event)

        def _finish_left_click(self, event):
            self.last_mouse = None
            origin = self._click_origin
            self._click_origin = None
            if origin is None or self._click_moved:
                return
            self._pick_mesh_at(event.x, event.y)

        def _on_mesh_list_select(self, _event=None):
            if self._syncing_mesh_selection:
                return
            selection = self.mesh_tree.selection()
            if not selection:
                return
            mesh_index = self._iid_meshes.get(selection[0])
            if mesh_index is not None:
                self.select_mesh(mesh_index, update_tree=False)

        def select_mesh(self, mesh_index, update_tree=True):
            mesh_index = int(mesh_index)
            if mesh_index not in self._mesh_iids:
                return
            self.selected_mesh_index = mesh_index
            if update_tree:
                iid = self._mesh_iids[mesh_index]
                self._syncing_mesh_selection = True
                try:
                    self.mesh_tree.selection_set(iid)
                    self.mesh_tree.focus(iid)
                    self.mesh_tree.see(iid)
                finally:
                    self._syncing_mesh_selection = False
            self.request_render()

        def clear_mesh_selection(self):
            self.selected_mesh_index = None
            if hasattr(self, "mesh_tree"):
                self._syncing_mesh_selection = True
                try:
                    self.mesh_tree.selection_remove(*self.mesh_tree.selection())
                finally:
                    self._syncing_mesh_selection = False
            self.request_render()

        def _apply_camera(self, width, height):
            gl = self._wgl.opengl
            gl.glViewport(0, 0, width, height)
            gl.glMatrixMode(mv.GL_PROJECTION)
            gl.glLoadIdentity()
            near = 0.05
            far = 250.0
            top = near * math.tan(math.radians(50.0) * 0.5)
            right = top * (width / float(height))
            gl.glFrustum(-right, right, -top, top, near, far)
            gl.glMatrixMode(mv.GL_MODELVIEW)
            gl.glLoadIdentity()
            gl.glTranslatef(self.pan_x, self.pan_y, -self.distance)
            gl.glRotatef(self.pitch, 1.0, 0.0, 0.0)
            gl.glRotatef(self.yaw, 0.0, 1.0, 0.0)

        def _pick_mesh_at(self, x, y):
            if self._closing or not self._make_current():
                return
            gl = self._wgl.opengl
            width = max(1, self.viewport.winfo_width())
            height = max(1, self.viewport.winfo_height())
            if x < 0 or y < 0 or x >= width or y >= height:
                return

            gl.glClearColor(0.0, 0.0, 0.0, 1.0)
            gl.glClear(mv.GL_COLOR_BUFFER_BIT | mv.GL_DEPTH_BUFFER_BIT)
            self._apply_camera(width, height)
            gl.glDisable(mv.GL_LIGHTING)
            gl.glDisable(mv.GL_TEXTURE_2D)
            gl.glDisable(mv.GL_BLEND)
            gl.glDisable(GL_DITHER)
            gl.glDisable(mv.GL_CULL_FACE)
            gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_FILL)
            gl.glEnableClientState(mv.GL_VERTEX_ARRAY)

            bound_vbuf = None
            for mesh in self._gpu_meshes:
                vbuf_index = mesh["vbuf_index"]
                if vbuf_index != bound_vbuf:
                    vbuf = self._gpu_vbufs[vbuf_index]
                    gl.glVertexPointer(
                        3,
                        mv.GL_FLOAT,
                        0,
                        ctypes.cast(vbuf["positions"], ctypes.c_void_p),
                    )
                    bound_vbuf = vbuf_index
                red, green, blue = _pick_color(int(mesh["mesh_index"]))
                gl.glColor4f(red, green, blue, 1.0)
                gl.glDrawElements(
                    mv.GL_TRIANGLES,
                    mesh["index_count"],
                    mv.GL_UNSIGNED_INT,
                    ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
                )

            pixel = (ctypes.c_ubyte * 3)()
            gl.glReadPixels(
                int(x),
                int(height - 1 - y),
                1,
                1,
                GL_RGB,
                mv.GL_UNSIGNED_BYTE,
                ctypes.cast(pixel, ctypes.c_void_p),
            )
            gl.glDisableClientState(mv.GL_VERTEX_ARRAY)
            gl.glEnable(mv.GL_BLEND)
            gl.glEnable(GL_DITHER)
            gl.glClearColor(0.075, 0.085, 0.105, 1.0)

            picked = _decode_pick_color(bytes(pixel))
            if picked is None or picked not in self._mesh_iids:
                self.clear_mesh_selection()
            else:
                self.select_mesh(picked)
            self.request_render()

        def _render(self):
            self._render_pending = False
            if self._closing or not self._make_current():
                return

            gl = self._wgl.opengl
            width = max(1, self.viewport.winfo_width())
            height = max(1, self.viewport.winfo_height())
            gl.glClear(mv.GL_COLOR_BUFFER_BIT | mv.GL_DEPTH_BUFFER_BIT)
            self._apply_camera(width, height)

            light_position = (ctypes.c_float * 4)(2.5, 4.0, 3.0, 0.0)
            gl.glLightfv(mv.GL_LIGHT0, mv.GL_POSITION, light_position)

            if self.show_grid.get():
                self._draw_grid()

            display_mode = getattr(self, "display_mode", None)
            mode = str(display_mode.get() if display_mode is not None else "Texturen")
            use_lighting = self.lighting_enabled.get() and mode == "Texturen"
            gl.glEnable(mv.GL_LIGHTING) if use_lighting else gl.glDisable(mv.GL_LIGHTING)

            if self.cull_faces.get():
                gl.glEnable(mv.GL_CULL_FACE)
                gl.glCullFace(mv.GL_BACK)
            else:
                gl.glDisable(mv.GL_CULL_FACE)

            gl.glPolygonMode(
                mv.GL_FRONT_AND_BACK,
                mv.GL_LINE if self.wireframe.get() else mv.GL_FILL,
            )
            gl.glEnableClientState(mv.GL_VERTEX_ARRAY)
            gl.glEnableClientState(mv.GL_NORMAL_ARRAY)
            gl.glEnableClientState(mv.GL_TEXTURE_COORD_ARRAY)

            selected_channel = self._selected_uv_channel() if hasattr(self, "_selected_uv_channel") else 0
            bound_vbuf = None
            for mesh in self._gpu_meshes:
                vbuf_index = mesh["vbuf_index"]
                if vbuf_index != bound_vbuf:
                    vbuf = self._gpu_vbufs[vbuf_index]
                    gl.glVertexPointer(3, mv.GL_FLOAT, 0, ctypes.cast(vbuf["positions"], ctypes.c_void_p))
                    gl.glNormalPointer(mv.GL_FLOAT, 0, ctypes.cast(vbuf["normals"], ctypes.c_void_p))
                    if "uv_channels_raw" in vbuf:
                        arrays = (
                            vbuf["uv_channels_blender"]
                            if (getattr(self, "blender_v", None) is None or self.blender_v.get())
                            else vbuf["uv_channels_raw"]
                        )
                        channel_index = min(selected_channel, max(0, len(arrays) - 1))
                        uv_pointer = arrays[channel_index]
                    else:
                        uv_pointer = vbuf["uvs"]
                    gl.glTexCoordPointer(2, mv.GL_FLOAT, 0, ctypes.cast(uv_pointer, ctypes.c_void_p))
                    bound_vbuf = vbuf_index

                material_index = int(mesh["material_index"])
                if mode == "UV-Testbild" and getattr(self, "_uv_debug_texture", None):
                    gl.glEnable(mv.GL_TEXTURE_2D)
                    gl.glBindTexture(mv.GL_TEXTURE_2D, self._uv_debug_texture)
                    gl.glColor4f(1.0, 1.0, 1.0, 1.0)
                elif mode == "Texturen":
                    texture_id = self._textures.get(material_index)
                    if self.textures_enabled.get() and texture_id:
                        gl.glEnable(mv.GL_TEXTURE_2D)
                        gl.glBindTexture(mv.GL_TEXTURE_2D, texture_id)
                        gl.glColor4f(1.0, 1.0, 1.0, 1.0)
                    else:
                        gl.glDisable(mv.GL_TEXTURE_2D)
                        red, green, blue = _material_color_fallback(material_index)
                        gl.glColor4f(red, green, blue, 1.0)
                else:
                    gl.glDisable(mv.GL_TEXTURE_2D)
                    red, green, blue = _material_color_fallback(material_index)
                    gl.glColor4f(red, green, blue, 1.0)

                gl.glDrawElements(
                    mv.GL_TRIANGLES,
                    mesh["index_count"],
                    mv.GL_UNSIGNED_INT,
                    ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
                )

            self._draw_selected_mesh_overlay()

            gl.glDisableClientState(mv.GL_TEXTURE_COORD_ARRAY)
            gl.glDisableClientState(mv.GL_NORMAL_ARRAY)
            gl.glDisableClientState(mv.GL_VERTEX_ARRAY)
            gl.glBindTexture(mv.GL_TEXTURE_2D, 0)
            gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_FILL)
            self._wgl.gdi.SwapBuffers(self._hdc)

        def _draw_selected_mesh_overlay(self):
            if self.selected_mesh_index is None:
                return
            selected = None
            for mesh in self._gpu_meshes:
                if int(mesh.get("mesh_index", -1)) == int(self.selected_mesh_index):
                    selected = mesh
                    break
            if selected is None:
                return

            gl = self._wgl.opengl
            vbuf = self._gpu_vbufs[selected["vbuf_index"]]
            gl.glDisableClientState(mv.GL_TEXTURE_COORD_ARRAY)
            gl.glDisableClientState(mv.GL_NORMAL_ARRAY)
            gl.glDisable(mv.GL_TEXTURE_2D)
            gl.glDisable(mv.GL_LIGHTING)
            gl.glDisable(mv.GL_CULL_FACE)
            gl.glEnable(GL_POLYGON_OFFSET_LINE)
            gl.glPolygonOffset(-1.0, -1.0)
            gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_LINE)
            gl.glLineWidth(3.0)
            gl.glColor4f(1.0, 0.58, 0.08, 1.0)
            gl.glVertexPointer(3, mv.GL_FLOAT, 0, ctypes.cast(vbuf["positions"], ctypes.c_void_p))
            gl.glDrawElements(
                mv.GL_TRIANGLES,
                selected["index_count"],
                mv.GL_UNSIGNED_INT,
                ctypes.cast(selected["gpu_indices"], ctypes.c_void_p),
            )
            gl.glLineWidth(1.0)
            gl.glDisable(GL_POLYGON_OFFSET_LINE)
            gl.glPolygonMode(
                mv.GL_FRONT_AND_BACK,
                mv.GL_LINE if self.wireframe.get() else mv.GL_FILL,
            )

    SelectableMeshViewer.__name__ = "SelectableMeshViewer"
    mv.MeshViewer = SelectableMeshViewer


def _material_color_fallback(material_index):
    palette = (
        (0.90, 0.28, 0.24),
        (0.25, 0.62, 0.92),
        (0.28, 0.78, 0.42),
        (0.92, 0.67, 0.22),
        (0.67, 0.38, 0.91),
        (0.20, 0.78, 0.76),
        (0.92, 0.42, 0.68),
        (0.72, 0.74, 0.28),
    )
    return palette[int(material_index) % len(palette)]


def _patch_wgl_bindings():
    if getattr(mv._WGL, "_mesh_selection_bindings", False):
        return

    original_bind = mv._WGL._bind

    def _bind(self):
        original_bind(self)
        c_uint = ctypes.c_uint
        c_int = ctypes.c_int
        c_float = ctypes.c_float
        c_void_p = ctypes.c_void_p
        self.opengl.glReadPixels.argtypes = [
            c_int, c_int, c_int, c_int, c_uint, c_uint, c_void_p,
        ]
        self.opengl.glReadPixels.restype = None
        self.opengl.glLineWidth.argtypes = [c_float]
        self.opengl.glLineWidth.restype = None
        self.opengl.glPolygonOffset.argtypes = [c_float, c_float]
        self.opengl.glPolygonOffset.restype = None

    mv._WGL._bind = _bind
    mv._WGL._mesh_selection_bindings = True
