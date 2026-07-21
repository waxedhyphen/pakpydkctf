"""EXEFS-guided shell-fur rendering for the GPU mesh viewer.

The game executable exposes a dedicated Fur/FurFins material family with these
relevant uniforms and permutations:

- uc_furMap / uc_furLengthMap / uc_furFlowMap
- uc_furDensity / uc_furThickness / uc_furOcclusionStartLength
- uc_furFlowStrength / uc_furBendPower
- uc_rimFresnelMin / uc_rimFresnelMax / uc_rimBrightness
- FUR_FINS / INITIALIZE_FUR_DYNAMICS / APPLY_FUR_DYNAMICS

This patch implements the static shell portion. The original view-dependent fin
pass and runtime fur dynamics remain outside the viewer, but fur materials no
longer fall through the generic PBR interpretation.
"""
from __future__ import annotations

import ctypes
import math
import tkinter as tk
from tkinter import ttk

import mesh_viewer as mv
import mesh_viewer_material_shader_patch as material_patch


_INSTALLED = False
_PREVIOUS_LOAD_SCENE = None
GL_NEAREST = 0x2600

_FUR_SLOT_BY_TAG = {
    "FURTTXTR": "fur_mask",
    "FURLTXTR": "fur_length",
    "FURFTXTR": "fur_flow",
    "SPCFTXTR": "spec_curve",
}


FUR_VERTEX_SHADER_SOURCE = r"""
#version 120
attribute vec4 a_tangent;

uniform float u_shell_fraction;
uniform float u_fur_thickness;
uniform float u_fur_bend_power;

varying vec2 v_uv;
varying vec3 v_eye_pos;
varying vec3 v_tangent;
varying vec3 v_bitangent;
varying vec3 v_normal;
varying float v_shell_fraction;

void main() {
    vec3 object_normal = normalize(gl_Normal.xyz);
    float shell_curve = pow(clamp(u_shell_fraction, 0.0, 1.0), max(u_fur_bend_power, 0.05));
    vec4 displaced = gl_Vertex;
    displaced.xyz += object_normal * (u_fur_thickness * shell_curve);

    vec4 eye_pos = gl_ModelViewMatrix * displaced;
    vec3 normal = normalize(gl_NormalMatrix * gl_Normal);
    vec3 tangent = gl_NormalMatrix * a_tangent.xyz;
    if (dot(tangent, tangent) < 0.000001) {
        vec3 helper = abs(normal.z) < 0.999 ? vec3(0.0, 0.0, 1.0) : vec3(0.0, 1.0, 0.0);
        tangent = cross(helper, normal);
    }
    tangent = normalize(tangent - normal * dot(normal, tangent));
    float handedness = a_tangent.w < 0.0 ? -1.0 : 1.0;
    vec3 bitangent = normalize(cross(normal, tangent)) * handedness;

    v_uv = gl_MultiTexCoord0.xy;
    v_eye_pos = eye_pos.xyz;
    v_tangent = tangent;
    v_bitangent = bitangent;
    v_normal = normal;
    v_shell_fraction = u_shell_fraction;
    gl_Position = gl_ProjectionMatrix * eye_pos;
}
"""


