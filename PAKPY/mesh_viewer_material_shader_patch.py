"""GLSL material rendering for the WGL mesh viewer.

Adds tangent-space normal maps, specular/gloss roughness, emission and material
property diagnostics. The existing fixed-function renderer remains available as
an automatic fallback when the driver does not expose GLSL 1.20 entry points.
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


_INSTALLED = False
_UV_SEMANTICS = {4, 5, 6, 7, 8, 9, 10, 11}
_NORMAL_SEMANTICS = {1}
_TANGENT_SEMANTICS = {2, 3, 12, 13}

GL_VERTEX_SHADER = 0x8B31
GL_FRAGMENT_SHADER = 0x8B30
GL_COMPILE_STATUS = 0x8B81
GL_LINK_STATUS = 0x8B82
GL_INFO_LOG_LENGTH = 0x8B84
GL_TEXTURE0 = 0x84C0
GL_FALSE = 0

_BASE_TAGS = {
    "DIFFTXTR", "DIFTTXTR", "COLRTXTR", "ALBDTXTR",
    "BASETXTR", "BASEXTR", "ALBRTXTR",
}
_NORMAL_TAG_PARTS = ("NMAP", "NRML", "NORM")
_EMISSION_TAG_PARTS = ("EMIS", "ICAN")


VERTEX_SHADER_SOURCE = r"""
#version 120
attribute vec4 a_tangent;
varying vec2 v_uv;
varying vec3 v_eye_pos;
varying vec3 v_tangent;
varying vec3 v_bitangent;
varying vec3 v_normal;

void main() {
    vec4 eye_pos = gl_ModelViewMatrix * gl_Vertex;
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
    gl_Position = gl_ProjectionMatrix * eye_pos;
}
"""


FRAGMENT_SHADER_SOURCE = r"""
#version 120
uniform sampler2D u_base_map;
uniform sampler2D u_normal_map;
uniform sampler2D u_spec_map;
uniform sampler2D u_rough_map;
uniform sampler2D u_emission_map;
uniform sampler2D u_metal_map;
uniform sampler2D u_ao_map;

uniform int u_has_base;
uniform int u_has_normal;
uniform int u_has_spec;
uniform int u_has_rough;
uniform int u_has_emission;
uniform int u_has_metal;
uniform int u_has_ao;
uniform int u_gloss_from_alpha;

uniform vec3 u_base_color;
uniform vec3 u_spec_color;
uniform vec3 u_emission_color;
uniform float u_normal_strength;
uniform float u_normal_y_sign;
uniform float u_spec_strength;
uniform float u_roughness;
uniform float u_metallic;
uniform float u_emission_strength;

varying vec2 v_uv;
varying vec3 v_eye_pos;
varying vec3 v_tangent;
varying vec3 v_bitangent;
varying vec3 v_normal;

