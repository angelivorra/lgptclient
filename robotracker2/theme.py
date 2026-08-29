"""Estética compartida de robotracker2 (portada de robotracker).

Fondo oscuro con acento oro. Registra la fuente "Icons" (DejaVu Sans, que sí
tiene los glifos ▶ ■ ◀ ✓ ✕ que Roboto no trae) y fija el color de ventana.
"""

from pathlib import Path

from kivy.core.text import LabelBase
from kivy.core.window import Window

# Paleta robotracker (RGBA)
COLOR_BG = (0.10, 0.10, 0.12, 1)
COLOR_BAR_BG = (0.07, 0.07, 0.09, 1)
COLOR_BAR_TEXT = (0.75, 0.75, 0.80, 1)
COLOR_ACCENT = (0.95, 0.75, 0.20, 1)
COLOR_BTN = (0.18, 0.19, 0.23, 1)
COLOR_BTN_DOWN = (0.30, 0.32, 0.38, 1)
COLOR_BORDER = (0.36, 0.38, 0.46, 1)
COLOR_OK = (0.45, 0.85, 0.45, 1)
COLOR_ERROR = (0.95, 0.45, 0.40, 1)

# Roboto no trae glifos de iconos; DejaVu Sans sí. Va bundled (fonts/).
LabelBase.register("Icons", str(Path(__file__).resolve().parent
                                / "fonts" / "DejaVuSans.ttf"))


def setup_window(fullscreen=False):
    """Fondo oscuro; en ventana por defecto (PC) o pantalla completa (Odin).

    En la Odin además el launcher fuerza fullscreen por Sway; aquí basta con
    `fullscreen=True` (via --fullscreen). En PC se queda en ventana con el
    tamaño de reserva configurado (1280×720)."""
    Window.clearcolor = COLOR_BG
    Window.fullscreen = "auto" if fullscreen else False
