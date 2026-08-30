"""Test end-to-end de la pantalla CONFIG con la app real.

Carga una canción, navega a CONFIG (Ctrl+abajo desde SONG), selecciona las
interfaces MIDI de entrada y verifica que se persisten en config.json.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from config import load_config, save_config, DEFAULTS  # noqa: E402
from controls import A, B, DOWN, L2, LEFT, RIGHT, UP  # noqa: E402

from songs import DEFAULT_SONGS  # noqa: E402


def _run(app):
    from robotracker2 import Robotracker2App  # noqa: E402

    # 1) cargar la primera canción
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    assert app.sm.current == "editor", "debe entrar al editor"
    assert app.editor_screen.current == "song"

    # 2) navegar a CONFIG (Ctrl+abajo = L2+DOWN)
    app._dispatch(DOWN, {DOWN, L2})

    assert app.editor_screen.current == "config", \
        f"debe estar en config, está en {app.editor_screen.current}"

    # 3) seleccionar MIDI Notas (campo 0) -> primer puerto
    m = app.editor_screen.config_menu
    m._ports = ["PuertoA", "PuertoB"]
    m.index = 0
    m.adjust(1)
    assert app.config["midi_notes"] == "PuertoA"

    # 4) seleccionar MIDI Control (campo 1) -> no puede ser el mismo
    m.index = 1
    m.adjust(1)   # salta a "PuertoB" (no "PuertoA")
    assert app.config["midi_control"] == "PuertoB"
    assert app.config["midi_control"] != app.config["midi_notes"]

    # 5) verificar que se persiste en config.json
    saved = load_config()
    assert saved["midi_notes"] == "PuertoA"
    assert saved["midi_control"] == "PuertoB"
    print("  e2e config OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    # usa un config.json temporal para no ensuciar el real
    tmp = tempfile.TemporaryDirectory()
    import config as config_mod
    config_mod.CONFIG_FILE = Path(tmp.name) / "config.json"

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
    tmp.cleanup()


if __name__ == "__main__":
    main()
