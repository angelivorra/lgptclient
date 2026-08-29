"""Diálogo modal de confirmación (cambios sin guardar).

Se superpone a todo con un velo semitransparente y un panel central con un
mensaje y varios botones. Se maneja con botones lógicos: izq/dcha mueven la
selección, A confirma, B/BACK cancelan. La app enruta la entrada aquí mientras
el diálogo está visible.
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label

from theme import COLOR_ACCENT, COLOR_BAR_BG, COLOR_BG, COLOR_BTN

PANEL_W = dp(600)
PANEL_H = dp(220)


class _Btn(Label):
    def __init__(self, **kw):
        super().__init__(bold=True, font_size=dp(20), halign="center",
                         valign="middle", **kw)
        with self.canvas.before:
            self._c = Color(*COLOR_BTN)
            self._r = RoundedRectangle(radius=[dp(8)])
        self.bind(pos=self._sync, size=self._sync)

    def _sync(self, *_):
        self.text_size = self.size
        self._r.pos = (self.x + dp(6), self.y + dp(6))
        self._r.size = (self.width - dp(12), self.height - dp(12))

    def set_selected(self, sel):
        self._c.rgba = COLOR_ACCENT if sel else COLOR_BTN
        self.color = COLOR_BG if sel else (0.87, 0.89, 0.92, 1)


class ConfirmDialog(FloatLayout):
    def __init__(self, message, options, on_proceed, selected=0, **kw):
        super().__init__(**kw)
        self.options = options            # list[(key, label)]
        self.on_proceed = on_proceed
        self.index = selected

        with self.canvas.before:
            Color(0, 0, 0, 0.6)           # velo
            self._scrim = Rectangle()
        self.bind(pos=self._sync_scrim, size=self._sync_scrim)

        panel = BoxLayout(orientation="vertical", size_hint=(None, None),
                          size=(PANEL_W, PANEL_H), padding=dp(24),
                          spacing=dp(16), pos_hint={"center_x": 0.5,
                                                    "center_y": 0.5})
        with panel.canvas.before:
            Color(*COLOR_BAR_BG)
            panel._bg = RoundedRectangle(radius=[dp(14)])
        panel.bind(pos=lambda w, *_: setattr(w._bg, "pos", w.pos),
                   size=lambda w, *_: setattr(w._bg, "size", w.size))

        msg = Label(text=message, font_size=dp(22), bold=True,
                    halign="center", valign="middle", color=COLOR_ACCENT)
        msg.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        panel.add_widget(msg)

        row = BoxLayout(orientation="horizontal", spacing=dp(12),
                        size_hint_y=None, height=dp(64))
        self._btns = []
        for _key, label in options:
            b = _Btn(text=label)
            row.add_widget(b)
            self._btns.append(b)
        panel.add_widget(row)

        self.add_widget(panel)
        self._refresh()

    def _sync_scrim(self, *_):
        self._scrim.pos = self.pos
        self._scrim.size = self.size

    def move(self, delta):
        self.index = (self.index + delta) % len(self.options)
        self._refresh()

    def selected_key(self):
        return self.options[self.index][0]

    def _refresh(self):
        for i, b in enumerate(self._btns):
            b.set_selected(i == self.index)
