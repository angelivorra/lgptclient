"""Modelos LGPT para el editor: vistas song / chain / phrase.

En LGPT cada canal referencia sus propias chains y phrases: la parrilla
SONG da una chain por canal y fila, y cada step de la chain apunta a una
phrase global de 16 steps. Las tres vistas reusan el mismo widget de
editor (length/num_tracks/cell + set_* para editar):

- `SongView`: 256 filas × 9 canales de índices de chain.
- `ChainView`: los 16 steps de la chain de cada canal en una fila de song.
- `PhraseView`: los 16 steps de la phrase de cada canal en un step de chain.

La escritura muta los arrays del LGPTProject en memoria; guardar a disco es
cosa de `lgpt_writer.save_project` (en sinte).
"""

from dataclasses import dataclass
from pathlib import Path

from sinte_bridge import (CHANNEL_COUNT, EXTRA_TRACK, LGPTProject,
                          expand_song, note_byte_to_name)
from robots import ROBOT_INSTR

# Instrumento 00: las canciones nuevas de LGPT lo traen; las legacy a
# veces no (p.ej. lgpt_abduccion arranca en 10). El engine usa 00 como
# last_instr por defecto, y robotracker2 no tiene UI de creación.
INSTR_0 = 0

# Params de un Sample vacío, alineados con lo que escribe LGPT en el XML
# para que el roundtrip abra igual en el tracker original.
SAMPLE_INSTR_DEFAULTS = {
    "sample": "",
    "volume": "255",
    "interpol": "linear",
    "crush": "16",
    "crushdrive": "255",
    "downsample": "0",
    "root note": "60",
    "fine tune": "127",
    "pan": "127",
    "filter cut": "255",
    "filter res": "0",
    "filter type": "0",
    "filter mode": "original",
    "attenuate": "255",
    "start": "0",
    "loopmode": "none",
    "slices": "1",
    "loopstart": "0",
    "end": "0",
    "table": "-1",
    "table automation": "false",
    "feedback tune": "176",
    "feedback mix": "0",
    "print fx": "none",
    "pad with silence": "0",
    "effect amount": "0",
}

EMPTY = 0xFF
SONG_ROWS = 256
CHAIN_LEN = 16
PHRASE_LEN = 16
NUM_TRACKS = CHANNEL_COUNT

NOTE_NAMES = ("C-", "C#", "D-", "D#", "E-", "F-",
              "F#", "G-", "G#", "A-", "A#", "B-")

# Comandos fx soportados por el engine de sinte (fourcc, 4 chars).
FX_COMMANDS = ("VOLM", "KILL", "FADE", "DLAY", "LEGA", "SLID", "TABL", "STOP",
               "HOP ", "MDCC", "MDPG", "MVEL", "CHRD", "ARPR", "FCUT", "FRES",
               "FMOD")
FX_EMPTY = "----"

# Límites del formato LGPT
MAX_CHAINS = 255
MAX_PHRASES = 255
MAX_INSTRUMENTS = 255          # 00..FE; FF es EMPTY


def alloc_chain(project: LGPTProject) -> int | None:
    """Primera chain no referenciada por la song."""
    used = {b for b in project.song if b != EMPTY}
    for i in range(MAX_CHAINS):
        if i not in used:
            return i
    return None


def referenced_phrases(project: LGPTProject) -> set[int]:
    """Phrases apuntadas por alguna chain que la song usa (no leftovers
    de chains que ya no están en la parrilla)."""
    used_c = {b for b in project.song if b != EMPTY}
    n = len(project.chains)
    out = set()
    for c in used_c:
        base = c * CHAIN_LEN
        for s in range(CHAIN_LEN):
            i = base + s
            if i >= n:
                break
            b = project.chains[i]
            if b != EMPTY:
                out.add(b)
    return out


