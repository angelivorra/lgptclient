"""Pantalla TABLE: una tabla (16 filas × 3 columnas FX: cmd+param).

Es la tabla ligada al contexto (nº en la cabecera): desde PHRASE, la del comando
TABL del step del cursor si lo hay; si no, la primera existente. Dpad: arr/abj
fila, izq/dcha campo (cmd1,prm1,cmd2,prm2,cmd3,prm3). A+dir edita (cmd cicla la
lista de FX de tablas; param ±1/±0x10), A copia/pega/def por campo, B borra.
Editar crea la tabla si no existe. Se guarda (writer de sinte extendido).
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from lgpt_model import FX_EMPTY
from theme import (COLOR_ACCENT, COLOR_BEAT, COLOR_BG, COLOR_EMPTY, COLOR_FX1,
                   COLOR_FX2, COLOR_FX3, COLOR_LINENUM, COLOR_LINENUM_CUR,
                   COLOR_ROW_CURSOR)

TABLE_LEN = 16
ROW_H = dp(30)
TOP_PAD = dp(20)
STEP_W = dp(52)
FONT = dp(17)

# FX que se pueden ciclar en tablas: solo los usados en las canciones de songs/
# (4 chars cada uno; "HOP ", "PAN " llevan espacio).
TABLE_FX = ["VOLM", "PTCH", "RTRG", "HOP ", "KILL", "ARPG", "CRSH", "FCUT",
            "FLTR", "FRES", "LPOF", "PAN ", "PFIN", "PLOF"]

# (kind, ancho) — 3 columnas cmd+param
COLS = [("cmd1", dp(74)), ("prm1", dp(74)),
        ("cmd2", dp(74)), ("prm2", dp(74)),
        ("cmd3", dp(74)), ("prm3", dp(74))]

_COL_COLOR = {"cmd1": COLOR_FX1, "prm1": COLOR_FX1, "cmd2": COLOR_FX2,
              "prm2": COLOR_FX2, "cmd3": COLOR_FX3, "prm3": COLOR_FX3}
_KIND = {"cmd1": "cmd", "cmd2": "cmd", "cmd3": "cmd",
         "prm1": "prm", "prm2": "prm", "prm3": "prm"}
_CMDKEY = {"cmd1": "cmd1", "prm1": "cmd1", "cmd2": "cmd2", "prm2": "cmd2",
           "cmd3": "cmd3", "prm3": "cmd3"}
_PRMKEY = {"cmd1": "param1", "prm1": "param1", "cmd2": "param2",
           "prm2": "param2", "cmd3": "param3", "prm3": "param3"}


class TableGrid(Widget):
    def __init__(self, on_change=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.table_id = 0
        self.cursor_row = 0
        self.cursor_col = 0
        self.clipboard = None          # (kind, value) — portapapeles propio
        self.on_change = on_change
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_context(self, project, table_id):
        self.project = project
        self.table_id = table_id
        self.cursor_row = 0
        self.cursor_col = 0
        self.clipboard = None
        self._redraw()

    def table_label(self):
        return f"{self.table_id:02X}"

    # -- acceso ---------------------------------------------------------
    def _table(self, create=False):
        t = self.project.tables.get(self.table_id)
        if t is None and create:
            t = {"cmd1": [FX_EMPTY] * TABLE_LEN, "param1": [0] * TABLE_LEN,
                 "cmd2": [FX_EMPTY] * TABLE_LEN, "param2": [0] * TABLE_LEN,
                 "cmd3": [FX_EMPTY] * TABLE_LEN, "param3": [0] * TABLE_LEN}
            self.project.tables[self.table_id] = t
        return t

    def _cmd(self, row, col):
        t = self._table()
        if t is None:
            return None
        c = t[_CMDKEY[COLS[col][0]]][row]
        return None if c == FX_EMPTY else c

    def _prm(self, row, col):
        if self._cmd(row, col) is None:
            return None
        return self._table()[_PRMKEY[COLS[col][0]]][row]

    def _get_raw(self, row, col):
        return self._cmd(row, col) if _KIND[COLS[col][0]] == "cmd" \
            else self._prm(row, col)

    def _set_raw(self, row, col, value):
        kind = COLS[col][0]
        t = self._table(create=True)
        if _KIND[kind] == "cmd":
            t[_CMDKEY[kind]][row] = FX_EMPTY if value is None else value
            if value is None:
                t[_PRMKEY[kind]][row] = 0
        else:
            t[_PRMKEY[kind]][row] = 0 if value is None else value & 0xFFFF

    # -- navegación / edición ------------------------------------------
    def move(self, button):
        if button == UP:
            self.cursor_row = max(0, self.cursor_row - 1)
        elif button == DOWN:
            self.cursor_row = min(TABLE_LEN - 1, self.cursor_row + 1)
        elif button == LEFT:
            self.cursor_col = max(0, self.cursor_col - 1)
        elif button == RIGHT:
            self.cursor_col = min(len(COLS) - 1, self.cursor_col + 1)
        self._redraw()

    def edit(self, button):
        row, col = self.cursor_row, self.cursor_col
        kind = COLS[col][0]
        if _KIND[kind] == "cmd":
            self._edit_cmd(row, col, 1 if button in (RIGHT, UP) else -1)
        else:
            delta = (1 if button == RIGHT else -1) if button in (LEFT, RIGHT) \
                else (0x10 if button == UP else -0x10)
            cur = self._prm(row, col) or 0
            self._set_raw(row, col, max(0, min(0xFFFF, cur + delta)))
        self._changed()

    def _edit_cmd(self, row, col, d):
        cur = self._cmd(row, col)
        if cur is None or cur not in TABLE_FX:
            if d > 0:
                self._set_raw(row, col, TABLE_FX[0])
        else:
            self._set_raw(row, col, TABLE_FX[(TABLE_FX.index(cur) + d)
                                             % len(TABLE_FX)])

    def a_tap(self):
        row, col = self.cursor_row, self.cursor_col
        val = self._get_raw(row, col)
        kind = _KIND[COLS[col][0]]
        if val is not None:
            self.clipboard = (kind, val)
            self._redraw()
        elif self.clipboard is not None and self.clipboard[0] == kind:
            self._set_raw(row, col, self.clipboard[1])
            self._changed()
        else:
            self._set_raw(row, col, TABLE_FX[0] if kind == "cmd" else 0)
            self._changed()

    def paste_field(self):
        col = self.cursor_col
        if self.clipboard is not None and self.clipboard[0] == _KIND[COLS[col][0]]:
            self._set_raw(self.cursor_row, col, self.clipboard[1])
            self._changed()

    def delete(self):
        self._set_raw(self.cursor_row, self.cursor_col, None)
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _field_text(self, row, col):
        kind = COLS[col][0]
        raw = self._get_raw(row, col)
        if _KIND[kind] == "cmd":
            return raw.strip().ljust(4) if raw is not None else "----"
        return f"{raw:04X}" if raw is not None else "...."

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
        if self.project is None:
            return
        block_w = STEP_W + dp(8) + sum(w for _k, w in COLS)   # centrar
        x_step = self.x + max(dp(8), (self.width - block_w) / 2)
        xs = []
        x = x_step + STEP_W + dp(8)
        for _kind, w in COLS:
            xs.append(x)
            x += w
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            for row in range(TABLE_LEN):
                y = self.y + self.height - TOP_PAD - (row + 1) * ROW_H
                if row == self.cursor_row:
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(self.x, y), size=(self.width, ROW_H))
                elif row % 4 == 0:
                    Color(*COLOR_BEAT)
                    Rectangle(pos=(x_step, y), size=(x - x_step, ROW_H))
                num_c = (COLOR_LINENUM_CUR if row == self.cursor_row
                         else COLOR_LINENUM)
                self._text(x_step, y, STEP_W, f"{row:02X}", num_c)
                for col, (kind, w) in enumerate(COLS):
                    cx = xs[col]
                    raw = self._get_raw(row, col)
                    text = self._field_text(row, col)
                    color = _COL_COLOR[kind] if raw is not None else COLOR_EMPTY
                    if row == self.cursor_row and col == self.cursor_col:
                        Color(*COLOR_ACCENT)
                        RoundedRectangle(pos=(cx + dp(2), y + dp(3)),
                                         size=(w - dp(4), ROW_H - dp(6)),
                                         radius=[dp(6)])
                        color = COLOR_BG
                    self._text(cx, y, w, text, color)
