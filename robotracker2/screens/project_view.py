"""Pantalla PROJECT: menú de ajustes y acciones de la canción.

Versión reducida de la pantalla Project de LGPT (sin Drive/Type/Transpose/
Scale/MIDI/Render). Campos:

  Tempo / Master        -> valores editables (izq/dcha ±1, A+izq/dcha ±10)
  Compact Sequencer / Compact Instruments  -> acciones (Save Song As: pendiente)
  Load Song / Save Song / Save Song As     -> acciones
  Exit                                      -> salir

El cursor (arriba/abajo) salta los separadores. A (tap) activa la acción; en un
valor no hace nada. Editar un valor muta `project.project` y marca dirty.
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from theme import COLOR_ACCENT, COLOR_BG, COLOR_ITEM, COLOR_VALUE

FONT = dp(24)
ITEM_H = dp(42)
GAP = dp(22)
PAD_TOP = dp(48)

# (clave, tipo, etiqueta); tipo: "value" | "action" | "gap"
ITEMS = [
    ("tempo", "value", "Tempo"),
    ("master", "value", "Master"),
    (None, "gap", None),
    ("compact_seq", "action", "Compact Sequencer"),
    ("compact_instr", "action", "Compact Instruments"),
    (None, "gap", None),
    ("load", "action", "Load Song"),
    ("save", "action", "Save Song"),
    ("save_as", "action", "Save Song As"),
    (None, "gap", None),
    ("exit", "action", "Exit"),
]

# límites de los valores editables
LIMITS = {"tempo": (10, 255), "master": (0, 255)}


class ProjectMenu(Widget):
    def __init__(self, on_action=None, on_change=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.on_action = on_action
        self.on_change = on_change
        self.index = self._first_selectable()
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    # -- estado ---------------------------------------------------------
    def set_project(self, project):
        self.project = project
        self.index = self._first_selectable()
        self._redraw()

    def _first_selectable(self):
        return next(i for i, it in enumerate(ITEMS) if it[1] != "gap")

    # -- navegación / edición ------------------------------------------
    def move(self, delta):
        i = self.index
        while True:
            i = (i + delta) % len(ITEMS)
            if ITEMS[i][1] != "gap":
                break
        self.index = i
        self._redraw()

    def adjust(self, delta, coarse=False):
        key, typ, _ = ITEMS[self.index]
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

    def activate(self):
        key, typ, _ = ITEMS[self.index]
        if typ == "action" and self.on_action:
            self.on_action(key)

    # -- dibujo ---------------------------------------------------------
    def _display(self, key, typ, label):
        if typ == "value" and self.project is not None:
            val = int(self.project.project.get(key, "0"))
            if key == "tempo":
                return f"{label}: {val}  [{val:02X}]"
            return f"{label}: {val}"
        return label

    def _texture(self, text):
        tex = self._tex.get(text)
        if tex is None:
            lbl = CoreLabel(text=text, font_size=FONT, bold=True)
            lbl.refresh()
            tex = lbl.texture
            self._tex[text] = tex
        return tex

    def _redraw(self, *_):
        self.canvas.clear()
        # bloque centrado: ancho = la etiqueta más ancha, alineadas a su izq.
        maxw = dp(1)
        for key, typ, label in ITEMS:
            if typ != "gap":
                maxw = max(maxw,
                           self._texture(self._display(key, typ, label)).size[0])
        x0 = self.center_x - maxw / 2
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            y = self.y + self.height - PAD_TOP
            for i, (key, typ, label) in enumerate(ITEMS):
                if typ == "gap":
                    y -= GAP
                    continue
                tex = self._texture(self._display(key, typ, label))
                tw, th = tex.size
                selected = (i == self.index)
                if selected:
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(x0 - dp(12), y - dp(6)),
                                     size=(tw + dp(24), th + dp(12)),
                                     radius=[dp(8)])
                    color = COLOR_BG
                elif typ == "value":
                    color = COLOR_VALUE
                else:
                    color = COLOR_ITEM
                Color(*color)
                Rectangle(texture=tex, size=(tw, th), pos=(x0, y))
                y -= ITEM_H
