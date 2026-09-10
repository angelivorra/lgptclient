"""En PHRASE, nota e instrumento viajan juntos.

Cortar/borrar una nota también quita el instrumento; pegar la nota lo
restaura; A en un hueco de NOTE usa el último instrumento usado.
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kivy.clock import Clock  # noqa: E402

from controls import RIGHT  # noqa: E402
from lgpt_model import EMPTY, note_name_to_byte  # noqa: E402
from screens.phrase_view import PhraseGrid  # noqa: E402
from sinte_bridge import LGPTProject  # noqa: E402


def _make_project(tmp: Path) -> LGPTProject:
    p = LGPTProject(tmp)
    p.root = object()
    p.project = {"tempo": "120", "master": "100", "transpose": "0"}
    p.song = bytearray([EMPTY] * (8 * 256))
    p.chains = bytearray([EMPTY] * (255 * 16))
    p.transposes = bytearray(255 * 16)
    p.notes = bytearray([EMPTY] * (255 * 16))
    p.instruments = bytearray([EMPTY] * (255 * 16))
    p.cmd1 = ["----"] * (255 * 16)
    p.param1 = [0] * (255 * 16)
    p.cmd2 = ["----"] * (255 * 16)
    p.param2 = [0] * (255 * 16)
    p.tables = {}
    p.grooves = bytearray()
    p.instrument_bank = {
        0x00: {"type": "Sample", "params": {"sample": "a.wav"}},
        0x10: {"type": "Sample", "params": {"sample": "b.wav"}},
        0x20: {"type": "Sample", "params": {"sample": "c.wav"}},
    }
    p.song[0] = 0
    p.chains[0] = 0
    return p


def _grid(project) -> PhraseGrid:
    g = PhraseGrid()
    g.set_context(project, 0, 0, 0)
    g.last_instr = None
    g.clipboard = None
    return g


def _run(_app):
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = _make_project(Path(tmp))
        g = _grid(p)
        t = g.track
        note = note_name_to_byte("C-4")

        g.pv.set_note(0, t, note)
        g.pv.set_instr(0, t, 0x10)
        g.cursor_step, g.cursor_col = 0, 0
        g.delete()
        assert g._note(0) is None, "B en NOTE debe borrar la nota"
        assert g._instr(0) is None, "B en NOTE debe borrar también el instrumento"
        print("  B en NOTE corta nota+instrumento OK")

        g.pv.set_note(0, t, note)
        g.pv.set_instr(0, t, 0x10)
        g.cursor_step, g.cursor_col = 0, 0
        g.sel_anchor = (0, 0)
        g.sel_stage = 1
        g.cut_selection()
        assert g._note(0) is None
        assert g._instr(0) is None
        assert g.block_clipboard == [[(note, 0x10)]]
        g.cursor_step = 1
        g.paste_block()
        assert g._note(1) == note, "pegar el bloque debe restaurar la nota"
        assert g._instr(1) == 0x10, "pegar el bloque debe restaurar el instrumento"
        print("  cortar/pegar bloque NOTE lleva el instrumento OK")

        g.pv.set_note(2, t, note)
        g.pv.set_instr(2, t, 0x20)
        g.cursor_step, g.cursor_col = 2, 0
        g.a_tap()
        assert g.clipboard == ("note", (note, 0x20))
        g.pv.set_note(3, t, None)
        g.pv.set_instr(3, t, None)
        g.cursor_step = 3
        g.a_tap()
        assert g._note(3) == note, "A en hueco con porta NOTE pega la nota"
        assert g._instr(3) == 0x20, "A en hueco pega también el instrumento"
        print("  A copia/pega nota+instrumento OK")

        g.clipboard = None
        g.last_instr = 0x10
        g.pv.set_note(5, t, None)
        g.pv.set_instr(5, t, None)
        g.cursor_step, g.cursor_col = 5, 0
        g.a_tap()
        assert g._note(5) == note, "A en hueco sin porta pone C-octava"
        assert g._instr(5) == 0x10, "A en hueco usa el último instrumento"
        print("  A en hueco usa last_instr OK")

        g.clipboard = None
        g.last_instr = 0x20
        g.cursor_step = 6
        g.edit(RIGHT)                   # A+dcha en nota vacía
        assert g._note(6) == note
        assert g._instr(6) == 0x20, "A+dcha en hueco usa last_instr"
        print("  A+dcha en hueco usa last_instr OK")


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
