#!/usr/bin/env python3
"""GLCH: glitch/stutter con intensidad y duración en filas."""
import sys
import unittest
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_TESTS))

from lgpt_engine import (  # noqa: E402
    ChannelGlitch,
    glch_pack,
    glch_unpack,
    TICKS_PER_STEP,
)
from test_engine import make_engine, note_row  # noqa: E402

SR = 44100


class TestGlchPack(unittest.TestCase):
    def test_pack_unpack(self):
        self.assertEqual(glch_unpack(glch_pack(0x80, 2)), (0x80, 2))
        self.assertEqual(glch_unpack(glch_pack(0, 0)), (0, 1))
        self.assertEqual(glch_unpack(glch_pack(300, 99)), (300 & 0xFF, 16))


class TestChannelGlitch(unittest.TestCase):
    def test_amount_cero_no_cambia(self):
        fx = ChannelGlitch(SR)
        fx.trigger(0.0, 8, 120.0)
        buf = np.full((256, 2), 0.5, dtype=np.float32)
        fx.apply(buf)
        np.testing.assert_array_equal(buf, 0.5)

    def test_repite_el_trozo(self):
        fx = ChannelGlitch(SR)
        fx.trigger(1.0, 64, 120.0)
        fx._rng.random = lambda: 1.0          # sin dropout ni revés
        n = fx._slice_n
        src = np.zeros((n + n, 2), dtype=np.float32)
        src[:n, :] = np.linspace(0.1, 0.9, n, dtype=np.float32)[:, None]
        src[n:, :] = 0.0
        fx.apply(src)
        # Tras capturar, el segundo trozo debe parecerse al primero
        # (ventana en los bordes: comparamos el centro).
        mid = slice(n // 4, n - n // 4)
        self.assertGreater(
            float(np.corrcoef(src[mid, 0], src[n:][mid, 0])[0, 1]), 0.85)

    def test_para_tras_los_ticks(self):
        fx = ChannelGlitch(SR)
        fx.trigger(1.0, 2, 120.0)
        fx.apply(np.ones((64, 2), dtype=np.float32))
        self.assertTrue(fx.active)
        fx.tick()
        fx.tick()
        self.assertEqual(fx.ticks_left, 0)
        # el release sigue un momento y luego se apaga
        for _ in range(32):
            fx.apply(np.ones((64, 2), dtype=np.float32))
            if not fx.active:
                break
        self.assertFalse(fx.active)


class TestGlchEngine(unittest.TestCase):
    def test_no_es_unsupported(self):
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "GLCH"
        engine.project.param1[0] = glch_pack(0x80, 2)
        engine._process_tick()
        self.assertNotIn("GLCH", engine.unsupported_cmds)
        self.assertIsNotNone(engine.channels[0].glitch)
        self.assertTrue(engine.channels[0].glitch.active)

    def test_dura_las_filas(self):
        engine = make_engine("120")
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "GLCH"
        engine.project.param1[0] = glch_pack(0xC0, 1)
        engine._process_tick()
        gl = engine.channels[0].glitch
        self.assertGreater(gl.ticks_left, 0)
        start = gl.ticks_left
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        self.assertLess(gl.ticks_left, start)

    def test_render_rompe_el_seno(self):
        engine = make_engine("120")
        engine.master_chain = None
        note_row(engine.project, 0, note=60)
        dry = np.concatenate([engine.render(512) for _ in range(8)], axis=0)
        engine = make_engine("120")
        engine.master_chain = None
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "GLCH"
        engine.project.param1[0] = glch_pack(0xFF, 4)
        wet = np.concatenate([engine.render(512) for _ in range(8)], axis=0)
        self.assertGreater(float(np.mean(np.abs(wet - dry))), 1e-4)


if __name__ == "__main__":
    unittest.main()
