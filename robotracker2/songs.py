"""Descubrimiento y carga de canciones LGPT (puente a ../sinte).

Portado de robotracker/lgpt_model.py (find_songs/load_project) y de
sinte/lgpt_player.py (display_name), para no depender del código de robotracker.
"""

from pathlib import Path

from sinte_bridge import LGPTProject

# Por defecto, las canciones del sinte (mismo criterio que robotracker).
DEFAULT_SONGS = Path(__file__).resolve().parent.parent / "sinte" / "songs"


def find_songs(songs_dir):
    """Proyectos LGPT = subdirectorios que contienen lgptsav.dat."""
    songs_dir = Path(songs_dir)
    if not songs_dir.is_dir():
        return []
    return sorted(d for d in songs_dir.iterdir()
                  if d.is_dir() and (d / "lgptsav.dat").exists())


def display_name(dirname):
    """Nombre para la lista: sin prefijo 'lgpt_', corto y en mayúsculas."""
    name = dirname
    if name.startswith("lgpt_"):
        name = name[5:]
    name = name.split(".")[0]
    return name.upper()[:10]


def load_project(project_dir):
    """Parsea el lgptsav.dat de la carpeta y devuelve el LGPTProject cargado."""
    project = LGPTProject(Path(project_dir))
    project.load()
    return project
