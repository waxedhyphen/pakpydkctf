from __future__ import annotations

from dataclasses import dataclass
import math
import struct
from pathlib import Path
from typing import Final


class AnimFormatError(ValueError):
    """Raised when a file violates a verified DKCTF ANIM invariant."""


@dataclass(frozen=True)
class FormDescriptor:
    form_size: int
    unknown_u64: int
    form_id: str
    form_version: int
    data_version: int


@dataclass(frozen=True)
class RootTransform:
    quaternion_wxyz: tuple[float, float, float, float]
    translation_xyz: tuple[float, float, float]

    @property
    def quaternion_norm_sq(self) -> float:
        return sum(value * value for value in self.quaternion_wxyz)


@dataclass(frozen=True)
class ChannelDescriptor:
    encoded_width: int
    source_count: int
    source_ids: tuple[int, ...]


@dataclass(frozen=True)
class DkctfAnim:
    raw: bytes
    form: FormDescriptor
    payload_tag: int
    inner_size: int
    control: int
    family: int
    family_flags: int
    mode: int
    stored_frame_count: int
    group_hash: int
    descriptor: ChannelDescriptor
    root_transform: RootTransform
    root_flags: int
    payload_offset: int
    payload: bytes

    @property
    def zero_padding_size(self) -> int:
        return len(self.payload) - len(self.payload.rstrip(b"\x00"))

    @property
    def used_payload(self) -> bytes:
        return self.payload.rstrip(b"\x00")


RFRM_HEADER_SIZE: Final[int] = 0x20
ANIM_INNER_HEADER_OFFSET: Final[int] = 0x20
ANIM_PAYLOAD_TAG: Final[int] = 0x49170014
SUPPORTED_FAMILIES: Final[set[int]] = {0x81, 0x82, 0xC1, 0xC2}
C_FAMILIES: Final[set[int]] = {0xC1, 0xC2}

