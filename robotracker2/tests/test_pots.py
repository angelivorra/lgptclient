"""Test de la pantalla EFECTOS: knobs por canción (robotraca.json).

Los knobs del controlador (solo POT 1/2/5/6) se configuran POR CANCIÓN:
clave "pots" ("canal:efecto") + "fx_mix" para el porcentaje de mezcla.
La pantalla EFECTOS está ENCIMA de PADS (L2+arriba desde PADS) y, como
PADS, guarda con su fila GUARDAR (select no hace nada). La edición es
estilo tracker: A+arr/abj cicla el canal, A sobre el efecto abre una
LISTA (arr/abj mueve, A elige, B cierra) y el % va con A+izq/dcha fino
(±1) y A+arr/abj de 10 en 10.

Flujo completo sobre canciones copiadas a un directorio temporal (nunca
toca los robotraca.json versionados de sinte/songs/):

  1. Cargar canción con "pots"/"fx_mix" -> EFECTOS muestra canal/efecto/%.
  2. L2+IZQ (SONG->PADS) y L2+ARR (PADS->EFECTOS) navegan a la pantalla.
  3. Todo EN MEMORIA (robotraca.json intacto hasta guardar) y en vivo
     (targets del MIDI y fx_mix del engine).
  4. Fila GUARDAR (abajo, cursor 4): A guarda; select no guarda.
  5. Con knobs sin guardar, cambiar de canción pide confirmación
     (descartar pierde el cambio); la canción conserva lo guardado.
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

from controls import A, B, DOWN, L2, LEFT, RIGHT, SELECT, UP  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _canción_origen():
    """Cualquier canción real de sinte/songs (solo se usa su lgptsav.dat)."""
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
    app._midi_ctrl.close()      # sin puertos reales en los tests

    # --- cargar la canción A: "pots" + "fx_mix" -------------------------
    app._request_load(song_a)
    assert app.editor_screen.current == "song"
    estado = app.editor_screen.pots_grid.pots
    assert estado == [(3, "acid", 40), (None, None, 100),
                      (None, None, 100), (None, None, 100)], estado
    print("  canción con 'pots': estado inicial OK")

    # --- L2+IZQ (SONG->PADS) y L2+ARR (PADS->EFECTOS) -------------------
    app._dispatch(L2, {L2})
    app._dispatch(LEFT, {LEFT, L2})
    assert app.editor_screen.current == "pads"
    app._dispatch(UP, {UP, L2})
    assert app.editor_screen.current == "pots", app.editor_screen.current
    g = app.editor_screen.pots_grid
    assert g.cursor == 0 and g.col == 0, (g.cursor, g.col)
    print("  PADS + L2+ARR -> pantalla EFECTOS OK")

    # --- columna canal: A+arr/abj cicla (A suelta no hace nada) ----------
    app._dispatch(A, {A})
    assert g.pots[0] == (3, "acid", 40) and not app._pots_dirty
    app._dispatch(UP, {UP, A})          # A mantenida + arriba
    assert g.pots[0] == (4, "acid", 100), g.pots
    assert app._pots_dirty
    assert app._midi_ctrl._cfg["pots"] == {"pot1": "3:acid"}
    assert _cfg_song(song_a)["pots"] == {"pot1": "2:acid"}, \
        "sin guardar, el robotraca.json no cambia"
    print("  canal con A+arr/abj, en memoria OK")

    # --- columna efecto: A abre la LISTA, arr/abj mueve, A elige, B cierra
    app._dispatch(RIGHT, {RIGHT})       # columna efecto
    assert g.col == 1
    app._dispatch(A, {A})
    assert g.picker == 2, g.picker      # "acid" en la lista (off, valve...)
    app._dispatch(B, {B})               # B cierra sin cambiar nada
    assert g.picker is None
    assert g.pots[0] == (4, "acid", 100)
    app._dispatch(A, {A})               # reabre en el efecto actual
    assert g.picker == 2
    app._dispatch(DOWN, {DOWN})         # acid -> acid_lfo
    assert g.picker == 3
    app._dispatch(A, {A})               # elegir
    assert g.picker is None
    assert g.pots[0][1] == "acid_lfo", g.pots
    assert app._midi_ctrl._cfg["pots"] == {"pot1": "3:acid_lfo"}
    print("  lista de efectos (A abre, A elige, B cierra) OK")

    # --- columna %: A+izq/dcha fino, A+arr/abj de 10 en 10 ---------------
    app._dispatch(RIGHT, {RIGHT})       # columna %
    assert g.col == 2
    app._dispatch(DOWN, {DOWN, A})      # -10: 100 -> 90
    assert g.pots[0] == (4, "acid_lfo", 90), g.pots
    app._dispatch(RIGHT, {RIGHT, A})    # fino +1: 90 -> 91
    assert g.pots[0] == (4, "acid_lfo", 91), g.pots
    assert app._midi_ctrl._cfg["fx_mix"] == {"2": {"acid": 40},
                                             "3": {"acid_lfo": 91}}
    # el fx_mix entra al engine por push_event (sin reproducir nada)
    app.player.engine._drain_events()
    assert app.player.engine.channels[3].fx_mix["acid_lfo"] == 0.91
    # SELECT no guarda
    app._dispatch(SELECT, {SELECT})
    assert app._pots_dirty and _cfg_song(song_a)["pots"] == {"pot1": "2:acid"}
    print("  % fino/grueso en fx_mix (memoria + engine) y select inerte OK")

    # --- fila GUARDAR (abajo, cursor 4): solo A guarda -------------------
    for _ in range(4):
        app._dispatch(DOWN, {DOWN})
    assert g.cursor == g.SAVE_ROW, g.cursor
    app._dispatch(LEFT, {LEFT})         # en GUARDAR: sin efecto
    assert g.pots[0] == (4, "acid_lfo", 91)
    app._dispatch(A, {A})
    cfg = _cfg_song(song_a)
    assert cfg["pots"] == {"pot1": "3:acid_lfo"}, cfg
    assert cfg["fx_mix"] == {"2": {"acid": 40}, "3": {"acid_lfo": 91}}, cfg
    assert not app._pots_dirty
    print("  fila GUARDAR (A) guarda el robotraca.json OK")

    # volver a la fila del POT 1
    for _ in range(4):
        app._dispatch(UP, {UP})
    assert g.cursor == 0

    # --- knobs sin guardar: cambiar de canción pide confirmación ---------
    app._dispatch(LEFT, {LEFT})         # columna % -> efecto -> canal (2->0)
    app._dispatch(LEFT, {LEFT})
    assert g.col == 0
    app._dispatch(DOWN, {DOWN, A})      # canal 4 -> 3 (sin guardar)
    assert g.pots[0] == (3, "acid_lfo", 100), g.pots
    assert app._pots_dirty
    app._request_load(song_b)
    assert app.dialog is not None, "knobs sin guardar deben pedir confirmación"
    app.dialog.index = 1          # Descartar
    app._dialog_choose()
    assert app._song_dir == song_b, app._song_dir
    estado = app.editor_screen.pots_grid.pots
    assert estado == [(None, None, 100)] * 4, estado
    print("  confirmación al cambiar con knobs sin guardar OK")

    # --- la canción A conserva lo guardado (el cambio descartado no) -----
    app._request_load(song_a)
    estado = app.editor_screen.pots_grid.pots
    assert estado == [(4, "acid_lfo", 91), (None, None, 100),
                      (None, None, 100), (None, None, 100)], estado
    print("  knobs guardados por canción OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        origen = _canción_origen()
        song_a = songs_dir / "lgpt_a_pots"
        song_b = songs_dir / "lgpt_b_pots"
        shutil.copytree(origen, song_a)
        shutil.copytree(origen, song_b)
        # robotraca.json controlado (nunca los versionados de sinte/songs)
        (song_a / "robotraca.json").write_text(
            json.dumps({"pots": {"pot1": "2:acid"},
                        "fx_mix": {"2": {"acid": 40}},
                        "pad_volume": 50}) + "\n")
        (song_b / "robotraca.json").write_text(
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
