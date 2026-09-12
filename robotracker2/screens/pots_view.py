"""Pantalla EFECTOS: configuración por canción de los knobs del controlador.

Cuadrícula 2×2 de knobs (POT 1/2 arriba, 5/6 abajo — los del LPD8) más
GUARDAR. El arco y la aguja siguen el **CC en vivo** del controlador
(0-127); el campo % sigue siendo la mezcla dry/wet (`fx_mix`).

- CANAL: canal al que afecta (1-9; en el robotraca.json se guarda 0-8),
  con el icono y el nombre del tipo de esa pista. Si el JSON trae varios
  ("1,2:acid"), se muestra el primero y al editar queda en uno solo.
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
from screens.icons import draw_icon
from screens.track_icons import draw_track_icon
from sinte_bridge import EFFECT_PRESETS
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_BORDER, COLOR_EMPTY,
                   COLOR_HINT, COLOR_NAME, COLOR_OK, COLOR_VOL, core_label)

_CARD = (0.14, 0.14, 0.15, 1)
_CHIP = (0.10, 0.10, 0.11, 1)
from tracks import DEFAULT_TRACKS, kind_at, track_caption

POT_NOS = [1, 2, 5, 6]              # knobs configurables del controlador
EFFECT_CYCLE = ["off", *EFFECT_PRESETS]
COL_HINTS = (
    "A+dir: cambia CANAL (1–9)",
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
        self.tracks = list(DEFAULT_TRACKS)
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

    def set_tracks(self, kinds):
        kinds = list(kinds)
        if kinds != self.tracks:
            self.tracks = kinds
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
            w = min(self.width - dp(48), dp(640))
            x0 = self.x + (self.width - w) / 2
            top = self.y + self.height - dp(16)
            self._draw_heading(x0, top - ROW_H, w, "effects", "EFECTOS")
            gap = dp(14)
            cell_w = (w - gap) / 2
            grid_top = top - ROW_H - dp(4)
            save_h = dp(52)
            grid_bottom = self.y + dp(8) + HINT_H + dp(8) + save_h
            cell_h = max(dp(140), (grid_top - grid_bottom - gap) / 2)
            for i in range(4):
                col, row = i % 2, i // 2
                x = x0 + col * (cell_w + gap)
                y = grid_top - (row + 1) * cell_h - row * gap
                self._draw_pot(i, x, y, cell_w, cell_h)
            self._draw_save(x0, grid_bottom - save_h, w, save_h - dp(6))
            self._draw_hint(x0, w)
            if self.picker is not None:
                self._draw_picker()

    def _draw_heading(self, x, y, w, icon, title):
        draw_icon(x + dp(16), y + ROW_H / 2, dp(24), icon, COLOR_ACCENT)
        self._text_left(x + dp(40), y, w, title, COLOR_ACCENT, h=ROW_H)

    def _draw_save(self, x, y, w, h):
        selected = self.cursor == self.SAVE_ROW
        bg = COLOR_OK if selected else _CARD
        ink = COLOR_BG if selected else COLOR_HINT
        Color(*bg)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(12)])
        draw_icon(x + w / 2 - dp(52), y + h / 2, dp(22), "save", ink)
        self._text_center(x + dp(16), y, w, "GUARDAR", ink, h=h)

    def _draw_pot(self, i, x, y, w, h):
        selected = i == self.cursor
        canal, efecto, pct = self.pots[i]
        Color(*(COLOR_ACCENT if selected else _CARD))
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[dp(14)])
        if selected:
            Color(*_CARD)
            RoundedRectangle(pos=(x + dp(3), y + dp(3)),
                             size=(w - dp(6), h - dp(6)), radius=[dp(12)])
        cx = x + w / 2
        r = min(w * 0.26, (h - dp(76)) * 0.40)
        cy = y + h - dp(22) - r
        cc = self.live_cc[i] if i < len(self.live_cc) else None
        live = cc is not None
        dial_pct = (cc / 127.0) * 100.0 if live else 0.0
        if live:
            dial_c = COLOR_ACCENT if selected and self.col == 2 else COLOR_OK
        else:
            dial_c = COLOR_BORDER
        self._draw_dial(cx, cy, r, dial_pct, dial_c)
        ink = COLOR_ACCENT if selected else COLOR_NAME
        title = f"POT {POT_NOS[i]}" + (f"  {cc}" if live else "")
        draw_icon(x + dp(22), cy - dp(2), dp(16), "effects", ink)
        self._text_left(x + dp(36), cy - dp(14), w - dp(48), title, ink,
                        h=dp(22), font_size=FONT_SMALL)
        on = efecto is not None
        e_txt = efecto if efecto else "—"
        p_txt = f"{pct}%" if on else "—"
        col_w = (w - dp(20)) * 0.44, (w - dp(20)) * 0.32, (w - dp(20)) * 0.24
        ly = y + dp(10)
        lx = x + dp(10)
        chip_h = dp(34)
        for c, cw in enumerate(col_w):
            cell = selected and c == self.col
            Color(*(COLOR_ACCENT if cell else _CHIP))
            RoundedRectangle(pos=(lx, ly), size=(cw - dp(4), chip_h),
                             radius=[dp(10)])
            if c == 0:
                self._draw_canal(lx, ly, cw - dp(4), canal, cell, chip_h)
            else:
                txt = e_txt if c == 1 else p_txt
                icon = "fx" if c == 1 else "mix"
                if cell:
                    color = COLOR_BG
                elif txt == "—":
                    color = COLOR_EMPTY
                elif c == 2:
                    color = COLOR_VOL
                else:
                    color = COLOR_NAME
                draw_icon(lx + dp(12), ly + chip_h / 2, dp(14), icon, color)
                self._text_left(lx + dp(24), ly, cw - dp(28), txt, color,
                                h=chip_h, font_size=FONT_SMALL)
            lx += cw

    def _draw_canal(self, x, y, w, canal, selected, h):
        """Icono de pista + '3 DRUM' (o —) en la columna CANAL."""
        color = COLOR_BG if selected else (COLOR_EMPTY if not canal else COLOR_NAME)
        if not canal:
            self._text_center(x, y, w, "—", color, h=h, font_size=FONT_SMALL)
            return
        kind = kind_at(self.tracks, canal - 1)
        s = dp(16)
        draw_track_icon(x + dp(12), y + h / 2, s, kind, color, bg=_CHIP)
        self._text_left(x + dp(24), y, w - dp(28),
                        track_caption(canal - 1, kind), color,
                        h=h, font_size=FONT_SMALL)

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
        Color(*_CARD)
        RoundedRectangle(pos=(x0, y), size=(w, HINT_H), radius=[dp(10)])
        if self.picker is not None:
            hint = "lista EFECTO · arr/abj mueve · A elige · B cierra"
        elif self.cursor == self.SAVE_ROW:
            hint = "A: guardar en la canción"
        else:
            hint = ("cruceta: knob / columna · "
                    + COL_HINTS[self.col])
        self._text_left(x0 + dp(14), y, w - dp(24), hint, COLOR_HINT,
                        h=HINT_H, font_size=FONT_SMALL)

    def _draw_picker(self):
        n = len(EFFECT_CYCLE)
        pw = dp(460)
        ph = (n + 2) * PICK_ROW_H
        px = self.x + (self.width - pw) / 2
        py = self.y + (self.height - ph) / 2
        Color(0, 0, 0, 0.62)
        Rectangle(pos=self.pos, size=self.size)
        Color(*_CARD)
        RoundedRectangle(pos=(px, py), size=(pw, ph), radius=[dp(16)])
        draw_icon(px + dp(36), py + (n + 1) * PICK_ROW_H + PICK_ROW_H / 2,
                  dp(20), "fx", COLOR_ACCENT)
        self._text_left(px + dp(52), py + (n + 1) * PICK_ROW_H, pw - dp(70),
                        "EFECTO", COLOR_ACCENT, h=PICK_ROW_H)
        for i, nombre in enumerate(EFFECT_CYCLE):
            y = py + (n - i) * PICK_ROW_H
            if i == self.picker:
                Color(*COLOR_ACCENT)
                RoundedRectangle(pos=(px + dp(12), y + dp(5)),
                                 size=(pw - dp(24), PICK_ROW_H - dp(10)),
                                 radius=[dp(10)])
                color = COLOR_BG
                icon = "yes"
            else:
                color = COLOR_NAME
                icon = "fx" if nombre != "off" else "cancel"
            draw_icon(px + dp(36), y + PICK_ROW_H / 2, dp(18), icon, color)
            self._text_left(px + dp(56), y, pw - dp(80), nombre, color,
                            h=PICK_ROW_H, font_size=FONT)
        self._text_center(px, py, pw, "A: elegir · B: cancelar", COLOR_HINT,
                          h=PICK_ROW_H, font_size=FONT_SMALL)
