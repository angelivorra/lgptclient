"""Test de la pantalla PADS: pads sampler POR CANCIÓN (robotraca.json).

Los pads NO tienen configuración global: cada canción define los suyos en
la clave "pads" del robotraca.json, resueltos contra la biblioteca de
pads (pads/ junto al repo; en el test, <tmp>/pads). Sin la clave, los
pads de la canción están VACÍOS.

Flujo completo sobre canciones copiadas a un directorio temporal (nunca
toca los robotraca.json versionados de sinte/songs/):

  1. Cargar canción sin clave "pads" -> pads vacíos ("—", vol. 50).
  2. L2+IZQ desde SONG navega a PADS (a la izquierda de SONG).
  3. IZQ/DCH cambian el volumen -/+5 EN MEMORIA (no persisten hasta
     guardar); SELECT ya NO guarda: guarda la fila GUARDAR de abajo
     (cursor 4) con A.
  4. A abre el navegador de la biblioteca de pads (no la general);
     _pads_sample_loaded asigna el wav por su nombre relativo a la
     biblioteca (sin copiarlo a la canción), suena en vivo (engine) y
     renderiza audio AUNQUE la canción no se esté reproduciendo (el
     disparo pasa por el hook on_trigger, que asegura el stream);
     Guardar la canción también persiste.
  5. B quita la asignación en memoria.
  6. Con pads sin guardar, cambiar de canción pide confirmación
     (descartar pierde el cambio); cada canción conserva lo guardado y
     la que no tiene "pads" sigue vacía (sin banco global).
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, B, DOWN, LEFT, L2, RIGHT, SELECT, UP  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _canción_origen():
    """Cualquier canción real de sinte/songs (solo se usa su lgptsav.dat)."""
    for song_dir in sorted(Path(DEFAULT_SONGS).iterdir()):
        if (song_dir / "lgptsav.dat").is_file():
            return song_dir
    raise AssertionError(f"ninguna canción con lgptsav.dat en "
                         f"{DEFAULT_SONGS}")


def _escribir_wav(path):
    data = (0.3 * np.sin(2 * np.pi * 440 * np.arange(4410) / 44100)
            )[:, None].astype(np.float32)
    sf.write(str(path), data, 44100)


def _cfg_song(song):
    return json.loads((song / "robotraca.json").read_text())


def _run(app, song_a, song_b, pads_dir):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    app._midi_ctrl.close()      # sin puertos reales en los tests

    # --- cargar la canción A: sin "pads" -> pads VACÍOS ------------------
    app._request_load(song_a)
    assert app.editor_screen.current == "song"
    estado = app.editor_screen.pads_grid.pads
    assert estado[0] == (None, 50), estado
    print("  canción sin 'pads': pads vacíos (sin banco global) OK")

    # --- L2+IZQ desde SONG navega a PADS (a la izquierda) ----------------
    app._dispatch(L2, {L2})
    app._dispatch(LEFT, {LEFT, L2})
    assert app.editor_screen.current == "pads", app.editor_screen.current
    g = app.editor_screen.pads_grid
    assert g.cursor == 0, g.cursor
    print("  L2+IZQ -> pantalla PADS OK")

    # --- IZQ/DCH: volumen -/+5 EN MEMORIA, no se persiste aún ------------
    app._dispatch(RIGHT, {RIGHT})
    assert g.pads[0] == (None, 55), g.pads
    assert app._pads_dirty, "cambiar el volumen marca pads sin guardar"
    assert _cfg_song(song_a) == {"pad_volume": 50}, \
        "sin guardar, el robotraca.json no cambia"
    print("  volumen ±5 en memoria (sin persistir) OK")

    # --- SELECT ya NO guarda ---------------------------------------------
    app._dispatch(SELECT, {SELECT})
    assert app._pads_dirty, "SELECT debe quedar sin efecto"
    assert _cfg_song(song_a) == {"pad_volume": 50}, \
        "SELECT ya no persiste los pads"
    print("  SELECT ya no guarda OK")

    # --- fila GUARDAR (abajo, cursor 4): solo A guarda -------------------
    for _ in range(4):
        app._dispatch(DOWN, {DOWN})
    assert g.cursor == g.SAVE_ROW, g.cursor
    app._dispatch(RIGHT, {RIGHT})       # en GUARDAR: sin efecto
    app._dispatch(B, {B})               # tampoco
    assert g.pads[0] == (None, 55), g.pads
    assert app._pads_dirty, "GUARDAR sin A no persiste"
    app._dispatch(A, {A})
    cfg = _cfg_song(song_a)
    assert cfg["pad_volume"] == {"1": 55, "2": 50, "3": 50, "4": 50}, cfg
    assert not app._pads_dirty
    print("  fila GUARDAR (A) guarda el robotraca.json OK")

    # volver a la fila del pad 1 para el resto del flujo
    for _ in range(4):
        app._dispatch(UP, {UP})
    assert g.cursor == 0, g.cursor

    # --- A abre el navegador de la biblioteca de pads, no la general -----
    app._dispatch(A, {A})
    assert app.browser is not None, "A debe abrir el navegador"
    assert app._pads_pad == 1, app._pads_pad
    assert app.browser.root == pads_dir, \
        f"el navegador de pads debe enseñar la biblioteca pads/ " \
        f"(enseña {app.browser.root})"

    # cargar un wav de la biblioteca: se asigna por su nombre relativo
    # (SIN copiarlo a la canción) y el engine lo carga en vivo
    app._pads_sample_loaded(pads_dir / "nuevo.wav")
    assert not (song_a / "pads").exists(), \
        "los wav de pads viven en la biblioteca, no se copian a la canción"
    assert not (song_a / "samples" / "nuevo.wav").exists(), \
        "tampoco van a samples/ de la canción"
    assert g.pads[0] == ("nuevo.wav", 55), g.pads
    assert app.player.engine.pad_names[0] == "nuevo.wav", \
        "el pad debe cargarse en vivo en el engine"
    assert app.browser is None, "el navegador debe cerrarse al cargar"
    assert not app.dirty, "asignar un pad no ensucia el lgptsav.dat"
    assert app._pads_dirty
    assert "pads" not in _cfg_song(song_a), "sin guardar no hay clave 'pads'"
    print("  A + carga de wav de la biblioteca pads/ OK")

    # --- los pads suenan AUNQUE la canción no se esté reproduciendo ------
    assert not app.player.playing, "el flujo aún no ha reproducido nada"
    # el disparo MIDI pasa por el hook on_trigger, que asegura el stream
    # de audio (perezoso: no se creó al cargar la canción)
    from player import Player
    llamadas = []
    Player._ensure_stream = lambda self: llamadas.append(1) or False
    assert app.player._stream is None, "el stream no debe existir aún"
    assert app._midi_ctrl.engine_ref["on_trigger"] is not None
    app._midi_ctrl.engine_ref["on_trigger"]()
    assert llamadas == [1], "disparar un pad debe asegurar el stream"
    # y el trigger renderiza audio sin reproducción: el Voice del pad se
    # dibuja en render() aunque el secuenciador esté parado
    app.player.engine.push_event("trigger", 0)
    out = app.player.engine.render(64)
    assert np.abs(out).max() > 0, "el pad debe sonar sin reproducción"
    print("  pads suenan sin reproducir (hook + render del engine) OK")

    # --- Guardar la canción también persiste los pads --------------------
    app._save()
    cfg = _cfg_song(song_a)
    assert cfg["pads"] == {"1": "nuevo.wav"}, cfg
    assert not app._pads_dirty
    print("  Guardar la canción persiste los pads OK")

    # --- B quita la asignación (en memoria) ------------------------------
    app._dispatch(B, {B})
    assert g.pads[0] == (None, 55), g.pads
    assert app.player.engine.pad_names[0] is None
    assert _cfg_song(song_a)["pads"] == {"1": "nuevo.wav"}, \
        "sin guardar, B no toca el JSON"
    print("  B quita en memoria OK")

    # --- pads sin guardar: cambiar de canción pide confirmación ----------
    app._request_load(song_b)
    assert app.dialog is not None, "pads sin guardar deben pedir confirmación"
    app.dialog.index = 1          # Descartar
    app._dialog_choose()
    assert app._song_dir == song_b, app._song_dir
    estado = app.editor_screen.pads_grid.pads
    assert estado[0] == (None, 50), estado
    print("  confirmación al cambiar con pads sin guardar OK")

    # --- la canción A conserva lo guardado (el B descartado no cuenta) ---
    app._request_load(song_a)
    estado = app.editor_screen.pads_grid.pads
    assert estado[0] == ("nuevo.wav", 55), estado
    print("  pads guardados por canción OK")

    # --- wav en subcarpeta: nombre relativo a la biblioteca --------------
    app._dispatch(L2, {L2})
    app._dispatch(LEFT, {LEFT, L2})
    app._dispatch(A, {A})
    app._pads_sample_loaded(pads_dir / "Sub" / "sub.wav")
    assert g.pads[0] == ("Sub/sub.wav", 55), g.pads
    assert app.player.engine.pad_names[0] == "Sub/sub.wav"
    print("  subcarpeta de la biblioteca pads/ OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        origen = _canción_origen()
        song_a = songs_dir / "lgpt_a_pads"
        song_b = songs_dir / "lgpt_b_pads"
        shutil.copytree(origen, song_a)
        shutil.copytree(origen, song_b)
        # robotraca.json controlado (nunca los versionados de sinte/songs)
        for song in (song_a, song_b):
            (song / "robotraca.json").write_text(
                json.dumps({"pad_volume": 50}) + "\n")
        # biblioteca de pads (la app la deriva de songs_dir: <tmp>/pads)
        pads_dir = tmp / "pads"
        pads_dir.mkdir()
        _escribir_wav(pads_dir / "nuevo.wav")
        (pads_dir / "Sub").mkdir()
        _escribir_wav(pads_dir / "Sub" / "sub.wav")

        app = Robotracker2App(songs_dir=songs_dir, samples_dir=tmp)

        def _go(_dt):
            try:
                _run(app, song_a, song_b, pads_dir)
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
