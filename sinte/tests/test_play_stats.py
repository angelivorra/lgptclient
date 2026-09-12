#!/usr/bin/env python3
"""Registro de la última reproducción (play_stats.txt)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
_TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_TESTS))

from lgpt_engine import Engine  # noqa: E402
from play_stats import PlayLog, _pct, enabled  # noqa: E402
from test_engine import make_project  # noqa: E402


class TestPct(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_pct([], 95), 0.0)

    def test_single(self):
        self.assertEqual(_pct([4.0], 95), 4.0)

    def test_median(self):
        self.assertAlmostEqual(_pct([1.0, 2.0, 3.0], 50), 2.0)


class TestPlayLog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_writes_on_finish(self):
        log = PlayLog(self.tmp, 44100)
        log.set_source("test")
        log.set_blocksize(512)
        log.begin(tempo=128, from_row=3)
        log.record_block(512, 0.004, voices=4, peak=0.5)
        log.note_xrun("output underflow")
        log.finish("stop")
        log.flush()
        text = (self.tmp / "play_stats.txt").read_text(encoding="utf-8")
        self.assertIn("origen      test", text)
        self.assertIn("fin         stop", text)
        self.assertIn("xruns         1", text)
        self.assertIn("voces máx     4", text)
        self.assertIn("tempo       128", text)

    def test_disabled(self):
        with patch.dict(os.environ, {"PLAY_STATS": "0"}):
            self.assertFalse(enabled())
            log = PlayLog(self.tmp, 44100)
            log.begin(tempo=100)
            log.record_block(512, 0.01)
            log.finish("stop")
            log.flush()
        self.assertFalse((self.tmp / "play_stats.txt").exists())

    def test_missing_dir_does_not_raise(self):
        log = PlayLog(Path("/nonexistent/play_stats_test"), 44100)
        log.begin(tempo=100)
        log.record_block(512, 0.001)
        log.finish("stop")
        log.flush()

    def test_engine_stop_writes(self):
        p = make_project()
        p.dir = self.tmp
        engine = Engine(p)
        engine.play_log.set_source("test")
        engine.start()
        engine.render(512)
        engine.push_event("stop")
        engine.render(512)
        engine.play_log.flush()
        text = (self.tmp / "play_stats.txt").read_text(encoding="utf-8")
        self.assertIn("origen      test", text)
        self.assertIn("fin         stop", text)
        self.assertIn("bloques", text)
        self.assertGreater(engine.play_log.blocks, 0)


if __name__ == "__main__":
    unittest.main()
