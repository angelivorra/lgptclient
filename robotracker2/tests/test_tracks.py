"""Test de tipos de pista (icono + nombre) por canción.

La clave "tracks" del robotraca.json lista 8 tipos (drum/bass/synth/noise/
robot/vocoder). Sin la clave se usan DEFAULT_TRACKS. La pantalla TRACKS
está debajo de PADS (L2+abajo) y guarda con su fila GUARDAR.

Flujo sobre canciones copiadas a un directorio temporal (nunca toca los
robotraca.json versionados de sinte/songs/):

  1. parse_tracks: defaults, lista, dict 1-based, valores inválidos.
  2. Cargar canción sin "tracks" -> defaults en SONG/CHAIN/PHRASE/TRACKS.
  3. L2+IZQ (SONG->PADS) y L2+ABJ (PADS->TRACKS) navegan a la pantalla.
  4. IZQ/DCH ciclan el tipo EN MEMORIA; el JSON no cambia hasta guardar.
  5. Fila GUARDAR (A) persiste; Guardar canción también.
  6. El tipo se refleja en la cabecera de SONG y en CHAIN/PHRASE.
  7. Con pistas sin guardar, cambiar de canción pide confirmación.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, DOWN, L2, LEFT, RIGHT, SELECT, UP  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402
from tracks import (DEFAULT_TRACKS, EXTRA_TRACK, TRACK_DISPLAY, cycle_kind,
                    parse_tracks, slot_of, track_at_slot, track_caption,
                    track_label)  # noqa: E402


def test_parse_tracks():
    assert parse_tracks({}) == list(DEFAULT_TRACKS)
    assert parse_tracks(None) == list(DEFAULT_TRACKS)
    got = parse_tracks({"tracks": ["noise"]})
    assert got[0] == "noise"
    assert got[1:] == list(DEFAULT_TRACKS[1:])
    got = parse_tracks({"tracks": {"1": "vocoder", "8": "drum"}})
    assert got[0] == "vocoder" and got[7] == "drum"
    got = parse_tracks({"tracks": ["nope", "bass"]})
    assert got[0] == DEFAULT_TRACKS[0] and got[1] == "bass"
    assert cycle_kind("drum", 1) == "bass"
    assert cycle_kind("vocoder", 1) == "drum"
    assert cycle_kind("drum", -1) == "vocoder"
    assert track_label("synth") == "SYNTH"
    assert TRACK_DISPLAY == (EXTRA_TRACK, 0, 1, 2, 3, 4, 5, 6, 7)
    assert slot_of(EXTRA_TRACK) == 0 and track_at_slot(0) == EXTRA_TRACK
    assert slot_of(6) == 7 and track_at_slot(8) == 7
    assert track_caption(EXTRA_TRACK, "synth") == "1 SYNTH"
    assert track_caption(0, "drum") == "2 DRUM"
    assert track_caption(7, kinds=list(DEFAULT_TRACKS)) == "9 ROBOT"
    print("  parse_tracks / cycle_kind OK")


def _canción_origen():
    for song_dir in sorted(Path(DEFAULT_SONGS).iterdir()):
        if (song_dir / "lgptsav.dat").is_file():
            return song_dir
    raise AssertionError(f"ninguna canción con lgptsav.dat en "
                         f"{DEFAULT_SONGS}")


def _cfg_song(song):
    return json.loads((song / "robotraca.json").read_text())


def _run(app, song_a, song_b):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    app._midi_ctrl.close()

    # --- canción A sin "tracks": defaults --------------------------------
    app._request_load(song_a)
    assert app.editor_screen.current == "song"
    kinds = app.editor_screen.song_grid.tracks
    assert kinds == list(DEFAULT_TRACKS), kinds
    assert app.editor_screen.tracks_grid.kinds == list(DEFAULT_TRACKS)
    print("  canción sin 'tracks': defaults OK")

    # --- L2+IZQ (SONG->PADS) y L2+ABJ (PADS->TRACKS) ---------------------
    app._dispatch(L2, {L2})
    app._dispatch(LEFT, {LEFT, L2})
    assert app.editor_screen.current == "pads"
    app._dispatch(DOWN, {DOWN, L2})
    assert app.editor_screen.current == "tracks", app.editor_screen.current
    g = app.editor_screen.tracks_grid
    assert g.cursor == 0, g.cursor
    print("  PADS + L2+ABJ -> pantalla TRACKS OK")

    # --- IZQ/DCH ciclan el tipo EN MEMORIA -------------------------------
    app._dispatch(RIGHT, {RIGHT})
    assert g.kinds[EXTRA_TRACK] == "noise", g.kinds[EXTRA_TRACK]
    assert app.editor_screen.song_grid.tracks[EXTRA_TRACK] == "noise"
    assert app._tracks_dirty
    assert "tracks" not in _cfg_song(song_a), \
        "sin guardar, el robotraca.json no cambia"
    print("  ciclar tipo en memoria (sin persistir) OK")

    # --- SELECT no guarda ------------------------------------------------
    app._dispatch(SELECT, {SELECT})
    assert app._tracks_dirty
    assert "tracks" not in _cfg_song(song_a)
    print("  SELECT no guarda OK")

    # --- fila GUARDAR (A) persiste ---------------------------------------
    for _ in range(9):
        app._dispatch(DOWN, {DOWN})
    assert g.cursor == g.SAVE_ROW, g.cursor
    app._dispatch(A, {A})
    cfg = _cfg_song(song_a)
    assert cfg["tracks"][EXTRA_TRACK] == "noise", cfg
    assert cfg["tracks"][:EXTRA_TRACK] == list(DEFAULT_TRACKS[:EXTRA_TRACK])
    assert not app._tracks_dirty
    print("  fila GUARDAR (A) guarda el robotraca.json OK")

    # --- se ve en CHAIN y PHRASE -----------------------------------------
    app._dispatch(L2, {L2})
    app._dispatch(UP, {UP, L2})          # TRACKS -> PADS
    app._dispatch(RIGHT, {RIGHT, L2})    # PADS -> SONG
    assert app.editor_screen.current == "song"
    app.editor_screen.song_grid.cursor_track = EXTRA_TRACK
    app._dispatch(RIGHT, {RIGHT, L2})    # SONG -> CHAIN
    assert app.editor_screen.current == "chain"
    assert "NOISE" in app.editor_screen._header_text()
    assert "1 NOISE" in app.editor_screen._header_text()
    assert app.editor_screen.chain_grid.tracks[EXTRA_TRACK] == "noise"
    app._dispatch(RIGHT, {RIGHT, L2})    # CHAIN -> PHRASE
    assert app.editor_screen.current == "phrase"
    assert "1 NOISE" in app.editor_screen._header_text()
    assert app.editor_screen.phrase_grid.tracks[EXTRA_TRACK] == "noise"
    print("  icono/nombre/número en CHAIN y PHRASE OK")

    # --- EFECTOS también ve el tipo del canal ----------------------------
    app._dispatch(LEFT, {LEFT, L2})      # PHRASE -> CHAIN
    app._dispatch(LEFT, {LEFT, L2})      # CHAIN -> SONG
    app._dispatch(LEFT, {LEFT, L2})      # SONG -> PADS
    app._dispatch(UP, {UP, L2})          # PADS -> EFECTOS
    assert app.editor_screen.current == "pots"
    assert app.editor_screen.pots_grid.tracks[EXTRA_TRACK] == "noise"
    print("  EFECTOS muestra el tipo de la pista OK")

    # --- volver a TRACKS, cambiar y pedir confirmación al cargar B -------
    app._dispatch(DOWN, {DOWN, L2})      # EFECTOS -> PADS
    app._dispatch(DOWN, {DOWN, L2})      # PADS -> TRACKS
    g = app.editor_screen.tracks_grid
    g.cursor = 0
    app._dispatch(RIGHT, {RIGHT})        # noise -> robot
    assert g.kinds[EXTRA_TRACK] == "robot"
    assert app._tracks_dirty
    app._request_load(song_b)
    assert app.dialog is not None, "pistas sin guardar deben pedir confirmación"
    app.dialog.index = 1                 # Descartar
    app._dialog_choose()
    assert app._song_dir == song_b
    assert app.editor_screen.song_grid.tracks == list(DEFAULT_TRACKS)
    print("  confirmación al cambiar con pistas sin guardar OK")

    # --- A conserva lo guardado (noise, no robot) -------------------------
    app._request_load(song_a)
    assert app.editor_screen.song_grid.tracks[EXTRA_TRACK] == "noise"
    print("  pistas guardadas por canción OK")

    # --- Guardar canción también persiste --------------------------------
    app._dispatch(L2, {L2})
    app._dispatch(LEFT, {LEFT, L2})
    app._dispatch(DOWN, {DOWN, L2})
    g = app.editor_screen.tracks_grid
    g.cursor = 3                          # visual 4 = canal LGPT 2 (synth)
    app._dispatch(LEFT, {LEFT})          # synth -> bass
    assert g.kinds[2] == "bass"
    app._save()
    assert _cfg_song(song_a)["tracks"][2] == "bass"
    assert not app._tracks_dirty
    print("  Guardar la canción persiste las pistas OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    test_parse_tracks()

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        origen = _canción_origen()
        song_a = songs_dir / "lgpt_a_tracks"
        song_b = songs_dir / "lgpt_b_tracks"
        shutil.copytree(origen, song_a)
        shutil.copytree(origen, song_b)
        for song in (song_a, song_b):
            (song / "robotraca.json").write_text(
                json.dumps({"pad_volume": 50}) + "\n")

        app = Robotracker2App(songs_dir=songs_dir, samples_dir=tmp)

        def _go(_dt):
            try:
                _run(app, song_a, song_b)
                print("TODOS LOS TESTS OK")
            except Exception as exc:                 # noqa: BLE001
                import traceback
                traceback.print_exc()
            finally:
                app.stop()

        Clock.schedule_once(_go, 0)
        app.run()


if __name__ == "__main__":
    main()
