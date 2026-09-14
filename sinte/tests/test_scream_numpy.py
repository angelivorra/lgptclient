#!/usr/bin/env python3
"""El scream numpy tiene que salir igual que Voice._render_filter."""

import os
import sys
import unittest
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE.parent))

import scream_numpy  # noqa: E402
from lgpt_engine import InstrumentDef, Sample, Voice  # noqa: E402

# float32 roundtrip del buffer; el lazo va en float64 como el original.
_ATOL = 2e-6


def _voice(n_ch=1, cut=111, res=80, mix=255, scream=True):
    data = np.zeros((32, n_ch), dtype=np.float32)
    sample = Sample(data, 44100)
    idef = InstrumentDef(
        index=0,
        sample_name="x.wav",
        cutoff=cut,
        reso=res,
        filter_mix=mix,
        filter_mode="scream" if scream else "original",
        filter_scream=scream,
    )
    return Voice(sample, idef, 60, 0, 44100, 100.0)


def _noise(n, ch, seed):
    rng = np.random.default_rng(seed)
    return (rng.standard_normal((n, ch)) * 0.4).astype(np.float32)


def _run_both(x, *, cut, res, mix, scream=True):
    """Copia del bloque: _render_filter vs scream_numpy.filter_block."""
    v = _voice(n_ch=x.shape[1], cut=cut, res=res, mix=mix, scream=scream)
    old = x.copy()
    v._render_filter(old)
    new, sp, hg, dl = scream_numpy.filter_block(
        x, cut=cut / 255.0, reso_base=res / 255.0, mix=mix / 255.0,
        scream=scream,
    )
    return old, new, v, (sp, hg, dl)


class TestScreamNumpy(unittest.TestCase):
    def test_numba_o_python(self):
        self.assertIn(scream_numpy._loop_impl, ("numba", "python"))

    def test_acordeon_bulebule(self):
        # accordion.wav: cut 111, res 0, type 255, scream.
        x = _noise(2048, 1, 1)
        old, new, _, _ = _run_both(x, cut=111, res=0, mix=255)
        np.testing.assert_allclose(new, old, atol=_ATOL, rtol=0)

    def test_res_alta_knobs_a_tope(self):
        # El caso que disparaba el lazo: res 80 + scream.
        x = _noise(2048, 1, 2)
        old, new, _, _ = _run_both(x, cut=111, res=80, mix=255)
        np.testing.assert_allclose(new, old, atol=_ATOL, rtol=0)

    def test_cut_mix_res_varios(self):
        x = _noise(512, 1, 3)
        for cut, res, mix in (
            (0, 0, 0),
            (40, 0, 0),
            (95, 0, 255),
            (128, 40, 128),
            (200, 200, 255),
            (255, 255, 0),
        ):
            old, new, _, _ = _run_both(x, cut=cut, res=res, mix=mix)
            np.testing.assert_allclose(
                new, old, atol=_ATOL, rtol=0,
                err_msg=f"cut={cut} res={res} mix={mix}",
            )

    def test_estereo_y_estado_entre_bloques(self):
        a = _noise(300, 2, 4)
        b = _noise(300, 2, 5)
        v = _voice(n_ch=2, cut=95, res=64, mix=255)
        old_a, old_b = a.copy(), b.copy()
        v._render_filter(old_a)
        v._render_filter(old_b)

        new_a, sp, hg, dl = scream_numpy.filter_block(
            a, cut=95 / 255.0, reso_base=64 / 255.0, mix=1.0, scream=True,
        )
        new_b, _, _, _ = scream_numpy.filter_block(
            b, cut=95 / 255.0, reso_base=64 / 255.0, mix=1.0, scream=True,
            speed=sp, height=hg, delay=dl,
        )
        np.testing.assert_allclose(new_a, old_a, atol=_ATOL, rtol=0)
        np.testing.assert_allclose(new_b, old_b, atol=_ATOL, rtol=0)
        self.assertEqual(len(v.f_speed), 2)

    def test_apply_escribe_el_estado_de_la_voz(self):
        x = _noise(256, 1, 6)
        v_old = _voice(cut=128, res=90, mix=200)
        v_new = _voice(cut=128, res=90, mix=200)
        old = x.copy()
        new = x.copy()
        v_old._render_filter(old)
        scream_numpy.apply(new, v_new)
        np.testing.assert_allclose(new, old, atol=_ATOL, rtol=0)
        np.testing.assert_allclose(v_new.f_speed, v_old.f_speed, atol=1e-9)
        np.testing.assert_allclose(v_new.f_height, v_old.f_height, atol=1e-9)
        np.testing.assert_allclose(v_new.f_delay, v_old.f_delay, atol=1e-9)

    def test_engine_scream_on_off_misma_mezcla(self):
        from test_engine import SAMPLE_RATE, make_engine, note_row

        prev = os.environ.get("SCREAM_NUMPY")

        def _render(use_numpy):
            os.environ["SCREAM_NUMPY"] = "1" if use_numpy else "0"
            engine = make_engine()
            t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
            data = (0.4 * np.sin(2 * np.pi * 220 * t))[:, None]
            engine.bank.samples["test.wav"] = Sample(
                data.astype(np.float32), SAMPLE_RATE)
            params = engine.project.instrument_bank[0]["params"]
            params["filter mode"] = "scream"
            params["filter cut"] = "111"
            params["filter res"] = "80"
            params["filter type"] = "255"
            note_row(engine.project, 0)
            engine._process_tick()
            return engine.render(4096)

        try:
            a = _render(False)
            b = _render(True)
        finally:
            if prev is None:
                os.environ.pop("SCREAM_NUMPY", None)
            else:
                os.environ["SCREAM_NUMPY"] = prev
        np.testing.assert_allclose(b, a, atol=3e-6, rtol=0)


if __name__ == "__main__":
    unittest.main()
