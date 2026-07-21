"""Lightweight Tkinter mesh viewer used by the PAK browser UI.

The first implementation deliberately has no external OpenGL dependency. It
renders triangle edges into a Canvas and supports orbit, pan, zoom, fit and
wireframe/solid-style display. Geometry is supplied through the existing model
OBJ exporter, so CMDL/SMDL/WMDL decoding stays in one place.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from pak_core import PakError
from pak_extract import export_model_entry_as_obj


def _parse_obj(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if line.startswith("v "):
            parts = line.split()
            if len(parts) >= 4:
                vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif line.startswith("f "):
            indices: list[int] = []
            for token in line.split()[1:]:
                value = token.split("/", 1)[0]
                if not value:
                    continue
                index = int(value)
                if index < 0:
                    index = len(vertices) + index
                else:
                    index -= 1
                if 0 <= index < len(vertices):
                    indices.append(index)
            if len(indices) >= 3:
                faces.append(tuple(indices))
    if not vertices or not faces:
        raise PakError("Das Modell enthält keine darstellbare Dreiecksgeometrie")
    return vertices, faces


def load_entry_geometry(parsed, entry):
    with tempfile.TemporaryDirectory(prefix="pakpy_mesh_viewer_") as folder:
        result = export_model_entry_as_obj(parsed, entry, folder, write_mtl=False)
        vertices, faces = _parse_obj(Path(result["obj_path"]))
    return vertices, faces, result


class MeshViewer(tk.Toplevel):
    def __init__(self, parent, parsed, entry):
        super().__init__(parent)
        self.title(f'Mesh Viewer - {entry.get("display_name") or entry.get("name") or entry.get("uuid_hex", "Modell")}')
        self.geometry("980x720")
        self.minsize(640, 480)
        self.transient(parent)

        self.vertices, self.faces, self.export_info = load_entry_geometry(parsed, entry)
        self.yaw = math.radians(35.0)
        self.pitch = math.radians(-20.0)
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.last_mouse: tuple[int, int] | None = None
        self.drag_mode = "orbit"
        self.fill_faces = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self._normalise_geometry()

        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Ansicht einpassen", command=self.fit_view).pack(side="left")
        ttk.Checkbutton(toolbar, text="Flächen", variable=self.fill_faces, command=self.redraw).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(toolbar, text="Grid", variable=self.show_grid, command=self.redraw).pack(side="left", padx=(12, 0))
        self.status = ttk.Label(toolbar, text=self._status_text())
        self.status.pack(side="right")

        self.canvas = tk.Canvas(self, background="#20242a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self.canvas.bind("<Configure>", lambda _event: self.redraw())
        self.canvas.bind("<ButtonPress-1>", self._start_orbit)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonPress-2>", self._start_pan)
        self.canvas.bind("<B2-Motion>", self._drag)
        self.canvas.bind("<ButtonPress-3>", self._start_pan)
        self.canvas.bind("<B3-Motion>", self._drag)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _event: self._zoom_by(1.12))
        self.canvas.bind("<Button-5>", lambda _event: self._zoom_by(1 / 1.12))
        self.bind("<Key-r>", lambda _event: self.fit_view())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.focus_set()
        self.after_idle(self.redraw)

    def _normalise_geometry(self):
        xs = [v[0] for v in self.vertices]
        ys = [v[1] for v in self.vertices]
        zs = [v[2] for v in self.vertices]
        center = ((min(xs) + max(xs)) * 0.5, (min(ys) + max(ys)) * 0.5, (min(zs) + max(zs)) * 0.5)
        centered = [(x - center[0], y - center[1], z - center[2]) for x, y, z in self.vertices]
        radius = max((math.sqrt(x*x + y*y + z*z) for x, y, z in centered), default=1.0)
        self.vertices = [(x / radius, y / radius, z / radius) for x, y, z in centered]

    def _status_text(self):
        triangles = sum(max(0, len(face) - 2) for face in self.faces)
        return f"{len(self.vertices)} Vertices | {triangles} Dreiecke | Ziehen: Orbit · Rechts/Mitte: Pan · Rad: Zoom"

    def fit_view(self):
        self.yaw = math.radians(35.0)
        self.pitch = math.radians(-20.0)
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.redraw()

    def _start_orbit(self, event):
        self.last_mouse = (event.x, event.y)
        self.drag_mode = "orbit"

    def _start_pan(self, event):
        self.last_mouse = (event.x, event.y)
        self.drag_mode = "pan"

    def _drag(self, event):
        if self.last_mouse is None:
            self.last_mouse = (event.x, event.y)
            return
        dx = event.x - self.last_mouse[0]
        dy = event.y - self.last_mouse[1]
        self.last_mouse = (event.x, event.y)
        if self.drag_mode == "pan":
            self.pan_x += dx
            self.pan_y += dy
        else:
            self.yaw += dx * 0.01
            self.pitch = max(-1.5, min(1.5, self.pitch + dy * 0.01))
        self.redraw()

    def _wheel(self, event):
        self._zoom_by(1.12 if event.delta > 0 else 1 / 1.12)

    def _zoom_by(self, factor):
        self.zoom = max(0.08, min(20.0, self.zoom * factor))
        self.redraw()

    def _project_vertices(self):
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        scale = min(width, height) * 0.38 * self.zoom
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        projected = []
        for x, y, z in self.vertices:
            x1 = cy * x + sy * z
            z1 = -sy * x + cy * z
            y2 = cp * y - sp * z1
            z2 = sp * y + cp * z1
            distance = 4.0
            perspective = distance / max(0.35, distance - z2)
            sx = width * 0.5 + self.pan_x + x1 * scale * perspective
            sy2 = height * 0.5 + self.pan_y - y2 * scale * perspective
            projected.append((sx, sy2, z2))
        return projected

    def _draw_grid(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        step = max(24, int(min(width, height) / 12))
        cx = width // 2 + int(self.pan_x)
        cy = height // 2 + int(self.pan_y)
        for x in range(cx % step, width, step):
            self.canvas.create_line(x, 0, x, height, fill="#2d333b")
        for y in range(cy % step, height, step):
            self.canvas.create_line(0, y, width, y, fill="#2d333b")
        self.canvas.create_line(0, cy, width, cy, fill="#505966")
        self.canvas.create_line(cx, 0, cx, height, fill="#505966")

    def redraw(self):
        if not hasattr(self, "canvas"):
            return
        self.canvas.delete("all")
        if self.show_grid.get():
            self._draw_grid()
        points = self._project_vertices()
        draw_faces = []
        for face in self.faces:
            polygon = [points[index] for index in face]
            depth = sum(point[2] for point in polygon) / len(polygon)
            draw_faces.append((depth, polygon))
        draw_faces.sort(key=lambda item: item[0])
        for depth, polygon in draw_faces:
            coords = [coordinate for x, y, _z in polygon for coordinate in (x, y)]
            if self.fill_faces.get():
                shade = max(52, min(132, int(88 + depth * 24)))
                fill = f"#{shade:02x}{min(150, shade + 12):02x}{min(170, shade + 25):02x}"
            else:
                fill = ""
            self.canvas.create_polygon(coords, fill=fill, outline="#cbd5df", width=1)


def open_mesh_viewer(parent, parsed, entry):
    return MeshViewer(parent, parsed, entry)
