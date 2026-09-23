"""Tipos de pista (nombre + icono) por canción.

Cada canal 0-9 tiene un tipo de `TRACK_KINDS`. Se persiste en el
robotraca.json como lista de 10 nombres, en orden de canal LGPT (0-9):

    "tracks": ["drum", "bass", "synth", "synth", "noise", "synth",
               "vocoder", "robot", "synth", "lights"]

Sin la clave, se usan `DEFAULT_TRACKS` (vocoder, robot y luces en los
canales 6, 7 y 9; la pista extra es el canal 8). En pantalla las
columnas/filas no van 0..9: la extra se muestra **la primera**, y
vocoder/robot/luces al final:

    extra(8), 0, 1, 2, 3, 4, 5, vocoder, robot, luces(9)
"""

from lgpt_model import EXTRA_TRACK, LIGHTS_TRACK, NUM_TRACKS

TRACK_KINDS = ("drum", "bass", "synth", "noise", "robot", "vocoder",
               "lights")

TRACK_LABELS = {
    "drum": "DRUM",
    "bass": "BASS",
    "synth": "SYNTH",
    "noise": "NOISE",
    "robot": "ROBOT",
    "vocoder": "VOCODER",
    "lights": "LUCES",
}

# Canal 6 = voz/vocoder, canal 7 = robotas, canal 9 = luces: fijos, no
# se ciclan.
DEFAULT_TRACKS = (
    "drum", "bass", "synth", "synth", "noise", "synth", "vocoder", "robot",
    "synth", "lights",
)

# Orden visual (SONG de izq a dcha, TRACKS de arriba a abajo): extra
# primero, vocoder, robot y luces al final.
TRACK_DISPLAY = (EXTRA_TRACK, 0, 1, 2, 3, 4, 5, 6, 7, LIGHTS_TRACK)
VOCODER_TRACK = 6
ROBOT_TRACK = 7
FIXED_TRACKS = {VOCODER_TRACK: "vocoder", ROBOT_TRACK: "robot",
                LIGHTS_TRACK: "lights"}
# En el resto de pistas no se elige vocoder/robot/luces: esas son fijas.
EDITABLE_TRACK_KINDS = ("drum", "bass", "synth", "noise")


def slot_of(track) -> int:
    """Puesto visual 0-9 del canal LGPT `track`."""
    try:
        return TRACK_DISPLAY.index(track)
    except ValueError:
        return 0


def track_at_slot(slot) -> int:
    """Canal LGPT del puesto visual `slot` (0-9)."""
    if 0 <= slot < len(TRACK_DISPLAY):
        return TRACK_DISPLAY[slot]
    return TRACK_DISPLAY[0]


def parse_tracks(cfg) -> list:
    """Lista de 10 tipos a partir del robotraca.json (`cfg` o {})."""
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
    for track, kind in FIXED_TRACKS.items():
        out[track] = kind
    return out


def cycle_kind(kind, delta) -> str:
    i = EDITABLE_TRACK_KINDS.index(kind) if kind in EDITABLE_TRACK_KINDS else 0
    return EDITABLE_TRACK_KINDS[(i + delta) % len(EDITABLE_TRACK_KINDS)]


def track_label(kind) -> str:
    return TRACK_LABELS.get(kind, TRACK_LABELS["synth"])


def kind_at(kinds, track) -> str:
    """Tipo de la pista `track` (0-9 LGPT), con default si falta."""
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
