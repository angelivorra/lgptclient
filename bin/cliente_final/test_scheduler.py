#!/usr/bin/env python3
"""El STOP tiene que anular tareas ya sacadas del heap (create_task)."""
import asyncio
import time
import unittest

from scheduler import Scheduler


class TestSchedulerEpoch(unittest.TestCase):
    def test_clear_queue_anula_tareas_en_vuelo(self):
        sched = Scheduler()
        ran = []
        sched.schedule_at_walltime(
            int(time.time() * 1000) - 1000,
            ran.append,
            args=("no",),
            description="stale",
        )
        task = sched._heap[0]
        sched.clear_queue()
        asyncio.run(sched._execute_task(task))
        self.assertEqual(ran, [])

    def test_tareas_nuevas_despues_del_stop_si_corren(self):
        sched = Scheduler()
        ran = []
        sched.clear_queue()
        sched.schedule_at_walltime(
            int(time.time() * 1000) - 1000,
            ran.append,
            args=("ok",),
            description="fresh",
        )
        task = sched._heap[0]
        asyncio.run(sched._execute_task(task))
        self.assertEqual(ran, ["ok"])


if __name__ == "__main__":
    unittest.main()