def referenced_instruments(project: LGPTProject) -> set[int]:
    """Instrumentos apuntados por alguna phrase que la song usa."""
    n = len(project.instruments)
    out = set()
    for ph in referenced_phrases(project):
        base = ph * PHRASE_LEN
        for s in range(PHRASE_LEN):
            i = base + s
            if i >= n:
                break
            b = project.instruments[i]
            if b != EMPTY:
                out.add(b)
    return out


def _alloc_id_above(used: set[int], src: int, limit: int) -> int | None:
    """Primer id en 0..limit-1 que no está en `used`, mayor que `src`
    (circular). `src` < 0 busca desde 00."""
    start = 0 if src < 0 else src + 1
    for i in range(start, limit):
        if i not in used:
            return i
    for i in range(0 if src < 0 else src):
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


def alloc_chain_above(project: LGPTProject, src: int) -> int | None:
    """Primera chain libre con índice mayor que `src`; si no hay ninguna por
    encima, da la vuelta y busca desde 0 (búsqueda circular). Devuelve None
    solo si la song referencia TODAS las chains (espacio lleno)."""
    used = {b for b in project.song if b != EMPTY}
    for i in range(src + 1, MAX_CHAINS):
        if i not in used:
            return i
    for i in range(src):
        if i not in used:
            return i
    return None


def alloc_unreferenced_phrase_above(project: LGPTProject,
                                    src: int) -> int | None:
    """Primera phrase no referenciada en la canción, con índice mayor que
    `src` (búsqueda circular). `src` < 0 busca desde 00. No mira si la
    phrase tiene notas: solo si alguna chain de la song la apunta."""
    used = referenced_phrases(project)
    return _alloc_id_above(used, src, MAX_PHRASES)


def alloc_unreferenced_instr_above(project: LGPTProject,
                                   src: int) -> int | None:
    """Primer instrumento no referenciado en la canción, mayor que `src`
    (circular). `src` < 0 busca desde 00. Solo mira IDs en phrases que la
    song usa, no si el instrumento existe en el banco."""
    return _alloc_id_above(referenced_instruments(project), src,
                           MAX_INSTRUMENTS)


def alloc_phrase_above(project: LGPTProject, src: int) -> int | None:
    """Primera phrase libre con índice mayor que `src`; si no hay ninguna por
    encima, da la vuelta y busca desde 0 (búsqueda circular). Devuelve None
    solo si las chains referencian TODAS las phrases (espacio lleno)."""
    used = {b for b in project.chains if b != EMPTY}
    for i in range(src + 1, MAX_PHRASES):
        if i not in used:
            return i
    for i in range(src):
        if i not in used:
            return i
    return None


def duplicate_chain(project: LGPTProject, src: int) -> int | None:
    """Copia la chain `src` (16 steps + transposes) a la primera chain libre
    con índice mayor que `src` (o, si no hay, la primera libre desde 0).
    Devuelve el índice nuevo, o None si no hay ningún hueco libre."""
    dst = alloc_chain_above(project, src)
    if dst is None:
        return None
    s0 = src * CHAIN_LEN
    d0 = dst * CHAIN_LEN
    project.chains[d0:d0 + CHAIN_LEN] = project.chains[s0:s0 + CHAIN_LEN]
    project.transposes[d0:d0 + CHAIN_LEN] = project.transposes[s0:s0 + CHAIN_LEN]
    return dst


def duplicate_phrase(project: LGPTProject, src: int) -> int | None:
    """Copia la phrase `src` (16 steps: notas, instrumentos y fx) a la primera
    phrase libre con índice mayor que `src` (o, si no hay, la primera libre
    desde 0). Devuelve el índice nuevo, o None si no hay ningún hueco libre."""
    dst = alloc_phrase_above(project, src)
    if dst is None:
        return None
    s0 = src * PHRASE_LEN
    d0 = dst * PHRASE_LEN
    project.notes[d0:d0 + PHRASE_LEN] = project.notes[s0:s0 + PHRASE_LEN]
    project.instruments[d0:d0 + PHRASE_LEN] = (
        project.instruments[s0:s0 + PHRASE_LEN])
    project.cmd1[d0:d0 + PHRASE_LEN] = project.cmd1[s0:s0 + PHRASE_LEN]
    project.param1[d0:d0 + PHRASE_LEN] = project.param1[s0:s0 + PHRASE_LEN]
    project.cmd2[d0:d0 + PHRASE_LEN] = project.cmd2[s0:s0 + PHRASE_LEN]
    project.param2[d0:d0 + PHRASE_LEN] = project.param2[s0:s0 + PHRASE_LEN]
    return dst



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


