"""Pantalla EFECTOS: configuración por canción de los knobs del controlador.

Cuadrícula 2×2 de knobs (POT 1/2 arriba, 5/6 abajo — los del LPD8) más
GUARDAR. El arco y la aguja siguen el **CC en vivo** del controlador
(0-127); el campo % sigue siendo la mezcla dry/wet (`fx_mix`).

- CANAL: canal al que afecta (1-8; en el robotraca.json se guarda 0-7).
  Si el JSON trae varios ("1,2:acid"), se muestra el primero y al editar
  queda en uno solo.
- EFECTO: "off" + los de EFFECT_PRESETS. "off" deja el knob sin target.
- %: mezcla dry/wet (`fx_mix`; 100 = sin fx_mix). El arco del knob es
  la posición física del CC, no este porcentaje.

La configuración vive en memoria hasta guardar (fila GUARDAR o Guardar
canción). Controles iguales que antes (arr/abj knob, izq/dcha campo).
"""

import math

from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from sinte_bridge import EFFECT_PRESETS
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_EMPTY,
                   COLOR_HINT, COLOR_HINT_BG, COLOR_NAME, COLOR_OK,
                   COLOR_ROW_CURSOR, COLOR_VOL, core_label)

POT_NOS = [1, 2, 5, 6]              # knobs configurables del controlador
EFFECT_CYCLE = ["off", *EFFECT_PRESETS]
COL_HINTS = (
    "A+dir: cambia CANAL (1–8)",
    "A+dir: cambia EFECTO · A: lista",
    "A+izq/dcha: % ±1 · A+arr/abj: % ±10",
)
ROW_H = dp(56)
FONT = dp(18)
FONT_SMALL = dp(15)
PICK_ROW_H = dp(48)
HINT_H = dp(36)
KNOB_START = 225.0                  # mínimo a las 7; el CC sube en sentido horario
KNOB_SWEEP = 270.0