FUR_FRAGMENT_SHADER_SOURCE = r"""
#version 120
uniform sampler2D u_base_map;
uniform sampler2D u_normal_map;
uniform sampler2D u_spec_map;
uniform sampler2D u_spec_curve_map;
uniform sampler2D u_fur_mask_map;
uniform sampler2D u_fur_length_map;
uniform sampler2D u_fur_flow_map;

uniform int u_has_normal;
uniform int u_has_spec;
uniform int u_has_spec_curve;

uniform vec3 u_base_color;
uniform vec3 u_spec_color;
uniform vec3 u_rim_color;
uniform float u_rim_strength;
uniform float u_rim_min;
uniform float u_rim_max;
uniform float u_fur_density;
uniform float u_fur_flow_strength;
uniform float u_fur_occlusion_start;
uniform float u_spec_power;
uniform float u_normal_y_sign;

varying vec2 v_uv;
varying vec3 v_eye_pos;
varying vec3 v_tangent;
varying vec3 v_bitangent;
varying vec3 v_normal;
varying float v_shell_fraction;

float hash12(vec2 value) {
    return fract(sin(dot(value, vec2(127.1, 311.7))) * 43758.5453123);
}

void main() {
    vec4 base_sample = texture2D(u_base_map, v_uv);
    vec3 flow_sample = texture2D(u_fur_flow_map, v_uv).rgb * 2.0 - 1.0;
    vec2 flow = flow_sample.xy;
    float flow_length = length(flow);
    if (flow_length > 0.0001) {
        flow /= flow_length;
    } else {
        flow = vec2(1.0, 0.0);
    }

    float density = max(u_fur_density, 1.0);
    vec2 mask_uv = v_uv * density;
    mask_uv += flow * (v_shell_fraction * u_fur_flow_strength * 0.018);
    float strand_mask = texture2D(u_fur_mask_map, mask_uv).r;
    if (strand_mask < 0.48) {
        discard;
    }

    float length_mask = texture2D(u_fur_length_map, v_uv).r;
    vec2 strand_cell = floor(fract(mask_uv) * 32.0);
    float strand_variation = mix(0.72, 1.0, hash12(strand_cell));
    float strand_length = clamp(length_mask * strand_variation, 0.0, 1.0);
    if (v_shell_fraction > strand_length) {
        discard;
    }

    vec3 normal = normalize(v_normal);
    if (u_has_normal != 0) {
        vec3 mapped = texture2D(u_normal_map, v_uv).xyz * 2.0 - 1.0;
        mapped.y *= u_normal_y_sign;
        mapped.z = max(mapped.z, 0.001);
        mat3 tbn = mat3(normalize(v_tangent), normalize(v_bitangent), normal);
        normal = normalize(tbn * normalize(mapped));
    }

    vec3 view_dir = normalize(-v_eye_pos);
    vec3 light_dir = normalize(vec3(0.35, 0.72, 0.58));
    vec3 half_dir = normalize(light_dir + view_dir);
    float n_dot_l = max(dot(normal, light_dir), 0.0);

    vec3 flow_tangent = normalize(v_tangent * flow.x + v_bitangent * flow.y + normal * 0.08);
    float t_dot_h = clamp(dot(flow_tangent, half_dir), -1.0, 1.0);
    float anisotropic_angle = sqrt(max(0.0, 1.0 - t_dot_h * t_dot_h));
    float spec_falloff = u_has_spec_curve != 0
        ? texture2D(u_spec_curve_map, vec2(anisotropic_angle, 0.5)).r
        : pow(anisotropic_angle, max(u_spec_power, 1.0));
    vec3 spec_sample = u_has_spec != 0 ? texture2D(u_spec_map, v_uv).rgb : vec3(1.0);

    float shell_position = v_shell_fraction / max(strand_length, 0.001);
    float root_light = smoothstep(clamp(u_fur_occlusion_start, 0.0, 0.98), 1.0, shell_position);
    float root_occlusion = mix(0.42, 1.0, root_light);

    vec3 albedo = base_sample.rgb * u_base_color;
    vec3 color = albedo * (0.18 + 0.82 * n_dot_l) * root_occlusion;
    color += spec_sample * u_spec_color * spec_falloff * n_dot_l;

    float fresnel = 1.0 - max(dot(normal, view_dir), 0.0);
    float rim = smoothstep(u_rim_min, max(u_rim_max, u_rim_min + 0.001), fresnel);
    color += u_rim_color * (rim * u_rim_strength);

    float tip_fade = 1.0 - smoothstep(0.86, 1.0, shell_position);
    float alpha = clamp(base_sample.a * mix(0.82, 0.58, v_shell_fraction) * max(tip_fade, 0.15), 0.0, 1.0);
    gl_FragColor = vec4(color, alpha);
}
"""


def _exact_color(colors, *tags, default):
    for tag in tags:
        value = colors.get(tag)
        if value is not None and len(value) >= 3:
            return tuple(float(component) for component in value[:3])
    return tuple(float(component) for component in default[:3])


def _scalar(scalars, tag, default):
    try:
        return float(scalars.get(tag, default))
    except Exception:
        return float(default)


def _safe_float(value, default=0.0):
    try:
        value = float(value)
        return value if math.isfinite(value) else float(default)
    except Exception:
        return float(default)


