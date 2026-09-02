"""PHRASE conserva cursor/selección al ir a INSTRUMENT o TABLE y volver.

Como CHAIN: solo se llama set_context si cambian canción, celda o step
de chain. Cambiar de step en CHAIN sí debe resetear el cursor de PHRASE.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import DOWN, LEFT, RIGHT  # noqa: E402


def _run(app):
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    ed = app.editor_screen
    assert ed.current == "song"

    ed.goto("chain")
    ed.goto("phrase")
    g = ed.phrase_grid
    assert g.pv is not None
    g.move(DOWN)
    g.move(DOWN)
    g.move(RIGHT)
    step, col = g.cursor_step, g.cursor_col
    assert (step, col) != (0, 0), "el cursor debe haberse movido"

    ed.goto("instrument")
    ed.goto("phrase")
    assert (g.cursor_step, g.cursor_col) == (step, col), \
        "volver de INSTRUMENT no debe resetear PHRASE"
    print("  PHRASE conserva cursor al volver de INSTRUMENT OK")

    ed.goto("phrase_table")
    ed.goto("phrase")
    assert (g.cursor_step, g.cursor_col) == (step, col), \
        "volver de TABLE no debe resetear PHRASE"
    print("  PHRASE conserva cursor al volver de TABLE OK")

    ed.goto("chain")
    ed.chain_grid.move(DOWN)
    ed.goto("phrase")
    assert (g.cursor_step, g.cursor_col) == (0, 0), \
        "cambiar de step en CHAIN debe recrear el contexto de PHRASE"
    print("  PHRASE se resetea al cambiar de step en CHAIN OK")


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
