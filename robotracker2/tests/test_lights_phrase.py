"""PHRASE de la pista LUCES: columnas COLOR / LUZ / FX (BRIL, FADE, STRB).

Unitario sobre un proyecto sintético (PhraseGrid sin app): editar cada
columna escribe los bytes que luego lee el engine (sinte/lights.py).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from controls import A, DOWN, LEFT, RIGHT, UP  # noqa: E402
from lgpt_model import EMPTY, LIGHTS_TRACK, SongView  # noqa: E402
from screens.phrase_view import LIGHTS_COLS, PhraseGrid  # noqa: E402
from sinte_bridge import LIGHT_FX, PALETTE  # noqa: E402
from test_ensure_track0 import _make_project  # noqa: E402


def _grid():
    import tempfile
    p = _make_project(Path(tempfile.mkdtemp()))
    SongView(p).new_chain(0, LIGHTS_TRACK)
    g = PhraseGrid()
    g.set_context(p, 0, LIGHTS_TRACK, 0)
    # editar un hueco crea la phrase; forzamos una para el test
    assert g.pv is not None
    return p, g


def _row(g, step=0):
    return g.pv._index(step, LIGHTS_TRACK)


def test_columnas_y_color():
    p, g = _grid()
    assert [k for k, _w in g._cols()] == [k for k, _w in LIGHTS_COLS]
    g.cursor_col = 0                               # COLOR
    g.edit(RIGHT)                                  # vacío -> ROJO
    i = _row(g)
    assert i is not None, "editar crea chain/phrase"
    assert p.notes[i] == 1 and g._field_text(0, 0) == "ROJO"
    g.edit(RIGHT)
    assert g._field_text(0, 0) == PALETTE[2][0]
    g.edit(LEFT)
    g.edit(LEFT)
    assert p.notes[i] == 0 and g._field_text(0, 0) == "APAGA"
    assert p.instruments[i] == EMPTY, "COLOR no toca el instrumento"
    print("  COLOR cicla la paleta OK")


def test_luz():
    p, g = _grid()
    g.cursor_col = 0
    g.edit(RIGHT)
    i = _row(g)
    g.cursor_col = 1                               # LUZ
    assert g._field_text(0, 1) == "TODAS"
    g.edit(RIGHT)
    assert p.instruments[i] == 1 and g._field_text(0, 1) == "IZQ"
    g.edit(RIGHT)
    assert g._field_text(0, 1) == "DER"
    g.edit(RIGHT)
    assert p.instruments[i] == EMPTY, "vuelve a TODAS"
    print("  LUZ cicla TODAS/IZQ/DER OK")


def test_fx_de_luz():
    p, g = _grid()
    g.cursor_col = 2                               # FX1 cmd
    assert g._fx_cmds() == list(LIGHT_FX)
    g.edit(RIGHT)
    i = _row(g)
    assert p.cmd1[i] == "BRIL" and p.param1[i] == 0xFF, (p.cmd1[i], p.param1[i])
    g.cursor_col = 3                               # FX1 param
    g.edit(DOWN)                                   # -16
    assert p.param1[i] == 0xEF and g._field_text(0, 3) == "EF"
    g.cursor_col = 2
    g.edit(RIGHT)
    assert p.cmd1[i] == "FADE" and p.param1[i] == 4
    g.cursor_col = 3
    g.edit(UP)
    assert p.param1[i] == 8 and g._field_text(0, 3) == "08"
    g.cursor_col = 4                               # FX2: A pone el primero
    g.a_tap()
    assert p.cmd2[i] == "BRIL" and p.param2[i] == 0xFF
    g.open_fx_picker()
    g.fx_picker_move(2)
    g.apply_fx_picker()
    assert p.cmd2[i] == "STRB" and p.param2[i] == 0x80
    print("  FX de luz (BRIL/FADE/STRB) OK")


def test_nota_en_vivo_es_color():
    p, g = _grid()
    g.cursor_col = 0
    g.edit(RIGHT)
    g.live_note(0, 60 + 6, 100)                    # F#: índice 6 = AZUL
    i = _row(g)
    assert g._field_text(0, 0) == PALETTE[6][0]
    assert p.cmd1[i] == "----", "sin VOLM en la pista de luces"
    print("  nota en vivo -> color OK")


def main():
    test_columnas_y_color()
    test_luz()
    test_fx_de_luz()
    test_nota_en_vivo_es_color()
    print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
