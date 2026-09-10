#!/usr/bin/env python3
"""Tests headless del motor de escenas (sin framebuffer)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import FRAME_BYTES, HEIGHT, WIDTH, SceneEngine, rgb888_to_rgb565  # noqa: E402


class TestScenes(unittest.TestCase):
    def test_frame_rgb565_tamano(self):
        eng = SceneEngine(invert=False)
        eng.set_scene("live")
        frame = eng.render()
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame), FRAME_BYTES)

    def test_sin_escena_no_pinta(self):
        eng = SceneEngine()
        self.assertIsNone(eng.render())

    def test_golpe_llena_el_frame(self):
        eng = SceneEngine(invert=False)
        eng.set_scene("live")
        eng.set_bpm(140)
        eng.pulse("kick", 127)
        frame = eng.render()
        self.assertEqual(len(frame), FRAME_BYTES)
        self.assertGreater(sum(frame[:2000]), 0)

    def test_invert_cambia_el_frame(self):
        a = SceneEngine(invert=False)
        b = SceneEngine(invert=True)
        a.set_scene("live")
        b.set_scene("live")
        a.pulse("kick", 127)
        b.pulse("kick", 127)
        fa, fb = a.render(), b.render()
        self.assertEqual(len(fa), len(fb))
        self.assertNotEqual(fa, fb)

    def test_rgb565_roundtrip_shape(self):
        import numpy as np
        rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        rgb[0, 0] = (255, 0, 0)
        data = rgb888_to_rgb565(rgb)
        self.assertEqual(len(data), FRAME_BYTES)
        pix = int.from_bytes(data[0:2], "little")
        self.assertEqual(pix, (31 << 11))  # R=31 en RGB565


if __name__ == "__main__":
    unittest.main()
