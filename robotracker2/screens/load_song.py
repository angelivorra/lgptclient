"""Pantalla de cargar canción: lista vertical, cursor oro, flechas + A.

El input lo centraliza la App (robotracker2.py); esta pantalla solo mantiene la
selección (self.index) y se redibuja. Con pocas canciones la lista se centra;
si no caben, una ventana de scroll (`_visible` / `_ensure_visible`, como los
navegadores) sigue al cursor. Wrap al llegar a los extremos.
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen

from songs import display_name
from theme import COLOR_ACCENT, COLOR_BAR_TEXT, COLOR_BG

ROW_H = dp(44)
TITLE_H = dp(60)


class SongRow(Label):
    """Fila de la lista: fondo oro cuando está seleccionada."""

    def __init__(self, **kw):
        super().__init__(bold=True, font_size=dp(22), halign="center",
                         valign="middle", size_hint=(None, None),
                         height=ROW_H, **kw)
        with self.canvas.before:
            self._bg_color = Color(0, 0, 0, 0)
            self._bg = RoundedRectangle(radius=[dp(8)])
        self.bind(pos=self._sync, size=self._sync)
        self.set_selected(False)

    def _sync(self, *_):
        self.text_size = self.size
        self._bg.pos = (self.x + dp(40), self.y + dp(4))
        self._bg.size = (max(self.width - dp(80), 0), self.height - dp(8))

    def set_selected(self, selected):
        self._bg_color.rgba = COLOR_ACCENT if selected else (0, 0, 0, 0)
        self.color = COLOR_BG if selected else COLOR_BAR_TEXT


class LoadSongScreen(Screen):
    def __init__(self, songs, **kw):
        super().__init__(**kw)
        self.songs = songs
        self.index = 0
        self.top_idx = 0
        self._rows = []

        with self.canvas.before:
            Color(*COLOR_BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._sync_bg, size=self._sync_bg)

        self._title = Label(text="CARGAR CANCION", bold=True,
                            color=COLOR_ACCENT, font_size=dp(28),
                            size_hint=(1, None), height=TITLE_H,
                            pos_hint={"top": 1})
        self.add_widget(self._title)

        for song in self.songs:
            row = SongRow(text=display_name(song.name))
            self._rows.append(row)
            self.add_widget(row)

        self.bind(size=self._relayout, pos=self._relayout)

    # -- dibujo ---------------------------------------------------------
    def _sync_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _visible(self):
        return max(1, int((self.height - TITLE_H - dp(16)) // ROW_H))

    def _ensure_visible(self):
        n = self._visible()
        if self.index < self.top_idx:
            self.top_idx = self.index
        elif self.index >= self.top_idx + n:
            self.top_idx = self.index - n + 1
        max_top = max(0, len(self._rows) - n)
        self.top_idx = max(0, min(self.top_idx, max_top))

    def _relayout(self, *_):
        n = len(self._rows)
        if not n:
            return
        n_vis = self._visible()
        self._ensure_visible()
        if n <= n_vis:
            total = n * ROW_H
            top = self.center_y + total / 2 - ROW_H
            start, count = 0, n
        else:
            top = self.y + self.height - TITLE_H - ROW_H
            start, count = self.top_idx, n_vis
        for i, row in enumerate(self._rows):
            row.width = self.width
            row.x = self.x
            vis = start <= i < start + count
            row.opacity = 1 if vis else 0
            row.y = top - (i - start) * ROW_H if vis else self.y - ROW_H
            row.set_selected(i == self.index)

    # -- navegación -----------------------------------------------------
    def move(self, delta):
        if not self.songs:
            return
        self.index = (self.index + delta) % len(self.songs)
        self._relayout()

    def selected(self):
        return self.songs[self.index]

    def on_pre_enter(self, *_):
        self._relayout()
