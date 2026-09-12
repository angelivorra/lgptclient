"""Iconos de tipo de pista (Phosphor Icons).

Los dibujos vectoriales (Line + joint miter) en la Odin se disparaban y
tapaban media pantalla. Aquí se pinta un glifo Phosphor anclado al
centro `(cx, cy)`.
"""

from screens.icons import draw_icon


def draw_track_icon(cx, cy, size, kind, color, bg=(0, 0, 0, 1)):
    """Dibuja el icono de `kind` centrado en `(cx, cy)`."""
    draw_icon(cx, cy, size, kind, color)
