"""Audio del tracker: perfil Odin vs PC (sin tocar el sinte de la Pi)."""

import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from host import is_handheld
from player import (BLOCKSIZE_DESKTOP, BLOCKSIZE_HANDHELD, _DAC_JUMP_S,
                    audio_blocksize)


def test_desktop_keeps_sinte_blocksize():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ROBOTRACKER2_EVDEV_GAMEPAD", None)
        assert not is_handheld()
        assert audio_blocksize() == BLOCKSIZE_DESKTOP == 2048


def test_odin_uses_larger_blocksize():
    with patch.dict(os.environ, {"ROBOTRACKER2_EVDEV_GAMEPAD": "1"}):
        assert is_handheld()
        assert audio_blocksize() == BLOCKSIZE_HANDHELD == 4096


def test_callback_catch_up_on_dac_jump():
    from player import Player

    caught = []

    class _Log:
        def note_xrun(self, _detail=""):
            pass

    class _Eng:
        play_log = _Log()

        def catch_up(self, seconds):
            caught.append(seconds)

        def render(self, frames):
            import numpy as np
            return np.zeros((frames, 2), dtype="float32")

    p = Player.__new__(Player)
    p.engine = _Eng()
    p._expected_dac = 1.0
    p._prio_done = True
    time_info = types.SimpleNamespace(outputBufferDacTime=1.0 + 0.050)
    out = __import__("numpy").zeros((64, 2), dtype="float32")
    p._audio_callback(out, 64, time_info, None)
    assert len(caught) == 1
    assert abs(caught[0] - 0.050) < 1e-9
    assert p._expected_dac == 1.050 + 64 / 44100


def test_callback_ignores_tiny_dac_jitter():
    from player import Player

    caught = []

    class _Log:
        def note_xrun(self, _detail=""):
            pass

    class _Eng:
        play_log = _Log()

        def catch_up(self, seconds):
            caught.append(seconds)

        def render(self, frames):
            import numpy as np
            return np.zeros((frames, 2), dtype="float32")

    p = Player.__new__(Player)
    p.engine = _Eng()
    p._expected_dac = 1.0
    p._prio_done = True
    time_info = types.SimpleNamespace(
        outputBufferDacTime=1.0 + _DAC_JUMP_S / 2)
    out = __import__("numpy").zeros((64, 2), dtype="float32")
    p._audio_callback(out, 64, time_info, None)
    assert caught == []


def test_callback_writes_recording():
    from player import Player
    import numpy as np
    import soundfile as sf
    import tempfile

    class _Log:
        def note_xrun(self, _detail=""):
            pass

    class _Eng:
        play_log = _Log()

        def catch_up(self, seconds):
            pass

        def render(self, frames):
            return np.full((frames, 2), 0.25, dtype="float32")

    p = Player.__new__(Player)
    p.engine = _Eng()
    p._expected_dac = None
    p._prio_done = True
    p.recorder = None
    p.record_path = None
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.wav"
        p.start_recording(path)
        out = np.zeros((64, 2), dtype="float32")
        p._audio_callback(out, 64, None, None)
        closed = p.stop_recording()
        assert closed == path
        data, sr = sf.read(path, dtype="float32")
        assert sr == 44100
        assert len(data) == 64
        assert abs(float(data[0, 0]) - 0.25) < 1e-3
        p._audio_callback(out, 64, None, None)
        print("  callback graba WAV OK")


def main():
    test_desktop_keeps_sinte_blocksize()
    test_odin_uses_larger_blocksize()
    test_callback_catch_up_on_dac_jump()
    test_callback_ignores_tiny_dac_jitter()
    test_callback_writes_recording()
    print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
