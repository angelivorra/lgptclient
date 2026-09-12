"""Pantalla PROJECT: menú de ajustes y acciones de la canción.

Versión reducida de la pantalla Project de LGPT (sin Drive/Type/Transpose/
Scale/MIDI/Render). Campos:

  Tempo / Master        -> valores editables (izq/dcha ±1; A+izq/dcha ±1,
                            A+arr/abj ±10, como en el resto)
  Compact Sequencer / Compact Instruments  -> acciones (Save Song As: pendiente)
  Load Song / Save Song / Save Song As     -> acciones
  Exit                                      -> salir

Cada acción es un botón con icono Phosphor. El cursor (arriba/abajo) salta
los separadores. A (tap) activa la acción; en un valor no hace nada.
Editar un valor muta `project.project` y marca dirty.
"""

from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from screens.icons import draw_icon
from theme import (COLOR_ACCENT, COLOR_BG, COLOR_ERROR, COLOR_HEADER_BG,
                   COLOR_ITEM, COLOR_VALUE, core_label)

FONT = dp(20)
FONT_VAL = dp(18)
PAD = dp(24)
GAP = dp(14)

# (clave, tipo, etiqueta, icono Phosphor); tipo: "value" | "action" | "gap"
ITEMS = [
    ("tempo", "value", "Tempo", "tempo"),
    ("master", "value", "Master", "master"),
    (None, "gap", None, None),
    ("compact_seq", "action", "Compactar secuencia", "compact_seq"),
    ("compact_instr", "action", "Compactar instrumentos", "compact_instr"),
    (None, "gap", None, None),
    ("load", "action", "Cargar", "load"),
    ("save", "action", "Guardar", "save"),
    ("save_as", "action", "Guardar como", "save_as"),
    (None, "gap", None, None),
    ("exit", "action", "Salir", "exit"),
]

LIMITS = {"tempo": (10, 255), "master": (0, 255)}
_BTN_BG = (0.14, 0.14, 0.15, 1)
_BTN_EXIT = (0.22, 0.10, 0.10, 1)


class ProjectMenu(Widget):
    def __init__(self, on_action=None, on_change=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.on_action = on_action
        self.on_change = on_change
        self.index = self._first_selectable()
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_project(self, project):
        self.project = project
        self.index = self._first_selectable()
        self._redraw()

    def _first_selectable(self):
        return next(i for i, it in enumerate(ITEMS) if it[1] != "gap")

    def current_item(self):
        return ITEMS[self.index]

    def move(self, delta):
        i = self.index
        while True:
            i = (i + delta) % len(ITEMS)
            if ITEMS[i][1] != "gap":
                break
        self.index = i
        self._redraw()

    def adjust(self, delta, coarse=False):
        key, typ, _label, _icon = ITEMS[self.index]
        if typ != "value" or self.project is None:
            return
        step = 10 if coarse else 1
        lo, hi = LIMITS[key]
        cur = int(self.project.project.get(key, "0"))
        cur = max(lo, min(hi, cur + delta * step))
        self.project.project[key] = str(cur)
        if self.on_change:
            self.on_change()
        self._redraw()

    def adjust_by(self, amount):
        """Suma `amount` al valor (A+dir: ±1 / ±10)."""
        key, typ, _label, _icon = ITEMS[self.index]
        if typ != "value" or self.project is None:
            return
        lo, hi = LIMITS[key]
        cur = int(self.project.project.get(key, "0"))
        cur = max(lo, min(hi, cur + amount))
        self.project.project[key] = str(cur)
        if self.on_change:
            self.on_change()
        self._redraw()

    def activate(self):
        key, typ, _label, _icon = ITEMS[self.index]
        if typ == "action" and self.on_action:
            self.on_action(key)

    def _value_text(self, key):
        val = int(self.project.project.get(key, "0")) if self.project else 0
        if key == "tempo":
            return f"{val}  [{val:02X}]"
        return str(val)

    def _texture(self, text, font_size=FONT):
        key = (text, font_size)
        tex = self._tex.get(key)
        if tex is None:
            tex = core_label(text, font_size).texture
            self._tex[key] = tex
        return tex

    def _redraw(self, *_):
        self.canvas.clear()
        n_btns = sum(1 for it in ITEMS if it[1] != "gap")
        n_gaps = sum(1 for it in ITEMS if it[1] == "gap")
        avail = max(dp(200), self.height - PAD * 2)
        btn_h = min(dp(56), max(dp(40),
                                (avail - n_gaps * GAP) / n_btns))
        btn_w = min(self.width - dp(48), dp(560))
        x0 = self.x + (self.width - btn_w) / 2
        radius = dp(12)
        icon_s = min(dp(26), btn_h * 0.48)
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            y = self.y + self.height - PAD - btn_h
            for i, (key, typ, label, icon) in enumerate(ITEMS):
                if typ == "gap":
                    y -= GAP
                    continue
                selected = (i == self.index)
                self._draw_button(x0, y, btn_w, btn_h - dp(6), radius,
                                  key, typ, label, icon, selected, icon_s)
                y -= btn_h

    def _draw_button(self, x, y, w, h, radius, key, typ, label, icon,
                     selected, icon_s):
        if selected:
            bg = COLOR_ACCENT
            ink = COLOR_BG
            val_ink = COLOR_BG
        elif key == "exit":
            bg = _BTN_EXIT
            ink = COLOR_ERROR
            val_ink = COLOR_ERROR
        elif typ == "value":
            bg = COLOR_HEADER_BG
            ink = COLOR_ITEM
            val_ink = COLOR_VALUE
        else:
            bg = _BTN_BG
            ink = COLOR_ITEM
            val_ink = COLOR_VALUE
        Color(*bg)
        RoundedRectangle(pos=(x, y), size=(w, h), radius=[radius])
        cx = x + dp(18) + icon_s / 2
        cy = y + h / 2
        draw_icon(cx, cy, icon_s, icon, ink)
        tx = x + dp(18) + icon_s + dp(12)
        tex = self._texture(label)
        tw, th = tex.size
        Color(*ink)
        Rectangle(texture=tex, size=(tw, th),
                  pos=(tx, y + (h - th) / 2))
        if typ == "value":
            vtex = self._texture(self._value_text(key), FONT_VAL)
            vw, vh = vtex.size
            Color(*val_ink)
            Rectangle(texture=vtex, size=(vw, vh),
                      pos=(x + w - vw - dp(18), y + (h - vh) / 2))
