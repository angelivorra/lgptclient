#!/usr/bin/env python3
"""Chispazos: más cortos que el número, y cada uno en un sitio distinto."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lyric_render import COUNTDOWN_FPS, COUNTDOWN_FRAMES  # noqa: E402
from sparks import (  # noqa: E402
    SPARK_FPS, SPARK_FRAMES, SPARKS, SHUTDOWN_FRAMES, shutdown_frames,
    spark_frames,
)


def _ink_xy(img):
    arr = np.asarray(img)
    ink = (arr[:, :, 0].astype(np.uint16)
           + arr[:, :, 1] + arr[:, :, 2]) > 0
    ys, xs = np.where(ink)
    return xs, ys


class TestSparks(unittest.TestCase):
    def test_duran_menos_que_el_numero(self):
        self.assertLess(SPARK_FRAMES / SPARK_FPS,
                        COUNTDOWN_FRAMES / COUNTDOWN_FPS)
        self.assertEqual(len(SPARKS), 4)

    def test_sitios_distintos_y_fondo_transparente(self):
        bursts = []
        for spec in SPARKS:
            frames = spark_frames(
                spec["kind"], spec["origin"], spec["color"], spec["seed"])
            self.assertEqual(len(frames), SPARK_FRAMES)
            self.assertEqual(int(np.asarray(frames[-1])[:, :, 3].max()), 0)
            corner = np.asarray(frames[2])
            self.assertEqual(int(corner[0, 0, 3]), 0)
            xs, ys = _ink_xy(frames[2])
            self.assertGreater(len(xs), 20)
            ox, oy = spec["origin"]
            self.assertLess(float(np.hypot(xs - ox, ys - oy).max()), 120)
            bursts.append((ox, oy))
        for i, a in enumerate(bursts):
            for b in bursts[i + 1:]:
                self.assertGreater(math_dist(a, b), 200)


def math_dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def _opaque(rgb):
    """Mismo criterio que DisplayExecutor._composite_rgb565."""
    r, g, b = (int(rgb[0]) >> 3, int(rgb[1]) >> 2, int(rgb[2]) >> 3)
    lum = r + g + b
    return not ((lum <= 6) or ((b > r) and lum <= 25))


class TestShutdown(unittest.TestCase):
    def test_dura_el_compas_y_tapa_el_fondo(self):
        # 16 filas a 180 BPM.
        self.assertAlmostEqual(SHUTDOWN_FRAMES / SPARK_FPS, 16 * (15 / 180))
        frames = shutdown_frames()
        self.assertEqual(len(frames), SHUTDOWN_FRAMES)
        first = np.asarray(frames[0])
        last = np.asarray(frames[-1])
        self.assertTrue(_opaque(first[0, 0, :3]))
        self.assertGreater(int(first[240, 400, 1]), int(first[0, 0, 1]))
        self.assertTrue(_opaque(last[240, 400, :3]))
        self.assertLess(int(last[:, :, 1].max()), 80)
