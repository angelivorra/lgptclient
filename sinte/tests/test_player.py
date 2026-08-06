#!/usr/bin/env python3
"""Tests del mapeo de botones MIDI del reproductor."""

import unittest
from pathlib import Path

import mido

from lgpt_player import CARGA_AVISO, EstadoAudio, match_button, match_pot, \
    match_pot_red, parse_button_spec, parse_pot_target


class TestParseButtonSpec(unittest.TestCase):
    def test_note(self):
        self.assertEqual(parse_button_spec("note:0:36"), ("note_on", 0, 36))
        self.assertEqual(parse_button_spec("note:9:127"), ("note_on", 9, 127))

    def test_cc(self):
        self.assertEqual(
            parse_button_spec("cc:2:41"), ("control_change", 2, 41))

    def test_invalid(self):
        self.assertIsNone(parse_button_spec(""))
        self.assertIsNone(parse_button_spec("note:0"))
        self.assertIsNone(parse_button_spec("foo:0:1"))
        self.assertIsNone(parse_button_spec("note:x:1"))
        self.assertIsNone(parse_button_spec(None))


class TestMatchButton(unittest.TestCase):
    def setUp(self):
        self.mapping = {
            "up": parse_button_spec("note:0:36"),
            "down": parse_button_spec("note:0:37"),
            "play": parse_button_spec("cc:0:41"),
            "stop": None,                    # sin asignar
        }

    def test_note_on(self):
        msg = mido.Message("note_on", channel=0, note=36, velocity=100)
        self.assertEqual(match_button(self.mapping, msg), "up")
        msg = mido.Message("note_on", channel=0, note=37, velocity=100)
        self.assertEqual(match_button(self.mapping, msg), "down")

    def test_note_off_ignored(self):
        msg = mido.Message("note_off", channel=0, note=36, velocity=0)
        self.assertIsNone(match_button(self.mapping, msg))
        msg = mido.Message("note_on", channel=0, note=36, velocity=0)
        self.assertIsNone(match_button(self.mapping, msg))

    def test_wrong_channel_or_number(self):
        msg = mido.Message("note_on", channel=1, note=36, velocity=100)
        self.assertIsNone(match_button(self.mapping, msg))
        msg = mido.Message("note_on", channel=0, note=38, velocity=100)
        self.assertIsNone(match_button(self.mapping, msg))

    def test_cc(self):
        msg = mido.Message("control_change", channel=0, control=41, value=127)
        self.assertEqual(match_button(self.mapping, msg), "play")
        # El release (valor 0) no dispara
        msg = mido.Message("control_change", channel=0, control=41, value=0)
        self.assertIsNone(match_button(self.mapping, msg))


class TestMatchPot(unittest.TestCase):
    def setUp(self):
        self.pots = [
            (parse_button_spec("cc:9:16"), ((2,), "lp_cutoff", 1.0), 0),
            (parse_button_spec("cc:9:17"), ((2,), "lp_res", 1.0), 4),
            (parse_button_spec("cc:9:18"), (None, "volume", 1.0), 7),  # canal via MIDI
        ]

    def test_pot_match(self):
        msg = mido.Message("control_change", channel=9, control=16, value=80)
        self.assertEqual(match_pot(self.pots, msg), ((2,), "lp_cutoff", 0, 1.0))
        msg = mido.Message("control_change", channel=9, control=17, value=80)
        self.assertEqual(match_pot(self.pots, msg), ((2,), "lp_res", 4, 1.0))

    def test_pot_channel_from_midi(self):
        msg = mido.Message("control_change", channel=9, control=18, value=80)
        self.assertEqual(match_pot(self.pots, msg), ((9 % 8,), "volume", 7, 1.0))

    def test_pot_no_match(self):
        msg = mido.Message("control_change", channel=9, control=19, value=80)
        self.assertIsNone(match_pot(self.pots, msg))
        msg = mido.Message("control_change", channel=0, control=16, value=80)
        self.assertIsNone(match_pot(self.pots, msg))
        msg = mido.Message("note_on", channel=9, note=16, velocity=100)
        self.assertIsNone(match_pot(self.pots, msg))


class TestMatchPotRed(unittest.TestCase):
    def setUp(self):
        self.pots_red = [
            (parse_button_spec("cc:9:16"), 3),
            (parse_button_spec("cc:9:17"), 7),
        ]

    def test_match(self):
        msg = mido.Message("control_change", channel=9, control=16, value=80)
        self.assertEqual(match_pot_red(self.pots_red, msg), 3)
        msg = mido.Message("control_change", channel=9, control=17, value=1)
        self.assertEqual(match_pot_red(self.pots_red, msg), 7)

    def test_no_match(self):
        msg = mido.Message("control_change", channel=9, control=18, value=80)
        self.assertIsNone(match_pot_red(self.pots_red, msg))
        msg = mido.Message("note_on", channel=9, note=16, velocity=100)
        self.assertIsNone(match_pot_red(self.pots_red, msg))


