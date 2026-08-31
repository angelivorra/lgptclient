"""Configuración persistente de robotracker2 (no por canción).

Guarda en un JSON en el directorio de la app las preferencias globales:
  - midi_notes:   interfaz MIDI de entrada para notas (o None)
  - midi_control: interfaz MIDI de entrada para control (o None)
  - buttons:      botones físicos del controlador (acción -> spec, los
                  mismos que `[buttons]` de sinte/lttileplayer.toml)
  - hw_pots:      knobs físicos (potN -> {"cc": "cc:canal:control"}), como
                  `[pots]` del TOML; los targets se leen de robotraca.json
                  de cada canción (ver midi_ctrl.py)
  - pad_volume:   volumen global de los pads sampler (0-100), como
                  `[audio] pad_volume` del TOML

Se persiste entre ejecuciones. Si una interfaz guardada ya no existe al
arrancar, se conserva en el fichero (para la siguiente ejecución) pero se
marca como "no disponible" en la UI. buttons/hw_pots/pad_volume solo se
editan a mano en el fichero (la pantalla CONFIG edita las interfaces).
"""

import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"

DEFAULTS = {
    "midi_notes": None,
    "midi_control": None,
    # Mismo mapeo físico que sinte/lttileplayer.toml (Akai LPD8): pads de
    # transporte en el canal 9, knobs CC 70-77 en el canal 0.
    "buttons": {
        "up": "note:9:40",
        "down": "note:9:36",
        "play": "note:9:41",
        "stop": "note:9:37",
        "sample1": "note:9:42",
        "sample2": "note:9:43",
        "sample3": "note:9:38",
        "sample4": "note:9:39",
    },
    "hw_pots": {
        "pot1": {"cc": "cc:0:70"},
        "pot2": {"cc": "cc:0:71"},
        "pot3": {"cc": "cc:0:72"},
        "pot4": {"cc": "cc:0:73"},
        "pot5": {"cc": "cc:0:74"},
        "pot6": {"cc": "cc:0:75"},
        "pot7": {"cc": "cc:0:76"},
        "pot8": {"cc": "cc:0:77"},
    },
    "pad_volume": 45,
}


def load_config(path: Path = None) -> dict:
    """Lee la configuración persistida (o los valores por defecto)."""
    if path is None:
        path = CONFIG_FILE
    cfg = dict(DEFAULTS)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in DEFAULTS:
            if key in data:
                cfg[key] = data[key]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def save_config(cfg: dict, path: Path = None) -> None:
    """Persiste la configuración en el fichero JSON."""
    if path is None:
        path = CONFIG_FILE
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except OSError:
        pass

