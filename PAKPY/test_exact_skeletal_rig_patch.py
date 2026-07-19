import json
import struct
import tempfile
import unittest
from pathlib import Path

import exact_skeletal_rig_patch as patch
import skeletal_tail_patch


def _column_to_rows(values):
    return [[float(values[column * 4 + row]) for column in range(4)] for row in range(4)]


def _mul(a, b):
    return [
        [sum(a[row][k] * b[k][column] for k in range(4)) for column in range(4)]
        for row in range(4)
    ]


def _write_test_glb(path):
    gltf = {
        "asset": {"version": "2.0"},
        "nodes": [{"name": "root"}, {"name": "child"}],
        "skins": [{"joints": [0, 1], "inverseBindMatrices": 0}],
        "accessors": [
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": 5126,
                "count": 2,
                "type": "MAT4",
            }
        ],
        "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": 128}],
        "buffers": [{"byteLength": 128}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
    }
    json_blob = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    while len(json_blob) % 4:
        json_blob += b" "
    binary = bytes(128)
    out = bytearray(
        struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(json_blob) + 8 + len(binary))
    )
    out.extend(struct.pack("<I4s", len(json_blob), b"JSON"))
    out.extend(json_blob)
    out.extend(struct.pack("<I4s", len(binary), b"BIN\x00"))
    out.extend(binary)
    Path(path).write_bytes(out)


class ExactSkeletalRigTests(unittest.TestCase):
    def test_exact_globals_and_inverse_binds_are_written(self):
        root = [
            0.0, -1.0, 0.0, 1.0,
            1.0, 0.0, 0.0, 2.0,
            0.0, 0.0, 1.0, 3.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        child = [
            0.0, 0.0, 1.0, 4.0,
            0.0, 1.0, 0.0, 5.0,
            -1.0, 0.0, 0.0, 6.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        root_rows = patch._matrix4(root, "root")
        child_rows = patch._matrix4(child, "child")
        bones = [
            {
                "parent_index": -1,
                "global_matrix": root,
                "inverse_bind_matrix": [
                    value for row in patch._inverse_affine(root_rows) for value in row
                ],
            },
            {
                "parent_index": 0,
                "global_matrix": child,
                "inverse_bind_matrix": [
                    value for row in patch._inverse_affine(child_rows) for value in row
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.glb"
            _write_test_glb(path)
            self.assertTrue(patch.patch_glb_bind_pose(path, bones))
            chunks = skeletal_tail_patch._read_glb(path)
            gltf = json.loads(bytes(chunks[0][1]).decode("utf-8"))
            root_local = _column_to_rows(gltf["nodes"][0]["matrix"])
            child_local = _column_to_rows(gltf["nodes"][1]["matrix"])
            child_global = _mul(root_local, child_local)
            for got, expected in zip(root_local, root_rows):
                self.assertEqual(got, expected)
            for got, expected in zip(child_global, child_rows):
                self.assertAlmostEqual(
                    max(abs(a - b) for a, b in zip(got, expected)), 0.0, places=12
                )
            self.assertTrue(gltf["asset"]["extras"]["pakpy_exact_skel_rig"])

    def test_blend_generation_does_not_edit_bones(self):
        script = patch.exact_blend_script("rig.glb", "rig.blend")
        self.assertNotIn("mode_set(mode='EDIT')", script)
        self.assertNotIn("bone.head=parent.tail", script)
        self.assertNotIn("bone.use_connect=True", script)
        self.assertIn("pakpy_exact_skel_rig", script)


if __name__ == "__main__":
    unittest.main()