void main() {
    vec4 base_sample = u_has_base != 0 ? texture2D(u_base_map, v_uv) : vec4(1.0);
    vec3 albedo = base_sample.rgb * u_base_color;

    vec3 normal = normalize(v_normal);
    if (u_has_normal != 0) {
        vec3 mapped = texture2D(u_normal_map, v_uv).xyz * 2.0 - 1.0;
        mapped.xy *= u_normal_strength;
        mapped.y *= u_normal_y_sign;
        mapped.z = max(mapped.z, 0.001);
        mat3 tbn = mat3(normalize(v_tangent), normalize(v_bitangent), normal);
        normal = normalize(tbn * normalize(mapped));
    }

    vec3 view_dir = normalize(-v_eye_pos);
    vec3 light_dir = normalize(vec3(0.35, 0.72, 0.58));
    vec3 half_dir = normalize(light_dir + view_dir);
    float n_dot_l = max(dot(normal, light_dir), 0.0);
    float n_dot_h = max(dot(normal, half_dir), 0.0);

    vec4 spec_sample = u_has_spec != 0 ? texture2D(u_spec_map, v_uv) : vec4(1.0);
    float spec_luma = dot(spec_sample.rgb, vec3(0.2126, 0.7152, 0.0722));
    float gloss = u_gloss_from_alpha != 0 ? spec_sample.a : spec_luma;
    float roughness = clamp(u_roughness, 0.03, 1.0);
    if (u_has_rough != 0) {
        vec4 rough_sample = texture2D(u_rough_map, v_uv);
        roughness = clamp(dot(rough_sample.rgb, vec3(0.2126, 0.7152, 0.0722)), 0.03, 1.0);
    } else if (u_has_spec != 0) {
        roughness = clamp(1.0 - gloss, 0.03, 1.0);
    }

    float shininess = mix(256.0, 2.0, roughness * roughness);
    float specular_term = pow(n_dot_h, shininess) * n_dot_l * u_spec_strength;
    float metallic = clamp(u_metallic, 0.0, 1.0);
    if (u_has_metal != 0) {
        vec3 metal_sample = texture2D(u_metal_map, v_uv).rgb;
        metallic = clamp(dot(metal_sample, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
    }
    float ao = 1.0;
    if (u_has_ao != 0) {
        vec3 ao_sample = texture2D(u_ao_map, v_uv).rgb;
        ao = clamp(dot(ao_sample, vec3(0.2126, 0.7152, 0.0722)), 0.0, 1.0);
    }
    vec3 dielectric_spec = spec_sample.rgb * u_spec_color;
    vec3 specular_color = mix(dielectric_spec, albedo, metallic);
    vec3 diffuse_color = albedo * (1.0 - metallic);

    vec3 color = diffuse_color * (0.20 * ao + 0.80 * n_dot_l * ao);
    color += specular_color * specular_term;

    if (u_has_emission != 0) {
        color += texture2D(u_emission_map, v_uv).rgb * u_emission_color * u_emission_strength;
    } else {
        color += u_emission_color * u_emission_strength;
    }

    gl_FragColor = vec4(color, base_sample.a);
}
"""


def _normalise3(value, fallback=(0.0, 0.0, 1.0)):
    x, y, z = (float(value[0]), float(value[1]), float(value[2]))
    length = math.sqrt(x * x + y * y + z * z)
    if length <= 1e-12:
        return fallback
    return (x / length, y / length, z / length)


def _add3(target, index, value):
    target[index][0] += value[0]
    target[index][1] += value[1]
    target[index][2] += value[2]


def _parse_vertices_with_material_channels(vertex_buffer, raw_vertex_data):
    stride = int(vertex_buffer.get("stride", 0))
    reported_vertex_count = int(vertex_buffer.get("vertex_count", 0))
    if stride <= 0:
        raise PakError("Vertex-Stride ist ungültig")
    actual_vertex_count = min(reported_vertex_count, len(raw_vertex_data) // stride)
    if actual_vertex_count <= 0:
        raise PakError("Keine lesbaren Vertexdaten gefunden")

    components = list(vertex_buffer.get("components") or [])
    uv_component_indices = [
        i for i, component in enumerate(components)
        if int(component.get("format", -1)) in (20, 21)
        and int(component.get("type", -1)) in _UV_SEMANTICS
    ]
    uv_lookup = {component_index: channel for channel, component_index in enumerate(uv_component_indices)}

    positions = []
    normals = []
    tangents = []
    uv_channels = [[] for _ in uv_component_indices]

    for vertex_index in range(actual_vertex_count):
        base = vertex_index * stride
        position = (0.0, 0.0, 0.0)
        normal = None
        tangent = None
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
                elif semantic in _TANGENT_SEMANTICS and tangent is None:
                    tangent = value
            elif component_index in uv_lookup and entry + 4 <= len(raw_vertex_data):
                channel = uv_lookup[component_index]
                vertex_uvs[channel] = (
                    pak_extract.read_half(raw_vertex_data, entry + 0),
                    pak_extract.read_half(raw_vertex_data, entry + 2),
                )

        positions.append(position)
        normals.append(normal)
        tangents.append(tangent)
        for channel, value in enumerate(vertex_uvs):
            uv_channels[channel].append(value if value is not None else (0.0, 0.0))

    descriptors = []
    for component_index in uv_component_indices:
        component = components[component_index]
        descriptors.append({
            "component_index": component_index,
            "semantic": int(component.get("type", -1)),
            "format": int(component.get("format", -1)),
            "offset": int(component.get("offset", 0)),
            "stride": int(component.get("stride", stride)),
        })

    return {
        "positions": positions,
        "normals": normals,
        "tangents": tangents,
        "uvs": list(uv_channels[0]) if uv_channels else [None] * actual_vertex_count,
        "uv_channels": uv_channels,
        "uv_channel_descriptors": descriptors,
        "reported_vertex_count": reported_vertex_count,
        "actual_vertex_count": actual_vertex_count,
        "truncated": actual_vertex_count < reported_vertex_count,
    }


def _complete_normals_and_tangents(model):
    for vbuf_index, vertex_set in model.get("vertex_sets", {}).items():
        positions = list(vertex_set.get("positions") or [])
        count = len(positions)
        if not count:
            continue
        uv_channels = list(vertex_set.get("uv_channels") or [])
        uvs = list(uv_channels[0]) if uv_channels else list(vertex_set.get("uvs") or [])
        while len(uvs) < count:
            uvs.append((0.0, 0.0))
        source_normals = list(vertex_set.get("normals") or [])
        source_tangents = list(vertex_set.get("tangents") or [])
        while len(source_normals) < count:
            source_normals.append(None)
        while len(source_tangents) < count:
            source_tangents.append(None)

        normal_acc = [[0.0, 0.0, 0.0] for _ in range(count)]
        tangent_acc = [[0.0, 0.0, 0.0] for _ in range(count)]
        bitangent_acc = [[0.0, 0.0, 0.0] for _ in range(count)]

        for mesh in model.get("meshes", []):
            if int(mesh.get("vertex_buffer_index", -1)) != int(vbuf_index):
                continue
            ibuf_index = mesh.get("index_buffer_index")
            if ibuf_index not in model.get("index_sets", {}):
                continue
            start = int(mesh.get("index_buffer_offset", 0))
            end = start + int(mesh.get("index_count", 0))
            faces = pak_extract.build_faces(
                int(mesh.get("primitive_mode", 3)),
                model["index_sets"][ibuf_index][start:end],
                vertex_limit=count,
            )
            for a, b, c in faces:
                p0, p1, p2 = positions[a], positions[b], positions[c]
                e1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
                e2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
                face_normal = (
                    e1[1] * e2[2] - e1[2] * e2[1],
                    e1[2] * e2[0] - e1[0] * e2[2],
                    e1[0] * e2[1] - e1[1] * e2[0],
                )
                for index in (a, b, c):
                    _add3(normal_acc, index, face_normal)

                uv0, uv1, uv2 = uvs[a], uvs[b], uvs[c]
                du1, dv1 = uv1[0] - uv0[0], uv1[1] - uv0[1]
                du2, dv2 = uv2[0] - uv0[0], uv2[1] - uv0[1]
                determinant = du1 * dv2 - du2 * dv1
                if abs(determinant) <= 1e-12:
                    continue
                inv = 1.0 / determinant
                tangent = (
                    (e1[0] * dv2 - e2[0] * dv1) * inv,
                    (e1[1] * dv2 - e2[1] * dv1) * inv,
                    (e1[2] * dv2 - e2[2] * dv1) * inv,
                )
                bitangent = (
                    (e2[0] * du1 - e1[0] * du2) * inv,
                    (e2[1] * du1 - e1[1] * du2) * inv,
                    (e2[2] * du1 - e1[2] * du2) * inv,
                )
                for index in (a, b, c):
                    _add3(tangent_acc, index, tangent)
                    _add3(bitangent_acc, index, bitangent)

        normals = []
        tangents = []
        for index in range(count):
            normal = source_normals[index]
            normal = _normalise3(normal if normal is not None else normal_acc[index])
            tangent_source = source_tangents[index]
            if tangent_source is not None:
                tangent_xyz = tangent_source[:3]
                handedness = -1.0 if len(tangent_source) > 3 and float(tangent_source[3]) < 0.0 else 1.0
            else:
                tangent_xyz = tangent_acc[index]
                handedness = 1.0
            tangent_xyz = (
                tangent_xyz[0] - normal[0] * (normal[0] * tangent_xyz[0] + normal[1] * tangent_xyz[1] + normal[2] * tangent_xyz[2]),
                tangent_xyz[1] - normal[1] * (normal[0] * tangent_xyz[0] + normal[1] * tangent_xyz[1] + normal[2] * tangent_xyz[2]),
                tangent_xyz[2] - normal[2] * (normal[0] * tangent_xyz[0] + normal[1] * tangent_xyz[1] + normal[2] * tangent_xyz[2]),
            )
            tangent_xyz = _normalise3(tangent_xyz, fallback=(1.0, 0.0, 0.0))
            if tangent_source is None:
                cross_nt = (
                    normal[1] * tangent_xyz[2] - normal[2] * tangent_xyz[1],
                    normal[2] * tangent_xyz[0] - normal[0] * tangent_xyz[2],
                    normal[0] * tangent_xyz[1] - normal[1] * tangent_xyz[0],
                )
                if sum(cross_nt[i] * bitangent_acc[index][i] for i in range(3)) < 0.0:
                    handedness = -1.0
            normals.append(normal)
            tangents.append((tangent_xyz[0], tangent_xyz[1], tangent_xyz[2], handedness))

        vertex_set["normals"] = normals
        vertex_set["tangents"] = tangents


def _classify_texture_tag(tag):
    upper = str(tag or "").upper()
    if upper in _BASE_TAGS:
        return "base"
    if any(part in upper for part in _NORMAL_TAG_PARTS):
        return "normal"
    if any(part in upper for part in _EMISSION_TAG_PARTS):
        return "emission"
    if "ROUGH" in upper or "RUGH" in upper:
        return "roughness"
    if "METAL" in upper or "METL" in upper:
        return "metallic"
    if "OCCL" in upper or upper.startswith("AO"):
        return "occlusion"
    if "SPCF" in upper:
        return "spec_curve"
    if "SPCT" in upper or "SPEC" in upper or upper.startswith("SPC"):
        return "spec_gloss"
    if upper.startswith("FUR"):
        return "fur"
    return "other"


def _find_prop(properties, needles, default):
    for tag, value in properties.items():
        upper = str(tag).upper()
        if any(needle in upper for needle in needles):
            return value
    return default


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, float(value)))


def _material_parameters(material):
    scalars = dict(material.get("scalars") or {})
    colors = dict(material.get("colors") or {})
    roughness = _find_prop(scalars, ("ROUGH", "RUGH"), None)
    gloss = _find_prop(scalars, ("GLOS", "SHIN"), None)
    if roughness is None and gloss is not None:
        roughness = 1.0 - float(gloss)
    if roughness is None:
        roughness = 0.55
    return {
        "base_color": tuple(float(x) for x in _find_prop(colors, ("DIFF", "BASE", "ALBD", "COLR"), (1.0, 1.0, 1.0, 1.0))[:3]),
        "spec_color": tuple(float(x) for x in _find_prop(colors, ("SPEC", "SPC"), (1.0, 1.0, 1.0, 1.0))[:3]),
        "emission_color": tuple(float(x) for x in _find_prop(colors, ("EMIS", "ICAN"), (0.0, 0.0, 0.0, 1.0))[:3]),
        "normal_strength": _clamp(_find_prop(scalars, ("NORM", "NMAP"), 1.0), 0.0, 4.0),
        "spec_strength": _clamp(_find_prop(scalars, ("SPEC", "SPC"), 1.0), 0.0, 8.0),
        "roughness": _clamp(roughness, 0.03, 1.0),
        "metallic": _clamp(_find_prop(scalars, ("METAL", "METL"), 0.0)),
        "emission_strength": _clamp(_find_prop(scalars, ("EMIS", "ICAN"), 1.0), 0.0, 16.0),
        "scalar_tags": scalars,
        "color_tags": colors,
        "mat_type": material.get("mat_type", ""),
        "variant": material.get("variant", 0),
    }


def _decode_material_maps(parsed, entry, require_store=None):
    maps = {}
    names = {}
    metadata = {}
    errors = []
    unsupported = {}
    cache = {}
    if mv.PILImage is None or mv.decode_txtr_image is None or mv.parse_txtr_asset is None:
        return maps, names, metadata, unsupported, ["Pillow/TXTR-Decoder nicht verfügbar"]

    for material in entry.get("model_materials", []):
        material_index = int(material.get("index", 0))
        material_maps = {}
        material_names = {}
        material_meta = {}
        material_unsupported = []
        for ref in material.get("txtr_refs", []):
            slot = _classify_texture_tag(ref.get("tag"))
            if slot == "base":
                continue
            uuid_hex = str(ref.get("uuid_hex", ""))
            if not uuid_hex:
                continue
            if slot in ("fur", "spec_curve", "other"):
                material_unsupported.append({"slot": slot, "tag": ref.get("tag"), "uuid_hex": uuid_hex})
                continue
            if slot in material_maps:
                material_unsupported.append({"slot": slot, "tag": ref.get("tag"), "uuid_hex": uuid_hex, "reason": "zusätzlicher Slot"})
                continue
            try:
                if uuid_hex not in cache:
                    asset, txtr_entry = mv._resolve_asset(parsed, uuid_hex, require_store)
                    if asset is None:
                        raise PakError(f"TXTR {uuid_hex} nicht gefunden")
                    info = mv.parse_txtr_asset(asset)
                    image, _decode_info = mv.decode_txtr_image(info, "Auto")
                    image = image.convert("RGBA")
                    cache[uuid_hex] = image
                    cache[(uuid_hex, "name")] = (
                        txtr_entry.get("display_name") or txtr_entry.get("name") or uuid_hex
                    )
                image = cache[uuid_hex]
                material_maps[slot] = image
                material_names[slot] = cache[(uuid_hex, "name")]
                extrema = image.getextrema()
                alpha_range = int(extrema[3][1]) - int(extrema[3][0])
                material_meta[slot] = {
                    "tag": str(ref.get("tag", "")),
                    "uuid_hex": uuid_hex,
                    "size": tuple(image.size),
                    "alpha_varies": alpha_range > 4 and extrema[3] != (255, 255),
                    "extra_words": list(ref.get("extra_words") or []),
                }
            except Exception as exc:
                errors.append(f"Material {material_index} {ref.get('tag')}: {exc}")
        if material_maps:
            maps[material_index] = material_maps
            names[material_index] = material_names
            metadata[material_index] = material_meta
        if material_unsupported:
            unsupported[material_index] = material_unsupported
    return maps, names, metadata, unsupported, errors


def _flatten_tangents(values, vertex_count):
    output = []
    for index in range(vertex_count):
        tangent = values[index] if index < len(values) else None
        if tangent is None or len(tangent) < 3:
            output.extend((1.0, 0.0, 0.0, 1.0))
        else:
            output.extend((
                float(tangent[0]), float(tangent[1]), float(tangent[2]),
                float(tangent[3]) if len(tangent) > 3 and float(tangent[3]) != 0.0 else 1.0,
            ))
    return output


def _load_scene_with_materials(parsed, entry, require_store=None):
    scene = _PREVIOUS_LOAD_SCENE(parsed, entry, require_store)
    model = pak_extract.load_model_bytes(get_entry_asset(parsed, entry))
    _complete_normals_and_tangents(model)
    for vbuf_index, source in model.get("vertex_sets", {}).items():
        target = scene.get("vertex_buffers", {}).get(vbuf_index)
        if target is None:
            continue
        target["normals"] = [component for normal in source.get("normals", []) for component in normal[:3]]
        target["tangents"] = _flatten_tangents(source.get("tangents") or [], int(target.get("vertex_count", 0)))

    material_maps, map_names, map_meta, unsupported, errors = _decode_material_maps(parsed, entry, require_store)
    scene["material_maps"] = material_maps
    scene["material_map_names"] = map_names
    scene["material_map_metadata"] = map_meta
    scene["unsupported_material_maps"] = unsupported
    scene["material_map_errors"] = errors
    scene["material_params"] = {
        int(material.get("index", 0)): _material_parameters(material)
        for material in entry.get("model_materials", [])
    }
    scene["material_source"] = list(entry.get("model_materials", []))
    return scene


def _decode_gl_string(value):
    if not value:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _load_gl_proc(wgl, name, restype, argtypes):
    address = wgl.opengl.wglGetProcAddress(name.encode("ascii"))
    invalid = {None, 0, 1, 2, 3, -1, ctypes.c_void_p(-1).value}
    if address in invalid:
        return None
    prototype = ctypes.WINFUNCTYPE(restype, *argtypes)
    return prototype(address)


def _shader_log(functions, shader):
    length = ctypes.c_int()
    functions["glGetShaderiv"](shader, GL_INFO_LOG_LENGTH, ctypes.byref(length))
    if length.value <= 1:
        return ""
    buffer = ctypes.create_string_buffer(length.value)
    written = ctypes.c_int()
    functions["glGetShaderInfoLog"](shader, length.value, ctypes.byref(written), buffer)
    return _decode_gl_string(buffer.value)


def _program_log(functions, program):
    length = ctypes.c_int()
    functions["glGetProgramiv"](program, GL_INFO_LOG_LENGTH, ctypes.byref(length))
    if length.value <= 1:
        return ""
    buffer = ctypes.create_string_buffer(length.value)
    written = ctypes.c_int()
    functions["glGetProgramInfoLog"](program, length.value, ctypes.byref(written), buffer)
    return _decode_gl_string(buffer.value)


_PREVIOUS_LOAD_SCENE = mv.load_entry_scene


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    pak_extract.parse_vertices = _parse_vertices_with_material_channels
    mv.load_entry_scene = _load_scene_with_materials
    BaseViewer = mv.MeshViewer

    class MaterialMeshViewer(BaseViewer):
        def __init__(self, parent, parsed, entry, require_store=None):
            self.material_shader_enabled = tk.BooleanVar(value=True)
            self.normal_maps_enabled = tk.BooleanVar(value=True)
            self.specular_maps_enabled = tk.BooleanVar(value=True)
            self.emission_maps_enabled = tk.BooleanVar(value=True)
            self.normal_y_mode = tk.StringVar(value="-Y (DirectX)")
            self._glsl = {}
            self._material_program = 0
            self._shader_objects = []
            self._shader_uniforms = {}
            self._tangent_location = -1
            self._material_gl_textures = {}
            self._default_gl_textures = {}
            self._material_shader_error = ""
            super().__init__(parent, parsed, entry, require_store=require_store)
            self._install_material_toolbar()

        def _install_material_toolbar(self):
            bar = ttk.Frame(self, padding=(8, 0, 8, 4))
            target = getattr(self, "_mesh_panel_paned", None)
            if target is not None:
                bar.pack(fill="x", before=target)
            else:
                bar.pack(fill="x")
            ttk.Label(bar, text="Material").pack(side="left")
            for text, variable in (
                ("Shader", self.material_shader_enabled),
                ("Normalmap", self.normal_maps_enabled),
                ("Spec/Gloss", self.specular_maps_enabled),
                ("Emission", self.emission_maps_enabled),
            ):
                ttk.Checkbutton(bar, text=text, variable=variable, command=self.request_render).pack(side="left", padx=(8, 0))
            ttk.Label(bar, text="Normal Y").pack(side="left", padx=(12, 3))
            normal_y = ttk.Combobox(
                bar,
                textvariable=self.normal_y_mode,
                values=("-Y (DirectX)", "+Y (OpenGL)"),
                state="readonly",
                width=13,
            )
            normal_y.pack(side="left")
            normal_y.bind("<<ComboboxSelected>>", lambda _event: self.request_render())
            ttk.Button(bar, text="Material-Info", command=self.show_material_info).pack(side="left", padx=(8, 0))
            self._material_status = ttk.Label(bar, text="GLSL wird initialisiert")
            self._material_status.pack(side="right")

        def _setup_gl_state(self):
            super()._setup_gl_state()
            try:
                self._initialise_material_shader()
                self._material_status.configure(text="GLSL Materialshader")
            except Exception as exc:
                self._material_shader_error = str(exc)
                self._material_program = 0
                self._material_status.configure(text="Fixed-Function-Fallback")

        def _initialise_material_shader(self):
            gl = self._wgl.opengl
            gl.wglGetProcAddress.argtypes = [ctypes.c_char_p]
            gl.wglGetProcAddress.restype = ctypes.c_void_p
            c_uint = ctypes.c_uint
            c_int = ctypes.c_int
            c_float = ctypes.c_float
            c_char_p = ctypes.c_char_p
            c_void_p = ctypes.c_void_p
            specs = {
                "glCreateShader": (c_uint, [c_uint]),
                "glShaderSource": (None, [c_uint, c_int, ctypes.POINTER(c_char_p), ctypes.POINTER(c_int)]),
                "glCompileShader": (None, [c_uint]),
                "glGetShaderiv": (None, [c_uint, c_uint, ctypes.POINTER(c_int)]),
                "glGetShaderInfoLog": (None, [c_uint, c_int, ctypes.POINTER(c_int), c_char_p]),
                "glDeleteShader": (None, [c_uint]),
                "glCreateProgram": (c_uint, []),
                "glAttachShader": (None, [c_uint, c_uint]),
                "glLinkProgram": (None, [c_uint]),
                "glGetProgramiv": (None, [c_uint, c_uint, ctypes.POINTER(c_int)]),
                "glGetProgramInfoLog": (None, [c_uint, c_int, ctypes.POINTER(c_int), c_char_p]),
                "glUseProgram": (None, [c_uint]),
                "glDeleteProgram": (None, [c_uint]),
                "glGetUniformLocation": (c_int, [c_uint, c_char_p]),
                "glUniform1i": (None, [c_int, c_int]),
                "glUniform1f": (None, [c_int, c_float]),
                "glUniform3f": (None, [c_int, c_float, c_float, c_float]),
                "glGetAttribLocation": (c_int, [c_uint, c_char_p]),
                "glEnableVertexAttribArray": (None, [c_uint]),
                "glDisableVertexAttribArray": (None, [c_uint]),
                "glVertexAttribPointer": (None, [c_uint, c_int, c_uint, ctypes.c_ubyte, c_int, c_void_p]),
                "glActiveTexture": (None, [c_uint]),
            }
            functions = {}
            missing = []
            for name, (restype, argtypes) in specs.items():
                function = _load_gl_proc(self._wgl, name, restype, argtypes)
                if function is None:
                    missing.append(name)
                else:
                    functions[name] = function
            if missing:
                raise PakError("GLSL-Funktionen fehlen: " + ", ".join(missing))
            self._glsl = functions

            def compile_shader(shader_type, source):
                shader = functions["glCreateShader"](shader_type)
                encoded = source.encode("utf-8")
                source_pointer = c_char_p(encoded)
                length = c_int(len(encoded))
                functions["glShaderSource"](shader, 1, ctypes.byref(source_pointer), ctypes.byref(length))
                functions["glCompileShader"](shader)
                status = c_int()
                functions["glGetShaderiv"](shader, GL_COMPILE_STATUS, ctypes.byref(status))
                if not status.value:
                    raise PakError("Shader-Compilefehler: " + _shader_log(functions, shader))
                return shader

            vertex_shader = compile_shader(GL_VERTEX_SHADER, VERTEX_SHADER_SOURCE)
            fragment_shader = compile_shader(GL_FRAGMENT_SHADER, FRAGMENT_SHADER_SOURCE)
            program = functions["glCreateProgram"]()
            functions["glAttachShader"](program, vertex_shader)
            functions["glAttachShader"](program, fragment_shader)
            functions["glLinkProgram"](program)
            status = c_int()
            functions["glGetProgramiv"](program, GL_LINK_STATUS, ctypes.byref(status))
            if not status.value:
                raise PakError("Shader-Linkfehler: " + _program_log(functions, program))
            self._material_program = int(program)
            self._shader_objects = [int(vertex_shader), int(fragment_shader)]
            uniform_names = (
                "u_base_map", "u_normal_map", "u_spec_map", "u_rough_map", "u_emission_map",
                "u_metal_map", "u_ao_map",
                "u_has_base", "u_has_normal", "u_has_spec", "u_has_rough", "u_has_emission",
                "u_has_metal", "u_has_ao",
                "u_gloss_from_alpha", "u_base_color", "u_spec_color", "u_emission_color",
                "u_normal_strength", "u_normal_y_sign", "u_spec_strength", "u_roughness",
                "u_metallic", "u_emission_strength",
            )
            self._shader_uniforms = {
                name: functions["glGetUniformLocation"](program, name.encode("ascii"))
                for name in uniform_names
            }
            self._tangent_location = functions["glGetAttribLocation"](program, b"a_tangent")

        def _upload_geometry(self):
            super()._upload_geometry()
            for vbuf_index, source in self.scene.get("vertex_buffers", {}).items():
                gpu = self._gpu_vbufs.get(vbuf_index)
                if gpu is None:
                    continue
                tangents = list(source.get("tangents") or [])
                if not tangents:
                    tangents = [1.0, 0.0, 0.0, 1.0] * int(source.get("vertex_count", 0))
                gpu["tangents"] = (ctypes.c_float * len(tangents))(*tangents)

        def _upload_one_texture(self, image):
            gl = self._wgl.opengl
            max_size = ctypes.c_int(4096)
            gl.glGetIntegerv(mv.GL_MAX_TEXTURE_SIZE, ctypes.byref(max_size))
            limit = max(256, int(max_size.value or 4096))
            source = image
            if max(source.size) > limit:
                scale = limit / float(max(source.size))
                size = (max(1, int(source.width * scale)), max(1, int(source.height * scale)))
                resampling = getattr(getattr(mv.PILImage, "Resampling", mv.PILImage), "LANCZOS")
                source = source.resize(size, resampling)
            transpose_enum = getattr(getattr(mv.PILImage, "Transpose", mv.PILImage), "FLIP_TOP_BOTTOM")
            source = source.transpose(transpose_enum).convert("RGBA")
            pixels = ctypes.create_string_buffer(source.tobytes("raw", "RGBA"))
            texture_id = ctypes.c_uint()
            gl.glGenTextures(1, ctypes.byref(texture_id))
            gl.glBindTexture(mv.GL_TEXTURE_2D, texture_id.value)
            gl.glTexParameteri(mv.GL_TEXTURE_2D, mv.GL_TEXTURE_MIN_FILTER, mv.GL_LINEAR)
            gl.glTexParameteri(mv.GL_TEXTURE_2D, mv.GL_TEXTURE_MAG_FILTER, mv.GL_LINEAR)
            gl.glTexParameteri(mv.GL_TEXTURE_2D, mv.GL_TEXTURE_WRAP_S, mv.GL_REPEAT)
            gl.glTexParameteri(mv.GL_TEXTURE_2D, mv.GL_TEXTURE_WRAP_T, mv.GL_REPEAT)
            gl.glPixelStorei(mv.GL_UNPACK_ALIGNMENT, 1)
            gl.glTexImage2D(
                mv.GL_TEXTURE_2D, 0, mv.GL_RGBA, source.width, source.height, 0,
                mv.GL_RGBA, mv.GL_UNSIGNED_BYTE, ctypes.cast(pixels, ctypes.c_void_p),
            )
            return int(texture_id.value)

        def _upload_textures(self):
            super()._upload_textures()
            if mv.PILImage is None:
                return
            defaults = {
                "white": mv.PILImage.new("RGBA", (1, 1), (255, 255, 255, 255)),
                "normal": mv.PILImage.new("RGBA", (1, 1), (128, 128, 255, 255)),
                "black": mv.PILImage.new("RGBA", (1, 1), (0, 0, 0, 255)),
            }
            self._default_gl_textures = {name: self._upload_one_texture(image) for name, image in defaults.items()}
            for material_index, slots in self.scene.get("material_maps", {}).items():
                self._material_gl_textures[material_index] = {
                    slot: self._upload_one_texture(image)
                    for slot, image in slots.items()
                }

        def _set_uniform_i(self, name, value):
            location = self._shader_uniforms.get(name, -1)
            if location >= 0:
                self._glsl["glUniform1i"](location, int(value))

        def _set_uniform_f(self, name, value):
            location = self._shader_uniforms.get(name, -1)
            if location >= 0:
                self._glsl["glUniform1f"](location, float(value))

        def _set_uniform_3(self, name, value):
            location = self._shader_uniforms.get(name, -1)
            if location >= 0:
                self._glsl["glUniform3f"](location, float(value[0]), float(value[1]), float(value[2]))

        def _bind_texture_unit(self, unit, texture_id):
            self._glsl["glActiveTexture"](GL_TEXTURE0 + int(unit))
            self._wgl.opengl.glBindTexture(mv.GL_TEXTURE_2D, int(texture_id))

        def _render(self):
            display_mode = getattr(self, "display_mode", None)
            mode = str(display_mode.get() if display_mode is not None else "Texturen")
            if (
                mode != "Texturen"
                or not self.material_shader_enabled.get()
                or not self._material_program
                or not self._glsl
            ):
                return super()._render()
            return self._render_material_shader()

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
            functions["glUseProgram"](self._material_program)
            for unit, name in enumerate((
                "u_base_map", "u_normal_map", "u_spec_map", "u_rough_map",
                "u_emission_map", "u_metal_map", "u_ao_map",
            )):
                self._set_uniform_i(name, unit)
            if self._tangent_location >= 0:
                functions["glEnableVertexAttribArray"](self._tangent_location)

            selected_channel = self._selected_uv_channel() if hasattr(self, "_selected_uv_channel") else 0
            meshes = self._visible_gpu_meshes() if hasattr(self, "_visible_gpu_meshes") else self._gpu_meshes
            bound_vbuf = None
            for mesh in meshes:
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
                    if self._tangent_location >= 0:
                        functions["glVertexAttribPointer"](
                            self._tangent_location, 4, mv.GL_FLOAT, GL_FALSE, 0,
                            ctypes.cast(vbuf["tangents"], ctypes.c_void_p),
                        )
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
                self._set_uniform_f("u_emission_strength", params.get("emission_strength", 1.0) if self.emission_maps_enabled.get() else 0.0)

                gl.glDrawElements(
                    mv.GL_TRIANGLES, mesh["index_count"], mv.GL_UNSIGNED_INT,
                    ctypes.cast(mesh["gpu_indices"], ctypes.c_void_p),
                )

            if self._tangent_location >= 0:
                functions["glDisableVertexAttribArray"](self._tangent_location)
            functions["glUseProgram"](0)
            functions["glActiveTexture"](GL_TEXTURE0)
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
            lines = [
                f"Modell: {self.scene.get('name')}",
                f"Renderer: {'GLSL Materialshader' if self._material_program else 'Fixed-Function-Fallback'}",
            ]
            if self._material_shader_error:
                lines.extend(("", "GLSL-Fehler:", self._material_shader_error))
            materials = self.scene.get("materials") or []
            maps = self.scene.get("material_map_names") or {}
            metadata = self.scene.get("material_map_metadata") or {}
            unsupported = self.scene.get("unsupported_material_maps") or {}
            params = self.scene.get("material_params") or {}
            lines.extend(("", "Materialien:"))
            material_indices = sorted(set(params) | set(maps) | set(range(len(materials))))
            for index in material_indices:
                name = materials[index] if index < len(materials) else f"material_{index}"
                lines.append(f"\n[{index}] {name}")
                for slot, texture_name in sorted(maps.get(index, {}).items()):
                    meta = metadata.get(index, {}).get(slot, {})
                    extra = " | Gloss aus Alpha" if slot == "spec_gloss" and meta.get("alpha_varies") else ""
                    lines.append(f"  {slot}: {texture_name} | {meta.get('tag', '?')} | {meta.get('size', '?')}{extra}")
                value = params.get(index, {})
                lines.append(
                    "  Parameter: roughness={:.3g}, metallic={:.3g}, spec={:.3g}, normal={:.3g}, emission={:.3g}".format(
                        value.get("roughness", 0.55), value.get("metallic", 0.0),
                        value.get("spec_strength", 1.0), value.get("normal_strength", 1.0),
                        value.get("emission_strength", 1.0),
                    )
                )
                if value.get("scalar_tags"):
                    lines.append("  Scalars: " + ", ".join(f"{tag}={number:.6g}" for tag, number in value["scalar_tags"].items()))
                if value.get("color_tags"):
                    lines.append("  Colors: " + ", ".join(value["color_tags"].keys()))
                for item in unsupported.get(index, []):
                    lines.append(f"  noch nicht simuliert: {item.get('tag')} ({item.get('slot')})")
            errors = self.scene.get("material_map_errors") or []
            if errors:
                lines.extend(("", "TXTR-Fehler:"))
                lines.extend(f"  {error}" for error in errors)
            lines.extend((
                "",
                "Hinweise:",
                "- SPCTTXTR wird als Specular/Gloss interpretiert.",
                "- Bei variablem Alpha wird Alpha als Gloss und 1-Gloss als Roughness verwendet.",
                "- Bei konstantem Alpha wird die RGB-Luminanz als Gloss verwendet.",
                "- SPCFTXTR und FUR*TXTR benötigen eigene, noch nicht rekonstruierte Shaderstufen.",
            ))
            dialog = tk.Toplevel(self)
            dialog.title("Material-Info")
            dialog.geometry("1000x720")
            text = ScrolledText(dialog, wrap="none")
            text.pack(fill="both", expand=True, padx=8, pady=8)
            text.insert("1.0", "\n".join(lines))
            text.configure(state="disabled")

        def close(self):
            try:
                if self._make_current():
                    if self._glsl and self._material_program:
                        self._glsl["glUseProgram"](0)
                        self._glsl["glDeleteProgram"](self._material_program)
                        for shader in self._shader_objects:
                            self._glsl["glDeleteShader"](shader)
                    texture_ids = list(self._default_gl_textures.values())
                    for slots in self._material_gl_textures.values():
                        texture_ids.extend(slots.values())
                    if texture_ids:
                        array = (ctypes.c_uint * len(texture_ids))(*texture_ids)
                        self._wgl.opengl.glDeleteTextures(len(texture_ids), array)
            except Exception:
                pass
            self._material_program = 0
            self._shader_objects = []
            self._default_gl_textures = {}
            self._material_gl_textures = {}
            return super().close()

    MaterialMeshViewer.__name__ = "MaterialMeshViewer"
    mv.MeshViewer = MaterialMeshViewer
