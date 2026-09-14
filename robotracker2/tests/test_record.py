"""Grabar audio (PROJECT): off al cargar, toggle, Play escribe WAV."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, DOWN, L2, LEFT, RIGHT, START, UP  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _run(app):
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._midi_ctrl.close()
    app._midi_hotplug = False
    song = songs[0]
    app._request_load(song)
    m = app.editor_screen.project_menu
    assert m.record_audio is False

    app._dispatch(UP, {UP, L2})
    assert app.editor_screen.current == "project"
    app._dispatch(DOWN, {DOWN})         # tempo -> master
    app._dispatch(DOWN, {DOWN})         # master -> record
    assert m.current_item()[0] == "record"
    assert m.record_audio is False
    app._dispatch(A, {A})
    app._release(A)
    assert m.record_audio is True
    app._dispatch(LEFT, {LEFT})
    assert m.record_audio is False
    app._dispatch(RIGHT, {RIGHT})
    assert m.record_audio is True
    print("  toggle Grabar audio OK")

    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "take.wav"
        with patch.object(app, "_recording_path", return_value=dest):
            app._dispatch(START, {START})
            if not app.player.playing:
                # sin tarjeta de audio: se ejercita start_recording a mano
                app.player.start_recording(dest)
            else:
                assert app.player.recorder is not None
            if app.player.recorder is not None:
                import numpy as np
                buf = np.zeros((128, 2), dtype="float32")
                app.player._audio_callback(buf, 128, None, None)
            app._stop_play()
        assert dest.is_file() and dest.stat().st_size > 44
        print("  Play con grabar escribe WAV OK")

    assert m.record_audio is True
    app._request_load(song)
    assert app.editor_screen.project_menu.record_audio is False
    print("  cargar canción deja Grabar audio en no OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    app = Robotracker2App(songs_dir=DEFAULT_SONGS)

    def _go(_dt):
        try:
            _run(app)
            print("TODOS LOS TESTS OK")
        except Exception:                 # noqa: BLE001
            import traceback
            traceback.print_exc()
        finally:
            app.stop()

    Clock.schedule_once(_go, 0)
    app.run()


if __name__ == "__main__":
    main()
