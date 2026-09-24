#!/usr/bin/env python3
"""Fundido a negro: 8 filas, y no es el hold de 2 s de las fotos."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fade_black import FADE_ROWS, FadeBlack, fade_frame, fade_seconds  # noqa: E402
from scenes import FRAME_BYTES, HEIGHT, WIDTH  # noqa: E402
from spark_hit import SPARK_CC, SPARK_VALUE  # noqa: E402


class TestFadeBlack(unittest.TestCase):
    def test_ocho_filas_a_180(self):
        self.assertEqual(FADE_ROWS, 8)
        self.assertAlmostEqual(fade_seconds(180), 8 * 15 / 180)

    def test_el_campo_final_no_es_transparente(self):
        arr = np.frombuffer(fade_frame(1.0), dtype="<u2").reshape(HEIGHT, WIDTH)
        pix = int(arr[0, 0])
        r, g, b = (pix >> 11) & 31, (pix >> 5) & 63, pix & 31
        lum = r + g + b
        self.assertGreater(lum, 6)
        self.assertFalse(b > r and lum <= 25)

    def test_empieza_vacio_y_acaba(self):
        fade = FadeBlack()
        self.assertEqual(fade.alpha(now=0.0), 0.0)
        fade.start(180, now=0.0)
        self.assertAlmostEqual(fade.alpha(now=0.0), 0.0)
        mid = fade_seconds(180) / 2
        self.assertGreater(fade.alpha(now=mid), 0.4)
        self.assertEqual(fade.alpha(now=10.0), 0.0)
        self.assertFalse(fade.pending(now=10.0))


class TestImagen01(unittest.TestCase):
    def setUp(self):
        import display_executor as de
        self.ex = de.DisplayExecutor(simulate=True)
        self.ex.set_live(True)
        self.ex.scenes.set_bpm(180)

    def tearDown(self):
        self.ex.cleanup()

    def test_01_no_es_el_404_ni_el_hold(self):
        frame = b"\x01" * FRAME_BYTES
        self.ex._show_image_internal(frame, SPARK_CC, SPARK_VALUE)
        self.assertIsNone(self.ex._overlay_image)
        self.assertIsNone(self.ex._scene_resume_at)
        self.assertGreater(self.ex.spark.pending(), 0)
        self.assertTrue(self.ex.fade.pending())

    def test_otra_imagen_sigue_siendo_overlay(self):
        frame = b"\x01" * FRAME_BYTES
        self.ex._show_image_internal(frame, 1, 30)
        self.assertEqual(self.ex._overlay_image, frame)
        self.assertIsNotNone(self.ex._scene_resume_at)
        self.assertEqual(self.ex.spark.pending(), 0)
        self.assertFalse(self.ex.fade.pending())
