"""Importar un sample cuyo basename ya existe en la canción.

Si el WAV es el mismo (ruta o contenido), se reutiliza. Si es otro fichero
con el mismo nombre, se copia como stem_2.wav y se avisa: nunca se asigna
en silencio el sample viejo.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from robotracker2 import resolve_sample_import  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dest_dir = tmp / "samples"
        dest_dir.mkdir()
        lib = tmp / "lib"
        lib.mkdir()

        kick = dest_dir / "kick.wav"
        kick.write_bytes(b"AAAA")

        # mismo fichero (ya está en samples/): reutilizar
        dest, notice = resolve_sample_import(kick, dest_dir)
        assert dest == kick and notice is None, (dest, notice)
        print("  mismo path: reutiliza OK")

        # mismo contenido, otra ruta: reutilizar el de la canción
        copy = lib / "kick.wav"
        copy.write_bytes(b"AAAA")
        dest, notice = resolve_sample_import(copy, dest_dir)
        assert dest == kick and notice is None, (dest, notice)
        print("  mismo contenido: reutiliza OK")

        # contenido distinto, mismo nombre: no pisar, stem_2.wav
        other = lib / "other" / "kick.wav"
        other.parent.mkdir()
        other.write_bytes(b"BBBB")
        dest, notice = resolve_sample_import(other, dest_dir)
        assert dest == dest_dir / "kick_2.wav", dest
        assert notice is not None and "kick_2.wav" in notice, notice
        print("  nombre ocupado distinto: kick_2.wav + aviso OK")

        # si kick_2 también está ocupado con otro contenido, kick_3
        (dest_dir / "kick_2.wav").write_bytes(b"CCCC")
        dest, notice = resolve_sample_import(other, dest_dir)
        assert dest == dest_dir / "kick_3.wav", dest
        assert "kick_3.wav" in notice, notice
        print("  kick_2 ocupado: kick_3.wav OK")

        # nombre libre: destino con el mismo basename
        snare = lib / "snare.wav"
        snare.write_bytes(b"DDDD")
        dest, notice = resolve_sample_import(snare, dest_dir)
        assert dest == dest_dir / "snare.wav" and notice is None, dest
        print("  nombre libre: copia como snare.wav OK")

    print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