def _model_radius(model):
    positions = [
        position
        for vertex_set in model.get("vertex_sets", {}).values()
        for position in (vertex_set.get("positions") or [])
    ]
    if not positions:
        return 1.0
    mins = [min(float(position[axis]) for position in positions) for axis in range(3)]
    maxs = [max(float(position[axis]) for position in positions) for axis in range(3)]
    center = [(mins[axis] + maxs[axis]) * 0.5 for axis in range(3)]
    radius = max(
        math.sqrt(sum((float(position[axis]) - center[axis]) ** 2 for axis in range(3)))
        for position in positions
    )
    return radius if radius > 1.0e-8 else 1.0


def _decode_fur_maps(parsed, entry, require_store=None):
    maps = {}
    names = {}
    metadata = {}
    errors = []
    cache = {}

    if mv.PILImage is None or mv.decode_txtr_image is None or mv.parse_txtr_asset is None:
        return maps, names, metadata, ["Pillow/TXTR-Decoder nicht verfügbar"]

    for material in entry.get("model_materials", []):
        material_index = int(material.get("index", 0))
        material_maps = {}
        material_names = {}
        material_metadata = {}
        for reference in material.get("txtr_refs", []):
            tag = str(reference.get("tag", "")).upper()
            slot = _FUR_SLOT_BY_TAG.get(tag)
            if slot is None:
                continue
            uuid_hex = str(reference.get("uuid_hex", ""))
            if not uuid_hex:
                continue
            try:
                if uuid_hex not in cache:
                    asset, txtr_entry = mv._resolve_asset(parsed, uuid_hex, require_store)
                    if asset is None:
                        raise RuntimeError(f"TXTR {uuid_hex} nicht gefunden")
                    info = mv.parse_txtr_asset(asset)
                    image, _decode_info = mv.decode_txtr_image(info, "Auto")
                    cache[uuid_hex] = image.convert("RGBA")
                    cache[(uuid_hex, "name")] = (
                        txtr_entry.get("display_name")
                        or txtr_entry.get("name")
                        or uuid_hex
                    )
                image = cache[uuid_hex]
                material_maps[slot] = image
                material_names[slot] = cache[(uuid_hex, "name")]
                material_metadata[slot] = {
                    "tag": tag,
                    "uuid_hex": uuid_hex,
                    "size": tuple(image.size),
                    "extra_words": list(reference.get("extra_words") or []),
                }
            except Exception as exc:
                errors.append(f"Material {material_index} {tag}: {exc}")
        if material_maps:
            maps[material_index] = material_maps
            names[material_index] = material_names
            metadata[material_index] = material_metadata
    return maps, names, metadata, errors


def _fur_parameters(material, normalization_radius):
    scalars = dict(material.get("scalars") or {})
    colors = dict(material.get("colors") or {})
    layer_control = colors.get("LCNTCOLR") or (0.0, 0.0, 0.0, 0.0)
    shell_count = max(0, min(32, int(round(_safe_float(layer_control[0] if layer_control else 0.0)))))
    thickness_world = max(0.0, _scalar(scalars, "FRTHSCLR", 0.0))
    thickness_normalized = max(0.0, min(0.18, thickness_world / max(normalization_radius, 1.0e-8)))
    rim_brightness = colors.get("RBRTCOLR") or (0.75, 0.75, 0.75, 1.0)
    rim_strength = _safe_float(rim_brightness[3] if len(rim_brightness) > 3 else 1.0, 1.0)

    return {
        "enabled": shell_count > 0 and thickness_normalized > 0.0,
        "shell_count": shell_count,
        "layer_control": tuple(_safe_float(value) for value in layer_control),
        "density": max(1.0, min(64.0, _scalar(scalars, "FRDNSCLR", 12.0))),
        "thickness_world": thickness_world,
        "thickness": thickness_normalized,
        "occlusion_start": max(0.0, min(0.98, _scalar(scalars, "FROCSCLR", 0.6))),
        "flow_strength": max(0.0, min(8.0, _scalar(scalars, "FRFSSCLR", 1.0))),
        "bend_power": max(0.05, min(8.0, _scalar(scalars, "FRBPSCLR", 1.0))),
        "spec_power": max(1.0, min(256.0, _scalar(scalars, "SPCPSCLR", 16.0))),
        "rim_min": max(0.0, min(1.0, _scalar(scalars, "RFMNSCLR", 0.4))),
        "rim_max": max(0.0, min(1.0, _scalar(scalars, "RFMXSCLR", 0.9))),
        "rim_color": tuple(_safe_float(value, 0.75) for value in rim_brightness[:3]),
        "rim_strength": max(0.0, min(8.0, rim_strength)),
        "drag": _scalar(scalars, "DRAGSCLR", 0.0),
        "stiffness": _scalar(scalars, "SCOFSCLR", 0.0),
        "constraint_height": _scalar(scalars, "CONHSCLR", 0.0),
        "constraint_ellipse": _scalar(scalars, "CONESCLR", 1.0),
    }


