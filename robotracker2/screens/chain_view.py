"""Pantalla CHAIN: los 16 steps de la chain donde está el cursor de SONG.

Como LGPT: dos columnas por step — PHRASE (índice de phrase) y TRANSPOSE. La
chain mostrada es la de la celda de SONG (song_row, track) desde la que se
entró. Dpad mueve (arr/abj = step, izq/dcha = columna), A+dir edita el valor,
A copia/pega/00, B borra. Crear una phrase en un hueco crea la chain si hace
falta (estilo Piggy), reutilizando `ChainView` del modelo.
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from lgpt_model import CHAIN_LEN, EMPTY, NUM_TRACKS, ChainView, SongView
from theme import COLOR_ACCENT, COLOR_BG

ROW_H = dp(30)
TOP_PAD = dp(20)
LM = dp(48)
STEP_W = dp(64)
COL_W = dp(96)
FONT = dp(17)

COLOR_CELL = (0.87, 0.89, 0.92, 1)
COLOR_TRSP = (0.72, 0.74, 0.80, 1)
COLOR_EMPTY = (0.30, 0.31, 0.36, 1)
COLOR_LINENUM = (0.45, 0.46, 0.52, 1)
COLOR_LINENUM_CUR = (1.0, 0.85, 0.40, 1)
COLOR_BEAT = (0.13, 0.14, 0.18, 1)
COLOR_ROW_CURSOR = (0.19, 0.21, 0.27, 1)
COLOR_PLAY = (0.16, 0.42, 0.24, 1)
COLOR_SEL = (0.95, 0.75, 0.20, 0.30)

_EDIT = {RIGHT: 1, LEFT: -1, UP: 0x10, DOWN: -0x10}


class ChainGrid(Widget):
    def __init__(self, on_change=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.cv = None
        self.song_row = 0
        self.track = 0
        self.cursor_step = 0
        self.cursor_col = 0            # 0 = phrase, 1 = transpose
        self.clipboard = None          # bloque list[list] (portapapeles propio)
        self.sel_stage = 0             # 0=sin sel, 1=libre, 2=columnas, 3=todo
        self.sel_anchor = None         # (step, col) extremo fijo
        self.play_step = None          # step en el playhead (o None)
        self.on_change = on_change
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_play(self, step):
        if step != self.play_step:
            self.play_step = step
            self._redraw()

    # -- contexto -------------------------------------------------------
    def set_context(self, project, song_row, track):
        self.project = project
        self.cv = ChainView(project, song_row)
        self.song_row = song_row
        self.track = track
        self.cursor_step = 0
        self.cursor_col = 0
        self.clipboard = None
        self.sel_stage = 0
        self.sel_anchor = None
        self._redraw()

    def chain_index(self):
        c = self.project.song[self.song_row * NUM_TRACKS + self.track]
        return None if c == EMPTY else c

    def chain_label(self):
        c = self.chain_index()
        return f"{c:02X}" if c is not None else "--"

    # -- acceso a valores ----------------------------------------------
    def _get(self, step, col):
        if col == 0:
            return self.cv.phrase_at(step, self.track)     # None o int
        c = self.chain_index()
        return None if c is None else self.project.transposes[c * CHAIN_LEN + step]

    def _set(self, step, col, value):
        if col == 0:
            self.cv.set_value(step, self.track, value)     # None limpia
            return
        c = self.chain_index()
        if c is None:
            if value is None:
                return
            c = SongView(self.project).new_chain(self.song_row, self.track)
        self.project.transposes[c * CHAIN_LEN + step] = (
            0 if value is None else value & 0xFF)

    # -- navegación / edición ------------------------------------------
    def move(self, button):
        if button == UP:
            self.cursor_step = max(0, self.cursor_step - 1)
        elif button == DOWN:
            self.cursor_step = min(CHAIN_LEN - 1, self.cursor_step + 1)
        elif button == LEFT:
            self.cursor_col = max(0, self.cursor_col - 1)
        elif button == RIGHT:
            self.cursor_col = min(1, self.cursor_col + 1)
        self._redraw()

    def edit(self, button):
        delta = _EDIT[button]
        step, col = self.cursor_step, self.cursor_col
        cur = self._get(step, col)
        if col == 0:
            if cur is None:
                if delta > 0:
                    self.cv.new_phrase(step, self.track)   # crea chain+phrase
                else:
                    return
            else:
                self._set(step, col, max(0, min(0xFE, cur + delta)))
        else:
            base = cur if cur is not None else 0
            self._set(step, col, (base + delta) & 0xFF)
        self._changed()

    @property
    def has_selection(self):
        return self.sel_stage > 0

    def a_tap(self):
        step, col = self.cursor_step, self.cursor_col
        cur = self._get(step, col)
        # celda con valor -> copiar; vacía -> pegar o poner 00
        if col == 0 and cur is not None:
            self.clipboard = [[cur]]
            self._redraw()
        elif col == 1 and self.chain_index() is not None:
            self.clipboard = [[cur]]
            self._redraw()
        elif self.clipboard is not None:
            self._paste_at(step, col)
            self._changed()
        else:
            self._set(step, col, 0)
            self._changed()

    def paste_block(self):
        if self.clipboard is not None:
            self._paste_at(self.cursor_step, self.cursor_col)
            self._changed()

    def _paste_at(self, step, col):
        for dr, row in enumerate(self.clipboard):
            for dc, val in enumerate(row):
                s, c = step + dr, col + dc
                if s < CHAIN_LEN and c < 2:
                    self._set(s, c, val)

    def delete(self):
        self._set(self.cursor_step, self.cursor_col, None)
        self._changed()

    # -- selección (Ctrl+S cicla, S copia, Ctrl+A corta, Esc cancela) --
    def copy_selection(self):
        region = self._region()
        if region:
            self.clipboard = self._read_block(region)
        self.cancel_selection()

    def cut_selection(self):
        region = self._region()
        if region:
            self.clipboard = self._read_block(region)
            s0, c0, s1, c1 = region
            for s in range(s0, s1 + 1):
                for c in range(c0, c1 + 1):
                    self._set(s, c, None)
            self._changed()
        self.cancel_selection()

    def _read_block(self, region):
        s0, c0, s1, c1 = region
        return [[self._get(s, c) for c in range(c0, c1 + 1)]
                for s in range(s0, s1 + 1)]

    def cycle_selection(self):
        if self.sel_stage == 0:
            self.sel_anchor = (self.cursor_step, self.cursor_col)
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
        """(s0, c0, s1, c1) según la etapa, o None."""
        if self.sel_stage == 0 or self.sel_anchor is None:
            return None
        as_, ac = self.sel_anchor
        s0, s1 = sorted((as_, self.cursor_step))
        if self.sel_stage == 1:
            c0, c1 = sorted((ac, self.cursor_col))
            return (s0, c0, s1, c1)
        if self.sel_stage == 2:                 # columnas completas
            return (s0, 0, s1, 1)
        return (0, 0, CHAIN_LEN - 1, 1)         # todo

    def _changed(self):
        if self.on_change:
            self.on_change()
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _text(self, x, y, w, text, color):
        tex = self._texture(text)
        tw, th = tex.size
        Color(*color)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(x + (w - tw) / 2, y + (ROW_H - th) / 2))

    def _redraw(self, *_):
        self.canvas.clear()
        if self.cv is None:
            return
        block_w = STEP_W + dp(16) + 2 * COL_W        # centrar el bloque
        x_step = self.x + max(dp(8), (self.width - block_w) / 2)
        x_ph = x_step + STEP_W + dp(16)
        x_tr = x_ph + COL_W
        chain = self.chain_index()
        region = self._region()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            for step in range(CHAIN_LEN):
                y = self.y + self.height - TOP_PAD - (step + 1) * ROW_H
                if step == self.cursor_step:
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(self.x, y), size=(self.width, ROW_H))
                elif step == self.play_step:
                    Color(*COLOR_PLAY)
                    Rectangle(pos=(x_step, y), size=(x_tr + COL_W - x_step, ROW_H))
                elif step % 4 == 0:
                    Color(*COLOR_BEAT)
                    Rectangle(pos=(x_step, y), size=(x_tr + COL_W - x_step, ROW_H))
                num_c = (COLOR_LINENUM_CUR if step == self.cursor_step
                         else COLOR_LINENUM)
                self._text(x_step, y, STEP_W, f"{step:02X}", num_c)
                # phrase / transpose
                for col, (cx, cw) in enumerate(((x_ph, COL_W), (x_tr, COL_W))):
                    v = self._get(step, col)
                    if col == 0:
                        text = "--" if v is None else f"{v:02X}"
                        base_c = COLOR_CELL if v is not None else COLOR_EMPTY
                    else:
                        text = "--" if chain is None else f"{v:02X}"
                        base_c = COLOR_TRSP if chain is not None else COLOR_EMPTY
                    in_sel = (region and region[0] <= step <= region[2]
                              and region[1] <= col <= region[3])
                    if step == self.cursor_step and col == self.cursor_col:
                        Color(*COLOR_ACCENT)
                        RoundedRectangle(pos=(cx + dp(3), y + dp(3)),
                                         size=(cw - dp(6), ROW_H - dp(6)),
                                         radius=[dp(6)])
                        base_c = COLOR_BG
                    elif in_sel:
                        Color(*COLOR_SEL)
                        Rectangle(pos=(cx + dp(1), y + dp(1)),
                                  size=(cw - dp(2), ROW_H - dp(2)))
                    self._text(cx, y, cw, text, base_c)
