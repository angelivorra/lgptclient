"""Scroll de la lista de cargar canción (ventana visible + wrap)."""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    from screens.load_song import LoadSongScreen

    songs = [Path(f"lgpt_{i:02d}") for i in range(40)]
    s = LoadSongScreen(songs, name="load")
    s.size = (1280, 720)
    s.pos = (0, 0)
    s._relayout()
    n = s._visible()
    assert 1 < n < 40, n
    assert s.top_idx == 0
    assert s._rows[0].opacity == 1
    assert s._rows[n].opacity == 0
    print("  lista larga: ventana, filas fuera ocultas OK")

    for _ in range(n + 3):
        s.move(1)
    assert s.index == n + 3
    assert s.top_idx > 0
    assert s._rows[s.index].opacity == 1
    print("  el cursor arrastra el scroll OK")

    s.index = len(songs) - 1
    s._relayout()
    s.move(1)
    assert s.index == 0
    assert s.top_idx == 0
    print("  wrap al final vuelve al principio OK")

    few = LoadSongScreen([Path("a"), Path("b")], name="few")
    few.size = (1280, 720)
    few._relayout()
    assert few._rows[0].opacity == 1 and few._rows[1].opacity == 1
    print("  pocas canciones: las dos visibles OK")

    print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
