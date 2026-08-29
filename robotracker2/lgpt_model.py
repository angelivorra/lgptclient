"""Modelos LGPT para el editor: vistas song / chain / phrase.

En LGPT cada canal referencia sus propias chains y phrases: la parrilla
SONG da una chain por canal y fila, y cada step de la chain apunta a una
phrase global de 16 steps. Las tres vistas reusan el mismo widget de
editor (length/num_tracks/cell + set_* para editar):

- `SongView`: 256 filas × 8 canales de índices de chain.
- `ChainView`: los 16 steps de la chain de cada canal en una fila de song.
- `PhraseView`: los 16 steps de la phrase de cada canal en un step de chain.

La escritura muta los arrays del LGPTProject en memoria; guardar a disco es
cosa de `lgpt_writer.save_project` (en sinte).
"""

from dataclasses import dataclass
from pathlib import Path

from sinte_bridge import LGPTProject, note_byte_to_name

EMPTY = 0xFF
SONG_ROWS = 256
CHAIN_LEN = 16
PHRASE_LEN = 16
NUM_TRACKS = 8

NOTE_NAMES = ("C-", "C#", "D-", "D#", "E-", "F-",
              "F#", "G-", "G#", "A-", "A#", "B-")

# Comandos fx soportados por el engine de sinte (fourcc, 4 chars).
FX_COMMANDS = ("VOLM", "KILL", "DLAY", "LEGA", "TABL", "STOP",
               "HOP ", "MDCC", "MDPG", "MVEL")
FX_EMPTY = "----"

# Límites del formato LGPT
MAX_CHAINS = 255
MAX_PHRASES = 255


def alloc_chain(project: LGPTProject) -> int | None:
    """Primera chain no referenciada por la song."""
    used = {b for b in project.song if b != EMPTY}
    for i in range(MAX_CHAINS):
        if i not in used:
            return i
    return None


def alloc_phrase(project: LGPTProject) -> int | None:
    """Primera phrase no referenciada por ninguna chain."""
    used = {b for b in project.chains if b != EMPTY}
    for i in range(MAX_PHRASES):
        if i not in used:
            return i
    return None


@dataclass
class Cell:
    note: str | None = None    # "C-4" (o índice hex en vistas song/chain)
    instr: str | None = None   # "01" (hex)
    fx1: str | None = None     # "VOLM 0040"
    fx2: str | None = None


def _fx(cmd: str, param: int) -> str | None:
    cmd = cmd.strip()
    return f"{cmd} {param:04X}" if cmd and cmd != "----" else None


def _hex(value: int) -> str | None:
    return None if value == EMPTY else f"{value:02X}"


def find_songs(songs_dir: Path) -> list[Path]:
    """Proyectos LGPT = subdirectorios con lgptsav.dat."""
    songs_dir = Path(songs_dir)
    return sorted(d for d in songs_dir.iterdir()
                  if d.is_dir() and (d / "lgptsav.dat").exists())


def load_project(project_dir: Path) -> LGPTProject:
    project = LGPTProject(Path(project_dir))
    project.load()
    return project


def note_name_to_byte(name: str) -> int:
    """"C-4" -> byte de nota LGPT (inverso de note_byte_to_name)."""
    semi = NOTE_NAMES.index(name[:2])
    octave = int(name[2])
    return (octave + 2) * 12 + semi


def used_chains(project: LGPTProject) -> list[int]:
    """Chains referenciadas en la song, ordenadas."""
    return sorted({b for b in project.song if b != EMPTY})


def used_phrases(project: LGPTProject) -> list[int]:
    """Phrases referenciadas en alguna chain, ordenadas."""
    return sorted({b for b in project.chains if b != EMPTY})


def _cycle(values: list[int], current: int | None, delta: int) -> int | None:
    """Valor siguiente/anterior de la lista ordenada. Con celda vacía:
    + = el primero, - = el último. None si no hay candidatos."""
    if not values:
        return None
    if current in values:
        return values[(values.index(current) + delta) % len(values)]
    return values[0] if delta > 0 else values[-1]


