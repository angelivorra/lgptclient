#!/usr/bin/env python3
"""Tests headless del motor de escenas (sin framebuffer)."""
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenes import FRAME_BYTES, HEIGHT, WIDTH, SceneEngine, rgb888_to_rgb565  # noqa: E402


class TestScenes(unittest.TestCase):
    def test_frame_rgb565_tamano(self):
        eng = SceneEngine(invert=False)
        eng.set_scene("live")
        frame = eng.render()
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame), FRAME_BYTES)

    def test_sin_escena_no_pinta(self):
        eng = SceneEngine()
        self.assertIsNone(eng.render())

    def test_sin_golpe_el_plasma_se_ve(self):
        """La cama no puede ser casi negra: si no, en el escenario no se nota."""
        import numpy as np
        eng = SceneEngine(invert=False)
        eng.set_scene("live")
        eng.set_bpm(128)
        frame = np.frombuffer(eng.render(), dtype="<u2").reshape(HEIGHT, WIDTH)
        self.assertGreater(int(frame.mean()), 8)

    def test_golpe_es_mas_brillante_que_el_reposo(self):
        import numpy as np
        quiet = SceneEngine(invert=False)
        quiet.set_scene("live")
        quiet.set_bpm(120)
        hit = SceneEngine(invert=False)
        hit.set_scene("live")
        hit.set_bpm(120)
        hit.pulse("kick", 127)
        a = np.frombuffer(quiet.render(), dtype="<u2")
        b = np.frombuffer(hit.render(), dtype="<u2")
        self.assertGreater(int(b.mean()), int(a.mean()))

    def test_el_bpm_hace_cambiar_el_frame(self):
        eng = SceneEngine(invert=False)
        eng.set_scene("live")
        eng.set_bpm(180)
        f1 = eng.render()
        time.sleep(0.2)
        f2 = eng.render()
        self.assertNotEqual(f1, f2)
        eng = SceneEngine(invert=False)
        eng.set_scene("live")
        eng.set_bpm(140)
        eng.pulse("kick", 127)
        frame = eng.render()
        self.assertEqual(len(frame), FRAME_BYTES)
        self.assertGreater(sum(frame[:2000]), 0)

    def test_invert_cambia_el_frame(self):
        a = SceneEngine(invert=False)
        b = SceneEngine(invert=True)
        a.set_scene("live")
        b.set_scene("live")
        a.pulse("kick", 127)
        b.pulse("kick", 127)
        fa, fb = a.render(), b.render()
        self.assertEqual(len(fa), len(fb))
        self.assertNotEqual(fa, fb)

    def test_rgb565_roundtrip_shape(self):
        import numpy as np
        rgb = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        rgb[0, 0] = (255, 0, 0)
        data = rgb888_to_rgb565(rgb)
        self.assertEqual(len(data), FRAME_BYTES)
        pix = int.from_bytes(data[0:2], "little")
        self.assertEqual(pix, (31 << 11))  # R=31 en RGB565


    def test_set_scene_live_no_reinicia_el_reloj(self):
        eng = SceneEngine()
        eng.set_scene("live")
        t0 = eng._t0
        eng.set_scene("live")
        self.assertEqual(eng._t0, t0)


class TestLiveResume(unittest.TestCase):
    """Tras un MDCC de imagen, el plasma tiene que volver."""

    def setUp(self):
        import display_executor as de
        self.de = de
        self.ex = de.DisplayExecutor(simulate=True)
        self.ex.set_live(True)
        self.ex.play_scene("live")
        time.sleep(0.08)

    def tearDown(self):
        self.ex.cleanup()

    def test_imagen_no_congela_el_live(self):
        self.assertEqual(self.ex._current_type, "scene")
        frame = b"\x01" * FRAME_BYTES
        self.ex.show_image(frame, 1, 30)
        time.sleep(0.08)
        self.assertEqual(self.ex._current_type, "scene")
        self.assertIsNotNone(self.ex._overlay_image)

    def test_idle_no_roba_el_live(self):
        from media_manager import AnimationConfig
        self.assertEqual(self.ex._current_type, "scene")
        cfg = AnimationConfig(
            cc=3, value=3, fps=30, loop=True, max_delay=5,
            pack_path="/dev/null", index_path="", frames=[],
            width=800, height=480, bpp=16)
        self.ex.play_animation(cfg, source="idle")
        time.sleep(0.08)
        self.assertEqual(self.ex._current_type, "scene")

    def test_stop_no_resucita_la_escena(self):
        self.ex.set_live(False)
        self.ex.play_scene("live")
        time.sleep(0.08)
        self.assertNotEqual(self.ex._current_type, "scene")
