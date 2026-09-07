"""Tipos de pista (nombre + icono) por canción.

Cada canal 0-7 tiene un tipo de `TRACK_KINDS`. Se persiste en el
robotraca.json como lista de 8 nombres:

    "tracks": ["drum", "bass", "synth", "synth", "noise", "synth", "vocoder", "robot"]

Sin la clave, se usan `DEFAULT_TRACKS` (mismos 8, con vocoder y robot en
los canales 7 y 8 como la cabecera histórica de SONG).
"""

from lgpt_model import NUM_TRACKS

TRACK_KINDS = ("drum", "bass", "synth", "noise", "robot", "vocoder")

TRACK_LABELS = {
    "drum": "DRUM",
    "bass": "BASS",
    "synth": "SYNTH",
    "noise": "NOISE",
    "robot": "ROBOT",
    "vocoder": "VOCODER",
}

# Canal 7 = voz/vocoder, canal 8 = robotas (como la cabecera histórica).
DEFAULT_TRACKS = (
    "drum", "bass", "synth", "synth", "noise", "synth", "vocoder", "robot",
)


def parse_tracks(cfg) -> list:
    """Lista de 8 tipos a partir del robotraca.json (`cfg` o {})."""
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
    """Tipo de la pista `track` (0-7), con default si falta."""
    if kinds and 0 <= track < len(kinds):
        return kinds[track]
    if 0 <= track < len(DEFAULT_TRACKS):
        return DEFAULT_TRACKS[track]
    return "synth"


def track_caption(track, kind=None, kinds=None) -> str:
    """Etiqueta '1 DRUM' (track 0-based)."""
    if kind is None:
        kind = kind_at(kinds, track)
    return f"{track + 1} {track_label(kind)}"
