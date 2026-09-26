#!/usr/bin/env python3
"""Tests headless del motor de escenas (sin framebuffer)."""
import json
import random
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

    def test_idle_ojos_sobre_slideshow(self):
        """En pausa, los ojos se mezclan encima del fondo, no lo tapán."""
        import tempfile
        from media_manager import AnimationConfig

        frame = b"\xFF\xFF" * (FRAME_BYTES // 2)
        n = 20
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack.bin"
            pack.write_bytes(frame * n)
            entries = [{"file": f"{i:03d}.bin", "offset": i * len(frame),
                        "size": len(frame)} for i in range(n)]
            cfg = AnimationConfig(
                cc=3, value=3, fps=30, loop=True, max_delay=1,
                pack_path=str(pack), index_path="",
                frames=entries, width=800, height=480, bpp=16)
            self.ex.set_live(False)
            self.ex.set_slideshow([b"\x00\x00" * (FRAME_BYTES // 2)], interval=1.0)
            self.ex.play_animation(cfg, source="idle")
            time.sleep(0.12)
            self.assertTrue(self.ex._idle_over_fondo)
            self.assertEqual(self.ex._current_type, "animation")
            self.assertIsNotNone(self.ex._overlay_image)

    def test_idle_desconectado_sobre_slideshow(self):
        """Sin conexión, 003/001 se mezcla encima del fondo, igual que los ojos."""
        import tempfile
        from media_manager import AnimationConfig

        frame = b"\xFF\xFF" * (FRAME_BYTES // 2)
        n = 20
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack.bin"
            pack.write_bytes(frame * n)
            entries = [{"file": f"{i:03d}.bin", "offset": i * len(frame),
                        "size": len(frame)} for i in range(n)]
            cfg = AnimationConfig(
                cc=3, value=1, fps=30, loop=True, max_delay=2,
                pack_path=str(pack), index_path="",
                frames=entries, width=800, height=480, bpp=16)
            self.ex.set_live(False)
            self.ex.set_slideshow([b"\x00\x00" * (FRAME_BYTES // 2)], interval=1.0)
            self.ex.play_animation(cfg, source="idle")
            time.sleep(0.12)
            self.assertTrue(self.ex._idle_over_fondo)
            self.assertEqual(self.ex._current_type, "animation")
            self.assertIsNotNone(self.ex._overlay_image)
            self.assertEqual(self.ex._current_animation.cc, 3)
            self.assertEqual(self.ex._current_animation.value, 1)

    def test_gesto_precargado_no_abre_el_pack(self):
        """Si los frames ya están en memoria, el gesto no toca el disco."""
        from media_manager import AnimationConfig

        frame = b"\xFF\xFF" * (FRAME_BYTES // 2)
        cfg = AnimationConfig(
            cc=3, value=14, fps=30, loop=True, max_delay=1,
            pack_path="/no/existe/pack.bin", index_path="",
            frames=[{"file": "000.bin", "offset": 0, "size": len(frame)}],
            width=800, height=480, bpp=16,
            frame_bytes=[frame],
        )
        self.ex.set_live(False)
        self.ex.set_slideshow([b"\x00\x00" * (FRAME_BYTES // 2)], interval=1.0)
        self.ex.play_animation(cfg, source="gesture")
        time.sleep(0.12)
        self.assertIsNone(self.ex._animation_pack_file)
        self.assertEqual(self.ex._overlay_image, frame)
        self.assertIn(self.ex._anim_source, ("gesture", "gesture-done"))

    def test_sprite_no_tapa_el_resto_de_la_pantalla(self):
        """Un recorte de ojos solo pisa su rectángulo. El negro no tapa."""
        import numpy as np
        from display_executor import DisplayExecutor

        bg = b"\xFF\xFF" * (800 * 480)
        green = (0xFFE0).to_bytes(2, "little")
        black = b"\x00\x00"
        fg = green + black + black + green
        out = DisplayExecutor._composite_sprite(bg, fg, 10, 20, 2, 2)
        arr = np.frombuffer(out, dtype="<u2").reshape(480, 800)
        self.assertEqual(int(arr[0, 0]), 0xFFFF)
        self.assertEqual(int(arr[20, 10]), 0xFFE0)
        self.assertEqual(int(arr[20, 11]), 0xFFFF)
        self.assertEqual(int(arr[21, 11]), 0xFFE0)

    def test_animacion_en_live_es_overlay(self):
        """Un MDCC de animación no sustituye el fondo: queda de overlay."""
        import json
        import tempfile
        from media_manager import AnimationConfig

        frame = b"\xFF\xFF" * (FRAME_BYTES // 2)  # blanco opaco
        n = 20  # ~0.66 s a 30 FPS: el clip no debe haber vuelto al live
        with tempfile.TemporaryDirectory() as tmp:
            pack = Path(tmp) / "pack.bin"
            pack.write_bytes(frame * n)
            entries = [{"file": f"{i:03d}.bin", "offset": i * len(frame),
                        "size": len(frame)} for i in range(n)]
            index = {"width": 800, "height": 480, "bpp": 16, "entries": entries}
            (Path(tmp) / "pack.bin.index.json").write_text(json.dumps(index))
            cfg = AnimationConfig(
                cc=3, value=2, fps=30, loop=False, max_delay=1,
                pack_path=str(pack), index_path=str(Path(tmp) / "pack.bin.index.json"),
                frames=entries, width=800, height=480, bpp=16)
            self.ex.play_animation(cfg, source="mdcc")
            time.sleep(0.12)
            self.assertEqual(self.ex._current_type, "animation")
            self.assertIsNotNone(self.ex._overlay_image)
            self.assertEqual(len(self.ex._overlay_image), FRAME_BYTES)


class TestKickShake(unittest.TestCase):
    def test_shake_desplaza_y_rellena_negro(self):
        import numpy as np
        from display_executor import shake_rgb565

        rgb = np.full((HEIGHT, WIDTH), 0xFFFF, dtype="<u2")
        rgb[10, 20] = 0x001F
        out = np.frombuffer(
            shake_rgb565(rgb.tobytes(), 3, 2), dtype="<u2"
        ).reshape(HEIGHT, WIDTH)
        self.assertEqual(int(out[12, 23]), 0x001F)
        self.assertTrue((out[:2, :] == 0).all())
        self.assertTrue((out[:, :3] == 0).all())

    def test_shake_cero_no_toca_el_frame(self):
        from display_executor import shake_rgb565
        frame = b"\x12\x34" * (FRAME_BYTES // 2)
        self.assertIs(shake_rgb565(frame, 0, 0), frame)

    def test_solo_el_bombo_enciende_shake(self):
        import display_executor as de
        ex = de.DisplayExecutor(simulate=True)
        try:
            self.assertEqual(ex._shake, 0.0)
            ex.pulse_hit("snare", 127)
            self.assertEqual(ex._shake, 0.0)
            ex.pulse_hit("crash", 127)
            self.assertEqual(ex._shake, 0.0)
            ex.pulse_hit("kick", 127)
            self.assertGreater(ex._shake, 0.9)
        finally:
            ex.cleanup()


class TestIdleBlinkRhythm(unittest.TestCase):
    def test_la_pausa_no_cabe_en_el_uniforme_de_antes(self):
        from display_executor import idle_blink_gap

        random.seed(0)
        gaps = [idle_blink_gap() for _ in range(500)]
        self.assertTrue(any(g < 0.4 for g in gaps))
        self.assertTrue(any(g > 7.0 for g in gaps))
        self.assertTrue(all(0.12 <= g <= 14.0 for g in gaps))

    def test_la_velocidad_del_parpadeo_cambia(self):
        from display_executor import idle_blink_interval

        random.seed(1)
        base = 1.0 / 30.0
        rates = [idle_blink_interval(base) for _ in range(300)]
        self.assertGreater(max(rates), base * 1.4)
        self.assertLess(min(rates), base * 0.85)
        self.assertTrue(all(base * 0.55 <= r <= base * 1.9 for r in rates))

    def test_el_desconectado_sigue_el_max_delay(self):
        from display_executor import loop_restart_delay

        random.seed(2)
        delays = [loop_restart_delay(2.0, idle_eyes=False) for _ in range(80)]
        self.assertTrue(all(0.4 <= d <= 2.0 for d in delays))
        eyes = [loop_restart_delay(5.0, idle_eyes=True) for _ in range(400)]
        self.assertTrue(any(d < 0.4 for d in eyes))
        self.assertTrue(any(d > 5.0 for d in eyes))
