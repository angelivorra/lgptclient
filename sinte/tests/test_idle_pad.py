"""Los pads sampler en pausa emiten el CC del gesto; en canción, no."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from midi_control import handle_sample_action, idle_pad_gesture  # noqa: E402


class _Sink:
    def __init__(self):
        self.calls = []

    def cc_immediate(self, channel, control, value):
        self.calls.append((channel, control, value))


class _Engine:
    def __init__(self, playing):
        self.playing = playing
        self.events = []

    def push_event(self, *args):
        self.events.append(args)


class TestIdlePadGesture(unittest.TestCase):
    def test_en_pausa_cada_pad_tiene_su_gesto(self):
        self.assertEqual(idle_pad_gesture(0, False), (3, 14))
        self.assertEqual(idle_pad_gesture(1, False), (3, 15))
        self.assertEqual(idle_pad_gesture(2, False), (3, 16))
        self.assertEqual(idle_pad_gesture(3, False), (3, 17))

    def test_en_cancion_el_pad_no_cambia_la_pantalla(self):
        self.assertIsNone(idle_pad_gesture(0, True))
        self.assertIsNone(idle_pad_gesture(3, True))

    def test_un_indice_raro_no_emite(self):
        self.assertIsNone(idle_pad_gesture(-1, False))
        self.assertIsNone(idle_pad_gesture(4, False))

    def test_en_la_lista_el_pad_manda_el_gesto(self):
        sink = _Sink()
        handle_sample_action("sample1", {}, sink)
        self.assertEqual(sink.calls, [(0, 3, 14)])

    def test_sonando_el_pad_no_manda_gesto(self):
        sink = _Sink()
        engine = _Engine(playing=True)
        handle_sample_action("sample2", {"engine": engine}, sink)
        self.assertEqual(sink.calls, [])
        self.assertEqual(engine.events, [("trigger", 1)])


if __name__ == "__main__":
    unittest.main()