def nudge_cell(view, row: int, track: int, delta: int,
               col: str | None = None) -> bool:
    """A+flechas estilo LGPT: incremento directo del valor de la celda,
    clamp 0..0xFE (notas 0..B-8). No cicla: suma crudo."""
    if isinstance(view, SongView):
        cur = view.chain_at(row, track)
        if cur == EMPTY:
            return False
        view.set_value(row, track, max(0, min(0xFE, cur + delta)))
        return True
    if isinstance(view, ChainView):
        cur = view.phrase_at(row, track)
        if cur is None:
            return False
        view.set_value(row, track, max(0, min(0xFE, cur + delta)))
        return True
    if isinstance(view, PhraseView):
        i = view._index(row, track)
        if i is None:
            return False
        p = view.project
        if col == "instr":
            if p.instruments[i] == EMPTY:
                return False
            view.set_instr(row, track,
                           max(0, min(0xFE, p.instruments[i] + delta)))
            return True
        if col == "note":
            if p.notes[i] == EMPTY:
                return False
            view.set_note(row, track,
                          max(0, min((8 + 2) * 12 + 11, p.notes[i] + delta)))
            return True
    return False


# ---------------------------------------------------------------------------
# Portapapeles (bloques de celdas, estilo LGPT)
# ---------------------------------------------------------------------------
def read_cell(view, row: int, track: int):
    """Contenido completo y copiable de una celda (None = vacía)."""
    if isinstance(view, PhraseView):
        i = view._index(row, track)
        if i is None:
            return None
        p = view.project
        return (None if p.notes[i] == EMPTY else p.notes[i],
                None if p.instruments[i] == EMPTY else p.instruments[i],
                p.cmd1[i], p.param1[i], p.cmd2[i], p.param2[i])
    if isinstance(view, SongView):
        v = view.chain_at(row, track)
        return None if v == EMPTY else v
    return view.phrase_at(row, track)  # ChainView


def write_cell(view, row: int, track: int, data):
    """Escribe una celda leída con read_cell (None = vaciar)."""
    if isinstance(view, PhraseView):
        if data is None:
            if view._index(row, track) is None:
                return
            view.set_note(row, track, None)
            view.set_instr(row, track, None)
            view.clear_fx(row, track, 1)
            view.clear_fx(row, track, 2)
            return
        note, instr, c1, p1, c2, p2 = data
        view.set_note(row, track, note)
        view.set_instr(row, track, instr)
        view.set_fx_cmd(row, track, 1, c1)
        view.set_fx_param(row, track, 1, p1)
        view.set_fx_cmd(row, track, 2, c2)
        view.set_fx_param(row, track, 2, p2)
        return
    view.set_value(row, track, data)


def clip_region(view, r0: int, t0: int, r1: int, t1: int,
                cut: bool = False) -> list[list]:
    """Lee el rectángulo (r0..r1, t0..t1); con cut=True lo vacía."""
    data = []
    for r in range(r0, r1 + 1):
        line = []
        for t in range(t0, t1 + 1):
            line.append(read_cell(view, r, t))
            if cut:
                write_cell(view, r, t, None)
        data.append(line)
    return data


def paste_region(view, row: int, track: int, data: list[list]):
    """Pega un bloque de clip_region con esquina superior en (row, track)."""
    for dr, line in enumerate(data):
        r = row + dr
        if r >= view.length:
            break
        for dt, cell in enumerate(line):
            t = track + dt
            if t >= view.num_tracks:
                break
            write_cell(view, r, t, cell)


