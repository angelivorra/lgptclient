"""CHRD en PHRASE: ciclado de comando y etiqueta del tipo de acorde."""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, B, DOWN, RIGHT, UP  # noqa: E402
from screens.phrase_view import FX_USED  # noqa: E402


def _run(app):
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    ed = app.editor_screen
    ed.goto("chain")
    ed.goto("phrase")
    pg = ed.phrase_grid
    t = pg.track
    assert "CHRD" in FX_USED, "CHRD debe poder ciclarse en PHRASE"
    assert "ARPR" in FX_USED, "ARPR debe poder ciclarse en PHRASE"

    pg.pv.set_note(0, t, 60)
    pg.pv.set_instr(0, t, 0)
    pg.pv.clear_fx(0, t, 1)
    pg.cursor_step = 0
    pg.cursor_col = 2                       # fx1cmd
    pg.edit(RIGHT)                          # primer comando = VOLM
    assert pg._cmd(0, 1) == FX_USED[0]
    for _ in range(len(FX_USED)):
        if pg._cmd(0, 1) == "CHRD":
            break
        pg.edit(RIGHT)
    assert pg._cmd(0, 1) == "CHRD", f"tras ciclar: {pg._cmd(0, 1)}"
    assert pg._prm(0, 1) == 0, "al elegir CHRD el tipo arranca en maj"
    pg.cursor_col = 3                       # fx1prm
    assert pg._field_text(0, 3).strip() == "maj"
    pg.edit(RIGHT)
    assert pg._prm(0, 1) == 1
    assert pg._field_text(0, 3).strip() == "min"
    print("  CHRD cicla tipos maj/min en PHRASE OK")

    pg.pv.set_fx_cmd(0, t, 1, "ARPR")
    pg.pv.set_fx_param(0, t, 1, 0)
    pg.cursor_col = 3
    assert pg._field_text(0, 3).strip() == "maj"
    pg.edit(RIGHT)
    assert pg._field_text(0, 3).strip() == "min"
    print("  ARPR cicla tipos maj/min en PHRASE OK")

    pg.pv.set_fx_cmd(0, t, 1, "CHRD")

    # A+arr/abj sobre el comando abre la lista con explicación
    pg.cursor_col = 2
    pg.edit(UP)
    assert pg.fx_picker is not None, "A+arr abre el picker de FX"
    assert pg.fx_commands[pg.fx_picker] == "CHRD", pg.fx_commands[pg.fx_picker]
    pg.fx_picker_move(-1)                   # CHRD -> SLID
    assert pg.fx_commands[pg.fx_picker] == "SLID"
    pg.apply_fx_picker()
    assert pg.fx_picker is None
    assert pg._cmd(0, 1) == "SLID", pg._cmd(0, 1)
    print("  picker de FX: A+arr abre, A elige OK")

    # arr en el primero va al último; abj en el último vuelve al primero
    pg.edit(UP)
    assert pg.fx_picker is not None
    pg.fx_picker = 0
    pg.fx_picker_move(-1)
    assert pg.fx_picker == len(pg.fx_commands) - 1, pg.fx_picker
    pg.fx_picker_move(1)
    assert pg.fx_picker == 0, pg.fx_picker
    pg.close_fx_picker()
    print("  picker de FX: wrap primero/último OK")

    pg.edit(DOWN)
    assert pg.fx_picker is not None
    before = pg._cmd(0, 1)
    pg.close_fx_picker()
    assert pg.fx_picker is None
    assert pg._cmd(0, 1) == before, "B/cancelar no cambia el comando"
    print("  picker de FX: cancelar no cambia el comando OK")

    # A+izq/dcha sigue ciclando sin abrir la lista
    pg.edit(RIGHT)
    assert pg.fx_picker is None
    assert pg._cmd(0, 1) == "CHRD", pg._cmd(0, 1)
    print("  A+dcha cicla FX sin abrir el picker OK")

    # dispatch: A+arr abre; arr/abj mueve; A aplica; B cierra
    pg.pv.set_fx_cmd(0, t, 1, FX_USED[-1])
    pg.edit(RIGHT)                          # último -> VOLM (wrap)
    assert pg._cmd(0, 1) == FX_USED[0]
    app._dispatch(UP, {UP, A})
    assert pg.fx_picker == 0, pg.fx_picker
    app._dispatch(DOWN, {DOWN})
    assert pg.fx_commands[pg.fx_picker] == FX_USED[1]
    app._dispatch(A, {A})
    assert pg.fx_picker is None
    assert pg._cmd(0, 1) == FX_USED[1]
    app._dispatch(UP, {UP, A})
    app._dispatch(B, {B})
    assert pg.fx_picker is None
    assert pg._cmd(0, 1) == FX_USED[1]
    print("  dispatch A+arr / A / B del picker OK")

    # SLID: param visible como "nota steps"; A+izq/dcha nota, A+arr/abj tiempo
    from sinte_bridge import note_byte_to_name, slid_pack, slid_unpack
    pg.pv.set_fx_cmd(0, t, 1, "SLID")
    pg.pv.set_fx_param(0, t, 1, slid_pack(72, 4))
    pg.cursor_col = 3                       # fx1prm
    assert pg._field_text(0, 3) == f"{note_byte_to_name(72)} 04", \
        pg._field_text(0, 3)
    pg.edit(RIGHT)                          # nota +1
    note, steps = slid_unpack(pg._prm(0, 1))
    assert note == 73 and steps == 4, (note, steps)
    pg.edit(UP)                             # tiempo +1
    note, steps = slid_unpack(pg._prm(0, 1))
    assert note == 73 and steps == 5, (note, steps)
    pg.edit(DOWN)
    note, steps = slid_unpack(pg._prm(0, 1))
    assert steps == 4
    print("  SLID muestra nota+tiempo y se edita por ejes OK")

    # FADE: param visible como filas decimales; A+izq/dcha ±1, A+arr/abj ±4
    pg.pv.set_fx_cmd(0, t, 1, "FADE")
    pg.pv.set_fx_param(0, t, 1, 0)
    pg.cursor_col = 3
    assert pg._field_text(0, 3) == "00", pg._field_text(0, 3)
    pg.edit(RIGHT)
    assert pg._prm(0, 1) == 1
    assert pg._field_text(0, 3) == "01"
    pg.edit(UP)
    assert pg._prm(0, 1) == 5
    pg.edit(DOWN)
    assert pg._prm(0, 1) == 1
    print("  FADE muestra filas y se edita por ejes OK")

    assert "FCUT" in FX_USED and "FRES" in FX_USED and "FMOD" in FX_USED
    pg.pv.set_fx_cmd(0, t, 1, "FCUT")
    pg.pv.set_fx_param(0, t, 1, 0)
    pg.cursor_col = 3
    assert pg._field_text(0, 3) == "muy sordo", pg._field_text(0, 3)
    pg.edit(UP)                             # +16
    assert pg._prm(0, 1) == 16
    pg.pv.set_fx_param(0, t, 1, 255)
    assert pg._field_text(0, 3) == "abierto", pg._field_text(0, 3)
    pg.pv.set_fx_cmd(0, t, 1, "FRES")
    pg.pv.set_fx_param(0, t, 1, 0)
    assert pg._field_text(0, 3) == "limpio", pg._field_text(0, 3)
    pg.pv.set_fx_cmd(0, t, 1, "FMOD")
    pg.pv.set_fx_param(0, t, 1, 2)          # lp
    assert pg._field_text(0, 3) == "grave", pg._field_text(0, 3)
    pg.edit(RIGHT)
    assert pg._field_text(0, 3) == "agudo", pg._field_text(0, 3)
    print("  FCUT/FRES/FMOD se leen en palabras OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    app = Robotracker2App()

    def _go(_dt):
        try:
            _run(app)
            print("TODOS LOS TESTS OK")
        except Exception:                            # noqa: BLE001
            import traceback
            traceback.print_exc()
        finally:
            app.stop()

    Clock.schedule_once(_go, 0)
    app.run()


if __name__ == "__main__":
    main()