def _load_scene_with_fur(parsed, entry, require_store=None):
    scene = _PREVIOUS_LOAD_SCENE(parsed, entry, require_store)
    model = material_patch.pak_extract.load_model_bytes(material_patch.get_entry_asset(parsed, entry))
    normalization_radius = _model_radius(model)
    scene["model_normalization_radius"] = normalization_radius

    fur_maps, fur_names, fur_metadata, fur_errors = _decode_fur_maps(parsed, entry, require_store)
    scene.setdefault("material_maps", {})
    scene.setdefault("material_map_names", {})
    scene.setdefault("material_map_metadata", {})
    for material_index, slots in fur_maps.items():
        scene["material_maps"].setdefault(material_index, {}).update(slots)
        scene["material_map_names"].setdefault(material_index, {}).update(fur_names.get(material_index, {}))
        scene["material_map_metadata"].setdefault(material_index, {}).update(fur_metadata.get(material_index, {}))

    scene.setdefault("material_map_errors", []).extend(fur_errors)
    source_materials = list(entry.get("model_materials", []))
    fur_parameters = {}
    scene.setdefault("material_params", {})

    for material in source_materials:
        material_index = int(material.get("index", 0))
        colors = dict(material.get("colors") or {})
        scalars = dict(material.get("scalars") or {})
        params = scene["material_params"].setdefault(material_index, {})

        # Do not use a broad "COLR" substring search: LCNTCOLR contains layer/LOD
        # controls, not an RGB tint. The game material has explicit color tags.
        params["base_color"] = _exact_color(
            colors, "DIFCCOLR", "BASECOLR", "ALBDCOLR", default=(1.0, 1.0, 1.0)
        )
        params["spec_color"] = _exact_color(
            colors, "SPCCOLR", default=(1.0, 1.0, 1.0)
        )
        params["emission_color"] = _exact_color(
            colors, "ICMCCOLR", "ICNCCOLR", "EMISCOLR", default=(0.0, 0.0, 0.0)
        )
        spec_power = max(1.0, _scalar(scalars, "SPCPSCLR", 16.0))
        params["spec_strength"] = 1.0
        params["roughness"] = max(0.03, min(1.0, math.sqrt(2.0 / (spec_power + 2.0))))

        tags = {str(reference.get("tag", "")).upper() for reference in material.get("txtr_refs", [])}
        if str(material.get("mat_type", "")).upper() == "FURM" or tags.intersection(_FUR_SLOT_BY_TAG):
            fur_parameters[material_index] = _fur_parameters(material, normalization_radius)

    scene["fur_materials"] = fur_parameters

    unsupported = scene.get("unsupported_material_maps") or {}
    supported_tags = set(_FUR_SLOT_BY_TAG)
    for material_index in list(unsupported):
        remaining = [
            item for item in unsupported[material_index]
            if str(item.get("tag", "")).upper() not in supported_tags
        ]
        if remaining:
            unsupported[material_index] = remaining
        else:
            unsupported.pop(material_index, None)
    return scene