def cycle_cell(view, row: int, track: int, delta: int, col: str | None = None,
               octave: int = 4, last_instr: int | None = None) -> bool:
    """+/- sobre la celda del cursor (dedo o mando): cicla SOLO por valores
    existentes; en celda vacía con + crea chain/phrase nueva. En phrase:
    col "instr" cicla por el banco, col "note" sube/baja semitonos.
    Devuelve True si hubo cambio."""
    if isinstance(view, SongView):
        cur = view.chain_at(row, track)
        if cur == EMPTY and delta > 0:
            return view.new_chain(row, track) is not None
        v = _cycle(used_chains(view.project), None if cur == EMPTY else cur,
                   delta)
        if v is None:
            return False
        view.set_value(row, track, v)
        return True
    if isinstance(view, ChainView):
        cur = view.phrase_at(row, track)
        if cur is None and delta > 0:
            return view.new_phrase(row, track) is not None
        v = _cycle(used_phrases(view.project), cur, delta)
        if v is None:
            return False
        view.set_value(row, track, v)
        return True
    if isinstance(view, PhraseView):
        i = view._index(row, track)
        if col == "instr":
            values = sorted(view.project.instrument_bank.keys())
            cur = None if i is None or view.project.instruments[i] == EMPTY \
                else view.project.instruments[i]
            v = _cycle(values, cur, delta)
            if v is None:
                return False
            view.set_instr(row, track, v)
            return True
        if col == "note":
            cur = None if i is None or view.project.notes[i] == EMPTY \
                else view.project.notes[i]
            if cur is None:
                if delta <= 0:
                    return False
                note = note_name_to_byte(f"C-{octave}")
            else:
                note = max(0, min((9 + 2) * 12 - 1, cur + delta))
            view.set_note(row, track, note)
            if last_instr is not None and view.cell(row, track).instr is None:
                view.set_instr(row, track, last_instr)
            return True
    return False


class SongView:
    """Parrilla song completa: 256 filas × 8 canales de chain index."""

    length = SONG_ROWS
    num_tracks = NUM_TRACKS
    editable_cols = ("note",)

    def __init__(self, project: LGPTProject):
        self.project = project

    def chain_at(self, row: int, track: int) -> int:
        return self.project.song[row * NUM_TRACKS + track]

    def cell(self, row: int, track: int) -> Cell:
        return Cell(note=_hex(self.chain_at(row, track)))

    def track_label(self, track: int) -> str:
        return f"CH{track + 1}"

    def set_value(self, row: int, track: int, value: int | None):
        self.project.song[row * NUM_TRACKS + track] = (
            EMPTY if value is None else value & EMPTY)

    def new_chain(self, row: int, track: int) -> int | None:
        """Asigna una chain nueva (vacía) a la celda; devuelve su índice."""
        chain = alloc_chain(self.project)
        if chain is not None:
            for s in range(CHAIN_LEN):
                self.project.chains[chain * CHAIN_LEN + s] = EMPTY
                self.project.transposes[chain * CHAIN_LEN + s] = 0
            self.project.song[row * NUM_TRACKS + track] = chain
        return chain


class ChainView:
    """Los 16 steps de la chain de cada canal en una fila de la song."""

    length = CHAIN_LEN
    num_tracks = NUM_TRACKS
    editable_cols = ("note",)

    def __init__(self, project: LGPTProject, song_row: int = 0):
        self.project = project
        self.song_row = song_row

    def chain_of(self, track: int) -> int | None:
        chain = self.project.song[self.song_row * NUM_TRACKS + track]
        return None if chain == EMPTY else chain

    def _chain_of(self, track: int, create: bool = False) -> int | None:
        chain = self.chain_of(track)
        if chain is None and create:
            chain = SongView(self.project).new_chain(self.song_row, track)
        return chain

    def phrase_at(self, step: int, track: int) -> int | None:
        chain = self.chain_of(track)
        if chain is None:
            return None
        phrase = self.project.chains[chain * CHAIN_LEN + step]
        return None if phrase == EMPTY else phrase

    def cell(self, row: int, track: int) -> Cell:
        phrase = self.phrase_at(row, track)
        return Cell(note=None if phrase is None else f"{phrase:02X}")

    def track_label(self, track: int) -> str:
        chain = self.chain_of(track)
        return f"{track + 1} C{chain:02X}" if chain is not None else f"{track + 1} --"

    def set_value(self, row: int, track: int, value: int | None):
        chain = self._chain_of(track, create=value is not None)
        if chain is None:
            return
        self.project.chains[chain * CHAIN_LEN + row] = (
            EMPTY if value is None else value & EMPTY)

    def new_phrase(self, row: int, track: int) -> int | None:
        """Asigna una phrase nueva (vacía) al step; crea la chain si hace
        falta. Devuelve el índice de la phrase."""
        chain = self._chain_of(track, create=True)
        if chain is None:
            return None
        phrase = alloc_phrase(self.project)
        if phrase is not None:
            i = phrase * PHRASE_LEN
            self.project.notes[i:i + PHRASE_LEN] = bytes([EMPTY]) * PHRASE_LEN
            self.project.instruments[i:i + PHRASE_LEN] = (
                bytes([EMPTY]) * PHRASE_LEN)
            for s in range(PHRASE_LEN):
                self.project.cmd1[i + s] = FX_EMPTY
                self.project.param1[i + s] = 0
                self.project.cmd2[i + s] = FX_EMPTY
                self.project.param2[i + s] = 0
            self.project.chains[chain * CHAIN_LEN + row] = phrase
        return phrase


