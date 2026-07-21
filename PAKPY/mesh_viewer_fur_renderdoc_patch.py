"""RenderDoc-grounded corrections for the static Fur shell pass.

The supplied capture shows that Fur layers are emitted as instanced indexed draws.
The previous viewer used a screen-space random dither and moved the tiny FURTTXTR
pattern independently on every shell.  That destroyed strand coherence and caused
the visible pepper noise.  This patch keeps every shell on one stable UV-bound
strand field, while FURLTXTR controls strand depth and FURFTXTR bends geometry.
"""
from __future__ import annotations

import mesh_viewer as mv
import mesh_viewer_fur_shader_patch as fur_patch


_INSTALLED = False


RENDERDOC_FUR_FRAGMENT_SHADER_SOURCE = r"""
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
uniform float u_shell_count;

varying vec2 v_uv;
varying vec3 v_eye_pos;
varying vec3 v_tangent;
varying vec3 v_bitangent;
varying vec3 v_normal;
varying vec2 v_fur_flow;
varying float v_fur_length;
varying float v_shell_fraction;

void main() {
    vec4 base_sample = texture2D(u_base_map, v_uv);
    float strand_length = clamp(v_fur_length, 0.0, 1.0);

    // RenderDoc shows instanced copies of the same shell geometry.  A strand must
    // therefore remain at the same UV position through all instances.  Moving or
    // randomly dithering the pattern per screen pixel turns coherent strands into
    // the pepper noise seen in the old viewport.
    vec2 mask_uv = v_uv * max(u_fur_density, 1.0);
    float strand_mask = texture2D(u_fur_mask_map, mask_uv).r;

    if (v_shell_fraction > strand_length) {
        discard;
    }

    // FURTTXTR is nearly binary.  The progressively higher threshold narrows the
    // anti-aliased edge on outer shells without changing the strand's UV anchor.
    // This is a deterministic single-sample substitute for the game's coverage
    // path, not screen-space noise.
    float shell_threshold = mix(0.46, 0.60, v_shell_fraction);
    float edge_width = max(fwidth(strand_mask), 1.0 / 255.0);
    float strand_coverage = smoothstep(
        shell_threshold - edge_width,
        shell_threshold + edge_width,
        strand_mask
    );
    if (strand_coverage < 0.5) {
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

    vec2 flow = v_fur_flow;
    vec3 flow_tangent = v_tangent * flow.x + v_bitangent * flow.y;
    if (dot(flow_tangent, flow_tangent) < 0.000001) {
        flow_tangent = v_tangent;
    }
    flow_tangent = normalize(flow_tangent + normal * 0.06);
    float t_dot_h = clamp(dot(flow_tangent, half_dir), -1.0, 1.0);
    float anisotropic_angle = sqrt(max(0.0, 1.0 - t_dot_h * t_dot_h));
    float spec_falloff = u_has_spec_curve != 0
        ? texture2D(u_spec_curve_map, vec2(anisotropic_angle, 0.5)).r
        : pow(anisotropic_angle, max(u_spec_power, 1.0));
    vec3 spec_sample = u_has_spec != 0
        ? texture2D(u_spec_map, v_uv).rgb
        : vec3(0.12);

    float shell_position = v_shell_fraction / max(strand_length, 0.001);
    float root_light = smoothstep(
        clamp(u_fur_occlusion_start, 0.0, 0.98),
        1.0,
        shell_position
    );
    float root_occlusion = mix(0.42, 1.0, root_light);

    // Fur colour comes from the diffuse texture and explicit diffuse colour only.
    // The Fur texture controls coverage, never RGB.
    vec3 albedo = base_sample.rgb * u_base_color;
    vec3 color = albedo * (0.23 + 0.77 * n_dot_l) * root_occlusion;
    color += spec_sample * u_spec_color * (spec_falloff * n_dot_l * 0.24);

    float fresnel = 1.0 - max(dot(normal, view_dir), 0.0);
    float rim = smoothstep(
        u_rim_min,
        max(u_rim_max, u_rim_min + 0.001),
        fresnel
    );
    vec3 rim_tint = mix(albedo, albedo * u_rim_color, 0.55);
    color += rim_tint * (rim * min(u_rim_strength, 3.0) * 0.14);

    gl_FragColor = vec4(max(color, vec3(0.0)), 1.0);
}
"""


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    # FurMeshViewer resolves these module globals when a viewer instance creates
    # its programs, so replacing the source here affects every subsequently opened
    # viewer without duplicating the full renderer implementation.
    fur_patch.FUR_FRAGMENT_SHADER_SOURCE = RENDERDOC_FUR_FRAGMENT_SHADER_SOURCE

    BaseViewer = mv.MeshViewer

    class RenderDocFurViewer(BaseViewer):
        def _setup_gl_state(self):
            super()._setup_gl_state()
            if getattr(self, "_fur_program", 0):
                status = getattr(self, "_fur_status", None)
                if status is not None:
                    status.configure(text="Fur: RenderDoc-stabile Shells")

    RenderDocFurViewer.__name__ = "RenderDocFurViewer"
    mv.MeshViewer = RenderDocFurViewer
