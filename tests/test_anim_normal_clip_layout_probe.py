import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "PAKPY" / "anim_normal_clip_layout_probe.py"
spec = importlib.util.spec_from_file_location("probe", MODULE_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(probe)


def test_mask_bits_length_and_order():
    mask = bytes([0x80]) + bytes(10)
    assert probe.mask_bits(mask, "msb")[0] == 1
    assert probe.mask_bits(mask, "lsb")[7] == 1
    assert len(probe.mask_bits(mask, "msb")) == 88


def test_stride_candidates_exact():
    found = probe.stride_candidates(bytes(61 * 192 + 2), 61)
    assert any(item["tail_bytes"] == 2 and item["record_bytes"] == 192 for item in found)
