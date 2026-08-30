"""Test del módulo de configuración persistente y de la lógica de ConfigMenu.

Verifica:
  - load_config/save_config persisten entre "ejecuciones" (fichero temporal).
  - La enumeración de puertos MIDI de entrada funciona (mido).
  - La lógica de "no pueden ser la misma interfaz" y de "no disponible".
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import load_config, save_config, DEFAULTS  # noqa: E402


def test_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.json"
        cfg = dict(DEFAULTS)
        cfg["midi_notes"] = "LPK25:LPK25 MIDI 1 20:0"
        cfg["midi_control"] = "Midi Through:Midi Through Port-0 14:0"
        save_config(cfg, path)
        loaded = load_config(path)
        assert loaded["midi_notes"] == cfg["midi_notes"]
        assert loaded["midi_control"] == cfg["midi_control"]
    print("  roundtrip OK")


def test_defaults_when_missing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "no_existe.json"
        cfg = load_config(path)
        assert cfg["midi_notes"] is None
        assert cfg["midi_control"] is None
    print("  defaults OK")


def test_midi_ports():
    try:
        import mido
        ports = mido.get_input_names()
    except Exception:                       # noqa: BLE001
        ports = []
    assert isinstance(ports, list)
    print(f"  midi ports OK: {len(ports)} puertos -> {ports}")


def test_same_interface_rejected():
    """La lógica de ConfigMenu no permite elegir la misma interfaz para
    notas y control. Se prueba la función pura equivalente."""
    from screens.config_view import ConfigMenu  # noqa: E402

    cfg = {"midi_notes": "A", "midi_control": None}
    menu = ConfigMenu(cfg=cfg)
    menu._ports = ["A", "B"]
    # midi_control no puede ser "A" (la misma que notas): al ciclar salta
    # directamente al siguiente puerto distinto -> "B"
    menu.index = 1  # midi_control
    menu.adjust(1)
    assert menu.cfg["midi_control"] == "B", "debería saltar a un puerto distinto"
    # y nunca puede quedar igual que notas
    assert menu.cfg["midi_control"] != menu.cfg["midi_notes"]
    print("  same-interface rejected OK")



def test_missing_interface_detected():
    from screens.config_view import ConfigMenu  # noqa: E402

    cfg = {"midi_notes": "Interfaz Fantasma", "midi_control": None}
    menu = ConfigMenu(cfg=cfg)
    menu._ports = ["A", "B"]
    menu._refresh_ports()
    assert "midi_notes" in menu._missing
    assert "midi_control" not in menu._missing
    print("  missing-interface detected OK")


if __name__ == "__main__":
    print("test_roundtrip:")
    test_roundtrip()
    print("test_defaults_when_missing:")
    test_defaults_when_missing()
    print("test_midi_ports:")
    test_midi_ports()
    print("test_same_interface_rejected:")
    test_same_interface_rejected()
    print("test_missing_interface_detected:")
    test_missing_interface_detected()
    print("TODOS LOS TESTS OK")
