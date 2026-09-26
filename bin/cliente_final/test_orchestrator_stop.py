#!/usr/bin/env python3
"""STOP/END se aplican en ts+delay, no al recibir el mensaje."""
import asyncio
import heapq
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from event_orchestrator import EventOrchestrator  # noqa: E402
from scheduler import Scheduler  # noqa: E402


def _orch(delay_ms=1000):
    cfg = MagicMock()
    cfg.invertir = False
    cfg.get_pins_for_note.return_value = []
    mm = MagicMock()
    mm.get_animation.return_value = None
    disp = MagicMock()
    gpio = MagicMock()
    sched = Scheduler()
    orch = EventOrchestrator(cfg, sched, gpio, mm, disp, base_delay_ms=delay_ms)
    orch._pantalla = False
    return orch, sched, disp


def _run_due(sched):
    while sched._heap:
        if sched._heap[0].due_mono > time.monotonic() + 0.02:
            break
        task = heapq.heappop(sched._heap)
        asyncio.run(sched._execute_task(task))


class TestIdlePadGesture(unittest.TestCase):
    def test_en_pausa_el_pad_lanza_el_gesto(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._playing = False
        orch._pantalla = True
        orch._connected = True
        orch._debug = False
        orch._fondo_images = [b"fondo"]
        orch._fondo_config = {"name": "001", "interval": 1, "transition": "cut"}
        cfg = MagicMock(cc=3, value=14)
        orch.media_manager.is_animation.return_value = True
        orch.media_manager.get_animation.return_value = cfg
        disp.play_animation.reset_mock()
        orch.handle_cc(int(time.time() * 1000), 14, 0, 3)
        _run_due(sched)
        disp.play_animation.assert_called_with(cfg, source="gesture")

    def test_en_cancion_el_mismo_cc_sigue_siendo_mdcc(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._playing = True
        orch._pantalla = True
        cfg = MagicMock(cc=3, value=14)
        orch.media_manager.is_animation.return_value = True
        orch.media_manager.get_animation.return_value = cfg
        disp.play_animation.reset_mock()
        orch.handle_cc(int(time.time() * 1000), 14, 0, 3)
        _run_due(sched)
        disp.play_animation.assert_called_with(cfg)

    def test_en_pausa_otro_cc_no_cambia_los_ojos(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._playing = False
        orch._pantalla = True
        orch._connected = True
        orch.media_manager.is_animation.return_value = True
        orch.media_manager.get_animation.return_value = MagicMock(cc=3, value=3)
        disp.play_animation.reset_mock()
        orch.handle_cc(int(time.time() * 1000), 3, 0, 3)
        _run_due(sched)
        disp.play_animation.assert_not_called()


class TestIdleGestureCache(unittest.TestCase):
    def test_al_parar_precarga_los_gestos_una_sola_vez(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._playing = True
        orch._connected = True
        orch._pantalla = True
        orch._debug = False
        orch._fondo_images = [b"fondo"]
        orch._fondo_config = {"name": "001", "interval": 1, "transition": "cut"}
        orch.media_manager.get_animation.return_value = MagicMock()
        orch.media_manager.clear_cache.reset_mock()
        orch.media_manager.release_animation_cache.reset_mock()
        orch.media_manager.preload_animations.reset_mock()
        orch.handle_stop(int(time.time() * 1000))
        _run_due(sched)
        orch.media_manager.clear_cache.assert_called()
        orch.media_manager.release_animation_cache.assert_called()
        orch.media_manager.preload_animations.assert_called_once()
        pairs = orch.media_manager.preload_animations.call_args.args[0]
        self.assertEqual(pairs, [(3, 3), (3, 14), (3, 15), (3, 16), (3, 17)])
        orch.media_manager.preload_animations.reset_mock()
        orch.media_manager.clear_cache.reset_mock()
        orch._show_idle()
        orch.media_manager.preload_animations.assert_not_called()
        orch.media_manager.clear_cache.assert_not_called()

    def test_start_suelta_la_cache_de_gestos(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._pantalla = True
        orch._idle_media_key = "gestos"
        orch.media_manager.release_animation_cache.reset_mock()
        orch.media_manager.clear_cache.reset_mock()
        orch.handle_start(int(time.time() * 1000))
        orch.media_manager.release_animation_cache.assert_called_once()
        orch.media_manager.clear_cache.assert_called_once()
        self.assertIsNone(orch._idle_media_key)

    def test_preload_mapea_el_pack_y_get_animation_lo_reutiliza(self):
        import json
        import tempfile
        from media_manager import MediaManager

        payload = b"\x01\x02" * 8
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            anim = root / "003" / "014"
            anim.mkdir(parents=True)
            (anim / "anim.cfg").write_text(json.dumps(
                {"fps": 24, "loop": True, "max_delay": 0.4}))
            (anim / "pack.bin").write_bytes(payload)
            (anim / "pack.bin.index.json").write_text(json.dumps({
                "width": 2, "height": 2, "bpp": 16,
                "entries": [{"file": "01.bin", "offset": 0, "size": len(payload)}],
            }))
            mm = MediaManager(str(root))
            mm._image_cache[(1, 1)] = b"foto"
            n = mm.preload_animations([(3, 14), (3, 99)])
            self.assertEqual(n, 1)
            cfg = mm.get_animation(3, 14)
            self.assertIsNotNone(cfg)
            self.assertIsNone(cfg.frame_bytes)
            self.assertEqual(cfg.frames[0]["size"], len(payload))
            again = mm.get_animation(3, 14)
            self.assertIs(again, cfg)
            mm.release_animation_cache()
            self.assertIsNone(mm._anim_cache.get((3, 14)))
            disk = mm.get_animation(3, 14)
            self.assertIsNone(disk.frame_bytes)


class TestDelayedStop(unittest.TestCase):
    def test_stop_no_corta_al_recibir(self):
        orch, sched, disp = _orch(delay_ms=1000)
        orch._playing = True
        disp.set_live.reset_mock()
        now = int(time.time() * 1000)
        orch.handle_stop(now)
        self.assertTrue(orch._playing)
        disp.set_live.assert_not_called()
        self.assertGreater(sched.get_pending_count(), 0)

    def test_stop_corta_al_vencer_el_delay(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._playing = True
        orch._connected = True
        orch._fondo_images = [b"frame"]
        orch._fondo_config = {"interval": 0.08, "transition": "cut"}
        orch._pantalla = True
        orch.media_manager.get_animation.return_value = MagicMock()
        disp.set_live.reset_mock()
        disp.clear_slideshow.reset_mock()
        orch.handle_stop(int(time.time() * 1000))
        _run_due(sched)
        self.assertFalse(orch._playing)
        disp.set_live.assert_called_with(False)
        disp.clear_slideshow.assert_not_called()
        disp.set_slideshow.assert_called()

    def test_desconectado_conserva_el_fondo(self):
        """Sin enlace: slideshow + animación idle, sin apagar el fondo."""
        orch, sched, disp = _orch(delay_ms=0)
        orch._connected = False
        orch._debug = False
        orch._playing = False
        orch._pantalla = True
        orch._fondo_images = []
        orch.media_manager.load_fondo_images.return_value = [b"fondo"]
        orch.media_manager.get_animation.return_value = MagicMock()
        disp.clear_slideshow.reset_mock()
        disp.set_slideshow.reset_mock()
        disp.play_animation.reset_mock()
        orch._show_idle()
        disp.clear_slideshow.assert_not_called()
        disp.set_slideshow.assert_called()
        disp.play_animation.assert_called()
        self.assertEqual(disp.play_animation.call_args.kwargs.get("source"), "idle")

    def test_desconexion_a_mitad_de_cancion_vuelve_a_idle(self):
        """Si se cae el TCP con START ya aplicado, hay que mostrar
        desconectado sobre el fondo, no quedarse en live sin overlay."""
        orch, sched, disp = _orch(delay_ms=0)
        orch._connected = True
        orch._playing = True
        orch._debug = False
        orch._pantalla = True
        orch._fondo_images = [b"fondo"]
        orch._fondo_config = {"name": "001", "interval": 0.08, "transition": "cut"}
        orch.media_manager.get_animation.return_value = MagicMock()
        disp.set_live.reset_mock()
        disp.play_animation.reset_mock()
        orch.set_connection_status(False, "192.168.0.2", 8888)
        self.assertFalse(orch._playing)
        self.assertFalse(orch._connected)
        disp.set_live.assert_called_with(False)
        disp.play_animation.assert_called()
        self.assertEqual(disp.play_animation.call_args.kwargs.get("source"), "idle")

    def test_fondo_cache_hit_no_borra_slideshow_al_play(self):
        """Idle carga 001; la canción pide 001 (cache hit). START debe
        conservar el slideshow, no irse a plasma."""
        orch, sched, disp = _orch(delay_ms=0)
        orch._pantalla = True
        orch._playing = False
        orch._fondo_images = [b"frame"]
        orch._fondo_config = {"name": "001", "interval": 0.08, "transition": "cut"}
        orch._song_wants_fondo = False
        orch.handle_fondo("001")
        self.assertTrue(orch._song_wants_fondo)
        disp.clear_slideshow.reset_mock()
        disp.set_slideshow.reset_mock()
        orch.handle_start(int(time.time() * 1000))
        disp.clear_slideshow.assert_not_called()
        disp.set_slideshow.assert_called()

    def test_acrd_espera_el_delay(self):
        orch, sched, disp = _orch(delay_ms=1000)
        orch._pantalla = True
        orch.handle_acrd(int(time.time() * 1000), [48, 52], 110)
        disp.pulse_chord.assert_not_called()
        self.assertGreater(sched.get_pending_count(), 0)

    def test_acrd_dispara_al_vencer(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch._pantalla = True
        orch.handle_acrd(int(time.time() * 1000), [48], 80)
        _run_due(sched)
        disp.pulse_chord.assert_called_once_with([48], 80)

    def test_acrd_sin_pantalla_no_programa(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch.handle_acrd(int(time.time() * 1000), [48], 80)
        disp.pulse_chord.assert_not_called()
        self.assertEqual(sched.get_pending_count(), 0)

    def test_start_anula_el_stop_pendiente(self):
        orch, sched, disp = _orch(delay_ms=0)
        orch.handle_stop(int(time.time() * 1000) - 50)
        orch.handle_start(int(time.time() * 1000) - 50)
        disp.set_live.reset_mock()
        _run_due(sched)
        self.assertTrue(orch._playing)
        self.assertFalse(
            any(c.args == (False,) for c in disp.set_live.call_args_list)
        )


if __name__ == "__main__":
    unittest.main()
