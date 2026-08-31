"""Mapa de navegación de pantallas estilo LittleGPTracker.

Las pantallas están en una rejilla 2D (el cuadro del indicador de LGPT) y se
navega con Ctrl+flechas hacia la pantalla adyacente. Diagrama:

EFECTOS PROJECT           GROOVE
PADS    SONG    CHAIN     PHRASE    INSTRUMENT
        CONFIG            TABLE     TABLE

PROJECT está encima de SONG y GROOVE encima de PHRASE; CONFIG debajo de SONG;
PADS a la izquierda de SONG (pads sampler por canción) y EFECTOS encima de
PADS (efectos de los knobs del controlador por canción); PHRASE e INSTRUMENT
tienen cada uno su TABLE debajo. Cada entrada: clave -> ((col, fila),
etiqueta, letra). Fila 0 = arriba.
"""

SCREENS = {
    "pots":             ((0, 0), "EFECTOS",    "E"),
    "project":          ((1, 0), "PROJECT",    "P"),
    "groove":           ((3, 0), "GROOVE",     "G"),
    "pads":             ((0, 1), "PADS",       "D"),
    "song":             ((1, 1), "SONG",       "S"),
    "chain":            ((2, 1), "CHAIN",      "C"),
    "phrase":           ((3, 1), "PHRASE",     "P"),
    "instrument":       ((4, 1), "INSTRUMENT", "I"),
    "config":           ((1, 2), "CONFIG",     "C"),
    "phrase_table":     ((3, 2), "TABLE",      "T"),
    "instrument_table": ((4, 2), "TABLE",      "T"),
}


GRID_COLS = 5
GRID_ROWS = 3

_BY_POS = {pos: key for key, (pos, _label, _letter) in SCREENS.items()}


def neighbor(current, dx, dy):
    """Pantalla adyacente en la dirección (dx, dy) o None si no hay ninguna."""
    (cx, cy), _label, _letter = SCREENS[current]
    return _BY_POS.get((cx + dx, cy + dy))
