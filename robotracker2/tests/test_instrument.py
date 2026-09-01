"""Test de la pantalla INSTRUMENT (layout por secciones, edición estilo LGPT).

Flujo e2e sobre una canción copiada a un directorio temporal (nunca toca las
canciones versionadas de sinte/songs/): cargar, entrar en INSTRUMENT y
comprobar:
- layout Sample por secciones: están los campos que el engine implementa
  (drive, attenuate, start, end incluidos) y NO los que no implementa
  (print fx / effect amount / feedback mix quedan fuera de la UI)
- edición estilo LGPT: A+arr/abj = paso grande, A+izq/dcha = paso fino;
  el dpad solo (move) no cambia valores; izq/dcha salta entre parejas
- instrumentos MIDI (type="Midi"): channel / note length / volume / table
- roundtrip guardar+recargar: los params fuera de la UI se conservan
  (writer actualiza VALUE en sitio y no toca lo demás)
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, DOWN, LEFT, RIGHT, UP  # noqa: E402
from lgpt_model import load_project  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _cancion_origen():
    """Cualquier canción real de sinte/songs (solo se usa su lgptsav.dat)."""
    for song_dir in sorted(Path(DEFAULT_SONGS).iterdir()):
        if (song_dir / "lgptsav.dat").is_file():
            return song_dir
    raise AssertionError(f"ninguna canción con lgptsav.dat en "
                         f"{DEFAULT_SONGS}")


def _fields(m):
    """claves de todos los slots del layout actual del menú."""
    return [sl[0] for _kind, payload in m._layout()
            if _kind == "row" for sl in payload]


def _row_of(m, key):
    """(item_idx, slot) de la fila que contiene el campo `key`."""
    for i, it in enumerate(m._layout()):
        if it[0] == "row":
            for s, sl in enumerate(it[1]):
                if sl[0] == key:
                    return i, s
    raise AssertionError(f"campo {key} no está en el layout")


def _navigate(m, row_idx, slot=0):
    """posiciona el cursor en (fila, slot) usando move() (solo foco)."""
    rows = [i for i, it in enumerate(m._layout()) if it[0] == "row"]
    m._reset_cursor()
    while m.row_idx != row_idx:
        m.move(DOWN if rows.index(m.row_idx) < rows.index(row_idx) else UP)
    if slot:
        m.move(RIGHT)


def _e2e(app, song):
    from robotracker2 import Robotracker2App  # noqa: E402

    assert isinstance(app, Robotracker2App)
    app._midi_ctrl.close()      # sin puertos reales en los tests
    app._request_load(song)
    ed = app.editor_screen
    assert ed.current == "song"
    p = ed.project
    ed.goto("instrument")
    m = ed.instrument_menu

    # inyectar un instrumento MIDI conocido (el banco puede no tener ninguno)
    p.instrument_bank[0x85] = {"type": "Midi",
                               "params": {"channel": "3", "note length": "5",
                                          "volume": "200", "table": "-1"}}
    m.set_project(p)            # re-cachea instr_ids

    # --- layout Sample ---------------------------------------------------
    sample_iid = next(i for i in sorted(p.instrument_bank)
                      if p.instrument_bank[i]["type"] == "Sample")
    m.select_instrument(sample_iid)
    keys = set(_fields(m))
    assert {"__instr__", "sample", "volume", "pan", "root note", "fine tune",
            "crush", "crushdrive", "downsample", "filter cut", "filter res",
            "filter type", "filter mode", "attenuate", "loopmode", "start",
            "end", "table"} <= keys, keys
    assert not ({"print fx", "effect amount", "feedback mix"} & keys), keys
    print("  layout Sample con secciones OK")

    # valores controlados para las aserciones de edición
    params = p.instrument_bank[sample_iid]["params"]
    params.update({"volume": "100", "root note": "60", "crush": "16",
                   "crushdrive": "200", "start": "0", "loopmode": "none",
                   "filter cut": "100"})

    # --- move() solo mueve el foco, no edita ------------------------------
    ri, si = _row_of(m, "volume")
    _navigate(m, ri, si)
    before = dict(params)
    m.move(DOWN)
    m.move(UP)
    m.move(LEFT)                      # fila de un solo campo: no hace nada
    assert params == before, "move() no debe cambiar valores"
    print("  move() solo foco OK")

    # --- A+dir vía dispatch: A+UP paso grande ------------------------------
    app._dispatch(UP, {UP, A})        # A+arr: +16
    app._release(A)
    assert params["volume"] == "116", params["volume"]
    m.edit(UP)                        # +16
    assert params["volume"] == "132", params["volume"]
    m.edit(DOWN)                      # -16
    m.edit(RIGHT)                     # +1 (fino)
    assert params["volume"] == "117", params["volume"]
    m.edit(LEFT)                      # -1 (fino)
    assert params["volume"] == "116", params["volume"]
    print("  edición A+arr/abj (grande) y A+izq/dcha (fino) OK")

    # --- note: fino ±1, grande ±12 ----------------------------------------
    ri, si = _row_of(m, "root note")
    _navigate(m, ri, si)
    m.edit(UP)
    assert params["root note"] == "72", params["root note"]
    m.edit(LEFT)
    assert params["root note"] == "71", params["root note"]
    print("  root note ±12/±1 OK")

    # --- pareja crush+drive: izq/dcha cambia de slot -----------------------
    ri, si = _row_of(m, "crush")
    _navigate(m, ri, si)
    assert m.slot == 0 and m.field_key() == "crush"
    m.move(RIGHT)
    assert m.slot == 1 and m.field_key() == "crushdrive"
    m.edit(UP)                        # drive +16
    assert params["crushdrive"] == "216", params["crushdrive"]
    m.edit(LEFT)                      # drive -1
    assert params["crushdrive"] == "215", params["crushdrive"]
    m.move(LEFT)                      # vuelta a crush
    m.edit(RIGHT)                     # crush +1 (clamp a 16)
    assert params["crush"] == "16", params["crush"]
    print("  pareja crush+drive OK")

    # --- hex: paso fino ±1, grande ±0x1000 --------------------------------
    ri, si = _row_of(m, "start")
    _navigate(m, ri, si)
    m.edit(UP)
    assert params["start"] == "4096", params["start"]
    m.edit(RIGHT)
    assert params["start"] == "4097", params["start"]
    assert m._value_text(m._layout()[ri][1][si]) == "0001001", \
        m._value_text(m._layout()[ri][1][si])
    print("  start hex ±0x1000/±1 OK")

    # --- enum: cicla ------------------------------------------------------
    ri, si = _row_of(m, "loopmode")
    _navigate(m, ri, si)
    assert params["loopmode"] == "none"
    m.edit(UP)
    assert params["loopmode"] == "loop"
    m.edit(DOWN)
    assert params["loopmode"] == "none"
    print("  enum loopmode cicla OK")

    # --- instrumento MIDI -------------------------------------------------
    m.select_instrument(0x85)
    assert set(_fields(m)) == {"__instr__", "channel", "note length",
                               "volume", "table"}, _fields(m)
    ri, si = _row_of(m, "channel")
    _navigate(m, ri, si)
    m.edit(UP)                        # coarse +4
    assert p.instrument_bank[0x85]["params"]["channel"] == "7"
    m.edit(LEFT)                      # fino -1
    assert p.instrument_bank[0x85]["params"]["channel"] == "6"
    m.edit(UP)                        # +4
    assert p.instrument_bank[0x85]["params"]["channel"] == "10"
    print("  instrumento MIDI (channel/note length/volume/table) OK")

    # --- selector de instrumento (A+dir cicla el banco) --------------------
    m.select_instrument(sample_iid)
    _navigate(m, 0, 0)
    ids = m.instr_ids
    pos = m.pos_in_ids
    m.edit(UP)
    assert m.pos_in_ids == (pos + 16) % len(ids), (m.pos_in_ids, pos)
    m.edit(DOWN)
    assert m.pos_in_ids == pos
    print("  selector de instrumento cicla OK")

    # --- roundtrip: los params fuera de la UI se conservan -----------------
    params["print fx"] = "hall"
    params["effect amount"] = "33"
    params["feedback mix"] = "77"
    params["interpol"] = "none"
    params["slices"] = "4"
    app._save()
    assert not app.dirty
    reloaded = load_project(song)
    rp = reloaded.instrument_bank[sample_iid]["params"]
    assert rp["print fx"] == "hall", rp.get("print fx")
    assert rp["effect amount"] == "33", rp.get("effect amount")
    assert rp["feedback mix"] == "77", rp.get("feedback mix")
    assert rp["interpol"] == "none", rp.get("interpol")
    assert rp["slices"] == "4", rp.get("slices")
    assert rp["volume"] == params["volume"], "los editados también persisten"
    print("  roundtrip: params fuera de la UI se conservan OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        song = songs_dir / "lgpt_instr"
        shutil.copytree(_cancion_origen(), song)

        app = Robotracker2App(songs_dir=songs_dir, samples_dir=tmp)

        def _go(_dt):
            try:
                _e2e(app, song)
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
