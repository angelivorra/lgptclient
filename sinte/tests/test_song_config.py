"""Config por canción (robotraca.json) y eventos en vivo del engine.

Lo que usa la app mixer/ del repo lgptclient, que embebe el engine:
los campos "fx"/"fx_mix" del JSON, los eventos "mute"/"vocoder"/"presence"
por push_event, y la guardia de plugins LADSPA ausentes (PC sin
swh-plugins).
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import lgpt_engine  # noqa: E402
from lgpt_player import Player  # noqa: E402
from test_engine import make_engine  # noqa: E402


def make_player_sin_audio() -> Player:
    """Player.__new__ con los args justos para _apply_song_config."""
    player = Player.__new__(Player)
    player.args = SimpleNamespace(
        hw_pots={}, pots=[], pots_red=[], pad_volume=60)
    return player


class TestFxEnApplySongConfig(unittest.TestCase):
    """El campo "fx" del robotraca.json se aplica al cargar la canción."""

    def aplicar(self, cfg: dict):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            (project_dir / "robotraca.json").write_text(json.dumps(cfg))
            engine = make_engine()
            Player._apply_song_config(make_player_sin_audio(),
                                      project_dir, engine)
            return engine

    def test_fx_field(self):
        engine = self.aplicar({"fx": {"2": {"acid": 80, "delay": 40}}})
        self.assertAlmostEqual(engine.channels[2].fx_amounts["acid"], 0.8)
        self.assertAlmostEqual(engine.channels[2].fx_amounts["delay"], 0.4)

    def test_fx_invalido_se_ignora(self):
        engine = self.aplicar({"fx": {"9": {"acid": 10},       # canal fuera
                                      "3": {"reverb": 50},     # fx desconocido
                                      "x": {"acid": 10}}})     # clave no numérica
        self.assertNotIn("acid", engine.channels[3].fx_amounts)
        self.assertNotIn("reverb", engine.channels[3].fx_amounts)


class TestFxMixEnApplySongConfig(unittest.TestCase):
    """El campo "fx_mix" del robotraca.json se aplica al cargar la canción
    (mezcla dry/wet 0-100 -> Channel.fx_mix 0-1)."""

    def aplicar(self, cfg: dict):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            (project_dir / "robotraca.json").write_text(json.dumps(cfg))
            engine = make_engine()
            Player._apply_song_config(make_player_sin_audio(),
                                      project_dir, engine)
            return engine

    def test_fx_mix_field(self):
        engine = self.aplicar({"fx_mix": {"2": {"acid": 50, "delay": 30}}})
        self.assertAlmostEqual(engine.channels[2].fx_mix["acid"], 0.5)
        self.assertAlmostEqual(engine.channels[2].fx_mix["delay"], 0.3)

    def test_fx_mix_invalido_se_ignora(self):
        engine = self.aplicar({"fx_mix": {"9": {"acid": 10},       # canal fuera
                                          "3": {"reverb": 50},     # fx desconocido
                                          "x": {"acid": 10}}})     # clave no numérica
        self.assertNotIn("acid", engine.channels[3].fx_mix)
        self.assertNotIn("reverb", engine.channels[3].fx_mix)


class TestFxMixEnRender(unittest.TestCase):
    """render() mezcla dry/wet por efecto según Channel.fx_mix (0-1): a
    falta de fx_mix se comporta igual que antes (100% wet)."""

    def _render_con_mix(self, mix):
        class FakeFx:
            """Efecto sintético: siempre deja el bloque a un valor
            constante (0.7), para poder predecir la mezcla dry/wet."""

            def __init__(self, sr):
                pass

            def apply(self, buf, amount):
                buf[:] = 0.7

        engine = make_engine()   # canal 0 sin notas -> dry = silencio (0)
        engine.channels[0].fx_amounts["fake"] = 1.0
        if mix is not None:
            engine.channels[0].fx_mix["fake"] = mix
        original = dict(lgpt_engine.EFFECT_PRESETS)
        lgpt_engine.EFFECT_PRESETS["fake"] = FakeFx
        try:
            return engine.render(64)
        finally:
            lgpt_engine.EFFECT_PRESETS.clear()
            lgpt_engine.EFFECT_PRESETS.update(original)

    def test_sin_fx_mix_100_wet_igual_que_antes(self):
        out = self._render_con_mix(None)
        np.testing.assert_allclose(out, 0.7, atol=1e-6)

    def test_mix_0_deja_el_canal_seco(self):
        out = self._render_con_mix(0.0)
        np.testing.assert_allclose(out, 0.0, atol=1e-6)

    def test_mix_50_mezcla_a_medias(self):
        out = self._render_con_mix(0.5)
        np.testing.assert_allclose(out, 0.35, atol=1e-6)


class TestEventosEnVivo(unittest.TestCase):
    """mute/vocoder/presence por push_event (lo que manda la app mixer)."""

    def test_mute(self):
        engine = make_engine()
        engine.push_event("mute", 3, True)
        engine.push_event("mute", 6, True)
        engine._drain_events()
        self.assertEqual(engine.muted, {3, 6})
        engine.push_event("mute", 3, False)
        engine._drain_events()
        self.assertEqual(engine.muted, {6})

    def test_vocoder_y_presence(self):
        engine = make_engine()
        engine.push_event("vocoder", 2, True)
        engine.push_event("presence", 5, True)
        engine._drain_events()
        self.assertTrue(engine.channels[2].vocoder_out)
        self.assertTrue(engine.channels[5].fx_presence)


class TestFxNoDisponible(unittest.TestCase):
    """Un preset cuyo plugin falta no debe tumbar el render: el canal suena
    en seco y no se reintenta la instanciación en cada bloque."""

    def test_render_sin_plugin(self):
        intentos = []

        class FxRoto:
            def __init__(self, sr):
                intentos.append(1)
                raise OSError("no existe el .so")

        engine = make_engine()
        engine.channels[0].fx_amounts["roto"] = 1.0
        original = dict(lgpt_engine.EFFECT_PRESETS)
        lgpt_engine.EFFECT_PRESETS["roto"] = FxRoto
        try:
            out = engine.render(512)
            engine.render(512)          # segundo bloque: no reintenta
        finally:
            lgpt_engine.EFFECT_PRESETS.clear()
            lgpt_engine.EFFECT_PRESETS.update(original)
        self.assertEqual(len(intentos), 1)
        self.assertEqual(engine.channels[0].fx_objs["roto"], False)
        self.assertEqual(out.shape, (512, 2))
        self.assertTrue(np.isfinite(out).all())


if __name__ == "__main__":
    unittest.main()
