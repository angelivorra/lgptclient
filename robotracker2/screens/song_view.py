"""Pantalla SONG: la parrilla 256 filas × 8 canales de índices de chain.

Clon de la pantalla Song de LGPT con estética moderna (bandas por compás/beat,
cursor redondeado dorado, adaptado a pantalla ancha tipo Odin 2). Trabaja con
botones lógicos (`controls`); la app resuelve los acordes y llama a estos
métodos:

- mover cursor (dpad), A+dir edita el valor (±1 / ±0x10; en vacío crea chain).
- A (tap): copia la celda si tiene valor; si está vacía pega el portapapeles, y
  si no hay portapapeles pone 00.
- Ctrl+S cicla la selección: libre -> filas completas -> todo lo visible.
- S copia la selección; Ctrl+A la corta; Ctrl+A sin selección pega el bloque.

La edición muta el `LGPTProject` en memoria vía `SongView`.
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from lgpt_model import (EMPTY, NUM_TRACKS, SongView, clip_region,
                        duplicate_chain, paste_region, read_cell)

from theme import COLOR_ACCENT, COLOR_BG

ROW_H = dp(30)
HEADER_H = dp(34)                       # cabecera con el nº de canal
GUTTER_W = dp(54)
FONT = dp(17)

# Canales especiales (0-index): 6 = voz (canal 7), 7 = robot (canal 8)
VOICE_TRACK = 6
ROBOT_TRACK = 7

# Colores de la parrilla
COLOR_CELL = (0.87, 0.89, 0.92, 1)     # valor de chain
COLOR_EMPTY = (0.30, 0.31, 0.36, 1)    # celda vacía "--"
COLOR_LINENUM = (0.45, 0.46, 0.52, 1)
COLOR_LINENUM_CUR = (1.0, 0.85, 0.40, 1)
COLOR_BAR = (0.16, 0.18, 0.23, 1)      # cada 16 filas (compás)
COLOR_BEAT = (0.13, 0.14, 0.18, 1)     # cada 4 filas (beat)
COLOR_ROW_CURSOR = (0.19, 0.21, 0.27, 1)
COLOR_SEL = (0.95, 0.75, 0.20, 0.30)   # selección (oro translúcido)
COLOR_PLAY = (0.16, 0.42, 0.24, 1)     # celda en el playhead (verde)
COLOR_HEADER_BG = (0.09, 0.10, 0.13, 1)
COLOR_HEADER_TXT = (0.60, 0.62, 0.70, 1)
COLOR_ICON = COLOR_ACCENT              # voz/robot resaltados en oro
COLOR_MUTED = (0.85, 0.35, 0.35, 1)   # cabecera de pista muteada (rojo)
COLOR_MUTE_OVERLAY = (0, 0, 0, 0.5)   # atenúa la columna muteada

_MOVE = {UP: (-1, 0), DOWN: (1, 0), LEFT: (0, -1), RIGHT: (0, 1)}
_EDIT = {RIGHT: 1, LEFT: -1, UP: 0x10, DOWN: -0x10}


class SongGrid(Widget):
    def __init__(self, on_change=None, **kw):
        super().__init__(**kw)
        self.view = None
        self.cursor_row = 0
        self.cursor_track = 0
        self.top_row = 0
        self.on_change = on_change
        self.clipboard = None          # bloque list[list] (o 1×1 en copia celda)
        self.sel_stage = 0             # 0=sin selección, 1=libre, 2=filas, 3=todo
        self.sel_anchor = None         # (row, track) extremo fijo de la selección
        self.play_pos = [None] * NUM_TRACKS   # fila en el playhead por canal
        self.muted = set()                    # canales muteados (0-7)
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_play(self, positions):
        if positions != self.play_pos:
            self.play_pos = positions
            self._redraw()

    def set_muted(self, muted):
        muted = set(muted)
        if muted != self.muted:
            self.muted = muted
            self._redraw()

    # -- datos ----------------------------------------------------------
    def set_project(self, project):
        self.view = SongView(project)
        self.cursor_row = self.cursor_track = self.top_row = 0
        self.sel_stage = 0
        self.sel_anchor = None
        self.clipboard = None
        self.play_pos = [None] * NUM_TRACKS
        self.muted = set()
        self._redraw()

    @property
    def has_selection(self):
        return self.sel_stage > 0

    # -- navegación -----------------------------------------------------
    def move(self, button):
        dr, dt = _MOVE[button]
        self.cursor_row = max(0, min(self.view.length - 1, self.cursor_row + dr))
        self.cursor_track = max(0, min(NUM_TRACKS - 1, self.cursor_track + dt))
        self._ensure_visible()
        self._redraw()

    # -- edición valor (A+dir) -----------------------------------------
    def edit(self, button):
        delta = _EDIT[button]
        r, t = self.cursor_row, self.cursor_track
        cur = self.view.chain_at(r, t)
        if cur == EMPTY:
            if delta > 0:
                self.view.new_chain(r, t)
            else:
                return
        else:
            self.view.set_value(r, t, max(0, min(0xFE, cur + delta)))
        self._changed()

    def delete(self):
        self.view.set_value(self.cursor_row, self.cursor_track, None)
        self._changed()

    # -- A (tap): copiar celda / pegar / 00 ----------------------------
    def a_tap(self):
        r, t = self.cursor_row, self.cursor_track
        if self.view.chain_at(r, t) != EMPTY:
            self.clipboard = [[read_cell(self.view, r, t)]]   # copiar celda
            self._redraw()
        elif self.clipboard is not None:
            paste_region(self.view, r, t, self.clipboard)     # pegar
            self._changed()
        else:
            self.view.set_value(r, t, 0x00)                   # poner 00
            self._changed()

    # -- portapapeles de bloque ----------------------------------------
    def paste_block(self):
        if self.clipboard is not None:
            paste_region(self.view, self.cursor_row, self.cursor_track,
                         self.clipboard)
            self._changed()

    def copy_selection(self):
        region = self._region()
        if region:
            self.clipboard = clip_region(self.view, *region)
        self.cancel_selection()

    def cut_selection(self):
        region = self._region()
        if region:
            self.clipboard = clip_region(self.view, *region, cut=True)
            self._changed()
        self.cancel_selection()

    def duplicate_chain(self):
        """Ctrl+A con selección: duplica la chain de la celda del cursor a la
        primera chain libre con índice mayor, y apunta la celda a la copia."""
        r, t = self.cursor_row, self.cursor_track
        src = self.view.chain_at(r, t)
        if src == EMPTY:
            return False
        dst = duplicate_chain(self.view.project, src)
        if dst is None:
            return False
        self.view.set_value(r, t, dst)
        self.cancel_selection()
        self._changed()
        return True

    # -- selección (Ctrl+S cicla, Esc cancela) -------------------------

    def cycle_selection(self):
        if self.sel_stage == 0:
            self.sel_anchor = (self.cursor_row, self.cursor_track)
            self.sel_stage = 1
        elif self.sel_stage == 1:
            self.sel_stage = 2
        elif self.sel_stage == 2:
            self.sel_stage = 3
        else:
            self.sel_stage = 1
        self._redraw()

    def cancel_selection(self):
        had = self.sel_stage > 0
        self.sel_stage = 0
        self.sel_anchor = None
        self._redraw()
        return had

    def _region(self):
        """(r0, t0, r1, t1) de la selección según la etapa, o None."""
        if self.sel_stage == 0 or self.sel_anchor is None:
            return None
        ar, at = self.sel_anchor
        r0, r1 = sorted((ar, self.cursor_row))
        if self.sel_stage == 1:
            t0, t1 = sorted((at, self.cursor_track))
            return (r0, t0, r1, t1)
        if self.sel_stage == 2:                       # filas completas
            return (r0, 0, r1, NUM_TRACKS - 1)
        n = self._visible_rows()                       # todo lo visible
        return (self.top_row, 0,
                min(self.view.length - 1, self.top_row + n - 1),
                NUM_TRACKS - 1)

    # -- helpers --------------------------------------------------------
    def _changed(self):
        if self.on_change:
            self.on_change()
        self._redraw()

    def _visible_rows(self):
        return max(1, int((self.height - HEADER_H) // ROW_H))

    def _ensure_visible(self):
        n = self._visible_rows()
        if self.cursor_row < self.top_row:
            self.top_row = self.cursor_row
        elif self.cursor_row >= self.top_row + n:
            self.top_row = self.cursor_row - n + 1
        self.top_row = max(0, min(self.top_row, max(0, self.view.length - n)))

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _text(self, x, y, w, text, color, h=ROW_H):
        tex = self._texture(text)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (h - th) / 2))

    def _icon_voice(self, cx, cy, s, color=COLOR_ICON):
        """Micrófono (canal de voz)."""
        Color(*color)
        bw, bh = s * 0.40, s * 0.56
        RoundedRectangle(pos=(cx - bw / 2, cy - bh * 0.10),
                         size=(bw, bh), radius=[bw / 2])
        Line(circle=(cx, cy - bh * 0.02, s * 0.34, 120, 240), width=1.4)
        Line(points=[cx, cy - bh * 0.46, cx, cy - bh * 0.10], width=1.4)
        Line(points=[cx - s * 0.20, cy - bh * 0.46,
                     cx + s * 0.20, cy - bh * 0.46], width=1.4)

    def _icon_robot(self, cx, cy, s, color=COLOR_ICON):
        """Cabeza de robot (canal de robot)."""
        hw, hh = s * 0.64, s * 0.52
        Color(*color)
        Line(points=[cx, cy + hh * 0.5, cx, cy + hh * 0.5 + s * 0.16],
             width=1.4)
        Ellipse(pos=(cx - s * 0.06, cy + hh * 0.5 + s * 0.10),
                size=(s * 0.12, s * 0.12))
        RoundedRectangle(pos=(cx - hw / 2, cy - hh / 2), size=(hw, hh),
                         radius=[s * 0.14])
        # ojos recortados en color de fondo
        Color(*COLOR_HEADER_BG)
        er = s * 0.12
        Ellipse(pos=(cx - hw * 0.26 - er / 2, cy - er / 2), size=(er, er))
        Ellipse(pos=(cx + hw * 0.26 - er / 2, cy - er / 2), size=(er, er))

    def _redraw(self, *_):
        self.canvas.clear()
        if self.view is None:
            return
        n = self._visible_rows()
        track_w = (self.width - GUTTER_W) / NUM_TRACKS
        region = self._region()
        content_top = self.y + self.height - HEADER_H
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            for i in range(n):
                row = self.top_row + i
                if row >= self.view.length:
                    break
                y = content_top - (i + 1) * ROW_H
                if row == self.cursor_row:
                    band = COLOR_ROW_CURSOR
                elif row % 16 == 0:
                    band = COLOR_BAR
                elif row % 4 == 0:
                    band = COLOR_BEAT
                else:
                    band = None
                if band:
                    Color(*band)
                    Rectangle(pos=(self.x, y), size=(self.width, ROW_H))
                num_color = (COLOR_LINENUM_CUR if row == self.cursor_row
                             else COLOR_LINENUM)
                self._text(self.x, y, GUTTER_W, f"{row:02X}", num_color)
                for t in range(NUM_TRACKS):
                    x = self.x + GUTTER_W + t * track_w
                    v = self.view.chain_at(row, t)
                    text = "--" if v == EMPTY else f"{v:02X}"
                    is_cursor = (row == self.cursor_row
                                 and t == self.cursor_track)
                    in_sel = (region and region[0] <= row <= region[2]
                              and region[1] <= t <= region[3])
                    if is_cursor:
                        Color(*COLOR_ACCENT)
                        RoundedRectangle(pos=(x + dp(3), y + dp(3)),
                                         size=(track_w - dp(6), ROW_H - dp(6)),
                                         radius=[dp(6)])
                        color = COLOR_BG
                    else:
                        if in_sel:
                            Color(*COLOR_SEL)
                            Rectangle(pos=(x + dp(1), y + dp(1)),
                                      size=(track_w - dp(2), ROW_H - dp(2)))
                        if self.play_pos[t] == row:
                            Color(*COLOR_PLAY)
                            Rectangle(pos=(x + dp(1), y + dp(1)),
                                      size=(track_w - dp(2), ROW_H - dp(2)))
                        color = COLOR_CELL if v != EMPTY else COLOR_EMPTY
                    self._text(x, y, track_w, text, color)
            # columnas muteadas: atenúa el cuerpo (debajo de la cabecera)
            for t in self.muted:
                x = self.x + GUTTER_W + t * track_w
                Color(*COLOR_MUTE_OVERLAY)
                Rectangle(pos=(x, self.y),
                          size=(track_w, self.height - HEADER_H))
            # cabecera de canales (1..6, voz, robot); muteadas en rojo
            hy = self.y + self.height - HEADER_H
            Color(*COLOR_HEADER_BG)
            Rectangle(pos=(self.x, hy), size=(self.width, HEADER_H))
            for t in range(NUM_TRACKS):
                x = self.x + GUTTER_W + t * track_w
                cx, cy = x + track_w / 2, hy + HEADER_H / 2
                s = min(track_w, HEADER_H) * 0.66
                muted = t in self.muted
                if t == VOICE_TRACK:
                    self._icon_voice(cx, cy, s,
                                     COLOR_MUTED if muted else COLOR_ICON)
                elif t == ROBOT_TRACK:
                    self._icon_robot(cx, cy, s,
                                     COLOR_MUTED if muted else COLOR_ICON)
                else:
                    self._text(x, hy, track_w, str(t + 1),
                               COLOR_MUTED if muted else COLOR_HEADER_TXT,
                               h=HEADER_H)
