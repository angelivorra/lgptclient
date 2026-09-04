"""Pantalla GROOVE: el groove seleccionado (16 steps de duración en ticks).

Hay 32 grooves (0x00–0x1F) de 16 steps; cada step es un nº de ticks (0xFF = fin
/ sin usar, se muestra "--"). Dpad: arr/abj = step, izq/dcha = cambiar de groove.
A+dir edita el valor, A copia/pega/def (6 ticks), B lo deja en "--". El groove es
global; editar afecta a la reproducción y se guarda (writer de sinte extendido).
Portapapeles propio.
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from theme import (COLOR_ACCENT, COLOR_BEAT, COLOR_BG, COLOR_CELL, COLOR_EMPTY,
                   COLOR_LINENUM, COLOR_LINENUM_CUR, COLOR_ROW_CURSOR,
                   core_label)

GROOVE_COUNT = 32
GROOVE_LEN = 16
END = 0xFF
DEFAULT_TICKS = 6

ROW_H = dp(30)
TOP_PAD = dp(20)
STEP_W = dp(64)
COL_W = dp(96)
FONT = dp(17)

_EDIT = {RIGHT: 1, LEFT: -1, UP: 0x10, DOWN: -0x10}


class GrooveGrid(Widget):
    def __init__(self, on_change=None, on_nav=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.groove = 0
        self.cursor_step = 0
        self.clipboard = None
        self.on_change = on_change
        self.on_nav = on_nav           # refrescar cabecera al cambiar groove
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_project(self, project):
        self.project = project
        # asegura 32×16 bytes (algunos proyectos traen menos)
        need = GROOVE_COUNT * GROOVE_LEN
        if len(project.grooves) < need:
            project.grooves.extend(bytes([END]) * (need - len(project.grooves)))
        self.groove = 0
        self.cursor_step = 0
        self.clipboard = None
        self._redraw()

    def groove_label(self):
        return f"{self.groove:02X}"

    # -- valores --------------------------------------------------------
    def _get(self, step):
        v = self.project.grooves[self.groove * GROOVE_LEN + step]
        return None if v == END else v

    def _set(self, step, value):
        i = self.groove * GROOVE_LEN + step
        self.project.grooves[i] = END if value is None else value & 0xFF

    # -- navegación / edición ------------------------------------------
    def move(self, button):
        if button == UP:
            self.cursor_step = max(0, self.cursor_step - 1)
        elif button == DOWN:
            self.cursor_step = min(GROOVE_LEN - 1, self.cursor_step + 1)
        elif button in (LEFT, RIGHT):
            self.groove = (self.groove + (1 if button == RIGHT else -1)) \
                % GROOVE_COUNT
            if self.on_nav:
                self.on_nav()
        self._redraw()

    def edit(self, button):
        delta = _EDIT[button]
        cur = self._get(self.cursor_step)
        if cur is None:
            if delta > 0:
                self._set(self.cursor_step, DEFAULT_TICKS)
            else:
                return
        else:
            self._set(self.cursor_step, max(1, min(0xFE, cur + delta)))
        self._changed()

    def a_tap(self):
        cur = self._get(self.cursor_step)
        if cur is not None:
            self.clipboard = cur
            self._redraw()
        elif self.clipboard is not None:
            self._set(self.cursor_step, self.clipboard)
            self._changed()
        else:
            self._set(self.cursor_step, DEFAULT_TICKS)
            self._changed()

    def paste(self):
        if self.clipboard is not None:
            self._set(self.cursor_step, self.clipboard)
            self._changed()

    def delete(self):
        self._set(self.cursor_step, None)
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()
        self._redraw()

    # -- dibujo ---------------------------------------------------------
    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            tex = core_label(text, FONT).texture
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
        block_w = STEP_W + dp(16) + COL_W          # centrar
        x_step = self.x + max(dp(8), (self.width - block_w) / 2)
        x_val = x_step + STEP_W + dp(16)
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            for step in range(GROOVE_LEN):
                y = self.y + self.height - TOP_PAD - (step + 1) * ROW_H
                if step == self.cursor_step:
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(self.x, y), size=(self.width, ROW_H))
                elif step % 4 == 0:
                    Color(*COLOR_BEAT)
                    Rectangle(pos=(x_step, y),
                              size=(x_val + COL_W - x_step, ROW_H))
                num_c = (COLOR_LINENUM_CUR if step == self.cursor_step
                         else COLOR_LINENUM)
                self._text(x_step, y, STEP_W, f"{step:02X}", num_c)
                v = self._get(step)
                text = "--" if v is None else f"{v:02X}"
                color = COLOR_CELL if v is not None else COLOR_EMPTY
                if step == self.cursor_step:
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(x_val + dp(3), y + dp(3)),
                                     size=(COL_W - dp(6), ROW_H - dp(6)),
                                     radius=[dp(6)])
                    color = COLOR_BG
                self._text(x_val, y, COL_W, text, color)
