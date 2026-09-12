"""Pantalla EQ: 7 bandas de la mezcla final, por canción.

Bajo CHAIN en el mapa. Cada barra es un pico (60 Hz … 12 kHz, ±12 dB).
Se oye al instante; se persiste en robotraca.json (`eq`) al GUARDAR o
al guardar la canción.

Controles (los resuelve la app en `_dispatch_eq`):

- izq/dcha: banda
- arr/abj: baja a GUARDAR / vuelve a las barras
- A+arr/abj: ±1 dB · A+izq/dcha: ±3 dB
- A en GUARDAR: escribe el JSON
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from screens.icons import draw_icon
from sinte_bridge import EQ_BANDS, EQ_LABELS, EQ_MAX_DB, EQ_MIN_DB
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_EMPTY,
                   COLOR_HINT, COLOR_NAME, COLOR_OK, COLOR_VOL, core_label)

_CARD = (0.14, 0.14, 0.15, 1)
_CHIP = (0.10, 0.10, 0.11, 1)
_BAR = (0.35, 0.72, 0.42, 1)
_BAR_SEL = (0.55, 0.88, 0.55, 1)

SAVE_ROW = EQ_BANDS
ROW_H = dp(56)
FONT = dp(18)
FONT_SMALL = dp(14)
HINT_H = dp(36)


class EqGrid(Widget):
    SAVE_ROW = SAVE_ROW

    def __init__(self, **kw):
        super().__init__(**kw)
        self.gains = [0.0] * EQ_BANDS
        self.cursor = 0
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_gains(self, gains):
        gains = list(gains)[:EQ_BANDS]
        while len(gains) < EQ_BANDS:
            gains.append(0.0)
        if gains != self.gains:
            self.gains = gains
            self._redraw()

    def move(self, button):
        if button == UP:
            if self.cursor == SAVE_ROW:
                self.cursor = 0
            # en las barras, arr/abj sin A no cambia de banda
        elif button == DOWN:
            self.cursor = SAVE_ROW
        self._redraw()

    def move_band(self, delta):
        if self.cursor == SAVE_ROW:
            return
        self.cursor = (self.cursor + delta) % EQ_BANDS
        self._redraw()

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
            self._tex[key] = tex
        return tex

    def _text(self, x, y, w, h, text, color, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex,
                  pos=(x + (w - tw) / 2, y + (h - th) / 2),
                  size=(tw, th))

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            pad = dp(16)
            top = self.y + self.height - pad
            w = self.width - 2 * pad
            x0 = self.x + pad
            self._draw_heading(x0, top - ROW_H, w)
            bars_top = top - ROW_H - dp(8)
            bars_bot = self.y + pad + ROW_H + HINT_H + dp(12)
            self._draw_bars(x0, bars_bot, w, bars_top - bars_bot)
            self._draw_save(x0, self.y + pad + HINT_H, w, ROW_H)
            self._text(x0, self.y + pad, w, HINT_H,
                       "A+arr/abj ±1 dB · A+izq/dcha ±3 · A en GUARDAR",
                       COLOR_HINT, FONT_SMALL)

    def _draw_heading(self, x, y, w):
        h = ROW_H
        Color(*_CARD)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        draw_icon(x + dp(28), y + h / 2, dp(22), "eq", COLOR_ACCENT)
        self._text(x + dp(48), y, w - dp(56), h, "EQ  mezcla",
                   COLOR_NAME, FONT)

    def _draw_bars(self, x, y, w, h):
        Color(*_CARD)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        gap = dp(8)
        inner = w - 2 * dp(16)
        bw = (inner - gap * (EQ_BANDS - 1)) / EQ_BANDS
        base = y + dp(36)
        max_h = h - dp(64)
        zero_y = base + max_h * 0.5
        Color(*_CHIP)
        Rectangle(pos=(x + dp(12), zero_y), size=(w - dp(24), dp(2)))
        for i in range(EQ_BANDS):
            bx = x + dp(16) + i * (bw + gap)
            sel = self.cursor == i
            db = self.gains[i]
            if sel:
                Color(0.25, 0.32, 0.22, 1)
                RoundedRectangle(pos=(bx - dp(2), y + dp(4)),
                                 size=(bw + dp(4), h - dp(8)),
                                 radius=[dp(6)])
            Color(*(_BAR_SEL if sel else _BAR))
            if db > 0:
                bh = max(dp(2), (max_h * 0.5) * (db / EQ_MAX_DB))
                Rectangle(pos=(bx + dp(4), zero_y), size=(bw - dp(8), bh))
            elif db < 0:
                bh = max(dp(2), (max_h * 0.5) * (-db / -EQ_MIN_DB))
                Rectangle(pos=(bx + dp(4), zero_y - bh), size=(bw - dp(8), bh))
            self._text(bx, y + dp(4), bw, dp(28), EQ_LABELS[i],
                       COLOR_ACCENT if sel else COLOR_EMPTY, FONT_SMALL)
            self._text(bx, y + h - dp(32), bw, dp(28),
                       f"{db:+.0f}", COLOR_VOL if sel else COLOR_HINT,
                       FONT_SMALL)

    def _draw_save(self, x, y, w, h):
        sel = self.cursor == SAVE_ROW
        Color(*(COLOR_OK if sel else _CARD))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(10)])
        ink = COLOR_BG if sel else COLOR_NAME
        draw_icon(x + dp(28), y + h / 2, dp(20), "save", ink)
        self._text(x + dp(48), y, w - dp(56), h, "GUARDAR", ink, FONT)
