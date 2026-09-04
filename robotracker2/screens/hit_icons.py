"""Iconos de golpe (bombo / caja / caja2) para PHRASE y LIVE."""

from kivy.graphics import Color, Ellipse, Line

from robots import HIT_PARTS


def draw_hit_icon(x, cy, size, note, color):
    """Dibuja el glifo (o combo) anclado a la izquierda en `x`, centro `cy`."""
    parts = HIT_PARTS.get(note, (note,))
    n = len(parts)
    gap = size * 0.10
    iw = (size - gap * (n - 1)) / n
    for i, part in enumerate(parts):
        cx = x + iw / 2 + i * (iw + gap)
        if part == 62:
            draw_kick(cx, cy, iw, color)
        elif part == 63:
            draw_snare(cx, cy, iw, color, hoop=False)
        else:
            draw_snare(cx, cy, iw, color, hoop=True)


def draw_kick(cx, cy, s, color):
    r = s * 0.42
    Color(*color)
    Line(circle=(cx, cy, r), width=1.5)
    Ellipse(pos=(cx - r * 0.28, cy - r * 0.28),
            size=(r * 0.56, r * 0.56))


def draw_snare(cx, cy, s, color, hoop=False):
    ew, eh = s * 0.82, s * 0.50
    Color(*color)
    Line(ellipse=(cx - ew / 2, cy - eh / 2, ew, eh), width=1.4)
    Line(points=[cx - ew * 0.28, cy - eh * 0.55,
                 cx + ew * 0.22, cy + eh * 0.55], width=1.1)
    Line(points=[cx + ew * 0.22, cy - eh * 0.55,
                 cx - ew * 0.28, cy + eh * 0.55], width=1.1)
    if hoop:
        Line(circle=(cx, cy, s * 0.14), width=1.1)
