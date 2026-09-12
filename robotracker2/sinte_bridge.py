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

from lgpt_parser import (CHANNEL_COUNT, EXTRA_TRACK, LGPTProject,  # noqa: E402
                         expand_song, note_byte_to_name)
from lgpt_engine import (  # noqa: E402
    EFFECT_PRESETS, Engine, glch_pack, glch_unpack, slid_pack, slid_unpack,
)
from chords import CHORD_TYPES, chord_label, cycle_chord  # noqa: E402
from filter_ui import (  # noqa: E402
    FILTER_MODES, PHRASE_FILTER_HELP, SVF_MODES, clamp255, cut_label,
    field_help, mode_from_param, mode_index, mode_label, normalize_mode,
    res_label, type_label,
)
from lgpt_writer import save_project  # noqa: E402
# Control MIDI (botones + knobs) y aplicación de robotraca.json: la misma
# maquinaria que usan sinte/lgpt_player y mixer (ver sinte/midi_control.py).
from master_eq import (  # noqa: E402
    EQ_BANDS, EQ_LABELS, EQ_MAX_DB, EQ_MIN_DB, parse_eq, eq_to_cfg,
)
from midi_control import _apply_pad_volume, apply_song_config, \
    build_song_pots, load_song_cfg, match_button, match_pot, \
    open_midi_input, parse_button_spec, parse_pot_target, \
    record_hw_pot_cc, save_song_cfg  # noqa: E402

__all__ = ["LGPTProject", "EFFECT_PRESETS", "Engine",
           "CHANNEL_COUNT", "EXTRA_TRACK", "expand_song",
           "note_byte_to_name", "save_project",
           "CHORD_TYPES", "chord_label", "cycle_chord",
           "slid_pack", "slid_unpack", "glch_pack", "glch_unpack",
           "FILTER_MODES", "PHRASE_FILTER_HELP", "SVF_MODES", "clamp255",
           "cut_label", "field_help", "mode_from_param", "mode_index",
           "mode_label", "normalize_mode", "res_label", "type_label",
           "SINTE_DIR", "_apply_pad_volume", "apply_song_config",
           "build_song_pots", "load_song_cfg", "match_button", "match_pot",
           "open_midi_input", "parse_button_spec", "parse_pot_target",
           "record_hw_pot_cc", "save_song_cfg",
           "EQ_BANDS", "EQ_LABELS", "EQ_MAX_DB", "EQ_MIN_DB",
           "parse_eq", "eq_to_cfg"]
