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
from lgpt_engine import Engine  # noqa: E402
from lgpt_writer import save_project  # noqa: E402

__all__ = ["LGPTProject", "Engine", "note_byte_to_name", "save_project",
           "SINTE_DIR"]