_VERIFIED_DESCRIPTOR_IDS: Final[dict[int, tuple[int, ...]]] = {
    1: (1,),
    3: (1, 2, 3),
    4: (1, 2, 3, 4),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnimFormatError(message)


def _be_u32(data: bytes, offset: int) -> int:
    _require(offset + 4 <= len(data), f"u32 outside file at 0x{offset:X}")
    return struct.unpack_from(">I", data, offset)[0]


def _be_u64(data: bytes, offset: int) -> int:
    _require(offset + 8 <= len(data), f"u64 outside file at 0x{offset:X}")
    return struct.unpack_from(">Q", data, offset)[0]


def _be_f32_tuple(data: bytes, offset: int, count: int) -> tuple[float, ...]:
    size = count * 4
    _require(offset + size <= len(data), f"{count} float32 values outside file at 0x{offset:X}")
    values = struct.unpack_from(f">{count}f", data, offset)
    _require(all(math.isfinite(value) for value in values), f"non-finite float at 0x{offset:X}")
    return values


def parse_anim_bytes(data: bytes, *, strict: bool = True) -> DkctfAnim:
    """Parse only fields whose byte layout is verified across the supplied corpus.

    This function intentionally does not decode the compressed skeletal payload.
    Returning invented Euler angles or sequential bone mappings would be incorrect.
    """
    _require(len(data) >= 0x55, "file is too small for a DKCTF ANIM")
    _require(data[0:4] == b"RFRM", "missing RFRM magic")

    form_size = _be_u64(data, 0x04)
    unknown_u64 = _be_u64(data, 0x0C)
    form_id_raw = data[0x14:0x18]
    _require(form_id_raw == b"ANIM", f"unexpected form id {form_id_raw!r}")
    form_version = _be_u32(data, 0x18)
    data_version = _be_u32(data, 0x1C)

    if strict:
        _require(form_size == len(data) - RFRM_HEADER_SIZE,
                 f"RFRM size mismatch: {form_size} != {len(data) - RFRM_HEADER_SIZE}")
        _require(unknown_u64 == 0, f"RFRM unknown u64 is 0x{unknown_u64:X}, expected 0")
        _require(form_version == 20, f"unexpected form version {form_version}")
        _require(data_version == form_version,
                 f"data version {data_version} != form version {form_version}")

    payload_tag = _be_u32(data, 0x20)
    inner_size = _be_u32(data, 0x24)
    control = _be_u32(data, 0x28)
    group_hash = _be_u32(data, 0x2C)
    family = (control >> 24) & 0xFF
    family_flags = (control >> 16) & 0xFF
    mode = (control >> 8) & 0xFF

    if strict:
        _require(payload_tag == ANIM_PAYLOAD_TAG,
                 f"unexpected ANIM payload tag 0x{payload_tag:08X}")
        _require(inner_size == len(data) - 0x28,
                 f"inner size mismatch: {inner_size} != {len(data) - 0x28}")
        _require(family in SUPPORTED_FAMILIES, f"unsupported control family 0x{family:02X}")

    c_family = family in C_FAMILIES
    descriptor_offset = 0x31 if c_family else 0x30
    stored_frame_count = data[0x30] if c_family else control & 0xFF

    encoded_width = data[descriptor_offset]
    source_count = data[descriptor_offset + 1]
    separator = data[descriptor_offset + 2]
    source_ids_raw = tuple(data[descriptor_offset + 3:descriptor_offset + 7])
    expected_ids = _VERIFIED_DESCRIPTOR_IDS.get(source_count)

    if strict:
        _require(expected_ids is not None, f"unverified descriptor source count {source_count}")
        _require(encoded_width == source_count * 7,
                 f"descriptor width {encoded_width} != 7 * source count {source_count}")
        _require(separator == 0xFF, f"descriptor separator is 0x{separator:02X}, expected 0xFF")
        _require(source_ids_raw[:source_count] == expected_ids,
                 f"unexpected descriptor source ids {source_ids_raw[:source_count]!r}")
        _require(all(value == 0 for value in source_ids_raw[source_count:]),
                 f"non-zero descriptor padding {source_ids_raw[source_count:]!r}")

    root_offset = descriptor_offset + 7
    quaternion = _be_f32_tuple(data, root_offset, 4)
    translation = _be_f32_tuple(data, root_offset + 16, 3)
    root_flags_offset = root_offset + 28
    root_flags = data[root_flags_offset]
    payload_offset = root_flags_offset + 1
    payload = data[payload_offset:]

    root_transform = RootTransform(
        quaternion_wxyz=(
            float(quaternion[0]), float(quaternion[1]),
            float(quaternion[2]), float(quaternion[3]),
        ),
        translation_xyz=(
            float(translation[0]), float(translation[1]), float(translation[2]),
        ),
    )

    if strict:
        _require(abs(root_transform.quaternion_norm_sq - 1.0) <= 1e-4,
                 f"root quaternion is not normalized: norm^2={root_transform.quaternion_norm_sq}")
        _require(payload, "ANIM has no compressed payload")

    return DkctfAnim(
        raw=data,
        form=FormDescriptor(
            form_size=form_size,
            unknown_u64=unknown_u64,
            form_id="ANIM",
            form_version=form_version,
            data_version=data_version,
        ),
        payload_tag=payload_tag,
        inner_size=inner_size,
        control=control,
        family=family,
        family_flags=family_flags,
        mode=mode,
        stored_frame_count=stored_frame_count,
        group_hash=group_hash,
        descriptor=ChannelDescriptor(
            encoded_width=encoded_width,
            source_count=source_count,
            source_ids=source_ids_raw[:source_count],
        ),
        root_transform=root_transform,
        root_flags=root_flags,
        payload_offset=payload_offset,
        payload=payload,
    )


def parse_anim(path: str | Path, *, strict: bool = True) -> DkctfAnim:
    return parse_anim_bytes(Path(path).read_bytes(), strict=strict)
