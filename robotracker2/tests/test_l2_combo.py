"""Test: L2/R2 + S no debe borrar la celda.

L2 (Ctrl izq) + S mutea; S sola borra al soltar. Si S llega antes que Ctrl,
o el SO repite S al soltar Ctrl, el combo consume el pulso y no borra.
R2+A con selección duplica; A tap sin L2 sigue copiando.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, B, DOWN, L2, R2  # noqa: E402
from lgpt_model import EMPTY  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _run(app):
    from robotracker2 import Robotracker2App  # noqa: E402

    # cargar la primera canción
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    assert app.editor_screen.current == "song"

    g = app.editor_screen.song_grid
    # ponemos un valor en la celda del cursor para verificar que no se borra
    r, t = g.cursor_row, g.cursor_track
    g.view.set_value(r, t, 0x05)
    assert g.view.chain_at(r, t) == 0x05, "celda debe tener valor 0x05"

    # --- flujo del usuario: L2 + B + A ---
    # 1) pulsa L2
    app._dispatch(L2, {L2})
    # 2) pulsa B (con L2 mantenido) — cicla selección, no borra al soltar
    app._dispatch(B, {B, L2})
    # 3) suelta B
    app._release(B)
    assert g.view.chain_at(r, t) == 0x05, \
        f"L2+S no debe borrar al soltar: {g.view.chain_at(r, t)}"
    if g.has_selection:
        g.cancel_selection()
    # 4) pulsa A (con L2, sin selección): no escribe
    app._dispatch(A, {A, L2})
    # 5) suelta A
    app._release(A)

    # la celda NO debe haberse cortado/borrado
    assert g.view.chain_at(r, t) == 0x05, \
        f"la celda se cortó: {g.view.chain_at(r, t)} != 0x05"
    print("  L2+B+A no corta la celda OK")

    # --- verificación: A tap normal (sin L2) SÍ funciona ---
    app._dispatch(A, {A})
    app._release(A)
    # a_tap copia la celda (no la borra) si tiene valor
    assert g.clipboard is not None, "a_tap normal debe copiar la celda"
    print("  A tap normal sigue funcionando OK")

    # --- verificación: R2+A (Ctrl+A) con selección duplica la chain ---
    # la celda (r, t) tiene 0x05; buscamos la siguiente chain libre mayor
    from lgpt_model import EMPTY
    used = {b for b in g.view.project.song if b != EMPTY}
    dst = next(i for i in range(0x05 + 1, 256) if i not in used)
    g.cycle_selection()          # activar selección
    app._dispatch(A, {A, R2})    # Ctrl+A: duplicar chain
    app._release(A)
    assert g.view.chain_at(r, t) == dst, \
        f"Ctrl+A debe duplicar la chain a {dst:02X}, obtuvo {g.view.chain_at(r, t):02X}"
    assert not g.has_selection, "la selección debe cancelarse tras duplicar"
    print("  R2+A (Ctrl+A) duplica la chain OK")

    # Restaura un valor para los casos Ctrl+S / S solo
    g.view.set_value(r, t, 0x05)

    # S llega antes que Ctrl: antes borraba la celda y luego muteaba
    app._fresh_press = True
    app._dispatch(B, {B})
    app._fresh_press = True
    app._dispatch(L2, {L2, B})
    app._release(B)
    assert g.view.chain_at(r, t) == 0x05, \
        f"S luego Ctrl no debe borrar: {g.view.chain_at(r, t)}"
    print("  S luego Ctrl (L2) no borra la celda OK")

    # Tras L2+S, el SO puede repetir S ya sin Ctrl: tampoco debe borrar
    app._fresh_press = True
    app._dispatch(B, {B, L2})
    app._fresh_press = False
    app._dispatch(B, {B})
    app._release(B)
    assert g.view.chain_at(r, t) == 0x05, \
        f"repetición de S sin Ctrl no debe borrar: {g.view.chain_at(r, t)}"
    print("  repetición de S tras soltar Ctrl no borra OK")

    # SONG: Ctrl izquierdo + A con selección corta el bloque
    g.view.set_value(r, t, 0x05)
    g.cycle_selection()
    app._dispatch(A, {A, L2})
    app._release(A)
    assert g.view.chain_at(r, t) == EMPTY, "Ctrl izq+A debe cortar en SONG"
    assert not g.has_selection
    print("  L2+A corta la selección en SONG OK")
    g.view.set_value(r, t, 0x05)

    # S solo (sin Ctrl) sigue borrando al soltar
    app._fresh_press = True
    app._dispatch(B, {B})
    app._release(B)
    assert g.view.chain_at(r, t) == EMPTY, \
        f"S sola debe borrar, quedó {g.view.chain_at(r, t)}"
    print("  S sola sigue borrando al soltar OK")

    # PHRASE: Ctrl izquierdo (L2) + A con selección corta el bloque.
    # En el PC "Ctrl+A" es casi siempre el Ctrl izquierdo, que antes no cortaba.
    ed = app.editor_screen
    ed.goto("phrase")
    pg = ed.phrase_grid
    assert pg.pv is not None
    t = pg.track
    pg.pv.set_note(0, t, 60)
    pg.pv.set_instr(0, t, 0x10)
    pg.cursor_step, pg.cursor_col = 0, 0
    pg.cycle_selection()
    assert pg.has_selection
    app._dispatch(A, {A, L2})
    app._release(A)
    assert pg._note(0) is None, "Ctrl izq+A debe cortar la nota"
    assert pg._instr(0) is None, "Ctrl izq+A debe cortar el instrumento"
    assert not pg.has_selection, "cortar cancela la selección"
    hint = pg._selection_hint() or ""
    assert "PORTAPAPELES" in hint and "pegar" in hint, hint
    pg.cursor_step = 1
    app._dispatch(A, {A, L2})
    app._release(A)
    assert pg._note(1) == 60, "Ctrl izq+A sin selección pega la nota"
    assert pg._instr(1) == 0x10, "Ctrl izq+A pega también el instrumento"
    print("  L2+A (Ctrl izq) corta la selección en PHRASE OK")
    print("  L2+A pega el bloque y el hint de portapapeles OK")

    pg.pv.set_note(0, t, 60)
    pg.pv.set_instr(0, t, 0x10)
    pg.cursor_step, pg.cursor_col = 0, 0
    pg.cycle_selection()
    app._dispatch(A, {A, R2})
    app._release(A)
    assert pg._note(0) is None, "Ctrl der+A debe seguir cortando"
    print("  R2+A sigue cortando la selección en PHRASE OK")

    ed.goto("chain")
    cg = ed.chain_grid
    assert cg.cv is not None
    cg.cursor_step, cg.cursor_col = 0, 0
    cg._set(0, 0, 0x10)
    cg.cycle_selection()
    app._dispatch(A, {A, L2})
    app._release(A)
    assert cg._get(0, 0) is None, "Ctrl izq+A debe cortar en CHAIN"
    assert not cg.has_selection
    print("  L2+A corta la selección en CHAIN OK")

    # Copiar/cortar en una chain y pegar en otra (otra celda de SONG).
    # Antes set_context vaciaba el portapapeles al cambiar de chain.
    ed.goto("song")
    sg = ed.song_grid
    sg.cursor_row = min(sg.cursor_row + 1, 255)
    ed.goto("chain")
    assert cg.clipboard is not None, "el bloque no debe perderse al cambiar de chain"
    hint = cg._selection_hint() or ""
    assert "PORTAPAPELES" in hint, hint
    cg.cursor_step, cg.cursor_col = 0, 0
    app._dispatch(A, {A, L2})
    app._release(A)
    assert cg._get(0, 0) == 0x10, "Ctrl+A debe pegar el bloque en la otra chain"
    print("  pegar el bloque en otra chain OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    app = Robotracker2App(songs_dir=DEFAULT_SONGS)

    def _go(_dt):
        try:
            _run(app)
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
