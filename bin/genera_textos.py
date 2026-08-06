#!/usr/bin/env python3
"""Genera el fichero `textos` de cada canción de sinte/songs/ a partir del
banco de frases compartido (por ahora solo existe `images/002/textos`).

El motor (sinte/lgpt_engine.py) reserva el CC 2 de los comandos MDCC como
"banco de textos": cuando una fila del tracker trae `MDCC` con control=2 y
valor=N, se muestra en pantalla la línea N del fichero `textos` de esa
canción. El contenido de esas líneas no es específico de la canción: es el
mismo banco de frases (images/002/textos) que cualquier canción puede
referenciar por índice, así que no hay nada que "escribir" — solo copiar
ese banco a las canciones que de verdad lo usan.

Una canción sin ningún MDCC control=2 en su partitura no tiene letra
autorada todavía: se salta sin tocar nada (ver `--check` para CI/ansible).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SINTE_DIR = REPO_ROOT / "sinte"
SONGS_DIR = SINTE_DIR / "songs"
BANK_FILE = REPO_ROOT / "images" / "002" / "textos"

sys.path.insert(0, str(SINTE_DIR))

from lgpt_parser import LGPTProject  # noqa: E402

TEXT_CC = 2  # igual que TEXT_CC en midi_monitor_linux/srt_recorder.py


def usa_banco_de_textos(song_dir: Path) -> bool:
    """True si algún MDCC de la canción referencia el banco de textos (CC=2)."""
    project = LGPTProject(song_dir)
    project.load()
    for cmd_arr, param_arr in ((project.cmd1, project.param1),
                               (project.cmd2, project.param2)):
        for cmd, param in zip(cmd_arr, param_arr):
            if cmd != "MDCC":
                continue
            control = (param >> 8) & 0x7F
            if control == TEXT_CC:
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true",
        help="no escribe nada, solo indica con el código de salida si haría "
             "algún cambio (útil para comprobar en CI/ansible sin tocar el repo)")
    args = parser.parse_args()

    if not BANK_FILE.is_file():
        print(f"[genera_textos] no existe el banco {BANK_FILE}", file=sys.stderr)
        return 1

    bank_content = BANK_FILE.read_bytes()
    changed = False
    for song_dir in sorted(SONGS_DIR.glob("lgpt_*")):
        if not song_dir.is_dir():
            continue
        dest = song_dir / "textos"
        try:
            necesita_banco = usa_banco_de_textos(song_dir)
        except Exception as exc:
            print(f"[genera_textos] {song_dir.name}: no se pudo leer la canción ({exc})",
                  file=sys.stderr)
            continue

        if not necesita_banco:
            print(f"[genera_textos] {song_dir.name}: sin MDCC control=2, no hace falta letra")
            continue

        ya_al_dia = dest.is_file() and dest.read_bytes() == bank_content
        if ya_al_dia:
            print(f"[genera_textos] {song_dir.name}: textos ya al día")
            continue

        changed = True
        if args.check:
            print(f"[genera_textos] {song_dir.name}: haría falta copiar el banco (--check)")
            continue
        shutil.copyfile(BANK_FILE, dest)
        print(f"[genera_textos] {song_dir.name}: copiado banco -> {dest}")

    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
