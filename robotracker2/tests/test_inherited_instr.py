"""Instrumento efectivo de PHRASE y salto a INSTRUMENT.

Sin Kivy: el step con `..` hereda el instrumento de arriba (como LGPT),
y ese id tiene que estar en el banco para que Ctrl+derecha no se quede
en 00.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lgpt_model import (EMPTY, FX_EMPTY, PHRASE_LEN, PhraseView,  # noqa: E402
                        SAMPLE_INSTR_DEFAULTS, ensure_instrument,
                        inherited_instr, nudge_cell)
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
    p.cmd1 = [FX_EMPTY] * (255 * 16)
    p.param1 = [0] * (255 * 16)
    p.cmd2 = [FX_EMPTY] * (255 * 16)
    p.param2 = [0] * (255 * 16)
    p.tables = {}
    p.grooves = bytearray()
    p.instrument_bank = {
        0x00: {"type": "Sample", "params": {"sample": "a.wav"}},
        0x01: {"type": "Sample", "params": {"sample": "b.wav"}},
        0x10: {"type": "Sample", "params": {"sample": "c.wav"}},
        0x20: {"type": "Sample", "params": {"sample": "d.wav"}},
    }
    p.song[0] = 0
    p.chains[0] = 0
    return p


def test_inherited_and_select():
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_project(Path(tmp))
        pv = PhraseView(p, 0, 0)

        pv.set_instr(0, 0, 0x10)
        assert inherited_instr(pv, 0, 0) == 0x10
        assert inherited_instr(pv, 3, 0) == 0x10, \
            "step vacío debe heredar el instrumento de arriba"
        assert inherited_instr(pv, 0, 1) is None

        pv.set_instr(2, 0, 0x20)
        assert inherited_instr(pv, 1, 0) == 0x10
        assert inherited_instr(pv, 2, 0) == 0x20
        print("  inherited_instr camina hacia atrás OK")

        # simula select_instrument: el id del step tiene que estar en el banco
        bank = sorted(p.instrument_bank)
        iid = inherited_instr(pv, 0, 0)
        assert iid in bank, iid
        assert bank[bank.index(iid)] == 0x10
        print("  el instrumento del step está en el banco (no cae al 00) OK")

        # A+dcha ±1 hex, A+arr ±0x10. No cicla el banco (01→10).
        pv.set_instr(0, 0, 0x01)
        assert nudge_cell(pv, 0, 0, 1, col="instr")
        assert p.instruments[0] == 0x02
        pv.set_instr(0, 0, 0x01)
        assert nudge_cell(pv, 0, 0, 0x10, col="instr")
        assert p.instruments[0] == 0x11
        pv.set_instr(0, 0, None)
        assert nudge_cell(pv, 0, 0, 1, col="instr")
        assert p.instruments[0] == 0x00
        pv.set_instr(1, 0, None)
        assert nudge_cell(pv, 1, 0, 0x10, col="instr")
        assert p.instruments[1] == 0x10
        print("  A+dcha ±1 / A+arr ±0x10 hex OK")

        assert 0x50 not in p.instrument_bank
        assert ensure_instrument(p, 0x50)
        assert p.instrument_bank[0x50]["type"] == "Sample"
        assert p.instrument_bank[0x50]["params"]["sample"] == ""
        for key, val in SAMPLE_INSTR_DEFAULTS.items():
            assert p.instrument_bank[0x50]["params"][key] == val, key
        assert not ensure_instrument(p, 0x50), "no recrea uno que ya existe"
        assert ensure_instrument(p, 0x81)
        assert p.instrument_bank[0x81]["type"] == "Midi"
        assert not ensure_instrument(p, 0xFF)
        assert not ensure_instrument(p, None)
        print("  ensure_instrument crea Sample/Midi y no pisa OK")


if __name__ == "__main__":
    test_inherited_and_select()
    print("TODOS LOS TESTS OK")
