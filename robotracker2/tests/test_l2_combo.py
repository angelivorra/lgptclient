"""Test del bug: L2 (Ctrl Izq) + B + A no debe cortar la celda seleccionada.

Reproduce el flujo exacto del usuario:
  1. Pulsa Ctrl Izq (L2)
  2. Pulsa B, suelta B
  3. Pulsa A, suelta A

Antes del fix, al soltar A con L2 mantenido se disparaba `a_tap()` que
cortaba/pegaba/ponía 00 sobre la celda. Ahora L2 es un modificador de
navegación: A y B con L2 no hacen nada (salvo L2+S mute mientras suena).
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, B, DOWN, L2, R2  # noqa: E402
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
    # 2) pulsa B (con L2 mantenido)
    app._dispatch(B, {B, L2})
    # 3) suelta B
    app._release(B)
    # 4) pulsa A (con L2 mantenido)
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
