import tempfile
import unittest
from pathlib import Path

import numpy as np

from anim_capture_fit import fit_clip, read_capture_csv, sample_frames


class CaptureFitTests(unittest.TestCase):
    def test_subframe_cyclic_fit(self):
        frames = np.zeros((5, 2, 3, 4), dtype=np.float64)
        for frame in range(4):
            frames[frame, :, 0, 0] = frame
            frames[frame, :, 1, 1] = frame * frame
        frames[4] = frames[0]
        times = 2.5 + np.arange(9) * 0.5
        captures = sample_frames(frames, times, 4.0)
        result = fit_clip(
            captures,
            'synthetic',
            'synthetic.json',
            frames,
            step_min=0.25,
            step_max=0.75,
            coarse_step=0.05,
            fine_step=0.005,
        )
        self.assertAlmostEqual(result.offset, 2.5, places=2)
        self.assertAlmostEqual(result.step, 0.5, places=2)
        self.assertLess(result.motion_rmse, 1e-10)

    def test_renderdoc_csv_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '1.csv'
            lines = ['Name,Value,Byte Offset,Type', '_child0,,0,float4[4096]']
            for index in range(6):
                lines.append(f'_child0[{index}],"{index}, {index+1}, {index+2}, {index+3}",{index*16},float4')
            path.write_text('\n'.join(lines), encoding='utf-8')
            result = read_capture_csv(path, bone_count=2)
            self.assertEqual(result.shape, (2, 3, 4))
            self.assertEqual(float(result[1, 2, 3]), 8.0)


if __name__ == '__main__':
    unittest.main()
