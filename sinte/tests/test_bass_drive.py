#!/usr/bin/env python3
"""BassDriveFx: saturación + LPF que conserva el grave (preset bass_drive).

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

    def test_menos_agudos_que_un_bitcrush_equivalente(self):
        """Valve (Decimator) llena 800-8k; bass_drive no tanto.

        Si LADSPA no está, se compara contra un bitcrush numpy (mismo
        síntoma: energía aguda alta sobre un seno de 80 Hz)."""
        src = _sine(80)
        bass = src.copy()
        BassDriveFx(SR).apply(bass, 1.0)
        bass_hf = _band_energy(bass, 800, 8000)

        crushed = src.copy()
        try:
            from lgpt_engine import ValveFx
            ValveFx(SR).apply(crushed, 1.0)
        except Exception:
            bits = 4
            step = 2.0 / (2 ** bits)
            crushed[:] = np.round(crushed / step) * step
        crush_hf = _band_energy(crushed, 800, 8000)
        self.assertLess(bass_hf, crush_hf * 0.6)


if __name__ == "__main__":
    unittest.main()
