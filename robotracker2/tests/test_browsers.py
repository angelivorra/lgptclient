"""Tests de los navegadores: historial de carpetas del de samples,
indicadores de scroll del de screens y flechas direccionales de la
cabecera del editor (navmap).

Sin app para el historial (SampleBrowser es autónomo): entrar por A en
dos carpetas y volver/avanzar con las flechas debe recordar el camino y
la posición del cursor en cada carpeta; una rama nueva mata el historial
"hacia delante". Los indicadores del ImageBrowser se comprueban por sus
flags de scroll (`_scroll_flags`, lo que enciende/apaga los triángulos),
y el dispatch izq/dcha de la app no debe romper ImageBrowser.
"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controls import A, DOWN, LEFT, RIGHT, UP  # noqa: E402


def _browser_sueltos():
    """Historias del navegador de samples sobre un árbol temporal."""
    from screens.sample_browser import SampleBrowser

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "A").mkdir()
        (root / "A" / "B").mkdir()
        (root / "A" / "C").mkdir()
        (root / "A" / "B" / "y.wav").write_bytes(b"")
        (root / "A" / "C" / "z.wav").write_bytes(b"")
        b = SampleBrowser(root, on_load=None, on_close=None)
        assert [p.name for p in b.entries] == ["A"], b.entries

        # entrar en A -> B (dos niveles) con A
        b.activate()                     # A sobre la carpeta A
        assert b.cwd.name == "A"
        assert [p.name for p in b.entries] == ["B", "C"], b.entries
        b.activate()                     # índice 0 = B
        assert b.cwd.name == "B"
        print("  entrar dos niveles con A OK")

        # flecha atrás: vuelve con memoria de la posición del cursor
        b.move(DOWN)                     # índice 1 = C en la carpeta A
        b.go_back()                      # A <- B: vuelve a A
        assert b.cwd.name == "A", b.cwd
        assert b.index == 0, b.index     # B está en el índice 0 de A
        print("  flecha atrás vuelve a la carpeta anterior OK")

        # la posición recordada: desde A entra en C (índice 1) y atrás
        b.move(DOWN)                     # índice 1 = C
        b.activate()
        assert b.cwd.name == "C"
        b.go_back()
        assert b.cwd.name == "A"
        assert b.index == 1 and b.selected().name == "C", \
            (b.index, b.selected())
        print("  memoria de la posición del cursor OK")

        # dos niveles atrás y dos delante
        b.go_back()                      # A -> raíz
        assert b.cwd == root, b.cwd
        b.go_forward()                   # raíz -> A
        assert b.cwd.name == "A"
        b.go_forward()                   # A -> C
        assert b.cwd.name == "C", b.cwd
        print("  dos niveles atrás y dos delante OK")

        # rama nueva: el historial hacia delante muere
        b.go_back()                      # C -> A
        assert b._fwd, "debe quedar historial hacia delante"
        b.move(UP)                       # índice 0 = B
        b.activate()                     # entrar en B = rama nueva
        assert b.cwd.name == "B"
        assert not b._fwd, "entrar por A debe limpiar el historial delante"
        print("  rama nueva limpia el historial hacia delante OK")

        # B sube un nivel y la flecha delante puede volver a bajar
        b.back()                         # B -> A
        assert b.cwd.name == "A"
        b.go_forward()                   # A -> B
        assert b.cwd.name == "B"
        print("  B sube y la flecha delante vuelve a bajar OK")

        # sin historial, las flechas no hacen nada (browser recién abierto)
        b2 = SampleBrowser(root, on_load=None, on_close=None)
        b2.go_back()
        assert b2.cwd == root, b2.cwd
        b2.go_forward()
        assert b2.cwd == root, b2.cwd
        print("  flechas sin historial no hacen nada OK")

        loaded = []
        wavs = root / "wavs"
        wavs.mkdir()
        (wavs / "hit.wav").write_bytes(b"x")
        b3 = SampleBrowser(wavs, on_load=lambda p: loaded.append(p.name),
                           on_close=None)
        b3.activate()
        assert loaded == ["hit.wav"], loaded
        print("  A sobre un wav carga (sin doble-tap) OK")


def _indicadores_screens():
    """Flags de scroll del navegador de screens (encienden los triángulos)."""
    from screens.image_browser import ImageBrowser

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for cc in range(1, 31):          # 30 carpetas -> desborda la lista
            (root / f"{cc:03d}").mkdir()
            (root / f"{cc:03d}" / "textos").write_text("línea\n")
        b = ImageBrowser(root)
        b.size = (800, 548)              # tamaño realista (13 filas visibles)
        n = b._visible()
        assert 0 < n < len(b.entries), (n, len(b.entries))

        can_up, can_down = b._scroll_flags()
        assert (can_up, can_down) == (False, True), "arriba del todo"
        print("  indicador: arriba del todo -> solo se puede bajar OK")

        for _ in range(20):              # a mitad: ventana desplazada
            b.move(DOWN)
        can_up, can_down = b._scroll_flags()
        assert (can_up, can_down) == (True, True), "a mitad con lista larga"
        print("  indicador: a mitad -> ambas direcciones OK")

        for _ in range(len(b.entries)):  # al final de la lista
            b.move(DOWN)
        can_up, can_down = b._scroll_flags()
        assert (can_up, can_down) == (True, False), "abajo del todo"
        print("  indicador: abajo del todo -> solo se puede subir OK")

        # el canvas lleva los dos triángulos (encendido + atenuado)
        from kivy.graphics import Triangle
        b._redraw()
        triangulos = [c for c in b.canvas.children
                      if isinstance(c, Triangle)]
        assert len(triangulos) == 2, len(triangulos)
        print("  los dos triángulos se dibujan OK")


def _flechas_nav():
    """Rayas blancas del chip activo: visibles si Ctrl+arriba/abajo lleva
    a otra pantalla (según navmap); ocultas si no, y en celdas inactivas."""
    from screens.editor import NAV_LINE, EditorScreen

    es = EditorScreen()
    es.current = "song"
    es._update_nav(1, 1, "S")
    cell = es.nav_cells[1]
    assert cell.text == "S", cell.text
    # SONG (1,1): PROJECT arriba, TABLE abajo
    assert tuple(cell._dir_colors["up"].rgba) == NAV_LINE
    assert tuple(cell._dir_colors["down"].rgba) == NAV_LINE
    print("  SONG: rayas arriba y abajo OK")

    for other in es.nav_cells[:1] + es.nav_cells[2:]:
        assert all(tuple(c.rgba)[3] == 0 for c in other._dir_colors.values())
    print("  celdas inactivas sin rayas OK")

    # PROJECT (1,0): sin pantalla arriba; SONG abajo
    es.current = "project"
    es._update_nav(1, 0, "P")
    cell = es.nav_cells[1]
    assert cell.text == "P", cell.text
    assert tuple(cell._dir_colors["up"].rgba)[3] == 0
    assert tuple(cell._dir_colors["down"].rgba) == NAV_LINE
    print("  PROJECT: solo raya abajo OK")

    # GROOVE (3,0): solo PHRASE debajo
    es.current = "groove"
    es._update_nav(3, 0, "G")
    cell = es.nav_cells[3]
    assert cell.text == "G", cell.text
    assert tuple(cell._dir_colors["down"].rgba) == NAV_LINE
    assert tuple(cell._dir_colors["up"].rgba)[3] == 0
    print("  GROOVE: solo raya abajo OK")

    # CHAIN (2,1): LIVE arriba, nada abajo
    es.current = "chain"
    es._update_nav(2, 1, "C")
    cell = es.nav_cells[2]
    assert cell.text == "C", cell.text
    assert tuple(cell._dir_colors["up"].rgba) == NAV_LINE
    assert tuple(cell._dir_colors["down"].rgba)[3] == 0
    print("  CHAIN: raya arriba (LIVE) OK")

    # LIVE (2,0): CHAIN abajo
    es.current = "live"
    es._update_nav(2, 0, "V")
    cell = es.nav_cells[2]
    assert cell.text == "V", cell.text
    assert tuple(cell._dir_colors["down"].rgba) == NAV_LINE
    assert tuple(cell._dir_colors["up"].rgba)[3] == 0
    print("  LIVE: solo raya abajo OK")

    # INSTRUMENT (4,1): TABLE abajo, nada arriba
    es.current = "instrument"
    es._update_nav(4, 1, "I")
    cell = es.nav_cells[4]
    assert cell.text == "I", cell.text
    assert tuple(cell._dir_colors["up"].rgba)[3] == 0
    assert tuple(cell._dir_colors["down"].rgba) == NAV_LINE
    print("  INSTRUMENT: solo raya abajo OK")

    es.song_name = "demo"
    es.current = "song"
    es.unsaved = False
    assert es._header_text() == "SONG    demo", es._header_text()
    es.set_unsaved(True)
    assert es._header_text() == "SONG    demo *", es._header_text()
    print("  cabecera: asterisco de cambios sin guardar OK")


def _dispatch_flechas(app):
    """El dispatch izq/dcha: SampleBrowser usa historial, ImageBrowser no
    se rompe (getattr sin go_back/go_forward)."""
    from screens.image_browser import ImageBrowser
    from screens.sample_browser import SampleBrowser

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp / "d").mkdir()

        llamadas = []

        class FakeB:
            def move(self, button):
                llamadas.append(("move", button))

            def activate(self):
                llamadas.append(("activate",))

            def back(self):
                llamadas.append(("back",))

            def go_back(self):
                llamadas.append(("go_back",))

            def go_forward(self):
                llamadas.append(("go_forward",))

        app.browser = FakeB()
        app._dispatch_browser(LEFT)
        app._dispatch_browser(RIGHT)
        assert llamadas == [("go_back",), ("go_forward",)], llamadas
        print("  dispatch: izq/dcha -> go_back/go_forward OK")

        # ImageBrowser no tiene historial: las flechas no deben romper
        app.browser = ImageBrowser(tmp)
        app._dispatch_browser(LEFT)
        app._dispatch_browser(RIGHT)
        app._dispatch_browser(A)
        app._dispatch_browser(UP)
        print("  dispatch: ImageBrowser ignora las flechas sin romper OK")

        # SampleBrowser de verdad: la flecha entra en el historial
        app.browser = SampleBrowser(tmp, on_load=None, on_close=None)
        app._dispatch_browser(DOWN)      # índice 0 = d
        app._dispatch_browser(A)         # entra en d
        assert app.browser.cwd.name == "d"
        app._dispatch_browser(LEFT)      # atrás por historial
        assert app.browser.cwd == tmp
        app._dispatch_browser(RIGHT)     # delante
        assert app.browser.cwd.name == "d"
        print("  dispatch: flechas en el navegador de samples OK")


def main():
    from robotracker2 import Robotracker2App

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        songs_dir = tmp / "songs"
        songs_dir.mkdir()
        app = Robotracker2App(songs_dir=songs_dir, samples_dir=tmp)

        _browser_sueltos()
        _indicadores_screens()
        _flechas_nav()
        _dispatch_flechas(app)
        print("TODOS LOS TESTS OK")


if __name__ == "__main__":
    main()
