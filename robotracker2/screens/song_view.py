"""Pantalla SONG: la parrilla 256 filas × 8 canales de índices de chain.

Clon de la pantalla Song de LGPT. Trabaja con
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

from theme import (COLOR_BAR, COLOR_BEAT, COLOR_BG, COLOR_CELL, COLOR_EMPTY,
                   COLOR_HEADER_BG, COLOR_HEADER_TXT, COLOR_HINT_BG,
                   COLOR_LINENUM, COLOR_LINENUM_CUR, COLOR_MUTE_OVERLAY,
                   COLOR_MUTED, COLOR_PLAY, COLOR_SONG_ACCENT,
                   COLOR_SONG_CELL_FG, COLOR_SONG_HEADER_SEL, COLOR_SONG_ROW,
                   COLOR_SONG_SEL, COLOR_SONG_TRACK)

ROW_H = dp(30)
HEADER_H = dp(34)                       # cabecera con el nº de canal
GUTTER_W = dp(54)
FONT = dp(17)
FONT_SMALL = dp(15)
HINT_H = dp(32)                         # franja inferior del hint de selección

# Canales especiales (0-index): 6 = voz (canal 7), 7 = robot (canal 8)
VOICE_TRACK = 6
ROBOT_TRACK = 7

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

    def _selection_hint(self):
        """Operaciones disponibles con la selección activa (None sin ella)."""
        if self.sel_stage == 0:
            return None
        return ("SELECCIÓN: B copiar · R2+A duplicar chain · "
                "R2+B ciclar · BACK cancelar")

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
    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=font_size, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[key] = tex
        return tex

    def _text(self, x, y, w, text, color, h=ROW_H):
        tex = self._texture(text)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (h - th) / 2))

    def _text_left(self, x, y, w, text, color, h=ROW_H, font_size=FONT):
        tex = self._texture(text, font_size)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th), pos=(x, y + (h - th) / 2))

    def _icon_voice(self, cx, cy, s, color=COLOR_SONG_ACCENT):
        """Micrófono (canal de voz)."""
        Color(*color)
        bw, bh = s * 0.40, s * 0.56
        RoundedRectangle(pos=(cx - bw / 2, cy - bh * 0.10),
                         size=(bw, bh), radius=[bw / 2])
        Line(circle=(cx, cy - bh * 0.02, s * 0.34, 120, 240), width=1.4)
        Line(points=[cx, cy - bh * 0.46, cx, cy - bh * 0.10], width=1.4)
        Line(points=[cx - s * 0.20, cy - bh * 0.46,
                     cx + s * 0.20, cy - bh * 0.46], width=1.4)

    def _icon_robot(self, cx, cy, s, color=COLOR_SONG_ACCENT):
        """Cabeza de robot (canal de robot)."""
        hw, hh = s * 0.64, s * 0.52
        Color(*color)
        Line(points=[cx, cy + hh * 0.5, cx, cy + hh * 0.5 + s * 0.16],
             width=1.4)
        Ellipse(pos=(cx - s * 0.06, cy + hh * 0.5 + s * 0.10),
                size=(s * 0.12, s * 0.12))
        RoundedRectangle(pos=(cx - hw / 2, cy - hh / 2), size=(hw, hh),
                         radius=[s * 0.14])
        # ojos recortados en el fondo de cabecera
        Color(*COLOR_BG)
        er = s * 0.12
        Ellipse(pos=(cx - hw * 0.26 - er / 2, cy - er / 2), size=(er, er))
        Ellipse(pos=(cx + hw * 0.26 - er / 2, cy - er / 2), size=(er, er))

    def _frame_column(self, x, y, w, h):
        """Marco naranja y escuadras en L del canal del cursor."""
        Color(*COLOR_SONG_ACCENT)
        Line(rectangle=(x + 0.5, y + 0.5, w - 1, h - 1), width=1)
        bar_h = dp(3)
        Rectangle(pos=(x, y + h - bar_h), size=(w, bar_h))
        arm = min(dp(12), w * 0.38, h * 0.10)
        x0, y0, x1, y1 = x, y, x + w, y + h
        for pts in (
            [x0, y1 - arm, x0, y1, x0 + arm, y1],
            [x1 - arm, y1, x1, y1, x1, y1 - arm],
            [x0, y0 + arm, x0, y0, x0 + arm, y0],
            [x1 - arm, y0, x1, y0, x1, y0 + arm],
        ):
            Line(points=pts, width=1.6, cap="square", joint="miter")

    def _track_ink(self, track, muted, selected):
        if muted:
            return COLOR_MUTED
        if selected:
            return COLOR_SONG_ACCENT
        return COLOR_SONG_TRACK[track]

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
                    band = COLOR_SONG_ROW
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
                        Color(*COLOR_SONG_ACCENT)
                        Rectangle(pos=(x + dp(2), y + dp(2)),
                                  size=(track_w - dp(4), ROW_H - dp(4)))
                        color = COLOR_SONG_CELL_FG
                    else:
                        if in_sel:
                            Color(*COLOR_SONG_SEL)
                            Rectangle(pos=(x + dp(1), y + dp(1)),
                                      size=(track_w - dp(2), ROW_H - dp(2)))
                        if self.play_pos[t] == row:
                            Color(*COLOR_PLAY)
                            Rectangle(pos=(x + dp(1), y + dp(1)),
                                      size=(track_w - dp(2), ROW_H - dp(2)))
                        color = COLOR_CELL if v != EMPTY else COLOR_EMPTY
                    self._text(x, y, track_w, text, color)
            hint = self._selection_hint()
            hint_h = HINT_H if hint else 0
            # columnas muteadas: atenúa el cuerpo (debajo de la cabecera)
            for t in self.muted:
                x = self.x + GUTTER_W + t * track_w
                Color(*COLOR_MUTE_OVERLAY)
                Rectangle(pos=(x, self.y + hint_h),
                          size=(track_w, self.height - HEADER_H - hint_h))
            # cabecera de canales (1..6, voz, robot); muteadas en rojo
            hy = self.y + self.height - HEADER_H
            Color(*COLOR_HEADER_BG)
            Rectangle(pos=(self.x, hy), size=(self.width, HEADER_H))
            strip_h = dp(3)
            for t in range(NUM_TRACKS):
                x = self.x + GUTTER_W + t * track_w
                selected = t == self.cursor_track
                muted = t in self.muted
                if selected:
                    Color(*COLOR_SONG_HEADER_SEL)
                    Rectangle(pos=(x, hy), size=(track_w, HEADER_H))
                Color(*COLOR_SONG_TRACK[t])
                Rectangle(pos=(x, hy + HEADER_H - strip_h),
                          size=(track_w, strip_h))
                cx, cy = x + track_w / 2, hy + HEADER_H / 2
                s = min(track_w, HEADER_H) * 0.66
                ink = self._track_ink(t, muted, selected)
                if t == VOICE_TRACK:
                    self._icon_voice(cx, cy, s, ink)
                elif t == ROBOT_TRACK:
                    self._icon_robot(cx, cy, s, ink)
                else:
                    self._text(x, hy, track_w, str(t + 1),
                               ink if selected else (
                                   COLOR_MUTED if muted else COLOR_HEADER_TXT),
                               h=HEADER_H)
            col_x = self.x + GUTTER_W + self.cursor_track * track_w
            self._frame_column(col_x, self.y + hint_h, track_w,
                               self.height - hint_h)
            if hint:
                Color(*COLOR_HINT_BG)
                Rectangle(pos=(self.x, self.y), size=(self.width, HINT_H))
                Color(*COLOR_SONG_ACCENT)
                Line(points=[self.x, self.y + HINT_H,
                             self.x + self.width, self.y + HINT_H], width=1)
                self._text_left(self.x + dp(12), self.y, self.width - dp(24),
                                hint, COLOR_SONG_ACCENT, h=HINT_H,
                                font_size=FONT_SMALL)
