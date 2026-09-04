"""Puente con el motor LGPT de sinte (`../sinte`).

sinte no es un paquete instalable: son scripts planos hermanos de este
directorio dentro del monorepo lgptclient. Aquí se añade al sys.path y se
reexporta lo que usa robotracker. Si sinte cambia de sitio, solo hay que
tocar SINTE_DIR.
"""

import sys
from pathlib import Path

SINTE_DIR = Path(__file__).resolve().parent.parent / "sinte"
if not SINTE_DIR.is_dir():
    raise RuntimeError(f"no se encuentra sinte en {SINTE_DIR}")
if str(SINTE_DIR) not in sys.path:
    sys.path.insert(0, str(SINTE_DIR))

from lgpt_parser import LGPTProject, note_byte_to_name  # noqa: E402
from lgpt_engine import EFFECT_PRESETS, Engine  # noqa: E402
from lgpt_writer import save_project  # noqa: E402
# Control MIDI (botones + knobs) y aplicación de robotraca.json: la misma
# maquinaria que usan sinte/lgpt_player y mixer (ver sinte/midi_control.py).
from midi_control import _apply_pad_volume, apply_song_config, \
    build_song_pots, load_song_cfg, match_button, match_pot, \
    open_midi_input, parse_button_spec, parse_pot_target, \
    record_hw_pot_cc, save_song_cfg  # noqa: E402

__all__ = ["LGPTProject", "EFFECT_PRESETS", "Engine",
           "note_byte_to_name", "save_project",
           "SINTE_DIR", "_apply_pad_volume", "apply_song_config",
           "build_song_pots", "load_song_cfg", "match_button", "match_pot",
           "open_midi_input", "parse_button_spec", "parse_pot_target",
           "record_hw_pot_cc", "save_song_cfg"]
