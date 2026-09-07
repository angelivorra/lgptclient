"""CHRD en PHRASE: ciclado de comando y etiqueta del tipo de acorde."""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import RIGHT  # noqa: E402
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

    pg.pv.set_note(0, t, 60)
    pg.pv.set_instr(0, t, 0)
    pg.pv.clear_fx(0, t, 1)
    pg.cursor_step = 0
    pg.cursor_col = 2                       # fx1cmd
    pg.edit(RIGHT)                          # primer comando = VOLM
    assert pg._cmd(0, 1) == FX_USED[0]
    for _ in range(len(FX_USED) - 1):
        pg.edit(RIGHT)
    assert pg._cmd(0, 1) == "CHRD", f"tras ciclar: {pg._cmd(0, 1)}"
    assert pg._prm(0, 1) == 0, "al elegir CHRD el tipo arranca en maj"
    pg.cursor_col = 3                       # fx1prm
    assert pg._field_text(0, 3).strip() == "maj"
    pg.edit(RIGHT)
    assert pg._prm(0, 1) == 1
    assert pg._field_text(0, 3).strip() == "min"
    print("  CHRD cicla tipos maj/min en PHRASE OK")


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
