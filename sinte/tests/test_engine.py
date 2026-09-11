#!/usr/bin/env python3
"""Tests headless del motor LGPT (sin tarjeta de audio).

Ejecutar con: .venv/bin/python -m unittest discover -s tests -v
o con pytest: .venv/bin/python -m pytest tests/
"""

import math
import random
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgpt_engine import (  # noqa: E402
    Engine,
    PANLAW,
    Sample,
    TICKS_PER_STEP,
    SAMPLE_RATE,
    NETCC_CHANNEL,
    parse_instrument,
    parse_midi_instrument,
)
from lgpt_parser import LGPTProject

SONGS_DIR = Path("/home/angel/LGPT/songs")
SONGS = ["lgpt_abduccion", "lgpt_Bulebule", "lgpt_Energia",
         "lgpt_Sartenazo.VERSION1"]


def make_project(tempo="120") -> LGPTProject:
    """Proyecto sintético mínimo: canal 0 toca la phrase 0 en bucle.

    Estructura: song row 0 -> chain 0 -> phrase 0 (16 pasos). No toca
    disco: el sample se inyecta después en el banco del engine.
    """
    p = LGPTProject(Path("/nonexistent"))
    p.root = object()                      # evita que Engine llame a load()
    p.project = {"tempo": tempo, "master": "100", "transpose": "0"}
    p.song = bytearray([0xFF] * (8 * 256))
    p.song[0] = 0                          # canal 0, fila 0 -> chain 0
    p.chains = bytearray([0xFF] * (255 * 16))
    p.chains[0] = 0                        # chain 0 paso 0 -> phrase 0
    p.transposes = bytearray(255 * 16)
    p.notes = bytearray([0xFF] * (255 * 16))
    p.instruments = bytearray([0xFF] * (255 * 16))
    p.cmd1 = ["----"] * (255 * 16)
    p.param1 = [0] * (255 * 16)
    p.cmd2 = ["----"] * (255 * 16)
    p.param2 = [0] * (255 * 16)
    p.tables = {}
    p.grooves = bytearray()
    p.instrument_bank = {
        0: {"type": "Sample",
            "params": {"sample": "test.wav", "volume": "128", "pan": "127"}},
        0x80: {"type": "Midi",
               "params": {"channel": "3", "volume": "255", "note length": "0"}},
    }
    return p


class MidiCollector:
    """Sink MidiOut de prueba: registra todos los eventos."""

    def __init__(self):
        self.events = []

    def note_on(self, channel, note, velocity):
        self.events.append(("note_on", channel, note, velocity))

    def note_off(self, channel, note):
        self.events.append(("note_off", channel, note))

    def cc(self, channel, control, value):
        self.events.append(("cc", channel, control, value))

    def program_change(self, channel, program):
        self.events.append(("program_change", channel, program))

    def chord_on(self, channel, notes, velocity):
        self.events.append(("chord_on", channel, tuple(notes), velocity))


def make_engine(tempo="120") -> Engine:
    engine = Engine(make_project(tempo))
    # Sample sintético: seno de 1s a 44100 Hz
    t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
    data = (0.5 * np.sin(2 * np.pi * 440 * t))[:, None].astype(np.float32)
    engine.bank.samples["test.wav"] = Sample(data, SAMPLE_RATE)
    engine.start()
    return engine


def note_row(p: LGPTProject, step: int, note=60, instr=0):
    p.notes[step] = note
    p.instruments[step] = instr


class TestTiming(unittest.TestCase):
    def test_samples_per_tick_formula(self):
        engine = make_engine("120")
        # SyncMaster::SetTempo del upstream
        expected = 60.0 * SAMPLE_RATE * 2.0 / 120 / 8.0 / TICKS_PER_STEP
        self.assertAlmostEqual(engine.samples_per_tick, expected)
        self.assertAlmostEqual(engine.samples_per_tick, 918.75)

    def test_step_advance_every_6_ticks(self):
        # La fila 0 dura 6 ticks (0-5); el avance ocurre en el tick 6
        engine = make_engine("120")
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertEqual(engine.channels[0].phrase_pos, 1)
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        self.assertEqual(engine.channels[0].phrase_pos, 2)

    def test_render_is_sample_accurate(self):
        # Renderizando un step completo (6 ticks) la phrase debe avanzar
        engine = make_engine("120")
        note_row(engine.project, 0)
        samples_per_step = engine.samples_per_tick * TICKS_PER_STEP  # 5512.5
        rendered = 0
        while rendered < math.ceil(samples_per_step) + 1:
            engine.render(512)
            rendered += 512
        self.assertEqual(engine.channels[0].phrase_pos, 1)
        # Sin deriva: los ticks procesados cuadran con los samples renderizados
        expected_ticks = rendered / engine.samples_per_tick
        self.assertAlmostEqual(engine.tick_count, expected_ticks, delta=1.0)


