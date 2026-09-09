"""Tipos de acorde para el comando de phrase CHRD.

El parámetro (byte bajo) es el índice en CHORD_TYPES. Los nombres caben
en 4 caracteres: es el ancho de la columna de parámetro del tracker.
Los intervalos son semitonos sobre la nota raíz de la fila.
"""

# (etiqueta, intervalos). Índice = valor del param de CHRD.
CHORD_TYPES: list[tuple[str, tuple[int, ...]]] = [
    ("maj", (4, 7)),
    ("min", (3, 7)),
    ("dim", (3, 6)),
    ("aug", (4, 8)),
    ("sus2", (2, 7)),
    ("sus4", (5, 7)),
    ("7", (4, 7, 10)),
    ("maj7", (4, 7, 11)),
    ("min7", (3, 7, 10)),
    ("dim7", (3, 6, 9)),
    ("hdim", (3, 6, 10)),   # semidisminuido (m7b5)
    ("6", (4, 7, 9)),
    ("min6", (3, 7, 9)),
    ("add9", (4, 7, 14)),
    ("9", (4, 7, 10, 14)),
    ("m9", (3, 7, 10, 14)),
]


def chord_intervals(param: int) -> tuple[int, ...]:
    """Intervalos del tipo de acorde; () si el índice no existe."""
    idx = param & 0xFF
    if idx >= len(CHORD_TYPES):
        return ()
    return CHORD_TYPES[idx][1]


def chord_label(param: int) -> str:
    """Etiqueta de 4 chars para la columna de parámetro, o hex si no hay tipo."""
    idx = param & 0xFF
    if idx >= len(CHORD_TYPES):
        return f"{param:04X}"
    return CHORD_TYPES[idx][0].ljust(4)


def cycle_chord(param: int, delta: int) -> int:
    """Siguiente/anterior tipo, cíclico. Fuera de rango arranca en 0."""
    n = len(CHORD_TYPES)
    idx = param & 0xFF
    if idx >= n:
        idx = 0
        if delta < 0:
            return (n + delta) % n
        return delta % n
    return (idx + delta) % n


def expand_chord_notes(root: int, intervals: tuple[int, ...]) -> list[int]:
    """Raíz + tensiones, descartando lo que se salga de 0..127."""
    notes = [root]
    for t in intervals:
        n = root + t
        if 0 <= n < 128:
            notes.append(n)
    return notes
