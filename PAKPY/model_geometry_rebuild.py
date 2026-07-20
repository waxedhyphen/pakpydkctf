"""Binary CMDL/SMDL/WMDL geometry encoder used by the BLEND repacker."""
from __future__ import annotations

import math
import struct
import zlib
from typing import Any, Iterable

import pak_core
import pak_extract
import rigged_gltf

def _pack_half(value: float) -> bytes:
    value = float(value)
    if not math.isfinite(value):
        value = 0.0
    value = min(max(value, -65504.0), 65504.0)
    return struct.pack("<e", value)


def _write_vec4_half(buffer: bytearray, offset: int, values: Iterable[float]) -> None:
    values = list(values)
    while len(values) < 4:
        values.append(0.0)
    for index in range(4):
        buffer[offset + index * 2 : offset + index * 2 + 2] = _pack_half(values[index])


def _write_vec2_half(buffer: bytearray, offset: int, values: Iterable[float]) -> None:
    values = list(values)
    while len(values) < 2:
        values.append(0.0)
    buffer[offset : offset + 2] = _pack_half(values[0])
    buffer[offset + 2 : offset + 4] = _pack_half(values[1])


def _decode_old_gpu_blocks(chunks: dict[str, bytes], vbufs: list[dict[str, Any]], ibufs: list[dict[str, Any]], meshes: list[dict[str, Any]]) -> list[bytes]:
    blocks = pak_extract.decompress_gpu_blocks(chunks["GPU "])
    expected_count = len(vbufs) + len(ibufs)
    if len(blocks) != expected_count:
        raise pak_core.PakError(f"GPU-Blockzahl {len(blocks)} passt nicht zu VBUF+IBUF {expected_count}")
    out: list[bytes] = []
    for index, vbuf in enumerate(vbufs):
        expected = int(vbuf["vertex_count"]) * int(vbuf["stride"])
        block = blocks[index]
        raw = block.get("data") if block.get("handled") else pak_extract.decode_gpu_block_data(block["tag"], block["payload"], expected)
        if len(raw) < expected:
            raise pak_core.PakError(f"Alter VBUF {index} ist zu kurz")
        out.append(bytes(raw[:expected]))
    for index, ibuf in enumerate(ibufs):
        bytes_per_index = 2 if int(ibuf["index_type"]) in (0, 1) else 4
        expected_count_for_buffer = max(
            (int(mesh["index_buffer_offset"]) + int(mesh["index_count"]) for mesh in meshes if int(mesh["index_buffer_index"]) == index),
            default=0,
        )
        expected = expected_count_for_buffer * bytes_per_index
        block = blocks[len(vbufs) + index]
        raw = block.get("data") if block.get("handled") else pak_extract.decode_gpu_block_data(block["tag"], block["payload"], expected)
        if len(raw) < expected:
            raise pak_core.PakError(f"Alter IBUF {index} ist zu kurz")
        out.append(bytes(raw[:expected]))
    return out


def _encode_vertex_buffer(
    descriptor: dict[str, Any],
    vertices: list[dict[str, Any]],
    template_data: bytes,
) -> bytes:
    stride = int(descriptor.get("stride", 0))
    if stride <= 0:
        raise pak_core.PakError("VBUF-Stride ist ungültig")
    template = template_data[:stride] if len(template_data) >= stride else bytes(stride)
    output = bytearray()
    for vertex in vertices:
        record = bytearray(template)
        tangent_written = False
        uv_written = False
        for component in descriptor.get("components") or []:
            offset = int(component.get("offset", 0))
            fmt = int(component.get("format", -1))
            semantic = int(component.get("type", -1))
            if offset < 0 or offset >= stride:
                raise pak_core.PakError("VBUF-Komponentenoffset liegt außerhalb des Strides")
            if fmt == 37 and semantic == 0 and offset + 12 <= stride:
                record[offset : offset + 12] = struct.pack("<3f", *[float(value) for value in vertex["position"][:3]])
            elif fmt == 34 and semantic == 1 and offset + 8 <= stride:
                _write_vec4_half(record, offset, list(vertex["normal"][:3]) + [0.0])
            elif fmt == 34 and semantic in {2, 3, 12, 13} and offset + 8 <= stride and not tangent_written:
                _write_vec4_half(record, offset, vertex["tangent"][:4])
                tangent_written = True
            elif fmt in (20, 21) and semantic in {4, 5, 6, 7, 8, 9, 10, 11} and offset + 4 <= stride and not uv_written:
                _write_vec2_half(record, offset, vertex["uv"][:2])
                uv_written = True
            elif fmt == 22 and semantic == 9 and offset + 4 <= stride:
                joints = [min(max(0, int(value)), 255) for value in vertex["joints"][:4]]
                while len(joints) < 4:
                    joints.append(0)
                record[offset : offset + 4] = bytes(joints[:4])
            elif fmt == 34 and semantic == 10 and offset + 8 <= stride:
                _write_vec4_half(record, offset, vertex["weights"][:4])
        output.extend(record)
    return bytes(output)