class TestParsePotTarget(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_pot_target("2:lp_cutoff"),
                         ((2,), "lp_cutoff", 1.0))
        self.assertEqual(parse_pot_target("0:volume"), ((0,), "volume", 1.0))

    def test_varios_canales(self):
        self.assertEqual(parse_pot_target("1,2:reverb"),
                         ((1, 2), "reverb", 1.0))

    def test_tope(self):
        # el knob solo recorre hasta el 35% del efecto
        self.assertEqual(parse_pot_target("1,2:reverb:35"),
                         ((1, 2), "reverb", 0.35))

    def test_invalid(self):
        self.assertIsNone(parse_pot_target(""))
        self.assertIsNone(parse_pot_target("8:volume"))   # canal fuera de rango
        self.assertIsNone(parse_pot_target("2:"))
        self.assertIsNone(parse_pot_target("x:volume"))
        self.assertIsNone(parse_pot_target(None))
        self.assertIsNone(parse_pot_target("1,9:reverb"))  # canal fuera
        self.assertIsNone(parse_pot_target("1:reverb:0"))  # tope inválido
        self.assertIsNone(parse_pot_target("1:reverb:x"))


class TestWavRecorder(unittest.TestCase):
    def test_records_wav(self):
        import numpy as np
        import soundfile as sf
        from lgpt_player import WavRecorder
        path = "/tmp/lgpt_recorder_test.wav"
        try:
            rec = WavRecorder(path, 44100)
            t = np.arange(4410, dtype=np.float32) / 44100
            block = np.stack([np.sin(t), np.cos(t)], axis=1)
            rec.write(block)
            rec.write(block)
            rec.close()
            data, sr = sf.read(path, dtype="float32")
            self.assertEqual(sr, 44100)
            self.assertEqual(len(data), 8820)
            np.testing.assert_allclose(data[:4410, 0], block[:, 0], atol=1e-3)
        finally:
            Path(path).unlink(missing_ok=True)


class TestPython311Compat(unittest.TestCase):
    """El código debe parsear con la gramática de Python 3.11 (la Pi)."""

    def test_sources_parse_as_311(self):
        import ast
        root = Path(__file__).resolve().parent.parent
        for name in ("lgpt_engine.py", "lgpt_parser.py",
                     "lgpt_player.py", "lgpt_setup.py"):
            src = (root / name).read_text()
            ast.parse(src, filename=name, feature_version=(3, 11))


class TestEstadoAudio(unittest.TestCase):
    """Contadores de cortes: distinguen las tres causas y no se mezclan."""

    def setUp(self):
        # 2048 muestras a 44100 = 46.44 ms de presupuesto
        self.est = EstadoAudio(2048 / 44100 * 1000)

    def test_presupuesto_y_carga(self):
        self.assertAlmostEqual(self.est.presupuesto_ms, 46.44, places=1)
        self.est.ultima_ms = 23.22
        self.assertAlmostEqual(self.est.carga, 0.5, places=2)

    def test_incidentes_suma_cortes_y_saltos_pero_no_apurados(self):
        self.est.xruns = 2
        self.est.saltos = 3
        self.est.apurados = 9      # apurado no es un corte: no cuenta
        self.assertEqual(self.est.incidentes, 5)

    def test_el_peor_reciente_se_olvida(self):
        """Un pico al arrancar no puede quedarse en pantalla toda la sesión."""
        self.est.peor_desde = 40.0
        for _ in range(2000):
            self.est.peor_desde = max(1.0, self.est.peor_desde * 0.999)
        self.assertLess(self.est.peor_desde, 10.0)

    def test_el_peor_absoluto_no_se_olvida(self):
        self.est.peor_ms = 40.0
        self.assertEqual(self.est.peor_ms, 40.0)

    def test_reinicia_deja_todo_a_cero_menos_el_presupuesto(self):
        self.est.xruns = 5
        self.est.causa = "algo"
        self.est.reinicia()
        self.assertEqual(self.est.xruns, 0)
        self.assertEqual(self.est.causa, "")
        self.assertAlmostEqual(self.est.presupuesto_ms, 46.44, places=1)

    def test_umbral_de_aviso_deja_margen_antes_de_cortar(self):
        self.assertLess(CARGA_AVISO, 1.0)
        self.assertGreater(CARGA_AVISO, 0.5)


if __name__ == "__main__":
    unittest.main()
