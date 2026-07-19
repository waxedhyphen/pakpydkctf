"""Correct post-LoadVecRange span scaling for normal_clip vector codecs.

The original setup port selected the span multiplier from unrelated low flag
bits. The game selects it from the same flag pairs that select compact versus
extended value readers. Importing this module applies the correction to the
existing setup module so old call sites keep working.
"""
from __future__ import annotations
import struct
import anim_normal_clip_setup as setup

FINE_MULTIPLIER = struct.unpack('<f', bytes.fromhex('00008030'))[0]
COARSE_MULTIPLIER = struct.unpack('<f', bytes.fromhex('08008035'))[0]

def translation_span_multiplier(flags: int) -> float:
    return FINE_MULTIPLIER if (flags & 0x0C) == 0x0C else COARSE_MULTIPLIER

def scale_span_multiplier(flags: int) -> float:
    return FINE_MULTIPLIER if (flags & 0x30) == 0x30 else COARSE_MULTIPLIER

def apply() -> None:
    setup.VEC_RANGE_FINE_MULTIPLIER = FINE_MULTIPLIER
    setup.VEC_RANGE_COARSE_MULTIPLIER = COARSE_MULTIPLIER
    setup.translation_span_multiplier = translation_span_multiplier
    setup.scale_span_multiplier = scale_span_multiplier

apply()
