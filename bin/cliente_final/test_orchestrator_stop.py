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
        disp.set_live.reset_mock()
        orch.handle_stop(int(time.time() * 1000))
        _run_due(sched)
        self.assertFalse(orch._playing)
        disp.set_live.assert_called_with(False)

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
