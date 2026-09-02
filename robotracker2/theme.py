"""Estética de robotracker2: skin inspirada en Renoise 3 (tema gris por defecto).

Cromado gris, datos en columnas de color (nota clara, instrumento verde, FX
amarillo/cian), selección azul, playhead verde. Sin acento oro.

Registra "Icons" (DejaVu Sans, glifos ▶ ■). Fija el color de ventana.
"""

from pathlib import Path

from kivy.core.text import LabelBase
from kivy.core.window import Window

_FONTS = Path(__file__).resolve().parent / "fonts"

# Paleta Renoise 3 (RGBA 0-1). Gris de cuerpo, no negro puro.
COLOR_BG = (0.20, 0.20, 0.20, 1)
COLOR_BAR_BG = (0.14, 0.14, 0.14, 1)
COLOR_BAR_TEXT = (0.78, 0.78, 0.76, 1)
COLOR_ACCENT = (0.42, 0.58, 0.82, 1)      # azul de selección / foco
COLOR_BTN = (0.32, 0.32, 0.32, 1)
COLOR_BTN_DOWN = (0.42, 0.42, 0.44, 1)
COLOR_BORDER = (0.10, 0.10, 0.10, 1)
COLOR_OK = (0.32, 0.78, 0.42, 1)
COLOR_ERROR = (0.90, 0.36, 0.32, 1)

# Patrón / rejillas
COLOR_CELL = (0.88, 0.88, 0.86, 1)
COLOR_EMPTY = (0.40, 0.40, 0.40, 1)
COLOR_LINENUM = (0.52, 0.52, 0.48, 1)
COLOR_LINENUM_CUR = (0.95, 0.92, 0.62, 1)
COLOR_BEAT = (0.16, 0.16, 0.16, 1)
COLOR_BAR = (0.13, 0.13, 0.14, 1)
COLOR_ROW_CURSOR = (0.26, 0.32, 0.40, 1)
COLOR_SEL = (0.28, 0.46, 0.72, 0.38)
COLOR_PLAY = (0.10, 0.38, 0.20, 1)
COLOR_HINT_BG = (0.12, 0.12, 0.13, 0.96)
COLOR_HEADER_BG = (0.16, 0.16, 0.16, 1)
COLOR_HEADER_TXT = (0.68, 0.68, 0.64, 1)
COLOR_MUTED = (0.86, 0.34, 0.32, 1)
COLOR_MUTE_OVERLAY = (0, 0, 0, 0.45)
COLOR_ICON = COLOR_ACCENT
COLOR_ARROW_DIM = (0.38, 0.38, 0.38, 1)

# Columnas de datos (como el pattern de Renoise)
COLOR_NOTE = (0.90, 0.90, 0.88, 1)
COLOR_INSTR = (0.42, 0.82, 0.48, 1)
COLOR_VALUE = (0.86, 0.78, 0.38, 1)       # valores editables / volumen
COLOR_TRSP = (0.70, 0.72, 0.68, 1)
COLOR_FX1 = (0.86, 0.78, 0.38, 1)
COLOR_FX2 = (0.48, 0.76, 0.90, 1)
COLOR_FX3 = (0.72, 0.55, 0.86, 1)
COLOR_HIT = (0.92, 0.55, 0.32, 1)
COLOR_SCREEN = (0.50, 0.74, 0.92, 1)

# Menús / browsers
COLOR_ITEM = COLOR_CELL
COLOR_LABEL = COLOR_CELL
COLOR_NAME = COLOR_CELL
COLOR_WAV = COLOR_CELL
COLOR_DIR = (0.52, 0.74, 0.92, 1)
COLOR_HDR = COLOR_LINENUM
COLOR_HINT = COLOR_LINENUM
COLOR_ACTION = COLOR_BAR_TEXT
COLOR_VOL = COLOR_OK
COLOR_MISSING = COLOR_ERROR
COLOR_SCRIM = (0.06, 0.06, 0.06, 0.94)
COLOR_PREVIEW_BG = COLOR_BAR_BG
COLOR_PREVIEW_BORDER = COLOR_BORDER
COLOR_HEADER = COLOR_ACCENT

# Altura de la tira D S C P I (fila media / arriba / abajo)
ROW_COLORS = {
    1: COLOR_ACCENT,
    0: (0.40, 0.72, 0.78, 1),
    2: (0.72, 0.52, 0.78, 1),
}

LabelBase.register("Icons", str(_FONTS / "DejaVuSans.ttf"))


def setup_window(fullscreen=False):
    """Fondo gris Renoise; ventana (PC) o pantalla completa (Odin)."""
    Window.clearcolor = COLOR_BG
    Window.fullscreen = "auto" if fullscreen else False