class PotsGrid(Widget):
    """4 knobs (POT 1/2/5/6) + fila GUARDAR; cursor de fila y de columna
    (0=canal, 1=efecto, 2=%). `picker` no-None = lista de efectos abierta."""

    SAVE_ROW = 4

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pots = [(None, None, 100)] * 4
        self.cursor = 0
        self.col = 0
        self.picker = None
        self.live_cc = [None] * 4       # CC 0-127 del hardware, o None
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_state(self, pots):
        if pots != self.pots:
            self.pots = pots
            self._redraw()

    def set_live(self, values):
        """Posición en vivo de los 4 knobs (CC 0-127 o None)."""
        values = list(values)
        if values != self.live_cc:
            self.live_cc = values
            self._redraw()

    def move(self, button):
        if button == UP:
            self.cursor = max(0, self.cursor - 1)
        elif button == DOWN:
            self.cursor = min(self.SAVE_ROW, self.cursor + 1)
        self._redraw()

    def move_col(self, delta):
        self.col = (self.col + delta) % 3
        self._redraw()

    def open_picker(self):
        efe = self.pots[self.cursor][1]
        self.picker = EFFECT_CYCLE.index(efe) if efe in EFFECT_CYCLE else 0
        self._redraw()

    def picker_move(self, delta):
        if self.picker is not None:
            self.picker = max(0, min(len(EFFECT_CYCLE) - 1,
                                     self.picker + delta))
            self._redraw()

    def picker_selected(self):
        return EFFECT_CYCLE[self.picker] if self.picker is not None else None

    def close_picker(self):
        self.picker = None
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
            top = self.y + self.height - dp(20)
            self._text_left(x0, top - ROW_H, w, "EFECTOS", COLOR_ACCENT,
                            h=ROW_H)
            gap = dp(12)
            cell_w = (w - gap) / 2
            grid_top = top - ROW_H - dp(4)
            save_h = ROW_H
            grid_bottom = self.y + dp(8) + HINT_H + dp(8) + save_h
            cell_h = max(dp(140), (grid_top - grid_bottom - gap) / 2)
            for i in range(4):
                col, row = i % 2, i // 2
                x = x0 + col * (cell_w + gap)
                y = grid_top - (row + 1) * cell_h - row * gap
                self._draw_pot(i, x, y, cell_w, cell_h)
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
            self._draw_hint(x0, w)
            if self.picker is not None:
                self._draw_picker()

    def _draw_pot(self, i, x, y, w, h):
        selected = i == self.cursor
        canal, efecto, pct = self.pots[i]
        Color(*COLOR_ROW_CURSOR)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(8)])
        if selected:
            Color(*COLOR_ACCENT)
            RoundedRectangle(pos=(x + dp(2), y + dp(2)),
                             size=(w - dp(4), h - dp(4)), radius=[dp(7)])
            Color(*COLOR_ROW_CURSOR)
            RoundedRectangle(pos=(x + dp(6), y + dp(6)),
                             size=(w - dp(12), h - dp(12)), radius=[dp(5)])
        cx = x + w / 2
        r = min(w * 0.28, (h - dp(72)) * 0.42)
        cy = y + h - dp(18) - r
        cc = self.live_cc[i] if i < len(self.live_cc) else None
        live = cc is not None
        dial_pct = (cc / 127.0) * 100.0 if live else 0.0
        if live:
            dial_c = COLOR_ACCENT if selected and self.col == 2 else COLOR_OK
        else:
            dial_c = COLOR_BORDER
        self._draw_dial(cx, cy, r, dial_pct, dial_c)
        title = f"POT {POT_NOS[i]}" + (f"  {cc}" if live else "")
        self._text_center(x, cy - dp(8), w, title,
                          COLOR_ACCENT if selected else COLOR_BORDER,
                          h=dp(22), font_size=FONT_SMALL)
        on = efecto is not None
        # CANAL · EFECTO · %
        c_txt = f"C {canal}" if canal else "—"
        e_txt = efecto if efecto else "—"
        p_txt = f"{pct}%" if on else "—"
        labels = (c_txt, e_txt, p_txt)
        col_w = (w - dp(20)) / 3
        ly = y + dp(8)
        for c, txt in enumerate(labels):
            lx = x + dp(10) + c * col_w
            cell = selected and c == self.col
            if cell:
                Color(*COLOR_ACCENT)
                RoundedRectangle(pos=(lx + dp(2), ly + dp(2)),
                                 size=(col_w - dp(4), dp(28)),
                                 radius=[dp(4)])
                Color(*COLOR_ROW_CURSOR)
                RoundedRectangle(pos=(lx + dp(5), ly + dp(5)),
                                 size=(col_w - dp(10), dp(22)),
                                 radius=[dp(3)])
            if cell:
                color = COLOR_ACCENT
            elif txt == "—":
                color = COLOR_EMPTY
            elif c == 2:
                color = COLOR_VOL
            else:
                color = COLOR_NAME
            self._text_center(lx, ly, col_w, txt, color, h=dp(32),
                              font_size=FONT_SMALL)

    def _draw_dial(self, cx, cy, r, pct, color):
        Color(0.08, 0.08, 0.09, 1)
        Ellipse(pos=(cx - r, cy - r), size=(2 * r, 2 * r))
        Color(*COLOR_BORDER)
        Line(circle=(cx, cy, r), width=1.2)
        sweep = KNOB_SWEEP * max(0.0, min(100.0, pct)) / 100.0
        Color(*color)
        # El Line.ellipse de Kivy barre en sentido horario; cos/sin matemático
        # es antihorario. El arco usa +sweep, la aguja −sweep, para ir juntos.
        Line(ellipse=(cx - r, cy - r, 2 * r, 2 * r,
                      KNOB_START, KNOB_START + sweep),
             width=2.2)
        ang = math.radians(KNOB_START - sweep)
        Color(*color)
        Line(points=[cx, cy,
                     cx + r * 0.78 * math.cos(ang),
                     cy + r * 0.78 * math.sin(ang)],
             width=1.6)
        Color(*COLOR_BORDER)
        Ellipse(pos=(cx - dp(4), cy - dp(4)), size=(dp(8), dp(8)))

    def _draw_hint(self, x0, w):
        y = self.y + dp(8)
        Color(*COLOR_HINT_BG)
        Rectangle(pos=(x0, y), size=(w, HINT_H))
        if self.picker is not None:
            hint = "lista EFECTO · arr/abj mueve · A elige · B cierra"
        elif self.cursor == self.SAVE_ROW:
            hint = "A: guardar en la canción"
        else:
            hint = ("cruceta: knob / columna · "
                    + COL_HINTS[self.col])
        self._text_left(x0 + dp(12), y, w - dp(24), hint, COLOR_ACCENT,
                        h=HINT_H, font_size=FONT_SMALL)

    def _draw_picker(self):
        n = len(EFFECT_CYCLE)
        pw = dp(460)
        ph = (n + 2) * PICK_ROW_H
        px = self.x + (self.width - pw) / 2
        py = self.y + (self.height - ph) / 2
        Color(0, 0, 0, 0.55)
        Rectangle(pos=self.pos, size=self.size)
        Color(*COLOR_ROW_CURSOR)
        Rectangle(pos=(px, py), size=(pw, ph))
        Color(*COLOR_ACCENT)
        RoundedRectangle(pos=(px + dp(3), py + dp(3)),
                         size=(pw - dp(6), ph - dp(6)), radius=[dp(8)])
        Color(*COLOR_ROW_CURSOR)
        RoundedRectangle(pos=(px + dp(7), py + dp(7)),
                         size=(pw - dp(14), ph - dp(14)), radius=[dp(6)])
        self._text_center(px, py + (n + 1) * PICK_ROW_H, pw, "EFECTO",
                          COLOR_ACCENT, h=PICK_ROW_H)
        for i, nombre in enumerate(EFFECT_CYCLE):
            y = py + (n - i) * PICK_ROW_H
            if i == self.picker:
                Color(*COLOR_ROW_CURSOR)
                Rectangle(pos=(px + dp(10), y + dp(3)),
                          size=(pw - dp(20), PICK_ROW_H - dp(6)))
                Color(*COLOR_ACCENT)
                RoundedRectangle(pos=(px + dp(12), y + dp(5)),
                                 size=(pw - dp(24), PICK_ROW_H - dp(10)),
                                 radius=[dp(4)])
                color = COLOR_ACCENT
            else:
                color = COLOR_NAME
            self._text_left(px + dp(40), y, pw - dp(80), nombre, color,
                            h=PICK_ROW_H, font_size=FONT)
        self._text_center(px, py, pw, "A: elegir · B: cancelar", COLOR_HINT,
                          h=PICK_ROW_H, font_size=FONT_SMALL)