class TestVoices(unittest.TestCase):
    def test_note_triggers_voice_and_sound(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()             # time_to_start 1 -> 0: trigger
        self.assertIsNotNone(engine.channels[0].voice)
        out = engine.render(512)
        self.assertGreater(float(np.abs(out).max()), 0.01)

    def test_transpose_of_chain(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.transposes[0] = 12  # chain 0 paso 0: +12 semitonos
        engine._process_tick()
        voice = engine.channels[0].voice
        self.assertIsNotNone(voice)
        self.assertEqual(voice.note, 72)
        self.assertAlmostEqual(voice.base_speed, 2.0, places=5)

    def test_kill(self):
        # KILL 00 mata la voz en el mismo tick en que se procesa (como el
        # upstream: timeToLive = param+1 y la cuenta atrás corre ese tick)
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[1] = "KILL"    # KILL 0000 en el paso 1
        engine.project.param1[1] = 0
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        self.assertIsNotNone(engine.channels[0].voice)
        engine._process_tick()             # avanza al paso 1 y ejecuta KILL
        self.assertIsNone(engine.channels[0].voice)

    def test_fade_inmediato(self):
        # FADE 00 apaga la nota en el mismo tick (declick, voces a releases)
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[1] = "FADE"
        engine.project.param1[1] = 0
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        self.assertIsNotNone(engine.channels[0].voice)
        engine._process_tick()
        self.assertIsNone(engine.channels[0].voice)
        self.assertTrue(engine.channels[0].releases)
        self.assertNotIn("FADE", engine.unsupported_cmds)
        engine.render(512)
        self.assertFalse(engine.channels[0].releases)

    def test_fade_en_filas(self):
        # FADE 03 rampa el volumen actual a 0 en 3 filas
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[1] = "FADE"
        engine.project.param1[1] = 3
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        v = engine.channels[0].voice
        self.assertIsNotNone(v)
        start = v.vol_cur
        row = int(TICKS_PER_STEP * engine.samples_per_tick)
        engine.render(row)
        self.assertTrue(v.active)
        self.assertGreater(v.vol_cur, start * 0.4)
        self.assertLess(v.vol_cur, start * 0.9)
        engine.render(row * 2 + 2000)
        self.assertFalse(v.active)
        self.assertIsNone(engine.channels[0].voice)
        self.assertNotIn("FADE", engine.unsupported_cmds)

    def test_volm_instant(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "VOLM"
        engine.project.param1[0] = 0x0000  # volumen 0 con micro-rampa de declick
        engine._process_tick()
        voice = engine.channels[0].voice
        self.assertIsNotNone(voice)
        # declick: no salta a 0 de golpe, baja en ~4 ms
        self.assertGreater(voice.vol_cur, 0.0)
        out = engine.render(512)           # 512 > declick (~176): completa el fundido
        self.assertLessEqual(voice.vol_cur, 0.5)
        self.assertEqual(float(np.abs(out[-1]).max()), 0.0)  # cola en silencio

    def test_volumen_instrumento_es_maximo(self):
        """El volumen del instrumento es el MÁXIMO de la voz: sin VOLM la
        nota suena a ese volumen, VOLM FF = el mismo máximo y VOLM 80 ≈ la
        mitad (escala relativa, no absoluta)."""
        pan = PANLAW[127]             # pan central del instrumento del test

        def set_vol(engine, v):
            engine.project.instrument_bank[0]["params"]["volume"] = str(v)
            engine.instruments[0] = parse_instrument(
                0, engine.project.instrument_bank[0]["params"])

        # sin VOLM: suena al máximo del instrumento (seno de amplitud 0.5)
        engine = make_engine()
        set_vol(engine, 100)
        note_row(engine.project, 0)
        engine._process_tick()
        out = engine.render(1024)
        self.assertAlmostEqual(float(np.abs(out).max()),
                               0.5 * (100 / 255) * pan, delta=0.02)

        # VOLM FF: el mismo máximo (antes saltaba a 255 absoluto)
        engine = make_engine()
        set_vol(engine, 100)
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "VOLM"
        engine.project.param1[0] = 0x00FF
        engine._process_tick()
        out = engine.render(1024)
        self.assertAlmostEqual(float(np.abs(out).max()),
                               0.5 * (100 / 255) * pan, delta=0.02)

        # VOLM 80: la mitad del máximo del instrumento (cola tras el
        # declick de ~4 ms para no medir la rampa inicial)
        engine = make_engine()
        set_vol(engine, 100)
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "VOLM"
        engine.project.param1[0] = 0x0080
        engine._process_tick()
        out = engine.render(2048)
        self.assertAlmostEqual(float(np.abs(out[-200:]).max()),
                               0.5 * (128 / 255) * (100 / 255) * pan,
                               delta=0.02)

        # subir el volumen del instrumento sube el máximo
        engine = make_engine()
        set_vol(engine, 200)
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "VOLM"
        engine.project.param1[0] = 0x00FF
        engine._process_tick()
        out = engine.render(1024)
        self.assertAlmostEqual(float(np.abs(out).max()),
                               0.5 * (200 / 255) * pan, delta=0.02)

    def test_volumen_instrumento_editable_en_vivo(self):
        """Editar el volumen del instrumento se oye en la nota que suena
        (vol_scale en vivo) y en la nota siguiente (re-parseo al disparar)."""
        pan = PANLAW[127]
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()
        out = engine.render(1024)
        self.assertAlmostEqual(float(np.abs(out).max()),
                               0.5 * (128 / 255) * pan, delta=0.02)

        # edición del editor: cambia el banco (objeto vivo) sin tocar la voz
        engine.project.instrument_bank[0]["params"]["volume"] = "200"
        out2 = engine.render(1024)          # la misma nota sigue sonando
        self.assertAlmostEqual(float(np.abs(out2).max()),
                               0.5 * (200 / 255) * pan, delta=0.02)

        # la nota siguiente se dispara con el instrumento re-parseado
        engine.start()                      # re-lee la fila 0
        engine._process_tick()
        self.assertIsNotNone(engine.channels[0].voice)
        self.assertEqual(engine.instruments[0].volume, 200)
        out3 = engine.render(1024)
        self.assertAlmostEqual(float(np.abs(out3).max()),
                               0.5 * (200 / 255) * pan, delta=0.02)

    def test_dlay(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "DLAY"
        engine.project.param1[0] = 2       # retrasa 2+1 = 3 ticks
        engine.start()                     # re-lee la fila 0 con el DLAY
        engine._process_tick()
        self.assertIsNone(engine.channels[0].voice)
        engine._process_tick()
        self.assertIsNone(engine.channels[0].voice)
        engine._process_tick()
        self.assertIsNotNone(engine.channels[0].voice)

    def test_stop_command(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "STOP"
        engine._process_tick()
        self.assertFalse(engine.playing)
        self.assertTrue(engine.finished)
        out = engine.render(512)
        # Declick de salida: el bloque puede tener cola, el final ya no.
        self.assertLess(float(np.abs(out[-1]).max()), 0.02)

    def test_table_volm(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "TABL"
        engine.project.param1[0] = 0
        engine.project.tables[0] = {
            "cmd1": ["VOLM"] + ["----"] * 15,
            "param1": [0] * 16,            # VOLM 0000 -> volumen 0
            "cmd2": ["----"] * 16, "param2": [0] * 16,
            "cmd3": ["----"] * 16, "param3": [0] * 16,
        }
        engine._process_tick()             # trigger + tabla fila 0
        voice = engine.channels[0].voice
        self.assertIsNotNone(voice)
        engine.render(512)                 # completa la micro-rampa de declick
        self.assertLessEqual(voice.vol_cur, 0.5)

    def test_midi_cc_events(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()
        engine.push_event("cc", 0, 7, 0)   # volumen canal 0 a 0
        out = engine.render(512)
        self.assertEqual(float(np.abs(out).max()), 0.0)

    def test_param_events(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()
        engine.push_event("param", 0, "volume", 0)
        out = engine.render(512)
        self.assertEqual(float(np.abs(out).max()), 0.0)
        # pitch: una octava arriba duplica la velocidad de la voz
        voice = engine.channels[0].voice
        base = voice.base_speed
        engine.push_event("param", 0, "pitch", 127)
        engine.render(16)
        self.assertAlmostEqual(
            engine.channels[0].cc_pitch, 2.0 ** (63 / 64), places=5)
        self.assertAlmostEqual(voice.base_speed, base)   # no cambia la base

    def test_pad_sample(self, tmp_dir=None):
        # pad sampler: dispara un WAV del banco (directo, sin delay), según
        # wavs_dir/pads.json ("1" -> pad índice 0)
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sf_write = __import__("soundfile").write
            t = np.arange(22050, dtype=np.float32) / SAMPLE_RATE
            sig = (0.4 * np.sin(2 * np.pi * 220 * t))[:, None]
            sf_write(str(Path(d) / "bombo.wav"), sig, SAMPLE_RATE,
                     subtype="PCM_16")
            (Path(d) / "pads.json").write_text(json.dumps({"1": "bombo.wav"}))
            engine = Engine(make_project(), wavs_dir=d)
            engine.start()
            engine.push_event("trigger", 0)
            out = engine.render(512)
            self.assertGreater(float(np.abs(out).max()), 0.01)

    def test_nuevo_sample_se_oye_sin_recargar(self):
        """Asignar un WAV nuevo al instrumento (como el editor) se oye
        al disparar, sin recrear el Engine ni recargar la canción."""
        import tempfile
        import soundfile as sf
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "samples").mkdir()
            t = np.arange(SAMPLE_RATE // 10, dtype=np.float32) / SAMPLE_RATE
            sig = (0.5 * np.sin(2 * np.pi * 440 * t))[:, None]
            p = make_project()
            p.dir = d
            engine = Engine(p)
            self.assertIsNone(engine.bank.samples.get("nuevo.wav"))

            sf.write(str(d / "samples" / "nuevo.wav"), sig, SAMPLE_RATE,
                     subtype="PCM_16")
            engine.project.instrument_bank[0]["params"]["sample"] = "nuevo.wav"
            note_row(engine.project, 0)
            engine.start()
            engine._process_tick()
            self.assertIsNotNone(engine.channels[0].voice)
            self.assertIn("nuevo.wav", engine.bank.samples)
            out = engine.render(512)
            self.assertGreater(float(np.abs(out).max()), 0.01)

    def test_satan_preset(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()
        engine.push_event("param", 0, "satan", 100)
        out = engine.render(2048)
        self.assertFalse(np.isnan(out).any())
        self.assertGreater(float(np.abs(out).max()), 0.0)

    def test_muted_channel(self):
        engine = make_engine()
        engine.muted = {0}
        engine.snap_mute_gains()
        note_row(engine.project, 0)
        engine._process_tick()
        out = engine.render(512)
        self.assertEqual(float(np.abs(out).max()), 0.0)
        # el secuenciador sigue vivo aunque el canal esté muteado
        self.assertIsNotNone(engine.channels[0].voice)

    def test_mute_unmute_sin_click(self):
        """Silenciar o reactivar en vivo rampa ~4 ms: sin salto de muestra."""
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()
        engine.render(2048)
        engine.push_event("mute", 0, True)
        silenced = engine.render(512)
        jump = float(np.abs(np.diff(silenced.mean(axis=1))).max())
        self.assertLess(jump, 0.08, f"click al mute: salto {jump:.3f}")
        self.assertLess(float(np.abs(silenced[-1]).max()), 0.02)
        engine.push_event("mute", 0, False)
        restored = engine.render(512)
        jump = float(np.abs(np.diff(restored.mean(axis=1))).max())
        self.assertLess(jump, 0.08, f"click al unmute: salto {jump:.3f}")
        self.assertGreater(float(np.abs(restored[-1]).max()), 0.05)

    def test_nota_entra_sin_click(self):
        """Un WAV que no parte de 0 no debe entrar a palo seco."""
        engine = make_engine()
        engine.bank.samples["test.wav"] = Sample(
            np.ones((SAMPLE_RATE, 1), dtype=np.float32) * 0.8, SAMPLE_RATE)
        note_row(engine.project, 0)
        engine.project.instrument_bank[0]["params"]["loopmode"] = "loop"
        engine.project.instrument_bank[0]["params"]["end"] = "0"
        engine._process_tick()
        out = engine.render(512)
        first = float(np.abs(out[0]).max())
        later = float(np.abs(out[400:]).max())
        self.assertLess(first, 0.05, f"click al disparar: {first:.3f}")
        self.assertGreater(later, 0.1)

    def test_stop_sin_click(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine._process_tick()
        engine.render(2048)
        engine.push_event("stop")
        silenced = engine.render(512)
        jump = float(np.abs(np.diff(silenced.mean(axis=1))).max())
        self.assertLess(jump, 0.08, f"click al stop: salto {jump:.3f}")
        self.assertLess(float(np.abs(silenced[-1]).max()), 0.02)


class TestMidiOut(unittest.TestCase):
    def make_midi_engine(self):
        engine = make_engine()
        engine.midi_out = MidiCollector()
        return engine

    def test_note_on_off(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine._process_tick()             # trigger: CC7 + note on
        self.assertEqual(
            engine.midi_out.events,
            [("cc", 3, 7, 127), ("note_on", 3, 60, 127)])
        note_row(engine.project, 1, note=62, instr=0x80)
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        # Nueva nota: note off de la anterior antes del note on
        events = engine.midi_out.events
        off_idx = events.index(("note_off", 3, 60))
        on_idx = events.index(("note_on", 3, 62, 127))
        self.assertLess(off_idx, on_idx)

    def test_fade_midi_inmediato(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "FADE"
        engine.project.param1[1] = 0
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertIn(("note_off", 3, 60), engine.midi_out.events)

    def test_fade_midi_en_filas(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "FADE"
        engine.project.param1[1] = 3
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertNotIn(("note_off", 3, 60), engine.midi_out.events)
        for _ in range(3 * TICKS_PER_STEP):
            engine._process_tick()
        self.assertIn(("note_off", 3, 60), engine.midi_out.events)

    def test_mdcc(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (74 << 8) | 100   # CC74 = 100
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertIn(("cc", 3, 74, 100), engine.midi_out.events)

    def test_netcc(self):
        # pots_red: no toca nada local (a diferencia de "cc"/"param"), solo
        # reenvía por midi_out con el canal virtual NETCC_CHANNEL.
        engine = self.make_midi_engine()
        vol_antes = engine.channels[0].cc_vol
        engine.push_event("netcc", 3, 90)
        engine.render(512)
        self.assertEqual(engine.midi_out.events, [("cc", NETCC_CHANNEL, 3, 90)])
        self.assertEqual(engine.channels[0].cc_vol, vol_antes)

    def _pasar_retardo_letra(self, engine):
        """La letra se encola y se aplica en render(), no en el tick que la
        dispara (ver Engine.LYRIC_DELAY_S) — hay que renderizar de sobra
        para que el retardo termine de pasar."""
        engine.render(int(engine.LYRIC_DELAY_S * SAMPLE_RATE) + SAMPLE_RATE)

    def test_mdcc_letra(self):
        # Banco de textos (control=2): la letra se actualiza en local
        # (con retardo) aunque siga reenviándose el CC por midi_out ya
        # mismo, como cualquier otro.
        engine = self.make_midi_engine()
        engine.lyric_lines = ["primera línea", "", "segunda línea"]
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (2 << 8) | 0   # control=2, valor=0
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertIn(("cc", 3, 2, 0), engine.midi_out.events)
        self.assertEqual(engine.current_lyric, "")   # todavía no, está encolada
        self._pasar_retardo_letra(engine)
        self.assertEqual(engine.current_lyric, "primera línea")

    def test_mdcc_letra_desaparece_al_pasar_lyric_max_s(self):
        # Cada palabra dura como mucho LYRIC_MAX_S en pantalla si no llega
        # otra antes (si no, se quedaría hasta el siguiente MDCC, que puede
        # tardar mucho más que la propia palabra cantada).
        engine = self.make_midi_engine()
        engine.lyric_lines = ["primera línea"]
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (2 << 8) | 0
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self._pasar_retardo_letra(engine)
        self.assertEqual(engine.current_lyric, "primera línea")
        # La canción sintética repite la phrase 0 en bucle: sin quitar el
        # comando, un render tan largo puede volver a dispararlo y
        # refrescar la caducidad. Se quita para comprobar solo el tope de
        # tiempo, no un redisparo.
        engine.project.cmd1[1] = "----"
        engine.render(int(engine.LYRIC_MAX_S * SAMPLE_RATE) + SAMPLE_RATE)
        self.assertEqual(engine.current_lyric, "")

    def test_mdcc_letra_valor_vacio_mantiene_la_anterior(self):
        engine = self.make_midi_engine()
        engine.lyric_lines = ["primera línea", ""]
        engine.current_lyric = "primera línea"
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (2 << 8) | 1   # valor=1: línea vacía
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self._pasar_retardo_letra(engine)
        self.assertEqual(engine.current_lyric, "primera línea")

    def test_mdcc_letra_valor_fuera_de_rango_mantiene_la_anterior(self):
        engine = self.make_midi_engine()
        engine.lyric_lines = ["primera línea"]
        engine.current_lyric = "primera línea"
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (2 << 8) | 5   # valor=5, fuera de rango
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self._pasar_retardo_letra(engine)
        self.assertEqual(engine.current_lyric, "primera línea")

    def test_mdcc_otro_control_no_toca_la_letra(self):
        # Un CC distinto de 2 (p. ej. el de imágenes/animaciones en
        # instrumentos 80-81) no debe chocar con el sistema de letras.
        engine = self.make_midi_engine()
        engine.lyric_lines = ["primera línea", "segunda línea"]
        engine.current_lyric = "primera línea"
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (81 << 8) | 1   # control=81, valor=1
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertIn(("cc", 3, 81, 1), engine.midi_out.events)
        self._pasar_retardo_letra(engine)
        self.assertEqual(engine.current_lyric, "primera línea")

    def test_mdpg(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "MDPG"
        engine.project.param1[1] = 42
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertIn(("program_change", 3, 42), engine.midi_out.events)

    def test_volm_midi_envia_cc7(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[1] = "VOLM"
        engine.project.param1[1] = 0x0080  # 128 // 2 = 64
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertIn(("cc", 3, 7, 64), engine.midi_out.events)

    def test_note_length(self):
        engine = self.make_midi_engine()
        engine.project.instrument_bank[0x80]["params"]["note length"] = "2"
        engine.midi_instruments = {
            0x80: parse_midi_instrument(
                0x80, engine.project.instrument_bank[0x80]["params"])
        }
        note_row(engine.project, 0, note=60, instr=0x80)
        engine._process_tick()             # trigger
        self.assertNotIn(("note_off", 3, 60), engine.midi_out.events)
        engine._process_tick()             # ticks 2 -> 1
        engine._process_tick()             # ticks 1 -> 0: note off
        self.assertIn(("note_off", 3, 60), engine.midi_out.events)

    def test_panic_apaga_notas(self):
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine._process_tick()
        engine.panic()
        self.assertIn(("note_off", 3, 60), engine.midi_out.events)

    def test_mdcc_ignorado_con_instrumento_sample(self):
        # Como en el upstream: MDCC solo sale si el canal tiene un
        # instrumento MIDI activo
        engine = self.make_midi_engine()
        note_row(engine.project, 0, note=60, instr=0)   # instrumento Sample
        engine.project.cmd1[1] = "MDCC"
        engine.project.param1[1] = (74 << 8) | 100
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        self.assertEqual(engine.midi_out.events, [])


class TestPlayFromRow(unittest.TestCase):
    """Play desde una fila de SONG: solo arrancan los canales que tienen
    algo en esa fila (sin escaneo hacia delante)."""

    def make_two_channel_engine(self):
        p = make_project()
        p.song[2 * 8 + 1] = 1            # canal 1, fila 2 -> chain 1
        p.chains[1 * 16] = 0             # chain 1 paso 0 -> phrase 0
        return Engine(p)

    def test_solo_canales_con_contenido_en_la_fila(self):
        engine = self.make_two_channel_engine()
        engine.start(2)
        self.assertTrue(engine.channels[1].playing)   # tiene algo en la fila 2
        self.assertFalse(engine.channels[0].playing)  # fila 2 vacía: no suena
        self.assertTrue(engine.playing)

    def test_contenido_mas_adelante_no_arranca(self):
        engine = self.make_two_channel_engine()
        engine.start(0)
        self.assertTrue(engine.channels[0].playing)   # tiene algo en la fila 0
        self.assertFalse(engine.channels[1].playing)  # su contenido es la fila 2

    def test_fila_vacia_no_suena_nada(self):
        engine = self.make_two_channel_engine()
        engine.start(3)                  # fila 3 vacía en todos los canales
        self.assertTrue(engine.playing)
        self.assertFalse(any(c.playing for c in engine.channels))

    def test_sin_fila_escanea_hacia_delante(self):
        # Arranque clásico (player/mixer): cada canal entra en su primer
        # contenido, aunque no esté en la fila 0.
        engine = self.make_two_channel_engine()
        engine.start()
        self.assertTrue(engine.channels[0].playing)   # fila 0
        self.assertTrue(engine.channels[1].playing)   # fila 2


class TestAudioDelay(unittest.TestCase):
    def test_audio_delayed_but_midi_immediate(self):
        engine = make_engine()
        engine.set_audio_delay(2 * 512 / SAMPLE_RATE)  # 2 bloques
        engine.midi_out = MidiCollector()
        note_row(engine.project, 0, note=60, instr=0x80)
        b1 = engine.render(512)
        # El MIDI sale al momento; el audio todavía es silencio
        self.assertTrue(engine.midi_out.events)
        self.assertEqual(float(np.abs(b1).max()), 0.0)
        b2 = engine.render(512)
        self.assertEqual(float(np.abs(b2).max()), 0.0)

    def test_delay_matches_offset(self):
        delay_samples = 512
        e1 = make_engine()
        note_row(e1.project, 0)
        e2 = make_engine()
        note_row(e2.project, 0)
        e2.set_audio_delay(delay_samples / SAMPLE_RATE)
        plain = np.concatenate([e1.render(512) for _ in range(8)])
        delayed = np.concatenate([e2.render(512) for _ in range(8)])
        self.assertEqual(
            float(np.abs(delayed[:delay_samples]).max()), 0.0)
        np.testing.assert_allclose(
            delayed[delay_samples:], plain[:-delay_samples], atol=1e-6)

    def test_delay_multichannel_no_crosstalk(self):
        # Con delay mayor que un bloque y varios canales, el audio
        # retrasado debe ser exactamente el mismo desplazado (sin
        # corrupción ni cruce entre canales)
        delay_samples = 3 * 512
        e1 = make_engine()
        note_row(e1.project, 0)
        note_row(e1.project, 4, note=48)
        e2 = make_engine()
        note_row(e2.project, 0)
        note_row(e2.project, 4, note=48)
        e2.set_audio_delay(delay_samples / SAMPLE_RATE)
        plain = np.concatenate([e1.render(512) for _ in range(12)])
        delayed = np.concatenate([e2.render(512) for _ in range(12)])
        self.assertEqual(
            float(np.abs(delayed[:delay_samples]).max()), 0.0)
        np.testing.assert_allclose(
            delayed[delay_samples:], plain[:-delay_samples], atol=1e-6)

    def test_modulation_applies_at_delay_output(self):
        # La modulación del controlador actúa sobre el audio que SALE del
        # delay (instantánea para quien escucha), no sobre la entrada
        engine = make_engine()
        engine.set_audio_delay(2 * 512 / SAMPLE_RATE)
        note_row(engine.project, 0)
        engine.render(512)                     # t=0 entra al delay
        engine.push_event("param", 0, "volume", 0)
        engine.render(512)
        out = engine.render(512)               # sale el audio de t=0
        # con la arquitectura antigua sonaría (vol se aplicó al entrar);
        # ahora el volumen 0 se aplica a la salida: silencio
        self.assertEqual(float(np.abs(out).max()), 0.0)


class TestGroove(unittest.TestCase):
    def make_groove_engine(self, pattern):
        engine = make_engine()
        engine.groove_data = bytearray([0xFF] * (0x20 * 16))
        engine.groove_data[:len(pattern)] = pattern
        engine.start()                     # re-inicia con el nuevo groove
        return engine

    def step_ticks(self, engine, n_steps):
        """Intervalos en ticks entre avances consecutivos de la phrase."""
        advances = []
        prev = engine.channels[0].phrase_pos
        for tick in range(1, 128):
            engine._process_tick()
            pos = engine.channels[0].phrase_pos
            if pos != prev:
                advances.append(tick)
                prev = pos
                if len(advances) >= n_steps + 1:
                    break
        return [b - a for a, b in zip(advances, advances[1:])]

    def test_default_groove_is_straight(self):
        engine = make_engine()
        self.assertEqual(self.step_ticks(engine, 4), [6, 6, 6, 6])

    def test_swing_groove(self):
        # Patrón [3, 1]: el avance N ocurre al terminar el slot N, así que
        # los intervalos son el patrón rotado: [1, 3, 1, 3, ...]
        engine = self.make_groove_engine(bytearray([3, 1]))
        self.assertEqual(self.step_ticks(engine, 5), [1, 3, 1, 3, 1])

    def test_bulebule_groove(self):
        # Groove real de Bulebule: [7, 5, 6, 5] (rotado por fase: empieza
        # en el segundo slot)
        engine = self.make_groove_engine(bytearray([7, 5, 6, 5]))
        self.assertEqual(self.step_ticks(engine, 5), [5, 6, 5, 7, 5])

    def test_grov_command(self):
        engine = make_engine()
        engine.project.cmd1[0] = "GROV"
        engine.project.param1[0] = 1
        engine.groove_data[16] = 3         # groove 1 = [3, 3]
        engine.groove_data[17] = 3
        engine._process_tick()             # procesa el GROV de la fila 0
        ch = engine.channels[0]
        self.assertEqual(ch.groove, 1)
        self.assertEqual(ch.g_ticks, 3)


class TestChrd(unittest.TestCase):
    """Comando CHRD: acorde sobre la nota de la fila (samples, MIDI, vocoder)."""

    def test_sample_chord_spawns_voices(self):
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 0          # maj = 4, 7
        engine._process_tick()
        notes = [v.note for v in engine.channels[0].voices]
        self.assertEqual(notes, [60, 64, 67])
        out = engine.render(512)
        self.assertGreater(float(np.abs(out).max()), 0.01)

    def test_sin_chrd_sigue_monofonico(self):
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine._process_tick()
        self.assertEqual(len(engine.channels[0].voices), 1)
        self.assertEqual(engine.channels[0].voice.note, 60)

    def test_kill_corta_el_acorde(self):
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 1          # min
        engine.project.cmd2[1] = "KILL"
        engine.project.param2[1] = 0
        engine._process_tick()
        self.assertEqual(len(engine.channels[0].voices), 3)
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        engine._process_tick()               # paso 1: KILL
        self.assertEqual(engine.channels[0].voices, [])
        self.assertIsNone(engine.channels[0].voice)

    def test_siguiente_nota_corta_el_acorde(self):
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 0
        note_row(engine.project, 1, note=62)
        engine._process_tick()
        self.assertEqual(len(engine.channels[0].voices), 3)
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        engine._process_tick()               # trigger paso 1
        self.assertEqual(len(engine.channels[0].voices), 1)
        self.assertEqual(engine.channels[0].voice.note, 62)

    def test_midi_chord_note_ons(self):
        engine = make_engine()
        engine.midi_out = MidiCollector()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 0          # maj
        engine._process_tick()
        ons = [e for e in engine.midi_out.events if e[0] == "note_on"]
        self.assertEqual(
            [(e[1], e[2]) for e in ons],
            [(3, 60), (3, 64), (3, 67)])

    def test_midi_chord_note_offs(self):
        engine = make_engine()
        engine.midi_out = MidiCollector()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 0
        note_row(engine.project, 1, note=62, instr=0x80)
        engine._process_tick()
        for _ in range(TICKS_PER_STEP + 1):
            engine._process_tick()
        offs = [e for e in engine.midi_out.events if e[0] == "note_off"]
        self.assertEqual(
            sorted(e[2] for e in offs),
            [60, 64, 67])
        ons = [e for e in engine.midi_out.events if e[0] == "note_on"]
        self.assertEqual(ons[-1], ("note_on", 3, 62, 127))

    def test_vocoder_chrd_acrd(self):
        engine = make_engine()
        engine.midi_out = MidiCollector()
        engine.channels[0].vocoder_out = True
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 1          # min = 3, 7
        engine._process_tick()
        # La raíz va por note_on (NOTA); el acorde completo por ACRD.
        ons = [e for e in engine.midi_out.events if e[0] == "note_on"]
        self.assertEqual([(e[1], e[2]) for e in ons], [(3, 60)])
        chords = [e for e in engine.midi_out.events if e[0] == "chord_on"]
        self.assertEqual(len(chords), 1)
        self.assertEqual(chords[0][1], 0)               # canal del tracker
        self.assertEqual(chords[0][2], (60, 63, 67))

    def test_vocoder_nibbles_siguen_funcionando(self):
        engine = make_engine()
        engine.midi_out = MidiCollector()
        engine.channels[0].vocoder_out = True
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.param1[0] = 0x0470     # E y G, sin comando CHRD
        engine._process_tick()
        chords = [e for e in engine.midi_out.events if e[0] == "chord_on"]
        self.assertEqual(chords[0][2], (60, 64, 67))
        self.assertEqual(len(engine.channels[0].midi_notes), 1)

    def test_chrd_no_es_unsupported(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 0
        engine._process_tick()
        self.assertNotIn("CHRD", engine.unsupported_cmds)

    def test_volm_aplica_a_todas_las_voces(self):
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "CHRD"
        engine.project.param1[0] = 0
        engine.project.cmd2[0] = "VOLM"
        engine.project.param2[0] = 0x0000
        engine._process_tick()
        for v in engine.channels[0].voices:
            self.assertNotEqual(v.vol_target, 255.0)


class TestArpr(unittest.TestCase):
    """ARPR: una nota al azar del acorde, de la tónica a la octava."""

    def test_una_voz_en_el_pool(self):
        engine = make_engine()
        engine._rng = random.Random(0)
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "ARPR"
        engine.project.param1[0] = 0          # maj
        engine._process_tick()
        self.assertEqual(len(engine.channels[0].voices), 1)
        self.assertIn(engine.channels[0].voice.note, {60, 64, 67, 72})
        self.assertNotIn("ARPR", engine.unsupported_cmds)
        self.assertEqual(engine.channels[0].arp_root, 60)

    def test_fila_vacia_sigue_la_tonica(self):
        engine = make_engine()
        engine._rng = random.Random(1)
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "ARPR"
        engine.project.param1[0] = 0
        engine.project.cmd1[1] = "ARPR"
        engine.project.param1[1] = 0
        engine._process_tick()
        self.assertEqual(engine.channels[0].arp_root, 60)
        for _ in range(TICKS_PER_STEP):
            engine._process_tick()
        engine._process_tick()               # paso 1, sin nota
        self.assertEqual(len(engine.channels[0].voices), 1)
        self.assertIn(engine.channels[0].voice.note, {60, 64, 67, 72})
        self.assertEqual(engine.channels[0].arp_root, 60)

    def test_vacio_sin_tonica_no_dispara(self):
        engine = make_engine()
        engine.project.cmd1[0] = "ARPR"
        engine.project.param1[0] = 0
        engine._process_tick()
        self.assertIsNone(engine.channels[0].voice)

    def test_midi_una_nota(self):
        engine = make_engine()
        engine._rng = random.Random(0)
        engine.midi_out = MidiCollector()
        note_row(engine.project, 0, note=60, instr=0x80)
        engine.project.cmd1[0] = "ARPR"
        engine.project.param1[0] = 0
        engine._process_tick()
        ons = [e for e in engine.midi_out.events if e[0] == "note_on"]
        self.assertEqual(len(ons), 1)
        self.assertIn(ons[0][2], {60, 64, 67, 72})

    def test_varia_con_la_semilla(self):
        heard = set()
        for seed in range(24):
            engine = make_engine()
            engine._rng = random.Random(seed)
            note_row(engine.project, 0, note=60)
            engine.project.cmd1[0] = "ARPR"
            engine.project.param1[0] = 0
            engine._process_tick()
            heard.add(engine.channels[0].voice.note)
        self.assertGreater(len(heard), 1)
        self.assertTrue(heard <= {60, 64, 67, 72})


class TestSlid(unittest.TestCase):
    def test_pack_unpack(self):
        from lgpt_engine import slid_pack, slid_unpack
        self.assertEqual(slid_unpack(slid_pack(72, 4)), (72, 4))
        self.assertEqual(slid_unpack(slid_pack(0, 0)), (0, 1))
        self.assertEqual(slid_unpack(slid_pack(200, 99)), (72, 16))  # 200&0x7F=72

    def test_no_es_unsupported(self):
        from lgpt_engine import slid_pack
        engine = make_engine()
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "SLID"
        engine.project.param1[0] = slid_pack(72, 1)
        engine._process_tick()
        self.assertNotIn("SLID", engine.unsupported_cmds)

    def test_llega_a_la_nota_destino(self):
        from lgpt_engine import slid_pack
        engine = make_engine("120")
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[0] = "SLID"
        engine.project.param1[0] = slid_pack(72, 1)   # +12 semitonos en 1 step
        engine.start()
        engine._process_tick()
        v = engine.channels[0].voice
        self.assertIsNotNone(v)
        self.assertAlmostEqual(v.lega_ratio, 1.0, places=2)
        samples = int(math.ceil(engine.samples_per_tick * TICKS_PER_STEP)) + 64
        rendered = 0
        while rendered < samples:
            engine.render(512)
            rendered += 512
        self.assertAlmostEqual(v.lega_ratio, 2.0, places=2)

    def test_sin_nota_nueva_desliza_la_voz(self):
        """Step 0 dispara; step 1 solo SLID (sin nota) mueve la misma voz."""
        from lgpt_engine import slid_pack
        engine = make_engine("120")
        note_row(engine.project, 0, note=60)
        engine.project.cmd1[1] = "SLID"
        engine.project.param1[1] = slid_pack(72, 1)
        engine.start()
        samples_per_step = engine.samples_per_tick * TICKS_PER_STEP
        rendered = 0
        while rendered < math.ceil(samples_per_step) + 1:
            engine.render(512)
            rendered += 512
        self.assertEqual(engine.channels[0].phrase_pos, 1)
        v = engine.channels[0].voice
        self.assertIsNotNone(v)
        self.assertEqual(v.note, 60)
        rendered = 0
        while rendered < math.ceil(samples_per_step) + 64:
            engine.render(512)
            rendered += 512
        self.assertAlmostEqual(v.lega_ratio, 2.0, places=2)


class TestPreview(unittest.TestCase):
    """Notas del teclado MIDI sobre el instrumento del editor."""

    def test_sample_suena_y_calla(self):
        engine = make_engine()
        engine.playing = False
        engine.push_event("preview_on", 0, 60, 100)
        out = engine.render(512)
        self.assertGreater(float(np.abs(out).max()), 0.01)
        self.assertIn(60, engine.preview_voices)
        engine.push_event("preview_off", 60)
        # declick (~4 ms a 44100 ≈ 176 samples): varios bloques hasta silencio
        for _ in range(8):
            engine.render(512)
        self.assertNotIn(60, engine.preview_voices)
        self.assertEqual(engine.preview_releases, [])

    def test_polifonia_dos_notas(self):
        engine = make_engine()
        engine.playing = False
        engine.push_event("preview_on", 0, 60, 100)
        engine.push_event("preview_on", 0, 64, 100)
        engine.render(64)
        self.assertEqual(set(engine.preview_voices), {60, 64})
        engine.push_event("preview_off", 60)
        engine.render(64)
        self.assertNotIn(60, engine.preview_voices)
        self.assertIn(64, engine.preview_voices)

    def test_midi_note_on_off(self):
        engine = make_engine()
        engine.playing = False
        engine.midi_out = MidiCollector()
        engine.push_event("preview_on", 0x80, 67, 90)
        engine.render(64)
        self.assertEqual(
            engine.midi_out.events,
            [("cc", 3, 7, 127), ("note_on", 3, 67, 90)])
        engine.push_event("preview_off", 67)
        engine.render(64)
        self.assertIn(("note_off", 3, 67), engine.midi_out.events)

    def test_off_all_y_instrumento_inexistente(self):
        engine = make_engine()
        engine.playing = False
        engine.push_event("preview_on", 0, 60, 100)
        engine.render(64)
        self.assertTrue(engine.preview_voices)
        engine.push_event("preview_off_all")
        engine.render(512)
        for _ in range(8):
            engine.render(512)
        self.assertEqual(engine.preview_voices, {})
        engine.push_event("preview_on", 99, 60, 100)  # iid que no existe
        engine.render(64)
        self.assertEqual(engine.preview_voices, {})


class TestRealSongs(unittest.TestCase):
    def test_render_all_songs(self):
        for name in SONGS:
            with self.subTest(song=name):
                engine = Engine(SONGS_DIR / name)
                engine.start()
                blocks = int(15 * SAMPLE_RATE / 512)
                peak = 0.0
                energy = 0.0
                for _ in range(blocks):
                    out = engine.render(512)
                    self.assertFalse(np.isnan(out).any())
                    peak = max(peak, float(np.abs(out).max()))
                    energy += float((out ** 2).mean())
                self.assertGreater(energy, 0.0, "salida silenciosa")
                self.assertLessEqual(peak, 1.0, "clipping")


    def test_bulebule_groove_timing(self):
        # El groove 0 de Bulebule es [7,5,6,5]: los intervalos entre steps
        # deben seguir ese patrón
        engine = Engine(SONGS_DIR / "lgpt_Bulebule")
        engine.start()
        self.assertEqual(list(engine.groove_data[:4]), [7, 5, 6, 5])
        ch = engine.channels[0]
        advances = []
        prev = ch.phrase_pos
        for tick in range(1, 400):
            engine._process_tick()
            if ch.phrase_pos != prev:
                advances.append(tick)
                prev = ch.phrase_pos
                if len(advances) >= 6:
                    break
        intervals = [b - a for a, b in zip(advances, advances[1:])]
        self.assertEqual(intervals, [5, 6, 5, 7, 5])


class TestFilter(unittest.TestCase):
    def _mix_engine(self, mode="lp", cut=40, res=0):
        engine = make_engine()
        t = np.arange(SAMPLE_RATE, dtype=np.float32) / SAMPLE_RATE
        data = (0.35 * np.sin(2 * np.pi * 120 * t)
                + 0.35 * np.sin(2 * np.pi * 4000 * t))[:, None]
        engine.bank.samples["test.wav"] = Sample(
            data.astype(np.float32), SAMPLE_RATE)
        params = engine.project.instrument_bank[0]["params"]
        params["filter mode"] = mode
        params["filter cut"] = str(cut)
        params["filter res"] = str(res)
        return engine

    def _bin_energy(self, buf, freq):
        spec = np.fft.rfft(buf[:, 0])
        idx = int(round(freq * len(buf) / SAMPLE_RATE))
        return float(abs(spec[idx]))

    def test_svf_lp_quita_agudos(self):
        engine = self._mix_engine("lp", cut=80)
        note_row(engine.project, 0)
        engine._process_tick()
        v = engine.channels[0].voice
        self.assertEqual(v.f_mode, "lp")
        self.assertTrue(v.f_active)
        out = engine.render(4096)
        self.assertGreater(self._bin_energy(out, 120),
                           self._bin_energy(out, 4000) * 2)

    def test_svf_hp_quita_graves(self):
        engine = self._mix_engine("hp", cut=200)
        note_row(engine.project, 0)
        engine._process_tick()
        out = engine.render(4096)
        self.assertGreater(self._bin_energy(out, 4000),
                           self._bin_energy(out, 120) * 2)

    def test_fcut_enciende_filtro(self):
        engine = make_engine()
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "FCUT"
        engine.project.param1[0] = 40
        engine._process_tick()
        v = engine.channels[0].voice
        self.assertTrue(v.f_active)
        self.assertAlmostEqual(v.f_cut_base, 40 / 255.0, places=5)
        self.assertNotIn("FCUT", engine.unsupported_cmds)

    def test_fmod_cambia_modo(self):
        engine = self._mix_engine("original", cut=255, res=0)
        note_row(engine.project, 0)
        engine.project.cmd1[0] = "FMOD"
        engine.project.param1[0] = 2          # lp
        engine._process_tick()
        v = engine.channels[0].voice
        self.assertEqual(v.f_mode, "lp")
        self.assertNotIn("FMOD", engine.unsupported_cmds)


if __name__ == "__main__":
    unittest.main()
