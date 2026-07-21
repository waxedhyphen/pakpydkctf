"""GPU accelerated model viewer for CMDL/SMDL/WMDL assets.

On Windows this embeds an OpenGL 1.1 context directly into a Tk child window via
WGL. It has no PyOpenGL dependency: the fixed-function API surface used here is
bound through ctypes. Geometry is read directly from the model decoder and linked
TXTR assets are decoded through txtrpreview.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import math
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from pak_core import PakError, get_entry_asset
from pak_extract import build_faces, get_mtl_slot_for_ref_tag, load_model_bytes

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

try:
    from txtrpreview import decode_txtr_image, parse_txtr_asset
except Exception:
    decode_txtr_image = None
    parse_txtr_asset = None

MODEL_TYPES = {"CMDL", "SMDL", "WMDL"}
DIFFUSE_TAG_PRIORITY = (
    "DIFFTXTR", "DIFTTXTR", "COLRTXTR", "ALBDTXTR",
    "BASETXTR", "BASEXTR", "ALBRTXTR",
)


def _apply_material_names(model, entry):
    materials = list(model.get("materials", []))
    for material in entry.get("model_materials", []):
        index = int(material.get("index", 0))
        while len(materials) <= index:
            materials.append(f"material_{len(materials)}")
        materials[index] = str(material.get("name") or f"material_{index}")
    model["materials"] = materials


def _pick_diffuse_ref(material):
    refs = list(material.get("txtr_refs", []))
    for wanted in DIFFUSE_TAG_PRIORITY:
        for ref in refs:
            if str(ref.get("tag", "")).upper() == wanted:
                return ref
    for ref in refs:
        if get_mtl_slot_for_ref_tag(ref.get("tag")) == "map_Kd":
            return ref
    return None


def _resolve_asset(parsed, uuid_hex, require_store=None):
    entry = parsed.get("uuid_to_entry", {}).get(uuid_hex)
    if entry is not None:
        return get_entry_asset(parsed, entry), entry
    if require_store is not None:
        try:
            asset, entry, _source = require_store.resolve_asset(parsed, uuid_hex)
            if asset is not None and entry is not None:
                return asset, entry
        except Exception:
            pass
    return None, None


def _decode_material_textures(parsed, entry, require_store=None):
    images = {}
    names = {}
    errors = []
    cache = {}
    if PILImage is None or decode_txtr_image is None or parse_txtr_asset is None:
        return images, names, ["Pillow/TXTR-Decoder nicht verfügbar"]
    for material in entry.get("model_materials", []):
        material_index = int(material.get("index", 0))
        ref = _pick_diffuse_ref(material)
        if ref is None:
            continue
        uuid_hex = str(ref.get("uuid_hex", ""))
        if not uuid_hex:
            continue
        try:
            if uuid_hex not in cache:
                asset, txtr_entry = _resolve_asset(parsed, uuid_hex, require_store)
                if asset is None:
                    raise PakError(f"TXTR {uuid_hex} nicht gefunden")
                info = parse_txtr_asset(asset)
                image, _decode_info = decode_txtr_image(info, "Auto")
                cache[uuid_hex] = image.convert("RGBA")
                cache[(uuid_hex, "name")] = (
                    txtr_entry.get("display_name")
                    or txtr_entry.get("name")
                    or uuid_hex
                )
            images[material_index] = cache[uuid_hex]
            names[material_index] = cache[(uuid_hex, "name")]
        except Exception as exc:
            errors.append(f"Material {material_index}: {exc}")
    return images, names, errors


def load_entry_scene(parsed, entry, require_store=None):
    if entry.get("type") not in MODEL_TYPES:
        raise PakError("Mesh Viewer unterstützt nur CMDL, SMDL und WMDL")
    model = load_model_bytes(get_entry_asset(parsed, entry))
    _apply_material_names(model, entry)
    all_positions = [
        position
        for vertex_set in model["vertex_sets"].values()
        for position in vertex_set.get("positions", [])
    ]
    if not all_positions:
        raise PakError("Das Modell enthält keine Vertexpositionen")
    min_x = min(v[0] for v in all_positions)
    min_y = min(v[1] for v in all_positions)
    min_z = min(v[2] for v in all_positions)
    max_x = max(v[0] for v in all_positions)
    max_y = max(v[1] for v in all_positions)
    max_z = max(v[2] for v in all_positions)
    center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5, (min_z + max_z) * 0.5)
    radius = max(
        math.sqrt((x - center[0]) ** 2 + (y - center[1]) ** 2 + (z - center[2]) ** 2)
        for x, y, z in all_positions
    )
    if radius <= 1e-12:
        radius = 1.0
    vertex_buffers = {}
    for index, vertex_set in model["vertex_sets"].items():
        positions = []
        normals = []
        uvs = []
        source_positions = vertex_set.get("positions", [])
        source_normals = vertex_set.get("normals", [])
        source_uvs = vertex_set.get("uvs", [])
        for vertex_index, (x, y, z) in enumerate(source_positions):
            positions.extend(((x - center[0]) / radius, (y - center[1]) / radius, (z - center[2]) / radius))
            normal = source_normals[vertex_index] if vertex_index < len(source_normals) else None
            normals.extend((0.0, 0.0, 1.0) if normal is None else (float(normal[0]), float(normal[1]), float(normal[2])))
            uv = source_uvs[vertex_index] if vertex_index < len(source_uvs) else None
            uvs.extend((0.0, 0.0) if uv is None else (float(uv[0]), float(uv[1])))
        vertex_buffers[index] = {
            "positions": positions,
            "normals": normals,
            "uvs": uvs,
            "vertex_count": len(source_positions),
        }
    draw_meshes = []
    triangle_count = 0
    for mesh in model["meshes"]:
        vbuf_index = mesh["vertex_buffer_index"]
        ibuf_index = mesh["index_buffer_index"]
        if vbuf_index not in vertex_buffers or ibuf_index not in model["index_sets"]:
            continue
        start = mesh["index_buffer_offset"]
        end = start + mesh["index_count"]
        source_indices = model["index_sets"][ibuf_index][start:end]
        faces = build_faces(
            mesh["primitive_mode"], source_indices,
            vertex_limit=vertex_buffers[vbuf_index]["vertex_count"],
        )
        if not faces:
            continue
        indices = [value for face in faces for value in face]
        triangle_count += len(faces)
        draw_meshes.append({
            "mesh_index": mesh["mesh_index"],
            "vbuf_index": vbuf_index,
            "material_index": mesh["material_index"],
            "indices": indices,
        })
    if not draw_meshes:
        raise PakError("Das Modell enthält keine darstellbaren Dreiecke")
    texture_images, texture_names, texture_errors = _decode_material_textures(parsed, entry, require_store)
    return {
        "name": entry.get("display_name") or entry.get("name") or entry.get("uuid_hex", "Modell"),
        "vertex_buffers": vertex_buffers,
        "meshes": draw_meshes,
        "materials": model.get("materials", []),
        "texture_images": texture_images,
        "texture_names": texture_names,
        "texture_errors": texture_errors,
        "vertex_count": sum(v["vertex_count"] for v in vertex_buffers.values()),
        "triangle_count": triangle_count,
    }

GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100
GL_LINES = 0x0001
GL_TRIANGLES = 0x0004
GL_FLOAT = 0x1406
GL_UNSIGNED_BYTE = 0x1401
GL_UNSIGNED_INT = 0x1405
GL_FRONT_AND_BACK = 0x0408
GL_LINE = 0x1B01
GL_FILL = 0x1B02
GL_MODELVIEW = 0x1700
GL_PROJECTION = 0x1701
GL_DEPTH_TEST = 0x0B71
GL_LEQUAL = 0x0203
GL_LIGHTING = 0x0B50
GL_LIGHT0 = 0x4000
GL_POSITION = 0x1203
GL_AMBIENT = 0x1200
GL_DIFFUSE = 0x1201
GL_NORMALIZE = 0x0BA1
GL_SMOOTH = 0x1D01
GL_TEXTURE_2D = 0x0DE1
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_LINEAR = 0x2601
GL_REPEAT = 0x2901
GL_RGBA = 0x1908
GL_UNPACK_ALIGNMENT = 0x0CF5
GL_VERTEX_ARRAY = 0x8074
GL_NORMAL_ARRAY = 0x8075
GL_TEXTURE_COORD_ARRAY = 0x8078
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303
GL_COLOR_MATERIAL = 0x0B57
GL_AMBIENT_AND_DIFFUSE = 0x1602
GL_MAX_TEXTURE_SIZE = 0x0D33
GL_CULL_FACE = 0x0B44
GL_BACK = 0x0405
GL_CCW = 0x0901
GL_LIGHT_MODEL_TWO_SIDE = 0x0B52


class PIXELFORMATDESCRIPTOR(ctypes.Structure):
    _fields_ = [
        ("nSize", wintypes.WORD), ("nVersion", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("iPixelType", wintypes.BYTE),
        ("cColorBits", wintypes.BYTE), ("cRedBits", wintypes.BYTE),
        ("cRedShift", wintypes.BYTE), ("cGreenBits", wintypes.BYTE),
        ("cGreenShift", wintypes.BYTE), ("cBlueBits", wintypes.BYTE),
        ("cBlueShift", wintypes.BYTE), ("cAlphaBits", wintypes.BYTE),
        ("cAlphaShift", wintypes.BYTE), ("cAccumBits", wintypes.BYTE),
        ("cAccumRedBits", wintypes.BYTE), ("cAccumGreenBits", wintypes.BYTE),
        ("cAccumBlueBits", wintypes.BYTE), ("cAccumAlphaBits", wintypes.BYTE),
        ("cDepthBits", wintypes.BYTE), ("cStencilBits", wintypes.BYTE),
        ("cAuxBuffers", wintypes.BYTE), ("iLayerType", wintypes.BYTE),
        ("bReserved", wintypes.BYTE), ("dwLayerMask", wintypes.DWORD),
        ("dwVisibleMask", wintypes.DWORD), ("dwDamageMask", wintypes.DWORD),
    ]


class _WGL:
    PFD_DOUBLEBUFFER = 0x00000001
    PFD_DRAW_TO_WINDOW = 0x00000004
    PFD_SUPPORT_OPENGL = 0x00000020
    PFD_TYPE_RGBA = 0
    PFD_MAIN_PLANE = 0

    def __init__(self):
        if sys.platform != "win32":
            raise PakError("Der GPU-Mesh-Viewer benötigt derzeit Windows/WGL")
        self.opengl = ctypes.windll.opengl32
        self.gdi = ctypes.windll.gdi32
        self.user = ctypes.windll.user32
        self._bind()

    def _bind(self):
        c_uint = ctypes.c_uint
        c_int = ctypes.c_int
        c_float = ctypes.c_float
        c_void_p = ctypes.c_void_p
        self.gdi.ChoosePixelFormat.argtypes = [c_void_p, ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
        self.gdi.ChoosePixelFormat.restype = c_int
        self.gdi.SetPixelFormat.argtypes = [c_void_p, c_int, ctypes.POINTER(PIXELFORMATDESCRIPTOR)]
        self.gdi.SetPixelFormat.restype = wintypes.BOOL
        self.gdi.SwapBuffers.argtypes = [c_void_p]
        self.gdi.SwapBuffers.restype = wintypes.BOOL
        self.user.GetDC.argtypes = [c_void_p]
        self.user.GetDC.restype = c_void_p
        self.user.ReleaseDC.argtypes = [c_void_p, c_void_p]
        self.opengl.wglCreateContext.argtypes = [c_void_p]
        self.opengl.wglCreateContext.restype = c_void_p
        self.opengl.wglMakeCurrent.argtypes = [c_void_p, c_void_p]
        self.opengl.wglMakeCurrent.restype = wintypes.BOOL
        self.opengl.wglDeleteContext.argtypes = [c_void_p]
        self.opengl.wglDeleteContext.restype = wintypes.BOOL
        signatures = {
            "glViewport": ([c_int, c_int, c_int, c_int], None),
            "glClearColor": ([c_float, c_float, c_float, c_float], None),
            "glClear": ([c_uint], None),
            "glEnable": ([c_uint], None),
            "glDisable": ([c_uint], None),
            "glDepthFunc": ([c_uint], None),
            "glShadeModel": ([c_uint], None),
            "glMatrixMode": ([c_uint], None),
            "glLoadIdentity": ([], None),
            "glFrustum": ([ctypes.c_double] * 6, None),
            "glTranslatef": ([c_float, c_float, c_float], None),
            "glRotatef": ([c_float, c_float, c_float, c_float], None),
            "glLightfv": ([c_uint, c_uint, ctypes.POINTER(c_float)], None),
            "glLightModeli": ([c_uint, c_int], None),
            "glColorMaterial": ([c_uint, c_uint], None),
            "glColor4f": ([c_float, c_float, c_float, c_float], None),
            "glPolygonMode": ([c_uint, c_uint], None),
            "glCullFace": ([c_uint], None),
            "glFrontFace": ([c_uint], None),
            "glBegin": ([c_uint], None),
            "glEnd": ([], None),
            "glVertex3f": ([c_float, c_float, c_float], None),
            "glGenTextures": ([c_int, ctypes.POINTER(c_uint)], None),
            "glDeleteTextures": ([c_int, ctypes.POINTER(c_uint)], None),
            "glBindTexture": ([c_uint, c_uint], None),
            "glTexParameteri": ([c_uint, c_uint, c_int], None),
            "glPixelStorei": ([c_uint, c_int], None),
            "glTexImage2D": ([c_uint, c_int, c_int, c_int, c_int, c_int, c_uint, c_uint, c_void_p], None),
            "glEnableClientState": ([c_uint], None),
            "glDisableClientState": ([c_uint], None),
            "glVertexPointer": ([c_int, c_uint, c_int, c_void_p], None),
            "glNormalPointer": ([c_uint, c_int, c_void_p], None),
            "glTexCoordPointer": ([c_int, c_uint, c_int, c_void_p], None),
            "glDrawElements": ([c_uint, c_int, c_uint, c_void_p], None),
            "glBlendFunc": ([c_uint, c_uint], None),
            "glGetIntegerv": ([c_uint, ctypes.POINTER(c_int)], None),
        }
        for name, (argtypes, restype) in signatures.items():
            function = getattr(self.opengl, name)
            function.argtypes = argtypes
            function.restype = restype


class MeshViewer(tk.Toplevel):
    def __init__(self, parent, parsed, entry, require_store=None):
        super().__init__(parent)
        self.scene = load_entry_scene(parsed, entry, require_store)
        self.title(f"Mesh Viewer - {self.scene['name']}")
        self.geometry("1100x780")
        self.minsize(700, 500)
        self.transient(parent)
        self.wireframe = tk.BooleanVar(value=False)
        self.textures_enabled = tk.BooleanVar(value=True)
        self.lighting_enabled = tk.BooleanVar(value=True)
        self.show_grid = tk.BooleanVar(value=True)
        self.cull_faces = tk.BooleanVar(value=False)
        self.yaw = 35.0
        self.pitch = -20.0
        self.distance = 3.3
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.last_mouse = None
        self.drag_mode = "orbit"
        self._render_pending = False
        self._closing = False
        self._wgl = None
        self._hdc = None
        self._hglrc = None
        self._hwnd = None
        self._gpu_vbufs = {}
        self._gpu_meshes = []
        self._textures = {}
        toolbar = ttk.Frame(self, padding=(8, 8, 8, 4))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Ansicht einpassen", command=self.fit_view).pack(side="left")
        for text, variable in (
            ("Texturen", self.textures_enabled),
            ("Beleuchtung", self.lighting_enabled),
            ("Wireframe", self.wireframe),
            ("Grid", self.show_grid),
            ("Backface Culling", self.cull_faces),
        ):
            ttk.Checkbutton(toolbar, text=text, variable=variable, command=self.request_render).pack(side="left", padx=(10, 0))
        ttk.Label(toolbar, text=self._status_text()).pack(side="right")
        self.viewport = tk.Frame(self, background="#20242a", takefocus=True)
        self.viewport.pack(fill="both", expand=True, padx=8, pady=(4, 8))
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
        self.bind("<Key-r>", lambda _event: self.fit_view())
        self.bind("<Escape>", lambda _event: self.close())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after_idle(self._initialise_gl)

    def _status_text(self):
        texture_count = len(self.scene["texture_images"])
        suffix = f" | {len(self.scene['texture_errors'])} TXTR nicht geladen" if self.scene["texture_errors"] else ""
        return (
            f"{self.scene['vertex_count']} Vertices | {self.scene['triangle_count']} Dreiecke | "
            f"{len(self.scene['meshes'])} Meshes | {texture_count} Texturen{suffix}"
        )

    def _initialise_gl(self):
        if self._closing:
            return
        try:
            self.update_idletasks()
            self.viewport.update_idletasks()
            self._wgl = _WGL()
            self._hwnd = ctypes.c_void_p(self.viewport.winfo_id())
            self._hdc = self._wgl.user.GetDC(self._hwnd)
            if not self._hdc:
                raise PakError("GetDC für den OpenGL-Viewport fehlgeschlagen")
            pfd = PIXELFORMATDESCRIPTOR()
            pfd.nSize = ctypes.sizeof(PIXELFORMATDESCRIPTOR)
            pfd.nVersion = 1
            pfd.dwFlags = self._wgl.PFD_DRAW_TO_WINDOW | self._wgl.PFD_SUPPORT_OPENGL | self._wgl.PFD_DOUBLEBUFFER
            pfd.iPixelType = self._wgl.PFD_TYPE_RGBA
            pfd.cColorBits = 32
            pfd.cAlphaBits = 8
            pfd.cDepthBits = 24
            pfd.cStencilBits = 8
            pfd.iLayerType = self._wgl.PFD_MAIN_PLANE
            pixel_format = self._wgl.gdi.ChoosePixelFormat(self._hdc, ctypes.byref(pfd))
            if pixel_format <= 0:
                raise PakError("Kein kompatibles OpenGL-Pixelformat gefunden")
            if not self._wgl.gdi.SetPixelFormat(self._hdc, pixel_format, ctypes.byref(pfd)):
                raise PakError("OpenGL-Pixelformat konnte nicht gesetzt werden")
            self._hglrc = self._wgl.opengl.wglCreateContext(self._hdc)
            if not self._hglrc:
                raise PakError("OpenGL-Kontext konnte nicht erzeugt werden")
            if not self._wgl.opengl.wglMakeCurrent(self._hdc, self._hglrc):
                raise PakError("OpenGL-Kontext konnte nicht aktiviert werden")
            self._setup_gl_state()
            self._upload_geometry()
            self._upload_textures()
            self.viewport.focus_set()
            self.request_render()
        except Exception as exc:
            messagebox.showerror("Mesh Viewer", f"GPU-Viewport konnte nicht gestartet werden:\n{exc}", parent=self)
            self.close()

    def _setup_gl_state(self):
        gl = self._wgl.opengl
        gl.glClearColor(0.075, 0.085, 0.105, 1.0)
        gl.glEnable(GL_DEPTH_TEST)
        gl.glDepthFunc(GL_LEQUAL)
        gl.glShadeModel(GL_SMOOTH)
        gl.glEnable(GL_NORMALIZE)
        gl.glEnable(GL_COLOR_MATERIAL)
        gl.glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        gl.glFrontFace(GL_CCW)
        light_ambient = (ctypes.c_float * 4)(0.28, 0.28, 0.32, 1.0)
        light_diffuse = (ctypes.c_float * 4)(0.90, 0.90, 0.90, 1.0)
        gl.glLightfv(GL_LIGHT0, GL_AMBIENT, light_ambient)
        gl.glLightfv(GL_LIGHT0, GL_DIFFUSE, light_diffuse)
        gl.glEnable(GL_LIGHT0)
        gl.glLightModeli(GL_LIGHT_MODEL_TWO_SIDE, 1)

    def _upload_geometry(self):
        for index, source in self.scene["vertex_buffers"].items():
            positions = (ctypes.c_float * len(source["positions"]))(*source["positions"])
            normals = (ctypes.c_float * len(source["normals"]))(*source["normals"])
            uvs = (ctypes.c_float * len(source["uvs"]))(*source["uvs"])
            self._gpu_vbufs[index] = {"positions": positions, "normals": normals, "uvs": uvs}
        for source in self.scene["meshes"]:
            indices = (ctypes.c_uint * len(source["indices"]))(*source["indices"])
            item = dict(source)
            item["gpu_indices"] = indices
            item["index_count"] = len(source["indices"])
            self._gpu_meshes.append(item)

    def _upload_textures(self):
        if not self.scene["texture_images"]:
            return
        gl = self._wgl.opengl
        max_size = ctypes.c_int(4096)
        gl.glGetIntegerv(GL_MAX_TEXTURE_SIZE, ctypes.byref(max_size))
        limit = max(256, int(max_size.value or 4096))
        for material_index, source_image in self.scene["texture_images"].items():
            image = source_image
            if max(image.size) > limit:
                scale = limit / float(max(image.size))
                size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
                resampling = getattr(getattr(PILImage, "Resampling", PILImage), "LANCZOS")
                image = image.resize(size, resampling)
            transpose_enum = getattr(getattr(PILImage, "Transpose", PILImage), "FLIP_TOP_BOTTOM")
            image = image.transpose(transpose_enum).convert("RGBA")
            pixel_buffer = ctypes.create_string_buffer(image.tobytes("raw", "RGBA"))
            texture_id = ctypes.c_uint()
            gl.glGenTextures(1, ctypes.byref(texture_id))
            gl.glBindTexture(GL_TEXTURE_2D, texture_id.value)
            gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT)
            gl.glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT)
            gl.glPixelStorei(GL_UNPACK_ALIGNMENT, 1)
            gl.glTexImage2D(
                GL_TEXTURE_2D, 0, GL_RGBA, image.width, image.height, 0,
                GL_RGBA, GL_UNSIGNED_BYTE, ctypes.cast(pixel_buffer, ctypes.c_void_p),
            )
            self._textures[material_index] = texture_id.value
        gl.glBindTexture(GL_TEXTURE_2D, 0)

    def _make_current(self):
        return bool(
            self._wgl and self._hdc and self._hglrc
            and self._wgl.opengl.wglMakeCurrent(self._hdc, self._hglrc)
        )

    def fit_view(self):
        self.yaw = 35.0
        self.pitch = -20.0
        self.distance = 3.3
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.request_render()

    def _start_orbit(self, event):
        self.last_mouse = (event.x, event.y)
        self.drag_mode = "orbit"
        self.viewport.focus_set()

    def _start_pan(self, event):
        self.last_mouse = (event.x, event.y)
        self.drag_mode = "pan"
        self.viewport.focus_set()

    def _drag(self, event):
        if self.last_mouse is None:
            self.last_mouse = (event.x, event.y)
            return
        dx = event.x - self.last_mouse[0]
        dy = event.y - self.last_mouse[1]
        self.last_mouse = (event.x, event.y)
        if self.drag_mode == "pan":
            scale = self.distance / max(300.0, min(self.viewport.winfo_width(), self.viewport.winfo_height()))
            self.pan_x += dx * scale
            self.pan_y -= dy * scale
        else:
            self.yaw += dx * 0.35
            self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.35))
        self.request_render()

    def _wheel(self, event):
        self._zoom_by(0.88 if event.delta > 0 else 1.0 / 0.88)

    def _zoom_by(self, factor):
        self.distance = max(0.25, min(100.0, self.distance * factor))
        self.request_render()

    def request_render(self, _event=None):
        if self._closing or self._render_pending:
            return
        self._render_pending = True
        self.after_idle(self._render)

    def _draw_grid(self):
        gl = self._wgl.opengl
        gl.glDisable(GL_TEXTURE_2D)
        gl.glDisable(GL_LIGHTING)
        gl.glColor4f(0.20, 0.23, 0.27, 1.0)
        gl.glBegin(GL_LINES)
        for i in range(-10, 11):
            value = i * 0.2
            gl.glVertex3f(-2.0, -1.0, value)
            gl.glVertex3f(2.0, -1.0, value)
            gl.glVertex3f(value, -1.0, -2.0)
            gl.glVertex3f(value, -1.0, 2.0)
        gl.glEnd()
        gl.glBegin(GL_LINES)
        gl.glColor4f(0.75, 0.20, 0.20, 1.0)
        gl.glVertex3f(-2.0, -1.0, 0.0)
        gl.glVertex3f(2.0, -1.0, 0.0)
        gl.glColor4f(0.20, 0.45, 0.80, 1.0)
        gl.glVertex3f(0.0, -1.0, -2.0)
        gl.glVertex3f(0.0, -1.0, 2.0)
        gl.glEnd()

    def _render(self):
        self._render_pending = False
        if self._closing or not self._make_current():
            return
        gl = self._wgl.opengl
        width = max(1, self.viewport.winfo_width())
        height = max(1, self.viewport.winfo_height())
        gl.glViewport(0, 0, width, height)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        gl.glMatrixMode(GL_PROJECTION)
        gl.glLoadIdentity()
        near = 0.05
        far = 250.0
        top = near * math.tan(math.radians(50.0) * 0.5)
        right = top * (width / float(height))
        gl.glFrustum(-right, right, -top, top, near, far)
        gl.glMatrixMode(GL_MODELVIEW)
        gl.glLoadIdentity()
        gl.glTranslatef(self.pan_x, self.pan_y, -self.distance)
        gl.glRotatef(self.pitch, 1.0, 0.0, 0.0)
        gl.glRotatef(self.yaw, 0.0, 1.0, 0.0)
        light_position = (ctypes.c_float * 4)(2.5, 4.0, 3.0, 0.0)
        gl.glLightfv(GL_LIGHT0, GL_POSITION, light_position)
        if self.show_grid.get():
            self._draw_grid()
        gl.glEnable(GL_LIGHTING) if self.lighting_enabled.get() else gl.glDisable(GL_LIGHTING)
        if self.cull_faces.get():
            gl.glEnable(GL_CULL_FACE)
            gl.glCullFace(GL_BACK)
        else:
            gl.glDisable(GL_CULL_FACE)
        gl.glPolygonMode(GL_FRONT_AND_BACK, GL_LINE if self.wireframe.get() else GL_FILL)
        gl.glColor4f(0.78, 0.80, 0.84, 1.0)
        gl.glEnableClientState(GL_VERTEX_ARRAY)
        gl.glEnableClientState(GL_NORMAL_ARRAY)
        gl.glEnableClientState(GL_TEXTURE_COORD_ARRAY)
        bound_vbuf = None
        for mesh in self._gpu_meshes:
            vbuf_index = mesh["vbuf_index"]
            if vbuf_index != bound_vbuf:
                vbuf = self._gpu_vbufs[vbuf_index]
                gl.glVertexPointer(3, GL_FLOAT, 0, ctypes.cast(vbuf["positions"], ctypes.c_void_p))
                gl.glNormalPointer(GL_FLOAT, 0, ctypes.cast(vbuf["normals"], ctypes.c_void_p))
                gl.glTexCoordPointer(2, GL_FLOAT, 0, ctypes.cast(vbuf["uvs"], ctypes.c_void_p))
                bound_vbuf = vbuf_index
            texture_id = self._textures.get(mesh["material_index"])
            if self.textures_enabled.get() and texture_id:
                gl.glEnable(GL_TEXTURE_2D)
                gl.glBindTexture(GL_TEXTURE_2D, texture_id)
                gl.glColor4f(1.0, 1.0, 1.0, 1.0)
            else:
                gl.glDisable(GL_TEXTURE_2D)
                shade = 0.68 + (mesh["material_index"] % 4) * 0.055
                gl.glColor4f(shade, shade, min(0.92, shade + 0.06), 1.0)
            gl.glDrawElements(
                GL_TRIANGLES, mesh["index_count"], GL_UNSIGNED_INT,
                ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
            )
        gl.glDisableClientState(GL_TEXTURE_COORD_ARRAY)
        gl.glDisableClientState(GL_NORMAL_ARRAY)
        gl.glDisableClientState(GL_VERTEX_ARRAY)
        gl.glBindTexture(GL_TEXTURE_2D, 0)
        gl.glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
        self._wgl.gdi.SwapBuffers(self._hdc)

    def close(self):
        if self._closing:
            return
        self._closing = True
        try:
            if self._make_current() and self._textures:
                texture_ids = (ctypes.c_uint * len(self._textures))(*self._textures.values())
                self._wgl.opengl.glDeleteTextures(len(self._textures), texture_ids)
            if self._wgl and self._hglrc:
                self._wgl.opengl.wglMakeCurrent(None, None)
                self._wgl.opengl.wglDeleteContext(self._hglrc)
            if self._wgl and self._hwnd and self._hdc:
                self._wgl.user.ReleaseDC(self._hwnd, self._hdc)
        except Exception:
            pass
        self.destroy()


def open_mesh_viewer(parent, parsed, entry, require_store=None):
    return MeshViewer(parent, parsed, entry, require_store=require_store)
