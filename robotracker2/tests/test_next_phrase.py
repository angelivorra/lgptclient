"""Doble A en CHAIN: la celda apunta a la siguiente phrase no referenciada.

No copia contenido. Libre = no aparece en ninguna chain de la song
(da igual si la phrase tiene notas). Búsqueda circular por encima del actual.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgpt_model import (CHAIN_LEN, EMPTY, FX_EMPTY, MAX_INSTRUMENTS,  # noqa: E402
                        MAX_PHRASES, NUM_TRACKS, PHRASE_LEN, SONG_ROWS,
                        ChainView, PhraseView, alloc_unreferenced_instr_above,
                        alloc_unreferenced_phrase_above)
from sinte_bridge import LGPTProject  # noqa: E402


def _make_project(tmp: Path) -> LGPTProject:
    p = LGPTProject(tmp)
    p.root = object()
    p.project = {"tempo": "120", "master": "100", "transpose": "0"}
    p.song = bytearray([EMPTY] * (NUM_TRACKS * SONG_ROWS))
    p.chains = bytearray([EMPTY] * (255 * CHAIN_LEN))
    p.transposes = bytearray(255 * CHAIN_LEN)
    p.notes = bytearray([EMPTY] * (255 * PHRASE_LEN))
    p.instruments = bytearray([EMPTY] * (255 * PHRASE_LEN))
    p.cmd1 = [FX_EMPTY] * (255 * PHRASE_LEN)
    p.param1 = [0] * (255 * PHRASE_LEN)
    p.cmd2 = [FX_EMPTY] * (255 * PHRASE_LEN)
    p.param2 = [0] * (255 * PHRASE_LEN)
    p.tables = {}
    p.grooves = bytearray()
    p.instrument_bank = {}
    p.song[0] = 0
    p.chains[0] = 0xA0
    p.chains[1] = 0xA0                 # A0 sigue usada en otro step
    return p


def _occupy(p: LGPTProject, phrase_ids, start_row=1):
    """Una chain por phrase, step 0, en filas de SONG a partir de start_row."""
    for i, pid in enumerate(phrase_ids):
        row = start_row + i
        p.song[row * NUM_TRACKS] = row  # chain = row
        p.chains[row * CHAIN_LEN] = pid


def test_next_unreferenced_phrase():
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_project(Path(tmp))
        cv = ChainView(p, 0)

        # A0 → A1 (A1 no está en la canción). Notas de A1 no se tocan.
        p.notes[0xA1 * PHRASE_LEN] = 60
        assert alloc_unreferenced_phrase_above(p, 0xA0) == 0xA1
        cv.set_value(0, 0, 0xA1)
        assert cv.phrase_at(0, 0) == 0xA1
        assert p.notes[0xA1 * PHRASE_LEN] == 60, "no debe copiar el contenido"
        print("  A0 → A1 sin copiar notas OK")

        # A1 → A2; A0 sigue referenciada en step 1
        assert alloc_unreferenced_phrase_above(p, 0xA1) == 0xA2
        cv.set_value(0, 0, 0xA2)
        print("  A1 → A2 OK")

        # Todo ocupado salvo A1: al dar la vuelta A1 es el único hueco
        _occupy(p, [i for i in range(MAX_PHRASES) if i != 0xA1], start_row=1)
        assert alloc_unreferenced_phrase_above(p, 0xA2) == 0xA1, \
            "debe envolver a A1, el único id no referenciado"
        cv.set_value(0, 0, 0xA1)
        assert cv.phrase_at(0, 0) == 0xA1
        print("  A2 → A1 (A1 libre de nuevo) OK")


def _occupy_instrs(p: LGPTProject, instr_ids, start_phrase=1):
    """Reparte IDs de instrumento en phrases usadas por la song."""
    for i, iid in enumerate(instr_ids):
        ph = start_phrase + i // PHRASE_LEN
        st = i % PHRASE_LEN
        p.instruments[ph * PHRASE_LEN + st] = iid
        # chain 0, steps 1.. cubren phrases extra; si no caben, otra chain
        if 1 <= ph < CHAIN_LEN:
            p.chains[ph] = ph
        else:
            row = ph
            p.song[row * NUM_TRACKS] = row
            p.chains[row * CHAIN_LEN] = ph


def test_next_unreferenced_instr():
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_project(Path(tmp))
        p.chains[0] = 0
        p.instruments[0] = 0xA0
        p.instruments[1] = 0xA0
        pv = PhraseView(p, 0, 0)

        assert alloc_unreferenced_instr_above(p, 0xA0) == 0xA1
        pv.set_instr(0, 0, 0xA1)
        print("  instr A0 → A1 OK")

        assert alloc_unreferenced_instr_above(p, 0xA1) == 0xA2
        pv.set_instr(0, 0, 0xA2)
        print("  instr A1 → A2 OK")

        _occupy_instrs(p, [i for i in range(MAX_INSTRUMENTS) if i != 0xA1])
        assert alloc_unreferenced_instr_above(p, 0xA2) == 0xA1, \
            "debe envolver a A1, el único id no referenciado"
        pv.set_instr(0, 0, 0xA1)
        print("  instr A2 → A1 (A1 libre de nuevo) OK")


if __name__ == "__main__":
    test_next_unreferenced_phrase()
    test_next_unreferenced_instr()
    print("TODOS LOS TESTS OK")
