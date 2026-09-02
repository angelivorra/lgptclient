#!/usr/bin/env python3
"""TranceGateFx: puerta rítmica sincronizada al tempo (preset "trance_gate").

Ejecutar con: .venv/bin/python -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_TESTS))

from lgpt_engine import EFFECT_PRESETS, TranceGateFx  # noqa: E402
from test_engine import make_engine  # noqa: E402

SR = 44100


class TestTranceGateFx(unittest.TestCase):
    def test_registrado_en_effect_presets(self):
        self.assertIs(EFFECT_PRESETS["trance_gate"], TranceGateFx)
        self.assertTrue(getattr(TranceGateFx, "after_presence", False))

    def test_amount_cero_no_toca_el_buffer(self):
        fx = TranceGateFx(SR)
        fx.set_tempo(120.0)
        buf = np.full((512, 2), 0.5, dtype=np.float32)
        fx.apply(buf, 0.0)
        np.testing.assert_array_equal(buf, 0.5)

    def test_set_tempo_fija_la_frecuencia_de_semicorchea(self):
        fx = TranceGateFx(SR)
        fx.set_tempo(120.0)
        # 120 BPM -> 2 negras/seg -> 8 semicorcheas/seg
        self.assertAlmostEqual(fx._freq, 8.0)
        fx.set_tempo(150.0)
        self.assertAlmostEqual(fx._freq, 10.0)

    def test_amount_maximo_silencia_el_valle_del_ciclo(self):
        fx = TranceGateFx(SR)
        fx.set_tempo(120.0)  # freq=8 Hz -> medio ciclo = 0.0625 s
        medio_ciclo = int(round(SR / fx._freq / 2))
        fx.apply(np.ones((medio_ciclo, 2), dtype=np.float32), 1.0)
        # tras medio ciclo la fase acumulada esta en el valle (coseno=-1)
        buf = np.ones((1, 2), dtype=np.float32)
        fx.apply(buf, 1.0)
        self.assertAlmostEqual(buf[0, 0], 0.0, places=3)

    def test_amount_maximo_deja_pasar_el_pico_del_ciclo(self):
        fx = TranceGateFx(SR)
        fx.set_tempo(120.0)
        buf = np.ones((1, 2), dtype=np.float32)
        fx.apply(buf, 1.0)   # fase 0 = pico del coseno -> sin atenuar
        self.assertAlmostEqual(buf[0, 0], 1.0, places=3)

    def test_cambio_de_tempo_en_vivo_no_salta_la_fase(self):
        fx = TranceGateFx(SR)
        fx.set_tempo(120.0)
        buf1 = np.ones((100, 2), dtype=np.float32)
        fx.apply(buf1, 1.0)
        fase_antes = fx._phase
        fx.set_tempo(140.0)   # solo cambia la frecuencia, no debe resetear _phase
        self.assertEqual(fx._phase, fase_antes)

    def test_presence_no_aplana_el_gate(self):
        """Presence ON + FX de tono no debe cancelar el contraste del gate."""
        import lgpt_engine

        class ToneFx:
            def __init__(self, sr):
                pass

            def apply(self, buf, amount):
                buf *= 0.5

        engine = make_engine()
        engine.tempo = 120.0
        engine.master_chain = None
        engine.channels[0].fx_amounts["tone"] = 1.0
        engine.channels[0].fx_amounts["trance_gate"] = 1.0
        engine.channels[0].fx_presence = True

        def _const_ch0(_ch, block):
            if _ch.idx == 0:
                return np.full_like(block, 0.5)
            return np.zeros_like(block)

        engine._delay_channel = _const_ch0

        original = dict(lgpt_engine.EFFECT_PRESETS)
        lgpt_engine.EFFECT_PRESETS.clear()
        lgpt_engine.EFFECT_PRESETS["tone"] = ToneFx
        lgpt_engine.EFFECT_PRESETS["trance_gate"] = TranceGateFx
        try:
            chunks = [engine.render(512) for _ in range(48)]
        finally:
            lgpt_engine.EFFECT_PRESETS.clear()
            lgpt_engine.EFFECT_PRESETS.update(original)
        out = np.concatenate(chunks, axis=0)[:, 0]
        win = 256
        rms = [float(np.sqrt((out[i:i + win] ** 2).mean()))
               for i in range(0, len(out) - win, win)]
        contrast = max(rms) / (min(rms) + 1e-9)
        self.assertGreater(contrast, 3.0, contrast)


if __name__ == "__main__":
    unittest.main()
