"""Al cargar, si la pista/canal 0 no existe (canciones legacy de LGPT),
se crea: instrumento 00 y, si la columna de SONG está vacía, una chain
en la fila 0.

1. Unitario sobre proyecto sintético (sin Kivy).
2. e2e: canción copiada sin instrumento 00 ni cells en el canal 0 → al
   cargar aparecen; Guardar los persiste (el writer añade el nodo XML).
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from lgpt_model import (EMPTY, EXTRA_TRACK, INSTR_0, NUM_TRACKS, SAMPLE_INSTR_DEFAULTS,  # noqa: E402
                        SONG_ROWS, SongView, ensure_extra_track, ensure_track_0,
                        load_project)
from sinte_bridge import save_project  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _make_project(tmp: Path):
    from lgpt_model import FX_EMPTY  # noqa: E402
    from sinte_bridge import LGPTProject  # noqa: E402

    p = LGPTProject(tmp)
    p.root = object()
    p.project = {"tempo": "120", "master": "100", "transpose": "0"}
    p.song = bytearray([EMPTY] * (NUM_TRACKS * SONG_ROWS))
    p.chains = bytearray([EMPTY] * (255 * 16))
    p.transposes = bytearray(255 * 16)
    p.notes = bytearray([EMPTY] * (255 * 16))
    p.instruments = bytearray([EMPTY] * (255 * 16))
    p.cmd1 = [FX_EMPTY] * (255 * 16)
    p.param1 = [0] * (255 * 16)
    p.cmd2 = [FX_EMPTY] * (255 * 16)
    p.param2 = [0] * (255 * 16)
    p.tables = {}
    p.grooves = bytearray()
    p.instrument_bank = {
        0x10: {"type": "Sample", "params": {"sample": "kick.wav"}},
    }
    return p


def test_unitario():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        p = _make_project(tmp)
        assert INSTR_0 not in p.instrument_bank
        assert all(p.song[r * NUM_TRACKS] == EMPTY for r in range(SONG_ROWS))

        assert ensure_track_0(p) is True
        assert p.instrument_bank[INSTR_0]["type"] == "Sample"
        assert p.instrument_bank[INSTR_0]["params"]["sample"] == ""
        for key, val in SAMPLE_INSTR_DEFAULTS.items():
            assert p.instrument_bank[INSTR_0]["params"][key] == val, key
        chain = SongView(p).chain_at(0, INSTR_0)
        assert chain != EMPTY, "columna 0 vacía → chain en fila 0"
        assert p.song[INSTR_0] == chain

        assert ensure_track_0(p) is False, "idempotente si ya está creado"
        assert SongView(p).chain_at(0, INSTR_0) == chain

        assert ensure_extra_track(p) is True
        extra = SongView(p).chain_at(0, EXTRA_TRACK)
        assert extra != EMPTY, "columna extra vacía → chain en fila 0"
        assert extra != chain
        assert ensure_extra_track(p) is False

        # columna 0 ya usada: no pisa la chain, sí crea el instrumento
        p2 = _make_project(tmp / "usada")
        p2.song[0] = 0x05
        p2.instrument_bank = {0x10: {"type": "Sample",
                                     "params": {"sample": "a.wav"}}}
        assert ensure_track_0(p2) is True
        assert INSTR_0 in p2.instrument_bank
        assert p2.song[0] == 0x05, "no pisa una chain que ya estaba"
        print("  ensure_track_0 unitario OK")


def _cancion_origen():
    for song_dir in sorted(Path(DEFAULT_SONGS).iterdir()):
        if (song_dir / "lgptsav.dat").is_file():
            return song_dir
    raise AssertionError(f"ninguna canción con lgptsav.dat en "
                         f"{DEFAULT_SONGS}")


def _strip_track_0(song: Path):
    """Quita el instrumento 00 y vacía la columna 0 de SONG."""
    p = load_project(song)
    p.instrument_bank.pop(INSTR_0, None)
    for row in range(min(SONG_ROWS, len(p.song) // NUM_TRACKS)):
        p.song[row * NUM_TRACKS + INSTR_0] = EMPTY
    save_project(p, path=song / "lgptsav.dat", backup=False)


def _run(app, song):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    app._midi_ctrl.close()
    app._midi_hotplug = False
    app._request_load(song)
    p = app.editor_screen.project
    assert INSTR_0 in p.instrument_bank, "al cargar se crea el instrumento 00"
    assert p.instrument_bank[INSTR_0]["type"] == "Sample"
    assert SongView(p).chain_at(0, INSTR_0) != EMPTY, \
        "al cargar se crea una chain en el canal 0"
    assert SongView(p).chain_at(0, EXTRA_TRACK) != EMPTY, \
        "al cargar se crea la novena pista"
    assert not app.dirty, "crear pista 0 no marca dirty (hasta Guardar)"
    print("  cargar canción legacy crea pista 0 OK")

    app._save()
    assert not app.dirty
    reloaded = load_project(song)
    assert INSTR_0 in reloaded.instrument_bank, "el writer persiste el 00"
    assert reloaded.instrument_bank[INSTR_0]["params"]["sample"] == ""
    assert SongView(reloaded).chain_at(0, INSTR_0) != EMPTY
    assert SongView(reloaded).chain_at(0, EXTRA_TRACK) != EMPTY
    xml = (song / "lgptsav.dat").read_text()
    assert 'INSTRUMENT ID="00"' in xml
    print("  Guardar persiste instrumento 00 y chain del canal 0 OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    test_unitario()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        song = songs_dir / "lgpt_legacy0"
        shutil.copytree(_cancion_origen(), song)
        _strip_track_0(song)
        assert 0 not in load_project(song).instrument_bank

        app = Robotracker2App(songs_dir=songs_dir, samples_dir=tmp)

        def _go(_dt):
            try:
                _run(app, song)
                print("TODOS LOS TESTS OK")
            except Exception:                        # noqa: BLE001
                import traceback
                traceback.print_exc()
            finally:
                app.stop()

        Clock.schedule_once(_go, 0)
        app.run()


if __name__ == "__main__":
    main()
