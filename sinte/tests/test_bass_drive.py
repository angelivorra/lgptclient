#!/usr/bin/env python3
"""BassDriveFx: pointer-cast paralelo (receta corte4000 mix55 rms110).

Ejecutar con: .venv/bin/python -m unittest discover -s tests -v
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgpt_engine import BassDriveFx, EFFECT_PRESETS, SAMPLE_RATE  # noqa: E402

SR = SAMPLE_RATE
N = 8192


def _sine(freq, n=N, sr=SR):
    t = np.arange(n) / sr
    x = 0.5 * np.sin(2.0 * math.pi * freq * t)
    return np.column_stack([x, x]).astype(np.float32)


def _band_energy(buf, lo, hi, sr=SR):
    spec = np.abs(np.fft.rfft(buf[:, 0] * np.hanning(len(buf))))
    freqs = np.fft.rfftfreq(len(buf), 1.0 / sr)
    mask = (freqs >= lo) & (freqs < hi)
    return float((spec[mask] ** 2).sum())


def _plugin_disponible():
    try:
        BassDriveFx(SR)
        return True
    except Exception:
        return False


@unittest.skipUnless(_plugin_disponible(), "pointer_cast_1910.so no instalado")
class TestBassDriveFx(unittest.TestCase):
    def test_registrado_en_effect_presets(self):
        self.assertIs(EFFECT_PRESETS["bass_drive"], BassDriveFx)
        names = list(EFFECT_PRESETS)
        self.assertLess(names.index("valve"), names.index("bass_drive"))
        self.assertLess(names.index("bass_drive"), names.index("acid"))

    def test_amount_cero_no_toca_el_buffer(self):
        fx = BassDriveFx(SR)
        buf = _sine(80)
        before = buf.copy()
        fx.apply(buf, 0.0)
        np.testing.assert_array_equal(buf, before)

    def test_el_grave_sigue_dominando(self):
        fx = BassDriveFx(SR)
        buf = _sine(80)
        fx.apply(buf, 1.0)
        low = _band_energy(buf, 40, 250)
        high = _band_energy(buf, 800, 8000)
        self.assertGreater(low, high * 3.0)

    def test_rms_cerca_del_seco(self):
        dry = _sine(80)
        wet = dry.copy()
        BassDriveFx(SR).apply(wet, 1.0)
        r_dry = float(np.sqrt((dry ** 2).mean()))
        r_wet = float(np.sqrt((wet ** 2).mean()))
        self.assertGreater(r_wet / r_dry, 0.9)
        self.assertLess(r_wet / r_dry, 1.4)

    def test_sigue_correlacionado_con_el_seco(self):
        """Mix 55 %: no sustituye el bajo, se oye el original debajo."""
        dry = _sine(80)[:, 0]
        wet = np.column_stack([dry, dry]).astype(np.float32)
        BassDriveFx(SR).apply(wet, 1.0)
        corr = float(np.corrcoef(dry, wet[:, 0])[0, 1])
        self.assertGreater(corr, 0.5)


if __name__ == "__main__":
    unittest.main()