def inherited_instr(view: "PhraseView", row: int, track: int) -> int | None:
    """Instrumento efectivo del step: el propio, o el último hacia atrás.

    En LGPT un step con instrumento vacío (`FF`) hereda el de la nota
    anterior. Sirve para abrir INSTRUMENT y para el instrumento por
    defecto al pintar una nota.
    """
    for s in range(row, -1, -1):
        i = view._index(s, track)
        if i is not None and view.project.instruments[i] != EMPTY:
            return int(view.project.instruments[i])
    return None


def find_songs(songs_dir: Path) -> list[Path]:
    """Proyectos LGPT = subdirectorios con lgptsav.dat."""
    songs_dir = Path(songs_dir)
    return sorted(d for d in songs_dir.iterdir()
                  if d.is_dir() and (d / "lgptsav.dat").exists())


def load_project(project_dir: Path) -> LGPTProject:
    project = LGPTProject(Path(project_dir))
    project.load()
    return project


def _ensure_width(project: LGPTProject):
    """El buffer SONG en memoria siempre tiene NUM_TRACKS columnas."""
    project.song = expand_song(project.song)


def ensure_track_0(project: LGPTProject) -> bool:
    """Crea la pista/canal 0 si la canción legacy no lo trae.

    - Instrumento 00 (Sample vacío) si no está en el banco: sin él las
      notas que heredan `last_instr=0` quedan mudas, y no hay UI para
      crear instrumentos.
    - Chain en SONG fila 0 / canal 0 si la columna entera está vacía, para
      poder entrar en CHAIN/PHRASE de esa pista sin crearla a mano.

    Devuelve True si ha creado algo (en memoria; el writer lo persiste
    al guardar). No marca dirty: las canciones legacy se parchean cada
    carga hasta el primer save, sin diálogo de cambios al salir.
    """
    _ensure_width(project)
    created = False
    if INSTR_0 not in project.instrument_bank:
        project.instrument_bank[INSTR_0] = {
            "type": "Sample",
            "params": dict(SAMPLE_INSTR_DEFAULTS),
        }
        created = True
    col_used = any(
        project.song[row * NUM_TRACKS + INSTR_0] != EMPTY
        for row in range(min(SONG_ROWS, len(project.song) // NUM_TRACKS))
    )
    if not col_used and project.song:
        if SongView(project).new_chain(0, INSTR_0) is not None:
            created = True
    return created


def ensure_extra_track(project: LGPTProject) -> bool:
    """Crea la novena pista (canal 8) si la columna está vacía.

    Es la pista extra de robotracker (visualmente la primera). Las
    canciones LGPT de 8 canales llegan sin ella: se asigna una chain
    vacía en la fila 0 para poder entrar en CHAIN/PHRASE. No marca dirty.
    """
    _ensure_width(project)
    created = False
    col_used = any(
        project.song[row * NUM_TRACKS + EXTRA_TRACK] != EMPTY
        for row in range(min(SONG_ROWS, len(project.song) // NUM_TRACKS))
    )
    if not col_used and project.song:
        if SongView(project).new_chain(0, EXTRA_TRACK) is not None:
            created = True
    return created


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


def compact_sequencer(project: LGPTProject) -> tuple[int, int]:
    """Compact Sequencer, fiel al `Project::Purge` del LGPT original:
    borra in-place (SIN renumerar) las chains que la song no usa y las
    phrases que ninguna chain usada referencia. No toca tables/grooves.
    Devuelve (n_chains, n_phrases) — lo que tenía contenido y se vacía."""
    _ensure_width(project)
    used_c = set(used_chains(project))
    used_p = {project.chains[c * CHAIN_LEN + s]
              for c in used_c for s in range(CHAIN_LEN)
              if project.chains[c * CHAIN_LEN + s] != EMPTY}

    n_chains = 0
    for c in range(MAX_CHAINS):
        if c in used_c:
            continue
        i = c * CHAIN_LEN
        if (project.chains[i:i + CHAIN_LEN] == bytes([EMPTY]) * CHAIN_LEN
                and project.transposes[i:i + CHAIN_LEN] == bytes(CHAIN_LEN)):
            continue
        project.chains[i:i + CHAIN_LEN] = bytes([EMPTY]) * CHAIN_LEN
        project.transposes[i:i + CHAIN_LEN] = bytes(CHAIN_LEN)
        n_chains += 1

    n_phrases = 0
    for p in range(MAX_PHRASES):
        if p in used_p:
            continue
        i = p * PHRASE_LEN
        if not any(project.notes[i + s] != EMPTY
                   or project.instruments[i + s] != EMPTY
                   or project.cmd1[i + s] != FX_EMPTY
                   or project.param1[i + s]
                   or project.cmd2[i + s] != FX_EMPTY
                   or project.param2[i + s]
                   for s in range(PHRASE_LEN)):
            continue
        project.notes[i:i + PHRASE_LEN] = bytes([EMPTY]) * PHRASE_LEN
        project.instruments[i:i + PHRASE_LEN] = bytes([EMPTY]) * PHRASE_LEN
        for s in range(PHRASE_LEN):
            project.cmd1[i + s] = FX_EMPTY
            project.param1[i + s] = 0
            project.cmd2[i + s] = FX_EMPTY
            project.param2[i + s] = 0
        n_phrases += 1

    return n_chains, n_phrases


def compact_instruments(project: LGPTProject) -> tuple[int, list[str]]:
    """Compact Instruments, fiel al `Project::PurgeInstruments` original:
    elimina del banco los instrumentos que NINGUNA phrase referencia (se
    miran TODAS las frases, también las de chains no usadas). INSTR_0 (00)
    y ROBOT_INSTR (0x80, canal de robotas) nunca se eliminan: robotracker2
    no tiene UI de creación de instrumentos y perderlos dejaría la pista 0
    o el canal de robotas mudo para siempre.
    Devuelve (n_eliminados, wavs_sin_usar) — los .wav de <song>/samples/ que
    ningún instrumento Sample restante referencia (para el borrado opcional
    del disco)."""
    _ensure_width(project)
    used = {b for b in project.instruments if b != EMPTY}
    n = 0
    for iid in list(project.instrument_bank.keys()):
        if iid in (INSTR_0, ROBOT_INSTR) or iid in used:
            continue
        del project.instrument_bank[iid]
        n += 1

    referenced = {ins["params"].get("sample", "")
                  for ins in project.instrument_bank.values()
                  if ins["type"] == "Sample"}
    samples_dir = project.dir / "samples"
    wavs = sorted(p.name for p in samples_dir.glob("*.wav"))
    return n, [name for name in wavs if name not in referenced]


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
        p = view.project
        if col == "instr":
            cur = None if i is None or p.instruments[i] == EMPTY \
                else p.instruments[i]
            if cur is None:
                if delta <= 0:
                    return False
                # vacío + A+dcha = 00; vacío + A+arr = 10
                view.set_instr(row, track,
                               0 if abs(delta) == 1 else min(0xFE, abs(delta)))
                return True
            view.set_instr(row, track, max(0, min(0xFE, cur + delta)))
            return True
        if i is None:
            return False
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
    """Parrilla song completa: 256 filas × 9 canales de chain index."""

    length = SONG_ROWS
    num_tracks = NUM_TRACKS
    editable_cols = ("note",)

    def __init__(self, project: LGPTProject):
        _ensure_width(project)
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
        _ensure_width(project)
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
        _ensure_width(project)
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
