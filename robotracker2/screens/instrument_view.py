"""Pantalla INSTRUMENT: parámetros del instrumento (menú moderno con scroll).

Adaptación libre del instrument de LGPT. Arr/abj mueve entre campos (con scroll),
izq/dcha edita (A+izq/dcha = paso grande). El instrumento se elige en el primer
campo (o viene del step de PHRASE). En "Sample", A abre el navegador de samples.
Se editan los params útiles incluyendo el efecto (Print FX / FX amount); el resto
de params se conservan al guardar (writer actualiza VALUE en sitio).
"""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from controls import DOWN, LEFT, RIGHT, UP
from sinte_bridge import note_byte_to_name
from theme import COLOR_ACCENT, COLOR_BG

FONT = dp(22)
ITEM_H = dp(38)
PAD_TOP = dp(30)

COLOR_LABEL = (0.87, 0.89, 0.92, 1)
COLOR_VALUE = (0.55, 0.82, 0.55, 1)

# Valores de los campos enum (se conserva el actual si no está en la lista).
ENUMS = {
    "filter mode": ["original", "bassy", "scream"],
    "loopmode": ["none", "loop"],
    "print fx": ["none", "church", "hall"],
    "interpol": ["linear", "none"],
    "table automation": ["false", "true"],
}

# (clave, etiqueta, tipo, *args). tipos: instr | sample | note | enum | int(min,max)
FIELDS = [
    ("__instr__", "Instrument", "instr"),
    ("sample", "Sample", "sample"),
    ("volume", "Volume", "int", 0, 255),
    ("pan", "Pan", "int", 0, 255),
    ("fine tune", "Fine tune", "int", 0, 255),
    ("root note", "Root note", "note"),
    ("filter cut", "Filter cut", "int", 0, 255),
    ("filter res", "Filter res", "int", 0, 255),
    ("filter type", "Filter type", "int", 0, 255),
    ("filter mode", "Filter mode", "enum"),
    ("crush", "Crush", "int", 1, 16),
    ("downsample", "Downsample", "int", 0, 16),
    ("loopmode", "Loop", "enum"),
    ("print fx", "Print FX", "enum"),
    ("effect amount", "FX amount", "int", 0, 255),
    ("feedback mix", "Feedback mix", "int", 0, 255),
    ("table", "Table", "int", -1, 0x7F),
]


