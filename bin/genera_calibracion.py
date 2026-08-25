#!/usr/bin/env python3
"""Genera las 3 canciones de test de calibración (una por nota de golpe:
62=bombo, 63/65=cajas) a partir de lgpt_TEST_BATERIA.

Cada canción reproduce EN BUCLE (loop de sección del engine) su nota en la
pista MIDI (canal 0, inst 128) y el sample correspondiente (kick/snare) en la
pista de audio, alineados en las mismas posiciones (0 y 8). El sinte las usa
en la pantalla de calibración: al pulsar play suena la del motor seleccionado.

Uso:
    sinte/.venv/bin/python bin/genera_calibracion.py [ruta_base]

Salida: sinte/songs_calib/nota{62,63,65}/  (lgptsav.dat + samples/)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "sinte"))
from lgpt_parser import LGPTProject          # noqa: E402
from lgpt_writer import save_project          # noqa: E402

DEFAULT_BASE = Path("/home/angel/LGPT/songs/lgpt_TEST_BATERIA")
OUT_DIR = REPO / "sinte" / "songs_calib"

# frase MIDI ya existente por nota; instrumento de audio (33=kick, 34=snare)
CHAIN_MIDI = 16          # canal 0 usa esta cadena
CHAIN_AUDIO = 32         # canal 1 usa esta cadena
AUDIO_PHRASE = 40        # frase de audio que creamos (libre en la base)
SONGS = [
    ("nota62", 16, 33),  # bombo -> nota 62, kick
    ("nota63", 17, 34),  # caja  -> nota 63, snare
    ("nota65", 18, 34),  # caja  -> nota 65, snare
]


def _clear_phrase(p: LGPTProject, ph: int):
    for pos in range(16):
        i = ph * 16 + pos
        p.notes[i] = 0xFF        # celda vacía = note 0xFF
        p.instruments[i] = 0xFF
        p.cmd1[i] = "----"
        p.param1[i] = 0
        p.cmd2[i] = "----"
        p.param2[i] = 0


def _set_cell(p: LGPTProject, ph: int, pos: int, note: int, instr: int):
    i = ph * 16 + pos
    p.notes[i] = note
    p.instruments[i] = instr
    p.cmd1[i] = "----"
    p.param1[i] = 0


def _set_chain(p: LGPTProject, chain: int, phrase: int):
    base = chain * 16
    p.chains[base] = phrase
    p.transposes[base] = 0
    for step in range(1, 16):
        p.chains[base + step] = 0xFF


def genera(base: Path):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for folder, midi_phrase, audio_instr in SONGS:
        p = LGPTProject(base)
        p.load()
        # audio: una frase con el sample en 0 y 8 (como los golpes MIDI)
        _clear_phrase(p, AUDIO_PHRASE)
        _set_cell(p, AUDIO_PHRASE, 0, 60, audio_instr)
        _set_cell(p, AUDIO_PHRASE, 8, 60, audio_instr)
        # cadenas: canal0 -> frase MIDI de la nota; canal1 -> frase de audio
        _set_chain(p, CHAIN_MIDI, midi_phrase)
        _set_chain(p, CHAIN_AUDIO, AUDIO_PHRASE)
        # (el song ya tiene filas 0-8 = [16,32,...]; loop de sección)
        dest = OUT_DIR / folder
        dest.mkdir(parents=True, exist_ok=True)
        save_project(p, dest / "lgptsav.dat", backup=False)
        # samples
        src_samples = base / "samples"
        if src_samples.is_dir():
            dst_samples = dest / "samples"
            if dst_samples.exists():
                shutil.rmtree(dst_samples)
            shutil.copytree(src_samples, dst_samples)
        print(f"generada {dest}  (nota via frase {midi_phrase}, audio inst {audio_instr})")


if __name__ == "__main__":
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BASE
    if not (base / "lgptsav.dat").is_file():
        sys.exit(f"no existe la canción base: {base}")
    genera(base)
