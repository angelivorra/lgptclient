"""Tipos de pista (nombre + icono) por canción.

Cada canal 0-8 tiene un tipo de `TRACK_KINDS`. Se persiste en el
robotraca.json como lista de 9 nombres, en orden de canal LGPT (0-8):

    "tracks": ["drum", "bass", "synth", "synth", "noise", "synth",
               "vocoder", "robot", "synth"]

Sin la clave, se usan `DEFAULT_TRACKS` (vocoder y robot en los canales
6 y 7; la pista extra es el canal 8). En pantalla las columnas/filas no
van 0..8: la extra se muestra **la primera**, y vocoder/robot al final:

    extra(8), 0, 1, 2, 3, 4, 5, vocoder, robot
"""

from lgpt_model import EXTRA_TRACK, NUM_TRACKS

TRACK_KINDS = ("drum", "bass", "synth", "noise", "robot", "vocoder")

TRACK_LABELS = {
    "drum": "DRUM",
    "bass": "BASS",
    "synth": "SYNTH",
    "noise": "NOISE",
    "robot": "ROBOT",
    "vocoder": "VOCODER",
}

# Canal 6 = voz/vocoder, canal 7 = robotas, canal 8 = pista extra.
DEFAULT_TRACKS = (
    "drum", "bass", "synth", "synth", "noise", "synth", "vocoder", "robot",
    "synth",
)

# Orden visual (SONG de izq a dcha, TRACKS de arriba a abajo): extra
# primero, vocoder y robot al final.
TRACK_DISPLAY = (EXTRA_TRACK, 0, 1, 2, 3, 4, 5, 6, 7)
VOCODER_TRACK = 6
ROBOT_TRACK = 7


def slot_of(track) -> int:
    """Puesto visual 0-8 del canal LGPT `track`."""
    try:
        return TRACK_DISPLAY.index(track)
    except ValueError:
        return 0


def track_at_slot(slot) -> int:
    """Canal LGPT del puesto visual `slot` (0-8)."""
    if 0 <= slot < len(TRACK_DISPLAY):
        return TRACK_DISPLAY[slot]
    return TRACK_DISPLAY[0]


def parse_tracks(cfg) -> list:
    """Lista de 9 tipos a partir del robotraca.json (`cfg` o {})."""
    raw = (cfg or {}).get("tracks")
    out = list(DEFAULT_TRACKS)
    if isinstance(raw, list):
        for i, kind in enumerate(raw[:NUM_TRACKS]):
            if kind in TRACK_LABELS:
                out[i] = kind
    elif isinstance(raw, dict):
        for key, kind in raw.items():
            try:
                i = int(key)
            except (TypeError, ValueError):
                continue
            if 1 <= i <= NUM_TRACKS:
                i -= 1
            if 0 <= i < NUM_TRACKS and kind in TRACK_LABELS:
                out[i] = kind
    return out


def cycle_kind(kind, delta) -> str:
    i = TRACK_KINDS.index(kind) if kind in TRACK_KINDS else 0
    return TRACK_KINDS[(i + delta) % len(TRACK_KINDS)]


def track_label(kind) -> str:
    return TRACK_LABELS.get(kind, TRACK_LABELS["synth"])


def kind_at(kinds, track) -> str:
    """Tipo de la pista `track` (0-8 LGPT), con default si falta."""
    if kinds and 0 <= track < len(kinds):
        return kinds[track]
    if 0 <= track < len(DEFAULT_TRACKS):
        return DEFAULT_TRACKS[track]
    return "synth"


def track_caption(track, kind=None, kinds=None) -> str:
    """Etiqueta '1 SYNTH': número de puesto visual + tipo."""
    if kind is None:
        kind = kind_at(kinds, track)
    return f"{slot_of(track) + 1} {track_label(kind)}"
