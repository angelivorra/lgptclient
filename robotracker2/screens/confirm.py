"""Diálogo modal de confirmación (cambios sin guardar).

Se superpone a todo con un velo semitransparente y un panel central con un
mensaje y varios botones (icono Phosphor + etiqueta). Se maneja con
botones lógicos (izq/dcha, A, B/BACK) y también con clic/toque: un tap
en un botón lo elige; un tap en el velo cancela.
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.widget import Widget

from screens.icons import draw_icon
from theme import (COLOR_ACCENT, COLOR_BAR_BG, COLOR_BG, COLOR_CELL,
                   COLOR_ERROR, COLOR_OK, COLOR_SCRIM, core_label)

PANEL_W = dp(640)
PANEL_H = dp(260)
BTN_ICON = {
    "save": "save",
    "discard": "discard",
    "cancel": "cancel",
    "yes": "yes",
    "no": "no",
}
_BTN_BG = (0.22, 0.22, 0.23, 1)


class _Btn(Widget):
    def __init__(self, key, label, index, on_tap, **kw):
        super().__init__(**kw)
        self.key = key
        self.label = label
        self.index = index
        self.on_tap = on_tap
        self._sel = False
        self._tex = None
        self.bind(pos=self._redraw, size=self._redraw)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        touch.grab(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is not self:
            return False
        touch.ungrab(self)
        if self.collide_point(*touch.pos) and self.on_tap:
            self.on_tap(self.index)
        return True

    def set_selected(self, sel):
        if sel != self._sel:
            self._sel = sel
            self._redraw()

    def _label_tex(self):
        if self._tex is None:
            self._tex = core_label(self.label, dp(18)).texture
        return self._tex

    def _redraw(self, *_):
        self.canvas.clear()
        if self.width < 2 or self.height < 2:
            return
        danger = self.key in ("discard", "no", "exit")
        ok = self.key in ("save", "yes")
        if self._sel:
            bg = COLOR_ACCENT
            ink = COLOR_BG
        elif danger:
            bg = (0.22, 0.10, 0.10, 1)
            ink = COLOR_ERROR
        elif ok:
            bg = (0.10, 0.20, 0.12, 1)
            ink = COLOR_OK
        else:
            bg = _BTN_BG
            ink = COLOR_CELL
        pad = dp(6)
        rx, ry = self.x + pad, self.y + pad
        rw, rh = self.width - pad * 2, self.height - pad * 2
        with self.canvas:
            Color(*bg)
            RoundedRectangle(pos=(rx, ry), size=(rw, rh), radius=[dp(12)])
            icon = BTN_ICON.get(self.key, "cancel")
            icon_s = dp(22)
            tex = self._label_tex()
            tw, th = tex.size
            gap = dp(8)
            block = icon_s + gap + th
            top = ry + (rh + block) / 2
            draw_icon(rx + rw / 2, top - icon_s / 2, icon_s, icon, ink)
            Color(*ink)
            Rectangle(texture=tex, size=(tw, th),
                      pos=(rx + (rw - tw) / 2, top - block))


class ConfirmDialog(FloatLayout):
    def __init__(self, message, options, on_proceed, selected=0,
                 on_choose=None, on_cancel=None, **kw):
        super().__init__(**kw)
        self.options = options            # list[(key, label)]
        self.on_proceed = on_proceed
        self.on_choose = on_choose        # tap/A: elige el botón del cursor
        self.on_cancel = on_cancel        # tap en el velo / B
        self.index = selected

        with self.canvas.before:
            Color(*COLOR_SCRIM)
            self._scrim = Rectangle()
        self.bind(pos=self._sync_scrim, size=self._sync_scrim)

        panel = BoxLayout(orientation="vertical", size_hint=(None, None),
                          size=(PANEL_W, PANEL_H), padding=dp(24),
                          spacing=dp(16), pos_hint={"center_x": 0.5,
                                                    "center_y": 0.5})
        with panel.canvas.before:
            Color(*COLOR_BAR_BG)
            panel._bg = RoundedRectangle(radius=[dp(16)])
        panel.bind(pos=lambda w, *_: setattr(w._bg, "pos", w.pos),
                   size=lambda w, *_: setattr(w._bg, "size", w.size))
        self._panel = panel

        from kivy.uix.label import Label
        msg = Label(text=message, font_size=dp(22), bold=True,
                    halign="center", valign="middle", color=COLOR_ACCENT)
        msg.bind(size=lambda w, *_: setattr(w, "text_size", w.size))
        panel.add_widget(msg)

        row = BoxLayout(orientation="horizontal", spacing=dp(10),
                        size_hint_y=None, height=dp(88))
        self._btns = []
        for i, (key, label) in enumerate(options):
            b = _Btn(key, label, i, self._tap_btn)
            row.add_widget(b)
            self._btns.append(b)
        panel.add_widget(row)

        self.add_widget(panel)
        self._refresh()

    def on_touch_down(self, touch):
        for b in self._btns:
            if b.collide_point(*touch.pos):
                return b.on_touch_down(touch)
        touch.grab(self)
        return True

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            if (self.on_cancel
                    and not self._panel.collide_point(*touch.pos)):
                self.on_cancel()
            return True
        for b in self._btns:
            if b.on_touch_up(touch):
                return True
        return True

    def _tap_btn(self, index):
        self.index = index
        self._refresh()
        if self.on_choose:
            self.on_choose()

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
