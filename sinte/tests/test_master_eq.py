#!/usr/bin/env python3
"""EQ gráfico de 7 bandas (nativo, por canción)."""

import sys
import unittest
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from master_eq import (  # noqa: E402
    EQ_BANDS, GraphicEQ, eq_to_cfg, parse_eq,
)
from midi_control import apply_song_config  # noqa: E402
from test_engine import make_engine  # noqa: E402


class TestParseEq(unittest.TestCase):
    def test_missing_is_flat(self):
        self.assertEqual(parse_eq(None), [0.0] * EQ_BANDS)
        self.assertEqual(parse_eq("no"), [0.0] * EQ_BANDS)

    def test_pads_and_clamps(self):
        g = parse_eq([3, -20, 1])
        self.assertEqual(len(g), EQ_BANDS)
        self.assertEqual(g[0], 3.0)
        self.assertEqual(g[1], -12.0)
        self.assertEqual(g[2], 1.0)
        self.assertTrue(all(x == 0.0 for x in g[3:]))

    def test_cfg_omits_flat(self):
        self.assertIsNone(eq_to_cfg([0, 0, 0, 0, 0, 0, 0]))
        self.assertEqual(eq_to_cfg([1.24, 0, 0, 0, 0, 0, 0])[0], 1.2)


class TestGraphicEQ(unittest.TestCase):
    def test_flat_is_noop(self):
        eq = GraphicEQ(44100)
        x = np.random.randn(256, 2).astype(np.float32) * 0.1
        before = x.copy()
        eq.apply(x)
        np.testing.assert_array_equal(x, before)

    def test_bass_boost_raises_low_band(self):
        sr = 44100
        eq = GraphicEQ(sr)
        eq.set_gains([12, 0, 0, 0, 0, 0, 0])
        t = np.arange(2048) / sr
        low = (0.2 * np.sin(2 * np.pi * 60 * t)).astype(np.float32)
        high = (0.2 * np.sin(2 * np.pi * 8000 * t)).astype(np.float32)
        buf_lo = np.stack([low, low], axis=1)
        buf_hi = np.stack([high, high], axis=1)
        peak_lo = float(np.abs(buf_lo).max())
        peak_hi = float(np.abs(buf_hi).max())
        eq.apply(buf_lo)
        eq2 = GraphicEQ(sr)
        eq2.set_gains([12, 0, 0, 0, 0, 0, 0])
        eq2.apply(buf_hi)
        self.assertGreater(float(np.abs(buf_lo).max()), peak_lo * 1.5)
        self.assertLess(float(np.abs(buf_hi).max()), peak_hi * 1.4)


class TestApplySongConfigEq(unittest.TestCase):
    def test_applies_to_engine(self):
        engine = make_engine()
        apply_song_config(engine, {"eq": [4, 0, 0, -2, 0, 0, 1]}, 60)
        self.assertEqual(engine.master_eq.gains[0], 4.0)
        self.assertEqual(engine.master_eq.gains[3], -2.0)
        self.assertTrue(engine.master_eq.active)

    def test_missing_eq_is_flat(self):
        engine = make_engine()
        engine.master_eq.set_gains([6, 0, 0, 0, 0, 0, 0])
        apply_song_config(engine, {}, 60)
        self.assertEqual(engine.master_eq.gains, [0.0] * EQ_BANDS)
        self.assertFalse(engine.master_eq.active)

    def test_render_runs(self):
        engine = make_engine()
        engine.master_eq.set_gains([3, 0, 0, 0, 0, 0, 0])
        out = engine.render(128)
        self.assertEqual(out.shape, (128, 2))
        self.assertFalse(np.isnan(out).any())


if __name__ == "__main__":
    unittest.main()
