"""Configuración persistente de robotracker2 (no por canción).

Guarda en un JSON en el directorio de la app las preferencias globales:
  - midi_notes:  interfaz MIDI de entrada para notas (o None)
  - midi_control: interfaz MIDI de entrada para control (o None)

Se persiste entre ejecuciones. Si una interfaz guardada ya no existe al
arrancar, se conserva en el fichero (para la siguiente ejecución) pero se
marca como "no disponible" en la UI.
"""

import json
import os
from pathlib import Path

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"

DEFAULTS = {
    "midi_notes": None,
    "midi_control": None,
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