def _compile_program(viewer, vertex_source, fragment_source):
    functions = viewer._glsl
    if not functions:
        raise RuntimeError("GLSL-Funktionen sind nicht verfügbar")

    def compile_shader(shader_type, source):
        shader = functions["glCreateShader"](shader_type)
        encoded = source.encode("utf-8")
        source_pointer = ctypes.c_char_p(encoded)
        length = ctypes.c_int(len(encoded))
        functions["glShaderSource"](shader, 1, ctypes.byref(source_pointer), ctypes.byref(length))
        functions["glCompileShader"](shader)
        status = ctypes.c_int()
        functions["glGetShaderiv"](shader, material_patch.GL_COMPILE_STATUS, ctypes.byref(status))
        if not status.value:
            raise RuntimeError("Fur-Shader-Compilefehler: " + material_patch._shader_log(functions, shader))
        return int(shader)

    vertex_shader = compile_shader(material_patch.GL_VERTEX_SHADER, vertex_source)
    fragment_shader = compile_shader(material_patch.GL_FRAGMENT_SHADER, fragment_source)
    program = int(functions["glCreateProgram"]())
    functions["glAttachShader"](program, vertex_shader)
    functions["glAttachShader"](program, fragment_shader)
    functions["glLinkProgram"](program)
    status = ctypes.c_int()
    functions["glGetProgramiv"](program, material_patch.GL_LINK_STATUS, ctypes.byref(status))
    if not status.value:
        raise RuntimeError("Fur-Shader-Linkfehler: " + material_patch._program_log(functions, program))
    return program, [vertex_shader, fragment_shader]


