"""Test de integración: navegación a la pantalla CONFIG y persistencia.

Verifica que el EditorScreen puede navegar a "config" (vía navmap), que el
ConfigMenu se instancia y que el callback de persistencia se dispara al
cambiar una interfaz.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.app import App  # noqa: E402

from config import load_config, save_config, DEFAULTS  # noqa: E402
from navmap import neighbor  # noqa: E402


class _TestApp(App):
    def build(self):
        return None



def test_navmap_config_below_song():
    # CONFIG está debajo de SONG en la rejilla
    assert neighbor("song", 0, 1) == "config"
    assert neighbor("config", 0, -1) == "song"
    print("  navmap config below song OK")


def test_editor_navigates_to_config():
    from screens.editor import EditorScreen  # noqa: E402

    ed = EditorScreen()
    ed.goto("config")
    assert ed.current == "config"
    assert ed.config_menu is not None
    print("  editor navigates to config OK")


def test_config_change_persists():
    from screens.editor import EditorScreen  # noqa: E402

    saved = {}
    ed = EditorScreen()
    cfg = dict(DEFAULTS)
    ed.set_config(cfg, on_change=lambda: saved.update(cfg))
    ed.goto("config")
    m = ed.config_menu
    m._ports = ["A", "B"]
    m.index = 0  # midi_notes
    m.adjust(1)  # -> "A"
    assert cfg["midi_notes"] == "A"
    assert saved.get("midi_notes") == "A", "el callback de persistencia debe dispararse"
    print("  config change persists OK")


def test_config_roundtrip_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        cfg = dict(DEFAULTS)
        cfg["midi_notes"] = "LPK25:LPK25 MIDI 1 20:0"
        save_config(cfg, path)
        loaded = load_config(path)
        assert loaded["midi_notes"] == "LPK25:LPK25 MIDI 1 20:0"
    print("  config roundtrip file OK")


if __name__ == "__main__":
    from kivy.clock import Clock  # noqa: E402

    def _run_tests(_dt):
        try:
            print("test_navmap_config_below_song:")
            test_navmap_config_below_song()
            print("test_editor_navigates_to_config:")
            test_editor_navigates_to_config()
            print("test_config_change_persists:")
            test_config_change_persists()
            print("test_config_roundtrip_file:")
            test_config_roundtrip_file()
            print("TODOS LOS TESTS OK")
        finally:
            app.stop()

    # Necesita un App Kivy activo para poder crear widgets (EditorScreen).
    app = _TestApp()
    Clock.schedule_once(_run_tests, 0)
    app.run()


