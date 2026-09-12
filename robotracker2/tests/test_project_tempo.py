"""En PROJECT, A+dir sobre Tempo: ±10 arr/abj, ±1 izq/dcha.

Sin A, arr/abj sigue saltando de fila. El BPM se oye al instante
(engine.base_tempo) y queda en project.project.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import A, DOWN, L2, LEFT, RIGHT, UP  # noqa: E402
from songs import DEFAULT_SONGS  # noqa: E402


def _run(app):
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    assert app.editor_screen.current == "song"

    ed = app.editor_screen
    tempo0 = int(ed.project.project["tempo"])
    ed.project.project["tempo"] = "120"
    app.player.engine.set_base_tempo(120)

    app._dispatch(L2, {L2})
    app._dispatch(UP, {UP, L2})
    assert ed.current == "project"
    m = ed.project_menu
    assert m.current_item()[0] == "tempo"

    app._dispatch(UP, {UP, A})
    assert int(ed.project.project["tempo"]) == 130
    assert app.player.engine.base_tempo == 130
    assert m.current_item()[0] == "tempo", "A+arr no debe saltar de fila"
    print("  A+arr +10 OK")

    app._dispatch(DOWN, {DOWN, A})
    assert int(ed.project.project["tempo"]) == 120
    assert app.player.engine.base_tempo == 120
    print("  A+abj -10 OK")

    app._dispatch(RIGHT, {RIGHT, A})
    assert int(ed.project.project["tempo"]) == 121
    app._dispatch(LEFT, {LEFT, A})
    assert int(ed.project.project["tempo"]) == 120
    print("  A+izq/dcha ±1 OK")

    app._dispatch(RIGHT, {RIGHT})
    assert int(ed.project.project["tempo"]) == 121
    print("  dcha sin A ±1 OK")

    ed.project.project["tempo"] = "10"
    app.player.engine.set_base_tempo(10)
    m._redraw()
    app._dispatch(DOWN, {DOWN, A})
    app._dispatch(LEFT, {LEFT, A})
    assert int(ed.project.project["tempo"]) == 10
    ed.project.project["tempo"] = "255"
    app.player.engine.set_base_tempo(255)
    m._redraw()
    app._dispatch(UP, {UP, A})
    app._dispatch(RIGHT, {RIGHT, A})
    assert int(ed.project.project["tempo"]) == 255
    print("  tope 10–255 OK")

    ed.project.project["tempo"] = "120"
    app.player.engine.set_base_tempo(120)
    m._redraw()
    app._dispatch(DOWN, {DOWN})
    assert m.current_item()[0] == "master"
    print("  abj sin A salta a Master OK")

    assert app.dirty
    ed.project.project["tempo"] = str(tempo0)
    app.player.engine.set_base_tempo(tempo0)
    print("  dirty + engine en vivo OK")


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
