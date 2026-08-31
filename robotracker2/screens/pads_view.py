"""Pantalla PADS: configuración por canción de los 4 pads sampler.

Una fila por pad (PAD 1-4; entre corchetes, el botón físico del LPD8:
7/8/3/4 = sample1-4 del controlador). Muestra el WAV asignado (nombre
resuelto contra la biblioteca de pads, pads/ en la raíz del repo — no
hay banco global, solo config por canción) o "—" y el volumen efectivo
(0-100%). La configuración vive en memoria (engine + cfg de MidiControl)
hasta guardar: la fila GUARDAR de abajo (A sobre ella) o Guardar de la
canción la persisten en el robotraca.json (claves "pads" y
"pad_volume"); NO toca el flag de "canción sucia" del editor (el
robotraca.json no es el lgptsav.dat).

Solo dibuja: el estado y la persistencia viven en MidiControl
(set_state/pads_state/assign_pad/set_pad_volume/save). Debajo de las 4
filas de pad hay una fila extra, GUARDAR (cursor 4). Controles (los
resuelve la app en _dispatch_pads):

- arr/abj: cambiar de pad (y bajar a la fila GUARDAR)
- izq/dcha: volumen -/+5 (solo en las filas de pad)
- A: navegador de la biblioteca de pads (asigna el WAV elegido);
     sobre la fila GUARDAR, guarda
- B: quitar la asignación del pad
- select: no hace nada aquí (guardar es la fila GUARDAR)
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from theme import COLOR_ACCENT, COLOR_BAR_BG, COLOR_BG, COLOR_BORDER, \
    COLOR_OK

PADS = 4                            # pads sampler de la canción (engine 0-3)
SAVE_ROW = PADS                     # fila extra de abajo: GUARDAR
PAD_NOTES = ["7", "8", "3", "4"]    # botones físicos del LPD8 (sample1-4)
ROW_H = dp(76)
GUTTER = dp(170)                    # columna "PAD n [tecla]"
VOL_W = dp(110)
FONT = dp(20)
FONT_SMALL = dp(16)
NAME_MAX = 40                       # caracteres máximos del nombre en pantalla

COLOR_ROW_CURSOR = (0.19, 0.21, 0.27, 1)
COLOR_NAME = (0.87, 0.89, 0.92, 1)
COLOR_EMPTY = (0.30, 0.31, 0.36, 1)
COLOR_HINT = (0.50, 0.52, 0.60, 1)
COLOR_VOL = COLOR_OK


class PadsGrid(Widget):
    SAVE_ROW = SAVE_ROW             # fila GUARDAR (última del cursor)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pads = [(None, 0)] * PADS   # (nombre_o_None, vol_pct)
        self.cursor = 0
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_state(self, pads):
        """Inyecta [(nombre, vol_pct)] de los pads 1-4
        (MidiControl.pads_state)."""
        if pads != self.pads:
            self.pads = pads
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
            lbl = CoreLabel(text=text, font_size=font_size, bold=True)
            lbl.refresh()
            tex = lbl.texture
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
            top = self.y + self.height - dp(30)
            # título + controles
            self._text_left(x0, top - ROW_H / 2, w, "PADS",
                            COLOR_ACCENT, h=ROW_H)
            hint = ("arr/abj: pad · izq/dcha: ±5 · A: sample/guardar · "
                    "B: quitar")
            self._text_left(x0, self.y + dp(28), w, hint, COLOR_HINT,
                            h=ROW_H, font_size=FONT_SMALL)
            for i in range(PADS):
                y = top - (i + 2) * ROW_H
                if i == self.cursor:
                    # Fila seleccionada: relleno oscuro con BORDE oro (no
                    # relleno oro), para que el texto de la fila (nombre,
                    # %, que son claros/dorados) se lea sobre el fondo.
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(x0, y), size=(w, ROW_H - dp(8)))
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(x0 + dp(3), y + dp(3)),
                                     size=(w - dp(6), ROW_H - dp(14)),
                                     radius=[dp(6)])
                    Color(*COLOR_ROW_CURSOR)
                    RoundedRectangle(pos=(x0 + dp(7), y + dp(7)),
                                     size=(w - dp(14), ROW_H - dp(22)),
                                     radius=[dp(4)])
                self._text_left(x0 + dp(16), y, GUTTER,
                                f"PAD {i + 1} [{PAD_NOTES[i]}]",
                                COLOR_ACCENT if i == self.cursor
                                else COLOR_BORDER)
                name, pct = self.pads[i]
                if name and len(name) > NAME_MAX:
                    name = name[:NAME_MAX - 1] + "…"
                self._text_left(x0 + GUTTER, y, w - GUTTER - VOL_W,
                                name if name else "—",
                                COLOR_NAME if name else COLOR_EMPTY)
                self._text_left(x0 + w - VOL_W + dp(16), y, VOL_W,
                                f"{pct}%", COLOR_VOL)
            # fila GUARDAR (cursor 4): botón de abajo para persistir; en
            # verde (acción) cuando está seleccionada, gris si no.
            y = top - 6 * ROW_H
            if self.cursor == self.SAVE_ROW:
                Color(*COLOR_ROW_CURSOR)
                Rectangle(pos=(x0, y), size=(w, ROW_H - dp(8)))
                Color(*COLOR_OK)
                RoundedRectangle(pos=(x0 + dp(3), y + dp(3)),
                                 size=(w - dp(6), ROW_H - dp(14)),
                                 radius=[dp(6)])
                Color(*COLOR_ROW_CURSOR)
                RoundedRectangle(pos=(x0 + dp(7), y + dp(7)),
                                 size=(w - dp(14), ROW_H - dp(22)),
                                 radius=[dp(4)])
                self._text_center(x0, y, w, "GUARDAR", COLOR_OK, h=ROW_H)
            else:
                self._text_center(x0, y, w, "GUARDAR", COLOR_HINT, h=ROW_H)
