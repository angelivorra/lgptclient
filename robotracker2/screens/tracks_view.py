"""Pantalla TRACKS: tipo (icono + nombre) de cada pista, por canción.

Ocho filas (canales 1-8) más GUARDAR. Cada pista elige un tipo de
`TRACK_KINDS` (drum / bass / synth / noise / robot / vocoder): el icono
y el nombre van juntos. Se persiste en la clave "tracks" del
robotraca.json; vive en memoria hasta la fila GUARDAR o Guardar canción.

Controles (los resuelve la app en `_dispatch_tracks`):

- arr/abj: cambiar de pista (y bajar a GUARDAR)
- izq/dcha: ciclar el tipo
- A sobre GUARDAR: persiste
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, UP
from lgpt_model import NUM_TRACKS
from screens.track_icons import draw_track_icon
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_HINT, COLOR_HINT_BG,
                   COLOR_NAME, COLOR_OK, COLOR_ROW_CURSOR, COLOR_SONG_TRACK,
                   core_label)
from tracks import DEFAULT_TRACKS, TRACK_KINDS, track_caption

ROW_H = dp(44)
FONT = dp(18)
FONT_SMALL = dp(15)
HINT_H = dp(36)
SAVE_ROW = NUM_TRACKS


class TracksGrid(Widget):
    SAVE_ROW = SAVE_ROW

    def __init__(self, **kw):
        super().__init__(**kw)
        self.kinds = list(DEFAULT_TRACKS)
        self.cursor = 0
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_state(self, kinds):
        kinds = list(kinds)
        if kinds != self.kinds:
            self.kinds = kinds
            self._redraw()

    def move(self, button):
        if button == UP:
            self.cursor = max(0, self.cursor - 1)
        elif button == DOWN:
            self.cursor = min(self.SAVE_ROW, self.cursor + 1)
        self._redraw()

    def cycle(self, delta):
        """Cicla el tipo de la pista del cursor. False en la fila GUARDAR."""
        if not 0 <= self.cursor < NUM_TRACKS:
            return False
        i = TRACK_KINDS.index(self.kinds[self.cursor]) \
            if self.kinds[self.cursor] in TRACK_KINDS else 0
        self.kinds[self.cursor] = TRACK_KINDS[(i + delta) % len(TRACK_KINDS)]
        self._redraw()
        return True

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
            w = min(self.width - dp(60), dp(520))
            x0 = self.x + (self.width - w) / 2
            top = self.y + self.height - dp(16)
            self._text_left(x0, top - ROW_H, w, "TRACKS", COLOR_ACCENT,
                            h=ROW_H)
            hint = "arr/abj: pista · izq/dcha: tipo · A: guardar"
            avail = top - ROW_H - HINT_H - dp(8)
            row_h = min(ROW_H, max(dp(28), avail / (NUM_TRACKS + 1)))
            y = top - ROW_H - row_h
            for t in range(NUM_TRACKS):
                selected = t == self.cursor
                if selected:
                    Color(*COLOR_ROW_CURSOR)
                    Rectangle(pos=(x0, y), size=(w, row_h))
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(x0 + dp(2), y + dp(3)),
                                     size=(w - dp(4), row_h - dp(6)),
                                     radius=[dp(6)])
                    Color(*COLOR_ROW_CURSOR)
                    RoundedRectangle(pos=(x0 + dp(6), y + dp(7)),
                                     size=(w - dp(12), row_h - dp(14)),
                                     radius=[dp(4)])
                Color(*COLOR_SONG_TRACK[t])
                Rectangle(pos=(x0, y + dp(6)), size=(dp(4), row_h - dp(12)))
                ink = COLOR_ACCENT if selected else COLOR_NAME
                kind = self.kinds[t]
                s = row_h * 0.62
                draw_track_icon(x0 + dp(28) + s / 2, y + row_h / 2, s, kind,
                                ink, bg=COLOR_ROW_CURSOR if selected
                                else COLOR_BG)
                self._text_left(x0 + dp(28) + s + dp(12), y, w,
                                track_caption(t, kind), ink,
                                h=row_h)
                y -= row_h
            y_save = y
            if self.cursor == self.SAVE_ROW:
                Color(*COLOR_ROW_CURSOR)
                Rectangle(pos=(x0, y_save), size=(w, row_h))
                Color(*COLOR_OK)
                RoundedRectangle(pos=(x0 + dp(3), y_save + dp(3)),
                                 size=(w - dp(6), row_h - dp(6)),
                                 radius=[dp(6)])
                Color(*COLOR_ROW_CURSOR)
                RoundedRectangle(pos=(x0 + dp(7), y_save + dp(7)),
                                 size=(w - dp(14), row_h - dp(14)),
                                 radius=[dp(4)])
                self._text_center(x0, y_save, w, "GUARDAR", COLOR_OK,
                                  h=row_h)
            else:
                self._text_center(x0, y_save, w, "GUARDAR", COLOR_HINT,
                                  h=row_h)
            Color(*COLOR_HINT_BG)
            Rectangle(pos=(self.x, self.y), size=(self.width, HINT_H))
            self._text_left(x0, self.y, w, hint, COLOR_HINT,
                            h=HINT_H, font_size=FONT_SMALL)