class PhraseView:
    """Los 16 steps de la phrase de cada canal en un step de chain.

    Interfaz compatible con PatternEditor (length/num_tracks/cell).
    """

    length = PHRASE_LEN
    num_tracks = NUM_TRACKS
    editable_cols = ("note", "instr")

    def __init__(self, project: LGPTProject, song_row: int = 0,
                 chain_step: int = 0):
        self.project = project
        self.song_row = song_row
        self.chain_step = chain_step

    def phrase_of(self, track: int) -> int | None:
        p = self.project
        if not p.song or not p.chains:
            return None
        chain = p.song[self.song_row * NUM_TRACKS + track]
        if chain == EMPTY:
            return None
        phrase = p.chains[chain * CHAIN_LEN + self.chain_step]
        return None if phrase == EMPTY else phrase

    def track_label(self, track: int) -> str:
        phrase = self.phrase_of(track)
        return (f"{track + 1} P{phrase:02X}" if phrase is not None
                else f"{track + 1} --")

    def _index(self, row: int, track: int, create: bool = False) -> int | None:
        phrase = self.phrase_of(track)
        if phrase is None and create:
            chain = ChainView(self.project, self.song_row)
            phrase = chain.new_phrase(self.chain_step, track)
        return None if phrase is None else phrase * PHRASE_LEN + row

    def cell(self, row: int, track: int) -> Cell:
        i = self._index(row, track)
        if i is None:
            return Cell()
        p = self.project
        return Cell(
            note=None if p.notes[i] == EMPTY else note_byte_to_name(p.notes[i]),
            instr=_hex(p.instruments[i]),
            fx1=_fx(p.cmd1[i], p.param1[i]),
            fx2=_fx(p.cmd2[i], p.param2[i]),
        )

    # -- edición ------------------------------------------------------------
    # Al editar una celda vacía (sin phrase en ese canal) se crean la chain
    # y la phrase sobre la marcha, como en el Piggy original.
    def set_note(self, row: int, track: int, note_byte: int | None):
        i = self._index(row, track, create=note_byte is not None)
        if i is not None:
            self.project.notes[i] = EMPTY if note_byte is None else note_byte

    def set_instr(self, row: int, track: int, value: int | None):
        i = self._index(row, track, create=value is not None)
        if i is not None:
            self.project.instruments[i] = EMPTY if value is None else value & EMPTY

    def fx_cmd_at(self, row: int, track: int, which: int) -> str:
        i = self._index(row, track)
        if i is None:
            return FX_EMPTY
        return (self.project.cmd1 if which == 1 else self.project.cmd2)[i]

    def fx_param_at(self, row: int, track: int, which: int) -> int:
        i = self._index(row, track)
        if i is None:
            return 0
        return (self.project.param1 if which == 1 else self.project.param2)[i]

    def set_fx_cmd(self, row: int, track: int, which: int, cmd: str):
        assert len(cmd) == 4
        i = self._index(row, track, create=cmd != FX_EMPTY)
        if i is not None:
            (self.project.cmd1 if which == 1 else self.project.cmd2)[i] = cmd

    def set_fx_param(self, row: int, track: int, which: int, value: int):
        i = self._index(row, track, create=True)
        if i is not None:
            params = self.project.param1 if which == 1 else self.project.param2
            params[i] = value & 0xFFFF

    def clear_fx(self, row: int, track: int, which: int):
        i = self._index(row, track)
        if i is not None:
            if which == 1:
                self.project.cmd1[i] = FX_EMPTY
                self.project.param1[i] = 0
            else:
                self.project.cmd2[i] = FX_EMPTY
                self.project.param2[i] = 0
