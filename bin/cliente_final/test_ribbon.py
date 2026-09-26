#!/usr/bin/env python3
"""Historial de la línea del fondo: solo avanza, el pasado no se recalcula."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ribbon import (  # noqa: E402
    BAND_CENTER, HEIGHT, WIDTH, FondoRibbon, overlay_block_cols,
)
from scenes import FRAME_BYTES  # noqa: E402


class TestFondoRibbon(unittest.TestCase):
    def test_kick_sube_el_reactor(self):
        r = FondoRibbon()
        r.pulse("kick", 127)
        self.assertGreater(r.env["kick"], 0.9)

    def test_kind_nuevo_se_acepta(self):
        r = FondoRibbon()
        r.pulse("button", 80)
        self.assertIn("button", r.env)
        self.assertGreater(r.env["button"], 0.0)

    def test_el_pasado_no_cambia_al_entrar_columnas(self):
        r = FondoRibbon()
        r.offset[:] = np.arange(WIDTH, dtype=np.float32)
        r._last = 10.0
        r._scroll_acc = 5.0  # 5 columnas de golpe
        r.bpm = 120.0
        wrote = r.step(10.0 + 5.0 / r.speed_px_s + 0.001)
        self.assertGreaterEqual(wrote, 4)
        # Lo que había a la izquierda se ha desplazado a la derecha, intacto.
        self.assertTrue(np.allclose(r.offset[wrote:],
                                    np.arange(WIDTH - wrote, dtype=np.float32)))

    def test_blit_solo_toca_la_franja(self):
        r = FondoRibbon()
        r.pulse("kick", 127)
        r._last = 1.0
        r.step(1.05)
        frame = np.zeros((HEIGHT, WIDTH), dtype="<u2")
        frame[10, 10] = 0xFFFF
        out = np.frombuffer(
            r.blit_rgb565(frame.tobytes(), 1.10), dtype="<u2"
        ).reshape(HEIGHT, WIDTH)
        self.assertEqual(int(out[10, 10]), 0xFFFF)
        band = out[BAND_CENTER - 20: BAND_CENTER + 20, :]
        self.assertGreater(int(band.max()), 0)

    def test_el_evento_aparece_a_la_izquierda(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("kick", 127)
        figs = r.snapshot_figures(1.0)
        self.assertEqual(len(figs), 1)
        self.assertEqual(figs[0]["shape"], "square")
        self.assertLess(figs[0]["x"], 1.0)
        self.assertEqual(figs[0]["fill"], (0, 0, 0))

    def test_el_cuadrado_crece(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("kick", 127)
        a = r.snapshot_figures(1.0)[0]["side"]
        b = r.snapshot_figures(1.12)[0]["side"]
        self.assertGreater(b, a)

    def test_el_evento_viaja_a_la_derecha(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("kick", 127)
        t = 1.0
        for _ in range(12):
            t += 0.05
            r.step(t)
        self.assertGreater(r.snapshot_figures(t)[0]["x"], 20)

    def test_el_cuadrado_negro_aparta_la_linea(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("kick", 127)
        t = 1.0
        for _ in range(8):
            t += 0.05
            r.step(t)
        fig = r.snapshot_figures(t)[0]
        self.assertGreater(fig["side"], 16)
        frame = np.full((HEIGHT, WIDTH), 0x07E0, dtype="<u2")  # verde
        out = np.frombuffer(
            r.blit_rgb565(frame.tobytes(), t), dtype="<u2"
        ).reshape(HEIGHT, WIDTH)
        cx = int(round(fig["x"]))
        cy = int(round(fig["y"]))
        self.assertEqual(int(out[cy, cx]), 0)

    def test_cajas_son_circulos_de_color_distinto(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("snare1", 127)
        r.pulse("snare2", 127)
        figs = r.snapshot_figures(1.0)
        self.assertEqual([f["shape"] for f in figs], ["circle", "circle"])
        self.assertNotEqual(figs[0]["outline"], figs[1]["outline"])
        self.assertEqual(figs[0]["kind"], "snare1")
        self.assertEqual(figs[1]["kind"], "snare2")

    def test_el_circulo_no_pinta_las_esquinas_del_bbox(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("snare1", 127)
        t = 1.0
        for _ in range(8):
            t += 0.05
            r.step(t)
        fig = r.snapshot_figures(t)[0]
        self.assertGreater(fig["side"], 12)
        frame = np.full((HEIGHT, WIDTH), 0x07E0, dtype="<u2")
        out = np.frombuffer(
            r.blit_rgb565(frame.tobytes(), t), dtype="<u2"
        ).reshape(HEIGHT, WIDTH)
        cx = int(round(fig["x"]))
        cy = int(round(fig["y"]))
        self.assertEqual(int(out[cy, cx]), 0)
        half = fig["side"] / 2.0
        px = min(WIDTH - 1, int(round(fig["x"] + half)))
        py = min(HEIGHT - 1, int(round(fig["y"] + half)))
        self.assertEqual(int(out[py, px]), 0x07E0)

    def test_bpm_cambia_la_velocidad(self):
        r = FondoRibbon()
        r.set_bpm(120)
        slow = r.speed_px_s
        r.set_bpm(180)
        self.assertGreater(r.speed_px_s, slow)

    def test_el_knob_acelera_como_el_fondo(self):
        """+12 % de tempo → ~2.5× de avance, la misma curva que el slideshow."""
        from ribbon import BPM_CURVE
        r = FondoRibbon()
        r.reset_tempo_base()
        r.set_bpm(125)
        quieto = r.speed_px_s
        r.set_bpm(125 * 1.12)
        self.assertAlmostEqual(r.speed_px_s / quieto, 1.12 ** BPM_CURVE, places=2)

    def test_al_tempo_de_la_cancion_sigue_lineal(self):
        r = FondoRibbon()
        r.reset_tempo_base()
        r.set_bpm(120)
        self.assertAlmostEqual(r.speed_px_s, 130.0, places=2)
        r.reset_tempo_base()
        r.set_bpm(180)
        self.assertAlmostEqual(r.speed_px_s, 130.0 * 180 / 120, places=2)

    def test_pulso_en_el_golpe_del_tempo(self):
        r = FondoRibbon()
        r.bpm = 120.0
        r._beat_t0 = 10.0
        self.assertGreater(r.beat_pulse(10.0), 0.9)
        self.assertLess(r.beat_pulse(10.25), 0.3)

    def test_mas_bpm_mas_pulsos(self):
        r = FondoRibbon()
        r.bpm = 60.0
        r._beat_t0 = 0.0
        valle = r.beat_pulse(0.5)
        r.bpm = 240.0
        r._beat_t0 = 0.0
        golpe = r.beat_pulse(0.5)
        self.assertLess(valle, 0.3)
        self.assertGreater(golpe, 0.9)

    def test_el_overlay_tapa_la_linea(self):
        r = FondoRibbon()
        r._last = 1.0
        r.pulse("kick", 127)
        t = 1.0
        for _ in range(8):
            t += 0.05
            r.step(t)
        fig = r.snapshot_figures(t)[0]
        overlay = np.zeros((HEIGHT, WIDTH), dtype="<u2")
        overlay[:, 100:700] = 0xFFFF
        block = overlay_block_cols(overlay.tobytes())
        self.assertTrue(block[400])
        self.assertFalse(block[20])
        frame = np.full((HEIGHT, WIDTH), 0x07E0, dtype="<u2")
        out = np.frombuffer(
            r.blit_rgb565(frame.tobytes(), t, block_cols=block), dtype="<u2"
        ).reshape(HEIGHT, WIDTH)
        cx = min(WIDTH - 1, max(0, int(round(fig["x"]))))
        cy = int(round(fig["y"]))
        if block[cx]:
            self.assertEqual(int(out[cy, cx]), 0x07E0)

    def test_recorte_solo_tapa_sus_columnas(self):
        fw, fh = 4, 4
        overlay = np.full((fh, fw), 0xFFFF, dtype="<u2")
        block = overlay_block_cols(
            overlay.tobytes(), ox=100, oy=BAND_CENTER - 2, fw=fw, fh=fh)
        self.assertTrue(block[101])
        self.assertFalse(block[50])
        self.assertFalse(block[200])

    def test_el_hueco_entre_ojos_no_se_tapa(self):
        overlay = np.zeros((HEIGHT, WIDTH), dtype="<u2")
        overlay[BAND_CENTER - 20: BAND_CENTER + 20, 180:280] = 0xFFFF
        overlay[BAND_CENTER - 20: BAND_CENTER + 20, 520:620] = 0xFFFF
        block = overlay_block_cols(overlay.tobytes())
        self.assertTrue(block[230])
        self.assertTrue(block[570])
        self.assertFalse(block[400])

    def test_la_onda_reescribe_el_path_sin_tocar_el_reposo(self):
        r = FondoRibbon()
        r.bpm = 120.0
        r._beat_t0 = 1.0
        r._last = 1.0
        r.offset[:] = 0
        a = r.path_ys(1.0).copy()
        b = r.path_ys(1.10).copy()
        self.assertFalse(np.allclose(a, b))
        self.assertTrue(np.allclose(r.offset, 0))
        self.assertGreater(float(np.ptp(r.path_ys(1.0))),
                           float(np.ptp(r.path_ys(1.25))))

    def test_cambiar_bpm_no_salta_la_fase(self):
        r = FondoRibbon()
        r.bpm = 120.0
        r._beat_t0 = 5.0
        r._last = 5.25
        antes = r.beat_pulse(5.25)
        r.set_bpm(180)
        self.assertAlmostEqual(r.beat_pulse(5.25), antes, places=2)


if __name__ == "__main__":
    unittest.main()
