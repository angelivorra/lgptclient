#!/usr/bin/env python3
"""Chispazo: croma, teñido, dentro de la pantalla, y no es un overlay de 2 s."""
import random
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lyric_render import TEMAS_ROBOT  # noqa: E402
from scenes import FRAME_BYTES, HEIGHT, WIDTH  # noqa: E402
from spark_hit import (  # noqa: E402
    NEON_COLORS, SPARK_CC, SPARK_VALUE, SparkHit, key_alpha, load_alpha,
)


class TestKey(unittest.TestCase):
    def test_verde_es_transparente(self):
        rgb = np.zeros((4, 4, 3), dtype=np.uint8)
        rgb[:] = (2, 162, 0)
        self.assertEqual(int(key_alpha(rgb).max()), 0)

    def test_el_halo_verde_no_entra(self):
        rgb = np.zeros((2, 2, 3), dtype=np.uint8)
        rgb[0, 0] = (20, 255, 0)
        self.assertEqual(int(key_alpha(rgb)[0, 0]), 0)

    def test_amarillo_queda_opaco(self):
        rgb = np.zeros((2, 2, 3), dtype=np.uint8)
        rgb[0, 0] = (255, 220, 40)
        self.assertEqual(int(key_alpha(rgb)[0, 0]), 255)

    def test_paleta_es_la_de_las_letras(self):
        self.assertEqual(NEON_COLORS, TEMAS_ROBOT)


class TestSprite(unittest.TestCase):
    def test_el_asset_nace_y_se_apaga(self):
        alpha = load_alpha()
        self.assertGreaterEqual(alpha.shape[0], 8)
        self.assertLessEqual(max(alpha.shape[1:]), 240)
        sums = alpha.reshape(alpha.shape[0], -1).sum(axis=1)
        self.assertGreater(int(sums.max()), int(sums[0]))
        self.assertGreater(int(sums.max()), int(sums[-1]) * 4)

    def test_cabe_entero_en_la_pantalla(self):
        hit = SparkHit()
        rng = random.Random(1)
        h, w = hit.size
        for _ in range(40):
            self.assertTrue(hit.trigger(now=0.0, rng=rng))
            x, y, color = hit.places()[-1]
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x + w, WIDTH)
            self.assertLessEqual(y + h, HEIGHT)
            self.assertIn(color, NEON_COLORS)

    def test_tine_y_no_pinta_fuera(self):
        alpha = np.zeros((2, 10, 10), dtype=np.uint8)
        alpha[0, 5, 5] = 255
        hit = SparkHit(alpha)
        hit.trigger(now=0.0, rng=random.Random(0))
        x, y, color = hit.places()[-1]
        black = b"\x00\x00" * (WIDTH * HEIGHT)
        out = hit.blit_rgb565(black, now=0.0)
        arr = np.frombuffer(out, dtype="<u2").reshape(HEIGHT, WIDTH).copy()
        cr, cg, cb = color
        packed = (
            (int(cr * 31 / 255) << 11)
            | (int(cg * 63 / 255) << 5)
            | int(cb * 31 / 255)
        )
        self.assertEqual(int(arr[y + 5, x + 5]), packed)
        arr[y:y + 10, x:x + 10] = 0
        self.assertEqual(int(arr.max()), 0)

    def test_al_terminar_no_queda_nada(self):
        alpha = np.zeros((2, 8, 8), dtype=np.uint8)
        alpha[:, 1, 1] = 255
        hit = SparkHit(alpha)
        hit.trigger(now=0.0, rng=random.Random(0))
        black = b"\x00\x00" * (WIDTH * HEIGHT)
        self.assertNotEqual(hit.blit_rgb565(black, now=0.0), black)
        self.assertEqual(hit.blit_rgb565(black, now=10.0), black)
        self.assertEqual(hit.pending(now=10.0), 0)


class TestNoEsOverlay(unittest.TestCase):
    def setUp(self):
        import display_executor as de
        self.ex = de.DisplayExecutor(simulate=True)
        self.ex.set_live(True)

    def tearDown(self):
        self.ex.cleanup()

    def test_01_no_arma_el_hold(self):
        frame = b"\x01" * FRAME_BYTES
        self.ex._show_image_internal(frame, SPARK_CC, SPARK_VALUE)
        self.assertIsNone(self.ex._overlay_image)
        self.assertIsNone(self.ex._scene_resume_at)
        self.assertGreater(self.ex.spark.pending(), 0)

    def test_otra_imagen_sigue_siendo_overlay(self):
        frame = b"\x01" * FRAME_BYTES
        self.ex._show_image_internal(frame, 1, 30)
        self.assertEqual(self.ex._overlay_image, frame)
        self.assertIsNotNone(self.ex._scene_resume_at)
        self.assertEqual(self.ex.spark.pending(), 0)

    def test_el_chispazo_no_borra_la_imagen_que_ya_esta(self):
        frame = b"\x02" * FRAME_BYTES
        self.ex._show_image_internal(frame, 1, 30)
        self.ex._show_image_internal(b"\x03" * FRAME_BYTES, SPARK_CC, SPARK_VALUE)
        self.assertEqual(self.ex._overlay_image, frame)
        self.assertGreater(self.ex.spark.pending(), 0)

    def test_sin_sprite_la_01_sigue_sin_404(self):
        self.ex.spark = SparkHit(np.zeros((0, 1, 1), dtype=np.uint8))
        frame = b"\x04" * FRAME_BYTES
        self.ex._show_image_internal(frame, SPARK_CC, SPARK_VALUE)
        self.assertIsNone(self.ex._overlay_image)
