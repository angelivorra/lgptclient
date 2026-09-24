#!/usr/bin/env python3
"""Latigazo del vocoder: parseo, fade y márgenes."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vocoder_neon import (  # noqa: E402
    FADE_S, HEIGHT, MARGIN, WIDTH, VocoderNeon, parse_acrd,
)


class TestParseAcrd(unittest.TestCase):
    def test_linea_completa(self):
        got = parse_acrd(["ACRD", "1000", "6", "100", "48", "52", "55"])
        self.assertEqual(got, (1000, 6, 100, [48, 52, 55]))

    def test_incompleta_o_basura(self):
        self.assertIsNone(parse_acrd(["ACRD", "1", "6", "80"]))
        self.assertIsNone(parse_acrd(["NOTA", "1", "60", "6", "80"]))
        self.assertIsNone(parse_acrd(["ACRD", "x", "6", "80", "48"]))


class TestLatigazo(unittest.TestCase):
    def test_pico_y_valle(self):
        n = VocoderNeon()
        n.pulse([48], 127, now=1.0)
        self.assertGreater(n.level(1.0), 0.9)
        self.assertLess(n.level(1.0 + FADE_S), 0.1)

    def test_otro_acrd_redispara(self):
        n = VocoderNeon()
        n.pulse([48], 127, now=1.0)
        medio = n.level(1.3)
        n.pulse([72], 127, now=1.3)
        self.assertGreater(n.level(1.3), medio)
        self.assertGreater(n.level(1.3), 0.9)

    def test_stop_apaga(self):
        n = VocoderNeon()
        n.pulse([60], 127, now=1.0)
        n.release(1.0)
        self.assertGreater(n.level(1.0), 0.9)
        self.assertLess(n.level(1.0 + FADE_S), 0.1)

    def test_no_pinta_el_centro(self):
        n = VocoderNeon()
        n.pulse([36], 127, now=1.0)
        frame = np.zeros((HEIGHT, WIDTH), dtype="<u2")
        frame[:, MARGIN:WIDTH - MARGIN] = 0xABCD
        out = np.frombuffer(
            n.blit_rgb565(frame.tobytes(), 1.0), dtype="<u2"
        ).reshape(HEIGHT, WIDTH)
        self.assertTrue(np.array_equal(
            out[:, MARGIN:WIDTH - MARGIN], frame[:, MARGIN:WIDTH - MARGIN]))
        self.assertGreater(int(out[240, 0]), 0)
        self.assertGreater(int(out[240, WIDTH - 1]), 0)

    def test_grave_mas_rojo_que_agudo(self):
        def edge(note):
            n = VocoderNeon()
            n.pulse([note], 127, now=1.0)
            frame = np.zeros((HEIGHT, WIDTH), dtype="<u2")
            out = np.frombuffer(
                n.blit_rgb565(frame.tobytes(), 1.0), dtype="<u2"
            ).reshape(HEIGHT, WIDTH)
            p = int(out[240, 0])
            return (p >> 11) & 31, p & 31

        grave_r, grave_b = edge(36)
        agudo_r, agudo_b = edge(84)
        self.assertGreater(grave_r, agudo_r)
        self.assertGreater(agudo_b, grave_b)


if __name__ == "__main__":
    unittest.main()