def install():
    global _INSTALLED, _PREVIOUS_LOAD_SCENE
    if _INSTALLED:
        return
    _INSTALLED = True
    if _PREVIOUS_LOAD_SCENE is None:
        _PREVIOUS_LOAD_SCENE = mv.load_entry_scene
    mv.load_entry_scene = _load_scene_with_fur
    BaseViewer = mv.MeshViewer

    class FurMeshViewer(BaseViewer):
        def __init__(self, parent, parsed, entry, require_store=None):
            self.fur_enabled = tk.BooleanVar(value=True)
            self._fur_program = 0
            self._fur_shader_objects = []
            self._fur_uniforms = {}
            self._fur_tangent_location = -1
            self._fur_shader_error = ""
            super().__init__(parent, parsed, entry, require_store=require_store)
            self._install_fur_toolbar()

        def _install_fur_toolbar(self):
            bar = ttk.Frame(self, padding=(8, 0, 8, 4))
            target = getattr(self, "_mesh_panel_paned", None)
            if target is not None:
                bar.pack(fill="x", before=target)
            else:
                bar.pack(fill="x")
            ttk.Label(bar, text="Fur (EXEFS)").pack(side="left")
            ttk.Checkbutton(
                bar,
                text="Shell-Fur",
                variable=self.fur_enabled,
                command=self.request_render,
            ).pack(side="left", padx=(8, 0))
            active = sum(1 for params in self.scene.get("fur_materials", {}).values() if params.get("enabled"))
            ttk.Label(bar, text=f"{active} aktive Fur-Materialien").pack(side="left", padx=(10, 0))
            self._fur_status = ttk.Label(bar, text="Fur-Shader wird initialisiert")
            self._fur_status.pack(side="right")

        def _setup_gl_state(self):
            super()._setup_gl_state()
            if not self._material_program or not self._glsl:
                self._fur_status.configure(text="Fur: GLSL-Fallback")
                return
            try:
                program, shaders = _compile_program(
                    self,
                    FUR_VERTEX_SHADER_SOURCE,
                    FUR_FRAGMENT_SHADER_SOURCE,
                )
                self._fur_program = program
                self._fur_shader_objects = shaders
                names = (
                    "u_base_map", "u_normal_map", "u_spec_map", "u_spec_curve_map",
                    "u_fur_mask_map", "u_fur_length_map", "u_fur_flow_map",
                    "u_has_normal", "u_has_spec", "u_has_spec_curve",
                    "u_base_color", "u_spec_color", "u_rim_color", "u_rim_strength",
                    "u_rim_min", "u_rim_max", "u_fur_density", "u_fur_flow_strength",
                    "u_fur_occlusion_start", "u_spec_power", "u_normal_y_sign",
                    "u_shell_fraction", "u_fur_thickness", "u_fur_bend_power",
                )
                self._fur_uniforms = {
                    name: self._glsl["glGetUniformLocation"](program, name.encode("ascii"))
                    for name in names
                }
                self._fur_tangent_location = self._glsl["glGetAttribLocation"](program, b"a_tangent")
                self._fur_status.configure(text="Fur: Shell-Pass aktiv")
            except Exception as exc:
                self._fur_shader_error = str(exc)
                self._fur_program = 0
                self._fur_status.configure(text="Fur: Shader-Fallback")

        def _upload_textures(self):
            super()._upload_textures()
            gl = self._wgl.opengl
            for material_index, slots in self._material_gl_textures.items():
                texture_id = slots.get("fur_mask")
                if not texture_id:
                    continue
                gl.glBindTexture(mv.GL_TEXTURE_2D, texture_id)
                gl.glTexParameteri(mv.GL_TEXTURE_2D, mv.GL_TEXTURE_MIN_FILTER, GL_NEAREST)
                gl.glTexParameteri(mv.GL_TEXTURE_2D, mv.GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            gl.glBindTexture(mv.GL_TEXTURE_2D, 0)

        def _fur_uniform_i(self, name, value):
            location = self._fur_uniforms.get(name, -1)
            if location >= 0:
                self._glsl["glUniform1i"](location, int(value))

        def _fur_uniform_f(self, name, value):
            location = self._fur_uniforms.get(name, -1)
            if location >= 0:
                self._glsl["glUniform1f"](location, float(value))

        def _fur_uniform_3(self, name, value):
            location = self._fur_uniforms.get(name, -1)
            if location >= 0:
                self._glsl["glUniform3f"](
                    location,
                    float(value[0]),
                    float(value[1]),
                    float(value[2]),
                )

        def _bind_base_material(self, mesh, selected_channel):
            gl = self._wgl.opengl
            vbuf = self._gpu_vbufs[mesh["vbuf_index"]]
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
            if self._tangent_location >= 0:
                self._glsl["glVertexAttribPointer"](
                    self._tangent_location,
                    4,
                    mv.GL_FLOAT,
                    material_patch.GL_FALSE,
                    0,
                    ctypes.cast(vbuf["tangents"], ctypes.c_void_p),
                )
            return vbuf

        def _render_material_shader(self):
            self._render_pending = False
            if self._closing or not self._make_current():
                return
            gl = self._wgl.opengl
            width = max(1, self.viewport.winfo_width())
            height = max(1, self.viewport.winfo_height())
            gl.glClear(mv.GL_COLOR_BUFFER_BIT | mv.GL_DEPTH_BUFFER_BIT)
            if hasattr(self, "_apply_camera"):
                self._apply_camera(width, height)
            else:
                gl.glViewport(0, 0, width, height)
            if self.show_grid.get():
                self._draw_grid()
            gl.glDisable(mv.GL_LIGHTING)
            if self.cull_faces.get():
                gl.glEnable(mv.GL_CULL_FACE)
                gl.glCullFace(mv.GL_BACK)
            else:
                gl.glDisable(mv.GL_CULL_FACE)
            gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_LINE if self.wireframe.get() else mv.GL_FILL)
            gl.glEnableClientState(mv.GL_VERTEX_ARRAY)
            gl.glEnableClientState(mv.GL_NORMAL_ARRAY)
            gl.glEnableClientState(mv.GL_TEXTURE_COORD_ARRAY)

            functions = self._glsl
            selected_channel = self._selected_uv_channel() if hasattr(self, "_selected_uv_channel") else 0
            meshes = self._visible_gpu_meshes() if hasattr(self, "_visible_gpu_meshes") else self._gpu_meshes

            # Standard opaque/base pass from the material renderer.
            functions["glUseProgram"](self._material_program)
            for unit, name in enumerate((
                "u_base_map", "u_normal_map", "u_spec_map", "u_rough_map",
                "u_emission_map", "u_metal_map", "u_ao_map",
            )):
                self._set_uniform_i(name, unit)
            if self._tangent_location >= 0:
                functions["glEnableVertexAttribArray"](self._tangent_location)

            bound_vbuf = None
            for mesh in meshes:
                vbuf_index = mesh["vbuf_index"]
                if vbuf_index != bound_vbuf:
                    self._bind_base_material(mesh, selected_channel)
                    bound_vbuf = vbuf_index

                material_index = int(mesh.get("material_index", 0))
                slots = self._material_gl_textures.get(material_index, {})
                base_texture = self._textures.get(material_index, self._default_gl_textures.get("white", 0))
                normal_texture = slots.get("normal", self._default_gl_textures.get("normal", 0))
                spec_texture = slots.get("spec_gloss", self._default_gl_textures.get("white", 0))
                rough_texture = slots.get("roughness", self._default_gl_textures.get("white", 0))
                emission_texture = slots.get("emission", self._default_gl_textures.get("black", 0))
                metal_texture = slots.get("metallic", self._default_gl_textures.get("black", 0))
                ao_texture = slots.get("occlusion", self._default_gl_textures.get("white", 0))
                for unit, texture_id in enumerate((
                    base_texture, normal_texture, spec_texture, rough_texture,
                    emission_texture, metal_texture, ao_texture,
                )):
                    self._bind_texture_unit(unit, texture_id)

                params = self.scene.get("material_params", {}).get(material_index, {})
                metadata = self.scene.get("material_map_metadata", {}).get(material_index, {})
                spec_meta = metadata.get("spec_gloss", {})
                self._set_uniform_i("u_has_base", material_index in self._textures)
                self._set_uniform_i("u_has_normal", self.normal_maps_enabled.get() and "normal" in slots)
                self._set_uniform_i("u_has_spec", self.specular_maps_enabled.get() and "spec_gloss" in slots)
                self._set_uniform_i("u_has_rough", self.specular_maps_enabled.get() and "roughness" in slots)
                self._set_uniform_i("u_has_emission", self.emission_maps_enabled.get() and "emission" in slots)
                self._set_uniform_i("u_has_metal", "metallic" in slots)
                self._set_uniform_i("u_has_ao", "occlusion" in slots)
                self._set_uniform_i("u_gloss_from_alpha", bool(spec_meta.get("alpha_varies")))
                self._set_uniform_3("u_base_color", params.get("base_color", (1.0, 1.0, 1.0)))
                self._set_uniform_3("u_spec_color", params.get("spec_color", (1.0, 1.0, 1.0)))
                self._set_uniform_3("u_emission_color", params.get("emission_color", (0.0, 0.0, 0.0)))
                self._set_uniform_f("u_normal_strength", params.get("normal_strength", 1.0))
                self._set_uniform_f("u_normal_y_sign", -1.0 if self.normal_y_mode.get().startswith("-Y") else 1.0)
                self._set_uniform_f("u_spec_strength", params.get("spec_strength", 1.0))
                self._set_uniform_f("u_roughness", params.get("roughness", 0.55))
                self._set_uniform_f("u_metallic", params.get("metallic", 0.0))
                self._set_uniform_f(
                    "u_emission_strength",
                    params.get("emission_strength", 1.0) if self.emission_maps_enabled.get() else 0.0,
                )
                gl.glDrawElements(
                    mv.GL_TRIANGLES,
                    mesh["index_count"],
                    mv.GL_UNSIGNED_INT,
                    ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
                )

            if self._tangent_location >= 0:
                functions["glDisableVertexAttribArray"](self._tangent_location)
            functions["glUseProgram"](0)

            # EXEFS-guided shell pass. LCNTCOLR.x is the layer count; the
            # "NO_fur" base material has zero and is deliberately skipped.
            if self.fur_enabled.get() and self._fur_program:
                functions["glUseProgram"](self._fur_program)
                fur_sampler_names = (
                    "u_base_map", "u_normal_map", "u_spec_map", "u_spec_curve_map",
                    "u_fur_mask_map", "u_fur_length_map", "u_fur_flow_map",
                )
                for unit, name in enumerate(fur_sampler_names):
                    self._fur_uniform_i(name, unit)
                if self._fur_tangent_location >= 0:
                    functions["glEnableVertexAttribArray"](self._fur_tangent_location)

                for mesh in meshes:
                    material_index = int(mesh.get("material_index", 0))
                    fur_params = self.scene.get("fur_materials", {}).get(material_index)
                    if not fur_params or not fur_params.get("enabled"):
                        continue
                    slots = self._material_gl_textures.get(material_index, {})
                    required = ("fur_mask", "fur_length", "fur_flow")
                    if any(slot not in slots for slot in required):
                        continue

                    vbuf = self._gpu_vbufs[mesh["vbuf_index"]]
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
                    if self._fur_tangent_location >= 0:
                        functions["glVertexAttribPointer"](
                            self._fur_tangent_location,
                            4,
                            mv.GL_FLOAT,
                            material_patch.GL_FALSE,
                            0,
                            ctypes.cast(vbuf["tangents"], ctypes.c_void_p),
                        )

                    base_texture = self._textures.get(material_index, self._default_gl_textures.get("white", 0))
                    normal_texture = slots.get("normal", self._default_gl_textures.get("normal", 0))
                    spec_texture = slots.get("spec_gloss", self._default_gl_textures.get("white", 0))
                    spec_curve_texture = slots.get("spec_curve", self._default_gl_textures.get("white", 0))
                    for unit, texture_id in enumerate((
                        base_texture,
                        normal_texture,
                        spec_texture,
                        spec_curve_texture,
                        slots["fur_mask"],
                        slots["fur_length"],
                        slots["fur_flow"],
                    )):
                        self._bind_texture_unit(unit, texture_id)

                    material_params = self.scene.get("material_params", {}).get(material_index, {})
                    self._fur_uniform_i("u_has_normal", self.normal_maps_enabled.get() and "normal" in slots)
                    self._fur_uniform_i("u_has_spec", self.specular_maps_enabled.get() and "spec_gloss" in slots)
                    self._fur_uniform_i("u_has_spec_curve", self.specular_maps_enabled.get() and "spec_curve" in slots)
                    self._fur_uniform_3("u_base_color", material_params.get("base_color", (1.0, 1.0, 1.0)))
                    self._fur_uniform_3("u_spec_color", material_params.get("spec_color", (1.0, 1.0, 1.0)))
                    self._fur_uniform_3("u_rim_color", fur_params.get("rim_color", (0.75, 0.75, 0.75)))
                    self._fur_uniform_f("u_rim_strength", fur_params.get("rim_strength", 1.0))
                    self._fur_uniform_f("u_rim_min", fur_params.get("rim_min", 0.4))
                    self._fur_uniform_f("u_rim_max", fur_params.get("rim_max", 0.9))
                    self._fur_uniform_f("u_fur_density", fur_params.get("density", 12.0))
                    self._fur_uniform_f("u_fur_flow_strength", fur_params.get("flow_strength", 1.0))
                    self._fur_uniform_f("u_fur_occlusion_start", fur_params.get("occlusion_start", 0.6))
                    self._fur_uniform_f("u_spec_power", fur_params.get("spec_power", 16.0))
                    self._fur_uniform_f("u_normal_y_sign", -1.0 if self.normal_y_mode.get().startswith("-Y") else 1.0)
                    self._fur_uniform_f("u_fur_thickness", fur_params.get("thickness", 0.0))
                    self._fur_uniform_f("u_fur_bend_power", fur_params.get("bend_power", 1.0))

                    shell_count = int(fur_params.get("shell_count", 0))
                    for shell_index in range(1, shell_count + 1):
                        shell_fraction = shell_index / float(shell_count)
                        self._fur_uniform_f("u_shell_fraction", shell_fraction)
                        gl.glDrawElements(
                            mv.GL_TRIANGLES,
                            mesh["index_count"],
                            mv.GL_UNSIGNED_INT,
                            ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
                        )

                if self._fur_tangent_location >= 0:
                    functions["glDisableVertexAttribArray"](self._fur_tangent_location)
                functions["glUseProgram"](0)

            functions["glActiveTexture"](material_patch.GL_TEXTURE0)
            gl.glBindTexture(mv.GL_TEXTURE_2D, 0)
            if hasattr(self, "_draw_selected_mesh_overlay"):
                selected = getattr(self, "selected_mesh_index", None)
                if selected is None or not hasattr(self, "_is_mesh_visible") or self._is_mesh_visible(selected):
                    self._draw_selected_mesh_overlay()
            gl.glDisableClientState(mv.GL_TEXTURE_COORD_ARRAY)
            gl.glDisableClientState(mv.GL_NORMAL_ARRAY)
            gl.glDisableClientState(mv.GL_VERTEX_ARRAY)
            gl.glPolygonMode(mv.GL_FRONT_AND_BACK, mv.GL_FILL)
            self._wgl.gdi.SwapBuffers(self._hdc)

        def show_material_info(self):
            super().show_material_info()

        def close(self):
            try:
                if self._make_current() and self._glsl and self._fur_program:
                    self._glsl["glUseProgram"](0)
                    self._glsl["glDeleteProgram"](self._fur_program)
                    for shader in self._fur_shader_objects:
                        self._glsl["glDeleteShader"](shader)
            except Exception:
                pass
            self._fur_program = 0
            self._fur_shader_objects = []
            return super().close()

    FurMeshViewer.__name__ = "FurMeshViewer"
    mv.MeshViewer = FurMeshViewer
