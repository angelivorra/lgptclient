#!/usr/bin/env python3
"""Pista LUCES: DmxOut (estado, fundidos, trama) y engine -> eventos DMX."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lgpt_engine import Engine, TICKS_PER_STEP  # noqa: E402
from lgpt_parser import CHANNEL_COUNT, LIGHTS_TRACK  # noqa: E402
from lights import (PALETTE, DmxOut, color_label, luz_label,  # noqa: E402
                    luz_targets)
from test_engine import make_project  # noqa: E402

ROJO = PALETTE.index(("ROJO", (255, 0, 0)))
AZUL = PALETTE.index(("AZUL", (0, 0, 255)))


class TestDmxOut(unittest.TestCase):
    def setUp(self):
        self.dmx = DmxOut(fixtures={"IZQ": 1, "DER": 8})

    def test_trama_inicial_apagada(self):
        frame = self.dmx.frame(0)
        self.assertEqual(len(frame), 24)            # MIN_FRAME
        self.assertEqual(frame[0], 255)             # dimmer a tope
        self.assertEqual(frame[1:4], b"\x00\x00\x00")

    def test_color_por_luz_y_a_su_hora(self):
        self.dmx.event(1000, [0], color=(255, 0, 0))
        self.dmx.event(1000, [1], color=(0, 0, 255), bril=0x80, strobe=0x40)
        self.assertEqual(self.dmx.frame(999)[1:4], b"\x00\x00\x00",
                         "antes de su hora no se aplica")
        f = self.dmx.frame(1000)
        self.assertEqual(f[0:5], bytes([255, 255, 0, 0, 0]))       # IZQ
        self.assertEqual(f[7:12], bytes([0x80, 0, 0, 255, 0x40]))  # DER

    def test_todas_y_fundido(self):
        self.dmx.event(0, None, color=(0, 0, 0))
        self.dmx.event(100, None, color=(200, 0, 0), fade_s=1.0)
        self.assertEqual(self.dmx.frame(600)[1], 100, "a mitad del fundido")
        self.assertEqual(self.dmx.frame(600)[8], 100, "DER también")
        self.assertEqual(self.dmx.frame(1200)[1], 200)

    def test_blackout_limpia_pendientes(self):
        self.dmx.event(0, None, color=(255, 255, 255))
        self.dmx.event(5000, None, color=(255, 0, 0))
        self.dmx.frame(10)
        self.dmx.transport_stop(True)
        self.assertEqual(self.dmx.frame(6000)[1:4], b"\x00\x00\x00")

    def test_sin_cable_no_rompe(self):
        def falla(_port):
            raise OSError("sin cable")
        dmx = DmxOut(serial_factory=falla).start()
        dmx.event(0, None, color=(255, 0, 0))
        dmx.close()
        self.assertIn("sin cable", dmx.error or "")

    def test_trama_por_serie(self):
        sent = []

        class FakeSerial:
            break_condition = False

            def write(self, data):
                sent.append(bytes(data))

            def flush(self):
                pass

            def close(self):
                pass

        dmx = DmxOut(serial_factory=lambda _p: FakeSerial()).start()
        dmx.event(0, [0], color=(1, 2, 3))
        import time
        time.sleep(0.15)
        dmx.close()
        self.assertTrue(sent)
        self.assertTrue(all(s[0] == 0 for s in sent), "start code 0")
        self.assertIn(bytes([0, 255, 1, 2, 3]), [s[:5] for s in sent])

    def test_snapshot(self):
        self.dmx.event(0, [1], color=(0, 0, 255), bril=0x40)
        snap = self.dmx.snapshot(10)
        self.assertEqual(snap[0], ("IZQ", (0, 0, 0), 255, 0, "APAGA"))
        self.assertEqual(snap[1], ("DER", (0, 0, 255), 0x40, 0, "AZUL"))

    def test_from_config(self):
        self.assertIsNone(DmxOut.from_config(None))
        self.assertIsNone(DmxOut.from_config({"activo": False}))
        d = DmxOut.from_config({"puerto": "/dev/x", "luces": {"A": 3}})
        self.assertEqual((d.port, d.names), ("/dev/x", ["A"]))

    def test_etiquetas(self):
        self.assertEqual(color_label(ROJO), "ROJO")
        self.assertEqual(color_label(None), "----")
        self.assertEqual(luz_label(None), "TODAS")
        self.assertEqual(luz_label(2), "DER")
        self.assertEqual(luz_targets(0xFF, 2), None)
        self.assertEqual(luz_targets(1, 2), [0])
        self.assertEqual(luz_targets(9, 2), [])


class Collector:
    def __init__(self):
        self.events = []
        self.transport = []
        self.fixtures = [object(), object()]

    def event(self, t_ms, targets, **kw):
        self.events.append((targets, kw))

    def transport_start(self):
        self.transport.append("start")

    def transport_stop(self, finished=False):
        self.transport.append("stop")


def lights_engine():
    """Canal 0 sin notas; pista LUCES (canal 9) -> chain 1 -> phrase 1."""
    engine = Engine(make_project())
    p = engine.project
    p.song[0 * CHANNEL_COUNT + LIGHTS_TRACK] = 1
    p.chains[1 * 16] = 1
    base = 1 * 16
    p.notes[base + 0] = ROJO
    p.instruments[base + 0] = 2                   # DER
    p.cmd1[base + 0], p.param1[base + 0] = "BRIL", 0x80
    p.cmd2[base + 0], p.param2[base + 0] = "FADE", 2
    p.cmd1[base + 1], p.param1[base + 1] = "STRB", 0x40
    p.notes[base + 2] = 60                        # fuera de paleta, instr 0
    p.instruments[base + 2] = 0
    engine.lights_out = Collector()
    return engine


class TestEngineLuces(unittest.TestCase):
    def test_steps_a_eventos(self):
        engine = lights_engine()
        engine.start()
        for _ in range(TICKS_PER_STEP * 3 + 1):
            engine._process_tick()
        out = engine.lights_out
        self.assertEqual(out.transport[0], "start")
        self.assertEqual(len(out.events), 2, out.events)
        targets, kw = out.events[0]
        self.assertEqual(targets, [1])
        self.assertEqual(kw["color"], (255, 0, 0))
        self.assertEqual(kw["bril"], 0x80)
        fade = 2 * TICKS_PER_STEP * engine.samples_per_tick / engine.sr
        self.assertAlmostEqual(kw["fade_s"], fade)
        targets, kw = out.events[1]
        self.assertEqual((targets, kw["strobe"], kw["color"]),
                         (None, 0x40, None))
        ch = engine.channels[LIGHTS_TRACK]
        self.assertEqual(ch.voices, [], "la pista LUCES nunca suena")

    def test_muteada_no_manda(self):
        engine = lights_engine()
        engine.muted = {LIGHTS_TRACK}
        engine.start()
        for _ in range(TICKS_PER_STEP * 3 + 1):
            engine._process_tick()
        self.assertEqual(engine.lights_out.events, [])

    def test_stop_apaga(self):
        engine = lights_engine()
        engine.start()
        engine.push_event("stop")
        engine.render(256)
        self.assertEqual(engine.lights_out.transport[-1], "stop")


if __name__ == "__main__":
    unittest.main()