def _serialize_vbufs(vbufs: list[dict[str, Any]]) -> bytes:
    out = bytearray(len(vbufs).to_bytes(4, "big"))
    for vbuf in vbufs:
        components = list(vbuf.get("components") or [])
        out += int(vbuf["vertex_count"]).to_bytes(4, "big")
        out += len(components).to_bytes(4, "big")
        for component in components:
            for key in ("field_0", "offset", "stride", "format", "type"):
                out += int(component.get(key, 0)).to_bytes(4, "big")
    return bytes(out)


def _serialize_ibufs(ibufs: list[dict[str, Any]]) -> bytes:
    out = bytearray(len(ibufs).to_bytes(4, "big"))
    for ibuf in ibufs:
        out += int(ibuf["index_type"]).to_bytes(4, "big")
    return bytes(out)


def _serialize_meshes(meshes: list[dict[str, Any]]) -> bytes:
    out = bytearray(len(meshes).to_bytes(4, "big"))
    for mesh in meshes:
        out += int(mesh.get("primitive_mode", 3)).to_bytes(4, "big")
        out += int(mesh.get("material_index", 0)).to_bytes(2, "big")
        out += bytes([int(mesh.get("vertex_buffer_index", 0)) & 0xFF, int(mesh.get("index_buffer_index", 0)) & 0xFF])
        out += int(mesh.get("index_buffer_offset", 0)).to_bytes(4, "big")
        out += int(mesh.get("index_count", 0)).to_bytes(4, "big")
        out += int(mesh.get("field_10", 0)).to_bytes(2, "big")
        out += bytes([int(mesh.get("field_12", 0)) & 0xFF, int(mesh.get("field_13", 0)) & 0xFF, int(mesh.get("flags", 0)) & 0xFF])
    return bytes(out)


