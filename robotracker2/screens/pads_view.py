"""Pantalla PADS: configuración por canción de los 4 pads sampler.

Una cuadrícula 2×2 (como el bloque 7/8/3/4 del LPD8) más la fila GUARDAR.
Cada pad muestra el WAV asignado (nombre resuelto contra la biblioteca de
pads, pads/ en la raíz del repo — no hay banco global, solo config por
canción) o "—" y el volumen efectivo (0-100%) como barra. Al disparar
(sample MIDI) el pad destella.

La configuración vive en memoria (engine + cfg de MidiControl) hasta
guardar: la fila GUARDAR de abajo (A sobre ella) o Guardar de la canción
la persisten en el robotraca.json (claves "pads" y "pad_volume"); NO toca
el flag de "canción sucia" del editor (el robotraca.json no es el
lgptsav.dat).

Solo dibuja: el estado y la persistencia viven en MidiControl
(set_state/pads_state/assign_pad/set_pad_volume/save). Controles (los
resuelve la app en _dispatch_pads):

- arr/abj: cambiar de pad (y bajar a la fila GUARDAR)
- izq/dcha: volumen -/+5 (solo en las filas de pad)
- A: navegador de la biblioteca de pads (asigna el WAV elegido);
     sobre la fila GUARDAR, guarda
- B: quitar la asignación del pad
- select: no hace nada aquí (guardar es la fila GUARDAR)
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_EMPTY,
                   COLOR_HINT, COLOR_NAME, COLOR_OK, COLOR_ROW_CURSOR,
                   COLOR_VOL, core_label)

PADS = 4                            # pads sampler de la canción (engine 0-3)
SAVE_ROW = PADS                     # fila extra de abajo: GUARDAR
PAD_NOTES = ["7", "8", "3", "4"]    # botones físicos del LPD8 (sample1-4)
ROW_H = dp(64)                      # fila título / GUARDAR / hint
FONT = dp(20)
FONT_SMALL = dp(16)
NAME_MAX = 22


class PadsGrid(Widget):
    SAVE_ROW = SAVE_ROW             # fila GUARDAR (última del cursor)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pads = [(None, 0)] * PADS   # (nombre_o_None, vol_pct)
        self.cursor = 0
        self.pulse = [0.0] * PADS
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_state(self, pads):
        """Inyecta [(nombre, vol_pct)] de los pads 1-4
        (MidiControl.pads_state)."""
        if pads != self.pads:
            self.pads = pads
            self._redraw()

    def hit(self, idx):
        """Destello al disparar el pad `idx` (0-3) desde MIDI."""
        if 0 <= idx < PADS:
            self.pulse[idx] = 1.0
            self._redraw()

    def tick_pulse(self, dt):
        decay = dt * 4.0
        alive = False
        for i in range(PADS):
            if self.pulse[i] > 0:
                self.pulse[i] = max(0.0, self.pulse[i] - decay)
                alive = True
        if alive:
            self._redraw()

    def move(self, button):
        if button == UP:
            self.cursor = max(0, self.cursor - 1)
        elif button == DOWN:
            self.cursor = min(self.SAVE_ROW, self.cursor + 1)
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
            self._tex[key] = tex
        return tex

    def _text_left(self, x, y, w, text, color, h=ROW_H, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th), pos=(x, y + (h - th) / 2))

    def _text_center(self, x, y, w, text, color, h=ROW_H, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (h - th) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            w = min(self.width - dp(60), dp(640))
            x0 = self.x + (self.width - w) / 2
            top = self.y + self.height - dp(24)
            self._text_left(x0, top - ROW_H, w, "PADS", COLOR_ACCENT,
                            h=ROW_H)
            hint = ("arr/abj: pad · izq/dcha: ±5 · A: sample/guardar · "
                    "B: quitar")
            self._text_left(x0, self.y + dp(8), w, hint, COLOR_HINT,
                            h=ROW_H, font_size=FONT_SMALL)
            gap = dp(12)
            cell_w = (w - gap) / 2
            grid_top = top - ROW_H - dp(8)
            save_h = ROW_H
            grid_bottom = self.y + dp(8) + ROW_H + dp(12) + save_h
            cell_h = max(dp(88), (grid_top - grid_bottom - gap) / 2)
            for i in range(PADS):
                col, row = i % 2, i // 2
                x = x0 + col * (cell_w + gap)
                y = grid_top - (row + 1) * cell_h - row * gap
                self._draw_pad(i, x, y, cell_w, cell_h)
            y_save = grid_bottom - save_h
            if self.cursor == self.SAVE_ROW:
                Color(*COLOR_ROW_CURSOR)
                Rectangle(pos=(x0, y_save), size=(w, save_h))
                Color(*COLOR_OK)
                RoundedRectangle(pos=(x0 + dp(3), y_save + dp(3)),
                                 size=(w - dp(6), save_h - dp(6)),
                                 radius=[dp(6)])
                Color(*COLOR_ROW_CURSOR)
                RoundedRectangle(pos=(x0 + dp(7), y_save + dp(7)),
                                 size=(w - dp(14), save_h - dp(14)),
                                 radius=[dp(4)])
                self._text_center(x0, y_save, w, "GUARDAR", COLOR_OK,
                                  h=save_h)
            else:
                self._text_center(x0, y_save, w, "GUARDAR", COLOR_HINT,
                                  h=save_h)

    def _draw_pad(self, i, x, y, w, h):
        selected = i == self.cursor
        name, pct = self.pads[i]
        a = self.pulse[i]
        Color(*COLOR_ROW_CURSOR)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(8)])
        if selected:
            Color(*COLOR_ACCENT)
            RoundedRectangle(pos=(x + dp(2), y + dp(2)),
                             size=(w - dp(4), h - dp(4)), radius=[dp(7)])
            Color(*COLOR_ROW_CURSOR)
            RoundedRectangle(pos=(x + dp(6), y + dp(6)),
                             size=(w - dp(12), h - dp(12)), radius=[dp(5)])
        if a > 0:
            Color(1, 1, 1, 0.40 * a)
            RoundedRectangle(pos=(x + dp(3), y + dp(3)),
                             size=(w - dp(6), h - dp(6)), radius=[dp(6)])
        label = f"PAD {i + 1}  [{PAD_NOTES[i]}]"
        self._text_left(x + dp(14), y + h - dp(36), w - dp(28), label,
                        COLOR_ACCENT if selected else COLOR_BORDER,
                        h=dp(28), font_size=FONT)
        if name and len(name) > NAME_MAX:
            name = name[:NAME_MAX - 1] + "…"
        self._text_left(x + dp(14), y + dp(36), w - dp(28),
                        name if name else "—",
                        COLOR_NAME if name else COLOR_EMPTY,
                        h=dp(28), font_size=FONT_SMALL)
        bar_x, bar_y = x + dp(14), y + dp(12)
        bar_w, bar_h = w - dp(70), dp(10)
        Color(*COLOR_BORDER)
        RoundedRectangle(pos=(bar_x, bar_y), size=(bar_w, bar_h),
                         radius=[dp(3)])
        fill = max(dp(2), bar_w * max(0, min(100, pct)) / 100.0)
        Color(*COLOR_VOL)
        RoundedRectangle(pos=(bar_x, bar_y), size=(fill, bar_h),
                         radius=[dp(3)])
        self._text_left(bar_x + bar_w + dp(8), y + dp(4), dp(48),
                        f"{pct}%", COLOR_VOL, h=dp(24),
                        font_size=FONT_SMALL)