class InstrumentMenu(Widget):
    def __init__(self, on_change=None, on_nav=None, on_pick_sample=None, **kw):
        super().__init__(**kw)
        self.project = None
        self.instr_ids = []
        self.pos_in_ids = 0
        self.index = 0
        self.top_idx = 0                   # primer campo visible (scroll)
        self.on_change = on_change
        self.on_nav = on_nav
        self.on_pick_sample = on_pick_sample
        self._tex = {}
        self.bind(pos=self._redraw, size=self._redraw)

    def set_project(self, project):
        self.project = project
        self.instr_ids = sorted(project.instrument_bank)
        self.pos_in_ids = 0
        self.index = 0
        self.top_idx = 0
        self._redraw()

    @property
    def instr_id(self):
        return self.instr_ids[self.pos_in_ids] if self.instr_ids else 0

    def instr_label(self):
        return f"{self.instr_id:02X}" if self.instr_ids else "--"

    def select_instrument(self, iid):
        if iid in self.instr_ids:
            self.pos_in_ids = self.instr_ids.index(iid)
            self.index = 0
            self.top_idx = 0
            self._redraw()

    def field_key(self):
        return FIELDS[self.index][0]

    def _params(self):
        if not self.instr_ids:
            return {}
        return self.project.instrument_bank[self.instr_id]["params"]

    # -- navegación / edición ------------------------------------------
    def move(self, button):
        if button == UP:
            self.index = max(0, self.index - 1)
        elif button == DOWN:
            self.index = min(len(FIELDS) - 1, self.index + 1)
        elif button in (LEFT, RIGHT):
            self._adjust(1 if button == RIGHT else -1, coarse=False)
        self._ensure_visible()
        self._redraw()

    def edit(self, button):
        if button in (LEFT, RIGHT):
            self._adjust(1 if button == RIGHT else -1, coarse=True)
            self._redraw()

    def _adjust(self, d, coarse):
        field = FIELDS[self.index]
        key, typ = field[0], field[2]
        if typ == "instr":
            if self.instr_ids:
                self.pos_in_ids = (self.pos_in_ids + d) % len(self.instr_ids)
                self.index = 0
                self.top_idx = 0
                if self.on_nav:
                    self.on_nav()
            return
        if typ == "sample":
            return                                   # el sample se elige con A
        params = self._params()
        if not params:
            return
        if typ == "enum":
            base = ENUMS.get(key, [])
            cur = params.get(key, base[0] if base else "")
            lst = base if cur in base else ([cur] + base)
            params[key] = lst[(lst.index(cur) + d) % len(lst)]
        elif typ == "note":
            cur = int(params.get(key, "60") or 0)
            params[key] = str(max(0, min(127, cur + d * (12 if coarse else 1))))
        else:  # int
            lo, hi = field[3], field[4]
            cur = int(params.get(key, str(lo)) or 0)
            params[key] = str(max(lo, min(hi, cur + d * (16 if coarse else 1))))
        if self.on_change:
            self.on_change()

    def activate(self):
        # A sobre el campo Sample abre el navegador de samples.
        if self.field_key() == "sample" and self.on_pick_sample:
            self.on_pick_sample()

    def set_sample(self, name):
        params = self._params()
        if params:
            params["sample"] = name
            if self.on_change:
                self.on_change()
            self._redraw()

    # -- scroll ---------------------------------------------------------
    def _visible(self):
        return max(1, int((self.height - PAD_TOP) // ITEM_H))

    def _ensure_visible(self):
        n = self._visible()
        if self.index < self.top_idx:
            self.top_idx = self.index
        elif self.index >= self.top_idx + n:
            self.top_idx = self.index - n + 1
        self.top_idx = max(0, min(self.top_idx, max(0, len(FIELDS) - n)))

    # -- dibujo ---------------------------------------------------------
    def _value_text(self, field):
        key, typ = field[0], field[2]
        if typ == "instr":
            return self.instr_label()
        params = self._params()
        if typ == "sample":
            s = params.get("sample", "--")
            return s if len(s) <= 24 else s[:23] + "…"
        if typ == "note":
            try:
                return note_byte_to_name(int(params.get(key, "60")))
            except (ValueError, TypeError):
                return params.get(key, "--")
        return params.get(key, "--")

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
        if self.project is None:
            return
        rows = [(f[1], self._value_text(f)) for f in FIELDS]
        label_w = max(self._texture(l).size[0] for l, _v in rows)
        gap = dp(24)
        block_w = label_w + gap + dp(200)
        x0 = self.center_x - block_w / 2
        xval = x0 + label_w + gap
        n = self._visible()
        with self.canvas:
            Color(*COLOR_BG)
            Rectangle(pos=self.pos, size=self.size)
            y = self.y + self.height - PAD_TOP
            for i in range(self.top_idx, min(self.top_idx + n, len(FIELDS))):
                label, value = rows[i]
                if i == self.index:
                    Color(*COLOR_ACCENT)
                    RoundedRectangle(pos=(x0 - dp(12), y - dp(4)),
                                     size=(block_w + dp(24), ITEM_H - dp(6)),
                                     radius=[dp(8)])
                lab_c = COLOR_BG if i == self.index else COLOR_LABEL
                val_c = COLOR_BG if i == self.index else COLOR_VALUE
                self._draw(x0, y, label, lab_c)
                self._draw(xval, y, value, val_c)
                y -= ITEM_H

    def _draw(self, x, y, text, color):
        tex = self._texture(text)
        Color(*color)
        Rectangle(texture=tex, size=tex.size,
                  pos=(x, y + (ITEM_H - tex.size[1]) / 2 - dp(3)))
