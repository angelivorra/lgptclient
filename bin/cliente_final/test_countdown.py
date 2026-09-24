#!/usr/bin/env python3
"""Cuenta atrás 3-2-1: neón que se apaga por bloques en 4 filas."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lyric_render import (  # noqa: E402
    COUNTDOWN_BLOCK, COUNTDOWN_FPS, COUNTDOWN_FRAMES, COUNTDOWN_HOLD,
    countdown_frames,
)

FONT = Path(__file__).resolve().parents[2] / "images" / "002" / "fuente.ttf"


def _ink(img) -> int:
    arr = np.asarray(img)
    return int(((arr[:, :, 0].astype(np.uint16)
                 + arr[:, :, 1] + arr[:, :, 2]) > 0).sum())


class TestCountdown(unittest.TestCase):
    def test_dura_cuatro_filas_a_180(self):
        # Fila = 15/BPM s con el groove de gobiernoIA (6 ticks).
        cuatro_filas = 4 * (15 / 180)
        self.assertAlmostEqual(COUNTDOWN_FRAMES / COUNTDOWN_FPS, cuatro_filas)

    def test_empieza_entero_y_acaba_negro(self):
        frames = countdown_frames("3", FONT)
        self.assertEqual(len(frames), COUNTDOWN_FRAMES)
        self.assertGreater(_ink(frames[0]), 1000)
        self.assertEqual(_ink(frames[-1]), 0)
        first = np.asarray(frames[0])
        self.assertEqual(int(first[0, 0, 3]), 0)
        self.assertEqual(int(first[-1, -1, 3]), 0)
        self.assertEqual(int(np.asarray(frames[-1])[:, :, 3].max()), 0)
        inks = [_ink(f) for f in frames]
        self.assertEqual(inks, sorted(inks, reverse=True))
        self.assertEqual(set(inks[:COUNTDOWN_HOLD]), {inks[0]})
        self.assertLess(inks[COUNTDOWN_HOLD], inks[0])

    def test_se_apaga_por_bloques_enteros(self):
        frames = countdown_frames("2", FONT)
        a = np.asarray(frames[0])
        b = np.asarray(frames[COUNTDOWN_HOLD + 1])
        ink0 = (a[:, :, 0].astype(np.uint16) + a[:, :, 1] + a[:, :, 2]) > 0
        ink5 = (b[:, :, 0].astype(np.uint16) + b[:, :, 1] + b[:, :, 2]) > 0
        gone = np.argwhere(ink0 & ~ink5)
        self.assertGreater(len(gone), 0)
        y, x = (int(v) for v in gone[0])
        bs = COUNTDOWN_BLOCK
        y0, x0 = (y // bs) * bs, (x // bs) * bs
        block = b[y0:y0 + bs, x0:x0 + bs, :3]
        self.assertEqual(int(block.sum()), 0)
        self.assertTrue(ink5.any())
