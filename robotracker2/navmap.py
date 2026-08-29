"""Mapa de navegación de pantallas estilo LittleGPTracker.

Las pantallas están en una rejilla 2D (el cuadro del indicador de LGPT) y se
navega con Ctrl+flechas hacia la pantalla adyacente. Diagrama:

    PROJECT           GROOVE
    SONG    CHAIN     PHRASE    INSTRUMENT
                      TABLE     TABLE

PROJECT está encima de SONG y GROOVE encima de PHRASE; PHRASE e INSTRUMENT
tienen cada uno su TABLE debajo. Cada entrada:
clave -> ((col, fila), etiqueta, letra). Fila 0 = arriba.
"""

SCREENS = {
    "project":          ((0, 0), "PROJECT",    "P"),
    "groove":           ((2, 0), "GROOVE",     "G"),
    "song":             ((0, 1), "SONG",       "S"),
    "chain":            ((1, 1), "CHAIN",      "C"),
    "phrase":           ((2, 1), "PHRASE",     "P"),
    "instrument":       ((3, 1), "INSTRUMENT", "I"),
    "phrase_table":     ((2, 2), "TABLE",      "T"),
    "instrument_table": ((3, 2), "TABLE",      "T"),
}

GRID_COLS = 4
GRID_ROWS = 3

_BY_POS = {pos: key for key, (pos, _label, _letter) in SCREENS.items()}


def neighbor(current, dx, dy):
    """Pantalla adyacente en la dirección (dx, dy) o None si no hay ninguna."""
    (cx, cy), _label, _letter = SCREENS[current]
    return _BY_POS.get((cx + dx, cy + dy))
