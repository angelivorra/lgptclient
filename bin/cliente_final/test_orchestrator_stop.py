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
