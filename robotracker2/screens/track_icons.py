"""Iconos vectoriales de tipo de pista (drum/bass/synth/noise/robot/vocoder).

Mismo estilo que `hit_icons.py` y la cabecera histórica de SONG (micrófono /
cabeza de robot): trazo + relleno, anclados al centro `(cx, cy)`.
"""

from kivy.graphics import Color, Ellipse, Line, RoundedRectangle


def draw_track_icon(cx, cy, size, kind, color, bg=(0, 0, 0, 1)):
    """Dibuja el glifo de `kind` centrado en `(cx, cy)`."""
    fn = _DRAW.get(kind, draw_synth)
    fn(cx, cy, size, color, bg)


def draw_drum(cx, cy, s, color, bg=(0, 0, 0, 1)):
    """Bombo: aro + parche."""
    r = s * 0.42
    Color(*color)
    Line(circle=(cx, cy, r), width=1.5)
    Ellipse(pos=(cx - r * 0.28, cy - r * 0.28),
            size=(r * 0.56, r * 0.56))


def draw_bass(cx, cy, s, color, bg=(0, 0, 0, 1)):
    """Altavoz / woofer."""
    Color(*color)
    Line(circle=(cx, cy, s * 0.42), width=1.5)
    Line(circle=(cx, cy, s * 0.24), width=1.3)
    er = s * 0.10
    Ellipse(pos=(cx - er, cy - er), size=(er * 2, er * 2))


def draw_synth(cx, cy, s, color, bg=(0, 0, 0, 1)):
    """Onda triangular (módulo de synth)."""
    w, h = s * 0.86, s * 0.46
    Color(*color)
    Line(points=[
        cx - w / 2, cy,
        cx - w / 4, cy + h / 2,
        cx, cy,
        cx + w / 4, cy - h / 2,
        cx + w / 2, cy,
    ], width=1.5, cap="square", joint="miter")


def draw_noise(cx, cy, s, color, bg=(0, 0, 0, 1)):
    """Estática: zigzag denso."""
    w, h = s * 0.86, s * 0.50
    xs = [cx - w / 2 + w * i / 6 for i in range(7)]
    ys = [cy, cy + h / 2, cy - h * 0.35, cy + h * 0.40,
          cy - h / 2, cy + h * 0.22, cy]
    pts = [v for pair in zip(xs, ys) for v in pair]
    Color(*color)
    Line(points=pts, width=1.4, cap="square", joint="miter")


def draw_robot(cx, cy, s, color, bg=(0, 0, 0, 1)):
    """Cabeza de robot (canal de robotas)."""
    hw, hh = s * 0.64, s * 0.52
    Color(*color)
    Line(points=[cx, cy + hh * 0.5, cx, cy + hh * 0.5 + s * 0.16],
         width=1.4)
    Ellipse(pos=(cx - s * 0.06, cy + hh * 0.5 + s * 0.10),
            size=(s * 0.12, s * 0.12))
    RoundedRectangle(pos=(cx - hw / 2, cy - hh / 2), size=(hw, hh),
                     radius=[s * 0.14])
    Color(*bg)
    er = s * 0.12
    Ellipse(pos=(cx - hw * 0.26 - er / 2, cy - er / 2), size=(er, er))
    Ellipse(pos=(cx + hw * 0.26 - er / 2, cy - er / 2), size=(er, er))


def draw_vocoder(cx, cy, s, color, bg=(0, 0, 0, 1)):
    """Micrófono (canal de voz / vocoder)."""
    Color(*color)
    bw, bh = s * 0.40, s * 0.56
    RoundedRectangle(pos=(cx - bw / 2, cy - bh * 0.10),
                     size=(bw, bh), radius=[bw / 2])
    Line(circle=(cx, cy - bh * 0.02, s * 0.34, 120, 240), width=1.4)
    Line(points=[cx, cy - bh * 0.46, cx, cy - bh * 0.10], width=1.4)
    Line(points=[cx - s * 0.20, cy - bh * 0.46,
                 cx + s * 0.20, cy - bh * 0.46], width=1.4)


_DRAW = {
    "drum": draw_drum,
    "bass": draw_bass,
    "synth": draw_synth,
    "noise": draw_noise,
    "robot": draw_robot,
    "vocoder": draw_vocoder,
}
