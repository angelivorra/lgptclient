"""PHRASE conserva cursor/selección al ir a INSTRUMENT o TABLE y volver.

Como CHAIN: solo se llama set_context si cambian canción, celda o step
de chain. Cambiar de step en CHAIN sí debe resetear el cursor de PHRASE.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import DOWN, LEFT, RIGHT  # noqa: E402


def _run(app):
    songs = app.load_screen.songs
    assert songs, "debe haber canciones"
    app._request_load(songs[0])
    ed = app.editor_screen
    assert ed.current == "song"

    ed.goto("chain")
    ed.goto("phrase")
    g = ed.phrase_grid
    assert g.pv is not None
    g.move(DOWN)
    g.move(DOWN)
    g.move(RIGHT)
    step, col = g.cursor_step, g.cursor_col
    assert (step, col) != (0, 0), "el cursor debe haberse movido"

    ed.goto("instrument")
    ed.goto("phrase")
    assert (g.cursor_step, g.cursor_col) == (step, col), \
        "volver de INSTRUMENT no debe resetear PHRASE"
    print("  PHRASE conserva cursor al volver de INSTRUMENT OK")

    ed.goto("phrase_table")
    ed.goto("phrase")
    assert (g.cursor_step, g.cursor_col) == (step, col), \
        "volver de TABLE no debe resetear PHRASE"
    print("  PHRASE conserva cursor al volver de TABLE OK")

    ed.goto("chain")
    ed.chain_grid.move(DOWN)
    ed.goto("phrase")
    assert (g.cursor_step, g.cursor_col) == (0, 0), \
        "cambiar de step en CHAIN debe recrear el contexto de PHRASE"
    print("  PHRASE se resetea al cambiar de step en CHAIN OK")

    # Ctrl+derecha desde PHRASE debe abrir el instrumento del step, no el 00
    bank = [i for i in sorted(ed.project.instrument_bank) if i != 0]
    assert bank, "la canción debe tener algún instrumento distinto de 00"
    target = bank[0]
    g.cursor_step = 0
    g.pv.set_instr(0, g.track, target)
    assert g._instr(0) == target
    ed.goto("instrument")
    assert ed.instrument_menu.instr_id == target, (
        f"Ctrl+derecha debe ir al {target:02X} del step, "
        f"no al {ed.instrument_menu.instr_id:02X}")
    print(f"  PHRASE -> INSTRUMENT abre el {target:02X} del step OK")

    # A+dcha en INST vacío pone 00, luego 01; Ctrl+dcha abre el puesto
    g.cursor_step = 1
    g.cursor_col = 1
    g.pv.set_instr(1, g.track, None)
    g.edit(RIGHT)                       # vacío + -> 00
    g.edit(RIGHT)                       # 00 -> 01
    chosen = g._instr(1)
    assert chosen is not None
    ed.goto("instrument")
    assert ed.instrument_menu.instr_id == chosen, (
        f"tras poner {chosen:02X} en PHRASE debe abrir ese, "
        f"fue {ed.instrument_menu.instr_id:02X}")
    print(f"  A+dcha pone {chosen:02X} y Ctrl+dcha abre ese OK")

    # step con `..`: se hereda el instrumento de arriba (no se queda en 00)
    other = bank[1] if len(bank) > 1 else target
    g.pv.set_instr(0, g.track, other)
    g.pv.set_instr(1, g.track, None)
    g.pv.set_instr(2, g.track, None)
    g.pv.set_instr(3, g.track, None)
    g.cursor_step = 3
    assert g._instr(3) is None
    assert g.effective_instr(3) == other
    ed.goto("instrument")
    assert ed.instrument_menu.instr_id == other, (
        f"step vacío debe heredar {other:02X}, "
        f"fue {ed.instrument_menu.instr_id:02X}")
    print(f"  PHRASE -> INSTRUMENT hereda {other:02X} del step anterior OK")


def main():
    from robotracker2 import Robotracker2App  # noqa: E402

    app = Robotracker2App()

    def _go(_dt):
        try:
            _run(app)
            print("TODOS LOS TESTS OK")
        except Exception:                            # noqa: BLE001
            import traceback
            traceback.print_exc()
        finally:
            app.stop()

    Clock.schedule_once(_go, 0)
    app.run()


if __name__ == "__main__":
    main()