def _build_model_asset(original_asset: bytes, parts: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    chunks = pak_extract.parse_chunks(original_asset)
    original_meshes = pak_extract.parse_meshes(chunks["MESH"])
    vbufs = pak_extract.parse_vbufs(chunks["VBUF"])
    ibufs = pak_extract.parse_ibufs(chunks["IBUF"])
    if len(parts) != len(original_meshes):
        raise pak_core.PakError(f"MESH-Partzahl änderte sich von {len(original_meshes)} auf {len(parts)}")
    old_gpu_data = _decode_old_gpu_blocks(chunks, vbufs, ibufs, original_meshes)
    new_meshes = [dict(mesh) for mesh in original_meshes]
    vbuf_vertices: list[list[dict[str, Any]]] = [[] for _ in vbufs]
    part_vertex_bases: dict[int, int] = {}
    for mesh_index, (mesh, part) in enumerate(zip(new_meshes, parts)):
        vbuf_index = int(mesh["vertex_buffer_index"])
        if not 0 <= vbuf_index < len(vbufs):
            raise pak_core.PakError(f"MESH {mesh_index} verweist auf ungültigen VBUF {vbuf_index}")
        part_vertex_bases[mesh_index] = len(vbuf_vertices[vbuf_index])
        count = len(part["positions"])
        for vertex_index in range(count):
            vbuf_vertices[vbuf_index].append(
                {
                    "position": part["positions"][vertex_index],
                    "normal": part["normals"][vertex_index],
                    "tangent": part["tangents"][vertex_index],
                    "uv": part["uvs"][vertex_index],
                    "joints": part["joints"][vertex_index],
                    "weights": part["weights"][vertex_index],
                }
            )
    new_vertex_blocks: list[bytes] = []
    for index, descriptor in enumerate(vbufs):
        if vbuf_vertices[index]:
            descriptor["vertex_count"] = len(vbuf_vertices[index])
            new_vertex_blocks.append(_encode_vertex_buffer(descriptor, vbuf_vertices[index], old_gpu_data[index]))
        else:
            new_vertex_blocks.append(old_gpu_data[index])
    ibuf_indices: list[list[int]] = [[] for _ in ibufs]
    for mesh_index, (mesh, part) in enumerate(zip(new_meshes, parts)):
        ibuf_index = int(mesh["index_buffer_index"])
        if not 0 <= ibuf_index < len(ibufs):
            raise pak_core.PakError(f"MESH {mesh_index} verweist auf ungültigen IBUF {ibuf_index}")
        base = part_vertex_bases[mesh_index]
        mesh["primitive_mode"] = 3
        mesh["index_buffer_offset"] = len(ibuf_indices[ibuf_index])
        converted = [base + int(value) for value in part["indices"]]
        mesh["index_count"] = len(converted)
        ibuf_indices[ibuf_index].extend(converted)
    new_index_blocks: list[bytes] = []
    for index, descriptor in enumerate(ibufs):
        values = ibuf_indices[index]
        used = any(int(mesh["index_buffer_index"]) == index for mesh in new_meshes)
        if not used:
            new_index_blocks.append(old_gpu_data[len(vbufs) + index])
            continue
        max_index = max(values, default=0)
        old_type = int(descriptor.get("index_type", 1))
        if max_index > 0xFFFF:
            descriptor["index_type"] = 2
        elif old_type not in (0, 1, 2):
            descriptor["index_type"] = 1
        index_type = int(descriptor["index_type"])
        if index_type in (0, 1):
            new_index_blocks.append(struct.pack("<" + "H" * len(values), *values) if values else b"")
        else:
            new_index_blocks.append(struct.pack("<" + "I" * len(values), *values) if values else b"")
    all_positions = [position for part in parts for position in part["positions"]]
    if not all_positions:
        raise pak_core.PakError("Modellrückbau erzeugte keine Vertices")
    head_payload = bytearray(chunks["HEAD"])
    if len(head_payload) < 44:
        raise pak_core.PakError("HEAD-Chunk ist zu klein für eine neue Bounding Box")
    mins = [min(position[axis] for position in all_positions) for axis in range(3)]
    maxs = [max(position[axis] for position in all_positions) for axis in range(3)]
    head_payload[20:32] = struct.pack(">3f", *mins)
    head_payload[32:44] = struct.pack(">3f", *maxs)
    gpu_payload = b"".join((0x0D000000).to_bytes(4, "big") + zlib.compress(block, 9) for block in new_vertex_blocks + new_index_blocks)
    replacement_payloads = {
        "HEAD": bytes(head_payload),
        "MESH": _serialize_meshes(new_meshes),
        "VBUF": _serialize_vbufs(vbufs),
        "IBUF": _serialize_ibufs(ibufs),
        "GPU ": gpu_payload,
    }
    chunk_records = pak_core.parse_asset_chunks(original_asset)
    rebuilt_chunks = []
    for record in chunk_records:
        payload = replacement_payloads.get(record["tag"])
        rebuilt_chunks.append(pak_core.build_chunk_raw(record, payload) if payload is not None else record["raw"])
    body = b"".join(rebuilt_chunks)
    root = bytearray(original_asset[:32])
    pak_core.w64(root, 4, len(body))
    new_asset = bytes(root) + body
    parsed = rigged_gltf.load_model_with_skin(new_asset)
    if len(parsed.get("meshes") or []) != len(parts):
        raise pak_core.PakError("Neu gebautes Modell konnte nicht mit korrekter MESH-Zahl gelesen werden")
    face_count = sum(len(part["indices"]) // 3 for part in parts)
    return new_asset, {
        "mesh_count": len(parts),
        "vertex_count": len(all_positions),
        "face_count": face_count,
        "vbuf_count": len(vbufs),
        "ibuf_count": len(ibufs),
        "gpu_codec": "zlib",
    }


def _relaxed_model_meta(original):
    def wrapped(entry, old_asset, new_asset):
        old_gpu = pak_core.find_asset_chunk(old_asset, "GPU ")
        new_gpu = pak_core.find_asset_chunk(new_asset, "GPU ")
        if old_gpu is None or new_gpu is None:
            return original(entry, old_asset, new_asset)
        old_payload = old_asset[old_gpu["payload_off"] : old_gpu["payload_end"]]
        new_payload = new_asset[new_gpu["payload_off"] : new_gpu["payload_end"]]
        if old_payload == new_payload:
            return original(entry, old_asset, new_asset)
        original_parse = pak_core.parse_gpu_segments
        cached_old_segments: list[dict[str, Any]] | None = None

        def compatible(payload):
            nonlocal cached_old_segments
            segments = original_parse(payload)
            if payload == old_payload:
                cached_old_segments = [dict(item) for item in segments]
                return segments
            if payload == new_payload:
                if cached_old_segments is None:
                    cached_old_segments = [dict(item) for item in original_parse(old_payload)]
                if len(cached_old_segments) == len(segments):
                    for old, new in zip(cached_old_segments, segments):
                        new["kind"] = old["kind"]
                        new["kind_name"] = old["kind_name"]
            return segments

        pak_core.parse_gpu_segments = compatible
        try:
            return original(entry, old_asset, new_asset)
        finally:
            pak_core.parse_gpu_segments = original_parse

    wrapped._pakpy_allow_zlib_model_segments = True
    return wrapped
