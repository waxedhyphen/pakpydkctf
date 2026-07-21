"""Deterministic UV diagnostics for the GPU mesh viewer.

This patch keeps the renderer fast while making texture problems measurable:
- all half-float UV-like vertex channels are preserved;
- semantic 11 is accepted as an observed UV semantic;
- the default viewport convention matches the OBJ/Blender exporter (V = 1 - V);
- UV checker, material-ID and real-texture modes isolate mapping failures;
- a report lists UV ranges, channel descriptors and mesh/material/TXTR bindings.
"""
from __future__ import annotations

import ctypes
import math
import struct
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import mesh_viewer as mv
import pak_extract
from pak_core import PakError, get_entry_asset

try:
    from PIL import ImageDraw
except Exception:
    ImageDraw = None


_INSTALLED = False
_DEBUG_TEXTURE_KEY = -2147483647
_UV_SEMANTICS = {4, 5, 6, 7, 8, 9, 10, 11}
_NORMAL_SEMANTICS = {1}
_TANGENT_SEMANTICS = {2, 3, 12, 13}


def _parse_vertices_with_uv_channels(vertex_buffer, raw_vertex_data):
    stride = int(vertex_buffer.get("stride", 0))
    reported_vertex_count = int(vertex_buffer.get("vertex_count", 0))
    if stride <= 0:
        raise PakError("Vertex-Stride ist ungültig")
    actual_vertex_count = min(reported_vertex_count, len(raw_vertex_data) // stride)
    if actual_vertex_count <= 0:
        raise PakError("Keine lesbaren Vertexdaten gefunden")

    components = list(vertex_buffer.get("components") or [])
    uv_component_indices = []
    for component_index, component in enumerate(components):
        if int(component.get("format", -1)) in (20, 21) and int(component.get("type", -1)) in _UV_SEMANTICS:
            uv_component_indices.append(component_index)
    uv_component_to_channel = {
        component_index: channel_index
        for channel_index, component_index in enumerate(uv_component_indices)
    }

    positions = []
    normals = []
    uv_channels = [[] for _ in uv_component_indices]

    for vertex_index in range(actual_vertex_count):
        base = vertex_index * stride
        position = (0.0, 0.0, 0.0)
        normal = None
        vertex_uvs = [None] * len(uv_component_indices)

        for component_index, component in enumerate(components):
            entry = base + int(component.get("offset", 0))
            fmt = int(component.get("format", -1))
            semantic = int(component.get("type", -1))

            if fmt == 37 and entry + 12 <= len(raw_vertex_data):
                value = struct.unpack_from("<3f", raw_vertex_data, entry)
                if semantic == 0:
                    position = value
            elif fmt == 34 and entry + 8 <= len(raw_vertex_data):
                value = (
                    pak_extract.read_half(raw_vertex_data, entry + 0),
                    pak_extract.read_half(raw_vertex_data, entry + 2),
                    pak_extract.read_half(raw_vertex_data, entry + 4),
                    pak_extract.read_half(raw_vertex_data, entry + 6),
                )
                if semantic in _NORMAL_SEMANTICS and normal is None:
                    normal = value[:3]
                elif semantic in _TANGENT_SEMANTICS and normal is None:
                    normal = value[:3]
            elif component_index in uv_component_to_channel and entry + 4 <= len(raw_vertex_data):
                channel_index = uv_component_to_channel[component_index]
                vertex_uvs[channel_index] = (
                    pak_extract.read_half(raw_vertex_data, entry + 0),
                    pak_extract.read_half(raw_vertex_data, entry + 2),
                )

        positions.append(position)
        normals.append(normal)
        for channel_index, value in enumerate(vertex_uvs):
            uv_channels[channel_index].append(value if value is not None else (0.0, 0.0))

    primary_uvs = list(uv_channels[0]) if uv_channels else [None] * actual_vertex_count
    uv_descriptors = []
    for component_index in uv_component_indices:
        component = components[component_index]
        uv_descriptors.append({
            "component_index": component_index,
            "semantic": int(component.get("type", -1)),
            "format": int(component.get("format", -1)),
            "offset": int(component.get("offset", 0)),
            "stride": int(component.get("stride", stride)),
        })

    return {
        "positions": positions,
        "normals": normals,
        "uvs": primary_uvs,
        "uv_channels": uv_channels,
        "uv_channel_descriptors": uv_descriptors,
        "reported_vertex_count": reported_vertex_count,
        "actual_vertex_count": actual_vertex_count,
        "truncated": actual_vertex_count < reported_vertex_count,
    }


def _flatten_uv_channel(channel):
    output = []
    for uv in channel:
        if uv is None or len(uv) < 2:
            output.extend((0.0, 0.0))
        else:
            output.extend((float(uv[0]), float(uv[1])))
    return output


def _load_entry_scene_with_uv_channels(parsed, entry, require_store=None):
    scene = _ORIGINAL_LOAD_ENTRY_SCENE(parsed, entry, require_store)
    model = pak_extract.load_model_bytes(get_entry_asset(parsed, entry))
    max_channels = 0

    for vbuf_index, source_vertex_set in model.get("vertex_sets", {}).items():
        target = scene.get("vertex_buffers", {}).get(vbuf_index)
        if target is None:
            continue
        channels = list(source_vertex_set.get("uv_channels") or [])
        if not channels:
            channels = [list(source_vertex_set.get("uvs") or [])]
        flattened = [_flatten_uv_channel(channel) for channel in channels]
        if not flattened:
            flattened = [[0.0, 0.0] * int(target.get("vertex_count", 0))]
        target["uv_channels"] = flattened
        target["uv_channel_descriptors"] = list(source_vertex_set.get("uv_channel_descriptors") or [])
        max_channels = max(max_channels, len(flattened))

    scene["uv_channel_count"] = max(1, max_channels)
    return scene


def _make_uv_checker_image():
    if mv.PILImage is None:
        return None
    size = 1024
    image = mv.PILImage.new("RGBA", (size, size), (32, 32, 36, 255))
    draw = ImageDraw.Draw(image) if ImageDraw is not None else None
    cells = 8
    cell = size // cells
    colors = (
        (224, 224, 224, 255),
        (70, 74, 84, 255),
    )
    if draw is not None:
        for y in range(cells):
            for x in range(cells):
                draw.rectangle(
                    (x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1),
                    fill=colors[(x + y) & 1],
                )
                draw.text((x * cell + 8, y * cell + 8), f"{x},{y}", fill=(20, 20, 20, 255) if (x + y) % 2 == 0 else (245, 245, 245, 255))
        draw.rectangle((0, 0, size - 1, 42), fill=(190, 50, 55, 255))
        draw.text((12, 12), "IMAGE TOP / GL V=1", fill=(255, 255, 255, 255))
        draw.rectangle((0, size - 43, size - 1, size - 1), fill=(45, 90, 200, 255))
        draw.text((12, size - 32), "IMAGE BOTTOM / GL V=0", fill=(255, 255, 255, 255))
        draw.line((0, 0, size - 1, size - 1), fill=(255, 220, 40, 255), width=6)
        draw.line((size - 1, 0, 0, size - 1), fill=(30, 220, 160, 255), width=6)
    return image


def _material_color(material_index):
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


_ORIGINAL_PARSE_VERTICES = pak_extract.parse_vertices
_ORIGINAL_LOAD_ENTRY_SCENE = mv.load_entry_scene
_BASE_VIEWER = mv.MeshViewer


class DiagnosticMeshViewer(_BASE_VIEWER):
    def __init__(self, parent, parsed, entry, require_store=None):
        super().__init__(parent, parsed, entry, require_store=require_store)
        self.display_mode = tk.StringVar(self, value="Texturen")
        self.uv_channel_name = tk.StringVar(self, value="UV0")
        self.blender_v = tk.BooleanVar(self, value=True)
        self._uv_debug_texture = None

        toolbar = None
        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                toolbar = child
                break
        if toolbar is not None:
            ttk.Label(toolbar, text="Darstellung").pack(side="left", padx=(12, 3))
            mode_box = ttk.Combobox(
                toolbar,
                textvariable=self.display_mode,
                values=("Texturen", "UV-Testbild", "Material-IDs"),
                state="readonly",
                width=12,
            )
            mode_box.pack(side="left")
            ttk.Label(toolbar, text="UV").pack(side="left", padx=(10, 3))
            uv_values = tuple(f"UV{i}" for i in range(int(self.scene.get("uv_channel_count", 1))))
            uv_box = ttk.Combobox(
                toolbar,
                textvariable=self.uv_channel_name,
                values=uv_values,
                state="readonly",
                width=5,
            )
            uv_box.pack(side="left")
            ttk.Checkbutton(
                toolbar,
                text="V wie Blender",
                variable=self.blender_v,
                command=self.request_render,
            ).pack(side="left", padx=(8, 0))
            ttk.Button(toolbar, text="UV-Diagnose", command=self.show_uv_diagnostics).pack(side="left", padx=(8, 0))

        self.display_mode.trace_add("write", lambda *_args: self.request_render())
        self.uv_channel_name.trace_add("write", lambda *_args: self.request_render())

    def _selected_uv_channel(self):
        text = str(self.uv_channel_name.get() or "UV0").upper()
        try:
            return max(0, int(text.replace("UV", "")))
        except Exception:
            return 0

    def _upload_geometry(self):
        super()._upload_geometry()
        for vbuf_index, source in self.scene.get("vertex_buffers", {}).items():
            gpu = self._gpu_vbufs.get(vbuf_index)
            if gpu is None:
                continue
            raw_arrays = []
            blender_arrays = []
            for channel in source.get("uv_channels") or [source.get("uvs") or []]:
                raw = list(channel)
                blender = []
                for offset in range(0, len(raw), 2):
                    u = float(raw[offset]) if offset < len(raw) else 0.0
                    v = float(raw[offset + 1]) if offset + 1 < len(raw) else 0.0
                    blender.extend((u, 1.0 - v))
                raw_arrays.append((ctypes.c_float * len(raw))(*raw))
                blender_arrays.append((ctypes.c_float * len(blender))(*blender))
            gpu["uv_channels_raw"] = raw_arrays
            gpu["uv_channels_blender"] = blender_arrays

    def _upload_textures(self):
        checker = _make_uv_checker_image()
        if checker is not None:
            self.scene["texture_images"][_DEBUG_TEXTURE_KEY] = checker
        try:
            super()._upload_textures()
            self._uv_debug_texture = self._textures.get(_DEBUG_TEXTURE_KEY)
        finally:
            self.scene["texture_images"].pop(_DEBUG_TEXTURE_KEY, None)

    def _render(self):
        self._render_pending = False
        if self._closing or not self._make_current():
            return
        gl = self._wgl.opengl
        width = max(1, self.viewport.winfo_width())
        height = max(1, self.viewport.winfo_height())
        gl.glViewport(0, 0, width, height)
        gl.glClear(mv.GL_COLOR_BUFFER_BIT | mv.GL_DEPTH_BUFFER_BIT)
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
        light_position = (ctypes.c_float * 4)(2.5, 4.0, 3.0, 0.0)
        gl.glLightfv(mv.GL_LIGHT0, mv.GL_POSITION, light_position)

        if self.show_grid.get():
            self._draw_grid()

        mode = str(self.display_mode.get() or "Texturen")
        use_lighting = self.lighting_enabled.get() and mode == "Texturen"
        gl.glEnable(mv.GL_LIGHTING) if use_lighting else gl.glDisable(mv.GL_LIGHTING)
        if self.cull_faces.get():
            gl.glEnable(mv.GL_CULL_FACE)
            gl.glCullFace(mv.GL_BACK)
        else:
            gl.glDisable(mv.GL_CULL_FACE)
        gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_LINE if self.wireframe.get() else mv.GL_FILL)
        gl.glEnableClientState(mv.GL_VERTEX_ARRAY)
        gl.glEnableClientState(mv.GL_NORMAL_ARRAY)
        gl.glEnableClientState(mv.GL_TEXTURE_COORD_ARRAY)

        selected_channel = self._selected_uv_channel()
        bound_vbuf = None
        for mesh in self._gpu_meshes:
            vbuf_index = mesh["vbuf_index"]
            if vbuf_index != bound_vbuf:
                vbuf = self._gpu_vbufs[vbuf_index]
                gl.glVertexPointer(3, mv.GL_FLOAT, 0, ctypes.cast(vbuf["positions"], ctypes.c_void_p))
                gl.glNormalPointer(mv.GL_FLOAT, 0, ctypes.cast(vbuf["normals"], ctypes.c_void_p))
                channel_arrays = vbuf["uv_channels_blender"] if self.blender_v.get() else vbuf["uv_channels_raw"]
                channel_index = min(selected_channel, max(0, len(channel_arrays) - 1))
                gl.glTexCoordPointer(2, mv.GL_FLOAT, 0, ctypes.cast(channel_arrays[channel_index], ctypes.c_void_p))
                bound_vbuf = vbuf_index

            if mode == "UV-Testbild" and self._uv_debug_texture:
                gl.glEnable(mv.GL_TEXTURE_2D)
                gl.glBindTexture(mv.GL_TEXTURE_2D, self._uv_debug_texture)
                gl.glColor4f(1.0, 1.0, 1.0, 1.0)
            elif mode == "Texturen":
                texture_id = self._textures.get(mesh["material_index"])
                if self.textures_enabled.get() and texture_id:
                    gl.glEnable(mv.GL_TEXTURE_2D)
                    gl.glBindTexture(mv.GL_TEXTURE_2D, texture_id)
                    gl.glColor4f(1.0, 1.0, 1.0, 1.0)
                else:
                    gl.glDisable(mv.GL_TEXTURE_2D)
                    r, g, b = _material_color(mesh["material_index"])
                    gl.glColor4f(r, g, b, 1.0)
            else:
                gl.glDisable(mv.GL_TEXTURE_2D)
                r, g, b = _material_color(mesh["material_index"])
                gl.glColor4f(r, g, b, 1.0)

            gl.glDrawElements(
                mv.GL_TRIANGLES,
                mesh["index_count"],
                mv.GL_UNSIGNED_INT,
                ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
            )

        gl.glDisableClientState(mv.GL_TEXTURE_COORD_ARRAY)
        gl.glDisableClientState(mv.GL_NORMAL_ARRAY)
        gl.glDisableClientState(mv.GL_VERTEX_ARRAY)
        gl.glBindTexture(mv.GL_TEXTURE_2D, 0)
        gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_FILL)
        self._wgl.gdi.SwapBuffers(self._hdc)

    def show_uv_diagnostics(self):
        selected_channel = self._selected_uv_channel()
        lines = [
            f"Modell: {self.scene.get('name')}",
            f"Aktiver UV-Kanal: UV{selected_channel}",
            f"V-Konvention: {'Blender/OBJ (1-V)' if self.blender_v.get() else 'Rohdaten'}",
            "",
            "Vertexbuffer:",
        ]
        for vbuf_index in sorted(self.scene.get("vertex_buffers", {})):
            source = self.scene["vertex_buffers"][vbuf_index]
            channels = source.get("uv_channels") or []
            descriptors = source.get("uv_channel_descriptors") or []
            lines.append(f"  VBUF {vbuf_index}: {source.get('vertex_count', 0)} Vertices, {len(channels)} UV-Kanal/Kanäle")
            for channel_index, channel in enumerate(channels):
                us = [float(channel[i]) for i in range(0, len(channel), 2)]
                vs = [float(channel[i]) for i in range(1, len(channel), 2)]
                descriptor = descriptors[channel_index] if channel_index < len(descriptors) else {}
                outside = sum(1 for u, v in zip(us, vs) if u < 0.0 or u > 1.0 or v < 0.0 or v > 1.0)
                if us and vs:
                    lines.append(
                        "    UV{}: semantic={} format={} offset={} | U {:.5g}..{:.5g} | V {:.5g}..{:.5g} | außerhalb 0..1: {}/{}".format(
                            channel_index,
                            descriptor.get("semantic", "?"),
                            descriptor.get("format", "?"),
                            descriptor.get("offset", "?"),
                            min(us), max(us), min(vs), max(vs), outside, len(us),
                        )
                    )
                else:
                    lines.append(f"    UV{channel_index}: leer")

        lines.extend(("", "Meshes / Materialien / Texturen:"))
        materials = self.scene.get("materials") or []
        texture_names = self.scene.get("texture_names") or {}
        for mesh in self.scene.get("meshes") or []:
            material_index = int(mesh.get("material_index", 0))
            material_name = materials[material_index] if material_index < len(materials) else f"material_{material_index}"
            texture_name = texture_names.get(material_index, "<keine diffuse TXTR geladen>")
            lines.append(
                f"  Mesh {mesh.get('mesh_index')} | VBUF {mesh.get('vbuf_index')} | Material {material_index}: {material_name} | TXTR: {texture_name}"
            )

        if self.scene.get("texture_errors"):
            lines.extend(("", "TXTR-Fehler:"))
            lines.extend(f"  {error}" for error in self.scene["texture_errors"])

        lines.extend((
            "",
            "Auswertung:",
            "- UV-Testbild falsch, aber Material-IDs korrekt: UV-Konvention oder UV-Kanal falsch.",
            "- UV-Testbild korrekt, reale Textur falsch: falsche TXTR-Referenz oder Materialbindung.",
            "- Material-IDs schon falsch verteilt: Mesh->Material-Index ist falsch.",
            "- UV0 und UV1 vergleichen, wenn mehrere Kanäle vorhanden sind.",
        ))

        dialog = tk.Toplevel(self)
        dialog.title("UV-Diagnose")
        dialog.geometry("980x680")
        text = ScrolledText(dialog, wrap="none")
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    pak_extract.parse_vertices = _parse_vertices_with_uv_channels
    mv.load_entry_scene = _load_entry_scene_with_uv_channels
    mv.MeshViewer = DiagnosticMeshViewer
